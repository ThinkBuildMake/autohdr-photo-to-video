### S08 — A photoshoot is uploaded straight to the bucket and each photo gets its room label

**Kind:** module
**Blocked by:** S01
**Review gate:** agents
**Size:** M — three routes, the labelling job and two interfaces on two tables
**Builds:** `photoshoots` and `photos` write paths; createUpload `POST /api/photoshoots`; completeUpload `POST /api/photoshoots/{id}/complete`; getPhotoshoot `GET /api/photoshoots/{id}`; the labelPhotoshoot background job, including relabelling a shoot left `labelling` on app start; Photoshoots interface listPhotos and importPhotoshoot; Photoshoots' Must holds
**Extends:** none
**Stubs:** Files (presignUpload, headObject, get, put, presignDownload), Media (probe, thumbnail) and Providers.labelPhotos — removed by S20
**Requirements:** DE-2, GC-9
**Supports:** FR-1.1, FR-1.10, FR-3.6 (shown in S20)
**Guards:** DE-2, FR-3.6, GC-9

#### Why
The photographer drops in a property's photos; the planner needs to know which room each one shows.

#### How it's checked
pytest against the routes with stubbed Files, Media and labelling.

#### Acceptance criteria
1. Upload links are handed out
   Given 3 JPEG files of 2 MB each
   When `POST /api/photoshoots` is sent with their names, sizes and types
   Then the answer is 201 with a photoshoot id and 3 upload forms
2. Bad files are refused with reasons
   Given a 30 MB JPEG, a `.mp4` and a valid PNG
   When `POST /api/photoshoots` is sent
   Then the answer has 1 upload and refuses the others as `too_large` and `wrong_type`
3. Too many files
   Given 41 JPEG files
   When `POST /api/photoshoots` is sent
   Then the answer is 400 `too_many_files`
4. Completing marks what arrived
   Given a shoot of 3 photos where the bucket holds 2
   When `POST /api/photoshoots/{id}/complete` is sent
   Then the answer is 202 with 2 photos `uploaded`, 1 `missing`, and the shoot `labelling`
5. Oversized uploads are deleted
   Given the bucket holds a 26 MB object for a photo
   When completeUpload runs
   Then the object is deleted and the photo is `too_large`
6. Labels arrive
   Given a shoot `labelling` and a stub labeller answering `kitchen`
   When labelling finishes
   Then `GET /api/photoshoots/{id}` shows the shoot `ready` and each photo's room and subject
7. Labelling failure is recorded
   Given the labeller raises `failed`
   When labelling runs
   Then the shoot is `label_failed`
8. Interrupted labelling restarts
   Given a shoot left `labelling` when the app stopped
   When the app starts
   Then labelling runs again for that shoot
9. Photos list in upload order
   Given a shoot with photos 1 to 3, one missing
   When listPhotos is called
   Then it returns the 2 uploaded photos in upload order with their labels
10. Server-side import
    Given a folder of 3 synthetic JPEGs
    When importPhotoshoot is called with the label "Test shoot A"
    Then a shoot exists with 3 uploaded photos and labelling has started
11. Unknown shoot
    Given no shoot with id `x`
    When `GET /api/photoshoots/x` is called
    Then the answer is 404 `photoshoot_not_found`
12. A photo's key never changes
    Given an uploaded photo with its file key
    When completeUpload runs again
    Then the photo's file key is unchanged

#### Not in this story
- The upload screen — picked up by S15
- Real bucket and real labels — picked up by S20
