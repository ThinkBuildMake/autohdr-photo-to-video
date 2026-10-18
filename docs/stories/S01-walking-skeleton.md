### S01 — The app runs on Railway with every page, route and table in place

**Kind:** skeleton
**Blocked by:** none
**Review gate:** human demo
**Size:** L — deploy, the regression gate, every table and every module and route as a contract stub
**Builds:** the database schema (all nine tables: `songs`, `styles`, `photoshoots`, `photos`, `jobs`, `job_shots`, `attempts`, `provider_calls`, `cut_checks`, with their constraints and indexes, created empty); every API route and every module interface as a contract stub; `GET /healthz`; the system-wide contracts Error format, Database, Blocking work, Processes and Configuration (`.env.example`); the Local, Test and CI, and Production environments; the regression gate (ruff, pytest, Playwright in GitHub Actions; Railway deploys only after it passes); the metrics report with one panel per metric in `KEY_METRICS.md`
**Extends:** none
**Stubs:** none (this story makes the stubs)
**Requirements:** DE-1, DE-3, GC-4, GC-9
**Guards:** GC-4, GC-9, FR-3.6

#### Why
Gives every later story a running, deployed app to build into, a gate that stops a broken change from reaching the demo address, and stubs that let the modules be built at the same time.

#### How it's checked
The human demo:
1. Open the Railway address in desktop Chrome; the Styles page renders from stub data.
2. Open `/healthz`; it answers 200.
3. Call `GET /api/jobs/{any id}` and `POST /api/jobs` with an empty body; the stubs answer in the contract's shapes and error format.
4. Open the latest GitHub Actions run; ruff, pytest and Playwright ran and passed, and the Railway deploy waited for it.
5. Run the metrics report; it prints the six panels from `KEY_METRICS.md`, each saying "no data yet".

#### Acceptance criteria
1. The app is deployed
   Given a push to the branch with the gate green
   When Railway finishes deploying
   Then the Railway address serves the Styles page in desktop Chrome
2. Health answers without data
   Given an empty database
   When `GET /healthz` is called
   Then it answers 200
3. Every table exists
   Given a fresh database file
   When the app starts
   Then all nine tables of the architecture's schema exist with their constraints and indexes
4. The single-running-job rule is in the schema
   Given a `jobs` row with status `running`
   When a second row is set to `running`
   Then the database refuses the write
5. Every route answers as its contract says
   Given the app running with stubs
   When each route in ARCHITECTURE.md is called with valid inputs
   Then each answers with its contract's status code and response shape
6. Errors share one format
   Given the app running with stubs
   When `GET /api/jobs/unknown-id` is called
   Then the answer is 404 with body `{ "error": "job_not_found", "message": ... }`
7. App and worker stop together
   Given the container running both processes
   When the worker process exits
   Then the app process exits too
8. Configuration is documented
   Given the repository
   When `.env.example` is read
   Then it lists every variable in the architecture's Configuration contract
9. The gate fails on a broken test
   Given a branch with one failing pytest case
   When CI runs
   Then the run is red and Railway does not deploy it
10. The gate checks the providers are approved
    Given the configuration
    When the gate runs
    Then it fails if any outside host other than OpenRouter and the Railway bucket is configured
11. The gate refuses committed photos
    Given a commit that adds a `.jpg`, `.png` or `.mp4` file outside test fixtures
    When the gate runs
    Then it fails and names the file
12. The metrics report exists
    Given an empty database
    When the metrics report runs
    Then it prints one panel per `KEY_METRICS.md` metric, each with "no data yet"
13. A clean install runs without a GPU
    Given a machine with Docker and no GPU
    When the image is built and started with `FAKE_PROVIDERS=1`
    Then `/healthz` answers 200
14. Foreign keys are on
    Given a fresh database
    When a `job_shots` row is inserted with an unknown job id
    Then the database refuses it
15. Slow calls do not block the server
    Given a stubbed bucket call that takes 5 s in progress
    When `GET /healthz` is called
    Then it answers 200 within 1 s
16. Only a table's owner writes it
    Given the codebase
    When the gate's ownership check runs
    Then it fails if a module writes a table the architecture gives to another module

#### Not in this story
- The passphrase and log scrubbing — picked up by S02
- Real behaviour of every route and module — picked up by the module stories S03–S14 and the screens S15–S18
