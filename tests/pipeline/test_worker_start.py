import threading

from app import worker
from app.jobs import worker_interface
from app.providers import interface as providers


def test_recovery_runs_before_any_claim(monkeypatch):
    calls = []
    stop = threading.Event()

    def claim_next_job():
        calls.append("claim")
        stop.set()

    monkeypatch.setattr(worker_interface, "recover_interrupted", lambda: calls.append("jobs"))
    monkeypatch.setattr(providers, "recover_calls", lambda: calls.append("providers"))
    monkeypatch.setattr(worker_interface, "claim_next_job", claim_next_job)

    worker.run(stop)

    assert calls == ["jobs", "providers", "claim"]
