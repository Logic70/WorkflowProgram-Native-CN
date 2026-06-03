# WorkflowProgram Target CLAUDE Guard 设计

## 1. 决策框架

用户目标：让 WorkflowProgram 生成的目标项目也能在 `CLAUDE.md` 中获得明确的防绕过控制面约束，降低 ClaudeCode 在上下文变长、runtime 失败或用户要求“继续完成”时绕过 runtime/finalizer 的概率。

实现状态：已实现。`workflowprogram-develop` 会在 managed apply 后写入目标项目 `CLAUDE.md` guard block，validators、S5 judge 与 publish eligibility 会检查该 block 是否存在且内容有效。

范围边界：

- 本设计只覆盖目标项目 `TARGET_ROOT/CLAUDE.md` 的生成、合并、校验和发布携带。
- 它不替代 `target-workflow-runner.py`、`target-runtime-finalizer.py`、`validate-target-publish-state.py` 等硬门禁。
- 它不承诺 OS 级阻止模型写文件；它的目标是提高提示命中率，并让 validator/doctor 能判断目标项目是否缺少必要的防绕过提示层。

当前真源：

- 目标 workflow runtime 仍采用 `generated_runtime_contract.mode=shared-control-plane-wrapper`。
- 新生成目标 workflow 默认使用 `target_runtime_policy.mode=managed_runtime`。
- `current_agent/manual` 只能提交 executor evidence，由 finalizer 复核后才可 PASS。
- 最终发布仍只能由 `target-runtime-finalizer.py` 完成。

输出产物：

- `workflow-spec.yaml.target_claude_guard`
- `TARGET_ROOT/CLAUDE.md` 中的 WorkflowProgram managed guard block
- `TARGET_ROOT/.workflowprogram/claude-guard-manifest.json`
- `RUN_ROOT/outputs/stages/target-claude-guard-apply.json`

## 2. 核心设计

### 2.1 目标项目需要自己的 CLAUDE guard

插件仓库的 `CLAUDE.md` 不会自动进入目标项目上下文。WorkflowProgram 必须在 develop 生成目标 workflow 时，为目标项目生成或维护自己的 `CLAUDE.md` 防绕过段落。

该段落只写“运行时行为边界”，不写业务节点细节：

- runtime 是唯一 orchestrator。
- command 只允许 `run/status/resume/diagnose`。
- `NEEDS_EVIDENCE/BLOCKED` 时只能处理当前 node task 并提交 executor evidence。
- `FAILED` 时只能 diagnose，不得继续补产物。
- 禁止手写 final report、manifest、latest marker、最终输出目录。
- finalizer 是唯一可信发布者。

### 2.2 采用 managed block，不接管整份 CLAUDE.md

目标项目可能已有自己的 `CLAUDE.md`。WorkflowProgram 不应整体覆盖用户文件。

设计采用带 marker 的受控块：

```markdown
<!-- BEGIN WORKFLOWPROGRAM RUNTIME GUARD: <workflow-id> -->
...
<!-- END WORKFLOWPROGRAM RUNTIME GUARD: <workflow-id> -->
```

合并策略：

- `CLAUDE.md` 不存在：创建文件并写入 guard block。
- `CLAUDE.md` 存在且无 guard block：在标题后或文件末尾追加 guard block，并保留原文。
- guard block 存在且未被用户改坏：替换 managed block。
- guard block 存在但 marker 损坏或 block 冲突：停止并生成冲突报告，不静默覆盖。

### 2.3 使用独立 guard manifest，而不是 managed-files 全文件所有权

`managed-assets.py` 当前以整文件 hash 管理 `.claude/**` 和 `.workflowprogram/**`。根目录 `CLAUDE.md` 是用户协作文件，不能用整文件所有权模型接管。

因此新增独立 manifest：

```json
{
  "manifest_version": 1,
  "file": "CLAUDE.md",
  "block_id": "workflowprogram-runtime-guard",
  "workflow_id": "stride-audit",
  "last_applied_block_sha256": "...",
  "file_sha256_after": "...",
  "updated_at": "..."
}
```

`managed-files.json` 不声明拥有整份 `CLAUDE.md`。`claude-guard-manifest.json` 只声明 WorkflowProgram 拥有 marker 之间的 block。

## 3. `workflow-spec.yaml` 契约

新增可选顶层字段：

```yaml
target_claude_guard:
  enabled: true
  file: CLAUDE.md
  mode: managed_block
  block_id: workflowprogram-runtime-guard
  required_for:
    - managed_runtime
    - target_publish_policy
  merge_policy:
    if_missing_file: create
    if_existing_no_block: append_after_title
    if_existing_block: replace_managed_block
    if_broken_block: conflict
  content:
    runtime_entry: .workflowprogram/runtime/workflow-entry.py
    allowed_actions: [run, status, resume, diagnose]
    blocked_behavior: current_node_evidence_only
    failed_behavior: diagnose_only
    trusted_publisher: target-runtime-finalizer.py
    forbidden_operations:
      - handwrite_final_report
      - write_final_manifest
      - write_latest_marker
      - copy_run_outputs_to_final
      - continue_after_runtime_fail
```

固定约束：

- `mode` 只允许 `managed_block`。
- `file` 第一版只允许 `CLAUDE.md`。
- `enabled=true` 时必须有 `block_id`、`merge_policy` 和 `content`。
- 若 `target_runtime_policy.mode=managed_runtime`，默认 `enabled=true`。
- 若 `target_publish_policy.enabled=true`，`required_for` 必须包含 `target_publish_policy`。
- `forbidden_operations` 必须覆盖 manifest/latest/final report/runtime fail 后继续这四类绕过。

## 4. 运行链路

### 4.1 S4 生成

`workflow-entry.py` 在生成目标资产时应在 candidate/run evidence 中生成：

- `outputs/stages/target-claude-guard.md`
- `outputs/stages/target-claude-guard-apply.json`

新脚本建议为：

```text
.claude/scripts/apply-target-claude-guard.py
```

职责：

- 从 `workflow-spec.yaml.target_claude_guard` 渲染 guard block。
- 读取目标项目 `CLAUDE.md`。
- 按 managed block 策略插入或替换 guard block。
- 写入 `TARGET_ROOT/.workflowprogram/claude-guard-manifest.json`。
- 记录 before/after hash、action、conflict、remediation。

### 4.2 S5 校验

`validate-generated-runtime.py` 和 S5 judge 必须校验：

- `target_claude_guard.enabled=true` 时，目标项目 `CLAUDE.md` 存在。
- 文件中存在匹配 `block_id` 的 guard block。
- guard block 包含 runtime entry、allowed actions、failed behavior、blocked behavior 和 forbidden operations。
- guard block 不得承诺“物理阻止写文件”，只能说明“不可信产物不能 publish”。
- 若 guard 缺失或冲突，对 managed runtime 工作流判为 `FAIL/design`，因为生成产物未满足防绕过提示层契约。

### 4.3 Publish 携带

`package-target-plugin.py` 已会复制目标项目 `CLAUDE.md`。发布前必须额外校验：

- 发布包中的 `CLAUDE.md` 包含同一 guard block。
- 若目标项目没有 `CLAUDE.md` 或 guard 缺失，publish eligibility 失败。

## 5. Guard 文案模板

```markdown
## WorkflowProgram Runtime Guard

This project contains a WorkflowProgram-managed workflow.

Runtime is the only workflow orchestrator. Use `.workflowprogram/runtime/workflow-entry.py` for workflow actions.

Allowed actions:
- `run`: start or continue a controlled runtime run.
- `status`: inspect the current runtime state.
- `resume`: ask runtime to validate submitted executor evidence and advance.
- `diagnose`: explain a blocked or failed runtime state without publishing.

If runtime state is `NEEDS_EVIDENCE` or `BLOCKED`, complete only the current node task and write executor evidence under the current run root.

If runtime state is `FAILED`, stop workflow execution and run diagnose only.

Do not manually write final reports, final manifests, latest markers, or final output directories. Do not copy run-scoped outputs into final outputs. `target-runtime-finalizer.py` is the only trusted publisher.

Files written outside this runtime/finalizer path are not trusted workflow results.
```

## 6. 实施计划

### Phase 1: 契约和文档

目标：定义 `target_claude_guard` schema、模板和设计文档。

成功标准：

- `validate-workflow-spec.py` 能校验 `target_claude_guard`。
- YAML 模板包含默认 guard 配置。
- HighLevel/LowLevel 明确目标项目 `CLAUDE.md` 是提示层防绕过，不是硬门禁。

### Phase 2: Guard apply 脚本

目标：实现 block-level 合并，不覆盖用户整份 `CLAUDE.md`。

成功标准：

- 缺文件时创建。
- 现有文件无 block 时追加。
- 已有 block 时替换。
- block 冲突时停止并输出 remediation。
- 写入 `claude-guard-manifest.json` 和 run evidence。

### Phase 3: 入口集成

目标：在 develop 生成链中调用 guard apply。

成功标准：

- `workflow-entry.py` 在 managed apply 后、S5 前完成 guard apply。
- guard apply 失败时 S5 不得 clean PASS。
- 目标 `.workflowprogram/design` 记录 guard 配置和应用证据。

### Phase 4: Validator / S5 / Publish

目标：让缺 guard、guard 损坏、发布包缺 guard 都可被机器发现。

成功标准：

- `validate-generated-runtime.py` 检查目标 `CLAUDE.md` guard。
- S5 judge 将 managed runtime 的 guard 缺失判为 `FAIL/design`。
- publish eligibility 检查发布包包含 guard。

### Phase 5: 回归测试

目标：覆盖目标项目有/无 `CLAUDE.md`、block 更新、冲突和 publish 携带。

测试：

- `target-claude-guard-create`
- `target-claude-guard-append-existing`
- `target-claude-guard-update-existing-block`
- `target-claude-guard-conflict-fail`
- `target-claude-guard-publish-package`

## 7. 设计审视闭环

### Round 1

问题：如果直接把 `CLAUDE.md` 加入 `managed-assets.py` 允许前缀，会把用户协作文件变成整文件托管，风险过高。

决策：accept。

修正：采用 managed block 和独立 `claude-guard-manifest.json`，不接管整份文件。

### Round 2

问题：`CLAUDE.md` 是提示词，不能作为可信执行边界。

决策：accept。

修正：设计中明确 guard 只是提示层，可信性仍由 runtime/finalizer/validator/doctor 保证。

### Round 3

问题：上下文变长时 `CLAUDE.md` 约束可能松动。

决策：accept。

修正：guard 文案只放最高优先级规则，runtime `status/run/resume/diagnose` 仍需在最近上下文重新输出当前允许动作。

### Round 4

问题：发布为插件后，如果目标项目 `CLAUDE.md` 没进入包，使用者仍拿不到 guard。

决策：accept。

修正：publish eligibility 必须验证发布包中的 `CLAUDE.md` 含 guard block。

### Closure

最新审视未发现新的职责冲突。该能力的定位是“目标项目提示层防绕过 + 机器校验存在性”，不与 runtime/finalizer 的硬控制面争夺职责。
