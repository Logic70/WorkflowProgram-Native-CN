---
name: workflowprogram-validate
description: Validate workflow assets in the current target project at workflow scope
version: 1.0.0
disable-model-invocation: true
---

面向 `TARGET_ROOT` 的 workflow 级验证主入口。负责对目标项目中的 workflow 资产执行统一校验，不等同于仓库维护命令 `/preflight`。

普通用户请求应优先从 `/workflowprogram-cn:workflowprogram-orchestrate <需求>` 进入；本 skill 是 orchestrate 选择 `validate` intent 后的 leaf 入口，也可用于高级显式调试。

## Native Default Entry

默认解析插件绝对路径并调用：

```text
Workflow({
  scriptPath: "<PLUGIN_ROOT>/workflows/workflowprogram-validate.js",
  args: { ... }
})
```

前台模型只负责按 `nextAction` 补充 candidate-bound 静态校验和外部验证证据，再重新调用同一 JS。不得在 skill 中复制 Native JS 的 Discover、Static Validate、External Verify 和 Report 顺序。

## When To Use

- 验证当前项目的 `.claude/` 资产是否齐全
- 在生成或修改 workflow 后做结构化校验
- 为后续审计或交付提供统一验证结论

## Core Rules

- 当前验证对象是 `TARGET_ROOT/.claude/`，不是插件源码仓。
- `preflight` 面向当前仓库 diff；本 skill 面向目标项目 workflow 资产。
- 单文件检查优先复用 `validate-file`；workflow 级结论由本 skill 汇总输出。
- 若项目已有专门 workflow 验证命令，可作为补充信息纳入结果。
- 若存在 `RUN_ROOT/workflow-spec.yaml` 且其中声明了 `test_contract`，验证目标应优先从 `entry / boundary / flow / artifacts / failure` 五类契约派生。
- 执行期边界、最小证据集、失败枚举与环境 skip 仍以 `runtime_contract` 为准，`test_contract` 只负责判定来源。
- S5 judge 是唯一验证主承载；runner 只负责 `runner-summary.json`，不负责 `validation-runtime-report.md` 或 `s5-validation-summary.json`。
- 验证阶段必须通过 `${CLAUDE_PLUGIN_ROOT}/scripts/workflow-s5-judge.py`（或等效 harness）写入：
  - `RUN_ROOT/validation-runtime-report.md`
  - `RUN_ROOT/outputs/stages/s5-validation-summary.json`

## Step 1: Resolve Validation Scope

1. 确认 `TARGET_ROOT` 和待验证的 workflow 根路径。
2. 列出关键目标：`settings.json`、`skills/`、`agents/`、`rules/`、必要时的 `commands/`。
3. 判断是全量验证还是指定范围验证。

## Step 2: Run Checks

1. 对关键文件调用 `validate-file`。
2. 汇总目录级存在性、注册一致性和文件格式状态。
3. 若存在 `test_contract`，将检查项映射到：
   - `entry`：主入口、缺参、非法入口预期
   - `boundary`：写入边界引用、managed 覆盖/冲突/外部写入策略
   - `flow`：required/skippable stages、失败回流、终止条件
   - `artifacts`：关键交付物、关键证据、可缺失非关键输出
   - `failure`：失败枚举引用、环境 skip 引用、`implemented_now` 覆盖度
4. 如有必要，补充调用 `test` 运行项目定义的 workflow 校验命令。
5. 将所有检查项按五类契约归档给 S5 judge，不能只输出 `contract_source` / `contract_categories` 元数据摘要。

## Step 3: Produce Verdict

输出统一结论：

- PASS
- WARN
- FAIL
- ENVIRONMENT-SKIP

并说明：

- 失败项
- 影响范围
- 修复优先级
- 每个检查项来源于哪类契约
- runner 与 S5 judge 的职责边界

## Output

输出应包含：

- 验证目标路径
- 覆盖范围
- 总体结论
- 失败或警告清单
- `s5-validation-summary.json` 路径
- 若存在 `test_contract`，输出 `contract_source` 与 `contract_categories`
- `validation-runtime-report.md` 路径
