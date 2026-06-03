<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->

# WorkflowProgram Constraints

来源：2026-03-20 仓库基线整理，2026-03-31 从 lessons 提取。

## 仓库不变量

- ALWAYS 保持 `README.md`、`CLAUDE.md`、`lessons.md` 和 `.claude/rules/constraints.md` 存在。
- ALWAYS 保持 `.claude/settings.json` 与对外命令、技能的真实状态同步。
- ALWAYS 在示例路径中优先使用仓库内相对路径，除非工作流明确需要外部目标路径。
- NEVER 把 `.claude/settings.local.json` 当作共享工作流逻辑的一部分。

## 命令设计

- ALWAYS 为用户可见命令保留 `## Usage` 段。
- ALWAYS 将用户可见命令组织为编号阶段，并为阶段提供 `Goal` 与 `Verify`。
- ALWAYS 将可复用的失败经验或上下文缺口记录到 `lessons.md`。
- ALWAYS 在 orchestrate 路由到 develop 的 Stage 3 完成后，向用户展示设计文档并获得明确批准，再进入 Stage 4 文件生成；`/develop` 仅作为兼容入口。
- ALWAYS 在命令设计中考虑非交互（CI/CD）模式下 gate 的行为：支持通过 prompt 参数或环境变量预批准。
- ALWAYS 通过 control-plane helper 调用高约束控制面脚本，不要让模型手工拼严格 CLI 参数。
- NEVER 在单个 fan-out 阶段中超过 4 个并行代理。
- NEVER 让子代理运行时依赖外部 agent 文件，只要可以内联提示词就必须内联。
- NEVER 在未经验证的情况下声明工作流"创建完成"。
- NEVER 把 `stage-progress.py` 这类严格参数词表的控制面脚本暴露成模型主路径。

## 技能与 Agent 设计

- ALWAYS 为每个 `SKILL.md` 提供 `name`、`description`、`version` frontmatter。
- ALWAYS 当用户以自然语言表达“为当前项目设计 / 审计 / 迭代 / 验证 workflow”时，优先路由到 `workflowprogram-orchestrate`；显式 marketplace 使用优先推荐 `/workflowprogram-cn:workflowprogram-orchestrate <需求>`。
- ALWAYS 为审查类和校验类 Agent 明确输出格式。
- ALWAYS 为 AI Agent 提供结构化方法论（Step 1/2/3...），不只给"关注点"列表。
- NEVER 同时让多个 `workflowprogram-*` 叶子 skill 承担自然语言自动触发职责。
- NEVER 漏掉任何被命令直接引用的支持资产。

## 工作流提取

- ALWAYS 对于与当前仓库技术栈明显不同的工作流，默认抽取为独立仓库。
- ALWAYS 在要求抽取到外部目录前声明工作区边界与 `--add-dir` 方案。
- ALWAYS 在 orchestrate 路由到 develop 的 Stage 3 增加工具链降级策略设计步骤。

## 校验

- ALWAYS 在仓库结构或注册规则变更后同步维护 `.claude/scripts/validate-workflow.ps1`。
- ALWAYS 普通提交前运行 `quality-gate.py commit`；runtime/schema/publish/harness 改动运行 `quality-gate.py integration`；插件版本发布前运行 `quality-gate.py release`。
- ALWAYS 保持发布门禁覆盖构建产物、版本一致性、完整仓库校验、插件 bootstrap 和 smoke matrix。
- ALWAYS 在验证脚本中检查外部工具链可用性（信息级别，不阻塞）。
- NEVER 在未说明原因和运行成本前引入重量级共享 hooks。

## 上下文管理

- ALWAYS 区分"追加式日志"（`lessons.md`，不读）和"会话缓存"（`session-findings.md`，读写）。
- ALWAYS 将审计目标代码克隆到项目内部路径，确保 Claude 工作区可访问。
- ALWAYS 配置轻量级 hooks 用于错误日志和进度追踪，减少 AI 文字输出消耗。
- ALWAYS 在审计报告中标注每个发现的来源（哪个工具或 AI Agent），以便评估可信度。

## 文件格式

- ALWAYS 抽取出的 Claude 工作流仓默认沿用 `.claude/settings.json` 对象映射注册格式。
- ALWAYS 把用户命令写成 `.claude/commands/*.md`。
- NEVER 在未说明目标运行时差异的情况下生成独立命令 JSON 文件。
