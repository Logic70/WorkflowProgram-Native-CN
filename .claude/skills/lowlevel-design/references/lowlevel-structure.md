# General Low-Level Design Structure

Use this structure for implementation-ready software design. Adapt sections to the target; mark irrelevant sections `不适用` with a reason.

```markdown
# <System> Low-Level Design

## 1. 设计输入与范围
## 2. HLD 决策映射
## 3. 目录、文件与模块结构
## 4. 组件详细设计
## 5. 接口与协议
## 6. 数据结构、Schema 与持久化
## 7. 状态机、不变量与生命周期
## 8. 关键流程与时序
## 9. 错误分类、恢复与回滚
## 10. 配置、依赖与部署细节
## 11. 安全、可观测性与运维
## 12. 测试设计
## 13. 需求与实现追踪矩阵
## 14. 未决问题
```

## Required Detail

### HLD Decision Mapping

| HLD Decision | LLD Mechanism | Artifact | Verification |
|---|---|---|---|

### Module Contract

| Module | Responsibility | Inputs | Outputs | Dependencies | Failure Behavior | Tests |
|---|---|---|---|---|---|---|

### State Transition

| Current State | Event | Guard | Next State | Side Effect | Failure |
|---|---|---|---|---|---|

### Error Taxonomy

| Error Code or Kind | Detection Point | User or Caller Feedback | Recovery | Evidence |
|---|---|---|---|---|

### Test Mapping

| Scenario | Level | Fixture or Setup | Expected Result | Evidence |
|---|---|---|---|---|

## Rules

- Keep the LLD consistent with the HLD source of truth.
- Name exact files, interfaces, schemas, enums, and validation rules.
- Use pseudocode only when implementation language is undecided.
- State concurrency and idempotency behavior when writes or retries exist.
- Keep rollout sequencing outside the steady-state LLD.
