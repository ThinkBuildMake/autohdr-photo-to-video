### S06 — The app can label photos, write a shot plan, edit photos and check edits and clips through OpenRouter

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** L — first contact with OpenRouter's chat API, four models, error kinds and the cost record
**Builds:** Providers interface labelPhotos, planShots, editPhoto, checkEdit, checkClip; the `provider_calls` write path for those calls; the error mapping to `ProviderErrorKind`; the cost rule (reported cost, or list price under BYOK); FakeProviders for these five calls, with error injection; the OpenRouter chat external contract
**Extends:** none
**Stubs:** none
**Requirements:** QC-1, CO-1, GC-3
**Supports:** FR-1.7, FR-1.8, FR-1.10 (shown in S21 and S22)
**Guards:** VR-5, CO-1, RL-1

#### Why
Labelling, planning, photo edits and both quality checks all go to OpenRouter's chat API. This story makes those calls, turns their failures into one set of kinds, and records what each one cost.

#### How it's checked
pytest with OpenRouter's HTTP answers mocked, and one marked live test per call that runs only by hand with a real key on synthetic images.

#### Acceptance criteria
1. Photos are labelled
   Given two synthetic photos of a kitchen and a bedroom
   When labelPhotos runs against a mocked answer
   Then it returns `kitchen` and `bedroom` with a subject for each
2. A shot plan comes back in the plan's shape
   Given a style text, a 40 s song and three labelled photos
   When planShots runs against a mocked answer
   Then it returns shots with photo, edit prompts, movement name, speed, length and transition, and the planner's notes
3. A plan that is not JSON is a bad response
   Given the planner answers with prose
   When planShots runs
   Then it raises ProviderError `bad_response`
4. A photo is edited
   Given a photo and the prompt "warm late-afternoon light, preserve all architectural and interior details"
   When editPhoto runs against a mocked answer
   Then it returns one image
5. An edit that changes a fixture is caught
   Given a mocked check answer listing a removed window
   When checkEdit runs
   Then the EditCheck has `architectureChanged` true and names the window
6. A clip with a person is flagged
   Given a mocked check answer counting one person
   When checkClip runs
   Then the ClipCheck has `passed` false and its notes name the person
7. Errors map to one set of kinds
   Given OpenRouter answers 429, 402, a content refusal, 500 and no answer in time
   When each call is made
   Then they raise `rate_limited`, `out_of_credit`, `refused`, `failed` and `timeout`
8. Every call leaves one cost row
   Given one successful and one failed call
   When `provider_calls` is read
   Then there are two rows with kind, model, status and cost
9. BYOK calls record list price
   Given a model listed in `BYOK_MODELS` and an answer reporting $0
   When the call finishes
   Then its row has `cost_source` `list_price` and a cost above 0
10. The key never leaks
    Given a failed call
    When the error message, the row and the logs are read
    Then none contains the API key
11. The fake can fail on demand
    Given `FAKE_PROVIDERS=1` told to raise `out_of_credit` on the second checkClip
    When checkClip is called twice
    Then the first passes and the second raises `out_of_credit`

#### Not in this story
- Clip generation — picked up by S07
- Live calls with the 12 test shoots — picked up by S20 and S21
