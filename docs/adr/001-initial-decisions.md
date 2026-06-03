# Architecture Decision Records

## ADR-001: One-Way Build from .claude/ to Root-Level

**Status**: Accepted

**Context**: 
WorkflowProgram initially had bidirectional sync between `.claude/` and root-level directories, causing state drift and confusion.

**Decision**:
Implement one-way build where `.claude/` is the single source of truth, and root-level directories are generated outputs.

**Consequences**:
- (+) Eliminates state drift
- (+) Clear editing guidelines (edit `.claude/` only)
- (-) Requires build step before Plugin mode works
- (-) Generated files must not be edited directly

---

## ADR-002: Dual-Track Output (YAML + Markdown)

**Status**: Accepted

**Context**:
Pure Markdown design documents rely on LLM's context memory for state management, which is unreliable for complex workflows with loops.

**Decision**:
Implement dual-track output:
1. `workflow-spec.yaml` - Machine-readable, single source of truth
2. `workflow-view.md` - Human-readable, generated from YAML

**Consequences**:
- (+) Precise state machine constraints
- (+) Prevents infinite loops via max_retries
- (+) Human-friendly views without editing risks
- (-) Slightly more complex workflow

---

## ADR-003: Turn Count Limits with Strict Mode

**Status**: Accepted

**Context**:
Physical time timeouts are inefficient. Token usage correlates with turn count, not wall time.

**Decision**:
Use turn count limits with optional strict mode:
- Default: S=50, M=100, L=200, XL=300 turns
- Strict: S=20, M=50, L=100, XL=150 turns

**Consequences**:
- (+) More efficient resource usage
- (+) Forces optimization in strict mode
- (-) May terminate valid long-running workflows if limits too tight

---

## ADR-004: CI/CD Auto-Approve Mode

**Status**: Accepted

**Context**:
Interactive gates block automated pipelines.

**Decision**:
Support `--auto-approve` flag and `CI=true` environment variable to skip confirmation gates.

**Consequences**:
- (+) Enables fully automated workflows
- (+) Backward compatible (default still interactive)
- (-) Less safe in CI (no human review)

---

## Future Considerations

### Native Plugin Structure
**Status**: Proposed

Migrate from `.claude/` structure to root-level native plugin structure when Claude Code fully supports it.

### External FSM Runner
**Status**: Under Discussion

Allow `workflow-spec.yaml` to be executed by external state machine runners, not just Claude Code.
