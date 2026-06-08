---
name: workflowprogram-orchestrate
description: Route natural-language WPN / WorkflowProgram / workflow design, migration, refactor, audit, iterate, validate, or publish requests to the correct WorkflowProgram entry; must not implement migration with generic foreground Agent/Write/Bash.
version: 1.0.0
---

<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->


作为 WorkflowProgram 的总控入口，负责把用户当前请求路由到正确的主能力。

## When To Use

- 用户希望为当前项目设计 Claude Code 工作流
- 用户希望审计当前项目中的 workflow 资产
- 用户希望根据 lessons 迭代当前 workflow
- 用户希望验证当前 workflow 是否符合结构约束
- 用户希望把已完成的目标 workflow 发布成 Claude Code marketplace plugin

## Core Rules

- Natural-language requests that mention WPN, WorkflowProgram Native, migrate an
  existing workflow, refactor workflow assets, or create/update `.claude`
  workflow control planes must be routed to `workflowprogram-native-develop` or
  another product WorkflowProgram leaf before any generic Agent implementation.
  The foreground assistant is a router and evidence adapter, not the migration
  author.
- Do not use a generic Agent to explore and then write `.claude/**`,
  `.workflowprogram/**`, or `managed-files.json` directly. Route first, then
  obey the product JS re-entrant state and nextAction.

- 当前工作对象是 `TARGET_ROOT`，即用户当前项目目录。
- 插件资产来自 `PLUGIN_ROOT`，应按只读资源处理。
- 不要把 `WorkflowProgram-CN` 仓库本身误当成默认目标项目。
- 不要把 `ship`、`preflight`、`hotfix` 这类仓库维护命令当成产品主入口。
- 这是当前唯一应承接普通自然语言自动触发的 `workflowprogram-*` 入口；用户不需要记住 slash command。
- `/workflowprogram-cn:workflowprogram-orchestrate <需求>` 仅作为显式调试、路由复核和自动命中失败时的兜底入口。
- 其他 `workflowprogram-develop/audit/iterate/validate` 是高级显式 leaf 或内部路由目标，不是普通首选入口。
- 若请求不明确，只提出最小必要的一个路由澄清问题；进入 develop 后的需求澄清由对应 leaf 负责。
- 路由前应优先调用 `workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/route-intent.py --request "<用户请求>" --target-root <TARGET_ROOT> --json`。
- 当 intent 为 `develop` 时，继续调用 `workflowprogram-python ${CLAUDE_PLUGIN_ROOT}/scripts/route-native-control-plane.py --target-root <TARGET_ROOT> --json`：所有目标默认进入 `native`；若发现旧 `.workflowprogram/runtime` 或旧设计 spec 标记，只记录 `manual_migration_required=true`，不得自动重写旧目标文件。
- 路由结果必须写入 `RUN_ROOT/outputs/stages/route-intent.json`；随后调用 `${CLAUDE_PLUGIN_ROOT}/scripts/resolve-change-context.py` 写入 `RUN_ROOT/outputs/stages/change-context.json`。
- 若 `change-context.json.change_policy_required=true`，必须把该证据交给 `workflowprogram-develop`，不得直接当作普通新建 workflow 处理。
- 当路由结果进入叶子入口后，确定性脚本链必须通过 `${CLAUDE_PLUGIN_ROOT}/scripts/workflow-entry.py run` 驱动，而不是只靠口头步骤串联或读取 prompt 文件后手工修改。
- 当 `WORKFLOWPROGRAM_STRICT_ROUTE=1` 或显式 strict 模式开启时，若路由歧义则必须先澄清，不得直接分发到叶子 skill。

## Step 1: Resolve Context

1. 识别当前工作目录是否为 `TARGET_ROOT`。
2. 若用户显式给出路径，以该路径作为 `TARGET_ROOT`。
3. 通过 `route-intent.py --out <RUN_ROOT>/outputs/stages/route-intent.json` 得到意图、置信度和 `request_kind`。
4. 通过 `resolve-change-context.py --route <RUN_ROOT>/outputs/stages/route-intent.json --out <RUN_ROOT>/outputs/stages/change-context.json` 判断目标是空项目、已有托管 workflow、已有非托管 workflow 还是 partial workflow。
5. 明确本次操作是“设计 / 审计 / 迭代 / 验证”中的哪一类，以及是否需要 change policy。
6. 若 intent 为 `develop`，写入 `RUN_ROOT/outputs/stages/control-plane-route.json`，并明确是否存在旧 runtime 标记和人工迁移注意事项。

## Step 2: Route Request

按照以下规则路由：

- 设计新 workflow -> 默认 `workflowprogram-native-develop`
- 更新已有 Native Workflow JS -> `workflowprogram-native-develop`
- 更新已有旧 WorkflowProgram runtime 目标 -> `workflowprogram-native-develop`，但必须保留 `manual_migration_required` 提示，先做候选区生成和样例验证，不自动重写旧 runtime 文件
- 审计现有 workflow 结构与模式 -> `workflowprogram-audit`
- 基于 `lessons.md` 生成改进草案 -> `workflowprogram-iterate`
- 对 workflow 资产执行结构化校验 -> `workflowprogram-validate`
- 发布已完成目标 workflow 为 marketplace plugin -> `workflowprogram-publish`

路由到 `workflowprogram-native-develop` 后，加载并遵循该 leaf skill。不要跳过产品 JS 返回的澄清、用户确认、generation、validation、smoke 和 apply gate；leaf 只负责绝对 `scriptPath` 启动与宿主侧 evidence 适配。

## Step 3: Hand-off Requirements

向目标主 skill 传递：

- `TARGET_ROOT`
- 用户原始需求
- `RUN_ROOT/outputs/stages/route-intent.json`
- `RUN_ROOT/outputs/stages/change-context.json`
- develop intent 下的 `RUN_ROOT/outputs/stages/control-plane-route.json`
- 必要的约束或范围说明
- 当前已知的 `.claude/` 现状

## Output

输出应包含：

- 路由结论
- 目标主 skill 名称
- 若存在，最小缺失信息项
