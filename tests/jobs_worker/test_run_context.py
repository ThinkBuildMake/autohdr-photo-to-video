import uuid

from sqlalchemy import text

from app.db.base import session_scope
from app.jobs import worker_interface
from tests.support.worker_rows import add_shot


def test_context_scopes_round_and_orders_history(running_job, shoot):
    shot = add_shot(running_job, 1)
    with session_scope() as session:
        session.execute(text("update job_shots set round=2 where id=:s"), {"s": shot})
        for round_no, number, status, error in [
            (2, 2, "error", "failed: check failed"),
            (1, 1, "flagged", None),
            (2, 1, "flagged", None),
        ]:
            session.execute(
                text(
                    "insert into attempts (id,job_shot_id,round,attempt_no,prompt,model,"
                    "requested_s,status,error,started_at) values "
                    "(:i,:s,:r,:n,'p','model',4,:st,:e,'2026-10-19T10:00:00Z')"
                ),
                {
                    "i": str(uuid.uuid4()),
                    "s": shot,
                    "r": round_no,
                    "n": number,
                    "st": status,
                    "e": error,
                },
            )
    context = worker_interface.run_context(shot)
    assert context.round_no == 2
    assert context.earlier == [("model", "flagged"), ("model", "check_error:failed")]
