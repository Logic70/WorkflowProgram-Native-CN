#!/usr/bin/env python3
"""WorkflowProgram-CN 的 runtime smoke harness。

该脚本会在复制出来的 fixture workspace 上执行一次最小端到端插件调用，
并把运行证据写入复制目标下的 RUN_ROOT。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / ".claude" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from lib.io_utils import iso_now, write_json
from lib.yaml_utils import try_load_yaml_mapping
from runtime_host import RuntimeHostInvocation, invoke_runtime_host, probe_runtime_host, resolve_runtime_host_config


FIXTURE_PRESETS: Dict[str, Dict[str, str]] = {
    "empty-project": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-develop",
        "request": "为当前项目设计一个最小 Claude Code workflow，至少包含 settings、一个 skill 和一个 rule 文件",
        "contract_categories": "entry,flow,artifacts,failure",
    },
    "existing-workflow": {
        "workspace_fixture": "existing-workflow",
        "entry_skill": "workflowprogram-audit",
        "request": "审计当前项目中的 workflow 结构，并输出结构问题、模式偏离和下一步建议",
        "contract_categories": "entry,flow,artifacts,failure",
    },
    "broken-workflow": {
        "workspace_fixture": "broken-workflow",
        "entry_skill": "workflowprogram-validate",
        "request": "验证当前项目中的 workflow 资产，并输出失败项、影响范围和修复优先级",
        "contract_categories": "entry,artifacts,failure",
    },
    "invalid-entry": {
        "workspace_fixture": "empty-project",
        "entry_skill": "missing-workflowprogram-entry",
        "request": "验证非法入口时是否被正确拒绝",
        "contract_categories": "entry,failure",
    },
    "missing-args": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-develop",
        "request": "",
        "contract_categories": "entry,failure",
    },
    "external-write": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-develop",
        "request": "触发 external-write 验证路径",
        "contract_categories": "boundary,artifacts,failure",
    },
    "managed-conflict": {
        "workspace_fixture": "existing-workflow",
        "entry_skill": "workflowprogram-develop",
        "request": "触发 managed-conflict 验证路径",
        "contract_categories": "boundary,artifacts,failure",
    },
    "capability-discovery-reverse-engineering": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-develop",
        "request": "为当前项目设计一个逆向分析 workflow，并识别需要的 skill、MCP 和 CLI 能力",
        "contract_categories": "artifacts,failure",
    },
    "host-capability-missing-develop": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-develop",
        "request": "触发 host capability 缺失验证路径",
        "contract_categories": "artifacts,failure",
    },
    "host-capability-project-local-bootstrap": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-develop",
        "request": "触发 project-local host bootstrap 验证路径",
        "contract_categories": "artifacts,failure",
    },
    "host-capability-host-global-bootstrap": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-develop",
        "request": "触发 host-global plan-only bootstrap 验证路径",
        "contract_categories": "artifacts,failure",
    },
    "host-capability-validate": {
        "workspace_fixture": "existing-workflow",
        "entry_skill": "workflowprogram-validate",
        "request": "验证目标工作流的宿主能力就绪状态",
        "contract_categories": "artifacts,failure",
    },
    "host-capability-audit": {
        "workspace_fixture": "existing-workflow",
        "entry_skill": "workflowprogram-audit",
        "request": "审计目标工作流的宿主能力声明与就绪状态",
        "contract_categories": "artifacts,failure",
    },
    "host-capability-iterate": {
        "workspace_fixture": "existing-workflow",
        "entry_skill": "workflowprogram-iterate",
        "request": "基于环境失败提炼宿主能力改进建议",
        "contract_categories": "artifacts,failure",
    },
    "agent-team-develop-pass": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-develop",
        "request": "触发 deterministic agent team orchestration PASS 路径",
        "contract_categories": "flow,artifacts,failure",
    },
    "agent-team-fanout-fail": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-develop",
        "request": "触发 deterministic agent team fan-out 失败路径",
        "contract_categories": "flow,artifacts,failure",
    },
    "agent-team-validate": {
        "workspace_fixture": "existing-workflow",
        "entry_skill": "workflowprogram-validate",
        "request": "验证目标工作流的 agent team orchestration 证据",
        "contract_categories": "flow,artifacts,failure",
    },
    "agent-team-audit": {
        "workspace_fixture": "existing-workflow",
        "entry_skill": "workflowprogram-audit",
        "request": "审计目标工作流的 agent team orchestration 契约",
        "contract_categories": "flow,artifacts,failure",
    },
    "node-loop-develop-pass": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-develop",
        "request": "触发 deterministic node loop PASS 路径，验证循环直到测试通过",
        "contract_categories": "flow,artifacts,failure",
    },
    "node-loop-max-iterations-fail": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-develop",
        "request": "触发 deterministic node loop max_iterations 失败路径",
        "contract_categories": "flow,artifacts,failure",
    },
    "change-policy-incremental-pass": {
        "workspace_fixture": "existing-workflow",
        "entry_skill": "workflowprogram-develop",
        "request": "修改已有工作流的 example 节点并应用",
        "contract_categories": "boundary,flow,artifacts,failure",
    },
    "change-policy-redesign-pass": {
        "workspace_fixture": "existing-workflow",
        "entry_skill": "workflowprogram-develop",
        "request": "重新设计已有工作流并保留历史设计作为输入",
        "contract_categories": "boundary,flow,artifacts,failure",
    },
    "change-policy-missing-fail": {
        "workspace_fixture": "existing-workflow",
        "entry_skill": "workflowprogram-develop",
        "request": "修改已有工作流但缺少 change policy",
        "contract_categories": "flow,artifacts,failure",
    },
    "change-policy-undeclared-write-fail": {
        "workspace_fixture": "existing-workflow",
        "entry_skill": "workflowprogram-develop",
        "request": "修改已有工作流但写出未声明资产",
        "contract_categories": "boundary,flow,artifacts,failure",
    },
    "change-policy-stale-context-fail": {
        "workspace_fixture": "existing-workflow",
        "entry_skill": "workflowprogram-develop",
        "request": "修改已有工作流但目标状态已变化",
        "contract_categories": "flow,artifacts,failure",
    },
    "design-review-closed-pass": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-develop",
        "request": "触发 S3 设计审视闭合后进入实现的 PASS 路径",
        "contract_categories": "flow,artifacts,failure",
    },
    "design-review-missing-fail": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-develop",
        "request": "触发 S3 设计审视缺失时阻断 S4 的 FAIL 路径",
        "contract_categories": "flow,artifacts,failure",
    },
    "design-review-blocker-fail": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-develop",
        "request": "触发 S3 设计审视存在 blocker 时阻断 S4 的 FAIL 路径",
        "contract_categories": "flow,artifacts,failure",
    },
    "design-review-accepted-risk-pass": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-develop",
        "request": "触发 S3 设计审视仅有 accepted risk 时允许进入实现的 PASS 路径",
        "contract_categories": "flow,artifacts,failure",
    },
    "publish-eligible-pass": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-publish",
        "request": "将已完成的目标工作流发布为 Claude Code marketplace 插件",
        "contract_categories": "artifacts,failure",
    },
    "publish-missing-develop-evidence-fail": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-publish",
        "request": "缺少完整 develop 证据时尝试发布目标工作流",
        "contract_categories": "artifacts,failure",
    },
    "publish-stale-managed-state-fail": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-publish",
        "request": "目标工作流托管资产发生漂移后尝试发布",
        "contract_categories": "artifacts,failure",
    },
    "publish-github-auth-missing-blocked": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-publish",
        "request": "GitHub 未登录时尝试执行发布",
        "contract_categories": "artifacts,failure",
    },
    "publish-package-validation-fail": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-publish",
        "request": "目标插件包元数据非法时尝试发布",
        "contract_categories": "artifacts,failure",
    },
    "publish-export-repo-plan": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-publish",
        "request": "为独立 export repo 生成目标工作流插件发布计划",
        "contract_categories": "artifacts,failure",
    },
    "publish-existing-marketplace-append-pass": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-publish",
        "request": "将目标 workflow 追加到已有 marketplace",
        "contract_categories": "artifacts,failure",
    },
    "publish-existing-marketplace-update-pass": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-publish",
        "request": "显式更新已有 marketplace 中同名 workflow plugin",
        "contract_categories": "artifacts,failure",
    },
    "publish-existing-marketplace-duplicate-plugin-blocked": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-publish",
        "request": "已有 marketplace 存在同名 plugin 且未授权更新",
        "contract_categories": "artifacts,failure",
    },
    "publish-existing-marketplace-source-mismatch-fail": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-publish",
        "request": "已有 marketplace 同名 plugin source 与固定目录不一致",
        "contract_categories": "artifacts,failure",
    },
    "publish-existing-marketplace-version-not-bumped-fail": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-publish",
        "request": "已有 marketplace 同名 plugin 版本未提升",
        "contract_categories": "artifacts,failure",
    },
    "publish-existing-marketplace-invalid-manifest-fail": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-publish",
        "request": "已有 marketplace manifest 非法",
        "contract_categories": "artifacts,failure",
    },
    "publish-existing-marketplace-dirty-checkout-blocked": {
        "workspace_fixture": "empty-project",
        "entry_skill": "workflowprogram-publish",
        "request": "已有 marketplace checkout 有未提交改动时执行发布",
        "contract_categories": "artifacts,failure",
    },
}


@dataclass
class RunVerdict:
    """smoke harness 在 S5 judge 前后统一使用的归一化 verdict。"""

    result: str
    category: Optional[str]
    message: str
    is_error: bool
    subagent_evidence: bool


@dataclass
class InvocationResult:
    """记录 runtime host 调用结果以及由此推导出的初步 verdict。"""

    command_text: str
    stdout: str
    stderr: str
    parsed: Dict[str, Any]
    verdict: RunVerdict


class RuntimeSmokeError(Exception):
    """表示在 provider 结果进入 judge 之前，harness 自身发生了失败。"""

    pass


def load_expectation(repo_root: Path, fixture: str) -> Tuple[Optional[Path], Optional[Dict[str, Any]]]:
    """加载某个 smoke fixture 对应的结构化 expectation。"""

    path = repo_root / "tests" / "expectations" / f"{fixture}.json"
    if not path.exists():
        return None, None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeSmokeError(f"invalid expectation file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeSmokeError(f"expectation file must be a JSON object: {path}")
    return path, payload


def evaluate_expectation(
    expectation: Dict[str, Any],
    *,
    entry_skill: str,
    final_result: str,
    final_category: Optional[str],
    run_root: Path,
    target_root: Path,
    transcript_text: str,
    report_text: str,
    stdout_text: str,
    stderr_text: str,
) -> List[str]:
    """根据结构化 expectation 校验一次 smoke 结果。"""

    mismatches: List[str] = []

    allowed_entry_skills = expectation.get("allowed_entry_skills", [])
    if isinstance(allowed_entry_skills, list) and allowed_entry_skills:
        allowed = [str(item).strip() for item in allowed_entry_skills if str(item).strip()]
        if entry_skill not in allowed:
            mismatches.append(f"entry_skill '{entry_skill}' not in allowed_entry_skills {allowed}")

    acceptable_results = expectation.get("acceptable_results", [])
    if isinstance(acceptable_results, list) and acceptable_results:
        allowed_results = [str(item).strip() for item in acceptable_results if str(item).strip()]
        if final_result not in allowed_results:
            mismatches.append(f"result '{final_result}' not in acceptable_results {allowed_results}")

    if "expected_category" in expectation:
        expected_category = expectation.get("expected_category")
        expected_text = None if expected_category is None else str(expected_category).strip() or None
        if final_category != expected_text:
            mismatches.append(f"category '{final_category}' does not match expected_category '{expected_text}'")

    required_files = expectation.get("required_files", [])
    if isinstance(required_files, list):
        for item in required_files:
            rel_path = str(item).strip()
            if rel_path and not (run_root / rel_path).exists():
                mismatches.append(f"required file missing: {rel_path}")

    required_target_files = expectation.get("required_target_files", [])
    if isinstance(required_target_files, list):
        for item in required_target_files:
            rel_path = str(item).strip()
            if rel_path and not (target_root / rel_path).exists():
                mismatches.append(f"required target file missing: {rel_path}")

    forbidden_patterns = expectation.get("forbidden_patterns", [])
    if isinstance(forbidden_patterns, list):
        combined_text = "\n".join([transcript_text, report_text, stdout_text, stderr_text])
        for item in forbidden_patterns:
            pattern = str(item)
            if pattern and pattern in combined_text:
                mismatches.append(f"forbidden pattern found: {pattern}")

    return mismatches


def make_run_id(fixture: str) -> str:
    """为一次 smoke 运行生成唯一的 transcript/run 目录 id。"""

    return f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{fixture}"


def write_text(path: Path, content: str) -> None:
    """创建父目录后写入 UTF-8 文本。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def append_event(path: Path, payload: Dict[str, Any]) -> None:
    """向 smoke JSONL 事件流追加一条结构化事件。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_yaml_mapping(path: Path) -> Optional[Dict[str, Any]]:
    """在存在运行时生成的 workflow spec 时加载其 YAML 映射。"""

    payload = try_load_yaml_mapping(path)
    return payload or None


def derive_contract_summary(run_root: Path, fixture_meta: Dict[str, str]) -> Dict[str, Any]:
    """为报告渲染推导 test/runtime contract 摘要。

    如果真实 workflow-spec.yaml 存在，smoke harness 会优先把它当作真源。
    fixture preset 只用于负例和特别早期的失败路径兜底。
    """

    spec_path = run_root / "workflow-spec.yaml"
    spec = load_yaml_mapping(spec_path)
    if spec is not None:
        test_contract = spec.get("test_contract", {})
        runtime_contract = spec.get("runtime_contract", {})
        if isinstance(test_contract, dict) and test_contract:
            categories = [name for name in ("entry", "boundary", "flow", "artifacts", "failure") if name in test_contract]
            failure = test_contract.get("failure", {})
            implemented_now = failure.get("implemented_now", []) if isinstance(failure, dict) else []
            environment_skip = runtime_contract.get("environment_skip", []) if isinstance(runtime_contract, dict) else []
            env_codes = []
            if isinstance(environment_skip, list):
                for item in environment_skip:
                    if isinstance(item, dict) and item.get("code"):
                        env_codes.append(str(item["code"]))
            return {
                "contract_source": "workflow-spec.yaml.test_contract",
                "contract_categories": categories,
                "implemented_failure_kinds": implemented_now if isinstance(implemented_now, list) else [],
                "environment_skip_codes": env_codes,
                "spec_path": str(spec_path),
            }

    preset_categories = [item.strip() for item in fixture_meta.get("contract_categories", "").split(",") if item.strip()]
    return {
        "contract_source": "fixture_preset",
        "contract_categories": preset_categories,
        "implemented_failure_kinds": [],
        "environment_skip_codes": [],
        "spec_path": str(spec_path) if spec_path.exists() else None,
    }


def detect_subagent_evidence(text: str) -> bool:
    """推断自由文本运行输出是否暗示了 subagent/task 活动。"""

    lowered = text.lower()
    tokens = [
        "subagentstart",
        "subagentstop",
        "subagent",
        "taskcreated",
        "taskcompleted",
    ]
    return any(token in lowered for token in tokens)


def sha256_file(path: Path) -> str:
    """为目标目录前后快照中的文件计算哈希。"""

    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def snapshot_tree(root: Path) -> List[Dict[str, Any]]:
    """对根目录下所有文件做快照，供后续基于 diff 的边界检查使用。"""

    if not root.exists():
        return []
    entries: List[Dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel_path = str(path.relative_to(root))
        entries.append(
            {
                "path": rel_path,
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
        )
    return entries


def snapshot_paths(entries: List[Dict[str, Any]]) -> List[str]:
    """把快照条目投影成相对路径列表。"""

    return [str(item.get("path", "")) for item in entries if str(item.get("path", "")).strip()]


def write_snapshot(path: Path, entries: List[Dict[str, Any]]) -> None:
    """按 S5 judge 需要的格式持久化文件树快照。"""

    write_json(
        path,
        {
            "files": snapshot_paths(entries),
            "entries": entries,
        },
    )


def update_state(state_path: Path, **changes: Any) -> Dict[str, Any]:
    """对 smoke 状态快照应用局部更新。"""

    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    else:
        state = {}
    state.setdefault("schema_version", 1)
    state.setdefault("schema_name", "runtime-smoke-state")
    state.update(changes)
    state["updated_at"] = iso_now()
    write_json(state_path, state)
    return state


def prepare_workspace(repo_root: Path, fixture: str, run_id: str) -> tuple[Path, Path]:
    """为单次 smoke 运行把 fixture 复制到隔离的 transcript 工作区。"""

    fixture_root = repo_root / "tests" / "fixtures" / fixture
    if not fixture_root.exists():
        raise RuntimeSmokeError(f"Fixture not found: {fixture_root}")

    workspace_root = repo_root / "tests" / "transcripts" / run_id
    target_root = workspace_root / "target"

    if workspace_root.exists():
        shutil.rmtree(workspace_root)
    workspace_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(fixture_root, target_root)
    return workspace_root, target_root


def run_s5_judge(
    repo_root: Path,
    run_root: Path,
    target_root: Path,
    verdict: RunVerdict,
    context: Dict[str, Any],
    checked_files: list[str],
    fixture_meta: Dict[str, str],
) -> Dict[str, Any]:
    """对收集到的 smoke 证据执行确定性的 S5 judge。"""

    cmd = [
        sys.executable,
        str(repo_root / ".claude" / "scripts" / "workflow-s5-judge.py"),
        "--run-root",
        str(run_root),
        "--target-root",
        str(target_root),
        "--result",
        verdict.result,
        "--failure-code",
        verdict.category or "",
        "--summary-message",
        verdict.message,
        "--entry-skill",
        str(context.get("entry_skill", "")),
        "--request",
        str(context.get("request", "")),
        "--fixture",
        str(context.get("fixture", "")),
        "--provider",
        str(context.get("runtime_provider", "")),
        "--fallback-contract-categories",
        fixture_meta.get("contract_categories", ""),
        "--json",
    ]
    for rel_path in checked_files:
        cmd.extend(["--checked-file", rel_path])
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeSmokeError(
            f"S5 judge failed: {completed.stderr.strip() or completed.stdout.strip() or completed.returncode}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeSmokeError(f"S5 judge returned invalid JSON: {exc}") from exc
    return payload if isinstance(payload, dict) else {}


def write_report(report_path: Path, context: Dict[str, Any], verdict: RunVerdict, state: Dict[str, Any], target_claude_files: list[str]) -> None:
    """写出人类可读的 runtime validation 报告。

    这份报告现在更多是 fallback/harness 视图；
    权威的最终 verdict 仍然以 workflow-s5-judge.py 为准。
    """

    contract_summary = context.get("contract_summary", {})
    lines = [
        "# Runtime Validation Report",
        "",
        f"- Run ID: `{context['run_id']}`",
        f"- Fixture: `{context['fixture']}`",
        f"- Entry skill: `{context['entry_skill']}`",
        f"- Result: `{verdict.result}`",
    ]
    if verdict.category:
        lines.append(f"- Category: `{verdict.category}`")
    lines.extend([
        f"- Target root: `{context['target_root']}`",
        f"- Plugin root: `{context['plugin_root']}`",
        f"- Plugin build manifest: `{context.get('plugin_build_manifest', 'not-captured')}`",
        f"- Contract source: `{contract_summary.get('contract_source', 'unknown')}`",
        f"- Contract categories: `{', '.join(contract_summary.get('contract_categories', [])) or 'none'}`",
        f"- Subagent evidence: `{str(state['subagent_evidence']).lower()}`",
        "",
        "## Message",
        "",
        verdict.message,
        "",
    ])
    implemented_failure_kinds = contract_summary.get("implemented_failure_kinds", [])
    environment_skip_codes = contract_summary.get("environment_skip_codes", [])
    if implemented_failure_kinds or environment_skip_codes:
        lines.extend([
            "## Contract Details",
            "",
        ])
        if implemented_failure_kinds:
            lines.extend(f"- Implemented failure kind: `{item}`" for item in implemented_failure_kinds)
        if environment_skip_codes:
            lines.extend(f"- Environment skip code: `{item}`" for item in environment_skip_codes)
        lines.append("")
    lines.extend([
        "## Output Snapshot",
        "",
    ])
    if target_claude_files:
        lines.extend(f"- `{item}`" for item in target_claude_files)
    else:
        lines.append("- No `.claude/` output files were detected in target workspace.")
    write_text(report_path, "\n".join(lines) + "\n")


def write_transcript(transcript_path: Path, command_text: str, stdout: str, stderr: str, verdict: RunVerdict, context: Dict[str, Any]) -> None:
    """写出供 S5 和人工审查使用的原始调用 transcript。"""

    contract_summary = context.get("contract_summary", {})
    lines = [
        "# Runtime Smoke Transcript",
        "",
        f"- Run ID: `{context['run_id']}`",
        f"- Fixture: `{context['fixture']}`",
        f"- Entry skill: `{context['entry_skill']}`",
        f"- Runtime provider: `{context.get('runtime_provider', 'unknown')}`",
        f"- Result: `{verdict.result}`",
        f"- Contract source: `{contract_summary.get('contract_source', 'unknown')}`",
        f"- Contract categories: `{', '.join(contract_summary.get('contract_categories', [])) or 'none'}`",
        "",
        "## Command",
        "",
        "```bash",
        command_text,
        "```",
        "",
        "## Stdout",
        "",
        "```text",
        stdout.strip() or "<empty>",
        "```",
        "",
        "## Stderr",
        "",
        "```text",
        stderr.strip() or "<empty>",
        "```",
    ]
    write_text(transcript_path, "\n".join(lines) + "\n")


def write_validation_summary(
    summary_path: Path,
    verdict: RunVerdict,
    checked_files: list[str],
    target_claude_files: list[str],
    contract_summary: Dict[str, Any],
) -> None:
    """在 Markdown 报告旁边写一份轻量级摘要载荷。"""

    payload = {
        "verdict": verdict.result,
        "failure_kind": verdict.category or "none",
        "checked_files": checked_files,
        "contract_source": contract_summary.get("contract_source"),
        "contract_categories": contract_summary.get("contract_categories", []),
        "implemented_failure_kinds": contract_summary.get("implemented_failure_kinds", []),
        "environment_skip_codes": contract_summary.get("environment_skip_codes", []),
        "target_claude_files": target_claude_files,
        "summary": verdict.message,
    }
    write_json(summary_path, payload)


def ensure_progress_outputs(run_root: Path, context: Dict[str, Any], verdict: RunVerdict) -> None:
    """当被调 provider 未生成 progress 产物时进行补齐。"""

    progress_root = run_root / "outputs" / "progress"
    current_path = progress_root / "current-progress.json"
    milestones_path = progress_root / "milestones.jsonl"
    user_progress_path = progress_root / "user-progress.md"

    current_stage = "S5" if verdict.result == "ENVIRONMENT-SKIP" else "finished"
    last_status = "warn" if verdict.result == "ENVIRONMENT-SKIP" else ("ok" if verdict.result == "PASS" else "error")
    next_action = (
        "fix environment and rerun"
        if verdict.result == "ENVIRONMENT-SKIP"
        else ("complete" if verdict.result == "PASS" else "inspect runtime failure and rerun")
    )

    if not current_path.exists():
        write_json(
            current_path,
            {
                "run_id": context["run_id"],
                "current_stage": current_stage,
                "current_node": "runtime_smoke",
                "percent": 100 if verdict.result == "PASS" else 60,
                "last_status": last_status,
                "last_verdict": verdict.result,
                "approval_status": "unknown",
                "next_action": next_action,
                "updated_at": iso_now(),
            },
        )
    if not milestones_path.exists():
        append_event(
            milestones_path,
            {
                "ts": iso_now(),
                "stage": current_stage,
                "node": "runtime_smoke",
                "event": "StageCompleted",
                "status": last_status,
                "result": verdict.result,
                "artifact_refs": [],
            },
        )
    if not user_progress_path.exists():
        write_text(
            user_progress_path,
            "\n".join(
                [
                    "# Workflow Progress",
                    "",
                    f"- run_id: `{context['run_id']}`",
                    f"- current_stage: `{current_stage}`",
                    "- current_node: `runtime_smoke`",
                    f"- percent: `{100 if verdict.result == 'PASS' else 60}`",
                    f"- last_status: `{last_status}`",
                    f"- last_verdict: `{verdict.result}`",
                    "- approval_status: `unknown`",
                    f"- updated_at: `{iso_now()}`",
                    "",
                    "## 历史关键节点结果",
                    "",
                    f"- runtime_smoke | {verdict.result} | {verdict.category or 'none'}",
                    "",
                    "## Next Action",
                    "",
                    f"- {next_action}",
                    "",
                ]
            ),
        )


def main() -> int:
    """端到端运行一个 smoke fixture，并输出最终 JSON 摘要。"""

    parser = argparse.ArgumentParser(description="Run runtime smoke validation for WorkflowProgram-CN")
    parser.add_argument("--fixture", default="empty-project", choices=sorted(FIXTURE_PRESETS.keys()))
    parser.add_argument("--entry-skill", help="Override fixture default entry skill")
    parser.add_argument("--request", help="Override fixture default request text")
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument("--runtime-provider", help="Runtime host provider")
    parser.add_argument("--provider-command", help="Provider command for runtime-provider=command_adapter")
    parser.add_argument("--execution-provider", help=argparse.SUPPRESS)
    parser.add_argument("--execution-command", help=argparse.SUPPRESS)
    parser.add_argument("--plugin-root", help="Override plugin root, defaults to dist/plugin")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--json", action="store_true", help="Print final summary as JSON")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    expectation_path, expectation = load_expectation(repo_root, args.fixture)
    plugin_root = Path(args.plugin_root).resolve() if args.plugin_root else (repo_root / "dist" / "plugin").resolve()
    plugin_build_manifest = plugin_root / "build-manifest.json"
    fixture_meta = FIXTURE_PRESETS[args.fixture]
    entry_skill = args.entry_skill or fixture_meta["entry_skill"]
    request = args.request or fixture_meta["request"]
    runtime_host = resolve_runtime_host_config(
        provider=args.runtime_provider or args.execution_provider or "",
        claude_bin=args.claude_bin,
        provider_command=args.provider_command or args.execution_command or "",
    )
    run_id = make_run_id(args.fixture)

    workspace_root = repo_root / "tests" / "transcripts" / run_id
    target_root = workspace_root / "target"
    run_root = target_root / ".workflowprogram" / "runs" / run_id
    outputs_root = run_root / "outputs"

    context = {
        "run_id": run_id,
        "started_at": iso_now(),
        "plugin_root": str(plugin_root),
        "target_root": str(target_root),
        "fixture": args.fixture,
        "entry_skill": entry_skill,
        "request": request,
        "claude_bin": args.claude_bin,
        "runtime_provider": runtime_host.provider,
        "provider_command": runtime_host.provider_command or None,
        "mode": "runtime-smoke",
        "plugin_build_manifest": str(plugin_build_manifest) if plugin_build_manifest.exists() else None,
        "contract_summary": derive_contract_summary(run_root, fixture_meta),
    }

    def emit(event_type: str, stage: str, status: str, message: str) -> None:
        append_event(
            run_root / "events.jsonl",
            {
                "ts": iso_now(),
                "type": event_type,
                "stage": stage,
                "source": "runtime_smoke",
                "status": status,
                "message": message,
            },
        )
        current = 0
        state_path = run_root / "state.json"
        if state_path.exists():
            current = json.loads(state_path.read_text(encoding="utf-8")).get("events_written", 0)
        update_state(state_path, events_written=current + 1)

    try:
        if not plugin_root.exists():
            raise RuntimeSmokeError(f"Plugin root not found: {plugin_root}")

        # 每次 smoke 运行都基于复制出来的 fixture，
        # 这样源 fixture 保持干净，且本次运行会留下可回放的 transcript 目录。
        workspace_fixture = fixture_meta.get("workspace_fixture", args.fixture)
        workspace_root, target_root = prepare_workspace(repo_root, workspace_fixture, run_id)
        run_root = target_root / ".workflowprogram" / "runs" / run_id
        outputs_root = run_root / "outputs"
        outputs_root.mkdir(parents=True, exist_ok=True)
        context["target_root"] = str(target_root)
        write_json(run_root / "context.json", context)
        update_state(
            run_root / "state.json",
            run_id=run_id,
            status="initializing",
            stage="prepare",
            result=None,
            category=None,
            subagent_evidence=False,
            events_written=0,
            started_at=context["started_at"],
        )
        emit("RunStarted", "prepare", "ok", f"Preparing fixture {args.fixture}")
        before_target_root = snapshot_tree(target_root)
        before_target_claude = snapshot_tree(target_root / ".claude")
        write_snapshot(outputs_root / "target-root-before.json", before_target_root)
        write_snapshot(outputs_root / "target-claude-before.json", before_target_claude)

        update_state(
            run_root / "state.json",
            status="running",
            stage="invoke",
            result=None,
            category=None,
            subagent_evidence=False,
        )
        emit("TaskCreated", "invoke", "ok", f"Invoking provider={runtime_host.provider} for /{entry_skill}")
        # 先做 probe，这样环境失败会产出结构化 skip，
        # 而不是低信号的子进程错误。
        host_probe = probe_runtime_host(runtime_host)
        if not host_probe.available:
            host_invocation = RuntimeHostInvocation(
                provider=runtime_host.provider,
                result="ENVIRONMENT-SKIP",
                failure_code="RUNTIME_HOST_MISSING",
                message=host_probe.message,
                is_error=False,
                parsed={
                    "provider": runtime_host.provider,
                    "probe_available": host_probe.available,
                    "probe_ready": host_probe.ready,
                    "probe_message": host_probe.message,
                },
            )
        elif not host_probe.ready:
            host_invocation = RuntimeHostInvocation(
                provider=runtime_host.provider,
                result="ENVIRONMENT-SKIP",
                failure_code="RUNTIME_HOST_NOT_READY",
                message=host_probe.message,
                is_error=False,
                parsed={
                    "provider": runtime_host.provider,
                    "probe_available": host_probe.available,
                    "probe_ready": host_probe.ready,
                    "probe_message": host_probe.message,
                },
            )
        else:
            try:
                host_invocation = invoke_runtime_host(
                    runtime_host,
                    plugin_root,
                    target_root,
                    run_root,
                    entry_skill,
                    request,
                    args.timeout,
                    fixture=args.fixture,
                )
            except RuntimeError as exc:
                raise RuntimeSmokeError(str(exc)) from exc
        invocation = InvocationResult(
            command_text=" ".join(shlex.quote(item) for item in host_invocation.command) if host_invocation.command else f"<provider={runtime_host.provider}>",
            stdout=host_invocation.stdout,
            stderr=host_invocation.stderr,
            parsed=host_invocation.to_dict(),
            verdict=RunVerdict(
                result=host_invocation.result,
                category=host_invocation.failure_code or None,
                message=host_invocation.message,
                is_error=host_invocation.is_error,
                subagent_evidence=host_invocation.subagent_evidence,
            ),
        )

        verdict = invocation.verdict
        if verdict.result == "ENVIRONMENT-SKIP":
            emit("EnvironmentSkip", "invoke", "warn", verdict.message)
        elif verdict.is_error:
            emit("RuntimeError", "invoke", "error", verdict.message)

        emit("TaskCompleted", "invoke", "ok" if not verdict.is_error else "error", verdict.message)

        # 同时采集 target-root 和仅 .claude 范围的前后快照，
        # 这样 S5 才能同时推断交付情况与边界违规。
        after_target_claude = snapshot_tree(target_root / ".claude")
        after_target_root = snapshot_tree(target_root)
        write_snapshot(outputs_root / "target-claude-before.json", before_target_claude)
        write_snapshot(outputs_root / "target-claude-files.json", after_target_claude)
        write_snapshot(outputs_root / "target-root-before.json", before_target_root)
        write_snapshot(outputs_root / "target-root-files.json", after_target_root)
        write_json(
            outputs_root / "runtime-provider-result.json",
            invocation.parsed,
        )
        if plugin_build_manifest.exists():
            shutil.copy2(plugin_build_manifest, outputs_root / "plugin-build-manifest.json")
            emit("OutputWritten", "invoke", "ok", "Captured plugin build manifest into RUN_ROOT outputs")
        write_text(outputs_root / "stdout.log", invocation.stdout)
        write_text(outputs_root / "stderr.log", invocation.stderr)
        update_state(
            run_root / "state.json",
            status="completed" if verdict.result != "ENVIRONMENT-SKIP" else "skipped",
            stage="finished",
            result=verdict.result,
            category=verdict.category,
            subagent_evidence=verdict.subagent_evidence,
        )
        ensure_progress_outputs(run_root, context, verdict)
        context["contract_summary"] = derive_contract_summary(run_root, fixture_meta)
        checked_files = [
            "context.json",
            "state.json",
            "events.jsonl",
            "transcript.md",
            "validation-runtime-report.md",
            "outputs/progress/current-progress.json",
            "outputs/progress/milestones.jsonl",
            "outputs/progress/user-progress.md",
            "outputs/stdout.log",
            "outputs/stderr.log",
            "outputs/runtime-provider-result.json",
            "outputs/target-claude-before.json",
            "outputs/target-claude-files.json",
            "outputs/target-root-before.json",
            "outputs/target-root-files.json",
        ]
        for rel_path in (
            "outputs/managed-change-plan.json",
            "outputs/managed-change-result.json",
            "outputs/managed-change-summary.md",
            "outputs/managed-rollback-manifest.json",
            "outputs/managed-recover-instructions.md",
            "outputs/mock-runtime-host.log",
            "outputs/stages/clarification-record.json",
            "outputs/stages/open-questions.json",
            "outputs/stages/assumption-log.md",
            "outputs/stages/design-readiness-report.json",
            "outputs/stages/question-backlog.json",
            "outputs/stages/requirement-logic-map.json",
            "outputs/stages/clarification-challenge-report.json",
            "outputs/stages/clarification-handoff.json",
            "outputs/stages/clarification-evidence.json",
            "outputs/stages/host-capability-report.json",
            "outputs/stages/host-capability-probe.json",
            "outputs/stages/host-bootstrap-plan.json",
            "outputs/stages/host-bootstrap-apply.json",
            "outputs/stages/team-plan.json",
            "outputs/stages/team-results.json",
            "outputs/stages/team-join-summary.json",
            "workflow-spec.md",
            "outputs/stages/s6-lessons-delta.md",
            "outputs/stages/publish/publish-intent.json",
            "outputs/stages/publish/publish-options.json",
            "outputs/stages/publish/publish-eligibility.json",
            "outputs/stages/publish/plugin-package-plan.json",
            "outputs/stages/publish/plugin-manifest-preview.json",
            "outputs/stages/publish/plugin-validation-report.json",
            "outputs/stages/publish/marketplace-resolution.json",
            "outputs/stages/publish/marketplace-merge-plan.json",
            "outputs/stages/publish/marketplace-manifest-preview.json",
            "outputs/stages/publish/marketplace-validation-report.json",
            "outputs/stages/publish/github-publish-plan.json",
            "outputs/stages/publish/github-publish-result.json",
            "outputs/stages/publish/install-instructions.md",
            "outputs/stages/publish/publish-summary.json",
        ):
            if (run_root / rel_path).exists():
                checked_files.append(rel_path)
        if plugin_build_manifest.exists():
            checked_files.append("outputs/plugin-build-manifest.json")
        write_transcript(run_root / "transcript.md", invocation.command_text, invocation.stdout, invocation.stderr, verdict, context)
        # provider 给出的初步 verdict 不是最终结果。
        # judge 会结合 test_contract/runtime_contract 和已记录证据重新评估，
        # 并可能覆盖原始观测结果。
        judge_payload = run_s5_judge(
            repo_root,
            run_root,
            target_root,
            verdict,
            context,
            checked_files,
            fixture_meta,
        )
        context["contract_summary"] = {
            "contract_source": judge_payload.get("contract_source"),
            "contract_categories": judge_payload.get("contract_categories", []),
            "implemented_failure_kinds": judge_payload.get("implemented_failure_kinds", []),
            "environment_skip_codes": judge_payload.get("environment_skip_codes", []),
        }
        final_result = str(judge_payload.get("verdict", verdict.result))
        final_failure_code = str(judge_payload.get("failure_code", verdict.category or "none"))
        transcript_text = (run_root / "transcript.md").read_text(encoding="utf-8") if (run_root / "transcript.md").exists() else ""
        report_text = (
            (run_root / "validation-runtime-report.md").read_text(encoding="utf-8")
            if (run_root / "validation-runtime-report.md").exists()
            else ""
        )
        expectation_mismatches: List[str] = []
        if expectation is not None:
            expectation_mismatches = evaluate_expectation(
                expectation,
                entry_skill=entry_skill,
                final_result=final_result,
                final_category=final_failure_code if final_failure_code != "none" else None,
                run_root=run_root,
                target_root=target_root,
                transcript_text=transcript_text,
                report_text=report_text,
                stdout_text=invocation.stdout,
                stderr_text=invocation.stderr,
            )
            if expectation_mismatches:
                final_result = "FAIL"
                final_failure_code = "EXPECTATION_MISMATCH"
                emit("ExpectationMismatch", "finished", "error", "; ".join(expectation_mismatches))
        update_state(
            run_root / "state.json",
            status="completed" if final_result != "ENVIRONMENT-SKIP" else "skipped",
            stage="finished",
            result=final_result,
            category=final_failure_code,
            observed_result=verdict.result,
            observed_category=verdict.category,
            subagent_evidence=verdict.subagent_evidence,
        )
        emit("RunFinished", "finished", "ok" if final_result == "PASS" else "warn", f"Run finished with result {final_result}")

        summary = {
            "run_id": run_id,
            "fixture": args.fixture,
            "entry_skill": entry_skill,
            "runtime_provider": runtime_host.provider,
            "result": final_result,
            "category": final_failure_code if final_failure_code != "none" else None,
            "observed_result": verdict.result,
            "observed_category": verdict.category,
            "contract_source": context["contract_summary"].get("contract_source"),
            "contract_categories": context["contract_summary"].get("contract_categories", []),
            "run_root": str(run_root),
            "target_root": str(target_root),
            "expectation_file": str(expectation_path) if expectation_path else None,
            "expectation_mismatches": expectation_mismatches,
        }
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(f"Result: {final_result}")
            if summary["category"]:
                print(f"Category: {summary['category']}")
            print(f"Run root: {run_root}")
        return 0 if final_result in {"PASS", "ENVIRONMENT-SKIP"} else 1

    except RuntimeSmokeError as exc:
        # 即使是 harness 级失败，也要进入 judge，
        # 这样负例路径也能产出与成功路径同形状的 S5 输出。
        emit("RuntimeError", "prepare", "error", str(exc))
        update_state(
            run_root / "state.json",
            status="completed",
            stage="finished",
            result="FAIL",
            category="STRUCTURE_FAILURE",
            subagent_evidence=False,
        )
        verdict = RunVerdict(
            result="FAIL",
            category="STRUCTURE_FAILURE",
            message=str(exc),
            is_error=True,
            subagent_evidence=False,
        )
        context["contract_summary"] = derive_contract_summary(run_root, fixture_meta)
        write_text(run_root / "transcript.md", f"# Runtime Smoke Transcript\n\n{exc}\n")
        ensure_progress_outputs(run_root, context, verdict)
        judge_payload = run_s5_judge(
            repo_root,
            run_root,
            target_root,
            verdict,
            context,
            [
                "context.json",
                "state.json",
                "events.jsonl",
                "transcript.md",
                "validation-runtime-report.md",
                "outputs/progress/current-progress.json",
                "outputs/progress/milestones.jsonl",
                "outputs/progress/user-progress.md",
            ],
            fixture_meta,
        )
        context["contract_summary"] = {
            "contract_source": judge_payload.get("contract_source"),
            "contract_categories": judge_payload.get("contract_categories", []),
            "implemented_failure_kinds": judge_payload.get("implemented_failure_kinds", []),
            "environment_skip_codes": judge_payload.get("environment_skip_codes", []),
        }
        final_result = str(judge_payload.get("verdict", verdict.result))
        final_failure_code = str(judge_payload.get("failure_code", verdict.category or "STRUCTURE_FAILURE"))
        transcript_text = (run_root / "transcript.md").read_text(encoding="utf-8") if (run_root / "transcript.md").exists() else ""
        report_text = (
            (run_root / "validation-runtime-report.md").read_text(encoding="utf-8")
            if (run_root / "validation-runtime-report.md").exists()
            else ""
        )
        expectation_mismatches: List[str] = []
        if expectation is not None:
            expectation_mismatches = evaluate_expectation(
                expectation,
                entry_skill=entry_skill,
                final_result=final_result,
                final_category=final_failure_code if final_failure_code != "none" else None,
                run_root=run_root,
                target_root=target_root,
                transcript_text=transcript_text,
                report_text=report_text,
                stdout_text="",
                stderr_text=str(exc),
            )
            if expectation_mismatches:
                final_result = "FAIL"
                final_failure_code = "EXPECTATION_MISMATCH"
                emit("ExpectationMismatch", "finished", "error", "; ".join(expectation_mismatches))
        update_state(
            run_root / "state.json",
            status="completed" if final_result != "ENVIRONMENT-SKIP" else "skipped",
            stage="finished",
            result=final_result,
            category=final_failure_code,
            observed_result=verdict.result,
            observed_category=verdict.category,
            subagent_evidence=verdict.subagent_evidence,
        )
        emit("RunFinished", "finished", "error", f"Run finished with result {final_result}")
        summary = {
            "run_id": run_id,
            "fixture": args.fixture,
            "entry_skill": entry_skill,
            "runtime_provider": runtime_host.provider,
            "result": final_result,
            "category": final_failure_code if final_failure_code != "none" else None,
            "observed_result": verdict.result,
            "observed_category": verdict.category,
            "contract_source": context["contract_summary"].get("contract_source"),
            "contract_categories": context["contract_summary"].get("contract_categories", []),
            "run_root": str(run_root),
            "target_root": str(target_root),
            "expectation_file": str(expectation_path) if expectation_path else None,
            "expectation_mismatches": expectation_mismatches,
        }
        if args.json:
            print(json.dumps(summary, ensure_ascii=False, indent=2))
        else:
            print(f"Result: {final_result}")
            if summary["category"]:
                print(f"Category: {summary['category']}")
            print(f"Run root: {run_root}")
        return 0 if final_result in {"PASS", "ENVIRONMENT-SKIP"} else 1


if __name__ == "__main__":
    sys.exit(main())
