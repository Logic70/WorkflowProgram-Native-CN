# General High-Level Design Structure

Use this structure for non-trivial software systems. Adapt depth to the design target; do not force irrelevant details.

## Main Document Skeleton

```markdown
# <System> High-Level Design

## 1. 目标与范围
## 2. 背景、基线、约束与关键决策
## 3. 系统上下文
## 4. 用户视图
## 5. 逻辑视图
## 6. 运行时视图
## 7. 数据视图
## 8. 部署视图
## 9. 质量属性
## 10. 验证策略
## 11. 与现有实现的关系
## 12. 未决问题
```

## View Guidance

### 1. 目标与范围

State the intended outcome, target users or callers, in-scope concerns, out-of-scope concerns, and completion boundary.

### 2. 背景、基线、约束与关键决策

List observed implementation facts and prior design sources. Record conflicts explicitly:

| Conflict | Decision | Reason | Affected Artifact |
|---|---|---|---|

Identify post-implementation sources of truth.

### 3. 系统上下文

Describe the system boundary, upstream and downstream systems, external actors, trust boundaries, and major dependencies. Use a context diagram when it improves clarity.

### 4. 用户视图

Required. Describe roles, entrypoints, key use cases, normal paths, visible failures, and outputs. Include non-human callers when they are material.

### 5. 逻辑视图

Required. Describe modules, components, responsibilities, interfaces, data flow, dependency direction, and ownership boundaries. Use a component diagram when useful.

### 6. 运行时视图

Assess for every design. Expand when requests, jobs, events, state transitions, retries, or concurrency matter. Describe important flows with sequence diagrams or ordered steps. Otherwise mark `不适用` and explain why.

### 7. 数据视图

Assess for every design. Expand when persistence, caches, schemas, ownership, consistency, migrations, retention, or sensitive data matter. Otherwise mark `不适用` and explain why.

### 8. 部署视图

Required. Describe runtime units, processes, nodes, environments, network boundaries, configuration, secrets, external services, packaging, release, and rollback. For a library or build-time tool, describe how consumers receive and execute it.

### 9. 质量属性

Write observable requirements and connect them to design mechanisms:

| Quality Attribute | Requirement | Design Mechanism | Verification |
|---|---|---|---|

### 10. 验证策略

Describe static validation, automated tests, integration tests, smoke checks, observability, and operational probes that verify the design's important claims.

### 11. 与现有实现的关系

Classify retained, replaced, historical, and deprecated assets. Explain compatibility boundaries and precedence rules.

### 12. 未决问题

List only unresolved questions that affect architecture, scope, or implementation sequencing. Name the decision owner or trigger where possible.

## Separate Supporting Documents

Keep these outside the steady-state HLD unless the user explicitly asks for one combined document:

- migration phases and rollout order;
- implementation task breakdown;
- risk register;
- rollback runbook;
- review log;
- test execution evidence.
