<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->

# WorkflowProgram High-Level Design Addendum

Use this addendum after applying the general `$highlevel-design` architecture views. It preserves alignment with the original WorkflowProgram Stage High-Level design without forcing that structure onto unrelated systems.

## Domain-Specific Sections

Append or integrate these sections where they fit the repository's existing document conventions:

```markdown
## WorkflowProgram 入口与意图路由
### 入口方式
### 用户使用过程
### 意图到 Stage 流程
### 输入与最终输出

## WorkflowProgram Stage 运行逻辑
### S0 <Stage Name>
### S1 <Stage Name>
### ...
### Stage 可验证验收矩阵
### 基础运行测试契约

## 产品入口编排
## 目标工作流生成与发布
## WorkflowProgram 资产关系与兼容边界
```

## Stage Contract

Each stage must declare:

- purpose;
- entry condition;
- inputs;
- main actions;
- outputs;
- exit criteria;
- failure path;
- validation or test evidence.

Use an acceptance matrix:

| Stage | Input | Output | Gate | Failure Condition | Evidence |
|---|---|---|---|---|---|

## Artifact Classification

Classify at least:

| Artifact Area | Typical Role | Required Decision |
|---|---|---|
| `.workflowprogram/` | authoring metadata, audit input, or historical compatibility state | runtime dependency or optional metadata |
| `.claude/workflows/*.js` | native executable control plane | authoritative runtime artifact or not used |
| `.claude/agents/` | reusable role definitions | inline, reusable, or independent invocation |
| `.claude/skills/` | reusable capability and routing instructions | workflow entrypoint, reusable support capability, or not required |
| validators and smoke fixtures | verification assets | retained, replaced, narrowed, or removed |

## Agent and Skill Boundary

- Keep workflow-specific agent prompts inline when they are tightly coupled to one JS control plane.
- Keep agents in `.claude/agents/` when they need reuse, independent invocation, independent permissions, or long separately versioned prompts.
- Keep skills in `.claude/skills/` for reusable capabilities, routing instructions, or repeated tool-use knowledge. A skill does not need to be the workflow entrypoint.

## Original Structure Mapping

The original WorkflowProgram document included:

- purpose and scope;
- design baseline and conflict convergence;
- project structure, installation, and distribution;
- user entry and intent-to-stage flow;
- ordered stage logic;
- stage acceptance matrix and smoke contract;
- product entry orchestration;
- target workflow publication;
- quality requirements;
- relationship to existing implementation.

Preserve these concerns, but organize the resulting HLD through the general architecture views first.
