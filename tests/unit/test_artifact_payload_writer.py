from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WRITER = ROOT / ".claude" / "scripts" / "artifact-payload-writer.py"
MASK_KEY = 173


def masked_base64(data: bytes, byte_offset: int = 0) -> str:
    masked = bytes(
        byte ^ ((MASK_KEY + byte_offset + index) & 0xFF)
        for index, byte in enumerate(data)
    )
    return base64.b64encode(masked).decode("ascii")


def write_transcript(projects_dir: Path, payload: dict) -> None:
    transcript = (
        projects_dir
        / "D--Code-FreeSTRIDE"
        / "session-001"
        / "subagents"
        / "workflows"
        / "wf_001"
        / "agent-artifact.jsonl"
    )
    transcript.parent.mkdir(parents=True, exist_ok=True)
    marker = (
        f"---BEGIN_ARTIFACT_PAYLOAD {payload['payload_id']}---\n"
        f"{json.dumps(payload)}\n"
        f"---END_ARTIFACT_PAYLOAD {payload['payload_id']}---"
    )
    with transcript.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"message": {"content": [{"text": marker}]}}) + "\n")


def run_writer(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(WRITER), *args],
        cwd=tmp_path / "FreeSTRIDE",
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_artifact_payload_writer_writes_and_appends_from_transcript_marker(tmp_path: Path) -> None:
    project = tmp_path / "FreeSTRIDE"
    project.mkdir()
    projects_dir = tmp_path / "claude-projects"
    target = project / "outputs" / "stride-audit" / "dfd.yaml"
    first = b'{"run_id":"device-auth"}'
    second = b"\n"
    write_transcript(
        projects_dir,
        {
            "payload_id": "apw-1-0-first",
            "target_file": str(target),
            "operation": "write",
            "chunk_index": 1,
            "chunk_count": 2,
            "byte_offset": 0,
            "mask_key": MASK_KEY,
            "base64": masked_base64(first, 0),
        },
    )
    write_transcript(
        projects_dir,
        {
            "payload_id": "apw-2-n-second",
            "target_file": str(target),
            "operation": "append",
            "chunk_index": 2,
            "chunk_count": 2,
            "byte_offset": len(first),
            "mask_key": MASK_KEY,
            "base64": masked_base64(second, len(first)),
        },
    )

    first_result = run_writer(
        tmp_path,
        "--payload-id",
        "apw-1-0-first",
        "--target-file",
        str(target),
        "--operation",
        "write",
        "--byte-offset",
        "0",
        "--mask-key",
        str(MASK_KEY),
        "--claude-projects-dir",
        str(projects_dir),
    )
    assert first_result.returncode == 0, first_result.stderr or first_result.stdout
    second_result = run_writer(
        tmp_path,
        "--payload-id",
        "apw-2-n-second",
        "--target-file",
        str(target),
        "--operation",
        "append",
        "--byte-offset",
        str(len(first)),
        "--mask-key",
        str(MASK_KEY),
        "--claude-projects-dir",
        str(projects_dir),
    )
    assert second_result.returncode == 0, second_result.stderr or second_result.stdout
    assert target.read_bytes() == first + second


def test_artifact_payload_writer_rejects_target_mismatch(tmp_path: Path) -> None:
    project = tmp_path / "FreeSTRIDE"
    project.mkdir()
    projects_dir = tmp_path / "claude-projects"
    target = project / "outputs" / "stride-audit" / "dfd.yaml"
    write_transcript(
        projects_dir,
        {
            "payload_id": "apw-mismatch",
            "target_file": str(target),
            "operation": "write",
            "chunk_index": 1,
            "chunk_count": 1,
            "byte_offset": 0,
            "mask_key": MASK_KEY,
            "base64": masked_base64(b"{}"),
        },
    )

    result = run_writer(
        tmp_path,
        "--payload-id",
        "apw-mismatch",
        "--target-file",
        str(project / "outputs" / "stride-audit" / "other.json"),
        "--operation",
        "write",
        "--byte-offset",
        "0",
        "--mask-key",
        str(MASK_KEY),
        "--claude-projects-dir",
        str(projects_dir),
    )
    assert result.returncode != 0
    assert "target_file mismatch" in (result.stderr + result.stdout)


def test_artifact_payload_writer_writes_complete_file_from_file_id(tmp_path: Path) -> None:
    project = tmp_path / "FreeSTRIDE"
    project.mkdir()
    projects_dir = tmp_path / "claude-projects"
    target = project / "outputs" / "stride-audit" / "threat_list.json"
    chunks = [b'{"run_id":"device-auth",', b'"threats":[{"id":"T-1"}]', b"}\n"]
    file_id = "apwf-3-complete"
    offset = 0
    for index, chunk in enumerate(chunks, start=1):
        write_transcript(
            projects_dir,
            {
                "payload_id": f"apw-{index}",
                "file_id": file_id,
                "target_file": str(target),
                "operation": "write" if index == 1 else "append",
                "chunk_index": index,
                "chunk_count": len(chunks),
                "byte_offset": offset,
                "mask_key": MASK_KEY,
                "base64": masked_base64(chunk, offset),
            },
        )
        offset += len(chunk)

    result = run_writer(
        tmp_path,
        "--file-id",
        file_id,
        "--target-file",
        str(target),
        "--operation",
        "write-file",
        "--chunk-count",
        str(len(chunks)),
        "--mask-key",
        str(MASK_KEY),
        "--claude-projects-dir",
        str(projects_dir),
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert json.loads(target.read_text(encoding="utf-8"))["run_id"] == "device-auth"
