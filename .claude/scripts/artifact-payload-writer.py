#!/usr/bin/env python3
"""Write WPN artifact payloads from transcript markers.

Generated workflow subagents are reliable at copying a short command, but not
long base64 payloads or long command sequences. The generator therefore puts
the payload chunks in the agent prompt and emits one guarded command that calls
this helper with a file id. This script finds the matching prompt markers in
the Claude transcript, decodes the byte-masked base64 chunks, and writes the
complete artifact bytes.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable


BEGIN_TEMPLATE = r"---BEGIN_ARTIFACT_PAYLOAD {payload_id}---"
END_TEMPLATE = r"---END_ARTIFACT_PAYLOAD {payload_id}---"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload-id", default=None)
    parser.add_argument("--file-id", default=None)
    parser.add_argument("--target-file", required=True)
    parser.add_argument("--operation", choices=("write", "append", "write-file"), required=True)
    parser.add_argument("--byte-offset", type=int, default=0)
    parser.add_argument("--chunk-count", type=int, default=None)
    parser.add_argument("--mask-key", type=int, required=True)
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--claude-projects-dir", default=None)
    parser.add_argument("--max-age-seconds", type=int, default=7 * 24 * 60 * 60)
    args = parser.parse_args()
    if bool(args.payload_id) == bool(args.file_id):
        parser.error("provide exactly one of --payload-id or --file-id")
    if args.file_id and args.operation != "write-file":
        parser.error("--file-id requires --operation write-file")
    if args.payload_id and args.operation == "write-file":
        parser.error("--payload-id does not support --operation write-file")
    return args


def normalize_path_text(value: str) -> str:
    text = str(value).replace("\\", "/").rstrip("/")
    return text.lower() if os.name == "nt" else text


def encoded_claude_project_name(path: Path) -> str:
    text = str(path.resolve())
    return re.sub(r"[\\/]+", "-", text.replace(":", "")).strip("-")


def existing_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.exists() else None


def claude_project_dirs(project_root: Path, projects_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    for env_name in ("CLAUDE_PROJECT_DIR", "CLAUDE_CODE_PROJECT_DIR"):
        path = existing_path(os.environ.get(env_name))
        if path:
            candidates.append(path)
    encoded = projects_dir / encoded_claude_project_name(project_root)
    if encoded.exists():
        candidates.append(encoded)
    if projects_dir.exists():
        candidates.extend(path for path in projects_dir.iterdir() if path.is_dir())

    seen: set[str] = set()
    result: list[Path] = []
    for path in candidates:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def transcript_candidates(project_root: Path, projects_dir: Path, max_age_seconds: int) -> list[Path]:
    candidates: list[Path] = []
    for env_name in (
        "CLAUDE_TRANSCRIPT_PATH",
        "CLAUDE_AGENT_TRANSCRIPT_PATH",
        "CLAUDE_CODE_TRANSCRIPT_PATH",
    ):
        path = existing_path(os.environ.get(env_name))
        if path and path.is_file():
            candidates.append(path)

    cutoff = time.time() - max_age_seconds if max_age_seconds > 0 else None
    for project_dir in claude_project_dirs(project_root, projects_dir):
        if not project_dir.exists():
            continue
        patterns = (
            "*.jsonl",
            "*/subagents/workflows/*/agent-*.jsonl",
            "*/subagents/workflows/*/*.jsonl",
        )
        for pattern in patterns:
            for path in project_dir.glob(pattern):
                if not path.is_file():
                    continue
                try:
                    if cutoff is not None and path.stat().st_mtime < cutoff:
                        continue
                except OSError:
                    continue
                candidates.append(path)

    seen: set[str] = set()
    unique: list[Path] = []
    for path in candidates:
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(path)
    unique.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
    return unique


def strings_from_json(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from strings_from_json(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings_from_json(item)


def payload_from_text(text: str, payload_id: str) -> dict[str, Any] | None:
    begin = re.escape(BEGIN_TEMPLATE.format(payload_id=payload_id))
    end = re.escape(END_TEMPLATE.format(payload_id=payload_id))
    pattern = re.compile(begin + r"\n(?P<body>[\s\S]*?)\n" + end)
    match = pattern.search(text)
    if not match:
        return None
    try:
        payload = json.loads(match.group("body"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid artifact payload marker JSON for {payload_id}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid artifact payload marker for {payload_id}: expected JSON object")
    return payload


def payload_markers_from_text(text: str) -> Iterable[dict[str, Any]]:
    pattern = re.compile(
        r"---BEGIN_ARTIFACT_PAYLOAD (?P<payload_id>[^\n]+)---\n"
        r"(?P<body>[\s\S]*?)\n"
        r"---END_ARTIFACT_PAYLOAD (?P=payload_id)---"
    )
    for match in pattern.finditer(text):
        try:
            payload = json.loads(match.group("body"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            yield payload


def find_payload(transcripts: Iterable[Path], payload_id: str) -> tuple[dict[str, Any], Path]:
    for transcript in transcripts:
        try:
            with transcript.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        payload = payload_from_text(line, payload_id)
                        if payload is not None:
                            return payload, transcript
                        continue
                    for text in strings_from_json(item):
                        payload = payload_from_text(text, payload_id)
                        if payload is not None:
                            return payload, transcript
        except OSError:
            continue
    raise SystemExit(f"Artifact payload marker not found: {payload_id}")


def find_file_payloads(transcripts: Iterable[Path], file_id: str, chunk_count: int) -> tuple[list[dict[str, Any]], Path]:
    chunks: dict[int, dict[str, Any]] = {}
    source_transcript: Path | None = None
    for transcript in transcripts:
        try:
            with transcript.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    texts: list[str]
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        texts = [line]
                    else:
                        texts = list(strings_from_json(item))
                    for text in texts:
                        for payload in payload_markers_from_text(text):
                            if str(payload.get("file_id") or "") != file_id:
                                continue
                            chunk_index = int(payload.get("chunk_index") or 0)
                            if 1 <= chunk_index <= chunk_count and chunk_index not in chunks:
                                chunks[chunk_index] = payload
                                source_transcript = transcript
                                if len(chunks) == chunk_count:
                                    return [chunks[index] for index in range(1, chunk_count + 1)], transcript
        except OSError:
            continue
    missing = [index for index in range(1, chunk_count + 1) if index not in chunks]
    location = f" in {source_transcript}" if source_transcript else ""
    raise SystemExit(f"Artifact file payload markers not found for {file_id}{location}; missing chunks: {missing[:20]}")


def require_payload_value(payload: dict[str, Any], key: str) -> Any:
    if key not in payload:
        raise SystemExit(f"Artifact payload marker missing key: {key}")
    return payload[key]


def validate_payload(payload: dict[str, Any], args: argparse.Namespace) -> None:
    if str(require_payload_value(payload, "payload_id")) != args.payload_id:
        raise SystemExit("Artifact payload id mismatch")
    if normalize_path_text(str(require_payload_value(payload, "target_file"))) != normalize_path_text(args.target_file):
        raise SystemExit("Artifact payload target_file mismatch")
    if str(require_payload_value(payload, "operation")) != args.operation:
        raise SystemExit("Artifact payload operation mismatch")
    if int(require_payload_value(payload, "byte_offset")) != args.byte_offset:
        raise SystemExit("Artifact payload byte_offset mismatch")
    if int(require_payload_value(payload, "mask_key")) != args.mask_key:
        raise SystemExit("Artifact payload mask_key mismatch")
    if not isinstance(require_payload_value(payload, "base64"), str):
        raise SystemExit("Artifact payload base64 must be a string")


def validate_file_payload(payload: dict[str, Any], args: argparse.Namespace, chunk_count: int) -> None:
    if str(require_payload_value(payload, "file_id")) != args.file_id:
        raise SystemExit("Artifact payload file_id mismatch")
    if normalize_path_text(str(require_payload_value(payload, "target_file"))) != normalize_path_text(args.target_file):
        raise SystemExit("Artifact payload target_file mismatch")
    if int(require_payload_value(payload, "chunk_count")) != chunk_count:
        raise SystemExit("Artifact payload chunk_count mismatch")
    if int(require_payload_value(payload, "mask_key")) != args.mask_key:
        raise SystemExit("Artifact payload mask_key mismatch")
    if not isinstance(require_payload_value(payload, "base64"), str):
        raise SystemExit("Artifact payload base64 must be a string")


def decode_payload(payload: dict[str, Any], byte_offset: int, mask_key: int) -> bytes:
    try:
        masked = base64.b64decode(str(payload["base64"]), validate=True)
    except Exception as exc:  # noqa: BLE001 - keep CLI error clear for hook logs
        raise SystemExit(f"Invalid artifact payload base64: {exc}") from exc
    return bytes(
        byte ^ ((mask_key + byte_offset + index) & 0xFF)
        for index, byte in enumerate(masked)
    )


def decode_file_payloads(payloads: list[dict[str, Any]], args: argparse.Namespace) -> bytes:
    chunks: list[bytes] = []
    expected_offset = 0
    for expected_index, payload in enumerate(payloads, start=1):
        validate_file_payload(payload, args, len(payloads))
        chunk_index = int(require_payload_value(payload, "chunk_index"))
        if chunk_index != expected_index:
            raise SystemExit(f"Artifact payload chunk_index mismatch: expected {expected_index}, got {chunk_index}")
        byte_offset = int(require_payload_value(payload, "byte_offset"))
        if byte_offset != expected_offset:
            raise SystemExit(
                f"Artifact payload byte_offset mismatch for chunk {chunk_index}: "
                f"expected {expected_offset}, got {byte_offset}"
            )
        chunk = decode_payload(payload, byte_offset, args.mask_key)
        chunks.append(chunk)
        expected_offset += len(chunk)
    return b"".join(chunks)


def write_payload(target_file: Path, operation: str, byte_offset: int, data: bytes) -> None:
    target_file.parent.mkdir(parents=True, exist_ok=True)
    if operation == "write":
        if byte_offset != 0:
            raise SystemExit("Write operation requires byte_offset=0")
        target_file.write_bytes(data)
        return
    if not target_file.exists():
        raise SystemExit(f"Append target does not exist: {target_file}")
    current_size = target_file.stat().st_size
    if current_size != byte_offset:
        raise SystemExit(
            f"Append byte_offset mismatch for {target_file}: expected {byte_offset}, got {current_size}"
        )
    with target_file.open("ab") as handle:
        handle.write(data)


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve() if args.project_root else Path.cwd().resolve()
    projects_dir = Path(args.claude_projects_dir).resolve() if args.claude_projects_dir else Path.home() / ".claude" / "projects"
    transcripts = transcript_candidates(project_root, projects_dir, args.max_age_seconds)
    target_file = Path(args.target_file)
    if args.file_id:
        if not args.chunk_count or args.chunk_count < 1:
            raise SystemExit("--chunk-count must be positive for --file-id")
        payloads, transcript = find_file_payloads(transcripts, args.file_id, args.chunk_count)
        data = decode_file_payloads(payloads, args)
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_bytes(data)
    else:
        payload, transcript = find_payload(transcripts, str(args.payload_id))
        validate_payload(payload, args)
        data = decode_payload(payload, args.byte_offset, args.mask_key)
        write_payload(target_file, args.operation, args.byte_offset, data)
    print(
        json.dumps(
            {
                "status": "PASS",
                "payload_id": args.payload_id,
                "file_id": args.file_id,
                "target_file": str(target_file),
                "operation": args.operation,
                "bytes": len(data),
                "transcript": str(transcript),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
