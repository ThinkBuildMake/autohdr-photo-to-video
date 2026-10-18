"""Provider errors: every outside-service failure becomes one of a few kinds."""

from app.shared.enums import ProviderErrorKind


class ProviderError(Exception):
    def __init__(
        self,
        kind: ProviderErrorKind | str,
        message: str,
        retry_after_s: float | None = None,
    ):
        super().__init__(message)
        self.kind = ProviderErrorKind(kind)
        self.message = message
        self.retry_after_s = retry_after_s
