# Phase 2 实施计划

## 1. Phase 目标

Phase 2 只解决一个问题：**把 WorkflowProgram-CN 的对外入口从 command-centric 收口为 skills-first**。

本阶段不处理：

- 动态运行验证落地
- agent teams 增强模式
- 根级兼容目录删除
- 正式插件安装方式定案
- `.claude/commands/` 的彻底移除

本阶段完成后，应达到以下状态：

1. 用户主入口变为 `workflowprogram-*` skills。
2. 旧 `/develop`、`/ship`、`/preflight`、`/hotfix`、`/evolve-workflow`、`/iterate-workflow` 继续可用，但被明确降级为兼容入口。
3. `.claude/settings.json` 中新增并注册新的对外 skills。
4. 文档中的主入口描述统一切换为 skills-first。
5. 构建产物 `dist/plugin/skills/` 能完整暴露新的 skills-first 接口。

## 2. 当前现状与冲突分析

### 2.1 当前对外入口仍以 commands 为中心

当前 `.claude/settings.json` 中：

- `commands` 注册了 6 个旧入口
- `skills` 只注册了辅助能力：`review`、`test`、`commit`、`doc`、`workflow-audit`、`validate-file`

这意味着：

- 当前用户真正可见的 WorkflowProgram 主能力仍然依赖 commands
- 现有 skills 主要是通用能力，不是 WorkflowProgram 的主编排接口

### 2.2 现有 `develop` skill 不能直接作为新主入口

当前仓库已存在：

- `.claude/skills/develop/SKILL.md`

它是内部支持资产，不是用户级工作流入口。

因此本阶段不能直接把用户主入口命名为 `develop` skill，否则会与现有目录职责冲突。

处理原则：

- 保留 `.claude/skills/develop/` 作为内部支持资产
- 新用户入口统一采用 `workflowprogram-*` 命名，避免与历史 command 和内部 support skill 混淆

### 2.3 现有 commands 仍承担完整能力定义

当前 `.claude/commands/*.md` 里包含完整流程逻辑。

如果直接新增 skills 而不调整旧 commands，会产生两个问题：

1. 新旧入口语义重复，用户难以判断主入口
2. 后续维护会形成“双主入口”

因此本阶段必须明确：

- 新 skills 承担主入口定义
- 旧 commands 降级为兼容 wrapper 或兼容说明

### 2.4 插件构建链与 settings 注册必须同步

`tools/build_plugin.py` 会把 `.claude/skills/` 复制到 `dist/plugin/skills/`。

这意味着：

- 新增 skills 不需要改构建逻辑主体
- 但必须保证 `.claude/settings.json` 与实际 skill 文件严格一致
- 否则源码层通过，运行时暴露仍会出现缺口

## 3. 影响范围

### 3.1 直接影响

- `.claude/settings.json`
- `.claude/skills/`
- `.claude/commands/`
- `README.md`
- `CLAUDE.md`
- `.claude-plugin/README.md`
- `.claude/scripts/validate-workflow.py`
- `.claude/scripts/validate-workflow.ps1`

### 3.2 间接影响

- `tools/build_plugin.py`
- `dist/plugin/skills/`
- `dist/plugin/commands/`
- `validation-report.md`

### 3.3 本阶段明确不动的范围

- `.claude/agents/` 提示词内容
- `.claude/rules/constraints.md` 的核心约束逻辑
- `tests/` 动态测试体系
- agent teams 相关设计
- 根级兼容目录删除动作

## 4. 文件动作清单

### 4.1 新建

- `.claude/skills/workflowprogram-orchestrate/SKILL.md`
  - 用途：总控入口，负责识别意图并路由到 develop / audit / iterate / validate

- `.claude/skills/workflowprogram-develop/SKILL.md`
  - 用途：面向目标项目的工作流设计主入口

- `.claude/skills/workflowprogram-audit/SKILL.md`
  - 用途：面向目标项目的工作流审计主入口

- `.claude/skills/workflowprogram-iterate/SKILL.md`
  - 用途：从经验日志生成改进建议

- `.claude/skills/workflowprogram-validate/SKILL.md`
  - 用途：对当前目标项目中的工作流资产执行结构化验证

### 4.2 更新

- `.claude/settings.json`
  - 更新点：新增 `workflowprogram-*` skills 注册；保留旧 commands 注册

- `.claude/commands/develop.md`
  - 更新点：降级为兼容入口；显式引导到 `workflowprogram-develop`

- `.claude/commands/evolve-workflow.md`
  - 更新点：降级为兼容入口；显式引导到 `workflowprogram-audit`

- `.claude/commands/iterate-workflow.md`
  - 更新点：降级为兼容入口；显式引导到 `workflowprogram-iterate`

- `.claude/commands/ship.md`
  - 更新点：标记为交付兼容命令；说明其在 skills-first 模型中的位置

- `.claude/commands/preflight.md`
  - 更新点：标记为兼容型准备命令；说明与验证 skill 的关系

- `.claude/commands/hotfix.md`
  - 更新点：标记为兼容型修复命令；不再作为主设计中心

- `README.md`
  - 更新点：对外使用说明改为以 `workflowprogram-*` skills 为主

- `CLAUDE.md`
  - 更新点：开发者说明改为 skills-first；commands 明确为兼容层

- `.claude-plugin/README.md`
  - 更新点：插件用法示例改成 skills-first

- `.claude/scripts/validate-workflow.py`
  - 更新点：新增对 `workflowprogram-*` skills 注册和文件存在性的校验

- `.claude/scripts/validate-workflow.ps1`
  - 更新点：与 Python 校验逻辑保持一致

### 4.3 可能需要小幅更新

- `tools/build_plugin.py`
  - 处理方式：只有在新 skill 命名、wrapper 生成或说明文案需要调整时再改
  - 当前判断：大概率无需改逻辑，只需复跑构建验证产物

### 4.4 本阶段不删除

以下对象本阶段不删除：

- `.claude/commands/*.md`
- 根级 `commands/`
- 根级 `skills/command-*`
- 旧用户可见 utility skills：`review`、`test`、`commit`、`doc`、`workflow-audit`

原因：

- 需要保留兼容性
- 需要给 Phase 3 的动态验证预留稳定入口
- 删除动作应放到 skills-first 跑通之后

## 5. 执行步骤

### Step 1: 审计现有入口职责边界

目标：确认旧 commands、现有 utility skills、内部 support skill 之间的职责分工。

执行内容：

- 盘点 `.claude/settings.json` 当前公开入口
- 盘点 `.claude/skills/` 当前目录职责
- 标记哪些能力属于“总控入口”、哪些属于“复用能力”、哪些属于“内部支持资产”
- 输出新旧入口对照表

产出：

- 一份入口边界审计文档，作为 skills-first 落地依据

### Step 2: 固定新的 skills-first 命名和职责

目标：确定 `workflowprogram-*` skills 的最小集合与边界。

建议集合：

- `workflowprogram-orchestrate`
- `workflowprogram-develop`
- `workflowprogram-audit`
- `workflowprogram-iterate`
- `workflowprogram-validate`

需要明确：

- 每个 skill 的输入范围
- 每个 skill 的输出目标
- 与旧 commands 的映射关系
- 哪些现有 utility skills 会被它们调用

产出：

- skill 命名与职责规范文档

### Step 3: 创建新的 skills-first 主入口

目标：新增 `workflowprogram-*` skills。

最低要求：

- 每个 skill 具有完整 frontmatter
- 每个 skill 明确说明其运行在 `TARGET_ROOT`
- 每个 skill 明确区分 `PLUGIN_ROOT` 和 `TARGET_ROOT`
- `workflowprogram-orchestrate` 明确作为总控入口
- 避免直接复制旧 command 的全部内容而不做职责收束

注意：

- 可以阶段性复用旧 commands 的流程语义
- 但文本定位必须改成“skill 是主入口，command 是兼容入口”

### Step 4: 更新 settings 和兼容入口

目标：让源码注册和兼容层定位一致。

执行内容：

- 更新 `.claude/settings.json` 的 `skills` 注册
- 保留 `commands` 注册
- 将旧 commands 改成兼容 wrapper / 兼容说明
- 在旧 commands 中显式标记推荐用户转向的新 skills

注意：

- 不在本阶段删除旧 command 文件
- 不在本阶段改变现有 utility skills 的公开性

### Step 5: 更新文档与校验脚本

目标：让文档、注册表、校验器保持一致。

执行内容：

- 更新 `README.md` 中的用户入口示例
- 更新 `CLAUDE.md` 中的开发入口说明
- 更新 `.claude-plugin/README.md` 中的插件用法示例
- 更新 `.claude/scripts/validate-workflow.py`
- 更新 `.claude/scripts/validate-workflow.ps1`

## 6. 风险点

### 风险 1：新旧入口重叠导致用户困惑

风险描述：

- 如果新 skills 建好了，但旧 commands 仍像主入口一样完整叙述，用户仍会被导向旧模式。

控制方式：

- 明确把旧 commands 改成兼容定位
- 在 README 和 CLAUDE 中统一把 skills 写为主入口

### 风险 2：内部 support skill 与新入口技能混淆

风险描述：

- 当前已有 `.claude/skills/develop/`
- 如果新入口命名不规范，会与内部 support skill 冲突

控制方式：

- 对外 skill 一律使用 `workflowprogram-*` 命名
- 内部 support skill 保持原职责，不直接暴露为主入口

### 风险 3：settings 注册和实际文件不一致

风险描述：

- 新增多个 skills 后，若 `.claude/settings.json`、校验脚本和实际文件不同步，会造成安装态与源码层不一致。

控制方式：

- 本阶段必须同步更新两套校验脚本
- 每一步改完后复跑结构校验和构建

### 风险 4：命令兼容层过早收缩影响现有可用性

风险描述：

- 如果旧 commands 直接被删或缩成过于空洞的占位内容，可能破坏现有调用方式。

控制方式：

- 本阶段保留旧 commands
- 只调整其定位，不移除基本说明和兼容信息

## 7. 验证方式

### 7.1 开发期默认验证

- `python3 .claude/scripts/validate-workflow.py`
- `powershell -ExecutionPolicy Bypass -File .claude/scripts/validate-workflow.ps1`
- `python3 tools/build_plugin.py`

验证点：

- 新增 `workflowprogram-*` skills 全部存在且被注册
- 原有 utility skills 不受影响
- 旧 commands 仍全部注册
- `dist/plugin/skills/` 中能看到新的 skills

### 7.2 发布前验证

本阶段暂不引入动态验证，但需要为 Phase 3 预留条件：

- skills-first 主入口命名稳定
- 兼容层仍可运行
- 文档已统一采用新主入口

## 8. Phase 完成定义

当以下条件同时满足时，Phase 2 可判定完成：

1. `workflowprogram-orchestrate`
2. `workflowprogram-develop`
3. `workflowprogram-audit`
4. `workflowprogram-iterate`
5. `workflowprogram-validate`

以上 5 个 skills 已全部存在、已注册、已通过结构校验。

同时满足：

- `README.md` 和 `CLAUDE.md` 已统一将主入口表述为 skills-first
- 旧 commands 已被标记为兼容入口
- `python3 tools/build_plugin.py` 能生成包含新 skills 的 `dist/plugin/`
