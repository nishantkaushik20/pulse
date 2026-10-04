"""Read-only language model boundary. No tool can mutate tenant data."""

from typing import Protocol

from pulse_api.errors import UnavailableError


class ModelResult:
    def __init__(self, payload: dict[str, object], input_tokens: int, output_tokens: int) -> None:
        self.payload = payload
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class LanguageModel(Protocol):
    name: str

    def complete(self, purpose: str, context: dict[str, object]) -> ModelResult: ...


class DisabledModel:
    """Default provider. Pulse does not call a vendor until one is configured."""

    name = "none"

    def complete(self, purpose: str, context: dict[str, object]) -> ModelResult:
        del purpose, context
        raise UnavailableError("ai is not configured")


def validate_text(payload: dict[str, object], field: str, limit: int) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise UnavailableError("ai output was not usable")
    text = value.strip()
    if not text or len(text) > limit:
        raise UnavailableError("ai output was not usable")
    return text
