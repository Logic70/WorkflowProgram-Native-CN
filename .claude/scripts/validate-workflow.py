#!/usr/bin/env python3
"""
跨平台的 WorkflowProgram 仓库校验脚本。

它负责校验 WorkflowProgram 仓库结构与一致性，
并替代 validate-workflow.ps1，提供 Mac/Linux/Windows 共用实现。

用法：
    python validate-workflow.py [ROOT_PATH]

退出码：
    0 - 校验通过
    1 - 校验失败
"""

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


REQUIRED_PRIMARY_SKILLS = [
    'workflowprogram-orchestrate',
    'workflowprogram-develop',
    'workflowprogram-native-develop',
    'workflowprogram-audit',
    'workflowprogram-iterate',
    'workflowprogram-validate',
    'workflowprogram-publish',
]

FORBIDDEN_LEGACY_PATHS = [
    'commands',
    'skills',
    'agents',
    'rules',
    'scripts',
    'tools/sync_plugin_assets.py',
    'tools/install_dev.sh',
    'tools/quick_install.sh',
]

PLUGIN_EXECUTABLE_PATHS = [
    ".claude-plugin/root/bin/workflowprogram-python",
    ".claude-plugin/root/bin/workflowprogram-doctor",
    ".claude-plugin/root/bin/workflowprogram-clean",
    ".claude-plugin/root/bin/workflowprogram-artifact-writer",
    "dist/plugin/bin/workflowprogram-python",
    "dist/plugin/bin/workflowprogram-doctor",
    "dist/plugin/bin/workflowprogram-clean",
    "dist/plugin/bin/workflowprogram-artifact-writer",
]

ACTIVE_DESIGN_DOCS = {
    "docs/workflowprogram-stage-highlevel-design.md": [
        "runtime_contract",
        "test_contract",
        "generated_runtime_contract",
        "workflow_graph",
        "shared-control-plane-wrapper",
        "logic70-plugins",
        "workflowprogram-python",
        "site-packages",
        "capability_discovery",
        "host-capability-candidates.json",
        "host-bootstrap-instructions.md",
        "clarification-record.json",
        "open-questions.json",
        "assumption-log.md",
        "design-readiness-report.json",
        "clarification-challenge-report.json",
        "clarification-handoff.json",
        "clarification-evidence.json",
        "requirement-clarification-lead",
        "workflow-design-reviewer",
        "design-review-packet.json",
        "validate-design-review-gate.py",
        "gate-validation.json",
        "host_capabilities",
        "agent_team_contract",
        "managed-rollback-manifest.json",
        "managed-recover-instructions.md",
        "workflow-entry.py",
        "workflowprogram-validate",
        "runtime_smoke.py",
        "quality-gate.py",
        "validation-runtime-report.md",
        "s5-validation-summary.json",
    ],
    "docs/workflowprogram-stage-lowlevel-design.md": [
        "runtime_contract",
        "test_contract",
        "generated_runtime_contract",
        "workflow_graph",
        "runtime_capabilities",
        "workflowprogram-python",
        "SessionStart",
        "site-packages",
        "capability_discovery",
        "host_capabilities",
        "agent_team_contract",
        "managed-rollback-manifest.json",
        "managed-recover-instructions.md",
        "discover-host-capabilities.py",
        "probe-host-capabilities.py",
        "apply-host-bootstrap.py",
        "generate-environment-remediation.py",
        "generate-clarification-package.py",
        "generate-clarification-review.py",
        "requirement-clarification-lead",
        "workflow-design-reviewer",
        "generate-design-review-packet.py",
        "validate-design-review-gate.py",
        "validate_design_review_gate",
        "gate-validation.json",
        "control-plane helper",
        "clarification-challenge-report.json",
        "clarification-handoff.json",
        "clarification-evidence.json",
        "workflow-entry.py",
        "runtime_contract.<field>",
        "implemented_now",
        "runner 只负责控制面",
        "workflowprogram-validate",
        "runtime_smoke.py",
        "quality-gate.py",
        "validation-runtime-report.md",
        "s5-validation-summary.json",
    ],
    "docs/workflowprogram-stage-consistency-check.md": [
        "runtime_contract",
        "test_contract",
        "当前无显式冲突",
    ],
}

ACTIVE_ENTRY_DOCS = {
    ".claude/commands/develop.md": [
        "runtime_contract",
        "test_contract",
        "generated_runtime_contract",
        ".workflowprogram/runtime/",
        "workflow_graph",
        "generate-target-runtime.py",
        "discover-host-capabilities.py",
        "probe-host-capabilities.py",
        "apply-host-bootstrap.py",
        "generate-environment-remediation.py",
        "generate-clarification-package.py",
        "generate-clarification-review.py",
        "requirement-clarification-lead",
        "workflow-design-reviewer",
        "generate-design-review-packet.py",
        "validate-design-review-gate.py",
        "design-review",
        "control-plane helper",
        "clarification-challenge-report.json",
        "clarification-handoff.json",
        "clarification-evidence.json",
        "workflow-entry.py",
        "runtime_contract.<field>",
        "workflowprogram-validate",
        "runtime_smoke.py",
        "s5-validation-summary.json",
    ],
    ".claude/skills/workflowprogram-develop/SKILL.md": [
        "runtime_contract",
        "test_contract",
        "generated_runtime_contract",
        ".workflowprogram/runtime/",
        "workflow_graph",
        "generate-target-runtime.py",
        "discover-host-capabilities.py",
        "probe-host-capabilities.py",
        "apply-host-bootstrap.py",
        "workflow-entry.py",
        "validate-design-review-gate.py",
        "implemented_now",
        "generate-clarification-review.py",
        "clarification-handoff.json",
        "clarification-evidence.json",
        "requirement-clarification-lead",
        "workflowprogram-validate",
        "runtime_smoke.py",
        "s5-validation-summary.json",
        ".workflowprogram/design/",
    ],
}

FORBIDDEN_ACTIVE_DOC_SNIPPETS = {
    ".claude/commands/develop.md": [
        "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/stage-progress.py update ...",
    ],
    ".claude/skills/workflowprogram-develop/SKILL.md": [
        "执行过程中必须通过 `${CLAUDE_PLUGIN_ROOT}/scripts/stage-progress.py` 写入进展与关键节点结果。",
    ],
    "docs/workflowprogram-stage-lowlevel-design.md": [
        "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/stage-progress.py update ...",
    ],
}

ACTIVE_TEMPLATE_DOC = {
    ".claude/skills/workflow-spec-support/yaml-spec-template.md": [
        "stage_slot: S5",
        "generated_runtime_contract",
        "runtime_capabilities",
        "workflow_graph",
        "capability_discovery",
        "host_capabilities",
        "agent_team_contract",
        "workflowprogram-validate",
        "validation-runtime-report.md",
        "test_contract",
        ".workflowprogram/design/workflow-maintenance.md",
        "registry",
    ],
}

ACTIVE_PLAN_DOC = {
    "docs/workflowprogram-test-change-plan.md": [
        "P1",
        "workflowprogram-validate",
        "runtime_smoke.py",
        "workflowprogram-design-status.md",
        "capability matrix",
    ],
}

ACTIVE_STATUS_DOCS = {
    "docs/workflowprogram-design-status.md": [
        "当前生效设计真源",
        "历史追溯文档",
        "已关闭决策",
        "workflow-entry.py",
        "shared-control-plane-wrapper",
        "capability_discovery",
    ],
}

ENTRY_EXPOSURE_DOCS = {
    "README.md": "/workflowprogram-native-cn:workflowprogram-orchestrate",
    "README.en.md": "/workflowprogram-native-cn:workflowprogram-orchestrate",
    ".claude-plugin/README.md": "/workflowprogram-native-cn:workflowprogram-orchestrate",
    "docs/workflowprogram-stage-highlevel-design.md": "/workflowprogram-native-cn:workflowprogram-orchestrate",
    "docs/workflowprogram-stage-lowlevel-design.md": "/workflowprogram-native-cn:workflowprogram-orchestrate",
}

CAPABILITY_MATRIX_PATH = "docs/workflowprogram-capability-matrix.json"

SOURCE_DIST_FILE_ROOTS = {
    ".claude/agents": "agents",
    ".claude/commands": "commands",
    ".claude/rules": "rules",
    ".claude/scripts": "scripts",
    ".claude/skills": "skills",
    ".claude/workflows": "workflows",
    ".claude-plugin": ".claude-plugin",
    ".claude-plugin/root": "",
}

PRODUCT_NATIVE_WORKFLOW_FILES = [
    "workflowprogram-develop.js",
    "workflowprogram-audit.js",
    "workflowprogram-iterate.js",
    "workflowprogram-validate.js",
    "workflowprogram-publish.js",
]


class ValidationResult:
    """收集校验通过项与错误项。"""

    def __init__(self):
        self.passes: List[str] = []
        self.errors: List[str] = []

    def add_pass(self, message: str):
        self.passes.append(message)

    def add_error(self, message: str):
        self.errors.append(message)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


def parse_frontmatter(content: str) -> Dict[str, str]:
    """从 Markdown 内容中解析 YAML frontmatter。"""
    match = re.search(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not match:
        raise ValueError("Missing YAML frontmatter")

    frontmatter = {}
    for line in match.group(1).split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        # 这里仅需要最简单的 `key: value` 解析，因此故意保持无依赖，
        # 不再额外引入 YAML 解析器。
        match_kv = re.match(r'^([^:#]+):\s*(.+?)\s*$', line)
        if match_kv:
            key = match_kv.group(1).strip()
            value = match_kv.group(2).strip().strip('"\'')
            frontmatter[key] = value

    return frontmatter


def sha256_file(path: Path) -> str:
    """返回文件的 SHA-256 摘要。"""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def utf8_subprocess_env() -> Dict[str, str]:
    """Return a child-process environment with a stable text protocol encoding."""

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def git_index_mode(root: Path, relative_path: str) -> Optional[str]:
    """返回 git index 中记录的文件模式；git 不可用时返回 None。"""

    try:
        completed = subprocess.run(
            ["git", "ls-files", "--stage", "--", relative_path],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=utf8_subprocess_env(),
            check=False,
        )
    except FileNotFoundError:
        return None
    if completed.returncode != 0:
        return None
    first_line = completed.stdout.strip().splitlines()[0] if completed.stdout.strip() else ""
    return first_line.split()[0] if first_line else None


def iter_source_files(root: Path) -> List[Path]:
    """递归枚举源码文件，并跳过 Python 缓存产物。"""
    files: List[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        files.append(path)
    return files


def load_build_plugin_module(root: Path):
    """加载 `build_plugin.py`，让 dist 期望值复用真实构建逻辑。"""
    module_path = root / "tools" / "build_plugin.py"
    spec = importlib.util.spec_from_file_location("workflowprogram_build_plugin", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load build_plugin.py from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expected_dist_bytes(build_plugin: Any, source_root_rel: str, source_file: Path) -> bytes:
    """计算某个源码文件在 dist/plugin 中应产出的精确字节内容。"""
    if source_root_rel == ".claude-plugin/root":
        return source_file.read_bytes()
    if source_root_rel == ".claude-plugin":
        return source_file.read_bytes()

    content = source_file.read_text(encoding="utf-8")
    if source_root_rel == ".claude/commands":
        name = source_file.stem
        desc, hint = build_plugin.COMMAND_DESCRIPTIONS[name]
        frontmatter = (
            "---\n"
            f"description: {build_plugin.yaml_string(desc)}\n"
            f"argument-hint: {build_plugin.yaml_string(hint)}\n"
            "---\n\n"
        )
        rendered = frontmatter + build_plugin.MARKDOWN_HEADER + build_plugin.apply_replacements(content)
        return rendered.encode("utf-8")

    if source_root_rel == ".claude/scripts":
        rendered = build_plugin.decorate_generated_text(source_file, build_plugin.apply_replacements(content))
        return rendered.encode("utf-8")

    rendered = build_plugin.decorate_generated_text(source_file, content)
    return rendered.encode("utf-8")


def validate_required_paths(root: Path, result: ValidationResult) -> None:
    """校验必需文件和目录是否存在。"""
    required_paths = [
        "CLAUDE.md",
        "README.md",
        "lessons.md",
        "validation-report.md",
        ".claude/settings.json",
        ".claude/commands",
        ".claude/skills",
        ".claude/rules/constraints.md",
        ".claude/scripts/managed-assets.py",
        ".claude/scripts/route-intent.py",
        ".claude/scripts/route-native-control-plane.py",
        ".claude/scripts/resolve-change-context.py",
        ".claude/scripts/validate-change-policy.py",
        ".claude/scripts/generate-design-review-packet.py",
        ".claude/scripts/validate-design-review-gate.py",
        ".claude/scripts/validate-target-design-governance.py",
        ".claude/scripts/validate-target-node-design.py",
        ".claude/scripts/runtime_host.py",
        ".claude/scripts/generate-target-runtime.py",
        ".claude/scripts/generate-workflow-view.py",
        ".claude/scripts/generate-workflow-maintenance.py",
        ".claude/scripts/generate-workflow-lowlevel.py",
        ".claude/scripts/generate-native-workflow.py",
        ".claude/scripts/build-native-develop-evidence.py",
        ".claude/scripts/build-native-iterate-evidence.py",
        ".claude/scripts/build-native-publish-evidence.py",
        ".claude/scripts/build-native-interactive-smoke.py",
        ".claude/scripts/workflowprogram-foreground-guard.py",
        ".claude/scripts/validate-native-authoring-readiness.py",
        ".claude/scripts/probe-host-capabilities.py",
        ".claude/scripts/probe-native-workflow-capability.py",
        ".claude/scripts/discover-host-capabilities.py",
        ".claude/scripts/apply-host-bootstrap.py",
        ".claude/scripts/apply-target-claude-guard.py",
        ".claude/scripts/generate-environment-remediation.py",
        ".claude/scripts/generate-clarification-package.py",
        ".claude/scripts/generate-clarification-review.py",
        ".claude/scripts/workflow-publish-entry.py",
        ".claude/scripts/validate-publish-eligibility.py",
        ".claude/scripts/package-target-plugin.py",
        ".claude/scripts/merge-target-marketplace.py",
        ".claude/scripts/validate-target-plugin-package.py",
        ".claude/scripts/github-publish-target-plugin.py",
        ".claude/scripts/bootstrap-python-runtime.py",
        ".claude/scripts/doctor.py",
        ".claude/scripts/clean-workflowprogram.py",
        ".claude/scripts/lib/control_plane.py",
        ".claude/scripts/lib/target_claude_guard.py",
        ".claude/scripts/lib/target_design_refs.py",
        ".claude/scripts/target-workflow-runner.py",
        ".claude/scripts/validate-target-runtime-state.py",
        ".claude/scripts/target-runtime-finalizer.py",
        ".claude/scripts/validate-target-publish-state.py",
        ".claude/scripts/validate-generated-runtime.py",
        ".claude/scripts/validate-workflow-maintenance.py",
        ".claude/scripts/validate-workflow-lowlevel.py",
        ".claude/scripts/validate-native-workflow-js.py",
        ".claude/scripts/build-native-workflow-manifest.py",
        ".claude/scripts/validate-publish-qualification.py",
        ".claude/scripts/resolve-task-model-policy.py",
        ".claude/scripts/assess-native-legacy-retirement.py",
        ".claude/scripts/validate-lessons-delta.py",
        ".claude/scripts/validate-run-state.py",
        ".claude/scripts/validate-workflow-draft.py",
        ".claude/scripts/validate-workflow-spec.py",
        ".claude/scripts/workflow-entry.py",
        ".claude/scripts/workflow-runner.py",
        ".claude/scripts/workflow-s5-judge.py",
        ".claude/scripts/stage-progress.py",
        ".claude/scripts/quality-gate.py",
        ".claude/scripts/validate-workflow.ps1",
        ".claude/scripts/validate-workflow.py",  # Self-check
        ".claude/agents/requirement-clarification-lead.md",
        ".claude/agents/workflow-design-reviewer.md",
        ".claude/skills/workflowprogram-native-develop/SKILL.md",
        ".claude/skills/workflow-spec-support/logic-lenses.md",
        ".claude/workflows/workflowprogram-native-authoring.js",
        *[f".claude/workflows/{name}" for name in PRODUCT_NATIVE_WORKFLOW_FILES],
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        ".claude-plugin/root/requirements.lock.txt",
        ".claude-plugin/root/runtime-manifest.json",
        ".claude-plugin/root/hooks/hooks.json",
        ".claude-plugin/root/bin/workflowprogram-python",
        ".claude-plugin/root/bin/workflowprogram-doctor",
        ".claude-plugin/root/bin/workflowprogram-clean",
        ".claude-plugin/root/bin/workflowprogram-artifact-writer",
        "tools/build_plugin.py",
        "tools/generate-view.py",
        "tools/mock_runtime_host.py",
        "tools/runtime_smoke.py",
        "tools/runtime_smoke_matrix.py",
        "tools/test_plugin_bootstrap.py",
        "tools/test_clean_workflowprogram.py",
        "tests/fixtures",
        "tests/spec-fixtures",
        "tests/draft-fixtures",
        "tests/expectations",
        "tests/transcripts",
        "tests/native-workflow-fixtures",
        "tests/manual-fixtures/native-workflow-authoring",
        "tests/manual-fixtures/native-workflow-develop-reentrant",
        "tests/manual-fixtures/native-workflow-product-registration",
        "tests/manual-fixtures/native-workflow-smoke",
        "docs/workflowprogram-stage-highlevel-design.md",
        "docs/workflowprogram-stage-lowlevel-design.md",
        "docs/workflowprogram-stage-consistency-check.md",
        "docs/native-workflow-control-plane-highlevel-design.md",
        "docs/native-workflow-control-plane-lowlevel-design.md",
        "docs/native-workflow-control-plane-migration-plan.md",
        "docs/native-workflow-control-plane-implementation-plan.md",
        "docs/workflowprogram-test-change-plan.md",
        "docs/workflowprogram-design-status.md",
        "docs/workflowprogram-capability-matrix.json",
        "docs/phase-07-implementation-plan.md",
        ".claude/skills/workflow-spec-support/yaml-spec-template.md",
        ".claude/skills/workflow-spec-support/target-node-design-template.md",
    ]

    for relative_path in required_paths:
        full_path = root / relative_path
        if full_path.exists():
            result.add_pass(f"Found {relative_path}")
        else:
            result.add_error(f"Missing required path: {relative_path}")

    for relative_path in FORBIDDEN_LEGACY_PATHS:
        full_path = root / relative_path
        if full_path.exists():
            result.add_error(f"Legacy compatibility path must not exist: {relative_path}")
        else:
            result.add_pass(f"Legacy compatibility path removed: {relative_path}")

    for relative_path in PLUGIN_EXECUTABLE_PATHS:
        full_path = root / relative_path
        if os.name == "nt" and full_path.exists():
            result.add_pass(f"Plugin executable local execute-bit check skipped on Windows: {relative_path}")
        elif full_path.exists() and full_path.stat().st_mode & 0o111:
            result.add_pass(f"Plugin executable has local execute bit: {relative_path}")
        else:
            result.add_error(f"Plugin executable is missing local execute bit: {relative_path}")
        git_mode = git_index_mode(root, relative_path)
        if git_mode is None:
            result.add_pass(f"Git mode check skipped for {relative_path}")
        elif git_mode == "100755":
            result.add_pass(f"Plugin executable has git mode 100755: {relative_path}")
        else:
            result.add_error(f"Plugin executable git mode must be 100755: {relative_path} is {git_mode}")


def validate_logic_lens_definition_drift(root: Path, result: ValidationResult) -> None:
    """Ensure human-readable and machine-readable logic lens definitions stay aligned."""

    lens_doc = root / ".claude" / "skills" / "workflow-spec-support" / "logic-lenses.md"
    if not lens_doc.exists():
        result.add_error("Missing logic lens definition doc: .claude/skills/workflow-spec-support/logic-lenses.md")
        return

    script_root = root / ".claude" / "scripts"
    if str(script_root) not in sys.path:
        sys.path.insert(0, str(script_root))
    try:
        from lib.clarification_utils import LOGIC_LENSES
    except Exception as exc:
        result.add_error(f"Cannot import LOGIC_LENSES for drift check: {exc}")
        return

    text = lens_doc.read_text(encoding="utf-8")
    for lens in LOGIC_LENSES:
        fields = [
            ("runtime_key", lens.get("runtime_key", lens["key"])),
            ("legacy_key", lens["key"]),
            ("title", lens["title"]),
            ("task", lens["task"]),
            ("question", lens["question"]),
        ]
        for field_name, value in fields:
            if value in text:
                result.add_pass(f"Logic lens doc includes {lens['key']} {field_name}")
            else:
                result.add_error(f"Logic lens doc missing {lens['key']} {field_name}: {value}")


def validate_document_contracts(root: Path, result: ValidationResult) -> None:
    """校验当前生效的设计文档和入口文档是否反映了最新契约模型。"""
    for relative_path, markers in ACTIVE_PLAN_DOC.items():
        full_path = root / relative_path
        if not full_path.exists():
            result.add_error(f"Missing active plan doc: {relative_path}")
            continue
        try:
            content = full_path.read_text(encoding='utf-8')
        except Exception as e:
            result.add_error(f"Cannot read active plan doc '{relative_path}': {e}")
            continue

        result.add_pass(f"Active plan doc present: {relative_path}")
        for marker in markers:
            if marker in content:
                result.add_pass(f"Active plan doc '{relative_path}' includes '{marker}'")
            else:
                result.add_error(f"Active plan doc '{relative_path}' is missing '{marker}'")

    for relative_path, markers in ACTIVE_STATUS_DOCS.items():
        full_path = root / relative_path
        if not full_path.exists():
            result.add_error(f"Missing active status doc: {relative_path}")
            continue
        try:
            content = full_path.read_text(encoding='utf-8')
        except Exception as e:
            result.add_error(f"Cannot read active status doc '{relative_path}': {e}")
            continue

        result.add_pass(f"Active status doc present: {relative_path}")
        for marker in markers:
            if marker in content:
                result.add_pass(f"Active status doc '{relative_path}' includes '{marker}'")
            else:
                result.add_error(f"Active status doc '{relative_path}' is missing '{marker}'")

    for relative_path, markers in ACTIVE_DESIGN_DOCS.items():
        full_path = root / relative_path
        if not full_path.exists():
            result.add_error(f"Missing active design doc: {relative_path}")
            continue
        try:
            content = full_path.read_text(encoding='utf-8')
        except Exception as e:
            result.add_error(f"Cannot read active design doc '{relative_path}': {e}")
            continue

        result.add_pass(f"Active design doc present: {relative_path}")
        for marker in markers:
            if marker in content:
                result.add_pass(f"Active design doc '{relative_path}' includes '{marker}'")
            else:
                result.add_error(f"Active design doc '{relative_path}' is missing '{marker}'")

    for relative_path, markers in ACTIVE_ENTRY_DOCS.items():
        full_path = root / relative_path
        if not full_path.exists():
            result.add_error(f"Missing active entry doc: {relative_path}")
            continue
        try:
            content = full_path.read_text(encoding='utf-8')
        except Exception as e:
            result.add_error(f"Cannot read active entry doc '{relative_path}': {e}")
            continue

        result.add_pass(f"Active entry doc present: {relative_path}")
        for marker in markers:
            if marker in content:
                result.add_pass(f"Active entry doc '{relative_path}' includes '{marker}'")
            else:
                result.add_error(f"Active entry doc '{relative_path}' is missing '{marker}'")

    for relative_path, markers in ACTIVE_TEMPLATE_DOC.items():
        full_path = root / relative_path
        if not full_path.exists():
            result.add_error(f"Missing active template doc: {relative_path}")
            continue
        try:
            content = full_path.read_text(encoding='utf-8')
        except Exception as e:
            result.add_error(f"Cannot read active template doc '{relative_path}': {e}")
            continue

        result.add_pass(f"Active template doc present: {relative_path}")
        for marker in markers:
            if marker in content:
                result.add_pass(f"Active template doc '{relative_path}' includes '{marker}'")
            else:
                result.add_error(f"Active template doc '{relative_path}' is missing '{marker}'")

    for relative_path, expected_entry in ENTRY_EXPOSURE_DOCS.items():
        full_path = root / relative_path
        if not full_path.exists():
            result.add_error(f"Missing entry exposure doc: {relative_path}")
            continue
        try:
            content = full_path.read_text(encoding='utf-8')
        except Exception as e:
            result.add_error(f"Cannot read entry exposure doc '{relative_path}': {e}")
            continue

        if expected_entry in content:
            result.add_pass(f"Entry exposure doc '{relative_path}' recommends namespaced orchestrator")
        else:
            result.add_error(f"Entry exposure doc '{relative_path}' must recommend {expected_entry}")
        if "/workflowprogram-orchestrate ..." in content or "/workflowprogram-develop \"" in content:
            result.add_error(f"Entry exposure doc '{relative_path}' still presents a non-namespaced primary entry")
        else:
            result.add_pass(f"Entry exposure doc '{relative_path}' avoids non-namespaced primary entry examples")

    for relative_path, snippets in FORBIDDEN_ACTIVE_DOC_SNIPPETS.items():
        full_path = root / relative_path
        if not full_path.exists():
            result.add_error(f"Missing active doc for anti-regression check: {relative_path}")
            continue
        try:
            content = full_path.read_text(encoding="utf-8")
        except Exception as e:
            result.add_error(f"Cannot read active doc '{relative_path}' for anti-regression check: {e}")
            continue

        for snippet in snippets:
            if snippet in content:
                result.add_error(
                    f"Active doc '{relative_path}' re-exposes fragile progress CLI assembly: '{snippet}'"
                )
            else:
                result.add_pass(f"Active doc '{relative_path}' avoids fragile progress CLI snippet '{snippet}'")


def validate_stage_progress_hardening(root: Path, result: ValidationResult) -> None:
    """Validate helper-backed progress emission and direct CLI compatibility."""

    helper_path = root / ".claude" / "scripts" / "lib" / "control_plane.py"
    script_path = root / ".claude" / "scripts" / "stage-progress.py"
    if not helper_path.exists() or not script_path.exists():
        result.add_error("Missing control-plane helper or stage-progress script for hardening validation")
        return

    helper_spec = importlib.util.spec_from_file_location("workflowprogram_control_plane_helper", helper_path)
    if helper_spec is None or helper_spec.loader is None:
        result.add_error(f"Cannot load control-plane helper from {helper_path}")
        return
    helper_module = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helper_module)

    sample_run_root = Path("/tmp/workflow-hardening-sample-run")
    command = helper_module.build_stage_progress_command(
        python_executable=sys.executable,
        stage_progress_script=script_path,
        run_root=sample_run_root,
        stage="S2",
        node="context_scan",
        event="StageCheckpoint",
        status="ok",
        percent=55,
        result="context report ready",
        next_action="review findings",
        artifact_refs=["outputs/stages/s2-context-report.md", ""],
        verdict="PASS",
        approval_status="approved",
    )
    expected_command = [
        sys.executable,
        str(script_path),
        "update",
        "--run-root",
        str(sample_run_root),
        "--stage",
        "S2",
        "--node",
        "context_scan",
        "--event",
        "StageCheckpoint",
        "--status",
        "ok",
        "--percent",
        "55",
        "--result",
        "context report ready",
        "--next-action",
        "review findings",
        "--verdict",
        "PASS",
        "--approval-status",
        "approved",
        "--artifact-ref",
        "outputs/stages/s2-context-report.md",
    ]
    if command == expected_command:
        result.add_pass("control-plane helper builds the expected stage-progress CLI argv")
    else:
        result.add_error("control-plane helper argv mapping drifted from the expected stage-progress CLI contract")

    with tempfile.TemporaryDirectory(prefix="workflow-stage-progress-helper-") as temp_dir:
        run_root = Path(temp_dir)
        for idx, event in enumerate(("StageStarted", "StageCheckpoint", "StageCompleted"), start=1):
            helper_module.emit_stage_progress(
                python_executable=sys.executable,
                stage_progress_script=script_path,
                run_root=run_root,
                stage="S1",
                node=f"node_{idx}",
                event=event,
                status="running" if event == "StageStarted" else "ok",
                percent=idx * 25,
                result=f"{event} through helper",
                next_action="continue",
                artifact_refs=[f"outputs/stages/{event.lower()}.md"],
                verdict="PASS" if event != "StageStarted" else "",
                approval_status="approved" if event == "StageCompleted" else "",
            )

        current_path = run_root / "outputs" / "progress" / "current-progress.json"
        milestones_path = run_root / "outputs" / "progress" / "milestones.jsonl"
        user_progress_path = run_root / "outputs" / "progress" / "user-progress.md"
        if current_path.exists() and milestones_path.exists() and user_progress_path.exists():
            result.add_pass("helper-backed progress emission materializes all progress artifacts")
        else:
            result.add_error("helper-backed progress emission did not materialize all progress artifacts")

        try:
            current_payload = json.loads(current_path.read_text(encoding="utf-8"))
            milestone_lines = [line for line in milestones_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            user_progress = user_progress_path.read_text(encoding="utf-8")
        except Exception as exc:
            result.add_error(f"Cannot read helper-backed progress artifacts: {exc}")
        else:
            if current_payload.get("current_stage") == "S1" and current_payload.get("last_status") == "ok":
                result.add_pass("helper-backed progress emission keeps current-progress.json semantics intact")
            else:
                result.add_error("helper-backed progress emission changed current-progress.json semantics")
            if len(milestone_lines) == 3:
                result.add_pass("helper-backed progress emission preserves milestone append behavior")
            else:
                result.add_error("helper-backed progress emission did not append the expected milestone count")
            if "## 历史关键节点结果" in user_progress:
                result.add_pass("helper-backed progress emission preserves user-progress.md structure")
            else:
                result.add_error("helper-backed progress emission changed user-progress.md structure")

    with tempfile.TemporaryDirectory(prefix="workflow-stage-progress-cli-") as temp_dir:
        run_root = Path(temp_dir)
        direct_command = [
            sys.executable,
            str(script_path),
            "update",
            "--run-root",
            str(run_root),
            "--stage",
            "S0",
            "--node",
            "route_intent",
            "--event",
            "StageStarted",
            "--status",
            "running",
            "--percent",
            "5",
            "--result",
            "direct cli compatibility",
            "--next-action",
            "continue routing",
            "--json",
        ]
        completed = subprocess.run(
            direct_command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=utf8_subprocess_env(),
            check=False,
        )
        if completed.returncode == 0:
            result.add_pass("Direct stage-progress.py CLI compatibility is preserved")
        else:
            result.add_error(
                f"Direct stage-progress.py CLI compatibility regressed: {completed.stderr.strip() or completed.stdout.strip()}"
            )


def validate_settings_json(root: Path, result: ValidationResult) -> Optional[Dict]:
    """校验 settings.json 格式，并在成功时返回解析结果。"""
    settings_path = root / ".claude/settings.json"

    if not settings_path.exists():
        result.add_error("Missing .claude/settings.json")
        return None

    try:
        with open(settings_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        result.add_pass("Parsed .claude/settings.json")
        return settings
    except json.JSONDecodeError as e:
        result.add_error(f"Invalid JSON in .claude/settings.json: {e}")
        return None


def validate_commands(root: Path, settings: Dict, result: ValidationResult) -> None:
    """校验命令文档是否结构正确且已注册。"""
    commands_dir = root / ".claude/commands"
    if not commands_dir.exists():
        result.add_error("Missing .claude/commands directory")
        return

    registered_commands = {}
    if settings and 'commands' in settings:
        for cmd_name, cmd_info in settings['commands'].items():
            file_path = cmd_info.get('file', '')
            registered_commands[cmd_name] = file_path
            full_path = root / file_path

            if full_path.exists():
                result.add_pass(f"Registered command '{cmd_name}' points to an existing file")
            else:
                result.add_error(f"Registered command '{cmd_name}' points to a missing file: {file_path}")

    # 每个命令不仅要存在于磁盘上，还要保持产品入口 wrapper 所依赖的 staged prompt 结构。
    for cmd_file in sorted(commands_dir.glob("*.md")):
        relative = f".claude/commands/{cmd_file.name}"

        try:
            with open(cmd_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            result.add_error(f"Cannot read command '{cmd_file.name}': {e}")
            continue

        # Usage / Stage / Goal / Verify 共同保证命令文档结构稳定，
        # 这样人工阅读和构建工具都能依赖同一套形态。
        if re.search(r'^## Usage\s*$', content, re.MULTILINE):
            result.add_pass(f"Command '{cmd_file.name}' has a Usage section")
        else:
            result.add_error(f"Command '{cmd_file.name}' is missing a Usage section")

        # 检查 staged 结构
        if re.search(r'^## Stage \d+:', content, re.MULTILINE):
            result.add_pass(f"Command '{cmd_file.name}' uses staged structure")
        else:
            result.add_error(f"Command '{cmd_file.name}' is missing numbered stages")

        # 检查 Goal 和 Verify
        if '**Goal**:' in content and '**Verify**:' in content:
            result.add_pass(f"Command '{cmd_file.name}' defines Goal and Verify")
        else:
            result.add_error(f"Command '{cmd_file.name}' is missing Goal or Verify")

        # 检查注册情况
        if relative in registered_commands.values():
            result.add_pass(f"Command '{cmd_file.name}' is registered in settings.json")
        else:
            result.add_error(f"Command '{cmd_file.name}' exists on disk but is not registered in settings.json")


def validate_skills(root: Path, settings: Dict, result: ValidationResult) -> None:
    """校验 skill 是否结构正确且已注册。"""
    skills_dir = root / ".claude/skills"
    if not skills_dir.exists():
        result.add_error("Missing .claude/skills directory")
        return

    registered_skills = {}
    if settings and 'skills' in settings:
        for skill_name, skill_info in settings['skills'].items():
            file_path = skill_info.get('file', '')
            registered_skills[skill_name] = file_path
            full_path = root / file_path

            if full_path.exists():
                result.add_pass(f"Registered skill '{skill_name}' points to an existing file")
            else:
                result.add_error(f"Registered skill '{skill_name}' points to a missing file: {file_path}")

    # 检查每个 skill 目录
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue

        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            result.add_error(f"Skill directory '{skill_dir.name}' is missing SKILL.md")
            continue

        try:
            with open(skill_md, 'r', encoding='utf-8') as f:
                content = f.read()

            frontmatter = parse_frontmatter(content)

            # frontmatter 被视为契约元数据，因为构建层和 UI 层都依赖它向用户暴露 skill。
            for field in ["name", "description", "version"]:
                if field in frontmatter and frontmatter[field]:
                    result.add_pass(f"Skill '{skill_dir.name}' includes frontmatter field '{field}'")
                else:
                    result.add_error(f"Skill '{skill_dir.name}' is missing frontmatter field '{field}'")

            # 检查注册情况（internal skill 可豁免）
            is_internal = frontmatter.get("internal", "").lower() == "true"
            relative_skill = f".claude/skills/{skill_dir.name}/SKILL.md"

            if is_internal:
                result.add_pass(f"Internal support skill '{skill_dir.name}' is exempt from settings registration")
            elif relative_skill in registered_skills.values():
                result.add_pass(f"Skill '{skill_dir.name}' is registered in settings.json")
            else:
                result.add_error(f"Skill '{skill_dir.name}' exists on disk but is not registered in settings.json")

        except ValueError as e:
            result.add_error(f"Skill '{skill_dir.name}': {e}")
        except Exception as e:
            result.add_error(f"Cannot validate skill '{skill_dir.name}': {e}")


def validate_primary_skill_set(settings: Dict, result: ValidationResult) -> None:
    """校验 skills-first 的主入口是否已经注册。"""
    if not settings or 'skills' not in settings:
        result.add_error('settings.json is missing skills registration')
        return

    registered = settings['skills']
    for skill_name in REQUIRED_PRIMARY_SKILLS:
        if skill_name in registered:
            result.add_pass(f"Primary skill '{skill_name}' is registered in settings.json")
        else:
            result.add_error(f"Missing required primary skill registration: {skill_name}")


def validate_constraints(root: Path, result: ValidationResult) -> None:
    """校验 constraints.md 是否同时包含 ALWAYS 与 NEVER 规则。"""
    constraints_path = root / ".claude/rules/constraints.md"

    if not constraints_path.exists():
        result.add_error("Missing .claude/rules/constraints.md")
        return

    try:
        with open(constraints_path, 'r', encoding='utf-8') as f:
            content = f.read()

        has_always = 'ALWAYS' in content
        has_never = 'NEVER' in content

        if has_always and has_never:
            result.add_pass("constraints.md includes BOTH ALWAYS and NEVER rules")
        else:
            missing = []
            if not has_always:
                missing.append("ALWAYS")
            if not has_never:
                missing.append("NEVER")
            result.add_error(f"constraints.md must include BOTH ALWAYS and NEVER rules (missing: {', '.join(missing)})")
    except Exception as e:
        result.add_error(f"Cannot validate constraints.md: {e}")


def validate_plugin_metadata(root: Path, result: ValidationResult) -> Optional[Dict[str, Any]]:
    """校验插件元数据文件，并返回解析后的 plugin.json 内容。"""
    plugin_json_path = root / ".claude-plugin" / "plugin.json"
    marketplace_json_path = root / ".claude-plugin" / "marketplace.json"
    runtime_manifest_path = root / ".claude-plugin" / "root" / "runtime-manifest.json"
    hooks_path = root / ".claude-plugin" / "root" / "hooks" / "hooks.json"

    plugin_meta: Optional[Dict[str, Any]] = None
    try:
        plugin_meta = json.loads(plugin_json_path.read_text(encoding="utf-8"))
        result.add_pass("Parsed .claude-plugin/plugin.json")
        for field in ["name", "version", "description"]:
            if plugin_meta.get(field):
                result.add_pass(f"plugin.json includes field '{field}'")
            else:
                result.add_error(f"plugin.json is missing field '{field}'")
    except Exception as e:
        result.add_error(f"Cannot parse .claude-plugin/plugin.json: {e}")

    try:
        marketplace_meta = json.loads(marketplace_json_path.read_text(encoding="utf-8"))
        result.add_pass("Parsed .claude-plugin/marketplace.json")
        plugins = marketplace_meta.get("plugins")
        if isinstance(plugins, list) and plugins:
            result.add_pass("marketplace.json defines at least one plugin entry")
            first_plugin = plugins[0]
            if isinstance(first_plugin, dict):
                source = first_plugin.get("source")
                if isinstance(source, dict):
                    if source.get("source") == "git-subdir":
                        result.add_pass("marketplace.json uses git-subdir source")
                    else:
                        result.add_error("marketplace.json source.source must be git-subdir")
                    if str(source.get("path", "")).strip() == "dist/plugin":
                        result.add_pass("marketplace.json points to dist/plugin")
                    else:
                        result.add_error("marketplace.json source.path must be dist/plugin")
                else:
                    result.add_error("marketplace.json plugin source must be a mapping/object")
        else:
            result.add_error("marketplace.json must define at least one plugin entry")
    except Exception as e:
        result.add_error(f"Cannot parse .claude-plugin/marketplace.json: {e}")

    try:
        runtime_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8"))
        result.add_pass("Parsed .claude-plugin/root/runtime-manifest.json")
        if runtime_manifest.get("python_dependency_model") == "plugin-local-site-packages":
            result.add_pass("runtime-manifest declares plugin-local-site-packages")
        else:
            result.add_error("runtime-manifest must declare python_dependency_model=plugin-local-site-packages")
        if str(runtime_manifest.get("launcher", "")).strip() == "bin/workflowprogram-python":
            result.add_pass("runtime-manifest launcher points to bin/workflowprogram-python")
        else:
            result.add_error("runtime-manifest launcher must be bin/workflowprogram-python")
    except Exception as e:
        result.add_error(f"Cannot parse .claude-plugin/root/runtime-manifest.json: {e}")

    try:
        hooks_meta = json.loads(hooks_path.read_text(encoding="utf-8"))
        result.add_pass("Parsed .claude-plugin/root/hooks/hooks.json")
        session_start = hooks_meta.get("hooks", {}).get("SessionStart")
        if isinstance(session_start, list) and session_start:
            result.add_pass("hooks.json defines SessionStart hook")
        else:
            result.add_error("hooks.json must define a non-empty SessionStart hook")
        pre_tool_use = hooks_meta.get("hooks", {}).get("PreToolUse")
        if isinstance(pre_tool_use, list) and pre_tool_use:
            result.add_pass("hooks.json defines PreToolUse foreground guard hook")
        else:
            result.add_error("hooks.json must define a non-empty PreToolUse hook")
    except Exception as e:
        result.add_error(f"Cannot parse .claude-plugin/root/hooks/hooks.json: {e}")

    return plugin_meta


def validate_capability_matrix(root: Path, result: ValidationResult) -> None:
    """校验用于跟踪实现覆盖度的 capability matrix。"""
    matrix_path = root / CAPABILITY_MATRIX_PATH
    if not matrix_path.exists():
        result.add_error(f"Missing capability matrix: {CAPABILITY_MATRIX_PATH}")
        return

    try:
        payload = json.loads(matrix_path.read_text(encoding="utf-8"))
    except Exception as e:
        result.add_error(f"Cannot parse capability matrix '{CAPABILITY_MATRIX_PATH}': {e}")
        return

    if payload.get("version") == 1:
        result.add_pass("Capability matrix version is 1")
    else:
        result.add_error("Capability matrix must declare version=1")

    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, list) or not capabilities:
        result.add_error("Capability matrix must define a non-empty capabilities list")
        return

    for capability in capabilities:
        if not isinstance(capability, dict):
            result.add_error("Capability matrix entries must be mapping objects")
            continue
        capability_id = str(capability.get("id", "")).strip()
        checks = capability.get("checks")
        if not capability_id:
            result.add_error("Capability matrix entry is missing id")
            continue
        if not isinstance(checks, list) or not checks:
            result.add_error(f"Capability '{capability_id}' must define non-empty checks")
            continue
        result.add_pass(f"Capability matrix defines checks for '{capability_id}'")
        for check in checks:
            if not isinstance(check, dict):
                result.add_error(f"Capability '{capability_id}' contains a non-mapping check")
                continue
            relative_path = str(check.get("file", "")).strip()
            markers = check.get("markers")
            if not relative_path:
                result.add_error(f"Capability '{capability_id}' contains a check without file")
                continue
            full_path = root / relative_path
            if not full_path.exists():
                result.add_error(f"Capability '{capability_id}' references a missing file: {relative_path}")
                continue
            result.add_pass(f"Capability '{capability_id}' references existing file: {relative_path}")
            if not isinstance(markers, list) or not markers:
                result.add_error(f"Capability '{capability_id}' check for '{relative_path}' must include non-empty markers")
                continue
            try:
                content = full_path.read_text(encoding="utf-8")
            except Exception as e:
                result.add_error(f"Cannot read capability matrix file '{relative_path}': {e}")
                continue
            for marker in markers:
                marker_text = str(marker)
                if marker_text in content:
                    result.add_pass(f"Capability '{capability_id}' file '{relative_path}' includes '{marker_text}'")
                else:
                    result.add_error(f"Capability '{capability_id}' file '{relative_path}' is missing '{marker_text}'")


def validate_draft_fixtures(root: Path, result: ValidationResult) -> None:
    """运行 S1 deep clarification draft fixtures。"""
    fixtures_root = root / "tests" / "draft-fixtures"
    if not fixtures_root.exists():
        result.add_error("Missing tests/draft-fixtures")
        return

    generator_script = root / ".claude" / "scripts" / "generate-clarification-package.py"
    review_script = root / ".claude" / "scripts" / "generate-clarification-review.py"
    validator_script = root / ".claude" / "scripts" / "validate-workflow-draft.py"

    for fixture_dir in sorted(path for path in fixtures_root.iterdir() if path.is_dir()):
        fixture_name = fixture_dir.name
        meta_path = fixture_dir / "fixture.json"
        spec_path = fixture_dir / "workflow-spec.md"
        if not meta_path.exists():
            result.add_error(f"Draft fixture '{fixture_name}' is missing fixture.json")
            continue
        if not spec_path.exists():
            result.add_error(f"Draft fixture '{fixture_name}' is missing workflow-spec.md")
            continue

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:
            result.add_error(f"Cannot parse draft fixture manifest '{meta_path}': {exc}")
            continue

        expected_status = str(meta.get("expected_status", "")).strip()
        if expected_status not in {"PASS", "FAIL"}:
            result.add_error(f"Draft fixture '{fixture_name}' must declare expected_status PASS or FAIL")
            continue

        with tempfile.TemporaryDirectory(prefix=f"workflow-draft-fixture-{fixture_name}-") as temp_dir:
            run_root = Path(temp_dir)
            temp_spec_path = run_root / "workflow-spec.md"
            temp_spec_path.write_text(spec_path.read_text(encoding="utf-8"), encoding="utf-8")

            for script_path, label in (
                (generator_script, "generate-clarification-package"),
                (review_script, "generate-clarification-review"),
            ):
                command = [
                    sys.executable,
                    str(script_path),
                    "--spec",
                    str(temp_spec_path),
                    "--run-root",
                    str(run_root),
                    "--json",
                ]
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=utf8_subprocess_env(),
                )
                if completed.returncode != 0:
                    stderr = completed.stderr.strip()
                    stdout = completed.stdout.strip()
                    details = stderr or stdout or f"exit code {completed.returncode}"
                    result.add_error(f"Draft fixture '{fixture_name}' failed during {label}: {details}")
                    break
                result.add_pass(f"Draft fixture '{fixture_name}' generated {label} outputs")
            else:
                validate_command = [
                    sys.executable,
                    str(validator_script),
                    "--spec",
                    str(temp_spec_path),
                    "--run-root",
                    str(run_root),
                    "--json",
                ]
                completed = subprocess.run(
                    validate_command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=utf8_subprocess_env(),
                )
                try:
                    payload = json.loads(completed.stdout or "{}")
                except Exception as exc:
                    result.add_error(f"Draft fixture '{fixture_name}' produced invalid validator JSON: {exc}")
                    continue

                observed_status = str(payload.get("status", "")).strip()
                if observed_status == expected_status:
                    result.add_pass(f"Draft fixture '{fixture_name}' returned expected status {expected_status}")
                else:
                    result.add_error(
                        f"Draft fixture '{fixture_name}' returned status {observed_status or 'UNKNOWN'} (expected {expected_status})"
                    )

                for snippet in meta.get("expected_error_substrings", []):
                    if any(str(snippet) in error for error in payload.get("errors", [])):
                        result.add_pass(f"Draft fixture '{fixture_name}' exposes expected error snippet '{snippet}'")
                    else:
                        result.add_error(f"Draft fixture '{fixture_name}' is missing expected error snippet '{snippet}'")

                if meta.get("expected_handoff_ready") is True:
                    handoff_path = run_root / "outputs" / "stages" / "clarification-handoff.json"
                    evidence_path = run_root / "outputs" / "stages" / "clarification-evidence.json"
                    try:
                        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
                        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
                    except Exception as exc:
                        result.add_error(f"Draft fixture '{fixture_name}' cannot read handoff/evidence outputs: {exc}")
                        continue
                    if handoff.get("ready") is True:
                        result.add_pass(f"Draft fixture '{fixture_name}' produces ready handoff for S2/S3")
                    else:
                        result.add_error(f"Draft fixture '{fixture_name}' must produce ready handoff for S2/S3")
                    if handoff.get("s2_inputs") and handoff.get("s3_inputs"):
                        result.add_pass(f"Draft fixture '{fixture_name}' includes non-empty s2_inputs and s3_inputs")
                    else:
                        result.add_error(f"Draft fixture '{fixture_name}' must include non-empty s2_inputs and s3_inputs")
                    evidence_checks = evidence.get("evidence_checks", {})
                    if evidence_checks.get("s2_handoff_ready") is True and evidence_checks.get("s3_handoff_ready") is True:
                        result.add_pass(f"Draft fixture '{fixture_name}' records handoff readiness in clarification evidence")
                    else:
                        result.add_error(f"Draft fixture '{fixture_name}' must record s2/s3 handoff readiness in clarification evidence")


def validate_dist_plugin(root: Path, plugin_meta: Optional[Dict[str, Any]], result: ValidationResult) -> None:
    """根据源码树和 build trace manifest 校验 dist/plugin。"""
    dist_root = root / "dist" / "plugin"
    if not dist_root.exists():
        result.add_pass("dist/plugin not present; build output validation skipped")
        return
    build_plugin = load_build_plugin_module(root)

    required_paths = [
        dist_root / ".claude-plugin" / "plugin.json",
        dist_root / ".claude-plugin" / "marketplace.json",
        dist_root / "requirements.lock.txt",
        dist_root / "runtime-manifest.json",
        dist_root / "hooks" / "hooks.json",
        dist_root / "bin" / "workflowprogram-python",
        dist_root / "bin" / "workflowprogram-doctor",
        dist_root / "bin" / "workflowprogram-clean",
        dist_root / "bin" / "workflowprogram-artifact-writer",
        dist_root / "build-manifest.json",
        dist_root / "scripts" / "managed-assets.py",
        dist_root / "scripts" / "route-intent.py",
        dist_root / "scripts" / "route-native-control-plane.py",
        dist_root / "scripts" / "resolve-change-context.py",
        dist_root / "scripts" / "validate-change-policy.py",
        dist_root / "scripts" / "generate-design-review-packet.py",
        dist_root / "scripts" / "validate-design-review-gate.py",
        dist_root / "scripts" / "validate-target-design-governance.py",
        dist_root / "scripts" / "validate-target-node-design.py",
        dist_root / "scripts" / "runtime_host.py",
        dist_root / "scripts" / "generate-target-runtime.py",
        dist_root / "scripts" / "generate-workflow-view.py",
        dist_root / "scripts" / "generate-workflow-maintenance.py",
        dist_root / "scripts" / "generate-workflow-lowlevel.py",
        dist_root / "scripts" / "generate-native-workflow.py",
        dist_root / "scripts" / "build-native-develop-evidence.py",
        dist_root / "scripts" / "build-native-iterate-evidence.py",
        dist_root / "scripts" / "build-native-publish-evidence.py",
        dist_root / "scripts" / "build-native-interactive-smoke.py",
        dist_root / "scripts" / "workflowprogram-foreground-guard.py",
        dist_root / "scripts" / "validate-native-authoring-readiness.py",
        dist_root / "scripts" / "probe-host-capabilities.py",
        dist_root / "scripts" / "probe-native-workflow-capability.py",
        dist_root / "scripts" / "discover-host-capabilities.py",
        dist_root / "scripts" / "apply-host-bootstrap.py",
        dist_root / "scripts" / "generate-environment-remediation.py",
        dist_root / "scripts" / "generate-clarification-package.py",
        dist_root / "scripts" / "generate-clarification-review.py",
        dist_root / "scripts" / "bootstrap-python-runtime.py",
        dist_root / "scripts" / "doctor.py",
        dist_root / "scripts" / "clean-workflowprogram.py",
        dist_root / "scripts" / "stage-progress.py",
        dist_root / "scripts" / "quality-gate.py",
        dist_root / "scripts" / "target-workflow-runner.py",
        dist_root / "scripts" / "validate-target-runtime-state.py",
        dist_root / "scripts" / "target-runtime-finalizer.py",
        dist_root / "scripts" / "validate-target-publish-state.py",
        dist_root / "scripts" / "validate-generated-runtime.py",
        dist_root / "scripts" / "validate-lessons-delta.py",
        dist_root / "scripts" / "validate-workflow-maintenance.py",
        dist_root / "scripts" / "validate-workflow-lowlevel.py",
        dist_root / "scripts" / "validate-native-workflow-js.py",
        dist_root / "scripts" / "build-native-workflow-manifest.py",
        dist_root / "scripts" / "validate-publish-qualification.py",
        dist_root / "scripts" / "resolve-task-model-policy.py",
        dist_root / "scripts" / "assess-native-legacy-retirement.py",
        dist_root / "scripts" / "validate-run-state.py",
        dist_root / "scripts" / "validate-workflow-draft.py",
        dist_root / "scripts" / "validate-workflow-spec.py",
        dist_root / "scripts" / "workflow-entry.py",
        dist_root / "scripts" / "workflow-runner.py",
        dist_root / "scripts" / "workflow-s5-judge.py",
        dist_root / "agents" / "requirement-clarification-lead.md",
        dist_root / "agents" / "workflow-design-reviewer.md",
        dist_root / "skills" / "workflowprogram-native-develop" / "SKILL.md",
        dist_root / "skills" / "workflow-spec-support" / "logic-lenses.md",
        dist_root / "workflows" / "workflowprogram-native-authoring.js",
        *[dist_root / "workflows" / name for name in PRODUCT_NATIVE_WORKFLOW_FILES],
    ]
    for path in required_paths:
        relative = path.relative_to(root)
        if path.exists():
            result.add_pass(f"Build output contains {relative}")
        else:
            result.add_error(f"Build output is missing {relative}")

    manifest_path = dist_root / "build-manifest.json"
    if not manifest_path.exists():
        return

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result.add_pass("Parsed dist/plugin/build-manifest.json")
    except Exception as e:
        result.add_error(f"Cannot parse dist/plugin/build-manifest.json: {e}")
        return

    for field in ["manifest_version", "generated_at", "plugin_name", "plugin_version", "files"]:
        if field in manifest:
            result.add_pass(f"build-manifest.json includes field '{field}'")
        else:
            result.add_error(f"build-manifest.json is missing field '{field}'")

    if plugin_meta:
        if manifest.get("plugin_name") == plugin_meta.get("name"):
            result.add_pass("build-manifest plugin_name matches source plugin.json")
        else:
            result.add_error("build-manifest plugin_name does not match source plugin.json")
        if manifest.get("plugin_version") == plugin_meta.get("version"):
            result.add_pass("build-manifest plugin_version matches source plugin.json")
        else:
            result.add_error("build-manifest plugin_version does not match source plugin.json")

    files = manifest.get("files", [])
    if not isinstance(files, list):
        result.add_error("build-manifest files must be a list")
        return

    manifest_paths = set()
    for item in files:
        path = item.get("path")
        sha256 = item.get("sha256")
        if not path:
            result.add_error("build-manifest contains an entry without path")
            continue
        manifest_paths.add(str(path))
        if not sha256 or len(sha256) != 64:
            result.add_error(f"build-manifest entry '{path}' is missing a valid sha256")
            continue
        built_file = dist_root / path
        if built_file.exists():
            result.add_pass(f"build-manifest file exists: {path}")
            actual_sha = sha256_file(built_file)
            if actual_sha == sha256:
                result.add_pass(f"build-manifest sha256 matches built file: {path}")
            else:
                result.add_error(f"build-manifest sha256 mismatch for {path}")
        else:
            result.add_error(f"build-manifest references a missing file: {path}")
    for source_root_rel, dist_root_rel in SOURCE_DIST_FILE_ROOTS.items():
        # 基于真源文件重新计算期望输出，这样一旦有人手改 dist/plugin，就会立刻被发现。
        source_root = root / source_root_rel
        destination_root = dist_root / dist_root_rel
        for source_file in iter_source_files(source_root):
            if source_root_rel == ".claude-plugin" and (root / ".claude-plugin" / "root") in source_file.parents:
                continue
            relative = source_file.relative_to(source_root)
            built_file = destination_root / relative
            dist_relative = str(built_file.relative_to(dist_root)).replace("\\", "/")
            if built_file.exists():
                result.add_pass(f"Build output contains mapped source file: {dist_relative}")
                if built_file.read_bytes() == expected_dist_bytes(build_plugin, source_root_rel, source_file):
                    result.add_pass(f"Build output matches source content: {dist_relative}")
                else:
                    result.add_error(f"Build output content drift for {dist_relative}")
            else:
                result.add_error(f"Build output is missing mapped source file: {dist_relative}")
                continue
            if dist_relative in manifest_paths:
                result.add_pass(f"build-manifest tracks mapped source file: {dist_relative}")
            else:
                result.add_error(f"build-manifest is missing mapped source file: {dist_relative}")

    command_wrappers = sorted((dist_root / "skills").glob("command-*/SKILL.md"))
    if command_wrappers:
        for wrapper_file in command_wrappers:
            wrapper_relative = str(wrapper_file.relative_to(dist_root)).replace("\\", "/")
            result.add_error(f"Unapproved command wrapper is exposed in dist/plugin: {wrapper_relative}")
    else:
        result.add_pass("No generated command-* wrapper skills are exposed in dist/plugin")

    for markdown_file in sorted((dist_root / "commands").glob("*.md")) + sorted((dist_root / "skills").glob("*/SKILL.md")):
        text = markdown_file.read_text(encoding="utf-8")
        relative = str(markdown_file.relative_to(dist_root)).replace("\\", "/")
        if text.startswith(build_plugin.MARKDOWN_HEADER):
            result.add_error(f"Generated Markdown marker appears before frontmatter in {relative}")
            continue
        if text.startswith("---\n"):
            result.add_pass(f"Generated Markdown preserves leading frontmatter: {relative}")
        else:
            result.add_pass(f"Generated Markdown has no leading frontmatter contract: {relative}")


def validate_product_native_workflows(root: Path, result: ValidationResult) -> None:
    """Run the lightweight Native JS validator for product registration assets."""

    validator = root / ".claude" / "scripts" / "validate-native-workflow-js.py"
    workflow_roots = [
        root / ".claude" / "workflows",
        root / "dist" / "plugin" / "workflows",
    ]
    workflow_files = ["workflowprogram-native-authoring.js", *PRODUCT_NATIVE_WORKFLOW_FILES]
    for workflow_root in workflow_roots:
        if not workflow_root.exists():
            continue
        for name in workflow_files:
            script = workflow_root / name
            if not script.exists():
                continue
            completed = subprocess.run(
                [sys.executable, str(validator), "--script", str(script), "--json"],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=utf8_subprocess_env(),
                check=False,
            )
            relative = script.relative_to(root)
            if completed.returncode == 0:
                result.add_pass(f"Native Workflow JS static validation passed: {relative}")
            else:
                result.add_error(f"Native Workflow JS static validation failed: {relative}\n{completed.stdout.strip()}")


def print_report(result: ValidationResult) -> None:
    """以结构化格式打印校验报告。"""
    print("\n" + "=" * 50)
    print("Workflow Validation Summary")
    print("=" * 50)

    print(f"\nPASS: {len(result.passes)}")
    for item in result.passes:
        print(f"  [PASS] {item}")

    print(f"\nFAIL: {len(result.errors)}")
    for item in result.errors:
        print(f"  [FAIL] {item}")

    print("\n" + "=" * 50)
    if result.is_valid:
        print("Result: ALL CHECKS PASSED")
    else:
        print(f"Result: {len(result.errors)} ERROR(S) FOUND")
    print("=" * 50 + "\n")


def main():
    """针对指定根目录运行整套仓库校验。"""
    # 若未显式传入路径，则默认使用仓库根目录。
    if len(sys.argv) > 1:
        root = Path(sys.argv[1]).resolve()
    else:
        # `.claude/scripts/validate-workflow.py` 位于仓库根目录下两级位置。
        root = Path(__file__).resolve().parents[2]

    print(f"Validating WorkflowProgram at: {root}")

    result = ValidationResult()

    # 这里的顺序是刻意安排的：先确保文件存在并解析 settings，
    # 后续检查才能安全假定核心仓库结构已经成立。
    validate_required_paths(root, result)
    validate_logic_lens_definition_drift(root, result)
    settings = validate_settings_json(root, result)

    if settings:
        validate_commands(root, settings, result)
        validate_skills(root, settings, result)
        validate_primary_skill_set(settings, result)

    validate_document_contracts(root, result)
    validate_stage_progress_hardening(root, result)
    validate_capability_matrix(root, result)
    validate_draft_fixtures(root, result)
    validate_product_native_workflows(root, result)
    validate_constraints(root, result)
    plugin_meta = validate_plugin_metadata(root, result)
    validate_dist_plugin(root, plugin_meta, result)

    # 输出完整的通过/失败报告，而不是首错即停，便于一次性完成仓库清理。
    print_report(result)

    sys.exit(0 if result.is_valid else 1)


if __name__ == '__main__':
    main()
