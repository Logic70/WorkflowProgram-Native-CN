# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

from lib.host_team_utils import project_local_outputs, project_local_outputs_ready


PROBE_TIMEOUT_SECONDS = 5


def codex_home() -> Path:
    return (Path.home() / ".codex").resolve()


def mcp_config_candidates(target_root: Path) -> List[Path]:
    home = codex_home()
    return [
        home / "config.toml",
        home / "config.json",
        target_root / ".mcp.json",
        target_root / ".codex" / "config.toml",
    ]


def resolve_skill_probe_path(target_root: Path, probe: Dict[str, Any], *, codex_skill: bool) -> Path:
    path_value = str(probe.get("path", "")).strip()
    if path_value:
        candidate = Path(path_value)
        return candidate.resolve() if candidate.is_absolute() else (target_root / candidate).resolve()
    skill_name = str(probe.get("skill_name", "")).strip()
    if codex_skill:
        return (codex_home() / "skills" / skill_name / "SKILL.md").resolve()
    return (target_root / ".claude" / "skills" / skill_name / "SKILL.md").resolve()


def expand_probe_path(path_text: str) -> Path:
    return Path(path_text).expanduser().resolve()


def probe_external_binary(probe: Dict[str, Any]) -> Tuple[bool, str]:
    binary = str(probe.get("binary", "")).strip()
    if not binary:
        return False, "probe.binary is missing"
    resolved = shutil.which(binary)
    search_paths = probe.get("search_paths", [])
    if resolved is None and isinstance(search_paths, list):
        for raw_path in search_paths:
            candidate_dir = expand_probe_path(str(raw_path).strip())
            candidate = candidate_dir / binary
            if candidate.exists():
                resolved = str(candidate)
                break
    if resolved is None:
        return False, f"binary not found on PATH: {binary}"
    raw_args = probe.get("args", [])
    args = [str(item) for item in raw_args] if isinstance(raw_args, list) else []
    if not args:
        return True, f"binary available: {resolved}"
    try:
        completed = subprocess.run(
            [resolved, *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        return False, f"binary probe failed: {exc}"
    if completed.returncode == 0:
        return True, f"binary probe succeeded: {resolved}"
    detail = completed.stderr.strip() or completed.stdout.strip() or f"exit={completed.returncode}"
    return False, f"binary probe returned non-zero status: {detail}"


def probe_mcp_server(target_root: Path, probe: Dict[str, Any]) -> Tuple[bool, str]:
    server_name = str(probe.get("server_name", "")).strip()
    if not server_name:
        return False, "probe.server_name is missing"
    for path in mcp_config_candidates(target_root):
        if not path.exists():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if server_name in content:
            return True, f"found MCP server reference '{server_name}' in {path}"
    return False, f"MCP server '{server_name}' not found in known config files"


def probe_skill(target_root: Path, probe: Dict[str, Any], *, codex_skill: bool) -> Tuple[bool, str]:
    path = resolve_skill_probe_path(target_root, probe, codex_skill=codex_skill)
    label = "Codex skill" if codex_skill else "Claude skill"
    if path.exists():
        return True, f"{label} found: {path}"
    return False, f"{label} not found: {path}"


def detect_ready_status(target_root: Path, capability: Dict[str, Any]) -> Tuple[bool, str, str]:
    if project_local_outputs_ready(target_root, capability):
        outputs = project_local_outputs(capability)
        return True, "ready", f"project-local bootstrap outputs present: {outputs}"

    kind = str(capability.get("kind", "")).strip()
    probe = capability.get("probe", {})
    if not isinstance(probe, dict):
        return False, "missing", "probe is missing or invalid"
    if kind == "external_binary":
        ready, message = probe_external_binary(probe)
    elif kind == "mcp_server":
        ready, message = probe_mcp_server(target_root, probe)
    elif kind == "codex_skill":
        ready, message = probe_skill(target_root, probe, codex_skill=True)
    elif kind == "claude_skill":
        ready, message = probe_skill(target_root, probe, codex_skill=False)
    else:
        ready, message = False, f"unsupported capability kind: {kind}"
    if ready:
        return True, "ready", message
    if capability.get("required") is False:
        return False, "degraded", message
    return False, "missing", message
