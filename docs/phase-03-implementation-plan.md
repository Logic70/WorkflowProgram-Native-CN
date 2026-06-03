# Phase 3 实施计划

## 1. Phase 目标

Phase 3 只解决一个问题：**把当前验证链从“结构正确 / 插件可发现”升级为“真实运行正确 / 有运行证据 / 可回溯”**。

本阶段不处理：

- agent teams 增强模式落地
- 根级兼容目录删除
- 正式插件安装方式定案
- 业务工作流的真实外部仓回归

本阶段完成后，应达到以下状态：

1. 至少有一套最小 fixture 可以作为 `TARGET_ROOT` 被真实运行。
2. 存在统一的运行时证据目录 `RUN_ROOT`。
3. 动态验证能落盘 `context.json`、`state.json`、`events.jsonl`、`transcript.md`、`validation-runtime-report.md`。
4. 至少一个主入口的运行结果可被自动判定为 PASS / FAIL / ENVIRONMENT-SKIP。
5. discovery-only 的 `verify-plugin-load.sh` 被降级，不再作为主验证依据。

## 2. 当前现状与缺口

### 2.1 当前验证主链仍是静态结构校验

当前主验证脚本：

- `.claude/scripts/validate-workflow.py`
- `.claude/scripts/validate-workflow.ps1`

它们能证明：

- 目录存在
- settings 注册一致
- commands/skills 结构正确
- 新增的 `workflowprogram-*` skills 已注册

但不能证明：

- `workflowprogram-*` skills 真能在目标项目目录运行
- `TARGET_ROOT/.claude/` 真会被写入或读取
- 运行期是否生成 `RUN_ROOT`
- subagent 是否真的参与执行

### 2.2 当前 `verify-plugin-load.sh` 只是发现性检查

现有 `.claude/scripts/verify-plugin-load.sh` 只做一件事：

- 调 Claude CLI 看 skill/command 是否能被发现

它的问题是：

- 把“未登录”也视为 PASS
- 不验证产物写入
- 不验证运行证据
- 不验证 subagent 参与痕迹

结论：

- 它不能继续作为动态验证主链
- 只能保留为 discovery smoke 或被替换

### 2.3 当前 `state-bus.py` 不是运行验证 harness

现有 `.claude/scripts/state-bus.py` 提供：

- 状态持久化
- stage 转换
- checkpoint
- 历史查看

它的问题是：

- 默认路径仍偏向插件源码仓内部 `.claude/session-state.json`
- 没有 `RUN_ROOT` 概念
- 没有事件日志模型
- 没有 transcript 输出
- 没有对 Claude 运行结果的自动判定能力

结论：

- 可以复用其中的状态结构思想
- 但必须更新为面向 `TARGET_ROOT/.workflowprogram/runs/<run-id>/` 的模型

### 2.4 测试夹具当前不存在

当前仓库还没有：

- `tests/fixtures/`
- `tests/expectations/`
- `tests/transcripts/`
- `tools/runtime_smoke.py`

这意味着：

- 动态验证从零开始
- 需要先固定最小样例和环境失败判定逻辑

## 3. 影响范围

### 3.1 直接影响

- `tests/`
- `tools/`
- `.claude/scripts/state-bus.py`
- `.claude/scripts/validate-workflow.py`
- `.claude/scripts/validate-workflow.ps1`
- `.claude/scripts/verify-plugin-load.sh`
- `validation-report.md`

### 3.2 间接影响

- `README.md`
- `CLAUDE.md`
- `dist/plugin/scripts/`
- `dist/plugin/skills/`

### 3.3 本阶段明确不动的范围

- `.claude/skills/` 的语义重构
- `.claude/commands/` 的删除
- agent teams 实际接入
- 根级兼容目录清理

## 4. 文件动作清单

### 4.1 新建

- `tests/fixtures/empty-project/`
- `tests/fixtures/existing-workflow/`
- `tests/fixtures/broken-workflow/`
- `tests/expectations/`
- `tests/transcripts/.gitkeep`
- `tools/runtime_smoke.py`
- `docs/phase-03-step-01-runtime-validation-audit.md`
- `docs/phase-03-step-02-runtime-evidence-spec.md`
- `docs/phase-03-step-03-fixture-plan.md`

### 4.2 更新

- `.claude/scripts/state-bus.py`
  - 更新点：从源码仓内部会话状态，改成支持 `RUN_ROOT` 的运行态证据模型

- `.claude/scripts/validate-workflow.py`
  - 更新点：区分 L0/L1 结构校验与 L2 动态验证入口说明

- `.claude/scripts/validate-workflow.ps1`
  - 更新点：与 Python 版一致

- `README.md`
  - 更新点：补充动态验证说明和开发验证 / 发布验证分层

- `CLAUDE.md`
  - 更新点：补充 `RUN_ROOT`、events 和 transcript 说明

- `validation-report.md`
  - 更新点：追加动态验证结果记录

### 4.3 替换或降级

- `.claude/scripts/verify-plugin-load.sh`
  - 处理方式：降级为 discovery-only 检查，或者由 `tools/runtime_smoke.py` 取代其主验证地位

## 5. 执行步骤

### Step 1: 审计现有验证能力

目标：明确当前哪些脚本和文档可复用，哪些只能视为历史资产。

执行内容：

- 审计 `validate-workflow.py` / `validate-workflow.ps1`
- 审计 `state-bus.py`
- 审计 `verify-plugin-load.sh`
- 审计文档中已有的运行态设计

产出：

- 一份运行验证现状审计文档

### Step 2: 固定运行时证据模型

目标：定义 `RUN_ROOT` 的目录和文件契约。

最低要求：

- `context.json`
- `state.json`
- `events.jsonl`
- `transcript.md`
- `validation-runtime-report.md`
- `outputs/`

需要明确：

- 事件字段
- 结果状态
- 环境失败与业务失败的区分
- subagent 参与的证据标准

### Step 3: 设计 fixture 体系

目标：创建最小但可判定的目标项目样例。

最低集合：

- `empty-project`
- `existing-workflow`
- `broken-workflow`

需要明确：

- 每个 fixture 的目标
- 预期输出
- 通过/失败判定

### Step 4: 实现 runtime smoke harness

目标：创建 `tools/runtime_smoke.py`。

最低能力要求：

- 调用 Claude CLI 对 `dist/plugin/` 做真实运行
- 支持指定 fixture
- 创建 `RUN_ROOT`
- 落盘运行证据
- 返回统一的 PASS / FAIL / ENVIRONMENT-SKIP

### Step 5: 收口验证入口和报告

目标：让仓库文档和校验脚本知道动态验证的地位。

执行内容：

- 将 `verify-plugin-load.sh` 降级
- 更新 README / CLAUDE
- 追加 `validation-report.md`

## 6. 风险点

### 风险 1：本地 Claude 环境不可用

风险描述：

- 未登录、版本不匹配、CLI 行为变化都会导致运行测试无法稳定执行。

控制方式：

- 动态验证必须区分 `FAIL` 与 `ENVIRONMENT-SKIP`
- 不允许把环境失败误记为运行成功

### 风险 2：没有可靠的 subagent 证据

风险描述：

- 即使 workflow 执行完成，也未必能证明 subagent 实际参与。

控制方式：

- 在事件模型中为 subagent 参与设定明确证据字段
- Phase 3 只要求“至少一个可判定 evidence source”，不强行假设所有事件都可获得

### 风险 3：fixture 过于理想化

风险描述：

- 如果 fixture 太简单，可能无法代表真实目标项目。

控制方式：

- 先做最小样例，确保 harness 成立
- Phase 4 以后再逐步扩充

## 7. 验证方式

### 7.1 开发期默认验证

- `python3 .claude/scripts/validate-workflow.py`
- `powershell.exe -ExecutionPolicy Bypass -File .claude/scripts/validate-workflow.ps1`
- `python3 tools/build_plugin.py`

### 7.2 发布前动态验证

- `python3 tools/runtime_smoke.py --fixture empty-project`
- 至少一个 fixture 完成真实运行或给出明确的 `ENVIRONMENT-SKIP`

验证点：

- `RUN_ROOT` 已创建
- `events.jsonl` 已生成
- `transcript.md` 已生成
- `validation-runtime-report.md` 已生成
- 能区分结构失败、运行失败、环境失败

## 8. Phase 完成定义

当以下条件同时满足时，Phase 3 可判定完成：

1. 存在 `tools/runtime_smoke.py`
2. 存在至少 1 个可运行 fixture
3. 存在统一的 `RUN_ROOT` 证据结构
4. `verify-plugin-load.sh` 已被降级或替代
5. `validation-report.md` 已记录至少一次动态验证结果
