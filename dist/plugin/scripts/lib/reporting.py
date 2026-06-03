# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict, List, Optional


REPORT_SCHEMA_VERSION = 1

SECRET_VALUE_RE = re.compile(
    r"(?i)(token|password|passwd|secret|api[_-]?key|access[_-]?key|private[_-]?key)\s*([:=])\s*([^\s\"']+)"
)
SECRET_KEY_RE = re.compile(r"(?i)(token|password|passwd|secret|api[_-]?key|access[_-]?key|private[_-]?key)")


def redact_text(value: str) -> str:
    """Redact token/password/key-like inline values from user-shareable reports."""

    return SECRET_VALUE_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", value)


def redact_payload(value: Any) -> Any:
    """Recursively redact common secret-shaped fields in JSON-like payloads."""

    if isinstance(value, dict):
        result: Dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if SECRET_KEY_RE.search(text_key):
                result[text_key] = "<redacted>"
            else:
                result[text_key] = redact_payload(item)
        return result
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def with_report_fields(
    payload: Dict[str, Any],
    *,
    schema_name: str,
    error_code: Optional[str] = None,
    failure_kind: str = "none",
    remediation: Optional[List[Dict[str, Any]]] = None,
    redact: bool = True,
) -> Dict[str, Any]:
    """Attach common report fields and optionally redact shareable content."""

    output = deepcopy(payload)
    output.setdefault("schema_version", REPORT_SCHEMA_VERSION)
    output.setdefault("schema_name", schema_name)
    output.setdefault("error_code", error_code)
    output.setdefault("failure_kind", failure_kind)
    output.setdefault("remediation", remediation or [])
    return redact_payload(output) if redact else output
