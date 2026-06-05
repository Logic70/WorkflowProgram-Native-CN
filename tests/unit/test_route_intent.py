from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".claude" / "scripts" / "route-intent.py"


def route(request: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--request", request, "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return json.loads(completed.stdout)


def test_workflow_migration_request_beats_domain_audit_keyword() -> None:
    payload = route("迁移 FreeSTRIDE 的 STRIDE 安全审计工作流到 WPN Native Workflow JS")

    assert payload["intent"] == "develop"
    assert payload["entry_skill"] == "workflowprogram-develop"
    assert payload["reason"] == "explicit-develop-workflow-change"


def test_plain_audit_request_still_routes_to_audit() -> None:
    payload = route("审计当前目标项目的 workflow 结构问题")

    assert payload["intent"] == "audit"
    assert payload["entry_skill"] == "workflowprogram-audit"
