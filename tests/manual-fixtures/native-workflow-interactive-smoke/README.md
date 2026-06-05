# Native Workflow Interactive Smoke Fixture

M11 first-version host-side interactive smoke harness for Native Workflow JS.
The fixture documents manual execution steps, Windows-accessible JSONL recording,
Computer Use boundaries, evidence profiles, and future adapter extension points.

## Purpose

Verify that a Native Workflow JS control plane (a `.claude/workflows/*.js` file)
can be interactively executed through Claude Code's `Workflow({ scriptPath, args })`
and produce deterministically evaluable evidence.

## Computer Use Boundary

Current security rules prohibit automated terminal-app interaction. Therefore:

- **Supported**: Manual WSL login-shell execution + deterministic JSONL evaluation.
- **NOT supported**: Terminal clicking, keyboard injection, PowerShell SendKeys,
  Windows UI automation, or simulated execution results.
- **Deferred**: Computer Use terminal-driving adapter — deferred until an allowed
  non-terminal integration exists.

The `packet` subcommand generates execution instructions but does NOT execute
Claude Code. The `evaluate` subcommand deterministically reads captured JSONL
without executing any external process.

## Key Features

### Ultrawork Trigger

The `packet` subcommand's `suggestedPrompt` now begins with the `ultrawork`
keyword. This keyword triggers Claude Code's `ultrawork_request` attachment,
which causes the model to directly invoke the `Workflow` tool with
`scriptPath`/`args` instead of describing how to run it.

### Evidence Profiles

Two evidence classification profiles are available via `--evidence-profile`:

| Profile | Use Case | Required Evidence |
|---|---|---|
| `full` (default) | Standard workflow execution with agents | skill_listing + workflow_invoked + async_launched + agent_started + schema_result + completion |
| `early-blocker` | Workflow blocked before agent starts (e.g. `BLOCKED_INPUT`) | skill_listing + workflow_invoked + async_launched + completion (NO agent/schema requirement) |

`early-blocker` is only valid with `--expected-status BLOCKED`. It allows
classifying workflows that legitimately terminate before any subagent is launched.

### Real Journal JSONL Format

The `evaluate` subcommand supports two journal JSONL formats:

**Legacy format** (existing tests):
```json
{"type": "subagent_start", "run_id": "wf_...", "subagent_id": "agent-1"}
{"type": "subagent_output", "run_id": "wf_...", "subagent_id": "agent-1", "output": "..."}
```

**Real-world format** (observed from actual Claude Code sessions):
```json
{"type": "started", "run_id": "wf_...", "agent_id": "agent-1"}
{"type": "result", "run_id": "wf_...", "agent_id": "agent-1", "result": {"status": "PASS", ...}}
```

Both formats are detected structurally. The `started` type triggers
`agent_started` evidence, and the `result` type with a `result.status` field
triggers `schema_result` evidence.

### Structured Evidence Classification

Evidence is classified using two strategies in priority order:

1. **Structural JSON parsing** (primary): Each JSONL line is parsed as JSON.
   Known record structures (tool_use content, skill_listing type, notification
   type, etc.) are identified through their schema rather than text patterns.
   User messages are explicitly excluded from text-substring fallback to prevent
   false positives from user prompt text containing trigger words.

2. **Text-substring fallback** (narrow compatibility): Only applied to
   non-user message lines. Preserves backward compatibility with existing
   fixture formats.

This ensures that ordinary text containing "PASS", "Workflow", "scriptPath",
or workflow names in user messages cannot trigger false evidence matches.

## Manual Execution Steps

### Step 1: Generate a Smoke Packet

```bash
python .claude/scripts/build-native-interactive-smoke.py packet \
  --workflow workflowprogram-native-smoke \
  --script-path "/mnt/d/Code/WorkflowProgram-CN/tests/manual-fixtures/native-workflow-smoke/target-root/.claude/workflows/workflowprogram-native-smoke.js" \
  --expected-status PASS \
  --scenario-id pass-smoke-001 \
  --evidence-profile full \
  --out packet-pass-001.json \
  --json
```

### Step 2: Execute in Claude Code (WSL)

1. Open a WSL terminal.
2. Navigate to the target project directory.
3. Ensure `CLAUDE_CODE_WORKFLOWS=1` is set.
4. Invoke Claude Code interactively.
5. Paste the `suggestedPrompt` from the packet JSON — it begins with `ultrawork`
   which triggers the ultrawork_request attachment:

```text
ultrawork

Workflow({
  scriptPath: "/mnt/d/Code/WorkflowProgram-CN/tests/manual-fixtures/native-workflow-smoke/target-root/.claude/workflows/workflowprogram-native-smoke.js"
})
```

6. Observe the `/workflows` panel for execution progress.
7. After completion, record the session JSONL path from `~/.claude/projects/`.
8. Optionally record the journal JSONL from the subagent workflow directory.

### Step 3: Record JSONL Paths

Record the Windows-accessible paths. For WSL, use `\\wsl.localhost\Ubuntu-22.04\...`:

Example session JSONL:
```
\\wsl.localhost\Ubuntu-22.04\home\<user>\.claude\projects\<project-hash>\<session-id>.jsonl
```

Example journal JSONL:
```
\\wsl.localhost\Ubuntu-22.04\home\<user>\.claude\projects\<project-hash>\<session-id>\subagents\workflows\<run-id>\journal.jsonl
```

The journal may use either the legacy `subagent_start`/`subagent_output` format
or the real-world `started`/`result` format — both are supported.

### Step 4: Evaluate Evidence

```powershell
python .claude/scripts/build-native-interactive-smoke.py evaluate `
  --jsonl "\\wsl.localhost\Ubuntu-22.04\home\zhde\.claude\projects\<project-hash>\<session-id>.jsonl" `
  --journal-jsonl "\\wsl.localhost\Ubuntu-22.04\home\zhde\.claude\projects\<project-hash>\<session-id>\subagents\workflows\<run-id>\journal.jsonl" `
  --workflow workflowprogram-native-smoke `
  --script-path "D:\Code\WorkflowProgram-Native-CN\tests\manual-fixtures\native-workflow-smoke\target-root\.claude\workflows\workflowprogram-native-smoke.js" `
  --candidate-root "D:\Code\WorkflowProgram-Native-CN\tests\manual-fixtures\native-workflow-smoke\target-root" `
  --expected-status PASS `
  --scenario-id pass-smoke-001 `
  --evidence-profile full `
  --json
```

For early-blocker scenarios:
```powershell
python .claude/scripts/build-native-interactive-smoke.py evaluate `
  --jsonl "\\wsl.localhost\Ubuntu-22.04\home\zhde\.claude\projects\<project-hash>\<session-id>.jsonl" `
  --workflow workflowprogram-native-smoke `
  --script-path "D:\Code\WorkflowProgram-Native-CN\tests\manual-fixtures\native-workflow-smoke\target-root\.claude\workflows\workflowprogram-native-smoke.js" `
  --candidate-root "D:\Code\WorkflowProgram-Native-CN\tests\manual-fixtures\native-workflow-smoke\target-root" `
  --expected-status BLOCKED `
  --scenario-id early-blocker-001 `
  --evidence-profile early-blocker `
  --json
```

## Evidence Categories

The evaluator classifies these evidence types:

| Evidence | Description | Detection Method |
|---|---|---|
| `skill_listing` | Workflow appears in plugin skill listing | JSON `type: skill_listing` with workflow in `skills` list (structural) OR workflow name + `skill_listing` in same line (fallback) |
| `workflow_invoked` | `Workflow({scriptPath})` tool call | JSON tool_use/tool with `Workflow` and `scriptPath` (structural) OR substring (fallback, not for user messages) |
| `async_launched` | Workflow launched asynchronously | JSON `status: async_launched` (structural) OR substring (fallback, not for user messages) |
| `agent_started` | Subagent execution started | JSON `type: subagent_start` or `type: started` in session or journal |
| `schema_result` | Structured JSON output from subagent | Parsed `output` JSON with `status` field (subagent_output) or `result.status` (result type) |
| `completed_pass` | Workflow completed with PASS status | Workflow-result notification with PASS status |
| `completed_blocked` | Workflow completed with BLOCKED status | Workflow-result notification with BLOCKED_* status |
| `environment_disabled` | Workflow tool not enabled | JSON `error` field with "Workflow exists but is not enabled" message |

## Support Matrix

| Environment | Status | Notes |
|---|---|---|
| WSL (Windows) | Supported | WSL2 with Ubuntu 22.04, manual execution |
| macOS | Supported | Native terminal, manual execution |
| Linux | Supported | Native terminal, manual execution |
| Windows native (cmd/PowerShell) | Not tested | Claude Code on Windows may have different JSONL paths |
| Computer Use automation | Deferred | Requires non-terminal integration |

## Exit Codes

| Exit Code | Status | Meaning |
|---|---|---|
| 0 | `PASS` | Expected evidence satisfied |
| 1 | `INCONCLUSIVE` | Insufficient or mismatched evidence |
| 2 | `UNAVAILABLE` | Workflow tool disabled in context |

## Future Adapter Extension Points

When a non-terminal integration becomes available for Computer Use:

1. Add a `computer-use-adapter` subcommand that drives Claude Code through the
   allowed integration channel.
2. Add a `--provider computer_use` option that consumes a smoke packet and
   interacts with Claude Code to execute the workflow.
3. Extend `evaluate` to compare computer-use-generated JSONL against expected
   evidence from the packet.
4. Do NOT modify Native Workflow JS files — smoke harness code stays in host-side
   scripts only.

## Known Limitations

- JSONL must come from a real Claude Code session; synthesized JSONL may not
  contain all expected evidence markers.
- WSL JSONL paths use `\\wsl.localhost\` prefix which may differ by WSL distro.
- Journal JSONL is optional but significantly improves agent evidence detection.
  If explicitly specified but the file does not exist, evaluate returns
  INCONCLUSIVE with a clear error message.
- Windows-native Claude Code execution and JSONL path conventions are not yet tested.
