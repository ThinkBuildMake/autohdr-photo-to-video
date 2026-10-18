### S27 — The demo is ready: live run rehearsed, a pre-made video kept offline, deploys frozen

**Kind:** wiring
**Blocked by:** S23, S24, S26
**Review gate:** human demo
**Size:** S — no new seam; checks the deployed system as the demo will use it
**Wires:** the Production environment on demo day: the live flow end to end and the Backup and restore contract (the demo job's video kept offline). Removes no stubs (none are left)
**Extends:** none
**Requirements:** DE-4, PF-1
**Guards:** PF-1, GC-3

#### Why
The demo must work whether or not a live job finishes in the time slot.

#### How it's checked
The human demo, a rehearsal:
1. A live Veo call confirms the route still works today.
2. Run the demo flow live: style, upload, plan, video, editor, comparison.
3. Play the pre-generated demo job from the offline copy.
4. Show Railway's auto-deploy frozen.

#### Acceptance criteria
1. The video route works today
   Given the production configuration
   When one 4 s clip is requested
   Then it returns a clip
2. The live flow runs
   Given the deployed app
   When the demo flow is walked from style to comparison
   Then each step works on a test shoot
3. The fallback video plays offline
   Given the pre-generated demo job
   When its offline copy is played with no network
   Then it plays in full with its song
4. Deploys are frozen
   Given the Railway service
   When a commit is pushed
   Then it is not deployed until unfrozen
5. No stub is left
   Given the codebase
   When the gate's stub check runs
   Then no route or module interface answers from a stub

#### Not in this story
- none
