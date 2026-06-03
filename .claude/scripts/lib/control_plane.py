from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterable, List


def build_stage_progress_command(
    *,
    python_executable: str,
    stage_progress_script: Path,
    run_root: Path,
    stage: str,
    node: str,
    event: str,
    status: str,
    percent: int,
    result: str,
    next_action: str = "",
    artifact_refs: Iterable[str] | None = None,
    verdict: str = "",
    approval_status: str = "",
) -> List[str]:
    """Build the strict `stage-progress.py update` argv from structured inputs."""

    command = [
        python_executable,
        str(stage_progress_script),
        "update",
        "--run-root",
        str(run_root),
        "--stage",
        str(stage).strip(),
        "--node",
        str(node).strip(),
        "--event",
        str(event).strip(),
        "--status",
        str(status).strip(),
        "--percent",
        str(percent),
        "--result",
        str(result),
        "--next-action",
        str(next_action),
    ]
    if verdict:
        command.extend(["--verdict", str(verdict).strip()])
    if approval_status:
        command.extend(["--approval-status", str(approval_status).strip()])
    for ref in artifact_refs or []:
        normalized = str(ref).strip()
        if normalized:
            command.extend(["--artifact-ref", normalized])
    return command


def emit_stage_progress(
    *,
    python_executable: str,
    stage_progress_script: Path,
    run_root: Path,
    stage: str,
    node: str,
    event: str,
    status: str,
    percent: int,
    result: str,
    next_action: str = "",
    artifact_refs: Iterable[str] | None = None,
    verdict: str = "",
    approval_status: str = "",
) -> None:
    """Invoke `stage-progress.py` through a thin internal control-plane helper."""

    command = build_stage_progress_command(
        python_executable=python_executable,
        stage_progress_script=stage_progress_script,
        run_root=run_root,
        stage=stage,
        node=node,
        event=event,
        status=status,
        percent=percent,
        result=result,
        next_action=next_action,
        artifact_refs=artifact_refs,
        verdict=verdict,
        approval_status=approval_status,
    )
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
        raise RuntimeError(f"control-plane progress emission failed: {message}")
