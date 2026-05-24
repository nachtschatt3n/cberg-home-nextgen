<?php

declare(strict_types=1);

namespace OCA\OpenclawMail\Controller;

use Horde_Imap_Client;
use Horde_Mail_Transport_Null;
use Horde_Mime_Headers_Date;
use Horde_Mime_Headers_MessageId;
use Horde_Mime_Mail;
use OCA\Mail\Address;
use OCA\Mail\AddressList;
use OCA\Mail\Db\MailboxMapper;
use OCA\Mail\IMAP\IMAPClientFactory;
use OCA\Mail\IMAP\MessageMapper;
use OCA\Mail\Service\AccountService;
use OCA\Mail\Service\DataUri\DataUriParser;
use OCA\Mail\Service\MimeMessage;
use OCA\Mail\Service\TransmissionService;
use OCP\AppFramework\Controller;
use OCP\AppFramework\Http;
use OCP\AppFramework\Http\JSONResponse;
use OCP\IRequest;
use OCP\IUserSession;
use Psr\Log\LoggerInterface;
use Throwable;

class DraftController extends Controller {
    public function __construct(
        string $appName,
        IRequest $request,
        private AccountService $accountService,
        private TransmissionService $transmissionService,
        private IMAPClientFactory $imapClientFactory,
        private MessageMapper $messageMapper,
        private MailboxMapper $mailboxMapper,
        private IUserSession $userSession,
        private LoggerInterface $logger,
    ) {
        parent::__construct($appName, $request);
    }

    /**
     * @NoAdminRequired
     * @NoCSRFRequired
     *
     * POST /apps/openclaw_mail/api/draft
     *
     * Body (JSON):
     *   {
     *     "accountId":  int,         // Nextcloud Mail account ID
     *     "subject":    string,
     *     "body":       string,      // text or HTML depending on isHtml
     *     "to":         string,      // comma-separated address list
     *     "cc":         string,
     *     "bcc":        string,
     *     "isHtml":     bool,        // default true
     *     "attachments": int[]|object[]   // NC Mail local-attachment IDs
     *                                     // (returned by POST /apps/mail/api/attachments)
     *                                     // bare ints or {"type":"local","id":N} both accepted
     *   }
     *
     * Returns JSON: { "success": true, "uid": int, "mailboxId": int,
     *                 "attachmentsAttached": int }
     */
    public function create(
        int $accountId,
        string $subject = '',
        string $body = '',
        string $to = '',
        string $cc = '',
        string $bcc = '',
        bool $isHtml = true,
        array $attachments = [],
    ): JSONResponse {
        $user = $this->userSession->getUser();
        if ($user === null) {
            return new JSONResponse(
                ['error' => 'no user session'],
                Http::STATUS_UNAUTHORIZED,
            );
        }

        try {
            $account = $this->accountService->find($user->getUID(), $accountId);
        } catch (Throwable $e) {
            return new JSONResponse(
                ['error' => 'account ' . $accountId . ' not found for user'],
                Http::STATUS_NOT_FOUND,
            );
        }

        // Normalize attachments to [{type:'local', id:int}, ...].
        // Accept bare ints, numeric strings, or already-shaped objects.
        $normalized = [];
        foreach ($attachments as $att) {
            if (is_int($att) || (is_string($att) && ctype_digit($att))) {
                $normalized[] = ['type' => 'local', 'id' => (int)$att];
            } elseif (is_array($att) && isset($att['id'])) {
                $normalized[] = [
                    'type' => isset($att['type']) ? (string)$att['type'] : 'local',
                    'id' => (int)$att['id'],
                ];
            }
        }

        // Build Horde MIME parts for every attachment using NC Mail's own
        // helper, which resolves the local attachment ID -> file content
        // and builds a properly-named Horde_Mime_Part.
        $attachmentParts = [];
        foreach ($normalized as $att) {
            try {
                $part = $this->transmissionService->handleAttachment($account, $att);
                if ($part !== null) {
                    $attachmentParts[] = $part;
                }
            } catch (Throwable $e) {
                $this->logger->error('openclaw_mail: handleAttachment failed for id ' . $att['id'] . ': ' . $e->getMessage(), [
                    'exception' => $e,
                ]);
            }
        }

        // Recipients
        $toList  = AddressList::parse($to);
        $ccList  = AddressList::parse($cc);
        $bccList = AddressList::parse($bcc);

        $from = Address::fromRaw($account->getName(), $account->getEMailAddress());

        $headers = [
            'From'    => $from->toHorde(),
            'To'      => $toList->toHorde(),
            'Cc'      => $ccList->toHorde(),
            'Bcc'     => $bccList->toHorde(),
            'Subject' => $subject,
            'Date'    => Horde_Mime_Headers_Date::create(),
        ];

        // Body — match the Outbox sendMessage path which keeps plain/html
        // separate and lets MimeMessage::build decide the multipart shape.
        $bodyPlain = $isHtml ? '' : $body;
        $bodyHtml  = $isHtml ? $body : '';

        // MimeMessage is constructed directly (matches sendMessage in
        // OCA\Mail\Service\MailTransmission) rather than DI — keeps us
        // independent of any registered overrides.
        $mimeMessage = new MimeMessage(new DataUriParser());
        $mimePart = $mimeMessage->build(
            $bodyPlain,
            $bodyHtml,
            $attachmentParts,
            false, // not PGP encrypted
        );

        $mail = new Horde_Mime_Mail();
        $mail->addHeaders($headers);
        $mail->setBasePart($mimePart);
        $mail->addHeaderOb(Horde_Mime_Headers_MessageId::create());

        // Serialize via a null transport — same trick saveDraft uses.
        try {
            $transport = new Horde_Mail_Transport_Null();
            $mail->send($transport, false, false);
        } catch (Throwable $e) {
            $this->logger->error('openclaw_mail: MIME serialization failed: ' . $e->getMessage(), [
                'exception' => $e,
            ]);
            return new JSONResponse(
                ['error' => 'mime build failed: ' . $e->getMessage()],
                Http::STATUS_INTERNAL_SERVER_ERROR,
            );
        }

        // Resolve the IMAP Drafts mailbox for this account.
        $draftsMailboxId = $account->getMailAccount()->getDraftsMailboxId();
        if ($draftsMailboxId === null) {
            return new JSONResponse(
                ['error' => 'no drafts mailbox configured on account ' . $accountId],
                Http::STATUS_INTERNAL_SERVER_ERROR,
            );
        }
        try {
            $draftsMailbox = $this->mailboxMapper->findById($draftsMailboxId);
        } catch (Throwable $e) {
            return new JSONResponse(
                ['error' => 'drafts mailbox ' . $draftsMailboxId . ' not found: ' . $e->getMessage()],
                Http::STATUS_INTERNAL_SERVER_ERROR,
            );
        }

        // APPEND to IMAP with the Draft flag — exactly what saveDraft does
        // for attachment-less drafts.
        $client = $this->imapClientFactory->getClient($account);
        try {
            $newUid = $this->messageMapper->save(
                $client,
                $draftsMailbox,
                $mail->getRaw(false),
                [Horde_Imap_Client::FLAG_DRAFT],
            );
        } catch (Throwable $e) {
            $this->logger->error('openclaw_mail: IMAP APPEND failed: ' . $e->getMessage(), [
                'exception' => $e,
                'accountId' => $accountId,
                'mailboxId' => $draftsMailboxId,
            ]);
            return new JSONResponse(
                ['error' => 'imap append failed: ' . $e->getMessage()],
                Http::STATUS_INTERNAL_SERVER_ERROR,
            );
        } finally {
            $client->logout();
        }

        return new JSONResponse([
            'success'             => true,
            'uid'                 => $newUid,
            'mailboxId'           => $draftsMailboxId,
            'attachmentsAttached' => count($attachmentParts),
        ]);
    }
}
