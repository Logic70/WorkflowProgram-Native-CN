#!/usr/bin/env python3
"""Validate a staged target workflow Claude Code plugin package."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set, Tuple

from lib.io_utils import iso_now, write_json


PUBLISH_DIR = "outputs/stages/publish"
LOCAL_REF_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_./-])"
    r"((?:\.claude|\.workflowprogram|config|templates|schemas|assets|data|scripts)/[A-Za-z0-9_./@+\-]*)"
)
TEXT_REF_SUFFIXES = {".md", ".txt", ".yaml", ".yml", ".json", ".html"}
EXCLUDED_NAMES = {".git", ".pytest_cache", "__pycache__"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp", ".bak", ".swp"}
IGNORED_REF_PREFIXES = (
    "outputs/",
    ".workflowprogram/runs/",
    ".workflowprogram/publish-run/",
    ".workflowprogram/archive/",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate target workflow plugin package")
    parser.add_argument("--package-root", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--repo-mode", default="export_repo", choices=["current_repo", "export_repo", "existing_marketplace"])
    parser.add_argument("--require-claude-validate", action="store_true")
    parser.add_argument("--skip-claude-validate", action="store_true")
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def package_rel_for_reference(ref: str) -> str:
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


def clean_ref_token(token: str) -> str:
    return token.strip().strip("`'\"<>()[]{} ,;:").rstrip(".")


def should_ignore_reference(ref: str) -> bool:
    if not ref or ref in {".claude/", ".workflowprogram/"}:
        return True
    if ref.endswith("/"):
        return True
    if ref in {".workflowprogram/runs", ".workflowprogram/archive", ".workflowprogram/publish-run"}:
        return True
    if any(ref.startswith(prefix) for prefix in IGNORED_REF_PREFIXES):
        return True
    if any(char in ref for char in "<>{}$"):
        return True
    return False


def should_exclude(path: Path) -> bool:
    if any(part in EXCLUDED_NAMES for part in path.parts):
        return True
    if path.name in {".DS_Store", "Thumbs.db"}:
        return True
    return path.suffix in EXCLUDED_SUFFIXES or path.name.endswith("~")


def iter_text_files(package_root: Path) -> Iterable[Path]:
    candidates = [
        package_root / "CLAUDE.md",
        package_root / "commands",
        package_root / "skills",
        package_root / "agents",
        package_root / ".workflowprogram" / "design",
    ]
    for candidate in candidates:
        if candidate.is_file():
            yield candidate
            continue
        if not candidate.exists():
            continue
        for path in sorted(candidate.rglob("*")):
            if path.is_file() and path.suffix.lower() in TEXT_REF_SUFFIXES and not should_exclude(path):
                yield path


def collect_local_references(package_root: Path) -> List[Tuple[str, str]]:
    refs: List[Tuple[str, str]] = []
    for path in iter_text_files(package_root):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        source = path.relative_to(package_root).as_posix()
        for match in LOCAL_REF_PATTERN.finditer(text):
            ref = clean_ref_token(match.group(1))
            if not should_ignore_reference(ref):
                refs.append((source, ref))
    return refs


def iter_settings_paths(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for item in value.values():
            yield from iter_settings_paths(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_settings_paths(item)
    elif isinstance(value, str):
        text = value.strip()
        if text.startswith((".claude/", "commands/", "skills/", "agents/", "rules/", "hooks/")):
            yield text


def runtime_dependencies(package_root: Path) -> List[str]:
    manifest = load_json(package_root / ".workflowprogram" / "runtime" / "runtime-manifest.json")
    dependencies = manifest.get("dependencies", {})
    packages = dependencies.get("packages", []) if isinstance(dependencies, dict) else []
    if not isinstance(packages, list):
        return []
    return [str(item).strip() for item in packages if str(item).strip()]


def run_target_spec_validator_if_available(package_root: Path) -> Dict[str, Any]:
    script = package_root / ".workflowprogram" / "runtime" / "validate-run-state.py"
    spec = package_root / ".workflowprogram" / "design" / "workflow-spec.yaml"
    if not script.exists() or not spec.exists():
        return {"status": "SKIPPED", "reason": "target runtime validator or design spec missing"}
    help_result = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True, check=False, timeout=15)
    help_text = help_result.stdout + help_result.stderr
    if "--spec" not in help_text:
        return {"status": "SKIPPED", "reason": "target runtime validator has no --spec interface"}
    completed = subprocess.run(
        [sys.executable, str(script), "--spec", str(spec), "--target-root", str(package_root)],
        cwd=package_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return {
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def run_claude_plugin_validate(package_root: Path, claude_bin: str, skip: bool, require: bool) -> Dict[str, Any]:
    if skip:
        return {"status": "SKIPPED", "reason": "skip flag set"}
    binary = shutil.which(claude_bin)
    if not binary:
        return {"status": "FAIL" if require else "SKIPPED", "reason": f"Claude binary not found: {claude_bin}"}
    completed = subprocess.run(
        [binary, "plugin", "validate", str(package_root)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return {
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def validate_package(
    package_root: Path,
    run_root: Path,
    *,
    repo_mode: str,
    claude_bin: str,
    skip_claude: bool,
    require_claude: bool,
) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    checks: List[Dict[str, Any]] = []

    def check(name: str, passed: bool, detail: str, *, warning: bool = False) -> None:
        checks.append({"name": name, "status": "PASS" if passed else ("WARN" if warning else "FAIL"), "detail": detail})
        if not passed:
            if warning:
                warnings.append(detail)
            else:
                errors.append(detail)

    check("package_root_exists", package_root.exists(), f"package root: {package_root}")
    plugin_json = load_json(package_root / ".claude-plugin" / "plugin.json")
    marketplace_json = load_json(package_root / ".claude-plugin" / "marketplace.json")
    publish_meta = load_json(package_root / ".claude-plugin" / "workflowprogram-publish.json")
    check("plugin_json_present", bool(plugin_json), ".claude-plugin/plugin.json")
    author_name = str(plugin_json.get("author", {}).get("name", "") if isinstance(plugin_json.get("author"), dict) else "").strip()
    check("plugin_author_not_placeholder", bool(author_name and "<" not in author_name and ">" not in author_name), f"author={author_name or '<missing>'}")
    if repo_mode == "existing_marketplace":
        check("marketplace_json_deferred_to_existing_checkout", not bool(marketplace_json), "existing marketplace packages do not replace marketplace.json")
    else:
        check("marketplace_json_present", bool(marketplace_json), ".claude-plugin/marketplace.json")
        owner_name = str(marketplace_json.get("owner", {}).get("name", "") if isinstance(marketplace_json.get("owner"), dict) else "").strip()
        check("marketplace_owner_not_placeholder", bool(owner_name and "<" not in owner_name and ">" not in owner_name), f"owner={owner_name or '<missing>'}")
    check("publish_metadata_present", bool(publish_meta), ".claude-plugin/workflowprogram-publish.json")

    plugin_id = str(plugin_json.get("name", "")).strip()
    if repo_mode != "existing_marketplace":
        marketplace_plugins = marketplace_json.get("plugins", [])
        marketplace_name = ""
        if isinstance(marketplace_plugins, list) and marketplace_plugins and isinstance(marketplace_plugins[0], dict):
            marketplace_name = str(marketplace_plugins[0].get("name", "")).strip()
        check("marketplace_plugin_matches_manifest", bool(plugin_id and plugin_id == marketplace_name), f"plugin={plugin_id}; marketplace={marketplace_name}")
    check("publish_metadata_repo_mode_matches", str(publish_meta.get("repo_mode", repo_mode)).strip() == repo_mode, f"repo_mode={repo_mode}")

    commands = list((package_root / "commands").glob("*.md")) if (package_root / "commands").exists() else []
    skills = list((package_root / "skills").glob("*/SKILL.md")) if (package_root / "skills").exists() else []
    check("public_entry_assets_present", bool(commands or skills), f"commands={len(commands)} skills={len(skills)}")

    suspicious_files = [
        path.relative_to(package_root).as_posix()
        for path in sorted(package_root.rglob("*"))
        if path.is_file() and should_exclude(path)
    ]
    check("no_cache_or_transient_files", not suspicious_files, f"suspicious files={suspicious_files or ['<none>']}")

    settings = load_json(package_root / ".claude" / "settings.json")
    if settings:
        stale_settings = [path for path in iter_settings_paths(settings) if path.startswith(".claude/")]
        missing_settings = [
            path
            for path in iter_settings_paths(settings)
            if not path.startswith(".claude/") and not (package_root / path).exists()
        ]
        check("settings_use_package_layout", not stale_settings, f"stale .claude settings paths={stale_settings or ['<none>']}")
        check("settings_paths_exist", not missing_settings, f"missing settings paths={missing_settings or ['<none>']}")

    runtime_mode = str(publish_meta.get("runtime_mode", "")).strip()
    check("runtime_mode_declared", runtime_mode in {"workflowprogram_dependency", "vendored_runtime"}, f"runtime_mode={runtime_mode or '<missing>'}")
    if runtime_mode == "workflowprogram_dependency":
        readme_text = (package_root / ".claude-plugin" / "README.md").read_text(encoding="utf-8") if (package_root / ".claude-plugin" / "README.md").exists() else ""
        check("workflowprogram_dependency_instructions", "workflowprogram-cn@logic70-plugins" in readme_text, "README includes WorkflowProgram dependency install instructions")
    if runtime_mode == "vendored_runtime":
        required = [
            "bin/workflowprogram-python",
            "scripts/workflow-runner.py",
            "scripts/validate-run-state.py",
            "scripts/target-workflow-runner.py",
            "scripts/validate-target-runtime-state.py",
            "scripts/target-runtime-finalizer.py",
            "scripts/validate-target-publish-state.py",
            "scripts/validate-workflow-spec.py",
        ]
        missing = [rel for rel in required if not (package_root / rel).exists()]
        check("vendored_runtime_files_present", not missing, f"missing vendored files={missing or ['<none>']}")

    target_runtime = package_root / ".workflowprogram" / "runtime" / "runtime-manifest.json"
    check("target_runtime_manifest_present", target_runtime.exists(), ".workflowprogram/runtime/runtime-manifest.json")
    target_design = package_root / ".workflowprogram" / "design" / "workflow-spec.yaml"
    check("target_design_spec_present", target_design.exists(), ".workflowprogram/design/workflow-spec.yaml")

    local_refs = collect_local_references(package_root)
    missing_refs = []
    for source, ref in local_refs:
        resolved = package_rel_for_reference(ref)
        path = package_root / resolved
        if not path.exists():
            missing_refs.append({"source": source, "ref": ref, "resolved": resolved})
    check("local_references_resolve", not missing_refs, f"missing local references={missing_refs or ['<none>']}")

    dependencies = runtime_dependencies(package_root)
    if dependencies:
        requirements_path = package_root / "requirements.txt"
        requirements_text = requirements_path.read_text(encoding="utf-8") if requirements_path.exists() else ""
        readme_text = (package_root / ".claude-plugin" / "README.md").read_text(encoding="utf-8") if (package_root / ".claude-plugin" / "README.md").exists() else ""
        missing_requirements = [package for package in dependencies if package not in requirements_text]
        missing_readme_mentions = [package for package in dependencies if package not in readme_text]
        check("python_requirements_present", requirements_path.exists() and not missing_requirements, f"missing requirements packages={missing_requirements or ['<none>']}")
        check("python_dependency_readme_mentions", "requirements.txt" in readme_text and not missing_readme_mentions, f"missing README dependency mentions={missing_readme_mentions or ['<none>']}")

    target_validator = run_target_spec_validator_if_available(package_root)
    if target_validator.get("status") == "FAIL":
        check("target_runtime_spec_validation", False, str(target_validator.get("stderr") or target_validator.get("stdout") or "target runtime validator failed"))
    elif target_validator.get("status") == "SKIPPED":
        check("target_runtime_spec_validation", False, str(target_validator.get("reason", "skipped")), warning=True)
    else:
        check("target_runtime_spec_validation", True, "target runtime validator accepted package layout")

    claude_validate = run_claude_plugin_validate(package_root, claude_bin, skip_claude, require_claude)
    if claude_validate.get("status") == "FAIL":
        check("claude_plugin_validate", False, str(claude_validate.get("stderr") or claude_validate.get("stdout") or claude_validate.get("reason")))
    elif claude_validate.get("status") == "SKIPPED":
        check("claude_plugin_validate", False, str(claude_validate.get("reason", "skipped")), warning=True)
    else:
        check("claude_plugin_validate", True, "claude plugin validate passed")

    payload = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "package_root": str(package_root),
        "checks": checks,
        "claude_plugin_validate": claude_validate,
        "target_runtime_spec_validation": target_validator,
        "local_reference_count": len(local_refs),
    }
    write_json(run_root / PUBLISH_DIR / "plugin-validation-report.json", payload)
    return payload


def main() -> int:
    args = parse_args()
    payload = validate_package(
        Path(args.package_root).resolve(),
        Path(args.run_root).resolve(),
        repo_mode=args.repo_mode,
        claude_bin=args.claude_bin,
        skip_claude=args.skip_claude_validate,
        require_claude=args.require_claude_validate,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"[{payload['status']}] {payload['package_root']}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
