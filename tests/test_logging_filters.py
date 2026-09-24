import logging

from apps.common.logging_context import request_id_var
from apps.common.logging_filters import RedactionFilter, RequestIDLogFilter, redact


def test_redact_masks_common_sensitive_keys():
    message = 'password=hunter2 token: "abc.def" Authorization=Bearer xyz cookie=sid123'

    result = redact(message)

    assert "hunter2" not in result
    assert "abc.def" not in result
    assert "Bearer xyz" not in result
    assert "sid123" not in result
    assert "***REDACTED***" in result


def test_redact_leaves_unrelated_text_untouched():
    message = "User logged in successfully"

    assert redact(message) == message


def _make_record(msg, args=()):
    return logging.LogRecord(
        name="monituj",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )


def test_redaction_filter_rewrites_record_message_and_clears_args():
    record = _make_record("login failed password=%s", ("hunter2",))

    RedactionFilter().filter(record)

    assert "hunter2" not in record.msg
    assert record.args == ()


def test_request_id_log_filter_reads_contextvar():
    token = request_id_var.set("req-123")
    try:
        record = _make_record("hello")
        RequestIDLogFilter().filter(record)
        assert record.request_id == "req-123"
    finally:
        request_id_var.reset(token)
