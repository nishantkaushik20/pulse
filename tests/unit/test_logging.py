import json
import logging

from pulse_api.logging import JsonFormatter, configure_logging


def test_json_formatter_emits_structured_fields() -> None:
    record = logging.LogRecord(
        name="pulse_api.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="application started",
        args=(),
        exc_info=None,
    )
    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "pulse_api.test"
    assert payload["message"] == "application started"
    assert "timestamp" in payload


def test_configure_logging_sets_level() -> None:
    configure_logging("WARNING")
    assert logging.getLogger().level == logging.WARNING
