from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class DiagnosticCollector:
    """Shared diagnostics payload builder for validator-style scripts."""

    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    passes: List[str] = field(default_factory=list)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def ok(self, message: str) -> None:
        self.passes.append(message)

    @property
    def status(self) -> str:
        return "PASS" if not self.errors else "FAIL"

    def payload(self, **extra: object) -> Dict[str, object]:
        return {
            "status": self.status,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            **extra,
        }
