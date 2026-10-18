### S04 — Files go to and from a private bucket through short-lived links

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** S — the key layout and five operations against moto
**Builds:** Files interface presignUpload, presignDownload, put, get, headObject; the bucket key layout; Files' Must holds
**Extends:** none
**Stubs:** none
**Requirements:** FR-1.1, FR-1.9, DE-2
**Guards:** DE-2

#### Why
Photos, clips and videos are too big for the app to carry, so the browser sends and receives them directly with signed links, and the bucket stays private.

#### How it's checked
pytest with moto's S3.

#### Acceptance criteria
1. Upload link accepts a small file
   Given a presigned upload for `photoshoots/s1/p1.jpg` with a 25 MB limit
   When a 1 MB JPEG is posted with its fields
   Then headObject reports 1 MB at that key
2. Upload link expires
   Given a presigned upload made 16 minutes ago
   When a file is posted with it
   Then the bucket refuses it
3. Download link works for an hour
   Given an object at `jobs/j1/video-v1.mp4`
   When presignDownload is asked for it
   Then the link fetches the file and its expiry is 1 hour
4. Download as attachment
   Given the same object
   When presignDownload is asked with `asAttachment` and the name `house.mp4`
   Then fetching the link returns a download named `house.mp4`
5. Missing object is reported
   Given no object at `photoshoots/s1/p9.jpg`
   When headObject is called for it
   Then it returns none
6. The bucket is private
   Given an object in the bucket
   When it is fetched by plain URL with no signature
   Then the bucket refuses it
7. Links are never logged
   Given presigned links were made
   When the captured logs are searched
   Then no link appears
8. Put and get round trip
   Given a local 3 MB clip file
   When put stores it at `jobs/j1/shots/1/r0/a1.mp4` and get reads it back
   Then the read file is identical

#### Not in this story
- Whether Railway enforces the size limit on the form (ARCHITECTURE open question 6) — checked at the real bucket in S20
