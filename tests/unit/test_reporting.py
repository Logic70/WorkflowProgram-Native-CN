#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parents[2] / ".claude" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from lib.reporting import redact_payload, redact_text, with_report_fields


def assert_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def main() -> int:
    assert_equal(redact_text("api_key=abc123"), "api_key=<redacted>", "inline api key")
    assert_equal(redact_text("password:secret"), "password:<redacted>", "inline password")
    payload = redact_payload({"token": "abc", "nested": {"safe": "x", "secret_value": "y"}})
    assert_equal(payload["token"], "<redacted>", "token key")
    assert_equal(payload["nested"]["secret_value"], "<redacted>", "nested secret key")
    report = with_report_fields({"status": "PASS"}, schema_name="unit-report")
    assert_equal(report["schema_version"], 1, "schema version")
    assert_equal(report["schema_name"], "unit-report", "schema name")
    assert_equal(report["failure_kind"], "none", "default failure kind")
    assert_equal(report["remediation"], [], "default remediation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
