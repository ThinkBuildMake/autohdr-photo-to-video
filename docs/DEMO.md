# Demo script

Deployed app: https://autohdr-app-production.up.railway.app (Railway project mellow-insight, service autohdr-app, volume /data, bucket autohdr-media). The passphrase is in `~/.autohdr-demo-passphrase`. Never paste it into this repo, a chat or a log.

Steps marked **paid** spend provider credit. Run them only with the owner's go-ahead.

## 0. Before the rehearsal

1. Deploys on the Hobby plan can be paused by Railway. Redeploy the integration branch head with `railway up`, then wait for the deployment to finish.
2. Open `https://autohdr-app-production.up.railway.app/healthz`. It must answer 200 before you go on. If it does not, redeploy again.
3. Check the passphrase file exists: `ls ~/.autohdr-demo-passphrase`. Do not print it.
4. Have a test shoot of photos ready on the laptop (see `README.md` for the 12-shoot set).

## 1. Live clip check (paid)

Needs the owner's go-ahead. One 4 s clip with the production video model:

`OPENROUTER_LIVE=1 uv run --env-file .env pytest tests/providers/video/test_live_clip.py -s`

Pass: the test passes and the clip is 4 s (within 0.5 s).

## 2. Live flow

Walk these in order on the deployed app. Log in with the passphrase from the file when asked. Part A makes a video from a preset style. Part B shows a reference beside its reproduction and needs a second paid job.

### A. Preset style to finished video

1. Open Styles (`/`). Pick a preset and press "Use this style". Expect `/new?styleId=...` with the style text and song filled in.
2. On New video press "Choose photos" and upload the test shoot. Expect each photo listed as uploaded.
3. Press "Next: write the shot plan". Expect one shot card per shot with its movement and length. Press "Back" or "Change the style text and re-plan" only if you want to show them.
4. Press "Make my video" (paid). Expect the Job page (`/jobs/{id}`) to say "Making your video" and then each shot finishing.
5. Play the finished video on the Job page. Expect it to play in full with its song. "Download video" saves the file.
6. Press "Open in editor" (`/jobs/{id}/edit`), change one shot and press "Re-export video". Expect "Re-exporting" with "changed shot", then a new video that plays.

### B. Reference and reproduction (comparison)

Preset styles have no reference video, so this needs a style you create from a demo shoot.

1. Open "Create a style" (`/styles/new`). Fill in the name, your name, a song, the style text and a demo photoshoot, then press "Try it on the demo shoot" (paid). Expect the try video to appear when the job finishes.
2. Press "Use as the reference video". Expect a note that the try is now the reference, with a "See reproductions" link.
3. Open Styles (`/`). The new style now shows "Has a reference video". Open "Make a reproduction", choose a different shoot (or the same house) and press "Start the reproduction". Expect the shot plan for the reproduction (`/new?jobId=...`). Press "Make my video" (paid), then expect the Job page (`/jobs/{id}`) and wait until it is ready.
4. Press "See reproductions" on the style card (`/styles/{id}/reproductions`). The "Run on another shoot" button on that page starts another reproduction. Expect the reference video beside the new reproduction.
5. Press "Play both together". Expect both videos to play in step.

## 3. Pre-made demo job (offline copy)

The demo must work even if a live job does not finish in its time slot (DE-4).

1. Make the demo job on the deployed app (paid) with the flow above. Note its job id.
2. Download it: `uv run python scripts/demo_video.py fetch --base https://autohdr-app-production.up.railway.app JOB_ID demo.mp4`. The script reads the passphrase from the file (or `DEMO_PASSPHRASE`) and does not print it.
3. Check it: `uv run python scripts/demo_video.py verify demo.mp4`. Expect a video stream, an audio stream and a duration of at least 20 s.
4. Copy `demo.mp4` to the presenter laptop (never commit it).
5. Turn Wi-Fi off and play it. Pass: it plays in full with its song.

Fallback rule: if the live job is not playable inside the slot, play the offline copy and carry on.

## 4. Freeze deploys

1. Open the service config (Railway MCP `get-service-config`, or the dashboard). Expect no connected source and no auto-deploy.
2. If a source is connected, disconnect it or turn auto-deploy off.
3. Push a commit. Expect no new deployment to appear.
4. To unfreeze later, reconnect the source or run `railway up` by hand.

## 5. Screen pass against the wireframe

Walk each screen and state against the published wireframe (https://claude.ai/artifact/Y9f7bkitn6dqRLvP5sN5vH): layout, labels, buttons. Write defects to the follow-ups list; do not fix them in the rehearsal.

- Styles: the preset texts
- New video: style text field, upload, then the shot plan to check, with Back, change the style text and re-plan, and cut-at times
- Jobs: the Jobs list
- Job: running, waiting, stopped, partly failed, ready, with shot cards and Redo this shot
- Editor: swap a room, change a shot, remove a room, re-export, the Re-exporting banner
- Create a style: the demo-shoot method
- Reference and reproduction: same house or a different house, Play both together
