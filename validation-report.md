# Validation Report

## 2026-03-20 Baseline

- status: PASS
- scope: repository bootstrap completeness
- command: `powershell -ExecutionPolicy Bypass -File .claude/scripts/validate-workflow.ps1`
- result: 70 checks passed, 0 failed
- notes: initial structure validation before contract refactor

## 2026-03-23 Contract Refactor

- status: PASS
- scope: contracts, command metadata, semantic validation, smoke testing
- command: `powershell -ExecutionPolicy Bypass -File .claude/scripts/validate-workflow.ps1`
- result: 186 checks passed, 0 failed
- notes: contract layer, internal core skills, and command metadata validation are active

## 2026-03-23 Smoke Test

- status: PASS
- scope: dependency resolution and write target sanity for registered commands
- command: `powershell -ExecutionPolicy Bypass -File .claude/scripts/smoke-test-workflow.ps1`
- result: 6 commands checked, pass
- notes: all registered commands resolve known skills and valid write targets

## 2026-03-23 Local Claude Hardening

- status: PASS
- scope: extracted-workflow conventions and workspace-boundary rules
- command: manual repository hardening after local Claude design session
- result: constraints, develop command, spec template, and lessons updated
- notes: fixes the specific drift that produced command JSON files and external write permission denials during C audit workflow extraction

## 2026-03-23 Audit-C-Workflow-Pro Generation

- status: PASS
- scope: end-to-end /develop flow producing Audit-C-Workflow-Pro standalone repository
- command: manual /develop execution + `powershell -ExecutionPolicy Bypass -File .claude/scripts/validate-workflow.ps1`
- result: 187 checks passed (WorkflowProgram-CN), 63 checks passed (Audit-C-Workflow-Pro), local Claude test produced 36 findings on kernel_liteos_m
- notes: all prior constraints (Markdown commands, object-map settings) correctly enforced. JSON command file detection added to validate-workflow.ps1. spec-template.md extended with Toolchain Dependencies and Security Scope sections. Gate pre-approval needed for -p mode — new constraint extracted.

## 2026-03-23 Five-Issue Fix (Audit-C-Workflow-Pro Hardening)

- status: PASS
- scope: toolchain validation, L2 methodology, lessons mechanism, code path, hooks configuration
- command: manual issue analysis + fixes + `powershell -ExecutionPolicy Bypass -File .claude/scripts/validate-workflow.ps1`
- result: 63 checks passed (Audit-C-Workflow-Pro), 187 checks passed (WorkflowProgram-CN), 0 failures
- notes:
  - Problem 1: Added L1 toolchain availability checks (WARN level, 6 warnings expected)
  - Problem 2: Added step-by-step methodology to all 4 L2 agents with evidence requirements and depth boundaries
  - Problem 3: Redesigned lessons.md as append-only log, created session-findings.md as session buffer
  - Problem 4: Changed Stage 1 to clone target into ./target-code/ within workspace
  - Problem 5: Configured PostToolUseFailure and Stop hooks for auto error logging and progress tracking
  - 5 new constraints extracted to WorkflowProgram-CN

## 2026-03-28 Claude Code Cleanup

- status: PASS
- scope: remove Codex mirror layer and contract-only assets, keep Claude Code compatible structure
- command: `powershell -ExecutionPolicy Bypass -File .claude/scripts/validate-workflow.ps1`
- result: 70 checks passed, 0 failed
- notes: removed `.agents/`, `.claude/contracts/`, `smoke-test-workflow.ps1`, `core-*` skills, and downstream transcript artifacts

## 2026-03-30 Plugin Packaging

- status: PASS
- scope: package WorkflowProgram-CN as a Claude Code plugin with root-level commands, skills, agents, rules, and scripts
- command: `scripts/verify-plugin-load.sh`
- result: 11 slash entrypoints discovered via `claude --plugin-dir /mnt/d/Code/WorkflowProgram-CN`, 0 discovery failures
- notes: WSL Claude is currently not logged in, so runtime checks stop at `/login`; discovery and plugin loading are confirmed.

## 2026-04-03 Runtime Smoke (empty-project)

- status: ENVIRONMENT-SKIP
- scope: Phase 3 runtime smoke against copied empty-project fixture
- command: `python3 tools/runtime_smoke.py --fixture empty-project --json`
- result: run_id `20260403T031024Z-empty-project`, category `CLAUDE_NOT_LOGGED_IN`
- notes: `RUN_ROOT` created successfully under `tests/transcripts/20260403T031024Z-empty-project/target/.workflowprogram/runs/20260403T031024Z-empty-project`; `context.json`, `state.json`, `events.jsonl`, `transcript.md`, and `validation-runtime-report.md` were all written; `EnvironmentSkip` event recorded; target `.claude/` output not generated because Claude CLI is not logged in.

## 2026-04-03 Runtime Smoke Expansion

- status: ENVIRONMENT-SKIP
- scope: existing-workflow and broken-workflow fixture coverage; state-bus RUN_ROOT alignment
- command: `python3 tools/runtime_smoke.py --fixture existing-workflow --json` and `python3 tools/runtime_smoke.py --fixture broken-workflow --json`
- result: run_id `20260403T032546Z-existing-workflow` and `20260403T032546Z-broken-workflow`, both classified as `CLAUDE_NOT_LOGGED_IN`
- notes: both fixtures produced complete `RUN_ROOT` evidence bundles under `tests/transcripts/*`; `.claude/scripts/state-bus.py` now defaults to `.workflowprogram/session-state.json`, supports `--run-root`, and appends state events to `events.jsonl` when a run root is provided.

## 2026-04-03 Phase 4 Finalization

- status: PASS
- scope: remove root compatibility layer, retire legacy sync script, archive obsolete migration docs
- command: `python3 tools/build_plugin.py`, `python3 .claude/scripts/validate-workflow.py`, `powershell.exe -ExecutionPolicy Bypass -File .claude/scripts/validate-workflow.ps1`, `python3 tools/runtime_smoke.py --fixture empty-project --json`
- result: build succeeded; Python validator `PASS: 117 / FAIL: 0`; PowerShell validator `PASS: 116 / FAIL: 0`; runtime smoke returned `ENVIRONMENT-SKIP` with run_id `20260403T033137Z-empty-project` and category `CLAUDE_NOT_LOGGED_IN`
- notes: root-level `commands/`, `skills/`, `agents/`, `rules/`, `scripts/` and `tools/sync_plugin_assets.py` are removed; `review_report.md`, `实施方案V3.md`, and `实施计划-Plugin架构迁移.md` were moved to `docs/archive/`; active entry docs now describe only `.claude/` source assets and `dist/plugin/` build output.

## 2026-04-05 Phase 5 Lifecycle Closure

- status: PASS
- scope: implement managed asset ownership guard and build trace manifest; update validators and runtime evidence
- command: `python3 tools/build_plugin.py`, `python3 .claude/scripts/validate-workflow.py`, `powershell.exe -ExecutionPolicy Bypass -File .claude/scripts/validate-workflow.ps1`, `python3 .claude/scripts/managed-assets.py plan/apply-staged ...`, `python3 tools/runtime_smoke.py --fixture empty-project --json`
- result: build succeeded with `dist/plugin/build-manifest.json`; Python validator `PASS: 183 / FAIL: 0`; PowerShell validator `PASS: 183 / FAIL: 0`; managed-assets smoke produced `plan_exit=0` and `apply_exit=2` with one expected unmanaged-file conflict and one managed-file update; runtime smoke returned `ENVIRONMENT-SKIP` with run_id `20260405T105730Z-empty-project` and category `CLAUDE_NOT_LOGGED_IN`
- notes:
  - added `.claude/scripts/managed-assets.py` to enforce staged candidate -> apply flow and maintain `TARGET_ROOT/.workflowprogram/managed-files.json`
  - `workflowprogram-develop` and `/develop` now require candidate generation under `RUN_ROOT/outputs/candidate/.claude/` before apply
  - `build_plugin.py` now packages the full script set and emits `dist/plugin/build-manifest.json` with plugin version, source commit, dirty flag, and per-file sha256
  - `tools/runtime_smoke.py` now captures `outputs/plugin-build-manifest.json` inside `RUN_ROOT`
  - the managed-assets smoke confirmed that unmanaged target files are not overwritten; candidate conflicts are copied to `RUN_ROOT/outputs/conflicts/`

## 2026-04-05 Natural-Language Routing Optimization

- status: PASS
- scope: keep natural-language auto-trigger on `workflowprogram-orchestrate` only; keep leaf skills explicit
- command: `python3 tools/build_plugin.py`, `python3 .claude/scripts/validate-workflow.py`
- result: build succeeded; Python validator `PASS: 183 / FAIL: 0`; regenerated plugin artifact confirms `dist/plugin/skills/workflowprogram-orchestrate/SKILL.md` no longer contains `disable-model-invocation`
- notes:
  - `workflowprogram-orchestrate` description is now bilingual and includes current-project workflow design / audit / iterate / validate cues
  - `.claude/settings.json` and `.claude/rules/constraints.md` now explicitly state that only `workflowprogram-orchestrate` should accept natural-language auto-trigger
  - leaf skills `workflowprogram-develop/audit/iterate/validate` remain slash-first to avoid multi-skill competition

## 2026-04-06 Phase 6 Stage Progress Instrumentation

- status: PASS
- scope: add stage progress instrumentation, stage-node encapsulation plan, and validator enforcement
- command: `python3 .claude/scripts/stage-progress.py update --run-root /tmp/wf-run ... --json`, `python3 tools/build_plugin.py`, `python3 .claude/scripts/validate-workflow.py`, `powershell.exe -ExecutionPolicy Bypass -File .claude/scripts/validate-workflow.ps1`
- result: stage-progress smoke generated `current-progress.json` / `milestones.jsonl` / `user-progress.md`; build succeeded; Python validator `PASS: 187 / FAIL: 0`; PowerShell validator `PASS: 187 / FAIL: 0`
- notes:
  - added `.claude/scripts/stage-progress.py` for `StageStarted/StageCheckpoint/StageCompleted` event logging
  - `/develop` and `workflowprogram-develop` now include explicit progress hook requirements
  - validators now require both source and build outputs to include `stage-progress.py`
  - added `docs/phase-06-implementation-plan.md` and expanded lowlevel design to provide stage-level node encapsulation and runtime progress contracts

## 2026-04-09 Phase 7 Planning And Validator Alignment

- status: PASS
- scope: freeze active design docs, add Phase 7 execution plan, and align repository validators with `runtime_contract / test_contract`
- command: `python3 tools/build_plugin.py`, `python3 .claude/scripts/validate-workflow.py`, `python3 .claude/scripts/validate-workflow-spec.py --spec .claude/skills/develop/yaml-spec-template.md --json`, `powershell.exe -ExecutionPolicy Bypass -File .claude/scripts/validate-workflow.ps1`
- result: build succeeded; Python validator passed with active design-doc checks enabled; `validate-workflow-spec.py` passed on the YAML template; PowerShell validator should be rerun on a native Windows shell when available to confirm parity
- notes:
  - added `docs/phase-07-implementation-plan.md` to decompose remaining work into documentation governance, static validation, S5 test-contract closure, fixed fixtures, and archive cleanup
  - repository validators now require the current active design docs and verify that `/develop` plus `workflowprogram-develop` both mention `runtime_contract / test_contract`
  - archive docs remain treated as historical trace only; they are not part of the active validation chain

## 2026-04-09 Phase 7 S5 Validation Closure And Fixed Fixtures

- status: PASS
- scope: push `test_contract` into S5 validation summaries, extend runtime smoke outputs, and add repository-owned spec fixtures
- command: `python3 tools/build_plugin.py`, `python3 .claude/scripts/validate-workflow.py`, `python3 .claude/scripts/validate-workflow-spec.py --spec tests/spec-fixtures/valid-minimal.yaml --json`, `python3 .claude/scripts/validate-workflow-spec.py --spec tests/spec-fixtures/invalid-entry.yaml --json`, `python3 .claude/scripts/workflow-runner.py run --spec tests/spec-fixtures/write-boundary-violation.yaml ... --json`, `python3 tools/runtime_smoke.py --fixture invalid-entry --json`, `python3 tools/runtime_smoke.py --fixture empty-project --json`
- result: build and Python validator passed; valid fixture passed; invalid-entry fixture failed on the expected missing entry error; write-boundary fixture failed on the expected RUN_ROOT write boundary violation; runtime smoke now writes `outputs/stages/s5-validation-summary.json` and returns `contract_source` plus `contract_categories`
- notes:
  - `workflowprogram-validate` now explicitly treats `test_contract` as the preferred judgment source when a spec is available
  - `runtime_smoke.py` now emits contract-aware JSON summaries and writes `s5-validation-summary.json` for both FAIL and ENVIRONMENT-SKIP paths
  - added `tests/spec-fixtures/valid-minimal.yaml`, `invalid-entry.yaml`, `write-boundary-violation.yaml`, and `environment-skip.yaml`

## 2026-04-09 Phase 7 Stage Model And S5 Judge Closure

- status: PASS
- scope: close the six-stage model drift, remove undocumented spec schema drift, and ship the S5 judge through source and dist
- command: `python3 .claude/scripts/validate-workflow-spec.py --spec .claude/skills/develop/yaml-spec-template.md --json`, `python3 .claude/scripts/validate-workflow-spec.py --spec tests/spec-fixtures/valid-minimal.yaml --json`, `python3 .claude/scripts/validate-workflow-spec.py --spec tests/spec-fixtures/write-boundary-violation.yaml --json`, `python3 .claude/scripts/validate-workflow-spec.py --spec tests/spec-fixtures/invalid-entry.yaml --json`, `WORKFLOWPROGRAM_CLAUDE_LOGGED_IN=true python3 .claude/scripts/workflow-runner.py run --spec tests/spec-fixtures/valid-minimal.yaml --run-root <tmp-run> --target-root <tmp-target> --intent develop --request "design a workflow" --auto-approve --json`, `WORKFLOWPROGRAM_CLAUDE_LOGGED_IN=true python3 .claude/scripts/workflow-runner.py run --spec tests/spec-fixtures/write-boundary-violation.yaml --run-root <tmp-run> --target-root <tmp-target> --intent develop --request "boundary" --auto-approve --json`, `python3 tools/build_plugin.py`, `python3 .claude/scripts/validate-workflow.py`, `python3 tools/runtime_smoke.py --fixture empty-project --json`, `python3 tools/runtime_smoke.py --fixture invalid-entry --json`
- result: YAML template and six-stage fixtures passed spec validation with no warnings; `invalid-entry` continued to fail on the expected missing entry; `valid-minimal` runner returned `PASS` with `transition_count=6`; `write-boundary-violation` continued to fail on the expected `workflow-spec.yaml` RUN_ROOT boundary; build succeeded; Python validator passed with `PASS: 260 / FAIL: 0`; runtime smoke returned `ENVIRONMENT-SKIP` for `empty-project` and `FAIL/STRUCTURE_FAILURE` for `invalid-entry`
- notes:
  - removed the undocumented top-level `stage_roles` field from the YAML template and moved the active schema to explicit `stage_slot`
  - `validate-workflow-spec.py` now requires `stage_slot: S1..S6` completeness and ordering, and `workflow-runner.py` no longer infers `producer` from stage index
  - `workflow-s5-judge.py` is now required by repository validators and shipped in `dist/plugin/build-manifest.json`
  - WSL invocation of `validate-workflow.ps1` still timed out after 20 seconds with no output; native Windows verification remains pending

## 2026-04-09 Phase 7 Non-Windows Review Sweep

- status: PASS
- scope: run five non-Windows review cycles after the latest validator and plan-marker alignment
- command: `git diff --check`, `python3 .claude/scripts/validate-workflow.py`, `python3 .claude/scripts/validate-workflow-spec.py --spec .claude/skills/develop/yaml-spec-template.md --json`, `python3 .claude/scripts/validate-workflow-spec.py --spec tests/spec-fixtures/valid-minimal.yaml --json`, `python3 .claude/scripts/validate-workflow-spec.py --spec tests/spec-fixtures/write-boundary-violation.yaml --json`, `python3 .claude/scripts/validate-workflow-spec.py --spec tests/spec-fixtures/invalid-entry.yaml --json`, `WORKFLOWPROGRAM_CLAUDE_LOGGED_IN=true python3 .claude/scripts/workflow-runner.py run --spec tests/spec-fixtures/valid-minimal.yaml ... --json`, `WORKFLOWPROGRAM_CLAUDE_LOGGED_IN=true python3 .claude/scripts/workflow-runner.py run --spec tests/spec-fixtures/write-boundary-violation.yaml ... --json`, `python3 tools/runtime_smoke.py --fixture empty-project --json`, `python3 tools/runtime_smoke.py --fixture invalid-entry --json`
- result: all five non-Windows review cycles completed without new issues; `git diff --check` passed; repository validator passed with `PASS: 260 / FAIL: 0`; template plus six-stage fixtures passed schema validation; `invalid-entry` continued to fail on the expected missing entry; `valid-minimal` runner continued to pass with `transition_count=6`; `write-boundary-violation` continued to fail on the expected RUN_ROOT boundary; runtime smoke continued to return `ENVIRONMENT-SKIP` for `empty-project` and `FAIL/STRUCTURE_FAILURE` for `invalid-entry`
- notes:
  - after de-scoping Windows, the active plan marker in repository validators was aligned from `P0` to `P1`
  - current non-Windows residual gap is only the missing logged-in Claude PASS smoke path

## 2026-04-09 Phase 7 Provider Abstraction And Dynamic Test Closure

- status: PASS
- scope: close the provider-agnostic runtime smoke path, harden S5 contract judgment, and tighten dist/plugin validation against build outputs
- command: `python3 tools/build_plugin.py`, `python3 .claude/scripts/validate-workflow.py /mnt/d/Code/WorkflowProgram-CN`, `python3 .claude/scripts/validate-workflow-spec.py --spec .claude/skills/develop/yaml-spec-template.md`, `python3 .claude/scripts/validate-workflow-spec.py --spec tests/spec-fixtures/valid-minimal.yaml`, `python3 .claude/scripts/validate-workflow-spec.py --spec tests/spec-fixtures/write-boundary-violation.yaml`, `python3 .claude/scripts/validate-workflow-spec.py --spec tests/spec-fixtures/invalid-entry.yaml`, `python3 .claude/scripts/workflow-runner.py run --spec tests/spec-fixtures/valid-minimal.yaml --run-root <tmp-run> --target-root <tmp-target> --intent develop --request "runner provider verification" --auto-approve --runtime-provider command_adapter --provider-command 'python3 tools/mock_runtime_host.py' --json`, `python3 tools/runtime_smoke.py --fixture empty-project --runtime-provider command_adapter --provider-command 'python3 tools/mock_runtime_host.py' --json`, `python3 tools/runtime_smoke.py --fixture existing-workflow --runtime-provider command_adapter --provider-command 'python3 tools/mock_runtime_host.py' --json`, `python3 tools/runtime_smoke.py --fixture broken-workflow --runtime-provider command_adapter --provider-command 'python3 tools/mock_runtime_host.py' --json`, `python3 tools/runtime_smoke.py --fixture invalid-entry --runtime-provider command_adapter --provider-command 'python3 tools/mock_runtime_host.py' --json`, `python3 tools/runtime_smoke.py --fixture missing-args --runtime-provider command_adapter --provider-command 'python3 tools/mock_runtime_host.py' --json`, `python3 tools/runtime_smoke.py --fixture external-write --runtime-provider command_adapter --provider-command 'python3 tools/mock_runtime_host.py' --json`, `python3 tools/runtime_smoke.py --fixture managed-conflict --runtime-provider command_adapter --provider-command 'python3 tools/mock_runtime_host.py' --json`, `git diff --check`
- result: build succeeded; Python validator passed with `PASS: 461 / FAIL: 0`; YAML template plus fixed fixtures passed spec validation, while `invalid-entry` continued to fail on the expected missing entry registration; runner returned `PASS` with `transition_count=6` through `command_adapter`; smoke matrix now returns `PASS` for `empty-project` and `existing-workflow`, `FAIL/EVIDENCE_FAILURE` for `broken-workflow`, `FAIL/STRUCTURE_FAILURE` for `invalid-entry`, `FAIL/S5_ENTRY_REQUIRED_ARGUMENTS_PRESENT` with observed `MISSING_ARGUMENT` for `missing-args`, `FAIL/S5_BOUNDARY_TARGET_ROOT_BOUNDARY_CHANGES` for `external-write`, and `FAIL/CONFLICT_FAILURE` for `managed-conflict`; `git diff --check` passed
- notes:
  - added `tools/mock_runtime_host.py` as a reference `command_adapter` runtime host and moved `runtime_smoke.py` onto shared `runtime_host.py` invocation
  - `workflow-s5-judge.py` now validates declared entry consistency, PASS/WARN flow evidence presence, route/runner semantic evidence, deliverable changedness via before/after snapshots, managed conflict candidate sources, and exception-path summary alignment
  - `validate-workflow.py` now verifies dist/plugin critical assets, build-manifest sha256 values, command wrapper outputs, and build-transformed source/dist consistency
  - `validate-workflow-spec.py` now rejects deprecated `claude_cli_available / claude_cli_logged_in` environment checks in favor of `runtime_host_available / runtime_host_ready`

## 2026-04-10 Phase 7 S1-S6 Deterministic Quality Gates And Smoke Matrix

- status: PASS
- scope: harden S1 draft quality checks, S6 lessons closure checks, progress backfill for skip paths, and standardized multi-provider smoke execution
- command: `python3 .claude/scripts/validate-workflow-draft.py --spec <run-root>/workflow-spec.md --json`, `python3 .claude/scripts/validate-lessons-delta.py --run-root <run-root> --run-id <run-id> --failure-kind <kind> --json`, `python3 tools/runtime_smoke.py --fixture empty-project --runtime-provider command_adapter --provider-command 'python3 tools/mock_runtime_host.py' --json`, `python3 tools/runtime_smoke.py --fixture existing-workflow --runtime-provider command_adapter --provider-command 'python3 tools/mock_runtime_host.py' --json`, `python3 tools/runtime_smoke.py --fixture existing-workflow --entry-skill workflowprogram-iterate --request '/workflowprogram-iterate evolve constraints from lessons' --runtime-provider command_adapter --provider-command 'python3 tools/mock_runtime_host.py' --json`, `python3 tools/runtime_smoke.py --fixture external-write --runtime-provider command_adapter --provider-command 'python3 tools/mock_runtime_host.py' --json`, `python3 tools/runtime_smoke.py --fixture empty-project --runtime-provider fixture_host --json`, `python3 tools/runtime_smoke_matrix.py --json`, `python3 tools/runtime_smoke_matrix.py --include-claude-cli --json`, `python3 tools/build_plugin.py`, `python3 .claude/scripts/validate-workflow.py /mnt/d/Code/WorkflowProgram-CN`, `git diff --check`
- result: S1 draft validator and S6 lessons validator both passed on generated run artifacts; `command_adapter` smoke returned `PASS` for `develop/audit/iterate`, and `FAIL/S5_BOUNDARY_TARGET_ROOT_BOUNDARY_CHANGES` for `external-write`; `fixture_host` smoke returned `PASS` for `develop/audit/iterate`; `runtime_smoke_matrix.py --json` passed all 8 adapter/fixture cases; `runtime_smoke_matrix.py --include-claude-cli --json` passed all 9 cases with `claude_cli` standardized to `ENVIRONMENT-SKIP/RUNTIME_HOST_NOT_READY` in the current environment; repository validator passed with `PASS: 461 / FAIL: 0`; `git diff --check` passed
- notes:
  - added `.claude/scripts/validate-workflow-draft.py` to enforce `workflow-spec.md` section completeness and placeholder bans
  - added `.claude/scripts/validate-lessons-delta.py` to enforce `run_id`, `failure_kind`, constraint-candidate semantics, and `user-progress.md` history summary
  - `workflow-s5-judge.py` now consumes both validators and emits explicit `workflow_spec_draft_*` / `s6_lessons_delta_*` checks in `validation-runtime-report.md`
  - `tools/mock_runtime_host.py` and `runtime_host.py` fixture paths now emit deterministic `workflow-spec.md`, `s6-lessons-delta.md`, and progress artifacts when applicable
  - `tools/runtime_smoke.py` now backfills minimum progress evidence for skip/error paths so `claude_cli` environment skips remain contract-compliant instead of collapsing into artifact failures

## 2026-04-10 Phase 7 Product Entry Wrapper And Capability Matrix

- status: PASS
- scope: close the remaining develop entry orchestration gap, add repository-level capability drift checks, and mark active vs historical design documents explicitly
- command: `python3 .claude/scripts/workflow-entry.py run --spec tests/spec-fixtures/valid-minimal.yaml --run-root <tmp-run> --target-root <tmp-target> --candidate-root <tmp-candidate> --entry-skill workflowprogram-develop --request "design workflow" --auto-approve --runtime-provider fixture_host --json`, `python3 tools/build_plugin.py`, `python3 .claude/scripts/validate-workflow.py /mnt/d/Code/WorkflowProgram-CN`, `python3 tools/runtime_smoke_matrix.py --include-claude-cli --json`, `git diff --check`
- result: deterministic product entry wrapper now produces `entry-orchestration-summary.json`, repository validator now checks `workflowprogram-capability-matrix.json` and `workflowprogram-design-status.md`, build output includes `workflow-entry.py`, and the smoke matrix plus repository validator continue to pass
- notes:
  - added `.claude/scripts/workflow-entry.py` to drive `validate-workflow-spec.py -> generate-workflow-view.py -> managed-assets.py -> workflow-runner.py -> validate-run-state.py`
  - added `docs/workflowprogram-design-status.md` to separate active truth sources, supporting docs, and historical records
  - added `docs/workflowprogram-capability-matrix.json` and wired it into `.claude/scripts/validate-workflow.py`
  - historical design review docs now carry a top-level status note pointing back to the active truth-source index
