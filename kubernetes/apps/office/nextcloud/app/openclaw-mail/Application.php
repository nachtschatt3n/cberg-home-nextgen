<?php

declare(strict_types=1);

namespace OCA\OpenclawMail\AppInfo;

use OCP\AppFramework\App;
use OCP\AppFramework\Bootstrap\IBootContext;
use OCP\AppFramework\Bootstrap\IBootstrap;
use OCP\AppFramework\Bootstrap\IRegistrationContext;

class Application extends App implements IBootstrap {
    public const APP_ID = 'openclaw_mail';

    public function __construct(array $urlParams = []) {
        parent::__construct(self::APP_ID, $urlParams);
    }

    public function register(IRegistrationContext $context): void {
        // DraftController is auto-wired by NC's DI container.
    }

    public function boot(IBootContext $context): void {
        // Nothing to do at boot — the Mail app's services are looked up
        // on-demand from the DI container when the route is invoked.
    }
}
