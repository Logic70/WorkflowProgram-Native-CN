# Lessons

这个文件用于记录工作流运行中的失败经验、后续动作和可沉淀的规则。

## 使用方式

- 为每次关键会话记录日期、命令和上下文。
- 同时记录成功模式和失败点。
- 将反复出现的问题沉淀到 `.claude/rules/constraints.md`。
- 在问题解决前保留明确的 follow-up。

## 归档规则

本文件最多保留 **10 条**最新记录。超过时：
1. 将最旧的记录移入 `lessons-archive/YYYY.md`（按年归档）。
2. 已沉淀为 constraints 且 follow-up 已关闭的记录优先归档。
3. `lessons-archive/` 不会被加载到 AI 上下文中，仅供人工查阅。
4. 归档操作由 `/iterate-workflow` 自动执行。

## 当前待处理项

- 抽取独立工作流仓时，继续加强“格式契约”和“工作区写边界”提示。

## 2026-04-18 - 控制面脚本调用硬化（stage-progress）

### Context
- `stage-progress.py` 作为严格枚举参数的控制面脚本，仍然在 active docs 中被描述成模型应手工拼接的 CLI 步骤。
- 实际使用中，这会让模型频繁因为 `stage/event/status/approval-status` 参数不精确而失败。

### What Worked
- 把 progress 事件继续保留为 `stage-progress.py update ...` 的兼容 CLI，便于调试和手工恢复。
- 用 runner 内部的 control-plane helper 包装 CLI 组装后，进展证据语义不需要改变。

### What Did Not Work
- 让模型直接拼高约束控制面脚本的 CLI，本质上是脆弱接口暴露，不是提示词质量问题。
- 仅依赖 lessons / prompt 演进，不能阻止相同的结构性失败重复出现。

### Constraints To Extract
- ALWAYS 通过 control-plane helper 调用高约束控制面脚本，而不是让模型手工拼 CLI。
- ALWAYS 将 `stage-progress.py` 这类脚本描述为 runner / control-plane 内部动作。
- NEVER 把严格参数词表的控制面脚本暴露成模型主路径。

### Follow-Ups
- 将约束沉淀到 `.claude/rules/constraints.md`。
- 为 active docs 和仓库级 validator 增加 anti-regression 检查。

## 2026-03-23 - /develop

### Context
- 使用本地 Claude 基于 `WorkflowProgram-CN` 设计并生成一个用于 C 语言代码审计的独立工作流仓。
- 目标输出路径为 `D:\Code\c-code-audit-workflow-cn`。

### What Worked
- `/develop` 能先做需求澄清，再给出完整的阶段化设计。
- 对 Level 1 / Level 2、嵌入式 / IoT 范围、自我迭代机制的澄清是有效的。

### What Did Not Work
- Claude 生成了 `.claude/commands/c-audit.json`，而不是 Claude 兼容的 Markdown 命令文件。
- 生成的 `.claude/settings.json` 使用了不适合当前仓系的数组化/异构结构。
- 当输出目录位于当前工作区之外时，没有提前明确写权限边界，导致出现 write permission denials。

### Constraints To Extract
- ALWAYS 抽取出的 Claude 工作流仓默认沿用 `.claude/settings.json` 对象映射注册格式。
- ALWAYS 把用户命令写成 `.claude/commands/*.md`。
- ALWAYS 在要求 Claude 写入外部目录前声明工作区边界与 `--add-dir` 方案。
- NEVER 在未说明目标运行时差异的情况下生成独立命令 JSON 文件。

### Follow-Ups
- 把上述约束写入 `.claude/rules/constraints.md`。
- 为本地 Claude 测试补充对话记录。

## 2026-03-23 - /develop（第二轮：Audit-C-Workflow-Pro）

### Context
- 基于 WorkflowProgram-CN 手动执行 `/develop` 流程，生成 C 语言代码审计工作流到 `D:\Code\Audit-C-Workflow-Pro`。
- 增加了数据流/控制流/污点分析能力、CodeQL + Infer 工具链支持。
- 用本地 Claude 测试了 `/c-audit` 命令，目标为 OpenHarmony kernel_liteos_m。

### What Worked
- 上次提取的约束（Markdown 命令文件、对象映射 settings.json）全部生效，本次未再出现格式错误。
- validate-workflow.ps1 中新增的 JSON 命令文件检测正确运行。
- 63 项结构验证全部通过。
- 本地 Claude 成功识别并执行 `/c-audit` 命令，完成 4-agent fan-out Level 2 分析。
- 输出了包含 36 个发现（16 critical / 20 warning）的完整审计报告。
- Level 1 工具全不可用时，降级策略正常工作。

### What Did Not Work
- `-p`（非交互）模式下，gate 会阻塞执行。需要在 prompt 中预先声明"所有 gate 预先批准"才能跳过。
- 审计报告未区分 AI-only 发现与工具确认发现的可信度差异。

### Constraints To Extract
- ALWAYS 在命令设计中考虑非交互（CI/CD）模式下 gate 的行为：支持通过 prompt 参数或环境变量预批准。
- ALWAYS 在审计报告中标注每个发现的来源（哪个工具或 AI Agent），以便评估可信度。
- ALWAYS 在 `/develop` 的 Stage 3 增加工具链降级策略设计步骤。

### Follow-Ups
- 安装 cppcheck/flawfinder 后重新测试 Level 1 扫描。
- 考虑为 gate 添加 `--auto-approve` 标志支持。

## 2026-03-23 - 五个问题修复（Audit-C-Workflow-Pro 优化）

### Context
- 用户提出 5 个尖锐问题：L1 工具不可用却通过验证、L2 无方法论、lessons 膨胀、代码路径不在项目内、无 hooks。
- 逐一修复并验证。

### What Worked
- 验证脚本增加工具链可用性检查（WARN 级别，非阻塞）。
- 4 个 L2 Agent 增加完整方法论：Step-by-step 分析流程、证据要求、深度边界、checklist。
- lessons.md 改为追加式日志（不读取），session-findings.md 作为会话缓存，避免上下文膨胀。
- 目标代码克隆到 `./target-code/` 确保在工作区内。
- 配置 PostToolUseFailure 和 Stop hooks 实现自动错误日志和进度追踪。

### What Did Not Work
- （无）

### Constraints To Extract
- ALWAYS 在验证脚本中检查外部工具链可用性（信息级别，不阻塞）。
- ALWAYS 为 AI Agent 提供结构化方法论（Step 1/2/3...），不只给"关注点"列表。
- ALWAYS 区分"追加式日志"（lessons.md，不读）和"会话缓存"（session-findings.md，读写）。
- ALWAYS 将审计目标代码克隆到项目内部路径，确保 Claude 工作区可访问。
- ALWAYS 配置轻量级 hooks 用于错误日志和进度追踪，减少 AI 文字输出消耗。

### Follow-Ups
- 将上述约束沉淀到 WorkflowProgram-CN 的 constraints.md。
- 更新 develop.md 的 spec-template 增加"会话缓存设计"和"hooks 配置"节。

## 2026-03-31 - /develop（daily-news 工作流设计）

### Context
- 用户要求创建一个每日科技新闻PDF工作流
- 使用 `/develop` 命令执行流程

### What Worked
- 完成了 Stage 1（需求澄清）和 Stage 2（领域研究）
- 生成的 design 文档结构完整

### What Did Not Work
- **严重违反 Stage 3 Gate**: 未向用户展示设计文档并获得批准，直接生成了所有文件
- **跳过 Stage 5**: 未进行运行时验证（TDD循环）
- **跳过 Stage 6**: 未进行约束演进和流程闭环
- **提取决策错误**: 该工作流与 WorkflowProgram-CN 技术栈不同（Python vs Markdown/JSON），且可独立复用，应该抽取为独立仓库

### Constraints To Extract
- ALWAYS 在 `/develop` Stage 3 完成后，向用户展示设计文档并获得明确批准，再进入 Stage 4
- ALWAYS 对于与当前仓库技术栈明显不同的工作流，默认抽取为独立仓库
- ALWAYS 完成 Stage 5 运行时验证后再标记工作流完成
- NEVER 在未经验证的情况下声明工作流"创建完成"

### Follow-Ups
- 删除错误创建的文件
- 重新按照正确流程执行
- 将工作流抽取为独立仓库 `daily-news-workflow/`

## 记录模板

```markdown
## YYYY-MM-DD - /command-name

### Context
- 本次变更了什么？
- 为什么运行这个命令？

### What Worked
- 成功模式或通过的检查

### What Did Not Work
- 失败点、歧义点或缺失资产

### Constraints To Extract
- ALWAYS ...
- NEVER ...

### Follow-Ups
- 下一步具体动作
```
