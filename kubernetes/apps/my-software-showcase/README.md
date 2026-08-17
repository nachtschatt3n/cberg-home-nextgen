
## No outbound integrations

This namespace is a portfolio showcase. It deliberately runs with **no external
services**: no SMTP, no error reporting (Sentry / Errbit / Airbrake), no
Twilio, no AppSignal, no BugHerd, no Facebook or Fastbill APIs.

Every one of these apps originally hardcoded credentials for those services.
They were scrubbed to environment variables and each integration was made
*inert when its variable is unset* — not merely unconfigured, but guarded, so
the app boots and runs normally with the feature disabled. None of those
variables is set in any `secret.sops.yaml` here, and none should be added.

Two consequences worth knowing:

- Features that depend on them are inactive by design (outbound mail, SMS,
  error reporting). That is the intended state for a showcase, not a defect.
- The original credentials remain exposed in the upstream Bitbucket history
  and must still be rotated at the providers. Not needing a service here is
  not the same as that service's key being safe.
