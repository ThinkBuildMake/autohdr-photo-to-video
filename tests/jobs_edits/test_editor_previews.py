from urllib.parse import unquote, urlparse

import pytest
from sqlalchemy import text

from app.db.base import session_scope


@pytest.mark.parametrize(
    "edit_status,edited,cropped,expected",
    [
        (
            "edited",
            "stored/custom-edited.jpg",
            "stored/custom-crop.jpg",
            "stored/custom-edited.jpg",
        ),
        ("crop_only", "stored/unused.jpg", "stored/custom-crop.jpg", "stored/custom-crop.jpg"),
        ("edited", None, "stored/custom-crop.jpg", "stored/custom-crop.jpg"),
        (None, None, None, None),
    ],
)
def test_editor_reads_actual_frames_for_only_this_job(
    bucket, client, make_job, shoot, edit_status, edited, cropped, expected
):
    job_id = make_job(passed=1)
    other_job = make_job(passed=1)
    with session_scope() as session:
        session.execute(
            text(
                "update job_shots set edit_status=:s, edited_key=:e, cropped_key=:c where job_id=:j"
            ),
            {"s": edit_status, "e": edited, "c": cropped, "j": job_id},
        )
        session.execute(
            text("update job_shots set cropped_key='other-job/private.jpg' where job_id=:j"),
            {"j": other_job},
        )

    response = client.get(f"/api/jobs/{job_id}")

    assert response.status_code == 200
    shots = response.json()["job"]["shots"]
    assert len(shots) == 1
    shot = shots[0]
    assert unquote(urlparse(shot["photoUrl"]).path).endswith(
        f"/photoshoots/{shoot[0]}/{shoot[1][0]}.jpg"
    )
    if expected is None:
        assert shot["firstFrameUrl"] is None
    else:
        assert unquote(urlparse(shot["firstFrameUrl"]).path).endswith("/" + expected)
    assert "other-job" not in str(shots)
