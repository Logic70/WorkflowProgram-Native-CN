#!/usr/bin/env python3
"""
根据 workflow-spec.yaml 为目标工作流生成确定性的 target-side runtime 资产。

这些资产本身不直接替代 WorkflowProgram 的共享脚本，
而是把“固定主链 + 固定控制面”的机制显式下沉到目标项目：

- `.workflowprogram/runtime/workflow-entry.py`
- `.workflowprogram/runtime/workflow-runner.py`
- `.workflowprogram/runtime/validate-run-state.py`
- `.workflowprogram/runtime/runtime-manifest.json`
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from lib.host_team_utils import (
    agent_team_contract_from_spec,
    agent_team_enabled,
    capability_discovery_from_spec,
    host_global_adapter,
    host_capabilities_from_spec,
    node_loop_enabled,
    runtime_capabilities_from_contract,
)
from lib.io_utils import iso_now, write_json
from lib.yaml_utils import load_yaml_mapping


REQUIRED_TOP_KEYS = [
    "meta",
    "stages",
    "intent_flows",
    "agent_refs",
    "skills",
    "registry",
    "constraints",
    "resource_limits",
    "runtime_contract",
    "generated_runtime_contract",
    "test_contract",
]

REQUIRED_GENERATED_RUNTIME_KEYS = {
    "runtime_root",
    "design_spec_path",
    "entry_script",
    "runner_script",
    "state_validator_script",
    "runtime_manifest",
    "run_root_dir",
    "mode",
    "runtime_capabilities",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate target-side workflow runtime assets from workflow-spec.yaml")
    parser.add_argument("--spec", default="workflow-spec.yaml", help="Path to workflow-spec.yaml")
    parser.add_argument("--out-root", required=True, help="Directory where generated runtime assets will be written")
    parser.add_argument("--json", action="store_true", help="Print JSON payload")
    return parser.parse_args()


def ensure_spec_shape(spec: Dict[str, Any]) -> List[str]:
    missing = [key for key in REQUIRED_TOP_KEYS if key not in spec]
    stages = spec.get("stages")
    if stages is None or not isinstance(stages, list):
        raise ValueError("workflow-spec.yaml field 'stages' must be a list")
    return missing


def require_runtime_contract(spec: Dict[str, Any]) -> Dict[str, Any]:
    contract = spec.get("generated_runtime_contract")
    if not isinstance(contract, dict):
        raise ValueError("generated_runtime_contract must be a mapping/object")
    missing = sorted(REQUIRED_GENERATED_RUNTIME_KEYS - set(contract.keys()))
    if missing:
        raise ValueError(f"generated_runtime_contract missing required keys: {', '.join(missing)}")
    normalized: Dict[str, Any] = {}
    for key in REQUIRED_GENERATED_RUNTIME_KEYS:
        if key == "runtime_capabilities":
            continue
        value = str(contract.get(key, "")).strip()
        if not value:
            raise ValueError(f"generated_runtime_contract.{key} must not be empty")
        normalized[key] = value
    runtime_capabilities = runtime_capabilities_from_contract(contract)
    if not runtime_capabilities:
        raise ValueError("generated_runtime_contract.runtime_capabilities must not be empty")
    normalized["runtime_capabilities"] = runtime_capabilities
    return normalized


def default_entry_skill(spec: Dict[str, Any]) -> str:
    test_contract = spec.get("test_contract", {})
    if not isinstance(test_contract, dict):
        return "workflow"
    entry = test_contract.get("entry", {})
    if not isinstance(entry, dict):
        return "workflow"
    value = str(entry.get("main_entry", "")).strip()
    return value or "workflow"


def render_entry_wrapper(
    contract: Dict[str, Any],
    main_entry: str,
    *,
    team_enabled_flag: bool,
    capability_discovery_enabled_flag: bool,
    target_managed_runtime_flag: bool,
    target_publish_finalizer_enabled_flag: bool,
) -> str:
    return f"""#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


DEFAULT_ENTRY_SKILL = {main_entry!r}
DEFAULT_INTENT = "develop"
DESIGN_SPEC_REL = {contract["design_spec_path"]!r}
RUN_ROOT_DIR_REL = {contract["run_root_dir"]!r}
RUNNER_SCRIPT_REL = {contract["runner_script"]!r}
STATE_VALIDATOR_SCRIPT_REL = {contract["state_validator_script"]!r}
DISCOVER_HOST_SCRIPT = "discover-host-capabilities.py"
PROBE_HOST_SCRIPT = "probe-host-capabilities.py"
APPLY_HOST_BOOTSTRAP_SCRIPT = "apply-host-bootstrap.py"
ENVIRONMENT_REMEDIATION_SCRIPT = "generate-environment-remediation.py"
TARGET_FINALIZER_SCRIPT = "target-runtime-finalizer.py"
TARGET_PUBLISH_STATE_VALIDATOR_SCRIPT = "validate-target-publish-state.py"
RUNTIME_CAPABILITIES = {contract["runtime_capabilities"]!r}
CAPABILITY_DISCOVERY_ENABLED = {capability_discovery_enabled_flag!r}
TEAM_ORCHESTRATION_ENABLED = {team_enabled_flag!r}
NODE_LOOP_EXECUTION_ENABLED = {"node_loop_execution" in contract["runtime_capabilities"]!r}
TARGET_MANAGED_RUNTIME_ENABLED = {target_managed_runtime_flag!r}
TARGET_PUBLISH_FINALIZER_ENABLED = {target_publish_finalizer_enabled_flag!r}


def utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("generated-runtime-%Y%m%dT%H%M%SZ")


def script_root() -> Path:
    return Path(__file__).resolve().parent


def resolve_target_root(explicit: str) -> Path:
    if explicit:
        return Path(explicit).resolve()
    return script_root().parents[1]


def resolve_plugin_root(explicit: str) -> Path:
    if explicit:
        return Path(explicit).resolve()
    env_value = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if env_value:
        return Path(env_value).resolve()
    raise RuntimeError("target runtime requires --plugin-root or CLAUDE_PLUGIN_ROOT")


def plugin_python(plugin_root: Path) -> Path:
    return plugin_root / "bin" / "workflowprogram-python"


def parse_json_output(text: str) -> Dict[str, Any]:
    text = text.strip()
    if not text:
        return {{}}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {{}}
    except json.JSONDecodeError:
        pass
    lines = [line for line in text.splitlines() if line.strip()]
    for idx in range(len(lines)):
        candidate = "\\n".join(lines[idx:])
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {{}}


def run_command(cmd: List[str]) -> Tuple[int, Dict[str, Any], str]:
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    text = completed.stdout.strip() or completed.stderr.strip()
    return completed.returncode, parse_json_output(text), text


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8", newline="\\n")


def required_host_missing(report: Dict[str, Any]) -> bool:
    capabilities = report.get("capabilities", [])
    if not isinstance(capabilities, list):
        return False
    return any(
        isinstance(item, dict)
        and bool(item.get("required", False))
        and str(item.get("status", "")).strip() != "ready"
        for item in capabilities
    )


def run_required_json_command(name: str, cmd: List[str]) -> Dict[str, Any]:
    code, payload, text = run_command(cmd)
    if code != 0:
        raise RuntimeError(f"{{name}} failed: {{text}}")
    if not payload:
        raise RuntimeError(f"{{name}} did not return JSON output")
    return payload


def probe_host_capabilities(plugin_root: Path, spec_path: Path, target_root: Path, run_root: Path) -> Dict[str, Any]:
    payload = run_required_json_command(
        PROBE_HOST_SCRIPT,
        [
            str(plugin_python(plugin_root)),
            str(plugin_root / "scripts" / PROBE_HOST_SCRIPT),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target_root),
            "--run-root",
            str(run_root),
            "--json",
        ],
    )
    report = payload.get("report", {{}})
    if not isinstance(report, dict):
        raise RuntimeError("probe-host-capabilities.py did not return a report object")
    return report


def discover_host_capabilities(plugin_root: Path, spec_path: Path, target_root: Path, run_root: Path, request_text: str) -> Dict[str, Any]:
    payload = run_required_json_command(
        DISCOVER_HOST_SCRIPT,
        [
            str(plugin_python(plugin_root)),
            str(plugin_root / "scripts" / DISCOVER_HOST_SCRIPT),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target_root),
            "--run-root",
            str(run_root),
            "--request",
            request_text,
            "--json",
        ],
    )
    report = payload.get("report", {{}})
    if not isinstance(report, dict):
        raise RuntimeError("discover-host-capabilities.py did not return a report object")
    return report

def apply_host_bootstrap(plugin_root: Path, spec_path: Path, target_root: Path, run_root: Path) -> Dict[str, Any]:
    cmd = [
        str(plugin_python(plugin_root)),
        str(plugin_root / "scripts" / APPLY_HOST_BOOTSTRAP_SCRIPT),
        "--spec",
        str(spec_path),
        "--target-root",
        str(target_root),
        "--run-root",
        str(run_root),
        "--json",
    ]
    return run_required_json_command(APPLY_HOST_BOOTSTRAP_SCRIPT, cmd)


def generate_environment_remediation(plugin_root: Path, spec_path: Path, target_root: Path, run_root: Path) -> Dict[str, Any]:
    payload = run_required_json_command(
        ENVIRONMENT_REMEDIATION_SCRIPT,
        [
            str(plugin_python(plugin_root)),
            str(plugin_root / "scripts" / ENVIRONMENT_REMEDIATION_SCRIPT),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target_root),
            "--run-root",
            str(run_root),
            "--json",
        ],
    )
    report = payload.get("report", {{}})
    if not isinstance(report, dict):
        raise RuntimeError("generate-environment-remediation.py did not return a report object")
    return report


def finalize_target_runtime(plugin_root: Path, spec_path: Path, target_root: Path, run_root: Path) -> Tuple[int, Dict[str, Any], str]:
    return run_command(
        [
            str(plugin_python(plugin_root)),
            str(plugin_root / "scripts" / TARGET_FINALIZER_SCRIPT),
            "--spec",
            str(spec_path),
            "--run-root",
            str(run_root),
            "--target-root",
            str(target_root),
            "--state",
            str(run_root / "target-state.json"),
            "--json",
        ],
    )


def validate_target_publish_state(plugin_root: Path, spec_path: Path, target_root: Path, run_root: Path) -> Tuple[int, Dict[str, Any], str]:
    return run_command(
        [
            str(plugin_python(plugin_root)),
            str(plugin_root / "scripts" / TARGET_PUBLISH_STATE_VALIDATOR_SCRIPT),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target_root),
            "--run-root",
            str(run_root),
            "--json",
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run generated workflow deterministic entry wrapper")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run generated workflow control plane")
    run.add_argument("--target-root", default="", help="Target workflow root; defaults from this script location")
    run.add_argument("--run-root", default="", help="Explicit RUN_ROOT; defaults to target/.workflowprogram/runs/<id>")
    run.add_argument("--plugin-root", default="", help="Plugin root containing shared WorkflowProgram scripts")
    run.add_argument("--request", default="", help="Original request text")
    run.add_argument("--intent", default=DEFAULT_INTENT, help="Logical intent for this invocation")
    run.add_argument("--entry-skill", default=DEFAULT_ENTRY_SKILL, help="Entry name for this generated workflow")
    run.add_argument("--runtime-provider", default="", help="Executor provider override; defaults to target_executor_policy.default_provider")
    run.add_argument("--provider-command", default="", help="Provider command for command_adapter")
    run.add_argument("--claude-bin", default="", help="Deprecated no-op; target runtime does not invoke Claude CLI")
    run.add_argument("--auto-approve", action="store_true", help="Resolve approval gate automatically")
    run.add_argument("--approve-host-global-bootstrap", action="store_true", help="Deprecated no-op; host-global bootstrap is plan-only")
    run.add_argument("--approval-status", default="", choices=["approved"], help="Resolve approval gate as manually approved")
    run.add_argument("--json", action="store_true", help="Print JSON summary")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_root = resolve_target_root(args.target_root)
    plugin_root = resolve_plugin_root(args.plugin_root)
    spec_path = target_root / DESIGN_SPEC_REL
    run_root = Path(args.run_root).resolve() if args.run_root else (target_root / RUN_ROOT_DIR_REL / utc_run_id()).resolve()
    run_root.mkdir(parents=True, exist_ok=True)

    validate_cmd = [
        str(plugin_python(plugin_root)),
        str(plugin_root / "scripts" / "validate-workflow-spec.py"),
        "--spec",
        str(spec_path),
        "--json",
    ]
    validate_code, validate_payload, validate_text = run_command(validate_cmd)
    if validate_code != 0 or validate_payload.get("status") != "PASS":
        payload = {{
            "status": "FAIL",
            "error": validate_text or "generated workflow spec validation failed",
            "run_root": str(run_root),
            "target_root": str(target_root),
            "spec": str(spec_path),
        }}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(payload["error"])
        return 1

    discovery_report = discover_host_capabilities(plugin_root, spec_path, target_root, run_root, args.request) if CAPABILITY_DISCOVERY_ENABLED else None
    host_report = probe_host_capabilities(plugin_root, spec_path, target_root, run_root)
    host_bootstrap = None
    environment_remediation_report = None
    auto_project_local = [
        item
        for item in host_report.get("bootstrap_plan", [])
        if isinstance(item, dict)
        and str(item.get("scope", "")).strip() == "project_local"
        and bool(item.get("approval_required", False)) is False
    ] if isinstance(host_report.get("bootstrap_plan", []), list) else []
    if auto_project_local:
        host_bootstrap = apply_host_bootstrap(
            plugin_root,
            spec_path,
            target_root,
            run_root,
        )
        host_report = probe_host_capabilities(plugin_root, spec_path, target_root, run_root)
    if isinstance(host_report.get("capabilities", []), list):
        environment_remediation_report = generate_environment_remediation(plugin_root, spec_path, target_root, run_root)

    runner_cmd = [
        sys.executable,
        str(target_root / RUNNER_SCRIPT_REL),
        "run",
        "--spec",
        str(spec_path),
        "--run-root",
        str(run_root),
        "--target-root",
        str(target_root),
        "--plugin-root",
        str(plugin_root),
        "--request",
        args.request,
        "--intent",
        args.intent,
        "--entry-skill",
        args.entry_skill,
        "--runtime-provider",
        args.runtime_provider,
        "--provider-command",
        args.provider_command,
        "--json",
    ]
    if args.auto_approve:
        runner_cmd.append("--auto-approve")
    if args.approval_status:
        runner_cmd.extend(["--approval-status", args.approval_status])
    runner_code, runner_payload, runner_text = run_command(runner_cmd)
    if runner_code not in {{0, 2, 3}} or not runner_payload:
        payload = {{
            "status": "FAIL",
            "error": runner_text or "generated workflow runner failed",
            "run_root": str(run_root),
            "target_root": str(target_root),
            "spec": str(spec_path),
        }}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(payload["error"])
        return 1

    validator_cmd = [
        sys.executable,
        str(target_root / STATE_VALIDATOR_SCRIPT_REL),
        "--state",
        str(run_root / "target-state.json"),
        "--plugin-root",
        str(plugin_root),
        "--json",
    ]
    state_code, state_payload, state_text = run_command(validator_cmd)
    if state_code != 0 or state_payload.get("status") != "PASS":
        payload = {{
            "status": "FAIL",
            "error": state_text or "generated workflow state validation failed",
            "run_root": str(run_root),
            "target_root": str(target_root),
            "spec": str(spec_path),
            "runner": runner_payload,
        }}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(payload["error"])
        return 1

    target_finalizer = None
    target_publish_state_validation = None
    runner_status = str(runner_payload.get("status", "")).strip()
    runner_blocked_phase = str(runner_payload.get("blocked_phase", "")).strip()
    should_run_target_finalizer = TARGET_PUBLISH_FINALIZER_ENABLED and not (
        runner_status == "BLOCKED" and runner_blocked_phase == "executor_evidence"
    )
    if should_run_target_finalizer:
        finalizer_code, finalizer_payload, finalizer_text = finalize_target_runtime(plugin_root, spec_path, target_root, run_root)
        target_finalizer = finalizer_payload or {{"status": "FAIL", "error": finalizer_text or "target runtime finalizer failed"}}
        if finalizer_code != 0 or target_finalizer.get("status") != "PASS":
            payload = {{
                "status": "FAIL",
                "failure_kind": "implementation",
                "error": finalizer_text or "generated workflow finalizer failed",
                "run_root": str(run_root),
                "target_root": str(target_root),
                "spec": str(spec_path),
                "runner": runner_payload,
                "state_validation": state_payload,
                "target_finalizer": target_finalizer,
            }}
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(payload["error"])
            return 1
        publish_state_code, publish_state_payload, publish_state_text = validate_target_publish_state(
            plugin_root,
            spec_path,
            target_root,
            run_root,
        )
        target_publish_state_validation = publish_state_payload or {{
            "status": "FAIL",
            "error": publish_state_text or "target publish state validation failed",
        }}
        if publish_state_code != 0 or target_publish_state_validation.get("status") != "PASS":
            payload = {{
                "status": "FAIL",
                "failure_kind": "implementation",
                "error": publish_state_text or "target publish state validation failed",
                "run_root": str(run_root),
                "target_root": str(target_root),
                "spec": str(spec_path),
                "runner": runner_payload,
                "state_validation": state_payload,
                "target_finalizer": target_finalizer,
                "target_publish_state_validation": target_publish_state_validation,
            }}
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(payload["error"])
            return 1

    effective_status = str(runner_payload.get("status", "PASS")).strip() or "PASS"
    if (
        effective_status == "BLOCKED"
        and isinstance(target_finalizer, dict)
        and str(target_finalizer.get("status", "")).strip() == "PASS"
    ):
        effective_status = "PASS"

    summary = {{
        "status": effective_status,
        "generated_runtime": True,
        "target_root": str(target_root),
        "run_root": str(run_root),
        "spec": str(spec_path),
        "entry_skill": args.entry_skill,
        "intent": args.intent,
        "runtime_capabilities": RUNTIME_CAPABILITIES,
        "capability_discovery_report": discovery_report,
        "host_capability_report": host_report,
        "host_bootstrap_result": host_bootstrap,
        "environment_remediation_report": environment_remediation_report,
        "team_orchestration_enabled": TEAM_ORCHESTRATION_ENABLED,
        "runner": runner_payload,
        "state_validation": state_payload,
        "target_finalizer": target_finalizer,
        "target_publish_state_validation": target_publish_state_validation,
    }}
    if required_host_missing(host_report):
        summary["status"] = "FAIL"
        summary["failure_kind"] = "environment"
    write_json(run_root / "outputs" / "stages" / "entry-orchestration-summary.json", summary)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"[{{summary['status']}}] generated workflow runtime completed: {{run_root}}")
    if summary["status"] == "PASS":
        return 0
    if summary["status"] == "ENVIRONMENT-SKIP":
        return 3
    if summary["status"] == "BLOCKED":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
"""


def render_runner_wrapper() -> str:
    return """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


def resolve_plugin_root(explicit: str) -> Path:
    if explicit:
        return Path(explicit).resolve()
    env_value = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if env_value:
        return Path(env_value).resolve()
    raise RuntimeError("generated workflow runner requires --plugin-root or CLAUDE_PLUGIN_ROOT")


def plugin_python(plugin_root: Path) -> Path:
    return plugin_root / "bin" / "workflowprogram-python"


def parse_json_output(text: str) -> Dict[str, Any]:
    text = text.strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        pass
    lines = [line for line in text.splitlines() if line.strip()]
    for idx in range(len(lines)):
        candidate = "\\n".join(lines[idx:])
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def run_command(cmd: List[str]) -> Tuple[int, Dict[str, Any], str]:
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    text = completed.stdout.strip() or completed.stderr.strip()
    return completed.returncode, parse_json_output(text), text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generated target workflow managed-runtime runner wrapper")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run generated workflow control plane")
    run.add_argument("--spec", required=True)
    run.add_argument("--run-root", required=True)
    run.add_argument("--target-root", required=True)
    run.add_argument("--plugin-root", default="")
    run.add_argument("--request", default="")
    run.add_argument("--intent", required=True)
    run.add_argument("--entry-skill", required=True)
    run.add_argument("--runtime-provider", default="")
    run.add_argument("--provider-command", default="")
    run.add_argument("--claude-bin", default="", help="Deprecated no-op; target runtime does not invoke Claude CLI")
    run.add_argument("--auto-approve", action="store_true")
    run.add_argument("--approval-status", default="", choices=["approved"])
    run.add_argument("--json", action="store_true")

    status = sub.add_parser("status", help="Read generated workflow runner status")
    status.add_argument("--run-root", required=True)
    status.add_argument("--plugin-root", default="")
    status.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plugin_root = resolve_plugin_root(getattr(args, "plugin_root", ""))
    cmd = [
        str(plugin_python(plugin_root)),
        str(plugin_root / "scripts" / "target-workflow-runner.py"),
        args.command,
    ]
    if args.command == "run":
        cmd.extend(
            [
                "--spec",
                str(Path(args.spec).resolve()),
                "--run-root",
                str(Path(args.run_root).resolve()),
                "--target-root",
                str(Path(args.target_root).resolve()),
                "--plugin-root",
                str(plugin_root),
                "--request",
                args.request,
                "--intent",
                args.intent,
                "--entry-skill",
                args.entry_skill,
                "--runtime-provider",
                args.runtime_provider,
                "--provider-command",
                args.provider_command,
                "--json",
            ]
        )
        if args.auto_approve:
            cmd.append("--auto-approve")
        if args.approval_status:
            cmd.extend(["--approval-status", args.approval_status])
    else:
        cmd.extend(["--run-root", str(Path(args.run_root).resolve()), "--json"])
    code, payload, text = run_command(cmd)
    if args.json:
        print(json.dumps(payload or {"status": "FAIL", "error": text or "runner wrapper failed"}, ensure_ascii=False, indent=2))
    else:
        print(text or json.dumps(payload, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
"""


def render_state_validator_wrapper() -> str:
    return """#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


def resolve_plugin_root(explicit: str) -> Path:
    if explicit:
        return Path(explicit).resolve()
    env_value = os.environ.get("CLAUDE_PLUGIN_ROOT", "").strip()
    if env_value:
        return Path(env_value).resolve()
    raise RuntimeError("generated workflow state validator requires --plugin-root or CLAUDE_PLUGIN_ROOT")


def plugin_python(plugin_root: Path) -> Path:
    return plugin_root / "bin" / "workflowprogram-python"


def parse_json_output(text: str) -> Dict[str, Any]:
    text = text.strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        pass
    lines = [line for line in text.splitlines() if line.strip()]
    for idx in range(len(lines)):
        candidate = "\\n".join(lines[idx:])
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def run_command(cmd: List[str]) -> Tuple[int, Dict[str, Any], str]:
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    text = completed.stdout.strip() or completed.stderr.strip()
    return completed.returncode, parse_json_output(text), text


def main() -> int:
    parser = argparse.ArgumentParser(description="Generated target workflow managed-runtime state validator wrapper")
    parser.add_argument("--state", required=True)
    parser.add_argument("--plugin-root", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    plugin_root = resolve_plugin_root(args.plugin_root)
    cmd = [
        str(plugin_python(plugin_root)),
        str(plugin_root / "scripts" / "validate-target-runtime-state.py"),
        "--state",
        str(Path(args.state).resolve()),
        "--json",
    ]
    code, payload, text = run_command(cmd)
    if args.json:
        print(json.dumps(payload or {"status": "FAIL", "error": text or "state validator wrapper failed"}, ensure_ascii=False, indent=2))
    else:
        print(text or json.dumps(payload, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
"""


def manifest_payload(
    contract: Dict[str, Any],
    main_entry: str,
    *,
    spec: Dict[str, Any],
) -> Dict[str, Any]:
    capability_discovery = capability_discovery_from_spec(spec)
    declared_host_capabilities = host_capabilities_from_spec(spec)
    target_runtime_policy = spec.get("target_runtime_policy", {})
    if not isinstance(target_runtime_policy, dict):
        target_runtime_policy = {}
    target_executor_policy = spec.get("target_executor_policy", {})
    if not isinstance(target_executor_policy, dict):
        target_executor_policy = {}
    managed_runtime = str(target_runtime_policy.get("mode", "")).strip() == "managed_runtime"
    target_publish_policy = spec.get("target_publish_policy", {})
    target_publish_enabled = isinstance(target_publish_policy, dict) and target_publish_policy.get("enabled") is True
    host_global_adapter_declared = any(
        str(item.get("bootstrap", {}).get("scope", "")).strip() == "host_global" and bool(host_global_adapter(item))
        for item in declared_host_capabilities
        if isinstance(item, dict) and isinstance(item.get("bootstrap"), dict)
    )
    return {
        "manifest_version": 1,
        "runtime_schema_version": 2,
        "generated_at": iso_now(),
        "runtime_mode": contract["mode"],
        "runtime_capabilities": contract["runtime_capabilities"],
        "managed_runtime": managed_runtime,
        "target_runtime_policy_mode": str(target_runtime_policy.get("mode", "")).strip(),
        "target_executor_policy": target_executor_policy,
        "target_publish_policy_enabled": target_publish_enabled,
        "runtime_root": contract["runtime_root"],
        "design_spec_path": contract["design_spec_path"],
        "entry_script": contract["entry_script"],
        "runner_script": contract["runner_script"],
        "state_validator_script": contract["state_validator_script"],
        "runtime_manifest": contract["runtime_manifest"],
        "run_root_dir": contract["run_root_dir"],
        "default_intent": "develop",
        "default_entry_skill": main_entry,
        "capability_discovery_enabled": bool(capability_discovery.get("enabled", False)),
        "capability_discovery_domains": capability_discovery.get("domains", []) if isinstance(capability_discovery.get("domains", []), list) else [],
        "host_capabilities_declared": bool(declared_host_capabilities),
        "host_global_adapter_declared": host_global_adapter_declared,
        "agent_team_enabled": agent_team_enabled(agent_team_contract_from_spec(spec)),
        "node_loop_enabled": node_loop_enabled(spec),
        "shared_plugin_dependency": True,
        "shared_scripts": [
            "target-workflow-runner.py",
            "validate-target-runtime-state.py",
            "target-runtime-finalizer.py",
            "validate-target-publish-state.py",
            "discover-host-capabilities.py",
            "apply-host-bootstrap.py",
            "probe-host-capabilities.py",
            "validate-workflow-spec.py",
        ],
    }


def main() -> int:
    args = parse_args()
    spec_path = Path(args.spec).resolve()
    out_root = Path(args.out_root).resolve()
    payload: Dict[str, Any] = {
        "status": "PASS",
        "spec": str(spec_path),
        "out_root": str(out_root),
        "files": {},
        "missing_top_keys": [],
    }
    try:
        spec = load_yaml_mapping(spec_path)
        payload["missing_top_keys"] = ensure_spec_shape(spec)
        contract = require_runtime_contract(spec)
        main_entry = default_entry_skill(spec)
        team_enabled_flag = agent_team_enabled(agent_team_contract_from_spec(spec))
        capability_discovery_enabled_flag = bool(capability_discovery_from_spec(spec).get("enabled", False))
        target_runtime_policy = spec.get("target_runtime_policy", {})
        target_managed_runtime_flag = isinstance(target_runtime_policy, dict) and str(target_runtime_policy.get("mode", "")).strip() == "managed_runtime"
        target_publish_policy = spec.get("target_publish_policy", {})
        target_publish_finalizer_enabled_flag = isinstance(target_publish_policy, dict) and target_publish_policy.get("enabled") is True

        entry_path = out_root / Path(contract["entry_script"]).name
        runner_path = out_root / Path(contract["runner_script"]).name
        validator_path = out_root / Path(contract["state_validator_script"]).name
        manifest_path = out_root / Path(contract["runtime_manifest"]).name

        out_root.mkdir(parents=True, exist_ok=True)
        entry_path.write_text(
            render_entry_wrapper(
                contract,
                main_entry,
                team_enabled_flag=team_enabled_flag,
                capability_discovery_enabled_flag=capability_discovery_enabled_flag,
                target_managed_runtime_flag=target_managed_runtime_flag,
                target_publish_finalizer_enabled_flag=target_publish_finalizer_enabled_flag,
            ),
            encoding="utf-8",
            newline="\n",
        )
        runner_path.write_text(render_runner_wrapper(), encoding="utf-8", newline="\n")
        validator_path.write_text(render_state_validator_wrapper(), encoding="utf-8", newline="\n")
        write_json(manifest_path, manifest_payload(contract, main_entry, spec=spec))

        payload["files"] = {
            "entry_script": str(entry_path),
            "runner_script": str(runner_path),
            "state_validator_script": str(validator_path),
            "runtime_manifest": str(manifest_path),
        }
    except Exception as exc:
        payload["status"] = "FAIL"
        payload["error"] = str(exc)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Error: {exc}")
        return 1

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Generated target runtime assets under {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
