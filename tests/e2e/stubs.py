"""Playwright stand-ins for the Photoshoots routes and the bucket, with synthetic files."""

import re

from app.jobs.plan_rules import MOVEMENTS

MAX_BYTES = 25 * 1024 * 1024
SHOOT_ID = "shoot-1"
JOB_ID = "job-1"
THUMB_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="90">'
    '<rect width="160" height="90" fill="#c9d1ce"/></svg>'
)


def photo(n: int, room: str | None = None, subject: str | None = None) -> dict:
    return {
        "id": f"photo-{n}",
        "position": n,
        "originalName": f"photo-{n}.jpg",
        "contentType": "image/jpeg",
        "sizeBytes": 2_000_000,
        "status": "uploaded",
        "room": room,
        "subject": subject,
        "thumbUrl": f"/stub-media/thumb-{n}.svg",
    }


def jpeg(name: str, size: int = 2_000_000) -> tuple[str, str, int]:
    return (name, "image/jpeg", size)


def drop_files(page, files: list[tuple[str, str, int]]) -> None:
    """Drop synthetic files, made in the browser, on the drop zone."""
    data = page.evaluate_handle(
        """files => {
            const transfer = new DataTransfer();
            for (const [name, type, size] of files) {
                transfer.items.add(new File([new Uint8Array(size)], name, { type }));
            }
            return transfer;
        }""",
        files,
    )
    page.dispatch_event("#drop-zone", "drop", {"dataTransfer": data})


class ShootStub:
    """createUpload, the bucket, completeUpload and getPhotoshoot for one shoot."""

    def __init__(self, page, photos, status="ready", unreachable=()):
        self.photos = photos
        self.status = status
        self.unreachable = set(unreachable)
        self.uploaded: list[str] = []
        self.upload_sizes: list[int] = []
        self.completed = 0
        page.route("**/api/photoshoots", self._create)
        page.route("**/stub-upload", self._upload)
        page.route(f"**/api/photoshoots/{SHOOT_ID}/complete", self._complete)
        page.route(f"**/api/photoshoots/{SHOOT_ID}", self._get)
        page.route(
            "**/stub-media/thumb-*",
            lambda route: route.fulfill(content_type="image/svg+xml", body=THUMB_SVG),
        )

    def _create(self, route):
        """Refuse like the real createUpload: tickets for the accepted files, in drop order."""
        accepted, refused = [], []
        for f in route.request.post_data_json["files"]:
            if f["type"] not in ("image/jpeg", "image/png"):
                refused.append({"name": f["name"], "reason": "wrong_type"})
            elif f["size"] > MAX_BYTES:
                refused.append({"name": f["name"], "reason": "too_large"})
            else:
                accepted.append(f)
        uploads = [
            {"photoId": f"photo-{n}", "name": f["name"], "url": "/stub-upload", "fields": {}}
            for n, f in enumerate(accepted, start=1)
        ]
        body = {"photoshootId": SHOOT_ID, "uploads": uploads, "refused": refused}
        route.fulfill(status=201, json=body)

    def _upload(self, route):
        body = route.request.post_data_buffer or b""
        name = re.search(rb'filename="([^"]+)"', body).group(1).decode()
        if name in self.unreachable:
            route.abort()
            return
        self.uploaded.append(name)
        self.upload_sizes.append(len(body))
        route.fulfill(status=204)

    def _complete(self, route):
        self.completed += 1
        unlabelled = [{**p, "room": None, "subject": None} for p in self.photos]
        shoot = {"id": SHOOT_ID, "status": "labelling", "photos": unlabelled}
        route.fulfill(status=202, json={"photoshoot": shoot})

    def _get(self, route):
        shoot = {"id": SHOOT_ID, "label": None, "status": self.status, "photos": self.photos}
        route.fulfill(json={"photoshoot": shoot})


def shot(n: int) -> dict:
    return {
        "id": f"shot-{n}",
        "position": n,
        "room": "living",
        "movementName": "dolly_in",
        "movementPrompt": MOVEMENTS["dolly_in"],
        "speed": "slow",
        "photoEditPrompts": [],
        "lengthS": 4.0,
        "transition": "cut",
        "transitionS": 0.0,
        "photoId": f"photo-{(n - 1) % 3 + 1}",
        "removed": False,
        "pendingChange": "none",
        "planNote": f"From the text: shot {n}",
        "editStatus": None,
        "editNote": None,
        "model": "google/veo-3.1",
        "usedFallback": False,
        "status": "pending",
        "statusDetail": "",
        "failureReason": None,
        "attempts": 0,
        "clipUrl": None,
    }


def job(plan_status: str = "ready", plan_notes: str | None = None) -> dict:
    return {
        "id": JOB_ID,
        "styleId": None,
        "styleName": "Golden hour",
        "photoshootId": SHOOT_ID,
        "purpose": "video",
        "styleText": "Slow and warm.",
        "planStatus": plan_status,
        "planNotes": plan_notes,
        "status": "draft",
        "stopReason": None,
        "submittedAt": None,
        "startedAt": None,
        "finishedAt": None,
        "elapsedS": 0.0,
        "totalCostUsd": 0.0,
        "waitingBehind": None,
        "shots": [shot(n) for n in range(1, 7)] if plan_status == "ready" else [],
        "video": None,
        "songCredit": "Sunrise Walk, Example Artist, CC BY-NC",
    }


class JobStub:
    """createJob, getJob (one answer per poll, the last repeated), updateJobShots, submitJob
    and replanJob for one draft job."""

    def __init__(self, page, *answers):
        self.answers = list(answers)
        self.created: list[dict] = []
        self.saved: list[list[dict]] = []
        self.submitted = 0
        self.replanned = 0
        self.calls: list[str] = []
        self.save_error: str | None = None
        page.route("**/api/jobs", self._create)
        page.route(f"**/api/jobs/{JOB_ID}", self._get)
        page.route(f"**/api/jobs/{JOB_ID}/shots", self._save)
        page.route(f"**/api/jobs/{JOB_ID}/submit", self._submit)
        page.route(f"**/api/jobs/{JOB_ID}/plan", self._replan)

    def _create(self, route):
        self.created.append(route.request.post_data_json)
        route.fulfill(status=201, json={"job": job("planning")})

    def _get(self, route):
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        route.fulfill(json={"job": answer})

    def _save(self, route):
        self.calls.append("save")
        if self.save_error:
            route.fulfill(status=400, json={"error": "invalid_plan", "message": self.save_error})
            return
        shots = route.request.post_data_json["shots"]
        self.saved.append(shots)
        saved = {**self.answers[-1], "shots": [{**shot(1), **s} for s in shots]}
        route.fulfill(json={"job": saved})

    def _submit(self, route):
        self.calls.append("submit")
        self.submitted += 1
        route.fulfill(status=202, json={"job": {**self.answers[-1], "status": "queued"}})

    def _replan(self, route):
        self.replanned += 1
        route.fulfill(status=202, json={"job": job("planning")})
