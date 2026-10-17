#!/usr/bin/env python3
"""Smoke-test clip generator (docs/VIDEO_RESEARCH.md). Key is read only from the environment.
Usage: gen_clip.py MODEL METHOD MOVE PHOTO DURATION [RESOLUTION]
Appends one JSON line per clip to out/clips.jsonl; never retries a paid call.
"""
import base64, json, mimetypes, os, sys, time, urllib.request, urllib.error

BASE = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
KEY = os.environ["OPENROUTER_API_KEY"]
OUT = os.path.join(os.path.dirname(__file__), "..", "out")

MOVES = {
    "push-in": "Slow, steady push-in (dolly forward) toward the centre of the room.",
    "pan": "Slow, steady horizontal pan to the right, camera position fixed on a tripod.",
    "tilt-up": "Slow, steady tilt up from the lower part of the room toward the ceiling, camera position fixed.",
}
TEMPLATE = (
    "Use the supplied photo as the sole visual authority for the room. "
    "Do not add, remove or move walls, windows, doors, fixtures or furniture. No new objects, no people. "
    "{move} Gimbal-smooth, no shake, real 3-D parallax rather than a flat zoom. "
    "The camera must not pass through walls or furniture; keep the whole frame inside the room. "
    "One continuous shot: no cuts, no transitions, no text, no audio."
)

def call(method, url, body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)

def main():
    model, meth, move, photo, dur = sys.argv[1:6]
    res = sys.argv[6] if len(sys.argv) > 6 else "720p"
    dur = int(dur)
    prompt = TEMPLATE.format(move=MOVES[move])
    mime = mimetypes.guess_type(photo)[0] or "image/jpeg"
    data_url = f"data:{mime};base64," + base64.b64encode(open(photo, "rb").read()).decode()
    body = {"model": model, "prompt": prompt, "duration": dur, "resolution": res, "aspect_ratio": "16:9",
            "generate_audio": False,
            "frame_images": [{"type": "image_url", "image_url": {"url": data_url}, "frame_type": "first_frame"}]}
    rec = {"model": model, "method": meth, "move": move, "photo": os.path.basename(photo), "prompt": prompt,
           "duration_s": dur, "resolution": res, "submit_ts": time.time(), "ok": False}
    name = f"{model.replace('/', '_')}_{move}_{os.path.basename(photo).rsplit('.',1)[0]}"
    os.makedirs(os.path.join(OUT, "clips"), exist_ok=True)
    try:
        job = call("POST", f"{BASE}/videos", body)
        rec["job_id"] = job["id"]
        while True:
            time.sleep(15)
            st = call("GET", job["polling_url"])
            rec["status"] = st["status"]
            if st["status"] in ("completed", "failed", "cancelled", "expired"):
                break
        rec["ready_ts"] = time.time()
        rec["seconds_taken"] = round(rec["ready_ts"] - rec["submit_ts"], 1)
        rec["cost_usd"] = (st.get("usage") or {}).get("cost")
        if st["status"] == "completed":
            req = urllib.request.Request(st["unsigned_urls"][0], headers={"Authorization": f"Bearer {KEY}"})
            path = os.path.join(OUT, "clips", name + ".mp4")
            with urllib.request.urlopen(req, timeout=300) as r, open(path, "wb") as f:
                f.write(r.read())
            rec["file"] = path; rec["ok"] = True
        else:
            rec["error"] = json.dumps(st.get("error"))
    except urllib.error.HTTPError as e:
        rec["error"] = f"HTTP {e.code}: {e.read().decode()[:500]}"
    except Exception as e:
        rec["error"] = repr(e)
    with open(os.path.join(OUT, "clips.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps({k: v for k, v in rec.items() if k != "prompt"}))

main()
