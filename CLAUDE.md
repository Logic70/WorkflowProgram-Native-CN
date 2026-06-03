# WorkflowProgram-CN

## 项目概述

WorkflowProgram-CN 是一个面向 Claude Code 风格工作区的元工作流仓库。
它不提供业务应用源码，而是提供一组可复用的命令、技能、Agent、
规则和校验脚本，用来设计、交付、审计和迭代其他工作流仓库。

## 技术栈

- 文档与配置：Markdown、JSON
- 自动化与校验：Python、PowerShell
- 运行环境：Claude Code 工作区命令体系
- 数据库：无

## 架构说明

本仓库采用分层工作流结构：

- `CLAUDE.md`
  项目级说明，进入工作区时优先读取。
- `.claude/settings.json`
  用户可见命令与技能的共享注册表。
- `.claude/settings.local.json`
  本机权限与本地覆盖配置，不应作为共享工作流逻辑依赖。
- `.claude/commands/`
  工作流编排入口，如 `/develop`、`/ship`、`/evolve-workflow`。
- `.claude/skills/`
  可复用技能模板，如审查、测试、文档和工作流审计。
- `.claude/agents/`
  专家角色定义，用于设计或内联子代理提示词。
- `.claude/rules/`
  持久化约束与演进规则。
- `.claude/scripts/`
  可执行校验脚本，使仓库能够被自动验证。

- `dist/plugin/` 是正式安装产物目录，由 `tools/build_plugin.py` 从 `.claude/` 和 `.claude-plugin/` 构建生成。

经验法则：
可确定、可复验的检查放到脚本里；
流程编排放到 commands 和 skills；
角色职责放到 agents；
长期有效的约束沉淀到 rules。

## 核心能力

- `workflowprogram-orchestrate`
  作为 skills-first 总控入口，负责将自然语言请求路由到正确主能力；当前只放开它承接自然语言自动触发。
- `workflowprogram-develop`
  面向 `TARGET_ROOT` 设计或更新 workflow 资产，产出的是工作流文件，不是应用代码。
- `workflowprogram-audit`
  审计目标工作流仓库，识别结构和模式问题。
- `workflowprogram-iterate`
  从 `lessons.md` 生成改进草案，展示 diff，待批准后再应用。
- `workflowprogram-validate`
  对目标项目中的 workflow 资产执行结构化验证。
- `/ship`、`/preflight`、`/hotfix`
  保留为当前仓库的维护兼容入口，不作为目标项目的主产品 API。

## 项目结构

```text
WorkflowProgram-CN/
|-- CLAUDE.md
|-- README.md
|-- lessons.md
|-- validation-report.md
|-- .claude/
|   |-- settings.json
|   |-- settings.local.json
|   |-- agents/
|   |-- commands/
|   |-- rules/
|   |-- scripts/
|   `-- skills/
|-- .claude-plugin/
|-- dist/plugin/
|-- docs/
|-- tests/
`-- tools/
```

## Primary Skills

面向目标项目的主入口统一采用 skills-first：

- `workflowprogram-orchestrate`
- `workflowprogram-develop`
- `workflowprogram-audit`
- `workflowprogram-iterate`
- `workflowprogram-validate`

这些 skill 面向 `TARGET_ROOT` 工作，不应与当前仓库维护命令混用。

## Compatibility Commands

工作流入口命令：

- `/develop <requirement>`
  根据需求设计新工作流，并按阶段完成规格、设计、生成与校验。
- `/ship [<scope>]`
  顺序执行审查、验证与提交准备。
- `/preflight [<scope>]`
  执行并行化的预检查与就绪性汇总。
- `/hotfix [<description>]`
  执行热修复专用精简流程。
- `/evolve-workflow [options] <workflow-path>`
  审计并演进目标工作流仓库。
- `/iterate-workflow [--dry-run] [--apply] [<workflow-path>]`
  从经验沉淀中生成审批优先的工作流改进草案。

## Skills

辅助/复用技能：

- `/review`
- `/test`
- `/commit`
- `/doc`
- `/workflow-audit`

内部支持资产：

- `.claude/skills/workflow-spec-support/spec-template.md`
  `/develop` 生成 `workflow-spec.md` 时使用的规格模板。

## Plugin Runtime Model

- 源码真源：`.claude/`
- 安装产物：`dist/plugin/`
- trace manifest：`dist/plugin/build-manifest.json`
- 目标项目交付位置：`TARGET_ROOT/.claude/`
- managed 资产清单：`TARGET_ROOT/.workflowprogram/managed-files.json`
- 运行证据位置：`TARGET_ROOT/.workflowprogram/runs/<run-id>/`
- Agent 双层定义：`.claude/agents/` -> `dist/plugin/agents/`
- 受支持的发现模型：`claude --plugin-dir <dist/plugin>`
- 受支持的显式入口：`/workflowprogram-*`
- `~/.claude` 覆盖式安装不属于正式稳态契约，只能视为实验性开发路径

## Development Commands

- Run：在 Claude Code 中打开本仓库后直接调用上述命令
- Commit Gate：`python3 .claude/scripts/quality-gate.py commit`
- Integration Gate：`python3 .claude/scripts/quality-gate.py integration`
- Release Gate：`python3 .claude/scripts/quality-gate.py release`
- Full Repository Validator：
  - Windows: `powershell -ExecutionPolicy Bypass -File .claude/scripts/validate-workflow.ps1`
  - macOS/Linux: `python3 .claude/scripts/validate-workflow.py`
- Runtime Smoke：`python3 tools/runtime_smoke.py --fixture empty-project`
- Managed Assets：`python3 .claude/scripts/managed-assets.py plan ...`
- Lint：同上
- Build：`python3 tools/build_plugin.py`

## 规则

- NEVER 直接在 `main` 分支上提交。
- ALWAYS 保持 `.claude/settings.json` 与实际对外命令、技能同步。
- ALWAYS 保持 `README.md`、`lessons.md` 和 `.claude/rules/constraints.md` 存在。
- ALWAYS 在命令或技能中为可独立运行的子代理内联完整提示词。
- NEVER 让子代理在运行时依赖外部 agent 文件。
- NEVER 在单次 fan-out 阶段中超过 4 个并行代理。
- ALWAYS 把可复用的失败经验和流程教训记录到 `lessons.md`。
- ALWAYS 若未来增加 hooks，保持其轻量、同步、可解释。

## Testing Rules

- 日常提交默认运行 `python3 .claude/scripts/quality-gate.py commit`，不要把每个小改动都升级成完整 smoke matrix。
- 涉及 runtime、runner、finalizer、schema、生成器、publish/package 或测试 harness 的改动，必须运行 `python3 .claude/scripts/quality-gate.py integration`。
- 发布 WorkflowProgram 插件版本前必须运行 `python3 .claude/scripts/quality-gate.py release`；发布门禁包含构建、版本一致性、完整仓库校验、插件 bootstrap 和 deterministic smoke matrix。
- 新增用户可见命令或技能时，必须同步更新 `README.md`、`CLAUDE.md` 和 `.claude/settings.json`。
- 可复用的长期约束应写入 `.claude/rules/constraints.md`。

## Lessons 机制

本仓库使用三层机制管理经验沉淀：

```
┌──────────────────────────────────────────────────────────────┐
│  constraints.md  ← 新会话只加载此文件                        │
│  - 精简的 ALWAYS/NEVER 规则                                  │
│  - 每次会话前加载到 AI 上下文                                │
│  - 由 /iterate-workflow 或人工从 lessons 提取                │
└──────────────────────────────────────────────────────────────┘
                              ▲
                              │ (定期提取)
┌──────────────────────────────────────────────────────────────┐
│  lessons.md  ← 只追加，不读取（或仅读最新3条）               │
│  - 记录失败经验和 Constraints To Extract                     │
│  - 类似日志，最多保留10条，旧记录归档到 lessons-archive/     │
│  - 由 /develop 等命令在失败时写入                            │
└──────────────────────────────────────────────────────────────┘
                              ▲
                              │ (会话内读写)
┌──────────────────────────────────────────────────────────────┐
│  session-findings.md  ← 可选，当前会话缓存                   │
│  - 会话内的临时上下文                                        │
│  - 会话结束后可选择归档或删除                                │
└──────────────────────────────────────────────────────────────┘
```

**关键原则**：
- `constraints.md` 是**长期记忆**，精简且结构化
- `lessons.md` 是**短期日志**，记录后定期归档
- 新会话**只加载 constraints.md**，避免上下文膨胀
