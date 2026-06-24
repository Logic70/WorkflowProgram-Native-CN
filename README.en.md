# WorkflowProgram Native CN

[中文](README.md) | [English](README.en.md)

WorkflowProgram Native CN is a meta-workflow plugin for Claude Code workspaces. It does not ship business code. It helps users design, generate, validate, safely apply, and iterate `.claude/` workflow assets.

## What It Solves

Many Claude Code workflows start as one `SKILL.md`, a few agents, and manual settings edits. That is enough to start, but it usually creates problems:

- docs, prompts, and runtime behavior drift apart
- step order depends on model memory
- target projects are overwritten directly
- runs lack structured success and failure evidence
- lessons from one run do not affect the next run

WPN treats a workflow as a maintainable product: it has a truth source, a control plane, validation, and a feedback loop.

## Installation

Prerequisite: a host `Python 3.10+` runtime is available.

The recommended installation path is the Claude Code marketplace:

```bash
claude plugin marketplace add Logic70/WorkflowProgram-Native-CN
claude plugin install workflowprogram-native-cn@logic70-plugins
```

Inside the Claude Code interactive UI:

```text
/plugin marketplace add Logic70/WorkflowProgram-Native-CN
/plugin install workflowprogram-native-cn@logic70-plugins
/reload-plugins
```

After installation:

1. Restart `claude`, or run `/reload-plugins`
2. On first startup, the plugin prepares private Python dependencies under `${CLAUDE_PLUGIN_DATA}/python/site-packages`
3. Run `workflowprogram-doctor` for basic diagnostics
4. Run `workflowprogram-clean` to clean plugin caches, test outputs, or old target runs; it is dry-run by default and requires `--apply` to delete files

If you see `Unknown skill: workflowprogram-orchestrate`, the plugin usually has not been reloaded. Run `/reload-plugins` or restart `claude`, then use `/workflowprogram-native-cn:workflowprogram-orchestrate ...`.

## Quick Start

Start Claude Code in the target project:

```bash
cd your-project
claude
```

Describe the target in natural language and let semantic routing select `workflowprogram-orchestrate`:

```text
"Design a code review workflow for this project"
"Audit the workflow structure of this project"
"Validate the workflow assets in this project"
"Publish this completed workflow as a Claude Code plugin"
```

Use an explicit slash command only for route debugging or as a fallback:

```text
/workflowprogram-native-cn:workflowprogram-orchestrate Design a code review workflow for this project
```

Main entries:

| Entry | Purpose |
|------|------|
| `workflowprogram-develop` | Clarify, design, generate, validate, and safely apply candidate workflow assets |
| `workflowprogram-audit` | Audit an existing workflow structure |
| `workflowprogram-validate` | Produce a validation verdict for workflow assets |
| `workflowprogram-iterate` | Turn lessons into improvement proposals |
| `workflowprogram-publish` | Publish a completed target workflow as a marketplace plugin |

## Current Capability Boundary

The main path is Native Workflow JS authoring. Product-level `workflowprogram-develop.js` owns Clarify, Confirm, Design, Review, Generate, Validate, Smoke, Apply, and Deliver state transitions. Host-side scripts perform narrow, repeatable actions such as static validation, candidate hashing, managed apply, manifest aggregation, and quality gates.

The default deliverable is `.claude/workflows/<name>.js`. Use `supporting_assets` only when a single JS workflow is insufficient. Optional reusable skills, agents, domain scripts, compatibility commands, and authoring metadata require an explicit reason and must pass the controlled-path allowlist.

`managed-files` is special authoring metadata. It may appear in reports for traceability, but it must not be staged as a normal candidate file that overwrites `TARGET_ROOT/.workflowprogram/managed-files.json`. The target manifest is maintained by `managed-assets.py apply-staged` from actual persisted files, target hashes, conflicts, and rollback data.

Targets that already contain `.workflowprogram/runtime/` assets or historical design specs are treated as requiring explicit migration confirmation. WPN does not silently apply historical control flow and does not automatically rewrite those files. This README documents the current Native path; compatibility details belong in the design docs.

## Core Model

### Three Roots

| Root | Role | Meaning |
|------|------|------|
| `PLUGIN_ROOT` | Capability source | WPN skills, workflows, scripts, and templates; read-only after installation |
| `TARGET_ROOT` | Delivery target | User project root; final `.claude/` assets are written only through managed apply |
| `RUN_ROOT` | Runtime evidence | Isolated per-run directory, usually `TARGET_ROOT/.workflowprogram/runs/<run-id>/` |

### Stage Model

| Stage | Responsibility |
|------|------|
| S0 | Route user intent and prepare the target environment |
| S1 | Clarify purpose, object, process, decision, evidence, acceptance, and boundary logic |
| S2 | Explore target context and reusable assets |
| S3 | Design, review, and approve an executable authoring plan |
| S4 | Generate candidates, run pre-apply checks, and apply controlled writes |
| S5 | Validate workflow behavior and evidence independently |
| S6 | Feed lessons and long-lived constraint candidates into later runs |

Ordering is constrained by Native workflow JS and deterministic scripts, not by model memory.

## Managed Write Flow

WPN does not edit the target project directly. The write flow is:

1. Write candidate assets to `RUN_ROOT/outputs/candidate/`
2. Build a change plan with `managed-assets.py plan`
3. After user approval, write allowed paths with `managed-assets.py apply-staged`
4. Preserve conflict copies instead of silently overwriting user files
5. Update the managed manifest, rollback manifest, and recovery instructions

Ordinary candidate writes are currently limited to `.claude/**`, `.workflowprogram/design/**`, and `.workflowprogram/runtime/**`. Expanding that scope requires matching managed-apply rules, validators, and documentation.

## Validation And Publishing

WPN maintains three quality gates:

| Gate | Command | When To Use |
|------|---------|-------------|
| Commit Gate | `python .claude/scripts/quality-gate.py commit` | Fast checks before ordinary commits |
| Integration Gate | `python .claude/scripts/quality-gate.py integration` | Runtime, schema, generator, publish, or smoke harness changes |
| Release Gate | `python .claude/scripts/quality-gate.py release` | Before publishing a WPN plugin version; validates source and `dist/plugin/` |

Common development commands:

```bash
# Repository validation
python .claude/scripts/validate-workflow.py

# Native workflow JS static validation
python .claude/scripts/validate-native-workflow-js.py --script <workflow.js> --json

# Single smoke fixture
python tools/runtime_smoke.py --fixture empty-project --runtime-provider fixture_host

# Smoke matrix
python tools/runtime_smoke_matrix.py

# Rebuild plugin payload
python tools/build_plugin.py
```

Publishing a target workflow requires successful develop, validation, managed evidence, and publish qualification checks. Real GitHub writes still require explicit user approval. Missing repositories, permissions, authentication, or checkouts return `BLOCKED` instead of attempting a partial publish.

## Design Documents

This README is only the overview and operator guide. For deeper design, read:

- [Current design status](docs/workflowprogram-design-status.md)
- [Native control-plane high-level design](docs/native-workflow-control-plane-highlevel-design.md)
- [Native control-plane low-level design](docs/native-workflow-control-plane-lowlevel-design.md)
- [Stage model high-level design](docs/workflowprogram-stage-highlevel-design.md)
- [Stage model low-level design](docs/workflowprogram-stage-lowlevel-design.md)
- [Capability matrix](docs/workflowprogram-capability-matrix.json)

## Repository Layout

```text
workflowprogram-native-cn/
├── CLAUDE.md
├── README.md
├── README.en.md
├── lessons.md
├── .claude/
│   ├── commands/
│   ├── skills/
│   ├── agents/
│   ├── rules/
│   └── scripts/
├── .claude-plugin/
├── dist/plugin/
├── docs/
├── tests/
└── tools/
```

## License

MIT
