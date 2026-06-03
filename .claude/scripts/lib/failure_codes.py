from __future__ import annotations


FAILURE_KIND_BY_CODE = {
    "": "none",
    "CONFLICT": "conflict",
    "CONFLICT_FAILURE": "conflict",
    "CLAUDE_NOT_LOGGED_IN": "environment",
    "CLAUDE_NOT_AVAILABLE": "environment",
    "RUNTIME_HOST_NOT_READY": "environment",
    "RUNTIME_HOST_MISSING": "environment",
    "TARGET_NOT_WRITABLE": "environment",
    "HOST_CAPABILITY_MISSING": "environment",
    "HOST_CAPABILITY_DEGRADED": "environment",
    "STRUCTURE_FAILURE": "design",
    "MISSING_ARGUMENT": "design",
    "INPUT_FAILURE": "design",
    "CHANGE_POLICY_FAILURE": "design",
    "CHANGE_POLICY_REQUIRED": "design",
    "CHANGE_POLICY_INVALID": "design",
    "CHANGE_CONTEXT_STALE": "design",
    "CHANGE_APPROVAL_MISSING": "design",
    "TEAM_CONTRACT_FAILURE": "design",
    "TEAM_ORCHESTRATION_FAILURE": "implementation",
    "RUNTIME_FAILURE": "implementation",
    "EVIDENCE_FAILURE": "implementation",
}


def failure_kind_from_code(failure_code: str) -> str:
    """Map a failure_code to the coarse failure_kind taxonomy."""

    normalized = failure_code.strip().upper()
    return FAILURE_KIND_BY_CODE.get(normalized, "implementation")


def failure_kind_for_result(result: str, failure_code: str) -> str:
    """Map a runtime verdict and failure_code to the coarse failure_kind taxonomy."""

    normalized_result = result.strip().upper()
    if normalized_result == "PASS":
        return "none"
    if normalized_result == "ENVIRONMENT-SKIP":
        return "environment"
    return failure_kind_from_code(failure_code)
