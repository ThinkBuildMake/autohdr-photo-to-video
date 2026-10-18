"""Pipeline: what the worker does once when it starts."""

from app.jobs import worker_interface
from app.providers import interface as providers


def recover_on_start() -> None:
    worker_interface.recover_interrupted()
    providers.recover_calls()
