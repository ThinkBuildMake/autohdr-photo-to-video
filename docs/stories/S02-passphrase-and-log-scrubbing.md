### S02 — Only people with the demo passphrase can use the app, and secrets never reach the logs

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** M — a wrapper on every route and a log filter, six criteria
**Builds:** Access (the shared passphrase on every route except `/healthz`); the Scrubbing system-wide contract
**Extends:** none
**Stubs:** none
**Requirements:** none
**Supports:** FR-3.2 (shown in S20)
**Guards:** GC-3

#### Why
The address is public and nothing caps spend, so a stranger must not be able to start a paid job; and the API key, passphrase and presigned links must never show up in a log.

#### How it's checked
pytest against the app with stubs: requests with and without the passphrase, and a captured log after requests that carry secrets.

#### Acceptance criteria
1. No passphrase, no access
   Given the app with `DEMO_PASSPHRASE` set to `test-pass`
   When `GET /api/styles` is called with no credentials
   Then the answer is 401 with a basic-auth challenge and no body detail
2. Wrong passphrase is refused
   Given the same app
   When `GET /` is called with the password `wrong`
   Then the answer is 401
3. The right passphrase lets any user name in
   Given the same app
   When `GET /api/styles` is called with user `anyone` and password `test-pass`
   Then the answer is 200
4. Health stays open
   Given the same app
   When `GET /healthz` is called with no credentials
   Then the answer is 200
5. The passphrase is never logged
   Given requests made with the right and the wrong passphrase
   When the captured logs are searched
   Then neither `test-pass` nor `wrong` appears
6. Secrets and links are scrubbed
   Given log lines that contain the OpenRouter key, a presigned URL and base64 image data
   When they are written through the app's logger
   Then the written lines contain none of the three

#### Not in this story
- Secrets in provider errors — checked by S06 and S07
