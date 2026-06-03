#!/usr/bin/env python3
"""
为 WorkflowProgram 的 smoke 和环境检查提供 runtime host 抽象层。
"""

from __future__ import annotations

import os
import hashlib
import json
import shlex
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from lib.failure_codes import failure_kind_from_code
from lib.io_utils import iso_now, write_json
from lib.target_design_refs import (
    PERSISTENT_DEFAULTS,
    iter_existing_node_design_refs,
    resolve_existing_run_refs,
    resolve_target_design_refs,
)


AUTH_STATUS_TIMEOUT_SECONDS = 5
VALID_RUNTIME_PROVIDERS = {"claude_cli", "fixture_host", "command_adapter"}


@dataclass
class RuntimeHostConfig:
    """在 smoke 和 runner 层之间传递的 runtime host 选择结果。"""

    provider: str
    claude_bin: str = "claude"
    provider_command: str = ""


@dataclass
class RuntimeHostProbe:
    """具体 runtime host provider 的 available/ready 探测结果。"""

    provider: str
    available: bool
    ready: bool
    message: str


@dataclass
class RuntimeHostInvocation:
    """所有 runtime provider 统一返回的归一化调用结果。

    对其余栈层来说，执行来自 Claude CLI、确定性的 fixture host，
    还是外部 command adapter，都应该被同一套结构抽象掉。
    """

    provider: str
    result: str
    failure_code: str
    message: str
    is_error: bool
    command: List[str] = field(default_factory=list)
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    parsed: Optional[Dict[str, Any]] = None
    subagent_evidence: bool = False
    stage_history: List[str] = field(default_factory=list)
    current_stage: str = ""
    stage_status: str = ""
    next_action: str = ""
    next_stage_on_failure: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def parse_bool_env(value: Optional[str]) -> Optional[bool]:
    """解析常见布尔环境变量写法。"""

    if value is None:
        return None
    text = value.strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def resolve_runtime_host_config(
    *,
    provider: str = "",
    claude_bin: str = "claude",
    provider_command: str = "",
) -> RuntimeHostConfig:
    """根据 CLI 参数和环境默认值解析 runtime host 配置。"""

    provider_name = (provider or "").strip() or os.environ.get("WORKFLOWPROGRAM_RUNTIME_PROVIDER", "").strip()
    if not provider_name:
        provider_name = "claude_cli"
    if provider_name not in VALID_RUNTIME_PROVIDERS:
        raise RuntimeError(
            f"unsupported runtime provider '{provider_name}', expected one of {sorted(VALID_RUNTIME_PROVIDERS)}"
        )
    command = provider_command.strip() or os.environ.get("WORKFLOWPROGRAM_RUNTIME_PROVIDER_COMMAND", "").strip()
    return RuntimeHostConfig(provider=provider_name, claude_bin=claude_bin, provider_command=command)


def read_json_from_output(stdout: str, stderr: str) -> Optional[Dict[str, Any]]:
    """尽可能从 provider 输出流中提取 JSON 对象。"""

    candidates: List[str] = []
    for stream in (stdout, stderr):
        for line in stream.splitlines():
            stripped = line.strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                candidates.append(stripped)
    for raw in reversed(candidates):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def detect_subagent_evidence(text: str) -> bool:
    """推断运行输出中是否包含 task/subagent 证据标记。"""

    lowered = text.lower()
    return any(token in lowered for token in ("subagentstart", "subagentstop", "subagent", "taskcreated", "taskcompleted"))


def _claude_command(claude_bin: str, plugin_root: Path, entry_skill: str, request: str) -> List[str]:
    """构造真实运行时使用的 Claude CLI 调用命令。"""

    invocation = f"/{entry_skill} {request}".strip()
    return [
        claude_bin,
        "-p",
        "--plugin-dir",
        str(plugin_root),
        "--output-format",
        "json",
        invocation,
    ]


def _probe_claude(config: RuntimeHostConfig) -> RuntimeHostProbe:
    """检查 Claude CLI 是否存在且已准备好执行。"""

    binary = shutil.which(config.claude_bin)
    if binary is None:
        return RuntimeHostProbe(config.provider, False, False, f"Claude binary not found: {config.claude_bin}")

    # 测试可以覆盖登录状态，这样即使机器上没有交互式 Claude 会话，
    # runtime 校验也能保持确定性。
    override = parse_bool_env(os.environ.get("WORKFLOWPROGRAM_CLAUDE_LOGGED_IN"))
    if override is not None:
        return RuntimeHostProbe(config.provider, True, override, f"WORKFLOWPROGRAM_CLAUDE_LOGGED_IN override={override}")

    try:
        completed = subprocess.run(
            [binary, "auth", "status"],
            capture_output=True,
            text=True,
            check=False,
            timeout=AUTH_STATUS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return RuntimeHostProbe(config.provider, True, False, f"claude auth status timed out after {AUTH_STATUS_TIMEOUT_SECONDS}s")

    output = completed.stdout.strip() or completed.stderr.strip()
    if completed.returncode != 0:
        return RuntimeHostProbe(config.provider, True, False, output or f"claude auth status exited with code {completed.returncode}")

    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return RuntimeHostProbe(config.provider, True, False, f"claude auth status returned non-JSON output: {output or '<empty>'}")

    logged_in = payload.get("loggedIn")
    if logged_in is True:
        return RuntimeHostProbe(config.provider, True, True, output or "claude auth status reported loggedIn=true")
    if logged_in is False:
        return RuntimeHostProbe(config.provider, True, False, output or "claude auth status reported loggedIn=false")
    return RuntimeHostProbe(config.provider, True, False, "claude auth status did not include a boolean loggedIn field")


def _classify_claude_result(stdout: str, stderr: str, parsed: Optional[Dict[str, Any]], returncode: int) -> RuntimeHostInvocation:
    """把原始 Claude CLI 输出归一化为共享调用结果结构。"""

    combined = "\n".join(part for part in [stdout.strip(), stderr.strip()] if part)
    subagent_evidence = detect_subagent_evidence(combined + "\n" + json.dumps(parsed or {}, ensure_ascii=False))

    # 环境类失败会被有意降级为 ENVIRONMENT-SKIP，
    # 这样 smoke 运行仍能产出有价值的证据。
    if "Not logged in · Please run /login" in combined:
        return RuntimeHostInvocation(
            provider="claude_cli",
            result="ENVIRONMENT-SKIP",
            failure_code="CLAUDE_NOT_LOGGED_IN",
            message="Claude CLI is installed but not logged in.",
            is_error=False,
            stdout=stdout,
            stderr=stderr,
            parsed=parsed,
            returncode=returncode,
            subagent_evidence=subagent_evidence,
        )

    # 缺失插件入口属于产品结构问题，而不是宿主问题。
    if "Unknown skill:" in combined or "Unknown command" in combined:
        return RuntimeHostInvocation(
            provider="claude_cli",
            result="FAIL",
            failure_code="STRUCTURE_FAILURE",
            message="Plugin entry was not discovered by Claude CLI.",
            is_error=True,
            stdout=stdout,
            stderr=stderr,
            parsed=parsed,
            returncode=returncode,
            subagent_evidence=subagent_evidence,
        )

    # 如果拿到了结构化 Claude JSON，就应优先于裸 return code，
    # 因为它包含了宿主对执行结果最强的语义解释。
    if parsed is not None:
        result_text = str(parsed.get("result", ""))
        is_error = bool(parsed.get("is_error", False))
        return RuntimeHostInvocation(
            provider="claude_cli",
            result="FAIL" if is_error else "PASS",
            failure_code="RUNTIME_FAILURE" if is_error else "",
            message=result_text or ("Claude CLI returned an error result." if is_error else "Claude CLI completed successfully."),
            is_error=is_error,
            stdout=stdout,
            stderr=stderr,
            parsed=parsed,
            returncode=returncode,
            subagent_evidence=subagent_evidence,
        )

    if returncode != 0:
        return RuntimeHostInvocation(
            provider="claude_cli",
            result="FAIL",
            failure_code="RUNTIME_FAILURE",
            message="Claude CLI exited with non-zero status without structured JSON output.",
            is_error=True,
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            subagent_evidence=subagent_evidence,
        )

    return RuntimeHostInvocation(
        provider="claude_cli",
        result="FAIL",
        failure_code="EVIDENCE_FAILURE",
        message="No structured Claude CLI JSON output was captured.",
        is_error=True,
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
        subagent_evidence=subagent_evidence,
    )


def _command_adapter_base(config: RuntimeHostConfig) -> List[str]:
    """把外部 adapter 命令归一化成可执行的 argv 列表。"""

    if not config.provider_command:
        raise RuntimeError("runtime provider 'command_adapter' requires WORKFLOWPROGRAM_RUNTIME_PROVIDER_COMMAND or --provider-command")
    raw = shlex.split(config.provider_command)
    repo_root = _repo_root()
    normalized: List[str] = []
    for idx, token in enumerate(raw):
        if not token:
            continue
        if idx == 0 and shutil.which(token):
            normalized.append(token)
            continue
        if token.startswith("-"):
            normalized.append(token)
            continue
        if idx > 0 and raw[idx - 1] in {"-m", "--module"}:
            normalized.append(token)
            continue
        candidate = Path(token)
        # 相对 adapter 路径会相对仓库根目录解析，
        # 这样调用方可以直接传项目内脚本，而不必写绝对路径。
        repo_candidate = (repo_root / token).resolve()
        if candidate.is_absolute():
            normalized.append(str(candidate))
        elif repo_candidate.exists():
            normalized.append(str(repo_candidate))
        else:
            normalized.append(token)
    return normalized


def _probe_command_adapter(config: RuntimeHostConfig) -> RuntimeHostProbe:
    """通过 JSON 协议探测外部 command adapter。"""

    try:
        base = _command_adapter_base(config)
    except RuntimeError as exc:
        return RuntimeHostProbe(config.provider, False, False, str(exc))

    binary = shutil.which(base[0]) or (Path(base[0]).resolve() if Path(base[0]).exists() else None)
    if binary is None:
        return RuntimeHostProbe(config.provider, False, False, f"Provider command not found: {base[0]}")

    completed = subprocess.run(
        [*base, "probe", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    output = completed.stdout.strip() or completed.stderr.strip()
    if completed.returncode != 0:
        return RuntimeHostProbe(config.provider, True, False, output or f"provider probe exited with code {completed.returncode}")
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return RuntimeHostProbe(config.provider, True, False, f"provider probe returned non-JSON output: {output or '<empty>'}")
    available = bool(payload.get("available", True))
    ready = bool(payload.get("ready", available))
    message = str(payload.get("message", output or "provider probe completed")).strip()
    return RuntimeHostProbe(config.provider, available, ready, message)


def probe_runtime_host(config: RuntimeHostConfig) -> RuntimeHostProbe:
    """在不触发真实 workflow 运行的前提下探测选定 runtime host。"""

    if config.provider == "claude_cli":
        return _probe_claude(config)
    if config.provider == "fixture_host":
        return RuntimeHostProbe(config.provider, True, True, "Deterministic fixture host is ready.")
    if config.provider == "command_adapter":
        return _probe_command_adapter(config)
    raise RuntimeError(f"unsupported runtime provider '{config.provider}'")


def _repo_root() -> Path:
    """根据已安装脚本位置返回仓库根目录。"""

    return Path(__file__).resolve().parents[2]


def _write_text(path: Path, content: str) -> None:
    """fixture_host 使用的内部 UTF-8 文本写入器。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    """fixture_host 使用的内部 JSONL 追加器。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _entry_exists(plugin_root: Path, entry_skill: str) -> bool:
    """检查插件入口是否能在运行时加载布局中被发现。"""

    candidates = [
        plugin_root / "skills" / entry_skill / "SKILL.md",
        plugin_root / "commands" / f"{entry_skill}.md",
        plugin_root / "skills" / f"command-{entry_skill}" / "SKILL.md",
    ]
    return any(path.exists() for path in candidates)


def _stage_history_for_entry(entry_skill: str) -> List[str]:
    """返回 fixture_host 暴露的简化逻辑阶段历史。"""

    if entry_skill == "workflowprogram-publish":
        return ["publish"]
    if entry_skill == "workflowprogram-audit":
        return ["validate", "lessons"]
    if entry_skill == "workflowprogram-validate":
        return ["validate"]
    if entry_skill == "workflowprogram-iterate":
        return ["lessons"]
    return ["requirement", "context", "design", "generate", "validate", "lessons"]


def _write_workflow_spec_draft(run_root: Path, entry_skill: str, request: str) -> None:
    """为 fixture_host 生成确定性的 S1 风格 workflow-spec.md。"""

    content = "\n".join(
        [
            "# Workflow Specification",
            "",
            "## Workflow Identity",
            "",
            "- 工作流名称：Fixture Host Generated Workflow",
            f"- 触发命令：/{entry_skill}",
            "- 简要描述：由 fixture_host 生成的确定性规格草案。",
            "",
            "## User Intent",
            "",
            f"- 用户诉求：希望围绕 `{request.strip() or 'default request'}` 形成可复用 workflow。",
            "- 最终目的：让目标项目获得可持续运行和验证的 Claude Code workflow 资产。",
            "- 成功标准：用户需求、交付物和验证门槛都已明确，并可进入 YAML 设计阶段。",
            "",
            "## Clarification Summary",
            "",
            "- 澄清轮次：2",
            "- 已确认事项：目标项目；触发方式；核心输入输出；质量门禁；非目标边界。",
            "- 已消解歧义：用户诉求；最终目的；成功标准；默认交付范围已明确。",
            "",
            "## Requirement Logic Interview",
            "",
            "- 复杂度：M",
            "- Purpose Lens：目标是为用户请求生成可持续运行、可验证、可审计的目标 workflow。",
            "- Object Lens：输入对象为用户请求和目标项目资产；中间对象为需求索引、设计源和 managed plan；输出对象为 `.claude/` 与 `.workflowprogram/` workflow 资产。",
            "- Process Lens：clarify requirement -> collect context -> design workflow graph -> generate managed assets -> validate runtime evidence。",
            "- Decision Lens：当存在资产冲突、审批未决、环境能力缺失或验证失败时，workflow 必须停止或回到对应阶段。",
            "- Evidence Lens：必须保留 clarification package、logic map、managed result、state.json、events.jsonl 和 S5 summary。",
            "- Acceptance Lens：给定明确用户请求时应生成目标 workflow 资产并通过 S5；给定冲突或验证失败时应留下失败证据。",
            "- Boundary Lens：不得静默覆盖非托管资产；不得跳过审批和 S5；不得自动修改应用代码。",
            "- 关键追问：哪些目标输出必须进入 registry 或 test_contract 以便 S5 验证；哪些失败证据足以阻止 clean PASS。",
            "- 候选节点：entry；generate-assets；validate-assets。",
            "- 负向/停止场景：审批未完成时停止；目标资产冲突时停止；必需环境能力缺失时失败并给出 remediation。",
            "",
            "## Open Questions",
            "",
            "- 阻塞未决问题：无",
            "- 可延后问题：可在 S3 继续细化的命名与文档措辞",
            "- 问题处理策略：阻塞问题必须在 S1 清零；可延后问题进入假设日志并在设计阶段追踪。",
            "",
            "## Assumptions and Boundaries",
            "",
            "- 当前假设：目标项目路径可访问；用户接受托管 workflow 资产；已有约束文件可读取。",
            "- 外部依赖：当前仓库中的 workflow 设计文档；constraints；目标项目现有 `.claude` 资产（如存在）。",
            "- 关键边界场景：审批未完成时不得进入 S4；目标资产冲突时不得静默覆盖；环境依赖缺失时必须显式失败或给出 remediation。",
            "- 明确不做：不直接修改应用代码；不跳过 S5 验证；不绕过 managed apply 边界。",
            "",
            "## Target Workflow Graph Readback",
            "",
            "- WorkflowProgram 自身是否仍按 `S0..S6` 开发主链执行：是，WorkflowProgram 自身仍按 S1-S6 控制面执行。",
            "- 目标工作流是否需要非 `S1..S6` 的业务节点：需要，目标工作流使用业务化节点而不是照搬 S1-S6。",
            "- 目标 workflow_graph 节点：entry -> generate-assets -> validate-assets",
            "- 目标 workflow_graph 入口与转移：entry 从注册命令进入；entry -> generate-assets；generate-assets -> validate-assets。",
            "- 每个 graph 节点的输入、输出、gate、owner：entry 输入用户请求并输出 intake summary；generate-assets 输出候选资产；validate-assets 输出验证报告。",
            "- 每个 graph 节点的执行模型（skill / agent / script / team / loop）：entry 使用 skill；generate-assets 使用 script；validate-assets 使用 script 与 judge。",
            "- 哪些 node 需要独立 agent，原因是什么：无，fixture_host 使用确定性 provider 生成证据。",
            "- 哪些 node 不需要独立 agent，原因是什么：entry、generate-assets、validate-assets 均可由确定性 provider 模拟。",
            "- 复杂 node-design 输出路径：无。",
            "- 需要 `loop_policy` 的 graph 节点：无。",
            "- 每个 loop 节点的 `max_iterations`、反馈命令、停止条件、证据输出：无。",
            "- 目标输出是否已映射到 `registry` 或 `test_contract.artifacts`：是，`.claude/` 与 `.workflowprogram/` 交付物均由 registry 或 deliverables 声明。",
            "",
            "## File Plan",
            "",
            "- 需要创建的文件：`.claude/settings.json`；`.claude/commands/example.md`；`.workflowprogram/design/workflow-spec.yaml`；`.workflowprogram/runtime/workflow-entry.py`。",
            "- 需要修改的文件：`.claude/rules/constraints.md`。",
            "",
            "## Readback Confirmation",
            "",
            "- 回读摘要：本工作流将围绕请求形成可验证的 Claude Code workflow 资产，明确交付物、质量门禁和非目标边界。",
            "- 用户确认状态：confirmed",
            "- 最近修正：无",
            "",
            "## Trigger Model",
            "",
            "- 调用方式：手动命令",
            f"- 触发细节：使用 `/{entry_skill}` 处理 `{request.strip() or 'default request'}`。",
            "",
            "## Inputs",
            "",
            "- 必需输入：用户请求文本",
            "- 可选输入：当前项目中的 workflow 资产",
            "- 所需外部上下文：仓库中的设计文档与 constraints",
            "",
            "## Outputs",
            "",
            "- 主交付物：托管的 `.claude/` workflow 资产",
            "- 次级产物：运行时验证报告和 lessons 增量",
            "- 输出格式：Markdown、JSON、YAML",
            "",
            "## Quality Gates",
            "",
            "- 阻塞条件：审批未决、冲突、边界违规",
            "- 必需验证：managed apply、spec schema、runtime judge",
            "- 完成定义：目标资产与运行时验证结论一致",
            "",
        ]
    )
    _write_text(run_root / "workflow-spec.md", content + "\n")


def _write_design_source_artifacts(run_root: Path, request: str) -> None:
    """写出最小但可追踪的 S1-S3 设计源证据。"""

    request_text = request.strip() or "default request"
    stages_root = run_root / "outputs" / "stages"
    _write_text(
        stages_root / "s1-requirements.yaml",
        yaml.safe_dump(
            {
                "requirements": [
                    {
                        "id": "REQ-001",
                        "source_ref": "USER-REQUEST-001",
                        "priority": "must",
                        "statement": f"Create a managed workflow for: {request_text}",
                        "acceptance_hint": "Generated assets, runtime evidence, and validation summary exist.",
                        "boundaries": [
                            "Do not overwrite unmanaged target assets silently.",
                            "Do not skip S5 validation.",
                        ],
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
    )
    write_json(
        stages_root / "question-backlog.json",
        {
            "schema_version": 1,
            "complexity": "M",
            "lead_role": "requirement-clarification-lead",
            "questions": [
                {
                    "id": "Q-001",
                    "lens": "evidence_model",
                    "question": "哪些目标输出必须进入 registry 或 test_contract 以便 S5 验证？",
                    "why_it_matters": "Different answers can alter workflow nodes, decisions, evidence, acceptance tests, or boundaries.",
                    "blocking": False,
                    "expected_answer_shape": "Concrete output-to-evidence mapping.",
                    "linked_requirement_ids": ["REQ-001"],
                    "design_consequence": True,
                    "status": "resolved",
                }
            ],
            "selected_next_question_id": None,
            "blocking_count": 0,
            "design_consequential_count": 1,
        },
    )
    write_json(
        stages_root / "requirement-logic-map.json",
        {
            "schema_version": 1,
            "complexity": "M",
            "status": "READY",
            "lenses": {
                "purpose": {"status": "complete", "required": True, "items": ["Generate a verifiable workflow asset set."]},
                "object_model": {"status": "complete", "required": True, "items": ["User request, target assets, managed plan, runtime evidence."]},
                "process_model": {"status": "complete", "required": True, "items": ["clarify -> context -> design -> generate -> validate"]},
                "decision_model": {"status": "complete", "required": True, "items": ["Stop on conflict, approval gap, environment gap, or validation failure."]},
                "evidence_model": {"status": "complete", "required": True, "items": ["state.json, events.jsonl, managed result, S5 summary."]},
                "acceptance_model": {"status": "complete", "required": True, "items": ["Workflow assets exist and S5 PASS/WARN is justified."]},
                "boundary_model": {"status": "complete", "required": True, "items": ["Do not overwrite unmanaged assets or skip validation."]},
            },
            "elements": {
                "process": [{"id": "PROC-001", "summary": "clarify -> context -> design -> generate -> validate"}],
                "decisions": [{"id": "DEC-001", "summary": "Stop on conflict or validation failure."}],
                "evidence": [{"id": "EVD-001", "summary": "state.json, events.jsonl, managed result, S5 summary."}],
                "acceptance": [{"id": "ACC-001", "summary": "Workflow assets exist and S5 PASS/WARN is justified."}],
                "boundaries": [{"id": "BND-001", "summary": "Do not overwrite unmanaged assets or skip validation."}],
            },
            "workflow_node_candidates": ["entry", "generate-assets", "validate-assets"],
            "negative_or_stop_scenarios": ["Conflict, missing approval, or validation failure stops clean PASS."],
            "requirement_links": [
                {
                    "requirement_id": "REQ-001",
                    "priority": "must",
                    "process_refs": ["PROC-001"],
                    "decision_refs": ["DEC-001"],
                    "evidence_refs": ["EVD-001"],
                    "acceptance_refs": ["ACC-001"],
                    "boundary_refs": ["BND-001"],
                }
            ],
            "open_logic_gaps": [],
            "coverage": {
                "all_required_lenses_present": True,
                "has_process_refs": True,
                "has_evidence_refs": True,
                "has_acceptance_refs": True,
                "has_design_consequential_questions": True,
            },
        },
    )
    _write_text(
        stages_root / "s2-context-findings.yaml",
        yaml.safe_dump(
            {
                "findings": [
                    {
                        "id": "CTX-001",
                        "requirement_refs": ["REQ-001"],
                        "kind": "workflow_asset_context",
                        "summary": "Target workflow assets and WorkflowProgram constraints are available to S3.",
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
    )
    _write_text(
        stages_root / "s3-design-highlevel.md",
        "\n".join(
            [
                "# S3 High-Level Design",
                "",
                "- Requirement refs: `REQ-001`",
                "- Target workflow purpose: generate managed Claude Code workflow assets with runtime evidence.",
                "- Target graph: `intake -> implement -> done`.",
                "- Boundary: design source stays outside `workflow-spec.yaml` prose.",
                "",
            ]
        ),
    )
    _write_text(
        stages_root / "s3-design-lowlevel.md",
        "\n".join(
            [
                "# S3 Low-Level Design",
                "",
                "- Requirement refs: `REQ-001`",
                "- `intake` captures request context and produces an intake summary.",
                "- `implement` generates `.claude` assets and `.workflowprogram` runtime/design assets.",
                "- S5 validates managed apply, state evidence, and design lineage.",
                "",
            ]
        ),
    )
    _write_text(
        stages_root / "s3-implementation-plan.md",
        "\n".join(
            [
                "# S3 Implementation Plan",
                "",
                "1. Generate candidate workflow assets from the accepted design.",
                "2. Apply managed assets through the managed-asset boundary.",
                "3. Run S5 validation and persist runtime evidence.",
                "",
            ]
        ),
    )
    _write_text(
        stages_root / "acceptance-tests.yaml",
        yaml.safe_dump(
            {
                "acceptance_tests": [
                    {
                        "id": "AT-001",
                        "covers": ["REQ-001"],
                        "verifier": "S5",
                        "expected_evidence": [
                            "state.json",
                            "events.jsonl",
                            "outputs/stages/s5-validation-summary.json",
                        ],
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
    )
    write_json(
        stages_root / "traceability-matrix.json",
        {
            "schema_version": 1,
            "links": [
                {
                    "requirement_id": "REQ-001",
                    "design_nodes": ["intake", "implement"],
                    "assets": [
                        ".workflowprogram/design/workflow-spec.yaml",
                        ".workflowprogram/runtime/workflow-entry.py",
                    ],
                    "acceptance_tests": ["AT-001"],
                    "evidence": [
                        "state.json",
                        "events.jsonl",
                        "outputs/stages/s5-validation-summary.json",
                    ],
                }
            ],
        },
    )
    canonical_pairs = {
        "s1-requirements.yaml": "target-requirements.yaml",
        "question-backlog.json": "target-question-backlog.json",
        "requirement-logic-map.json": "target-requirement-logic-map.json",
        "s2-context-findings.yaml": "target-context-findings.yaml",
        "s3-design-highlevel.md": "target-design-overview.md",
        "s3-design-lowlevel.md": "target-design-detail.md",
        "s3-implementation-plan.md": "target-implementation-plan.md",
        "acceptance-tests.yaml": "target-acceptance-tests.yaml",
        "traceability-matrix.json": "target-traceability-matrix.json",
    }
    for legacy_name, canonical_name in canonical_pairs.items():
        source = stages_root / legacy_name
        if source.exists():
            shutil.copy2(source, stages_root / canonical_name)


def _copy_runtime_spec(repo_root: Path, run_root: Path, entry_skill: str) -> Path:
    """为 fixture_host 准备可供 view/maintenance 生成器消费的 workflow-spec.yaml。"""

    spec_path = repo_root / "tests" / "spec-fixtures" / "valid-minimal.yaml"
    payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"fixture spec is invalid: {spec_path}")
    target = run_root / "workflow-spec.yaml"
    _write_text(target, yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))
    _write_design_review_evidence(repo_root, run_root, request="fixture_host request")
    return target


def _stage_design_source_archive(run_root: Path, spec_path: Path, candidate_root: Path) -> Dict[str, str]:
    """把 target design source 放入 managed candidate，模拟真实 workflow-entry 行为。"""

    try:
        spec_payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except Exception:
        spec_payload = {}
    if not isinstance(spec_payload, dict):
        spec_payload = {}
    resolved = resolve_target_design_refs(spec_payload)
    persistent_refs = dict(PERSISTENT_DEFAULTS)
    persistent_refs.update(resolved.persistent_refs)

    copied: Dict[str, str] = {}
    for key, rel_path in resolve_existing_run_refs(run_root, spec_payload).items():
        target_rel = persistent_refs.get(key)
        source = run_root / rel_path
        if not target_rel or not source.exists() or not source.is_file():
            continue
        target = candidate_root / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied[key] = target.relative_to(candidate_root).as_posix()

    for node_id, rel_path in iter_existing_node_design_refs(run_root, spec_payload).items():
        source = run_root / rel_path
        if not source.exists() or not source.is_file():
            continue
        target_rel = resolved.persistent_node_designs.get(
            node_id,
            f".workflowprogram/design/source/target-node-designs/{node_id}.md",
        )
        target = candidate_root / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied[f"node_design:{node_id}"] = target.relative_to(candidate_root).as_posix()
    return copied


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_design_review_evidence(repo_root: Path, run_root: Path, *, request: str) -> None:
    """为 fixture_host 写出最小闭合的 S3 design-review 证据。"""

    review_root = run_root / "outputs" / "stages" / "design-review"
    script_root = repo_root / ".claude" / "scripts"
    completed = subprocess.run(
        [
            sys.executable,
            str(script_root / "generate-design-review-packet.py"),
            "--run-root",
            str(run_root),
            "--request",
            request,
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode not in {0, 2}:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "generate-design-review-packet.py failed")
    packet_path = review_root / "design-review-packet.json"
    packet_payload = json.loads(packet_path.read_text(encoding="utf-8"))
    artifact_fingerprints = packet_payload.get("artifact_fingerprints", {}) if isinstance(packet_payload.get("artifact_fingerprints"), dict) else {}
    write_json(review_root / "round-1.json", {"schema_version": 1, "round": 1, "status": "PASS", "summary": "fixture_host design review", "issues": []})
    write_json(review_root / "issues.json", {"schema_version": 1, "generated_at": iso_now(), "issues": []})
    _write_text(review_root / "report.md", "# Design Review Report\n\n- status: `PASS`\n- provider: `fixture_host`\n")
    write_json(
        review_root / "closure.json",
        {
            "schema_version": 1,
            "schema_name": "design-review-closure",
            "generated_at": iso_now(),
            "status": "PASS",
            "packet_path": "outputs/stages/design-review/design-review-packet.json",
            "packet_sha256": _sha256_file(packet_path),
            "artifact_fingerprints": artifact_fingerprints,
            "issue_count": 0,
            "open_blocking_count": 0,
            "accepted_risk_count": 0,
        },
    )
    gate = subprocess.run(
        [
            sys.executable,
            str(script_root / "validate-design-review-gate.py"),
            "--run-root",
            str(run_root),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if gate.returncode != 0:
        raise RuntimeError(gate.stderr.strip() or gate.stdout.strip() or "validate-design-review-gate.py failed")


def _generate_design_docs(spec_path: Path, run_root: Path) -> Dict[str, Path]:
    """基于真实生成器产出 run_root 下的 view / maintenance。"""

    script_root = _repo_root() / ".claude" / "scripts"
    outputs = {
        "workflow_spec": spec_path,
        "workflow_view": run_root / "workflow-view.md",
        "workflow_maintenance": run_root / "workflow-maintenance.md",
    }
    for script_name, out_path in (
        ("generate-workflow-view.py", outputs["workflow_view"]),
        ("generate-workflow-maintenance.py", outputs["workflow_maintenance"]),
    ):
        completed = subprocess.run(
            [
                sys.executable,
                str(script_root / script_name),
                "--spec",
                str(spec_path),
                "--out",
                str(out_path),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"{script_name} failed")
    return outputs


def _generate_target_runtime_assets(spec_path: Path, out_root: Path) -> Dict[str, Path]:
    """基于真实生成器产出 target-side runtime 资产。"""

    script_root = _repo_root() / ".claude" / "scripts"
    completed = subprocess.run(
        [
            sys.executable,
            str(script_root / "generate-target-runtime.py"),
            "--spec",
            str(spec_path),
            "--out-root",
            str(out_root),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "generate-target-runtime.py failed")
    payload = json.loads(completed.stdout)
    files = payload.get("files", {})
    return {
        "entry_script": Path(str(files.get("entry_script", ""))).resolve(),
        "runner_script": Path(str(files.get("runner_script", ""))).resolve(),
        "state_validator_script": Path(str(files.get("state_validator_script", ""))).resolve(),
        "runtime_manifest": Path(str(files.get("runtime_manifest", ""))).resolve(),
    }


def _apply_target_claude_guard(spec_path: Path, target_root: Path, run_root: Path) -> Dict[str, Any]:
    """Apply the same target CLAUDE.md runtime guard used by the real develop entry."""

    script_root = _repo_root() / ".claude" / "scripts"
    completed = subprocess.run(
        [
            sys.executable,
            str(script_root / "apply-target-claude-guard.py"),
            "--spec",
            str(spec_path),
            "--target-root",
            str(target_root),
            "--run-root",
            str(run_root),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout.strip()) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    if completed.returncode not in {0}:
        message = completed.stderr.strip() or completed.stdout.strip() or "apply-target-claude-guard.py failed"
        if isinstance(payload, dict) and payload.get("reason"):
            message = str(payload.get("reason"))
        raise RuntimeError(message)
    return payload if isinstance(payload, dict) else {}


def _write_lessons_delta(run_root: Path, entry_skill: str, request: str, failure_kind: str) -> None:
    """为 fixture_host 运行生成确定性的 S6 lessons delta。"""

    content = "\n".join(
        [
            "# S6 Lessons Delta",
            "",
            f"- run_id: `{run_root.name}`",
            f"- failure_kind: `{failure_kind}`",
            f"- entry_skill: `{entry_skill}`",
            "",
            "## Observations",
            "",
            f"- Request: `{request.strip() or 'default request'}`",
            "- Runtime evidence and stage summaries were preserved under RUN_ROOT.",
            "",
            "## Constraint Candidates",
            "",
            "- Keep managed workflow assets confined to `.claude/**` and preserve runtime evidence under RUN_ROOT.",
            "",
        ]
    )
    _write_text(run_root / "outputs" / "stages" / "s6-lessons-delta.md", content + "\n")


def _write_progress_artifacts(
    run_root: Path,
    stage_history: List[str],
    result: str,
    next_action: str,
    *,
    current_stage: str,
    approval_status: str = "approved",
) -> None:
    """落地 S5/S6 检查所需的最小 progress 产物。"""

    progress_root = run_root / "outputs" / "progress"
    write_json(
        progress_root / "current-progress.json",
        {
            "run_id": run_root.name,
            "current_stage": current_stage,
            "current_node": current_stage,
            "percent": 100 if result == "PASS" else 80,
            "last_status": "ok" if result == "PASS" else "error",
            "last_verdict": result,
            "approval_status": approval_status,
            "next_action": next_action,
        },
    )
    _append_jsonl(
        progress_root / "milestones.jsonl",
        {
            "stage": current_stage,
            "node": current_stage,
            "event": "StageCompleted",
            "status": "ok" if result == "PASS" else "error",
            "result": result,
            "artifact_refs": [],
        },
    )
    _write_text(
        progress_root / "user-progress.md",
        "\n".join(
            [
                "# Workflow Progress",
                "",
                f"- run_id: `{run_root.name}`",
                f"- current_stage: `{current_stage}`",
                f"- current_node: `{current_stage}`",
                f"- percent: `{100 if result == 'PASS' else 80}`",
                f"- last_status: `{'ok' if result == 'PASS' else 'error'}`",
                f"- last_verdict: `{result}`",
                f"- approval_status: `{approval_status}`",
                "",
                "## 历史关键节点结果",
                "",
                f"- Stage history: `{', '.join(stage_history) or 'none'}`",
                f"- Result: `{result}`",
                "",
                "## Next Action",
                "",
                f"- {next_action}",
                "",
            ]
        ),
    )


def _write_runner_evidence(
    run_root: Path,
    target_root: Path,
    entry_skill: str,
    stage_history: List[str],
    result: str,
    failure_code: str,
) -> None:
    """补齐 develop fixture 路径所需的最小 runner 证据。"""

    outputs = run_root / "outputs"
    write_json(
        outputs / "stages" / "s0-route.json",
        {
            "intent": "develop",
            "entry_skill": entry_skill,
            "target_root": str(target_root),
            "routed_at": iso_now(),
        },
    )
    write_json(
        outputs / "stages" / "runner-summary.json",
        {
            "run_id": run_root.name,
            "status": result,
            "entry_skill": entry_skill,
            "transition_count": len(stage_history),
            "failure_code": failure_code or None,
        },
    )


def _write_publish_route_evidence(run_root: Path, target_root: Path, entry_skill: str, result: str, failure_code: str) -> None:
    """为 publish fixture 写出最小路由摘要。"""

    outputs = run_root / "outputs"
    write_json(
        outputs / "stages" / "s0-route.json",
        {
            "intent": "publish",
            "entry_skill": entry_skill,
            "target_root": str(target_root),
            "routed_at": iso_now(),
        },
    )
    write_json(
        outputs / "stages" / "runner-summary.json",
        {
            "run_id": run_root.name,
            "status": result,
            "entry_skill": entry_skill,
            "transition_count": 1,
            "failure_code": failure_code or None,
        },
    )


def _seed_publishable_target(plugin_root: Path, target_root: Path, request: str) -> Path:
    """在 fixture_host 内部构造一条已完成 develop 的目标 workflow。"""

    prior_run_root = target_root / ".workflowprogram" / "runs" / "prior-develop-for-publish"
    if prior_run_root.exists():
        shutil.rmtree(prior_run_root)
    prior = _invoke_fixture_host(
        RuntimeHostConfig(provider="fixture_host"),
        plugin_root,
        target_root,
        prior_run_root,
        "workflowprogram-develop",
        request or "seed publishable workflow",
        "empty-project",
    )
    if prior.result != "PASS":
        raise RuntimeError(prior.message)
    write_json(
        prior_run_root / "state.json",
        {
            "schema_version": 1,
            "schema_name": "fixture-host-prior-develop-state",
            "run_id": prior_run_root.name,
            "status": "completed",
            "stage": "finished",
            "result": "PASS",
            "category": None,
            "values": {"stage_history": prior.stage_history},
            "updated_at": iso_now(),
        },
    )
    write_json(
        prior_run_root / "outputs" / "stages" / "s5-validation-summary.json",
        {
            "verdict": "PASS",
            "failure_kind": "none",
            "failure_code": "",
            "summary": "fixture_host prior develop run passed and is publishable.",
            "checked_files": [
                "state.json",
                "events.jsonl",
                "outputs/managed-change-result.json",
                "outputs/stages/design-review/closure.json",
            ],
        },
    )
    return prior_run_root


def _seed_existing_marketplace_checkout(run_root: Path, scenario: str, plugin_id: str) -> Path:
    """构造 existing_marketplace publish fixture 所需的 marketplace checkout。"""

    repo_path = run_root / "outputs" / "existing-marketplace-checkout"
    if repo_path.exists():
        shutil.rmtree(repo_path)
    (repo_path / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    if scenario == "publish-existing-marketplace-invalid-manifest-fail":
        _write_text(repo_path / ".claude-plugin" / "marketplace.json", "{ invalid marketplace json\n")
        return repo_path

    plugin_entry = {
        "name": "other-plugin",
        "source": "./plugins/other-plugin",
        "description": "Existing unrelated plugin",
        "version": "0.1.0",
    }
    plugins: List[Dict[str, Any]] = [plugin_entry]
    if scenario in {
        "publish-existing-marketplace-update-pass",
        "publish-existing-marketplace-duplicate-plugin-blocked",
        "publish-existing-marketplace-source-mismatch-fail",
        "publish-existing-marketplace-version-not-bumped-fail",
    }:
        existing_source = "./legacy/publish-smoke" if scenario == "publish-existing-marketplace-source-mismatch-fail" else f"./plugins/{plugin_id}"
        existing_version = "0.1.0" if scenario == "publish-existing-marketplace-version-not-bumped-fail" else "0.0.9"
        plugins.append(
            {
                "name": plugin_id,
                "source": existing_source,
                "description": "Existing target workflow plugin",
                "version": existing_version,
            }
        )
    write_json(
        repo_path / ".claude-plugin" / "marketplace.json",
        {
            "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
            "name": "fixture-marketplace",
            "description": "Existing marketplace fixture",
            "owner": {"name": "fixture-host"},
            "plugins": plugins,
        },
    )

    if scenario == "publish-existing-marketplace-dirty-checkout-blocked":
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, text=True, check=False)
        subprocess.run(["git", "config", "user.name", "Fixture Host"], cwd=repo_path, capture_output=True, text=True, check=False)
        subprocess.run(["git", "config", "user.email", "fixture@example.invalid"], cwd=repo_path, capture_output=True, text=True, check=False)
        subprocess.run(["git", "add", ".claude-plugin/marketplace.json"], cwd=repo_path, capture_output=True, text=True, check=False)
        subprocess.run(["git", "commit", "-m", "Seed marketplace"], cwd=repo_path, capture_output=True, text=True, check=False)
        _write_text(repo_path / "dirty-note.md", "uncommitted fixture change\n")
    return repo_path


def _invoke_fixture_host(
    config: RuntimeHostConfig,
    plugin_root: Path,
    target_root: Path,
    run_root: Path,
    entry_skill: str,
    request: str,
    fixture: str,
) -> RuntimeHostInvocation:
    """执行测试用的内置确定性 provider。

    fixture_host 不试图模拟 Claude 的内部推理，
    它只负责以可重复的方式产出控制面与验证链所需的最小产物。
    """

    if not _entry_exists(plugin_root, entry_skill):
        return RuntimeHostInvocation(
            provider=config.provider,
            result="FAIL",
            failure_code="STRUCTURE_FAILURE",
            message=f"Plugin entry '{entry_skill}' was not found in plugin root.",
            is_error=True,
        )

    # 缺少请求文本用于模拟 S1/input 失败，而且应发生在任何资产生成之前。
    if not request.strip():
        _write_progress_artifacts(
            run_root,
            ["requirement"],
            "FAIL",
            "provide required request arguments and rerun",
            current_stage="requirement",
            approval_status="pending",
        )
        return RuntimeHostInvocation(
            provider=config.provider,
            result="FAIL",
            failure_code="INPUT_FAILURE",
            message="Required request arguments were not provided.",
            is_error=True,
            stage_history=["requirement"],
            current_stage="requirement",
            stage_status="failed",
            next_action="provide required request arguments and rerun",
            next_stage_on_failure="requirement",
        )

    if entry_skill == "workflowprogram-develop":
        # develop fixture 路径会写出与真实运行同类的产物：
        # spec draft、candidate assets、managed apply 输出和 S6 产物。
        _write_workflow_spec_draft(run_root, entry_skill, request)
        _write_design_source_artifacts(run_root, request)
        spec_path = _copy_runtime_spec(_repo_root(), run_root, entry_skill)
        design_docs = _generate_design_docs(spec_path, run_root)
        candidate_root = run_root / "outputs" / "candidate"
        candidate_claude_root = candidate_root / ".claude"
        write_json(
            candidate_claude_root / "settings.json",
            {
                "skills": {
                    "generated-smoke": {
                        "description": "Generated by fixture_host for runtime smoke validation",
                        "file": ".claude/skills/generated-smoke/SKILL.md",
                    }
                }
            },
        )
        _write_text(
            candidate_claude_root / "rules" / "constraints.md",
            "\n".join(
                [
                    "# Runtime Smoke Constraints",
                    "",
                    f"- Source fixture: `{fixture}`",
                    f"- Source request: `{request.strip()}`",
                    "- Generated by fixture_host.",
                    "",
                ]
            ),
        )
        _write_text(
            candidate_claude_root / "skills" / "generated-smoke" / "SKILL.md",
            "\n".join(
                [
                    "---",
                    "name: generated-smoke",
                    "description: Generated by fixture_host for runtime smoke validation",
                    "version: 1.0.0",
                    "---",
                    "",
                    "This skill was generated by fixture_host.",
                    "",
                ]
            ),
        )
        _write_text(
            candidate_claude_root / "skills" / "example" / "SKILL.md",
            "\n".join(
                [
                    "---",
                    "name: example-skill",
                    "description: Example skill declared by fixture workflow-spec",
                    "version: 1.0.0",
                    "---",
                    "",
                    "This skill satisfies the fixture workflow-spec registry.",
                    "",
                ]
            ),
        )
        _write_text(
            candidate_claude_root / "commands" / "generated-smoke.md",
            "\n".join(
                [
                    "## Usage",
                    "",
                    "```text",
                    "/generated-smoke <request>",
                    "```",
                    "",
                    "Generated by fixture_host.",
                    "",
                ]
            ),
        )
        _write_text(
            candidate_claude_root / "commands" / "example.md",
            "\n".join(
                [
                    "---",
                    "description: Example managed-runtime command declared by fixture workflow-spec",
                    "---",
                    "",
                    "## Usage",
                    "",
                    "```text",
                    "/example <request>",
                    "```",
                    "",
                    "This command is a thin wrapper for the generated WorkflowProgram target runtime.",
                    "",
                    "Run:",
                    "",
                    "```bash",
                    "python3 .workflowprogram/runtime/workflow-entry.py run --request \"$ARGUMENTS\"",
                    "```",
                    "",
                ]
            ),
        )
        _write_text(
            candidate_claude_root / "agents" / "example-agent.md",
            "# Example Agent\n\nGenerated by fixture_host to satisfy registry references.\n",
        )
        _write_text(
            candidate_claude_root / "hooks" / "example-hook.json",
            '{\n  "name": "example-hook",\n  "enabled": false\n}\n',
        )
        candidate_design_root = candidate_root / ".workflowprogram" / "design"
        candidate_design_root.mkdir(parents=True, exist_ok=True)
        for source_name, target_name in (
            ("workflow_spec", "workflow-spec.yaml"),
            ("workflow_view", "workflow-view.md"),
            ("workflow_maintenance", "workflow-maintenance.md"),
        ):
            shutil.copy2(design_docs[source_name], candidate_design_root / target_name)
        _stage_design_source_archive(run_root, spec_path, candidate_root)
        _generate_target_runtime_assets(spec_path, candidate_root / ".workflowprogram" / "runtime")

        cmd = [
            sys.executable,
            str(_repo_root() / ".claude" / "scripts" / "managed-assets.py"),
            "apply-staged",
            "--target-root",
            str(target_root),
            "--source-root",
            str(candidate_root),
            "--run-root",
            str(run_root),
            "--json",
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
        payload = read_json_from_output(completed.stdout, completed.stderr)
        if payload is None:
            result_path = run_root / "outputs" / "managed-change-result.json"
            if result_path.exists():
                try:
                    payload = json.loads(result_path.read_text(encoding="utf-8"))
                except Exception:
                    payload = None

        conflicts = payload.get("conflicts", []) if isinstance(payload, dict) else []
        applied = payload.get("applied", []) if isinstance(payload, dict) else []
        # apply-staged 在“保留冲突而非写入”时会返回 2。
        if completed.returncode == 2:
            if fixture == "external-write":
                external_path = target_root / "external-write.txt"
                _write_text(external_path, "external write\n")
            _write_runner_evidence(
                run_root,
                target_root,
                entry_skill,
                ["requirement", "context", "design", "generate"],
                "FAIL",
                "CONFLICT_FAILURE",
            )
            _write_progress_artifacts(
                run_root,
                ["requirement", "context", "design", "generate"],
                "FAIL",
                "resolve managed asset conflicts and rerun",
                current_stage="generate",
            )
            return RuntimeHostInvocation(
                provider=config.provider,
                result="FAIL",
                failure_code="CONFLICT_FAILURE",
                message=f"Managed asset conflicts detected: {len(conflicts)}",
                is_error=True,
                command=cmd,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                parsed=payload,
                stage_history=["requirement", "context", "design", "generate"],
                current_stage="generate",
                stage_status="failed",
                next_action="resolve managed asset conflicts and rerun",
                next_stage_on_failure="generate",
                metadata={"applied": applied, "conflicts": conflicts},
            )
        if completed.returncode != 0:
            _write_runner_evidence(
                run_root,
                target_root,
                entry_skill,
                ["requirement", "context", "design", "generate"],
                "FAIL",
                "RUNTIME_FAILURE",
            )
            _write_progress_artifacts(
                run_root,
                ["requirement", "context", "design", "generate"],
                "FAIL",
                "inspect fixture_host apply failure",
                current_stage="generate",
            )
            return RuntimeHostInvocation(
                provider=config.provider,
                result="FAIL",
                failure_code="RUNTIME_FAILURE",
                message=completed.stderr.strip() or completed.stdout.strip() or "fixture_host apply failed",
                is_error=True,
                command=cmd,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                parsed=payload,
            )
        if fixture == "external-write":
            external_path = target_root / "external-write.txt"
            _write_text(external_path, "external write\n")
        try:
            guard_payload = _apply_target_claude_guard(spec_path, target_root, run_root)
        except RuntimeError as exc:
            _write_runner_evidence(
                run_root,
                target_root,
                entry_skill,
                ["requirement", "context", "design", "generate"],
                "FAIL",
                "CONFLICT_FAILURE",
            )
            _write_progress_artifacts(
                run_root,
                ["requirement", "context", "design", "generate"],
                "FAIL",
                "resolve target CLAUDE.md runtime guard conflict and rerun",
                current_stage="generate",
            )
            return RuntimeHostInvocation(
                provider=config.provider,
                result="FAIL",
                failure_code="CONFLICT_FAILURE",
                message=str(exc),
                is_error=True,
                command=cmd,
                returncode=2,
                stdout=completed.stdout,
                stderr=completed.stderr,
                parsed=payload,
                stage_history=["requirement", "context", "design", "generate"],
                current_stage="generate",
                stage_status="failed",
                next_action="resolve target CLAUDE.md runtime guard conflict and rerun",
                next_stage_on_failure="generate",
                metadata={"applied": applied, "conflicts": conflicts},
            )
        _write_runner_evidence(
            run_root,
            target_root,
            entry_skill,
            ["requirement", "context", "design", "generate", "validate", "lessons"],
            "PASS",
            "",
        )
        _write_lessons_delta(run_root, entry_skill, request, failure_kind_from_code(""))
        _write_progress_artifacts(
            run_root,
            ["requirement", "context", "design", "generate", "validate", "lessons"],
            "PASS",
            "complete",
            current_stage="lessons",
        )
        return RuntimeHostInvocation(
            provider=config.provider,
            result="PASS",
            failure_code="",
            message=f"fixture_host applied {len(applied)} managed workflow assets.",
            is_error=False,
            command=cmd,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            parsed=payload,
            stage_history=["requirement", "context", "design", "generate", "validate", "lessons"],
            current_stage="lessons",
            stage_status="done",
            next_action="complete",
            next_stage_on_failure="",
            metadata={"applied": applied, "conflicts": conflicts, "target_claude_guard": guard_payload},
        )

    if entry_skill == "workflowprogram-publish":
        stage_history = ["publish"]
        develop_run_root: Path | None = None
        if fixture != "publish-missing-develop-evidence-fail":
            develop_run_root = _seed_publishable_target(plugin_root, target_root, request)
        if fixture == "publish-stale-managed-state-fail":
            stale_path = target_root / ".claude" / "commands" / "generated-smoke.md"
            if stale_path.exists():
                stale_path.unlink()
        plugin_id = "invalid_plugin_id" if fixture == "publish-package-validation-fail" else "publish-smoke"
        existing_marketplace_fixture = fixture.startswith("publish-existing-marketplace-")
        existing_repo_path = _seed_existing_marketplace_checkout(run_root, fixture, plugin_id) if existing_marketplace_fixture else None
        cmd = [
            sys.executable,
            str(_repo_root() / ".claude" / "scripts" / "workflow-publish-entry.py"),
            "run",
            "--target-root",
            str(target_root),
            "--run-root",
            str(run_root),
            "--plugin-id",
            plugin_id,
            "--plugin-name",
            "Publish Smoke Workflow",
            "--version",
            "0.1.0",
            "--repository",
            "https://github.com/example/publish-smoke",
            "--repo-mode",
            "existing_marketplace" if existing_marketplace_fixture else "export_repo",
            "--runtime-mode",
            "workflowprogram_dependency",
            "--skip-claude-validate",
        ]
        if existing_repo_path is not None:
            cmd.extend(
                [
                    "--repo-path",
                    str(existing_repo_path),
                    "--marketplace-name",
                    "fixture-marketplace",
                ]
            )
        if fixture in {
            "publish-existing-marketplace-update-pass",
            "publish-existing-marketplace-source-mismatch-fail",
            "publish-existing-marketplace-version-not-bumped-fail",
        }:
            cmd.append("--update-existing-entry")
        if develop_run_root is not None:
            cmd.extend(["--develop-run-root", str(develop_run_root)])
        if fixture == "publish-github-auth-missing-blocked":
            cmd.append("--simulate-github-auth-missing")
        elif fixture == "publish-existing-marketplace-dirty-checkout-blocked":
            cmd.extend(["--execute-github", "--approve-github", "--simulate-github-auth-ready"])
        else:
            cmd.append("--dry-run")
        cmd.append("--json")
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
        try:
            parsed_payload = json.loads(completed.stdout.strip()) if completed.stdout.strip() else {}
        except json.JSONDecodeError:
            parsed_payload = {}
        payload = parsed_payload if isinstance(parsed_payload, dict) and parsed_payload else read_json_from_output(completed.stdout, completed.stderr)
        publish_status = str((payload or {}).get("status", "")).strip()
        if not publish_status:
            publish_status = "FAIL"
        result = "PASS" if publish_status == "PASS" else "FAIL"
        if publish_status == "BLOCKED":
            failure_code = "PUBLISH_GITHUB_AUTH_MISSING" if fixture == "publish-github-auth-missing-blocked" else "PUBLISH_BLOCKED"
        elif publish_status == "FAIL":
            failure_code = "PUBLISH_FAILURE"
        else:
            failure_code = ""
        _write_publish_route_evidence(run_root, target_root, entry_skill, result, failure_code)
        _write_progress_artifacts(
            run_root,
            stage_history,
            result,
            "complete" if result == "PASS" else "inspect publish-summary.json",
            current_stage="publish",
        )
        return RuntimeHostInvocation(
            provider=config.provider,
            result=result,
            failure_code=failure_code,
            message=str((payload or {}).get("message", "fixture_host completed publish flow.")),
            is_error=result != "PASS",
            command=cmd,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            parsed=payload,
            stage_history=stage_history,
            current_stage="publish",
            stage_status="done" if result == "PASS" else "failed",
            next_action="complete" if result == "PASS" else "inspect publish-summary.json",
            next_stage_on_failure="publish" if result != "PASS" else "",
        )

    # 非 develop 流程会刻意保持更轻，只合成足以让阶段契约可观测的产物。
    if entry_skill == "workflowprogram-validate":
        has_settings = (target_root / ".claude" / "settings.json").exists()
        has_constraints = (target_root / ".claude" / "rules" / "constraints.md").exists()
        _write_progress_artifacts(
            run_root,
            ["validate"],
            "PASS" if has_settings and has_constraints else "FAIL",
            "complete" if has_settings and has_constraints else "restore missing workflow assets",
            current_stage="validate",
        )
        if has_settings and has_constraints:
            return RuntimeHostInvocation(
                provider=config.provider,
                result="PASS",
                failure_code="",
                message="fixture_host validated target workflow assets successfully.",
                is_error=False,
                stage_history=["validate"],
                current_stage="validate",
                stage_status="done",
                next_action="complete",
            )
        return RuntimeHostInvocation(
            provider=config.provider,
            result="FAIL",
            failure_code="RUNTIME_FAILURE",
            message="fixture_host validation failed because required workflow assets are missing.",
            is_error=True,
            stage_history=["validate"],
            current_stage="validate",
            stage_status="failed",
            next_action="restore missing workflow assets",
            next_stage_on_failure="generate",
        )

    if entry_skill == "workflowprogram-audit":
        has_claude_root = (target_root / ".claude").exists()
        stage_history = _stage_history_for_entry(entry_skill)
        if has_claude_root:
            _write_lessons_delta(run_root, entry_skill, request, failure_kind_from_code(""))
        _write_progress_artifacts(
            run_root,
            stage_history,
            "PASS" if has_claude_root else "FAIL",
            "complete" if has_claude_root else "create workflow assets first",
            current_stage=stage_history[-1],
        )
        return RuntimeHostInvocation(
            provider=config.provider,
            result="PASS" if has_claude_root else "FAIL",
            failure_code="" if has_claude_root else "RUNTIME_FAILURE",
            message="fixture_host completed audit." if has_claude_root else "fixture_host found no workflow assets to audit.",
            is_error=not has_claude_root,
            stage_history=stage_history,
            current_stage=stage_history[-1],
            stage_status="done" if has_claude_root else "failed",
            next_action="complete" if has_claude_root else "create workflow assets first",
            next_stage_on_failure="" if has_claude_root else "requirement",
        )

    if entry_skill == "workflowprogram-iterate":
        _write_lessons_delta(run_root, entry_skill, request, failure_kind_from_code(""))
        _write_progress_artifacts(
            run_root,
            ["lessons"],
            "PASS",
            "complete",
            current_stage="lessons",
        )
        return RuntimeHostInvocation(
            provider=config.provider,
            result="PASS",
            failure_code="",
            message="fixture_host completed iterate flow.",
            is_error=False,
            stage_history=["lessons"],
            current_stage="lessons",
            stage_status="done",
            next_action="complete",
        )

    _write_progress_artifacts(
        run_root,
        _stage_history_for_entry(entry_skill),
        "PASS",
        "complete",
        current_stage=_stage_history_for_entry(entry_skill)[-1],
    )
    return RuntimeHostInvocation(
        provider=config.provider,
        result="PASS",
        failure_code="",
        message=f"fixture_host completed generic invocation for '{entry_skill}'.",
        is_error=False,
        stage_history=_stage_history_for_entry(entry_skill),
        current_stage=_stage_history_for_entry(entry_skill)[-1],
        stage_status="done",
        next_action="complete",
    )


def _invoke_command_adapter(
    config: RuntimeHostConfig,
    plugin_root: Path,
    target_root: Path,
    run_root: Path,
    entry_skill: str,
    request: str,
    timeout: int,
    fixture: str,
) -> RuntimeHostInvocation:
    """调用一个遵循 command-adapter 协议的外部 provider。"""

    base = _command_adapter_base(config)
    cmd = [
        *base,
        "invoke",
        "--plugin-root",
        str(plugin_root),
        "--target-root",
        str(target_root),
        "--run-root",
        str(run_root),
        "--entry-skill",
        entry_skill,
        "--request",
        request,
        "--fixture",
        fixture,
        "--timeout",
        str(timeout),
        "--json",
    ]
    completed = subprocess.run(cmd, cwd=target_root, capture_output=True, text=True, check=False)
    output = completed.stdout.strip() or completed.stderr.strip()
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        if completed.returncode != 0:
            return RuntimeHostInvocation(
                provider=config.provider,
                result="FAIL",
                failure_code="RUNTIME_FAILURE",
                message=output or f"provider invoke exited with code {completed.returncode}",
                is_error=True,
                command=cmd,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        return RuntimeHostInvocation(
            provider=config.provider,
            result="FAIL",
            failure_code="EVIDENCE_FAILURE",
            message=f"provider invoke returned non-JSON output: {output or '<empty>'}",
            is_error=True,
            command=cmd,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    if not isinstance(payload, dict):
        return RuntimeHostInvocation(
            provider=config.provider,
            result="FAIL",
            failure_code="EVIDENCE_FAILURE",
            message="provider invoke must return a JSON object",
            is_error=True,
            command=cmd,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    result = str(payload.get("result", "")).strip()
    # adapter 契约尽量贴近共享调用结构，
    # 这样上层栈就不需要为每个 provider 写分支。
    if result not in {"PASS", "WARN", "FAIL", "ENVIRONMENT-SKIP"}:
        return RuntimeHostInvocation(
            provider=config.provider,
            result="FAIL",
            failure_code="EVIDENCE_FAILURE",
            message=f"provider invoke returned invalid result='{result}'",
            is_error=True,
            command=cmd,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            parsed=payload,
        )
    return RuntimeHostInvocation(
        provider=config.provider,
        result=result,
        failure_code=str(payload.get("failure_code", "")).strip(),
        message=str(payload.get("message", "")).strip() or "provider invoke completed",
        is_error=bool(payload.get("is_error", result in {"FAIL", "WARN"} and str(payload.get("failure_code", "")).strip())),
        command=cmd,
        returncode=completed.returncode,
        stdout=str(payload.get("stdout", completed.stdout)),
        stderr=str(payload.get("stderr", completed.stderr)),
        parsed=payload,
        subagent_evidence=bool(payload.get("subagent_evidence", False)),
        stage_history=[str(item) for item in payload.get("stage_history", []) if str(item).strip()],
        current_stage=str(payload.get("current_stage", "")).strip(),
        next_action=str(payload.get("next_action", "")).strip(),
        metadata=payload.get("metadata", {}) if isinstance(payload.get("metadata", {}), dict) else {},
    )


def invoke_runtime_host(
    config: RuntimeHostConfig,
    plugin_root: Path,
    target_root: Path,
    run_root: Path,
    entry_skill: str,
    request: str,
    timeout: int,
    fixture: str = "",
) -> RuntimeHostInvocation:
    """把运行请求分发到选定的 provider 实现。"""

    if config.provider == "claude_cli":
        cmd = _claude_command(config.claude_bin, plugin_root, entry_skill, request)
        try:
            completed = subprocess.run(
                cmd,
                cwd=target_root,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return RuntimeHostInvocation(
                provider=config.provider,
                result="FAIL",
                failure_code="RUNTIME_FAILURE",
                message=f"Claude CLI timed out after {timeout}s.",
                is_error=True,
                command=cmd,
                returncode=1,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
            )
        parsed = read_json_from_output(completed.stdout, completed.stderr)
        invocation = _classify_claude_result(completed.stdout, completed.stderr, parsed, completed.returncode)
        invocation.command = cmd
        invocation.returncode = completed.returncode
        return invocation
    if config.provider == "fixture_host":
        return _invoke_fixture_host(config, plugin_root, target_root, run_root, entry_skill, request, fixture)
    if config.provider == "command_adapter":
        return _invoke_command_adapter(config, plugin_root, target_root, run_root, entry_skill, request, timeout, fixture)
    raise RuntimeError(f"unsupported runtime provider '{config.provider}'")
