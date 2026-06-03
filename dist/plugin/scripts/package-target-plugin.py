#!/usr/bin/env python3
# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
"""Stage a WorkflowProgram-generated target workflow as a Claude Code plugin package."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set

from lib.io_utils import iso_now, write_json
from lib.yaml_utils import load_yaml_mapping


PUBLISH_DIR = "outputs/stages/publish"
VALID_RUNTIME_MODES = {"workflowprogram_dependency", "vendored_runtime"}
VALID_REPO_MODES = {"current_repo", "export_repo", "existing_marketplace"}
CORE_CLAUDE_DIRS = ("commands", "skills", "agents", "rules", "hooks")
WORKFLOWPROGRAM_DIRS = ("design", "runtime", "loops", "bootstrap")
SUPPORT_DIRS = ("config", "templates", "schemas", "assets", "data", "scripts")
TEXT_REF_SUFFIXES = {".md", ".txt", ".yaml", ".yml", ".json", ".html", ".py"}
EXCLUDED_NAMES = {".git", ".pytest_cache", "__pycache__"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp", ".bak", ".swp"}
LOCAL_REF_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_./-])"
    r"((?:\.claude|\.workflowprogram|config|templates|schemas|assets|data|scripts)/[A-Za-z0-9_./@+\-]*)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package a target workflow as a Claude Code plugin")
    parser.add_argument("--target-root", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--plugin-id", required=True)
    parser.add_argument("--plugin-name", default="")
    parser.add_argument("--version", default="0.1.0")
    parser.add_argument("--description", default="WorkflowProgram generated Claude Code workflow plugin")
    parser.add_argument("--repository-url", default="")
    parser.add_argument("--marketplace-name", default="target-workflow-plugins")
    parser.add_argument("--repo-mode", default="export_repo", choices=sorted(VALID_REPO_MODES))
    parser.add_argument("--runtime-mode", default="workflowprogram_dependency", choices=sorted(VALID_RUNTIME_MODES))
    parser.add_argument("--workflowprogram-plugin-root", default="")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def sanitize_plugin_id(value: str) -> str:
    return value.strip().lower()


def valid_plugin_id(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", value))


def should_exclude(path: Path) -> bool:
    if any(part in EXCLUDED_NAMES for part in path.parts):
        return True
    if path.name in {".DS_Store", "Thumbs.db"}:
        return True
    return path.suffix in EXCLUDED_SUFFIXES or path.name.endswith("~")


def record_included(path: Path, included: List[str], package_root: Path) -> None:
    rel = path.relative_to(package_root).as_posix()
    if rel not in included:
        included.append(rel)


def package_rel_for_source_ref(ref: str) -> str:
    value = ref.strip().strip("`'\"")
    if value.startswith(".claude/commands/"):
        return "commands/" + value[len(".claude/commands/") :]
    if value.startswith(".claude/skills/"):
        return "skills/" + value[len(".claude/skills/") :]
    if value.startswith(".claude/agents/"):
        return "agents/" + value[len(".claude/agents/") :]
    if value.startswith(".claude/rules/"):
        return "rules/" + value[len(".claude/rules/") :]
    if value.startswith(".claude/hooks/"):
        return "hooks/" + value[len(".claude/hooks/") :]
    return value


def copy_file_if_exists(src: Path, dst: Path, included: List[str], package_root: Path) -> None:
    if not src.exists() or not src.is_file() or should_exclude(src):
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    record_included(dst, included, package_root)


def copy_tree_if_exists(src: Path, dst: Path, included: List[str], package_root: Path) -> None:
    if not src.exists():
        return
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        if should_exclude(path):
            continue
        rel = path.relative_to(src)
        target = dst / rel
        copy_file_if_exists(path, target, included, package_root)


def write_text(path: Path, content: str, included: List[str], package_root: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    record_included(path, included, package_root)


def package_files(package_root: Path) -> List[Dict[str, Any]]:
    files: List[Dict[str, Any]] = []
    for path in sorted(package_root.rglob("*")):
        if path.is_file():
            files.append({"path": path.relative_to(package_root).as_posix(), "size": path.stat().st_size})
    return files


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def rewrite_settings_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: rewrite_settings_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [rewrite_settings_value(item) for item in value]
    if isinstance(value, str):
        return package_rel_for_source_ref(value)
    return value


def copy_rewritten_settings(target_root: Path, package_root: Path, included: List[str]) -> None:
    settings_path = target_root / ".claude" / "settings.json"
    settings = load_json(settings_path)
    if not settings:
        return
    write_json(package_root / ".claude" / "settings.json", rewrite_settings_value(settings))
    record_included(package_root / ".claude" / "settings.json", included, package_root)


def text_files_for_reference_scan(target_root: Path) -> Iterable[Path]:
    roots = [
        target_root / "CLAUDE.md",
        target_root / ".workflowprogram" / "design",
        target_root / ".claude" / "commands",
        target_root / ".claude" / "skills",
        target_root / ".claude" / "agents",
        target_root / ".claude" / "rules",
    ]
    for root in roots:
        if root.is_file():
            yield root
            continue
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in TEXT_REF_SUFFIXES and not should_exclude(path):
                yield path


def clean_ref_token(token: str) -> str:
    return token.strip().strip("`'\"<>()[]{} ,;:").rstrip(".")


def support_ref_allowed(ref: str) -> bool:
    allowed = [".workflowprogram/loops/", ".workflowprogram/bootstrap/"]
    allowed.extend(f"{prefix}/" for prefix in SUPPORT_DIRS)
    return any(ref == prefix.rstrip("/") or ref.startswith(prefix) for prefix in allowed)


def discover_support_refs(target_root: Path) -> Set[str]:
    refs: Set[str] = set()
    spec_path = target_root / ".workflowprogram" / "design" / "workflow-spec.yaml"
    if spec_path.exists():
        try:
            spec = load_yaml_mapping(spec_path)
        except Exception:
            spec = {}
        refs.update(string_refs_from_payload(spec))
    for path in text_files_for_reference_scan(target_root):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for match in LOCAL_REF_PATTERN.finditer(text):
            refs.add(clean_ref_token(match.group(1)))
    return {ref for ref in refs if support_ref_allowed(ref)}


def string_refs_from_payload(payload: Any) -> Set[str]:
    refs: Set[str] = set()
    if isinstance(payload, dict):
        for value in payload.values():
            refs.update(string_refs_from_payload(value))
    elif isinstance(payload, list):
        for value in payload:
            refs.update(string_refs_from_payload(value))
    elif isinstance(payload, str):
        value = clean_ref_token(payload)
        if support_ref_allowed(value):
            refs.add(value)
    return refs


def copy_support_ref(target_root: Path, package_root: Path, ref: str, included: List[str]) -> None:
    src = target_root / ref
    dst = package_root / package_rel_for_source_ref(ref)
    if src.is_dir():
        copy_tree_if_exists(src, dst, included, package_root)
    elif src.is_file():
        copy_file_if_exists(src, dst, included, package_root)


def copy_support_assets(target_root: Path, package_root: Path, included: List[str]) -> List[str]:
    copied_refs: List[str] = []
    copy_file_if_exists(target_root / ".workflowprogram" / "managed-files.json", package_root / ".workflowprogram" / "managed-files.json", included, package_root)
    for name in WORKFLOWPROGRAM_DIRS:
        copy_tree_if_exists(target_root / ".workflowprogram" / name, package_root / ".workflowprogram" / name, included, package_root)
    for name in SUPPORT_DIRS:
        copy_tree_if_exists(target_root / name, package_root / name, included, package_root)
    copy_file_if_exists(target_root / "CLAUDE.md", package_root / "CLAUDE.md", included, package_root)
    for ref in sorted(discover_support_refs(target_root)):
        before = set(included)
        copy_support_ref(target_root, package_root, ref, included)
        if set(included) != before:
            copied_refs.append(ref)
    return copied_refs


def runtime_dependencies(target_root: Path) -> List[str]:
    manifest = load_json(target_root / ".workflowprogram" / "runtime" / "runtime-manifest.json")
    dependencies = manifest.get("dependencies", {})
    packages = dependencies.get("packages", []) if isinstance(dependencies, dict) else []
    if not isinstance(packages, list):
        return []
    result: List[str] = []
    for item in packages:
        value = str(item).strip()
        if value and value not in result:
            result.append(value)
    return result


def infer_repo_owner(repository_url: str) -> str:
    value = repository_url.strip().rstrip("/")
    if not value:
        return "workflowprogram-user"
    match = re.search(r"github\.com[:/](?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?$", value)
    if match:
        return match.group("owner")
    if "/" in value and not value.startswith("http"):
        return value.split("/", 1)[0] or "workflowprogram-user"
    return "workflowprogram-user"


def vendor_runtime_assets(workflowprogram_plugin_root: Path, package_root: Path, included: List[str]) -> List[str]:
    copied: List[str] = []
    if not workflowprogram_plugin_root.exists():
        return copied
    for rel_path in [
        "bin/workflowprogram-python",
        "requirements.lock.txt",
        "scripts/workflow-runner.py",
        "scripts/validate-run-state.py",
        "scripts/target-workflow-runner.py",
        "scripts/validate-target-runtime-state.py",
        "scripts/target-runtime-finalizer.py",
        "scripts/validate-target-publish-state.py",
        "scripts/validate-workflow-spec.py",
        "scripts/probe-host-capabilities.py",
        "scripts/apply-host-bootstrap.py",
        "scripts/discover-host-capabilities.py",
        "scripts/generate-environment-remediation.py",
    ]:
        src = workflowprogram_plugin_root / rel_path
        if not src.exists() or not src.is_file():
            continue
        dst = package_root / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel_path)
        included.append(rel_path)
    return copied


def package_target_plugin(
    *,
    target_root: Path,
    run_root: Path,
    plugin_id: str,
    plugin_name: str,
    version: str,
    description: str,
    repository_url: str,
    marketplace_name: str,
    repo_mode: str,
    runtime_mode: str,
    workflowprogram_plugin_root: Path | None,
) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    normalized_id = sanitize_plugin_id(plugin_id)
    if normalized_id != plugin_id.strip():
        warnings.append(f"plugin id normalized to {normalized_id}")
    if not valid_plugin_id(normalized_id):
        errors.append("plugin id must match [a-z0-9][a-z0-9-]{1,62}")
    if runtime_mode not in VALID_RUNTIME_MODES:
        errors.append(f"runtime mode must be one of {sorted(VALID_RUNTIME_MODES)}")
    if repo_mode not in VALID_REPO_MODES:
        errors.append(f"repo mode must be one of {sorted(VALID_REPO_MODES)}")
    if errors:
        payload = {
            "schema_version": 1,
            "generated_at": iso_now(),
            "status": "FAIL",
            "errors": errors,
            "warnings": warnings,
            "package_root": None,
        }
        write_json(run_root / PUBLISH_DIR / "plugin-package-plan.json", payload)
        return payload

    package_root = run_root / PUBLISH_DIR / "package-root"
    if package_root.exists():
        shutil.rmtree(package_root)
    package_root.mkdir(parents=True, exist_ok=True)
    included: List[str] = []

    for src_name, dst_name in ((name, name) for name in CORE_CLAUDE_DIRS):
        copy_tree_if_exists(target_root / ".claude" / src_name, package_root / dst_name, included, package_root)

    copy_rewritten_settings(target_root, package_root, included)
    copied_support_refs = copy_support_assets(target_root, package_root, included)

    vendored_files: List[str] = []
    if runtime_mode == "vendored_runtime":
        vendored_files = vendor_runtime_assets(workflowprogram_plugin_root or Path(), package_root, included)
        if not vendored_files:
            warnings.append("vendored_runtime selected but no WorkflowProgram runtime files were copied")

    display_name = plugin_name.strip() or normalized_id
    repo = repository_url.strip() or f"https://github.com/<owner>/{normalized_id}"
    owner_name = infer_repo_owner(repo)
    dependency_packages = runtime_dependencies(target_root)
    plugin_json = {
        "name": normalized_id,
        "version": version,
        "description": description,
        "author": {"name": owner_name},
        "homepage": repo,
        "repository": repo,
        "license": "MIT",
        "keywords": ["claude-code", "workflow", "workflowprogram"],
    }
    marketplace_json = None
    if repo_mode != "existing_marketplace":
        marketplace_json = {
            "name": marketplace_name,
            "owner": {"name": owner_name},
            "plugins": [
                {
                    "name": normalized_id,
                    "source": {"source": "git-subdir", "url": repo, "path": "dist/plugin", "ref": "main"},
                    "description": description,
                    "version": version,
                    "homepage": repo,
                    "repository": repo,
                    "license": "MIT",
                    "keywords": ["workflow", "claude-code", "workflowprogram"],
                    "category": "workflow",
                    "tags": ["workflow", "claude-code"],
                    "strict": False,
                }
            ],
        }
    publish_meta = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "plugin_id": normalized_id,
        "plugin_name": display_name,
        "version": version,
        "repo_mode": repo_mode,
        "runtime_mode": runtime_mode,
        "source_target_root": str(target_root),
        "workflowprogram_dependency": runtime_mode == "workflowprogram_dependency",
        "vendored_runtime_files": vendored_files,
        "support_asset_refs": copied_support_refs,
        "dependency_packages": dependency_packages,
    }
    write_json(package_root / ".claude-plugin" / "plugin.json", plugin_json)
    included.append(".claude-plugin/plugin.json")
    if marketplace_json is not None:
        write_json(package_root / ".claude-plugin" / "marketplace.json", marketplace_json)
        included.append(".claude-plugin/marketplace.json")
    write_json(package_root / ".claude-plugin" / "workflowprogram-publish.json", publish_meta)
    included.append(".claude-plugin/workflowprogram-publish.json")
    readme_lines = [
        f"# {display_name}",
        "",
        "This Claude Code plugin was packaged from a WorkflowProgram-generated target workflow.",
        "",
    ]
    if repo_mode != "existing_marketplace":
        readme_lines.extend(
            [
                "## Install This Plugin",
                "",
                "Add this workflow plugin marketplace, then install the plugin:",
                "",
                "```text",
                f"/plugin marketplace add {marketplace_name} {repository_url}",
                f"/plugin install {normalized_id}@{marketplace_name}",
                "```",
                "",
            ]
        )
    readme_lines.extend(
        [
            "## Runtime Mode",
            "",
            f"- `{runtime_mode}`",
        ]
    )
    if runtime_mode == "workflowprogram_dependency":
        readme_lines.extend(
            [
                "- Install WorkflowProgram first:",
                "",
                "```text",
                "/plugin marketplace add logic70-plugins https://github.com/Logic70/WorkflowProgram.git",
                "/plugin install workflowprogram-cn@logic70-plugins",
                "```",
            ]
        )
    if dependency_packages:
        write_text(package_root / "requirements.txt", "\n".join(dependency_packages) + "\n", included, package_root)
        readme_lines.extend(
            [
                "",
                "## Python Dependencies",
                "",
                "Install target workflow Python dependencies before running scripts that render reports or validate workflow outputs:",
                "",
                "```text",
                "python3 -m pip install -r requirements.txt",
                "```",
                "",
                "Declared packages:",
                "",
                *[f"- `{package}`" for package in dependency_packages],
            ]
        )
    write_text(package_root / ".claude-plugin" / "README.md", "\n".join(readme_lines) + "\n", included, package_root)

    manifest_preview = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "plugin_json": plugin_json,
        "marketplace_json": marketplace_json,
        "publish_metadata": publish_meta,
    }
    write_json(run_root / PUBLISH_DIR / "plugin-manifest-preview.json", manifest_preview)
    payload = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "status": "PASS",
        "errors": [],
        "warnings": warnings,
        "target_root": str(target_root),
        "package_root": str(package_root),
        "plugin_id": normalized_id,
        "repo_mode": repo_mode,
        "runtime_mode": runtime_mode,
        "included_files": sorted(set(included)),
        "support_asset_refs": copied_support_refs,
        "dependency_packages": dependency_packages,
        "files": package_files(package_root),
    }
    write_json(run_root / PUBLISH_DIR / "plugin-package-plan.json", payload)
    return payload


def main() -> int:
    args = parse_args()
    payload = package_target_plugin(
        target_root=Path(args.target_root).resolve(),
        run_root=Path(args.run_root).resolve(),
        plugin_id=args.plugin_id,
        plugin_name=args.plugin_name,
        version=args.version,
        description=args.description,
        repository_url=args.repository_url,
        marketplace_name=args.marketplace_name,
        repo_mode=args.repo_mode,
        runtime_mode=args.runtime_mode,
        workflowprogram_plugin_root=Path(args.workflowprogram_plugin_root).resolve() if args.workflowprogram_plugin_root.strip() else None,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[{payload['status']}] package-root={payload.get('package_root')}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
