发布已经完整经过 WorkflowProgram develop 的目标工作流为 Claude Code marketplace plugin。

## Usage

```text
/workflowprogram-publish <target-root> --plugin-id <id> --repo <owner/repo-or-url> [--version 0.1.0] [--repo-mode existing_marketplace --repo-path <checkout>] [--dry-run]
```

## Behavior

## Stage 1: Resolve Publish Inputs

**Goal**: 明确发布目标、插件 ID、GitHub 仓库、版本、repo mode 和 runtime mode。

1. 解析目标项目路径、插件 ID、GitHub 仓库和版本。
2. 默认选择 `export_repo` 和 `workflowprogram_dependency`，除非用户显式指定；若用户要复用已有 marketplace，则改用 `existing_marketplace`。
3. 若缺少 GitHub 仓库或插件 ID，先向用户补问，不进入打包。

**Verify**: 发布输入足以生成 `publish-intent.json` 和 `publish-options.json`。

## Stage 2: Validate Eligibility

**Goal**: 确认目标 workflow 已完整通过 `workflowprogram-develop`。

1. 使用 `workflowprogram-publish` skill 的规则检查目标 workflow 是否完整通过 `workflowprogram-develop`。
2. 检查 design-review、managed apply、state/events、runtime manifest 和 S5 verdict。
3. 发现缺口时停止，并指向需要重新运行的 develop/change-policy 流程。

**Verify**: `publish-eligibility.json.status=PASS` 才能进入打包。

## Stage 3: Package And Publish

**Goal**: 生成 marketplace plugin payload、校验包，并生成 GitHub 发布计划或执行结果。

1. 调用 `${CLAUDE_PLUGIN_ROOT}/scripts/workflow-publish-entry.py run` 完成发布资格检查、打包、包校验和 GitHub 发布计划。
2. 若 `repo_mode=existing_marketplace`，还必须生成 marketplace merge 证据，并保证已有 manifest 被追加/更新而不是整份替换。
3. 真实 GitHub 写入必须有显式审批；缺少 `gh` 登录或权限时，只生成阻塞报告和修复指引。
4. 输出 `install-instructions.md`，用于其他用户通过 Claude Code marketplace 安装。

**Verify**: `publish-summary.json` 明确记录 `PASS`、`BLOCKED` 或 `FAIL`，并能回溯到 package、validation 和 GitHub 证据。

## Notes

- publish 是独立环节，不会直接修改目标 workflow 的语义设计。
- 如果发现目标 workflow 不可发布，应回到 `/workflowprogram-cn:workflowprogram-develop` 走 change-policy 修改流。
- 默认 runtime 模式是 `workflowprogram_dependency`，消费者需要先安装 WorkflowProgram 插件。
