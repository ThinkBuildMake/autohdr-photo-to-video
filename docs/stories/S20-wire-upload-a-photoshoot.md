### S20 — Upload a real photoshoot and see each photo labelled with its room

**Kind:** wiring
**Blocked by:** S02, S04, S05, S06, S08, S15
**Review gate:** human demo
**Size:** M — four seams: screen to Photoshoots, Photoshoots to Files and the real bucket, to Media, and to labelling on OpenRouter
**Wires:** the "Upload a photoshoot" trace (createUpload, browser upload, completeUpload, labelPhotos, getPhotoshoot). Removes the stubs for Files, Media.probe and thumbnail and Providers.labelPhotos in Photoshoots, and the Photoshoots routes behind the New video screen
**Extends:** none
**Requirements:** FR-1.1, DE-2, FR-1.10, FR-3.2
**Guards:** DE-2, GC-9

#### Why
First real data in the system: the photographer's photos go straight to the bucket and come back labelled.

#### How it's checked
The human demo, on the deployed app, with one of the 12 test shoots:
1. Open the Railway address; enter the passphrase.
2. Open New video and drop the shoot's photos, plus one `.mp4` and one oversized file.
3. The grid shows every photo's thumbnail, the two bad files refused with reasons, and then each photo's room and subject once labelling finishes.
4. Open the bucket console; the photos are there and are not public.

#### Acceptance criteria
1. Browser uploads reach the real bucket
   Given the deployed app and the real bucket
   When 3 photos are dropped on New video
   Then the bucket holds 3 objects under that shoot
2. Labels come from the real model
   Given an uploaded test shoot
   When labelling finishes
   Then each photo in the grid shows a room and a subject
3. Bad files are refused at the screen
   Given a `.mp4` and a 30 MB JPEG among the drop
   When the drop is processed
   Then both are listed with their reasons and nothing is uploaded for them
4. An oversized object is caught after upload
   Given a photo object larger than 25 MB reached the real bucket
   When completeUpload runs
   Then the object is deleted and the photo shows "too large"
5. Labelling failure is survivable
   Given OpenRouter answers `failed` to labelling
   When labelling runs
   Then the page says labels are missing and the shoot can still be used
6. The passphrase guards the real app
   Given the deployed address
   When it is opened without the passphrase
   Then the browser is asked for the passphrase
7. The seams join the gate
   Given the regression gate
   When it runs
   Then it holds integration cases for upload, complete and label across the real Photoshoots, Files on moto and Providers on mocked OpenRouter answers, including a labelling error

#### Not in this story
- Writing a plan from these photos — picked up by S21
