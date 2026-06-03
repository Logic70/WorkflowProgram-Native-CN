#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely clean WorkflowProgram-owned caches and selected artifacts")
    parser.add_argument("--plugin-root", default="", help="Override CLAUDE_PLUGIN_ROOT")
    parser.add_argument("--plugin-data", default="", help="Override CLAUDE_PLUGIN_DATA")
    parser.add_argument("--repo-root", default="", help=argparse.SUPPRESS)
    parser.add_argument("--target-root", default="", help="Target workflow root for run-history pruning")
    parser.add_argument("--python-runtime", action="store_true", help="Clean plugin-local Python dependency cache")
    parser.add_argument("--test-artifacts", action="store_true", help="Clean repository test transcripts and bytecode")
    parser.add_argument("--run-history", action="store_true", help="Prune TARGET_ROOT/.workflowprogram/runs")
    parser.add_argument("--keep-last", type=int, default=None, help="Keep the newest N run directories")
    parser.add_argument("--older-than-days", type=int, default=None, help="Delete runs older than N days")
    parser.add_argument("--apply", action="store_true", help="Delete planned items instead of dry-run reporting")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    return parser.parse_args()


def resolve_optional(value: str, env_name: str = "") -> Path | None:
    raw = value.strip() or (os.environ.get(env_name, "").strip() if env_name else "")
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return total
    for child in path.rglob("*"):
        if child.is_file() and not child.is_symlink():
            total += file_size(child)
    return total


def path_size(path: Path) -> int:
    if path.is_file() and not path.is_symlink():
        return file_size(path)
    if path.is_dir() and not path.is_symlink():
        return dir_size(path)
    return 0


def add_item(
    items: List[Dict[str, Any]],
    *,
    kind: str,
    path: Path,
    action: str,
    status: str,
    reason: str,
    size_bytes: int | None = None,
    message: str = "",
) -> None:
    entry: Dict[str, Any] = {
        "kind": kind,
        "path": str(path),
        "action": action,
        "status": status,
        "reason": reason,
    }
    if size_bytes is not None:
        entry["size_bytes"] = size_bytes
    if message:
        entry["message"] = message
    items.append(entry)


def delete_path(path: Path) -> tuple[bool, str]:
    try:
        if path.is_symlink():
            return False, "refusing to delete symlink"
        if path.is_dir():
            shutil.rmtree(path)
            return True, "deleted directory"
        if path.exists():
            path.unlink()
            return True, "deleted file"
        return False, "path no longer exists"
    except Exception as exc:
        return False, str(exc)


def plan_or_apply_delete(
    items: List[Dict[str, Any]],
    *,
    kind: str,
    path: Path,
    root: Path,
    reason: str,
    apply: bool,
) -> None:
    resolved = path.resolve()
    resolved_root = root.resolve()
    if not is_relative_to(resolved, resolved_root):
        add_item(items, kind=kind, path=resolved, action="delete", status="skipped", reason=reason, message="outside allowed root")
        return
    if resolved.is_symlink():
        add_item(items, kind=kind, path=resolved, action="delete", status="skipped", reason=reason, message="refusing to delete symlink")
        return
    if not resolved.exists():
        return
    size = path_size(resolved)
    if not apply:
        add_item(items, kind=kind, path=resolved, action="delete", status="planned", reason=reason, size_bytes=size)
        return
    ok, message = delete_path(resolved)
    add_item(
        items,
        kind=kind,
        path=resolved,
        action="delete",
        status="deleted" if ok else "error",
        reason=reason,
        size_bytes=size,
        message=message,
    )


def collect_python_runtime(items: List[Dict[str, Any]], plugin_data: Path | None, *, apply: bool) -> None:
    if plugin_data is None:
        add_item(
            items,
            kind="python_runtime",
            path=Path("${CLAUDE_PLUGIN_DATA}"),
            action="delete",
            status="skipped",
            reason="plugin data is not configured",
        )
        return
    python_root = plugin_data / "python"
    for relative in ("site-packages", "site-packages.tmp", "bootstrap-state.json", "requirements.lock.txt"):
        plan_or_apply_delete(
            items,
            kind="python_runtime",
            path=python_root / relative,
            root=python_root,
            reason="plugin-local Python runtime cache",
            apply=apply,
        )


def iter_bytecode_paths(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("__pycache__")):
        if path.is_dir():
            yield path
    for path in sorted(root.rglob("*.pyc")):
        if path.is_file():
            yield path


def collect_test_artifacts(items: List[Dict[str, Any]], root: Path, *, apply: bool) -> None:
    tests_root = root / "tests"
    transcripts_root = tests_root / "transcripts"
    if transcripts_root.exists():
        for child in sorted(transcripts_root.iterdir()):
            if child.is_dir() and child.name.startswith("20"):
                plan_or_apply_delete(
                    items,
                    kind="test_artifact",
                    path=child,
                    root=transcripts_root,
                    reason="timestamped runtime smoke transcript",
                    apply=apply,
                )
    for path in iter_bytecode_paths(root):
        plan_or_apply_delete(
            items,
            kind="python_bytecode",
            path=path,
            root=root,
            reason="rebuildable Python bytecode cache",
            apply=apply,
        )


def run_sort_key(path: Path) -> float:
    summary_path = path / "runner-summary.json"
    for candidate in (summary_path, path / "state.json"):
        if not candidate.exists():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        for key in ("completed_at", "generated_at", "started_at", "created_at"):
            value = str(payload.get(key, "")).strip()
            if not value:
                continue
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                continue
    try:
        return path.stat().st_mtime
    except OSError:
        return 0


def collect_run_history(
    items: List[Dict[str, Any]],
    target_root: Path | None,
    *,
    keep_last: int | None,
    older_than_days: int | None,
    apply: bool,
) -> None:
    if target_root is None:
        add_item(
            items,
            kind="run_history",
            path=Path("${TARGET_ROOT}"),
            action="delete",
            status="skipped",
            reason="target root is required for run-history pruning",
        )
        return
    if keep_last is None and older_than_days is None:
        add_item(
            items,
            kind="run_history",
            path=target_root / ".workflowprogram" / "runs",
            action="delete",
            status="skipped",
            reason="run-history pruning requires --keep-last or --older-than-days",
        )
        return
    if keep_last is not None and keep_last < 1:
        add_item(
            items,
            kind="run_history",
            path=target_root / ".workflowprogram" / "runs",
            action="delete",
            status="skipped",
            reason="--keep-last must be at least 1",
        )
        return

    runs_root = target_root / ".workflowprogram" / "runs"
    if not runs_root.exists():
        add_item(items, kind="run_history", path=runs_root, action="delete", status="skipped", reason="runs directory is missing")
        return

    runs = [path for path in runs_root.iterdir() if path.is_dir()]
    sorted_runs = sorted(runs, key=run_sort_key, reverse=True)
    keep_names = {path.name for path in sorted_runs[: max(keep_last or 1, 1)]}
    if sorted_runs:
        keep_names.add(sorted_runs[0].name)
    cutoff = None
    if older_than_days is not None:
        if older_than_days < 0:
            add_item(
                items,
                kind="run_history",
                path=runs_root,
                action="delete",
                status="skipped",
                reason="--older-than-days must be non-negative",
            )
            return
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).timestamp()

    for run in sorted_runs:
        if run.name in keep_names:
            add_item(items, kind="run_history", path=run.resolve(), action="delete", status="skipped", reason="retained by newest/keep-last policy")
            continue
        if cutoff is not None and run_sort_key(run) >= cutoff:
            add_item(items, kind="run_history", path=run.resolve(), action="delete", status="skipped", reason="newer than older-than-days cutoff")
            continue
        plan_or_apply_delete(
            items,
            kind="run_history",
            path=run,
            root=runs_root,
            reason="run history outside retention policy",
            apply=apply,
        )


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def summarize(items: List[Dict[str, Any]]) -> Dict[str, int]:
    return {
        "planned_delete_count": sum(1 for item in items if item.get("status") == "planned"),
        "deleted_count": sum(1 for item in items if item.get("status") == "deleted"),
        "skipped_count": sum(1 for item in items if item.get("status") == "skipped"),
        "error_count": sum(1 for item in items if item.get("status") == "error"),
    }


def explicit_scopes(args: argparse.Namespace) -> List[str]:
    scopes: List[str] = []
    if args.python_runtime:
        scopes.append("python_runtime")
    if args.test_artifacts:
        scopes.append("test_artifacts")
    if args.run_history:
        scopes.append("run_history")
    return scopes


def default_scopes(args: argparse.Namespace) -> List[str]:
    scopes = explicit_scopes(args)
    if scopes:
        return scopes
    return ["python_runtime", "test_artifacts", "run_history"]


def main() -> int:
    args = parse_args()
    root = resolve_optional(args.repo_root) or default_repo_root()
    plugin_data = resolve_optional(args.plugin_data, "CLAUDE_PLUGIN_DATA")
    target_root = resolve_optional(args.target_root, "TARGET_ROOT")
    has_explicit_scope = bool(explicit_scopes(args))
    scopes = default_scopes(args)
    should_apply = args.apply and has_explicit_scope
    items: List[Dict[str, Any]] = []

    if "python_runtime" in scopes:
        collect_python_runtime(items, plugin_data, apply=should_apply)
    if "test_artifacts" in scopes:
        collect_test_artifacts(items, root, apply=should_apply)
    if "run_history" in scopes:
        collect_run_history(
            items,
            target_root,
            keep_last=args.keep_last,
            older_than_days=args.older_than_days,
            apply=should_apply,
        )

    payload = {
        "generated_at": iso_now(),
        "dry_run": not should_apply,
        "scopes": scopes,
        "items": items,
        "summary": summarize(items),
    }

    run_root = resolve_optional("", "RUN_ROOT")
    if run_root:
        write_json(run_root / "outputs" / "stages" / "cache-cleanup-report.json", payload)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for item in items:
            print(f"[{item['status'].upper()}] {item['kind']} {item['action']} {item['path']} - {item['reason']}")
        print(json.dumps(payload["summary"], ensure_ascii=False))
    return 1 if payload["summary"]["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
