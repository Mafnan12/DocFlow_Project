import json
import logging

from docflow.logging import (
    JSONFormatter,
    clear_log_context,
    mask_sensitive_data,
    set_log_context,
)


def test_mask_credit_card_numbers():
    # 16-digit card
    card = "Paid with card 4111222233334444 on terminal 1"
    masked = mask_sensitive_data(card)
    assert "4111********4444" in masked
    assert "4111222233334444" not in masked

    # Dashed card
    dashed = "Card: 4111-2222-3333-4444"
    masked_dashed = mask_sensitive_data(dashed)
    assert "2222-3333" not in masked_dashed

    # Normal short numbers should NOT be masked
    invoice_num = "Invoice #10425"
    assert mask_sensitive_data(invoice_num) == invoice_num

    # Phone number or 10-digit number
    short_num = "Order 123456789"
    assert mask_sensitive_data(short_num) == short_num


def test_json_formatter_output():
    formatter = JSONFormatter()
    clear_log_context()
    set_log_context(document_id="doc_123", worker_id="w_1")

    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Processing document with total $50.00",
        args=(),
        exc_info=None,
    )

    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test_logger"
    assert "total $50.00" in parsed["message"]
    assert parsed["document_id"] == "doc_123"
    assert parsed["worker_id"] == "w_1"
    assert "timestamp" in parsed

    clear_log_context()
