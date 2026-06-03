# WorkflowProgram-CN 技能优先插件化重构设计

> Historical Note
>
> 本文档保留为历史设计与问题追溯材料，不再作为当前运行时真源。
> 当前真源和已关闭决策见 [workflowprogram-design-status.md](/mnt/d/Code/WorkflowProgram-CN/docs/workflowprogram-design-status.md)。

## 1. 文档目的

本文档用于固定 `WorkflowProgram-CN` 的插件化稳态架构，避免后续边实现边改架构。

本文回答四个问题：

1. 最终插件形态应该是什么。
2. 开发视图、运行视图、用户视图如何划分。
3. 最终测试方案应该如何落地。
4. 面对当前仓库中的现有文件，分别应该保留、更新、替换、新建、删除还是归档。

Phase 1 到 Phase 4 的结构收口已经完成；本文档现在同时承担两类职责：

1. 记录已经落地的稳态设计契约
2. 记录仍未闭环的软件生命周期缺口

因此，本文档不再只是“未来方案草图”，而是当前仓库的设计基线。

## 2. 历史问题与剩余缺口

本仓库在 Phase 1 到 Phase 4 之前，曾有三个核心结构问题：

1. 插件自身上下文和目标项目上下文容易混淆。
   - 当前设计仍带有“在 `WorkflowProgram-CN` 仓库里开发别的工作流”的痕迹。
   - 实际使用时，很容易混淆插件自己的 `.claude/` 和目标项目自己的 `.claude/`。

2. 仓库长期处于过渡态。
   - `.claude/` 被视为源码层。
   - 根级 `commands/`、`skills/`、`agents/`、`rules/`、`scripts/` 是同步产物。
   - 这导致同一份能力被重复表达，长期会产生漂移。

3. 当前验证仍然偏浅。
   - 已有静态结构校验。
   - 已有插件发现校验。
   - 但还没有把“真实运行、真实 subagent 调用、真实目标项目产物、真实运行证据”作为默认验证主链。

以上三类问题已经在当前工作区中基本收口。当前需要显式管理的，是 6 个生命周期层面的问题：前 4 项仍属未闭环缺口，后 2 项已在 Phase 5 做了最小工程化实现，但还未扩展成完整发布运维能力。

1. **插件发现契约缺失**
   - 文档没有明确写清 Claude Code 为什么能在不修改用户 `~/.claude` 的前提下识别到 WorkflowProgram 的 skills、agents、commands。

2. **安装模型双轨冲突**
   - 一部分文档假设 `claude --plugin-dir <dist/plugin>`。
   - 另一部分脚本又尝试把产物复制到 `~/.claude/`。
   - 这两种模型的发现路径、隔离性和升级方式并不一致。

3. **调用契约不统一**
   - 文档里混用了自然语言调用、`workflowprogram-*`、`workflowprogram:*`、`/workflowprogram-*` 等多种写法。
   - 这会直接影响 README、自动化脚本、runtime smoke 和用户心智模型。

4. **安装后生命周期未闭环**
   - 还没有正式定义升级、卸载、版本兼容和安装后验证契约。
   - 因此当前只能说“源码/构建/runtime 已闭环”，不能说“分发/维护也已闭环”。

5. **目标项目资产所有权契约曾缺失**
   - 当前已补充 `managed-assets.py` 与 `managed-files.json` 的最小实现。
   - 但还没有保证所有写入入口都已强制接入这条链。

6. **发布产物可追溯性曾缺失**
   - 当前已补充 `dist/plugin/build-manifest.json`。
   - 但还没有正式签名、安装时验真或团队分发闭环。

## 3. 目标架构

### 3.1 核心结论

`WorkflowProgram-CN` 应重构为一个**用户级 Claude Code 插件源码仓**。

安装完成后，用户应当直接在**目标项目目录**中，通过自然语言或显式 skill 调用 WorkflowProgram 的能力来生成、审计和迭代工作流。

`WorkflowProgram-CN` 本身不再作为“运行时工作目录”。

### 3.2 核心原则

- `.claude/` 是唯一源码真源。
- `dist/plugin/` 是仓库内 canonical 运行时载荷目录。
- `skills` 是主入口。
- `commands` 如保留，只做兼容层。
- 运行时产物写入目标项目，不写回插件源码仓。
- 默认执行模型使用 `subagents`。
- `agent teams` 仅作为增强模式，不作为基础依赖。
- agent 采用双层定义：源码定义位于 `.claude/agents/`，插件运行时暴露位于 `dist/plugin/agents/`。

## 4. 开发视图

### 4.1 目标目录结构

```text
WorkflowProgram-CN/
├── .claude/                      # 唯一源码真源
│   ├── skills/
│   ├── agents/
│   ├── rules/
│   ├── scripts/
│   └── settings.json
├── .claude-plugin/               # 插件元数据
├── tools/
│   ├── build_plugin.py
│   ├── validate_source.py
│   ├── validate_package.py
│   └── runtime_smoke.py
├── tests/
│   ├── fixtures/
│   ├── expectations/
│   └── transcripts/
├── dist/
│   └── plugin/                   # 仓库内 canonical 运行时载荷目录
├── docs/
├── README.md
├── CLAUDE.md
├── lessons.md
└── validation-report.md
```

### 4.2 开发期职责划分

- `.claude/`：可编辑源码层
- `.claude-plugin/`：插件清单和安装元数据
- `tools/`：构建、校验、动态测试工具
- `dist/plugin/`：生成产物，不手工编辑
- `tests/`：目标项目夹具、动态验证记录
- `docs/`：设计和架构文档

### 4.3 和当前仓库的冲突点

当前仓库存在以下重复层：

- `.claude/*` 源资产
- 根级 `commands/*`
- 根级 `skills/*`
- 根级 `agents/*`
- 根级 `rules/*`
- 根级 `scripts/*`
- `tools/sync_plugin_assets.py` 直接把源码同步为根级资产

这说明当前仓库同时存在：

1. 源码层
2. 兼容产物层

迁移期可以接受，但不能作为最终形态长期保留。

## 5. 运行视图

### 5.1 三根路径模型

为了彻底避免路径和上下文混淆，运行期必须显式区分三类路径：

- `PLUGIN_ROOT`
  - 插件安装目录
  - 只读
  - 用于读取模板、规则、skills、subagent 定义

- `TARGET_ROOT`
  - 用户当前项目目录
  - 所有工作流交付都写到这里

- `RUN_ROOT`
  - `TARGET_ROOT/.workflowprogram/runs/<run-id>/`
  - 存储本次运行的状态、事件、转录、产物摘要和验证报告

### 5.2 运行目录结构

```text
<TARGET_ROOT>/
├── .claude/                          # 最终交付的工作流资产
└── .workflowprogram/
    └── runs/<run-id>/
        ├── context.json
        ├── state.json
        ├── events.jsonl
        ├── transcript.md
        ├── outputs/
        ├── validation-runtime-report.md
        └── summary.md
```

### 5.3 默认运行流程

```text
用户请求
-> /workflowprogram-orchestrate ...
-> 识别 TARGET_ROOT
-> 从 PLUGIN_ROOT 加载资产
-> 分阶段编排
-> 在需要时调度 subagents
-> 将正式工作流写入 TARGET_ROOT/.claude/
-> 将过程证据写入 RUN_ROOT
-> 输出总结
```

### 5.4 主会话与 subagent 的职责边界

主会话负责：

- 目标项目识别
- 阶段编排
- fan-out 决策
- 结果汇总
- 最终结论和报告写入

subagent 负责：

- 工作流设计
- 工作流审计
- 测试场景生成
- 运行时验证
- 聚焦型评审任务

### 5.5 为什么 agent teams 不是基础方案

`agent teams` 仅作为增强模式，原因如下：

- 基础运行链必须稳定、可回放、可复现
- 默认验证链不能依赖实验能力
- 当前仓库现有设计本身更接近 `subagents` 模型

因此最终原则是：

- 默认：`主会话 + subagents`
- 增强：`agent teams`

## 5A. Plugin 运行时模型

### 5A.1 自动加载与显式暴露

需要明确区分三种层次：

- 源码层：`.claude/*`
  - 这是仓库内部的开发真源
  - 不等于插件安装后的自动加载目录

- 插件产物层：`dist/plugin/*`
  - 这是 Claude Code 插件运行时实际消费的目录
  - 其中 `dist/plugin/skills/` 和 `dist/plugin/agents/` 是对外暴露的运行时资产

- 目标项目层：`TARGET_ROOT/.claude/`
  - 这是插件执行后写入目标项目的最终工作流资产

### 5A.2 Agent 的正确位置模型

Agent 不应再被描述成“只有根级 `agents/` 才是真正定义库”。

本方案的正确表达是：

- 源码定义：`.claude/agents/`
- 插件运行时定义：`dist/plugin/agents/`

也就是说：

- `.claude/agents/` 负责维护源定义
- 构建脚本负责把它们转成插件运行时可见的 `dist/plugin/agents/`
- Skill 调用时面向的是插件运行时暴露的 agent，而不是直接把 `.claude/agents/` 当安装态目录

### 5A.3 建议补充的安装模型

当前设计必须区分“受支持路径”和“实验路径”，不能继续把两者混写。

**当前受支持的安装 / 验证模型**：

- Source Build 通道（仓库内）：
  - 先运行 `python3 tools/build_plugin.py`
  - 再通过 `claude --plugin-dir <abs-path-to-dist/plugin>` 加载插件
  - Claude Code 从 `PLUGIN_ROOT` 发现 skills、agents、commands、rules、scripts

- GitHub Release Package 通道（发布包）：
  - 下载并解压 release 附件（包含 `plugin/`）
  - 校验 `plugin/build-manifest.json` 与 release 版本一致
  - 通过 `claude --plugin-dir <abs-path-to-extracted-plugin-dir>` 加载

说明：

- `dist/plugin/` 是仓库内 canonical 载荷目录，不等于唯一可能安装绝对路径
- 安装本质上是“加载同构插件载荷目录”，不是强绑定仓库路径

这条路径的特点是：

- 发现来源明确
- 和 `RUN_ROOT` / `TARGET_ROOT` 模型一致
- 不污染用户自己的 `~/.claude` 资产
- 最适合做开发验证和发布前验证

**当前不属于受支持稳态模型的路径**：

- 将 `dist/plugin/` 复制到用户 `~/.claude/`
- 在未验证 marketplace 行为前，直接宣称 `/plugin install` 为正式安装路径

这些路径可以保留为实验性脚本或后续扩展，但不能继续被主文档表述为等价正式方案。

### 5A.4 Claude Code 插件发现契约

Claude Code 识别 WorkflowProgram 能力的前提，不是用户目录里存在这些 skill 文件，而是：

1. WorkflowProgram 被作为 plugin 加载
2. Claude Code 将加载目录视为 `PLUGIN_ROOT`
3. Claude Code 从 `PLUGIN_ROOT` 中发现运行时资产

当前约定的运行时资产位置如下：

- `PLUGIN_ROOT/skills/`
  - 对外 skill 入口与兼容 wrapper
- `PLUGIN_ROOT/agents/`
  - 供 plugin 运行时引用的 agent 定义
- `PLUGIN_ROOT/commands/`
  - 兼容 slash 入口
- `PLUGIN_ROOT/rules/`
  - 运行时规则引用
- `PLUGIN_ROOT/scripts/`
  - 运行时脚本引用
- `PLUGIN_ROOT/.claude-plugin/`
  - 插件元数据

其中：

- `.claude-plugin/plugin.json` 和 `marketplace.json` 负责描述插件元数据
- `dist/plugin/skills/`、`dist/plugin/agents/`、`dist/plugin/commands/` 才是 Claude Code 运行时真正消费的目录

因此，**`~/.claude` 不是 WorkflowProgram 插件能力发现的必要前提**。

### 5A.5 对外调用契约

当前唯一受支持的显式调用语法是 **slash skill / slash command 入口**：

- `/workflowprogram-orchestrate <request>`
- `/workflowprogram-develop <request>`
- `/workflowprogram-audit <target>`
- `/workflowprogram-iterate <target>`
- `/workflowprogram-validate <target>`

兼容入口如下：

- `/develop`
- `/evolve-workflow`
- `/iterate-workflow`
- `/ship`
- `/preflight`
- `/hotfix`

约束如下：

- `workflowprogram-*` 是产品主入口
- 兼容 commands 只用于迁移和仓库维护，不是用户主 API
- 纯自然语言触发可以作为易用性增强，但不能作为发布验证的唯一契约
- 当前自然语言优化策略只放开 `workflowprogram-orchestrate` 承接自动触发；叶子 skill 继续以显式 slash 为主

### 5A.6 Stage 输出可验证契约

为避免“Stage 目标和输出只能靠主观判断”，本设计要求每个关键阶段都产生可判定证据：

- 路由阶段：`RUN_ROOT/outputs/stages/s0-route.json`
- 需求阶段：`RUN_ROOT/workflow-spec.md`（不得包含 `TBD`）
- 研究阶段：`RUN_ROOT/outputs/stages/s2-context-report.md`
- 设计阶段：`RUN_ROOT/workflow-spec.yaml`、`RUN_ROOT/workflow-view.md`
- 生成阶段：`RUN_ROOT/outputs/candidate/.claude/` + managed plan/result
- 验证阶段：`validation-runtime-report.md` + `RUN_ROOT/outputs/stages/s5-validation-summary.json`
- 闭环阶段：`RUN_ROOT/outputs/stages/s6-lessons-delta.md`
- 进展播报：`RUN_ROOT/outputs/progress/current-progress.json`、`milestones.jsonl`、`user-progress.md`

进展播报应统一通过：

- `${CLAUDE_PLUGIN_ROOT}/scripts/stage-progress.py`

判定原则：

- 每个阶段至少有一个机读证据文件
- 每个阶段的准出条件都应映射为可检查字段或文件存在性检查
- 若证据缺失，该阶段默认不通过

### 5A.7 用户目录边界

`~/.claude` 在当前设计中只保留 Claude Code 自己的用户级配置语义。

WorkflowProgram 的正式契约不要求：

- 将 skill/agent 复制到 `~/.claude/skills` 或 `~/.claude/agents`
- 依赖用户目录中的全局文件来完成 plugin 发现

如果未来需要支持“用户级全局安装”，必须单独新增一份安装契约，明确：

- 安装位置
- 升级策略
- 卸载方式
- 与用户现有 `~/.claude` 资产的冲突处理

### 5A.7 目标项目资产所有权与更新契约

除了插件自身的安装与发现，WorkflowProgram 还必须明确它对 `TARGET_ROOT/.claude/` 的写入边界。

当前设计要求后续实现至少满足以下规则：

1. **只管理自己声明过的目标文件**
   - WorkflowProgram 只能把“由自己创建或登记为 managed 的文件”视为可直接更新对象。
   - 未登记为 managed 的现有目标文件，不能被静默覆盖。

2. **目标项目必须存在一份 managed 资产清单**
   - 建议位置：`TARGET_ROOT/.workflowprogram/managed-files.json`
   - 至少记录：
     - `relative_path`
     - `producer_version`
     - `last_applied_hash`
     - `ownership`（如 `managed` / `user-owned` / `external`）

3. **重复执行时必须先做冲突判断**
   - 如果目标文件属于 managed，且当前 hash 与上次记录一致，可以直接更新。
   - 如果目标文件属于 managed，但当前 hash 已变化，必须视为“用户或外部过程修改过”，不能静默覆盖。
   - 如果目标文件不在 managed 清单中，只能新建同名候选产物或报冲突，不能直接替换。

4. **冲突时优先保留用户资产**
   - 当 WorkflowProgram 发现 managed 文件已被用户修改，应把候选新版本写入 `RUN_ROOT/outputs/`，并在报告中明确冲突原因。
   - 只有在显式确认后，才允许把候选版本覆盖回 `TARGET_ROOT/.claude/`。

5. **所有写入都应可回溯**
   - 每次写入目标项目时，都应在 `RUN_ROOT` 中记录本次 planned changes、最终 applied changes 和相关文件 hash。
   - 这也是后续实现原子写入、回滚和升级策略的前提。

Phase 5 的最小工程化实现已经补上：

- `${CLAUDE_PLUGIN_ROOT}/scripts/managed-assets.py`
- `TARGET_ROOT/.workflowprogram/managed-files.json`
- `RUN_ROOT/outputs/managed-change-plan.json`
- `RUN_ROOT/outputs/managed-change-result.json`
- `RUN_ROOT/outputs/managed-change-summary.md`

## 6. 用户视图

### 6.1 用户目标

安装完成后，用户应当能够留在目标项目目录中直接说：

```text
帮我给当前项目设计一个 Claude Code 工作流
```

或使用当前受支持的显式入口：

```text
/workflowprogram-develop 为当前项目生成工作流
```

用户不应再需要：

- 进入 `WorkflowProgram-CN` 仓库
- 手工分辨插件资产和目标项目资产
- 手工搬运生成文件

### 6.2 对外入口

正式对外入口应改为 skills-first：

- `/workflowprogram-orchestrate`
- `/workflowprogram-develop`
- `/workflowprogram-audit`
- `/workflowprogram-iterate`
- `/workflowprogram-validate`

旧 command 可以临时保留，但只能作为兼容层，不再是架构中心。

### 6.3 用户如何感知插件已生效

用户不需要去检查 `~/.claude/` 下是否出现 WorkflowProgram 文件。

当前设计下，更可靠的判断方法是：

1. Claude Code 通过 `--plugin-dir <dist/plugin>` 成功启动
2. `/workflowprogram-orchestrate ...` 等入口可被识别
3. 在 `TARGET_ROOT` 中执行后，`TARGET_ROOT/.workflowprogram/runs/<run-id>/` 被创建
4. 最终产物写入 `TARGET_ROOT/.claude/`

## 7. 最终测试方案

### 7.1 方案定案

最终测试方案为分层默认：

- 开发默认：`L0 + L1`
- 发布默认：`L2`
- 增强模式：`L3 (agent teams)`

其中运行执行模型仍然是：

- 默认主链：`主会话 + subagents + hooks + 隔离 worktree`
- 增强模式：`agent teams`

这意味着仓库未来不再依赖：

- 纯文本静态校验
- 只验证插件是否被发现
- 递归式 `subagent -> subagent` 假设

### 7.2 测试分层

#### L0 源码结构校验

检查内容：

- `.claude/settings.json` 一致性
- 源 skill 结构完整性
- agent 自包含性
- rules 完整性
- 模板与脚本存在性

#### L1 插件打包校验

检查内容：

- `dist/plugin/` 是否完整
- plugin manifest 是否和产物一致
- 生成结果是否是最新构建结果
- 最终模型下是否还残留陈旧根级产物

#### L2 运行时 Smoke Test

这是发布和正式验收时的默认验证主链。

在 fixture 目标项目中真实执行插件并验证：

- skill 能否在目标项目里运行
- 目标 `.claude/` 是否被正确写入
- `RUN_ROOT` 是否被创建
- 预期 subagent 是否被触发
- `events.jsonl` 和 `validation-runtime-report.md` 是否存在

#### L3 高级并行验证

这是可选增强层，仅用于复杂并行场景：

- 多视角评审
- 竞争式方案设计
- 对抗式安全验证

这一层不是插件最小可用条件。

### 7.3 运行证据模型

每次动态运行至少要产出：

- `context.json`
- `state.json`
- `events.jsonl`
- `transcript.md`
- `validation-runtime-report.md`

关键事件类型建议统一记录：

- `SubagentStart`
- `SubagentStop`
- `TaskCreated`
- `TaskCompleted`
- `PreToolUse`
- `PostToolUse`
- `Stop`

### 7.4 安装后验证分层

除了源码校验和 runtime smoke，生命周期还需要一个“安装后验证”层，用于回答：

- 构建出来的 plugin 是否真的可被 Claude Code 发现
- 发现到的入口是否与文档契约一致
- 运行时引用路径是否全部落在 `PLUGIN_ROOT`

当前最小安装后验证链应为：

1. `python3 tools/build_plugin.py`
2. discovery-only 校验：
   - `claude -p --plugin-dir <dist/plugin> --output-format json "/workflowprogram-develop smoke-test"`
3. runtime smoke：
   - `python3 tools/runtime_smoke.py --fixture empty-project --json`

其中 discovery-only 校验只证明“入口可发现”，不能替代 runtime smoke。

### 7.5 生命周期剩余缺口

在当前设计补完“发现 / 安装 / 调用契约”，并完成 Phase 5 的最小工程化实现之后，仍然有以下 6 个未闭环项：

1. **正式发布安装契约未定**
   - marketplace 安装、离线安装、团队分发仍未完成实测定案

2. **升级 / 回滚 / 卸载契约缺失**
   - 当前没有定义已安装插件如何升级、如何回滚、如何安全卸载

3. **版本兼容矩阵缺失**
   - 尚未写清 Claude Code 版本、平台差异、CLI 行为变化对 WorkflowProgram 的影响边界

4. **目标项目写入的原子性与回滚缺失**
   - 还没有定义当 `TARGET_ROOT/.claude/` 写到一半失败时，应如何回滚或恢复

5. **RUN_ROOT 保留与清理策略缺失**
   - 运行证据会持续累积，但尚未定义 retention、归档和清理策略

6. **发布态验真与全入口覆盖仍未闭环**
   - `dist/plugin/build-manifest.json` 和 `managed-assets.py` 已落地
   - 但仍没有正式签名 / 安装时验真机制，也还没有证明所有会写入 `TARGET_ROOT/.claude/` 的入口都强制接入了 managed-assets 链

以上缺口不推翻当前架构，但意味着“发布运维生命周期”仍未完全成型。

## 8. 文件级冲突分析与动作定义

本节只定义后续重构时每类文件的动作，不立即执行。

动作类型：

- `keep`
- `update`
- `replace`
- `create`
- `delete`
- `archive`

### 8.1 作为源码保留的现有文件

以下文件保留为源码资产：

- `.claude/agents/logic-reviewer.md`
- `.claude/agents/performance-reviewer.md`
- `.claude/agents/security-reviewer.md`
- `.claude/agents/style-reviewer.md`
- `.claude/agents/test-scenario-generator.md`
- `.claude/agents/workflow-designer.md`
- `.claude/agents/workflow-validator.md`
- `.claude/agents/workflow-verifier.md`

说明：以上是**源码层 agent 定义**，不是插件安装后的最终暴露位置；最终暴露位置应由构建链生成到 `dist/plugin/agents/`。
- `.claude/rules/constraints.md`
- `.claude/skills/commit/SKILL.md`
- `.claude/skills/develop/SKILL.md`
- `.claude/skills/develop/spec-template.md`
- `.claude/skills/develop/test-scenarios-template.md`
- `.claude/skills/develop/yaml-spec-template.md`
- `.claude/skills/doc/SKILL.md`
- `.claude/skills/review/SKILL.md`
- `.claude/skills/test/SKILL.md`
- `.claude/skills/validate-file/SKILL.md`
- `.claude/skills/workflow-audit/SKILL.md`

原因：

- 这些文件仍然是当前仓库里最有价值的能力资产
- 它们符合“源码真源”定位
- 不需要用破坏性方式全部推倒重建

### 8.2 需要更新的现有文件

#### 插件和注册层

- `.claude/settings.json`
  - 动作：`update`
  - 改动：切换到 skills-first 注册方式，兼容 wrapper 要显式标记为兼容层

- `.claude-plugin/plugin.json`
  - 动作：`update`
  - 改动：反映最终插件结构和运行契约

- `.claude-plugin/README.md`
  - 动作：`update`
  - 改动：改为说明“安装后如何在目标项目中使用”

#### 文档层

- `README.md`
  - 动作：`update`
  - 改动：面向用户，说明安装、目标项目使用方式和动态验证方式

- `CLAUDE.md`
  - 动作：`update`
  - 改动：面向开发者，说明源码层、构建链、运行模型和迁移规则

- `lessons.md`
  - 动作：`update`
  - 改动：只保留插件开发与验证经验，不再混入下游目标项目执行日志

- `validation-report.md`
  - 动作：`update`
  - 改动：改成 L0/L1/L2/L3 分层验证记录

#### 脚本层

- `.claude/scripts/validate-workflow.py`
  - 动作：`update`
  - 改动：成为源码校验真源

- `.claude/scripts/validate-workflow.ps1`
  - 动作：`update`
  - 改动：作为 Windows 包装入口，与 Python 真源保持一致

- `.claude/scripts/state-bus.py`
  - 动作：`update`
  - 改动：如果继续保留，需要对齐 `RUN_ROOT`、事件模型和运行状态记录

#### 命令层

- `.claude/commands/develop.md`
  - 动作：`update`
  - 改动：从主入口降级为兼容入口，与新的 skills-first 模型对齐

- `.claude/commands/evolve-workflow.md`
  - 动作：`update`
  - 改动：同上

- `.claude/commands/hotfix.md`
  - 动作：`update`
  - 改动：同上

- `.claude/commands/iterate-workflow.md`
  - 动作：`update`
  - 改动：同上

- `.claude/commands/preflight.md`
  - 动作：`update`
  - 改动：同上

- `.claude/commands/ship.md`
  - 动作：`update`
  - 改动：同上

### 8.3 需要替换的过渡文件

- `tools/sync_plugin_assets.py`
  - 动作：`replace`
  - 替代为：`tools/build_plugin.py`
  - 原因：最终产物应输出到 `dist/plugin/`，而不是继续维护根级重复资产

- `.claude/scripts/verify-plugin-load.sh`
  - 动作：`replace`
  - 替代为：运行时 smoke test 包装脚本
  - 原因：当前脚本只验证发现，不验证功能

### 8.4 需要新建的文件

#### 新的对外 skills

- `.claude/skills/workflowprogram-orchestrate/SKILL.md`
  - 动作：`create`

- `.claude/skills/workflowprogram-develop/SKILL.md`
  - 动作：`create`

- `.claude/skills/workflowprogram-audit/SKILL.md`
  - 动作：`create`

- `.claude/skills/workflowprogram-iterate/SKILL.md`
  - 动作：`create`

- `.claude/skills/workflowprogram-validate/SKILL.md`
  - 动作：`create`

#### 构建和校验工具

- `tools/build_plugin.py`
  - 动作：`create`

- `tools/validate_source.py`
  - 动作：`create`

- `tools/validate_package.py`
  - 动作：`create`

- `tools/runtime_smoke.py`
  - 动作：`create`

#### 测试夹具与期望

- `tests/fixtures/empty-project/`
  - 动作：`create`

- `tests/fixtures/existing-workflow/`
  - 动作：`create`

- `tests/fixtures/broken-workflow/`
  - 动作：`create`

- `tests/expectations/`
  - 动作：`create`

- `tests/transcripts/.gitkeep`
  - 动作：`create`

#### 架构记录文档

- `docs/adr/002-skills-first-plugin-architecture.md`
  - 动作：`create`

- `docs/adr/003-runtime-validation-strategy.md`
  - 动作：`create`

### 8.5 迁移完成后删除的目录

以下目录当前是兼容层或同步产物，只有在 `dist/plugin/` 稳定后才删除：

- `commands/`
  - 动作：`delete`

- `skills/`
  - 动作：`delete`

- `agents/`
  - 动作：`delete`

- `rules/`
  - 动作：`delete`

- `scripts/`
  - 动作：`delete`

注意：

- 这些不是第一步立即删除
- 只有满足以下条件才删：
  - `build_plugin.py` 已落地
  - `dist/plugin/` 已可完整生成
  - L0/L1/L2 验证全部通过

### 8.6 建议归档的历史文档

以下文件建议移动到 `docs/archive/`，而不是直接删除：

- `review_report.md`
- `实施方案V3.md`
- `实施计划-Plugin架构迁移.md`

原因：

- 它们属于历史设计资产
- 仍有参考价值
- 继续留在仓库根目录会干扰当前主结构

## 9. 推荐实施顺序

进入任何一个 Phase 之前，必须先输出该 Phase 的**具体实施计划**，作为执行前的操作指引。

每个 Phase 的实施计划至少包含以下内容：

1. 目标
2. 影响范围
3. 需要新增的文件
4. 需要更新的文件
5. 需要替换或删除的文件
6. 执行顺序
7. 风险点
8. 验证方式

如果某个 Phase 内部仍然过大，则必须继续拆成更小的子步骤，在执行前逐步确认。

### Phase 1

先确定源码和产物边界。

- 新建 `tools/build_plugin.py`
- 定义 `dist/plugin/`
- 停止把根级同步目录当长期维护资产

#### Phase 1 实施计划模板

**目标**

- 固定 `.claude/` 为源码真源
- 固定 `dist/plugin/` 为仓库内 canonical 运行时载荷目录
- 明确根级兼容目录只是迁移期资产

**影响范围**

- `tools/`
- `dist/`
- 根级 `commands/`、`skills/`、`agents/`、`rules/`、`scripts/`
- `README.md`
- `CLAUDE.md`

**需要新增的文件**

- `tools/build_plugin.py`
- `dist/plugin/.gitkeep` 或等价初始化文件

**需要更新的文件**

- `README.md`
- `CLAUDE.md`
- `.claude-plugin/README.md`

**需要替换的文件**

- `tools/sync_plugin_assets.py` -> 新的构建逻辑

**执行顺序**

1. 审查当前根级同步目录和 `.claude/` 的映射关系
2. 设计新的 `dist/plugin/` 产物布局
3. 实现 `tools/build_plugin.py`
4. 保留旧同步逻辑直到新构建链可运行
5. 更新文档，声明 `dist/plugin/` 的 canonical 载荷地位与安装通道契约

**风险点**

- 新构建脚本与现有 plugin manifest 不一致
- 根级兼容目录仍被其他脚本引用
- 构建产物与源资产之间的路径替换逻辑不完整

**验证方式**

- 能从 `.claude/` 成功生成 `dist/plugin/`
- `dist/plugin/` 具备完整插件结构
- 现有功能在迁移期不被破坏
- 文档中不再把根级同步目录描述为长期维护资产

### Phase 2

落地新的 skills-first 对外接口。

- 新建 `workflowprogram-*` skills
- 更新 `.claude/settings.json`
- 将旧 commands 收缩成兼容 wrapper

#### Phase 2 实施计划模板

**目标**

- 将用户入口从 command-centric 切换为 skills-first
- 保留旧 commands 的兼容性，但不再作为主设计中心

**影响范围**

- `.claude/settings.json`
- `.claude/skills/`
- `.claude/commands/`
- `.claude-plugin/plugin.json`
- `README.md`

**需要新增的文件**

- `.claude/skills/workflowprogram-orchestrate/SKILL.md`
- `.claude/skills/workflowprogram-develop/SKILL.md`
- `.claude/skills/workflowprogram-audit/SKILL.md`
- `.claude/skills/workflowprogram-iterate/SKILL.md`
- `.claude/skills/workflowprogram-validate/SKILL.md`

**需要更新的文件**

- `.claude/settings.json`
- 现有 `.claude/commands/*.md`
- `.claude-plugin/plugin.json`

**需要替换或降级的文件**

- 旧 command 入口改为兼容说明，不再承担主能力定义

**执行顺序**

1. 定义新的技能命名规范和职责边界
2. 创建 `workflowprogram-*` skills
3. 更新 `.claude/settings.json`
4. 收缩旧 command 内容到兼容 wrapper
5. 更新 README 中的用户入口说明

**风险点**

- settings 注册与实际技能文件不一致
- 新旧入口语义重叠，导致用户仍被导向旧模式
- 插件 manifest 对 skills 的暴露方式和预期不一致

**验证方式**

- 新技能能被 Claude Code 正常发现
- 旧命令仍可兼容使用
- 文档中的主入口已统一为 skills-first
- 不存在未注册的对外技能

### Phase 3

落地动态验证。

- 新建 fixtures
- 新建 runtime smoke harness
- 替换 discovery-only 校验

#### Phase 3 实施计划模板

**目标**

- 把默认验证链从“结构正确”升级到“运行正确”
- 为 subagent 行为提供真实证据和可回溯记录

**影响范围**

- `tests/`
- `tools/`
- `.claude/scripts/`
- `validation-report.md`
- `lessons.md`

**需要新增的文件**

- `tests/fixtures/empty-project/`
- `tests/fixtures/existing-workflow/`
- `tests/fixtures/broken-workflow/`
- `tests/expectations/`
- `tests/transcripts/.gitkeep`
- `tools/runtime_smoke.py`

**需要更新的文件**

- `.claude/scripts/validate-workflow.py`
- `.claude/scripts/validate-workflow.ps1`
- `.claude/scripts/state-bus.py`
- `validation-report.md`

**需要替换的文件**

- `.claude/scripts/verify-plugin-load.sh`

**执行顺序**

1. 设计运行时证据格式：`context.json`、`state.json`、`events.jsonl`、`transcript.md`
2. 创建最小 fixture 项目
3. 实现 `tools/runtime_smoke.py`
4. 替换 discovery-only 校验脚本
5. 将运行结果写入 `validation-report.md`

**风险点**

- 本地 Claude 运行环境与 CI 环境行为不一致
- 事件模型定义不足，无法证明 subagent 真正参与
- fixture 设计过于理想化，不能覆盖典型失败场景

**验证方式**

- 至少一个 fixture 能完成端到端运行
- `RUN_ROOT` 被正确创建
- 至少一个预期 subagent 有明确事件记录
- 能区分结构失败、运行失败和环境失败

### Phase 4

清理过渡资产。

- 删除根级生成目录
- 归档历史方案文档

#### Phase 4 实施计划模板

**目标**

- 从稳态架构中去除迁移期兼容层
- 收敛仓库结构，降低长期维护成本

**影响范围**

- 根级 `commands/`
- 根级 `skills/`
- 根级 `agents/`
- 根级 `rules/`
- 根级 `scripts/`
- 根级历史设计文档

**需要归档的文件**

- `review_report.md`
- `实施方案V3.md`
- `实施计划-Plugin架构迁移.md`

**需要删除的目录**

- `commands/`
- `skills/`
- `agents/`
- `rules/`
- `scripts/`

**执行顺序**

1. 先确认 `dist/plugin/` 已稳定且通过验证
2. 归档历史设计文档到 `docs/archive/`
3. 删除根级兼容目录
4. 更新 README 和 CLAUDE 中的结构说明

**风险点**

- 仍有脚本或文档引用根级兼容目录
- 删除兼容目录后，某些本地验证路径失效
- 历史文档归档后失去可追溯索引

**验证方式**

- 仓库中不再依赖根级兼容目录
- 所有引用均已切换到 `.claude/` 或 `dist/plugin/`
- 插件构建和运行验证仍然通过
- 历史文档可在 `docs/archive/` 中追溯

## 10. 验收标准

只有当以下条件全部满足，重构才算完成：

1. 用户安装 WorkflowProgram 后可以直接在目标项目目录使用它。
2. 插件上下文和目标项目上下文不再混淆。
3. `.claude/` 是唯一源码真源。
4. `dist/plugin/` 是仓库内 canonical 运行时载荷目录，并已定义 Source Build / GitHub Release 安装通道。
5. 默认验证链基于真实动态执行和 subagent 证据。
6. `agent teams` 只是增强模式，不是强依赖。
7. 根级生成兼容目录不再属于稳态架构的一部分。

## 11. 当前状态

截至当前工作区状态：

- Phase 1：源码层 / 安装产物层边界已经落地
- Phase 2：`workflowprogram-*` 主入口已经存在并注册
- Phase 3：runtime smoke、fixtures、RUN_ROOT 证据模型已经落地
- Phase 4：根级兼容目录和旧同步链已经移除

因此，本文档不再描述“是否应该开始重构”，而是描述：

1. 当前稳态架构是什么
2. Claude Code 应如何发现和调用 WorkflowProgram 能力
3. 还有哪些生命周期缺口需要后续 phase 单独处理
