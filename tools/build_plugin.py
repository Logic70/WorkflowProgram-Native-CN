#!/usr/bin/env python3
"""
WorkflowProgram 的 dist/plugin 构建器。

真源目录：
    .claude/
    .claude-plugin/

构建输出：
    dist/plugin/
"""

from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = ROOT / ".claude" / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from lib.io_utils import iso_now


CLAUDE = ROOT / ".claude"
PLUGIN_META = ROOT / ".claude-plugin"
PLUGIN_ROOT_ASSETS = PLUGIN_META / "root"
DIST = ROOT / "dist" / "plugin"

COMMAND_DESCRIPTIONS = {
    "develop": ("Compatibility workflow design entry; prefer workflowprogram-orchestrate", "<requirement> [--auto-approve]"),
    "ship": ("Repository shipping compatibility command", "[scope] [--auto-approve]"),
    "preflight": ("Repository preflight compatibility command", "[scope]"),
    "hotfix": ("Repository hotfix compatibility command", "[description]"),
    "evolve-workflow": ("Compatibility workflow audit entry; prefer workflowprogram-orchestrate", "[options] <workflow-path>"),
    "iterate-workflow": ("Compatibility lessons iteration entry; prefer workflowprogram-orchestrate", "[--dry-run] [--apply] [workflow-path]"),
    "workflowprogram-publish": ("Publish a completed target workflow as a Claude Code marketplace plugin", "<target-root> --plugin-id <id> --repo <owner/repo-or-url> [--repo-mode existing_marketplace --repo-path <checkout>] [--dry-run]"),
}

REPLACEMENTS = {
    ".claude/skills/workflow-spec-support/spec-template.md": "${CLAUDE_PLUGIN_ROOT}/skills/workflow-spec-support/spec-template.md",
    ".claude/rules/constraints.md": "${CLAUDE_PLUGIN_ROOT}/rules/constraints.md",
    ".claude/scripts/validate-workflow.ps1": "${CLAUDE_PLUGIN_ROOT}/scripts/validate-workflow.ps1",
    ".claude/scripts/managed-assets.py": "${CLAUDE_PLUGIN_ROOT}/scripts/managed-assets.py",
}

MARKDOWN_HEADER = "<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->\n\n"
SCRIPT_BANNER = "AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY"


def ensure_parent(path: Path) -> None:
    """在写入生成文件前确保父目录存在。"""
    path.parent.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> None:
    """以统一换行格式写入 UTF-8 文本。"""
    ensure_parent(path)
    path.write_text(content, encoding="utf-8", newline="\n")


def decorate_generated_text(src: Path, content: str) -> str:
    """按输出文件类型添加合适的“自动生成”头部标记。"""
    suffix = src.suffix.lower()
    if suffix == ".md":
        return add_generated_markdown_header(content)
    if suffix in {".py", ".sh", ".ps1"}:
        banner = f"# {SCRIPT_BANNER}\n"
        if content.startswith("#!"):
            first_line, _, remainder = content.partition("\n")
            return f"{first_line}\n{banner}{remainder}"
        return banner + content
    return content


def add_generated_markdown_header(content: str) -> str:
    """为 Markdown 添加生成标记，同时不破坏 Claude Code frontmatter 发现。

    Claude Code 会用文件开头的 frontmatter 解析 command / skill 描述。
    如果把注释放在 `---` 之前，UI 可能把生成标记当成描述显示。
    """

    if content.startswith("---\n"):
        closing = content.find("\n---\n", 4)
        if closing != -1:
            end = closing + len("\n---\n")
            return content[:end] + "\n" + MARKDOWN_HEADER + content[end:]
    return MARKDOWN_HEADER + content


def copy_generated_text(src: Path, dst: Path, *, replace_paths: bool = False) -> None:
    """把文本资产复制到 dist，并可选做路径替换和头部标记注入。"""
    content = src.read_text(encoding="utf-8")
    if replace_paths:
        content = apply_replacements(content)
    write_text(dst, decorate_generated_text(src, content))


def copy_tree_generated(src_dir: Path, dst_dir: Path, *, replace_paths: bool = False) -> None:
    """把整棵生成型文本目录树复制到 dist。"""
    for src in sorted(src_dir.rglob("*")):
        if src.is_file():
            dst = dst_dir / src.relative_to(src_dir)
            copy_generated_text(src, dst, replace_paths=replace_paths)


def copy_plugin_manifest(src_dir: Path, dst_dir: Path) -> None:
    """把插件元数据文件原样复制到 dist 载荷。"""
    for src in sorted(src_dir.rglob("*")):
        if src.is_file():
            if PLUGIN_ROOT_ASSETS in src.parents:
                continue
            dst = dst_dir / src.relative_to(src_dir)
            ensure_parent(dst)
            shutil.copy2(src, dst)


def copy_plugin_root_assets(src_dir: Path, dst_dir: Path) -> None:
    """把插件根级资产复制到 dist/plugin 根目录。"""
    if not src_dir.exists():
        return
    for src in sorted(src_dir.rglob("*")):
        if not src.is_file():
            continue
        dst = dst_dir / src.relative_to(src_dir)
        ensure_parent(dst)
        shutil.copy2(src, dst)


def apply_replacements(content: str) -> str:
    """把仓库内路径改写成 dist/plugin 运行时占位路径。"""
    for old, new in REPLACEMENTS.items():
        content = content.replace(old, new)
    return content


def yaml_string(value: str) -> str:
    """Render a frontmatter string as a quoted YAML scalar."""
    return json.dumps(value, ensure_ascii=False)


def render_command(src: Path, dst: Path, desc: str, hint: str) -> None:
    """为命令 Markdown 生成带 frontmatter 的分发版本。"""
    body = apply_replacements(src.read_text(encoding="utf-8"))
    frontmatter = (
        "---\n"
        f"description: {yaml_string(desc)}\n"
        f"argument-hint: {yaml_string(hint)}\n"
        "---\n\n"
    )
    write_text(dst, frontmatter + MARKDOWN_HEADER + body)


def prepare_output_dirs(root: Path) -> None:
    """从零重建 dist/plugin 目录。"""
    if root.exists():
        shutil.rmtree(root)
    for dirname in [".claude-plugin", "agents", "bin", "commands", "hooks", "skills", "rules", "scripts", "workflows"]:
        (root / dirname).mkdir(parents=True, exist_ok=True)


def build_agents() -> None:
    """把 agent 定义复制到 dist 载荷。"""
    copy_tree_generated(CLAUDE / "agents", DIST / "agents")


def build_rules() -> None:
    """把当前生效的规则集复制到 dist 载荷。"""
    copy_generated_text(CLAUDE / "rules" / "constraints.md", DIST / "rules" / "constraints.md")


def build_scripts() -> None:
    """复制必须随插件一起分发的运行时脚本。"""
    allowed_suffixes = {".py", ".ps1", ".sh"}
    for src in sorted((CLAUDE / "scripts").rglob("*")):
        if not src.is_file():
            continue
        if src.suffix.lower() not in allowed_suffixes:
            continue
        dst = DIST / "scripts" / src.relative_to(CLAUDE / "scripts")
        copy_generated_text(src, dst, replace_paths=True)


def build_skills() -> None:
    """把 skill 目录复制到 dist/plugin。"""
    copy_tree_generated(CLAUDE / "skills", DIST / "skills")


def build_workflows() -> None:
    """把插件自身的 Native Workflow JS 控制面复制到 dist/plugin。"""

    copy_tree_generated(CLAUDE / "workflows", DIST / "workflows")


def build_commands() -> None:
    """根据源命令生成命令 Markdown。

    command-as-skill wrapper 曾用于兼容旧发现模型，但会让 `command-develop`
    等重复入口暴露给用户。Marketplace 分发只保留 command 本身。
    """
    for src in sorted((CLAUDE / "commands").glob("*.md")):
        name = src.stem
        desc, hint = COMMAND_DESCRIPTIONS[name]
        render_command(src, DIST / "commands" / src.name, desc, hint)


def build_plugin_manifest_dir() -> None:
    """把插件市场元数据复制到 dist/plugin。"""
    copy_plugin_manifest(PLUGIN_META, DIST / ".claude-plugin")


def build_plugin_root_assets() -> None:
    """把插件根目录运行时资产复制到 dist/plugin 根。"""
    copy_plugin_root_assets(PLUGIN_ROOT_ASSETS, DIST)


def ensure_executable_bits() -> None:
    """确保 marketplace 载荷中的 launcher 在新安装缓存里可直接执行。"""
    for relative in (
        "bin/workflowprogram-python",
        "bin/workflowprogram-doctor",
        "bin/workflowprogram-clean",
        "bin/workflowprogram-artifact-writer",
    ):
        path = DIST / relative
        if path.exists():
            path.chmod(path.stat().st_mode | 0o755)


def sha256_file(path: Path) -> str:
    """返回文件 SHA-256，用于 build trace manifest。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_plugin_metadata() -> dict:
    """从源 manifest 加载插件元数据。"""
    return json.loads((PLUGIN_META / "plugin.json").read_text(encoding="utf-8"))


def git_output(*args: str) -> str | None:
    """执行 git 命令，并在可用时返回 stdout。"""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def source_commit() -> str | None:
    """在 git 元数据可用时返回源码 commit hash。"""
    return git_output("rev-parse", "HEAD")


def source_dirty() -> bool | None:
    """返回源码工作区是否存在未提交修改。"""
    output = git_output("status", "--short")
    if output is None:
        return None
    return bool(output)


def collect_output_files(root: Path) -> list[dict]:
    """枚举构建输出文件，供 build trace manifest 记录。"""
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name == "build-manifest.json":
            continue
        relative = path.relative_to(root).as_posix()
        files.append(
            {
                "path": relative,
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
        )
    return files


def build_trace_manifest(commit: str | None, dirty: bool | None) -> None:
    """写出把 dist 载荷与源码树关联起来的 trace manifest。"""
    plugin_meta = load_plugin_metadata()
    payload = {
        "manifest_version": 1,
        "generated_at": iso_now(),
        "builder": "tools/build_plugin.py",
        "plugin_name": plugin_meta.get("name"),
        "plugin_version": plugin_meta.get("version"),
        "source_commit": commit,
        "source_dirty": dirty,
        "files": collect_output_files(DIST),
    }
    write_text(DIST / "build-manifest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    """根据真源目录构建 dist/plugin 载荷。"""
    commit = source_commit()
    dirty = source_dirty()
    prepare_output_dirs(DIST)
    build_plugin_manifest_dir()
    build_plugin_root_assets()
    ensure_executable_bits()
    build_agents()
    build_rules()
    build_scripts()
    build_skills()
    build_workflows()
    build_commands()
    build_trace_manifest(commit, dirty)
    plugin_meta = load_plugin_metadata()
    print("Build complete")
    print(f"  Source: {CLAUDE}")
    print(f"  Manifest: {PLUGIN_META}")
    print(f"  Output: {DIST}")
    print(f"  Plugin: {plugin_meta.get('name')}@{plugin_meta.get('version')}")
    print(f"  Trace manifest: {DIST / 'build-manifest.json'}")


if __name__ == "__main__":
    main()
