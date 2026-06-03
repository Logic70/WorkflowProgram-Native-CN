# WorkflowProgram Low-Level Design Addendum

Apply this addendum after the general `$lowlevel-design` structure.

## Required Domain Sections

```markdown
## WorkflowProgram 入口与模式选择
## Authoring Stage 详细设计
## 目标 Native Workflow JS 文件契约
## Agent、Skill 与领域脚本边界
## L1 / L2 / L3 验证契约
## 轻量静态校验器规则
## Controlled Update 与 Drift 检测
## Smoke Fixture 与 JSONL 证据
## 发布与兼容契约
## 旧 Runtime 能力迁移矩阵
```

## Authoring Stage Contract

For each authoring stage define:

- purpose;
- entry condition;
- inputs;
- ordered actions;
- outputs;
- exit gate;
- failure kind or status;
- owned files;
- verification evidence.

Use:

| Stage | Purpose | Entry | Actions | Outputs | Gate | Failure | Owned Files | Evidence |
|---|---|---|---|---|---|---|---|---|

## Artifact Decision

Classify at least:

| Artifact | Typical Target Role | Required Decision |
|---|---|---|
| `.claude/workflows/*.js` | authoritative executable control plane | required for Native mode |
| `.claude/skills/` | optional reusable instructions or thin router | explicit generation condition |
| `.claude/agents/` | optional reusable roles | explicit extraction condition |
| `.claude/scripts/` | optional deterministic domain scripts | explicit external-fact need |
| `.workflowprogram/design/` | optional authoring metadata | retention need |
| `.workflowprogram/runs/` | optional authoring evidence | retention need |
| `.workflowprogram/managed-files.json` | optional drift metadata | controlled-update need |
| old `.workflowprogram/runtime/` | historical or deprecated runtime | migration action |
| `workflow-spec.yaml` | optional stable IR | explicit complexity or audit need |

## Old-to-Native Decision Rule

For each inherited feature:

1. name its current responsibility;
2. decide whether the target use case still requires it;
3. check whether Native Workflow JS already covers it;
4. retain, replace, narrow, or remove it;
5. name the test or evidence.

Cover runner, validator, guard, spec YAML, smoke, resume/cache, evidence ledger, managed assets, finalizer, reusable skills, and reusable Agents.
