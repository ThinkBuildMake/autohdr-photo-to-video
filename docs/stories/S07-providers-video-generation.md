### S07 — The app can generate a clip from a photo with Veo 3.1, or Seedance as a fallback

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** L — first contact with OpenRouter's Videos API: submit, poll, download, cost under BYOK, and recovery after a restart
**Builds:** Providers interface generateClip, allowedLengths, recoverCalls; the `provider_calls` write path for clip calls; FakeProviders' generateClip with a short generated test clip and error injection; the OpenRouter Videos API external contract
**Extends:** the `provider_calls` write path and error mapping owned by S06
**Stubs:** none
**Requirements:** FR-1.4, CO-1, DE-5
**Guards:** RL-1, CO-1, DE-5

#### Why
Each shot is a clip made from its photo. This story asks for the clip at 1080p with no audio, waits for it, downloads it, and records its seconds and cost.

#### How it's checked
pytest with the Videos API mocked, and one live test run by hand that makes one 4 s Veo 3.1 clip from a synthetic image.

#### Acceptance criteria
1. A clip is made
   Given a first-frame image, a prompt and a length of 4 s
   When generateClip runs against mocked submit, poll and download answers
   Then it returns a clip file with 4 s, the model and the cost
2. The request asks for the right format
   Given the same call
   When the submitted request is read
   Then it asks for 1080p, 16:9, audio off and the photo as the first frame
3. Allowed lengths come from the model list
   Given a mocked model list where Veo 3.1 accepts 4, 6 and 8 s
   When allowedLengths runs for `google/veo-3.1`
   Then it returns 4, 6 and 8
4. A failed video job is an error
   Given the poll answer reports the job failed
   When generateClip runs
   Then it raises ProviderError `failed` and the cost row has status `error`
5. BYOK clips record list price
   Given `google/veo-3.1` in `BYOK_MODELS` and a reported cost of $0
   When a 4 s clip finishes
   Then its row records 4 output seconds and 4 × the listed price per second
6. A clip left running is collected after a restart
   Given a `generate_clip` row still `running` with a provider request id whose job finished
   When recoverCalls runs
   Then the clip is downloaded into the bucket and the row is closed
7. No retry after out of credit
   Given the submit answers 402
   When generateClip runs
   Then it raises `out_of_credit` and makes no second request
8. The fake makes a playable clip
   Given `FAKE_PROVIDERS=1`
   When generateClip runs for 4 s
   Then the clip probes as a 4 s video and its row has cost 0

#### Not in this story
- Choosing the fallback model for a shot — picked up by S12
