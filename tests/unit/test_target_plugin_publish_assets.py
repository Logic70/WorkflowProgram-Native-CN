#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = ROOT / ".claude" / "scripts"


def run_json(*args: str, expect: int = 0) -> dict:
    completed = subprocess.run(
        [sys.executable, *args, "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != expect:
        raise AssertionError(
            f"expected exit {expect}, got {completed.returncode}\nstdout={completed.stdout}\nstderr={completed.stderr}"
        )
    payload = json.loads(completed.stdout)
    if not isinstance(payload, dict):
        raise AssertionError("expected JSON object")
    return payload


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def seed_target(target: Path, *, missing_reference: bool = False) -> None:
    write_json(
        target / ".claude" / "settings.json",
        {
            "commands": {"demo": ".claude/commands/demo.md"},
            "skills": {"demo-skill": ".claude/skills/demo-skill/SKILL.md"},
            "agents": {"demo-agent": ".claude/agents/demo-agent.md"},
        },
    )
    missing_line = "\n- Missing helper: `config/scripts/missing-helper.py`" if missing_reference else ""
    write_text(
        target / ".claude" / "commands" / "demo.md",
        "---\ndescription: Demo command\n---\n\n"
        "Use `config/scripts/render.py`, `templates/report.html`, and `.workflowprogram/loops/report-render.md`."
        f"{missing_line}\n",
    )
    write_text(
        target / ".claude" / "skills" / "demo-skill" / "SKILL.md",
        "---\nname: demo-skill\ndescription: Demo skill\n---\n\nRead `config/data.json`.\n",
    )
    write_text(target / ".claude" / "agents" / "demo-agent.md", "# Demo Agent\n\nUse `templates/report.html`.\n")
    write_text(target / "CLAUDE.md", "# Demo\n\nSupport files live in `config/` and `templates/`.\n")
    write_text(target / "config" / "scripts" / "render.py", "print('render')\n")
    write_text(target / "config" / "data.json", "{}\n")
    write_text(target / "config" / "scripts" / "__pycache__" / "render.cpython-313.pyc", "cache\n")
    write_text(target / "templates" / "report.html", "<html></html>\n")
    write_text(target / ".workflowprogram" / "loops" / "report-render.md", "# Report Loop\n")
    write_text(
        target / ".workflowprogram" / "design" / "workflow-spec.yaml",
        "meta:\n"
        "  name: demo\n"
        "loop_policy:\n"
        "  prompt_package: .workflowprogram/loops/report-render.md\n",
    )
    write_text(target / ".workflowprogram" / "design" / "workflow-maintenance.md", "# Maintenance Guide\n")
    write_json(
        target / ".workflowprogram" / "runtime" / "runtime-manifest.json",
        {
            "dependencies": {"packages": ["jinja2", "pyyaml"]},
        },
    )
    write_text(
        target / ".workflowprogram" / "runtime" / "validate-run-state.py",
        "#!/usr/bin/env python3\n"
        "import argparse, sys\n"
        "from pathlib import Path\n"
        "p=argparse.ArgumentParser(); p.add_argument('--spec', required=True); p.add_argument('--target-root', default='.')\n"
        "a=p.parse_args(); root=Path(a.target_root)\n"
        "missing=[x for x in ['commands/demo.md','skills/demo-skill/SKILL.md','agents/demo-agent.md','templates/report.html'] if not (root/x).exists()]\n"
        "print('missing=' + ','.join(missing))\n"
        "sys.exit(1 if missing else 0)\n",
    )


def package_target_direct(target: Path, run_root: Path, *, plugin_id: str = "demo-plugin") -> dict:
    return run_json(
        str(SCRIPT_ROOT / "package-target-plugin.py"),
        "--target-root",
        str(target),
        "--run-root",
        str(run_root),
        "--plugin-id",
        plugin_id,
        "--plugin-name",
        "Demo Plugin",
        "--version",
        "0.1.0",
        "--repository-url",
        "https://github.com/example/demo-plugin",
    )


def validate_package(package_root: Path, run_root: Path, *, expect: int = 0) -> dict:
    return run_json(
        str(SCRIPT_ROOT / "validate-target-plugin-package.py"),
        "--package-root",
        str(package_root),
        "--run-root",
        str(run_root),
        "--skip-claude-validate",
        expect=expect,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="target-publish-assets-") as temp_dir:
        temp = Path(temp_dir)

        target = temp / "target"
        run_root = temp / "run"
        seed_target(target)
        package = package_target_direct(target, run_root)
        assert package["status"] == "PASS"
        package_root = Path(package["package_root"])
        marketplace = json.loads((package_root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        assert "$schema" not in marketplace
        assert "description" not in marketplace
        assert marketplace["name"] == "target-workflow-plugins"
        for rel in [
            "commands/demo.md",
            "skills/demo-skill/SKILL.md",
            "agents/demo-agent.md",
            "config/scripts/render.py",
            "templates/report.html",
            ".workflowprogram/loops/report-render.md",
            "requirements.txt",
        ]:
            assert (package_root / rel).exists(), rel
        assert not (package_root / "config/scripts/__pycache__/render.cpython-313.pyc").exists()

        settings = json.loads((package_root / ".claude/settings.json").read_text(encoding="utf-8"))
        assert settings["commands"]["demo"] == "commands/demo.md"
        assert settings["skills"]["demo-skill"] == "skills/demo-skill/SKILL.md"
        assert settings["agents"]["demo-agent"] == "agents/demo-agent.md"
        validation = validate_package(package_root, run_root)
        assert validation["status"] == "PASS"

        bad_target = temp / "bad-target"
        bad_run = temp / "bad-run"
        seed_target(bad_target, missing_reference=True)
        bad_package = package_target_direct(bad_target, bad_run)
        bad_validation = validate_package(Path(bad_package["package_root"]), bad_run, expect=1)
        assert bad_validation["status"] == "FAIL"
        assert any("missing-helper.py" in error for error in bad_validation["errors"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
