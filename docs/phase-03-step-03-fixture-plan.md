# Phase 3 Step 3 Fixture 设计计划

## 1. 目的

本计划用于固定 Phase 3 动态验证所需的最小 fixture 集合，确保 `tools/runtime_smoke.py` 有可执行、可判定、可回溯的目标项目样例。

## 2. 设计原则

fixture 必须满足：

1. 面向 `TARGET_ROOT` 真实运行
2. 通过条件可自动判定
3. 失败原因可被归类
4. 尽量小，不引入无关业务代码

## 3. 最小 fixture 集合

### 3.1 `tests/fixtures/empty-project/`

**目标**

- 验证 `workflowprogram-develop` 能在一个几乎空白的目标目录上建立最小 workflow 资产

**初始状态**

- 只有最小 README 或占位文件
- 不存在 `.claude/`

**预期结果**

- 创建 `TARGET_ROOT/.workflowprogram/runs/<run-id>/`
- 运行 evidence 文件齐全
- 至少生成或规划 `.claude/` 下的关键资产
- 若因环境问题无法运行，明确返回 `ENVIRONMENT-SKIP`

### 3.2 `tests/fixtures/existing-workflow/`

**目标**

- 验证 `workflowprogram-audit` / `workflowprogram-validate` 能处理一个已有基础 workflow 的项目

**初始状态**

- 存在最小可接受的 `.claude/` 结构
- 包含 `settings.json`、至少一个 skill、至少一个 rule 文件

**预期结果**

- 生成审计或验证报告
- `RUN_ROOT` 和证据文件完整
- 能输出结构化 findings 或 validation verdict

### 3.3 `tests/fixtures/broken-workflow/`

**目标**

- 验证 `workflowprogram-validate` / `workflowprogram-audit` 能识别明显损坏的 workflow 结构

**初始状态**

- 缺失关键文件
- 或存在错误注册、错误 frontmatter、缺失 rules 等问题

**预期结果**

- 结果为 `FAIL` 或明确的结构失败分类
- 失败项在 report 中可读
- 运行证据目录仍完整

## 4. 目录建议

```text
tests/
├── fixtures/
│   ├── empty-project/
│   ├── existing-workflow/
│   └── broken-workflow/
├── expectations/
└── transcripts/
```

## 5. expectations 设计

建议为每个 fixture 准备最小期望说明文件，例如：

- `tests/expectations/empty-project.md`
- `tests/expectations/existing-workflow.md`
- `tests/expectations/broken-workflow.md`

每份期望至少说明：

- 入口 skill
- 预期结果状态
- 关键输出文件
- 可接受的环境跳过条件

## 6. 通过/失败判定原则

### 6.1 `empty-project`

通过条件：

- `RUN_ROOT` 存在
- 证据文件齐全
- 至少有一个 workflow 设计输出或明确的设计计划

### 6.2 `existing-workflow`

通过条件：

- `RUN_ROOT` 存在
- 证据文件齐全
- 有审计或验证结论

### 6.3 `broken-workflow`

通过条件：

- `RUN_ROOT` 存在
- 证据文件齐全
- 结果明确为失败或结构问题，不允许“误通过”

## 7. 执行顺序

1. 先创建 `empty-project`
2. 再创建 `existing-workflow`
3. 最后创建 `broken-workflow`
4. 同步写入 expectations

原因：

- `empty-project` 最容易验证 harness 是否能真正跑通
- `existing-workflow` 用于验证审计与验证主入口
- `broken-workflow` 用于验证失败路径是否可判定

## 8. 约束

- fixture 内不要放真实业务代码
- fixture 应尽量小，便于重复执行
- fixture 中的 `.claude/` 内容只保留验证所需最小集合

## 9. 结论

Phase 3 不需要一开始就有复杂样例。最小可行策略是：

- 先让 `empty-project` 跑通
- 再补 `existing-workflow`
- 最后用 `broken-workflow` 锁定失败路径
