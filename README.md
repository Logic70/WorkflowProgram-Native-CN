# WorkflowProgram Native CN

[中文](README.md) | [English](README.en.md)

WorkflowProgram Native CN 是面向 Claude Code 工作区的元工作流插件。它不交付业务代码，而是帮助用户把 `.claude/` 工作流资产设计、生成、验证、受控写入并持续迭代。

## 它解决什么问题

很多 Claude Code workflow 一开始只是一个 `SKILL.md`、几个 agent 和少量手工配置。这样可以快速跑起来，但很容易出现：

- 文档、提示词和运行行为漂移
- 步骤顺序依赖模型记忆，容易漏步或重复
- 目标项目被直接覆盖，冲突和回滚不清楚
- 成功/失败缺少结构化证据
- 一次运行的经验无法沉淀到下一次

WPN 的核心目标是把 workflow 变成可维护的产品：有真源、有控制面、有验证层、有经验闭环。

## 安装

前置要求：宿主机可用 `Python 3.10+`。

推荐通过 Claude Code marketplace 安装：

```bash
claude plugin marketplace add Logic70/WorkflowProgram-Native-CN
claude plugin install workflowprogram-native-cn@logic70-plugins
```

如果已经在 Claude Code 交互界面中：

```text
/plugin marketplace add Logic70/WorkflowProgram-Native-CN
/plugin install workflowprogram-native-cn@logic70-plugins
/reload-plugins
```

安装后：

1. 重启 `claude`，或在当前会话执行 `/reload-plugins`
2. 首次启动时插件会在 `${CLAUDE_PLUGIN_DATA}/python/site-packages` 准备私有 Python 依赖
3. 排障时运行 `workflowprogram-doctor`
4. 清理插件缓存、测试产物或旧 run 时运行 `workflowprogram-clean`；默认 dry-run，删除必须加 `--apply`

如果出现 `Unknown skill: workflowprogram-orchestrate`，通常是插件未重新加载。先执行 `/reload-plugins` 或重启 `claude`，再使用 `/workflowprogram-native-cn:workflowprogram-orchestrate ...`。

## 快速使用

在目标项目中启动 Claude Code：

```bash
cd your-project
claude
```

直接用自然语言描述目标，优先让语义路由命中 `workflowprogram-orchestrate`：

```text
"为当前项目设计一个 code review workflow"
"审计当前项目的 workflow 结构"
"验证当前项目的 workflow 资产"
"把这个已经完成的 workflow 发布成 Claude Code 插件"
```

显式 slash command 只建议用于调试路由或自动命中失败时兜底：

```text
/workflowprogram-native-cn:workflowprogram-orchestrate 为当前项目设计一个 code review workflow
```

主要入口：

| 入口 | 用途 |
|------|------|
| `workflowprogram-develop` | 从需求澄清到候选资产生成、验证和受控写入 |
| `workflowprogram-audit` | 审计已有 workflow 结构和约定 |
| `workflowprogram-validate` | 对 workflow 资产生成验证 verdict |
| `workflowprogram-iterate` | 从 lessons 中生成改进建议 |
| `workflowprogram-publish` | 将已完成的目标 workflow 发布为 marketplace plugin |

## 当前能力边界

WPN 当前主路径是 Native Workflow JS authoring：产品级 `workflowprogram-develop.js` 负责 Clarify、Confirm、Design、Review、Generate、Validate、Smoke、Apply 和 Deliver 的状态推进。宿主侧脚本只执行窄化、可复验的动作，例如静态校验、candidate hash、managed apply、manifest 聚合和质量门禁。

默认交付目标是 `.claude/workflows/<name>.js`。只有在单文件 JS 不足以表达能力时，才通过 `supporting_assets` 显式生成 reusable skill、agent、领域脚本、compatibility command 或 authoring metadata。每个 supporting asset 必须有理由，并受受控路径白名单约束。

`managed-files` 是特殊 authoring metadata：它可以出现在报告中用于追踪受控写入意图，但不能作为普通 candidate 文件覆盖 `TARGET_ROOT/.workflowprogram/managed-files.json`。目标 manifest 由 `managed-assets.py apply-staged` 根据实际落盘结果、目标 hash、冲突处理和回滚信息维护。

已存在 `.workflowprogram/runtime/` 或历史设计 spec 的目标会被识别为需要人工迁移确认；WPN 不会自动套用历史链路，也不会自动重写这些文件。README 只描述当前 Native 主路径，兼容细节见设计文档。

## 核心模型

### 三根目录

| 目录 | 角色 | 说明 |
|------|------|------|
| `PLUGIN_ROOT` | 能力来源 | WPN 插件技能、工作流、脚本和模板，安装后视为只读 |
| `TARGET_ROOT` | 交付目标 | 用户项目根目录，最终 `.claude/` 资产只通过 managed apply 写入 |
| `RUN_ROOT` | 运行证据 | 单次运行隔离目录，通常位于 `TARGET_ROOT/.workflowprogram/runs/<run-id>/` |

### 阶段模型

| 阶段 | 职责 |
|------|------|
| S0 | 路由用户意图并准备目标环境 |
| S1 | 需求澄清，建立 purpose/object/process/decision/evidence/acceptance/boundary 逻辑 |
| S2 | 研究目标项目上下文和可复用资产 |
| S3 | 设计、审视和审批，形成可执行 authoring plan |
| S4 | 生成 candidate，执行受控写入前检查和 apply |
| S5 | 独立验证 workflow 行为和证据 |
| S6 | 回收 lessons 和长期约束候选 |

编排顺序由 Native workflow JS 和确定性脚本共同约束，不依赖模型记忆。

## 受控写入

WPN 不直接修改目标项目。写入流程是：

1. 将候选资产写入 `RUN_ROOT/outputs/candidate/`
2. 使用 `managed-assets.py plan` 生成变更计划
3. 用户批准后使用 `managed-assets.py apply-staged` 写入允许路径
4. 出现冲突时保留冲突副本，不静默覆盖用户文件
5. 写入结果更新 managed manifest、rollback manifest 和恢复说明

当前普通 candidate 写入范围限制在 `.claude/**`、`.workflowprogram/design/**` 和 `.workflowprogram/runtime/**`。扩展范围必须同时扩展 managed apply 规则、验证器和文档。

## 验证与发布

WPN 自身维护三层质量门禁：

| 门禁 | 命令 | 使用场景 |
|------|------|----------|
| Commit Gate | `python .claude/scripts/quality-gate.py commit` | 普通提交前快速检查 |
| Integration Gate | `python .claude/scripts/quality-gate.py integration` | 改到 runtime、schema、generator、publish 或 smoke harness 时 |
| Release Gate | `python .claude/scripts/quality-gate.py release` | 发布 WPN 插件版本前，验证源码和 `dist/plugin/` 产物 |

常用开发命令：

```bash
# 仓库结构校验
python .claude/scripts/validate-workflow.py

# Native workflow JS 静态校验
python .claude/scripts/validate-native-workflow-js.py --script <workflow.js> --json

# 运行单个 smoke fixture
python tools/runtime_smoke.py --fixture empty-project --runtime-provider fixture_host

# 运行 smoke 矩阵
python tools/runtime_smoke_matrix.py

# 重建插件载荷
python tools/build_plugin.py
```

发布目标 workflow 前，目标必须已经通过 develop、验证、managed evidence 和发布资格检查。真实 GitHub 写入仍要求用户显式批准；缺少仓库、权限、登录或 checkout 时会返回 `BLOCKED`，不会猜测性发布。

## 设计文档

README 只保留总览和操作入口。深入设计请看：

- [当前设计状态](docs/workflowprogram-design-status.md)
- [Native 控制面高层设计](docs/native-workflow-control-plane-highlevel-design.md)
- [Native 控制面低层设计](docs/native-workflow-control-plane-lowlevel-design.md)
- [阶段模型高层设计](docs/workflowprogram-stage-highlevel-design.md)
- [阶段模型低层设计](docs/workflowprogram-stage-lowlevel-design.md)
- [能力矩阵](docs/workflowprogram-capability-matrix.json)

## 项目结构

```text
workflowprogram-native-cn/
├── CLAUDE.md
├── README.md
├── README.en.md
├── lessons.md
├── .claude/
│   ├── commands/
│   ├── skills/
│   ├── agents/
│   ├── rules/
│   └── scripts/
├── .claude-plugin/
├── dist/plugin/
├── docs/
├── tests/
└── tools/
```

## 许可

MIT
