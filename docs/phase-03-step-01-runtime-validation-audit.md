# Phase 3 Step 1 运行验证现状审计

> Historical Note
>
> 本文档保留为 Phase 3 的运行验证审计记录，不再单独定义当前 S5/S6 或 runtime evidence 契约。
> 当前真源和已关闭决策见 [workflowprogram-design-status.md](/mnt/d/Code/WorkflowProgram-CN/docs/workflowprogram-design-status.md)。

## 1. 目的

本审计用于确认当前仓库在“动态验证”方面已经有什么、缺什么，以及哪些现有资产可以复用到 Phase 3。

## 2. 现有验证资产盘点

### 2.1 结构校验器

当前存在两套结构校验脚本：

- `.claude/scripts/validate-workflow.py`
- `.claude/scripts/validate-workflow.ps1`

当前能力：

- 校验核心路径存在
- 校验 commands 注册一致性
- 校验 skills frontmatter
- 校验 5 个 `workflowprogram-*` 主入口 skills 已注册
- 校验 `constraints.md` 具备 ALWAYS / NEVER

当前不足：

- 不创建或检查 `RUN_ROOT`
- 不验证目标项目 `.claude/` 的读写结果
- 不验证 runtime transcript
- 不验证 subagent 参与痕迹
- 不区分环境失败与运行失败

结论：

- 这两套脚本应继续保留为 L0/L1 验证
- 不能单独充当 L2 动态验证

### 2.2 Plugin 发现性检查

当前存在：

- `.claude/scripts/verify-plugin-load.sh`

当前能力：

- 调用 Claude CLI 检查命令/skill 是否能被发现

关键问题：

- 把“未登录”也视为 PASS
- 只证明 discovery，不证明 execution
- 不产出运行期证据目录
- 不关注 `TARGET_ROOT`
- 不验证 `workflowprogram-*` 主入口的行为正确性

结论：

- 该脚本应在 Phase 3 被降级为 discovery-only smoke
- 不应继续作为主验证依据

### 2.3 状态总线脚本

当前存在：

- `.claude/scripts/state-bus.py`
- 参考文档：[state-bus.md](/mnt/d/Code/WorkflowProgram-CN/docs/state-bus.md)

当前能力：

- 初始化会话状态
- stage 切换
- 键值写入/读取
- checkpoint / restore
- 状态与历史查看

关键问题：

- 默认路径是 `.claude/session-state.json`
- 以插件源码仓内部状态为中心，而非 `TARGET_ROOT` 运行态
- 没有统一事件流文件
- 没有 transcript 文件
- 没有 runtime verdict
- 还不是 smoke harness

结论：

- 其中“状态 + 检查点”模型可复用
- 但必须重构到 `RUN_ROOT`，不能原样拿来当 Phase 3 动态验证器

## 3. 运行态证据现状

当前仓库里还不存在以下对象：

- `tests/fixtures/`
- `tests/expectations/`
- `tests/transcripts/`
- `tools/runtime_smoke.py`
- `RUN_ROOT` 契约
- `events.jsonl`
- `transcript.md`
- `validation-runtime-report.md`

这意味着：

- Phase 3 不是优化现有 harness，而是新建最小动态验证链

## 4. 当前可复用的设计约束

从现有设计文档中，可以直接复用这些约束：

- 运行期必须区分 `PLUGIN_ROOT`、`TARGET_ROOT`、`RUN_ROOT`
- 默认执行模型是 `主会话 + subagents`
- `agent teams` 不是基础方案
- 动态验证应至少证明：
  - `RUN_ROOT` 创建成功
  - 运行证据已落盘
  - 至少一个预期 subagent 有明确 evidence source

这些约束主要来自：

- [workflowprogram-skills-first-redesign.md](/mnt/d/Code/WorkflowProgram-CN/docs/workflowprogram-skills-first-redesign.md)
- [CLAUDE.md](/mnt/d/Code/WorkflowProgram-CN/CLAUDE.md)

## 5. 现状结论

当前仓库已经具备：

- 稳定的源码层验证
- 清晰的 skills-first 主入口
- 可构建的 `dist/plugin/`

但仍缺少 Phase 3 所需的 4 个核心能力：

1. 目标项目 fixture
2. 运行时证据契约
3. 动态 smoke harness
4. 基于运行证据的自动判定逻辑

## 6. 对下一步实现的约束

### 6.1 不要把 `verify-plugin-load.sh` 硬改成主 harness

原因：

- 它的设计目标本来就只是 discovery smoke
- 直接在上面堆逻辑会让责任边界继续混乱

建议：

- 保留它作为轻量发现检查
- 新建 `tools/runtime_smoke.py` 承担运行验证主链

### 6.2 不要把 `state-bus.py` 原样当作 smoke harness

原因：

- 它是状态工具，不是运行 orchestration 工具
- 其默认路径模型与 `RUN_ROOT` 不一致

建议：

- 复用其状态结构思想
- 但以 `tools/runtime_smoke.py` 为主入口
- 后续再决定是否把 state-bus 下沉成 runtime_smoke 的内部模块

### 6.3 动态验证必须显式区分环境失败

原因：

- Claude CLI 未登录、版本不符、运行能力受限时，不能把测试失败误判为 workflow 失败

建议：

- 在 runtime report 中加入明确状态：`PASS / FAIL / ENVIRONMENT-SKIP`

## 7. 审计结论

Phase 3 的首要任务不是“改更多文档”，而是建立一条新的最小运行验证链：

- fixture
- `RUN_ROOT`
- `runtime_smoke.py`
- 动态验证报告

现有脚本中：

- `validate-workflow.py` / `validate-workflow.ps1` 应保留并继续承担 L0/L1
- `verify-plugin-load.sh` 应降级
- `state-bus.py` 需要重构或被 runtime harness 吸收
