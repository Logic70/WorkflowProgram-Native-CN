# Phase 7 实施计划

## 1. Phase 目标

Phase 7 聚焦把“设计已定义、实现已部分落地”的测试契约补成可执行闭环，目标只有三项：

1. **收口当前生效设计真源**
   - 明确以 HighLevel / LowLevel / consistency-check 为当前生效设计文档。
   - 将历史 phase 文档与 archive 文档降级为追溯材料，而不是运行真源。

2. **把仓库级静态校验对齐到当前设计**
   - `validate-workflow.py/.ps1` 不再只检查目录和脚本存在，还要检查当前生效设计文档与主入口文档是否同步包含 `runtime_contract / test_contract` 语义。

3. **补齐 S5 面向 `test_contract` 的验证闭环**
   - 让动态验证目标可以从 `test_contract` 派生，而不只停留在 spec 校验器层。
   - 为基础运行测试固定成功/非法入口/越界写入/环境不足等最小场景集，并解除对 Claude 登录的单一路径依赖。

## 2. 本阶段不处理

- Benchmark 平台化、批量评测报表
- PTY/TUI 层自动化
- 删除所有 phase 文档或 ADR
- 直接删除 `docs/archive/` 全量历史文档

## 3. 当前剩余工作分解

### 3.1 文档治理

- 明确当前生效设计真源：
  - `docs/workflowprogram-stage-highlevel-design.md`
  - `docs/workflowprogram-stage-lowlevel-design.md`
  - `docs/workflowprogram-stage-consistency-check.md`
- 明确 supporting doc：
  - `docs/phase-03-step-02-runtime-evidence-spec.md`
- 新增文档状态索引：
  - `docs/workflowprogram-design-status.md`
- 新增能力矩阵：
  - `docs/workflowprogram-capability-matrix.json`
- 明确历史追溯文档：
  - `docs/archive/*`
  - 已完成 phase 计划文档

### 3.2 静态校验升级

- 更新 `validate-workflow.py`
  - 检查当前生效设计文档存在
  - 检查 HighLevel / LowLevel 明确包含 `runtime_contract` 与 `test_contract`
  - 检查 `/develop` 与 `workflowprogram-develop` 已同步声明 `test_contract`
- 更新 `validate-workflow.ps1`
  - 与 Python 版保持同一契约
- 重建 `dist/plugin`
  - 确保发布载荷同步新的验证器

### 3.3 S5 动态验证闭环

- 更新 `workflowprogram-validate`
  - 明确当存在 `test_contract` 时，验证目标应按 `entry / boundary / flow / artifacts / failure` 五类派生
- 更新 `tools/runtime_smoke.py`
  - 输出每次 smoke 覆盖了哪些契约类别
  - 至少能区分成功、非法入口、越界写入、环境不足
- 如有必要，补充 `RUN_ROOT/outputs/stages/s5-validation-summary.json`
  - 记录每个检查项来源于哪类契约

### 3.4 固定场景与夹具

- 新增最小 spec fixtures：
  - `valid-minimal`
  - `invalid-entry`
  - `write-boundary-violation`
  - `environment-skip`
- 将负例从临时 `/tmp` 运行提升为仓库内固定验证输入

### 3.5 历史文档清理

- 先做引用审计
- 若 `docs/archive/*` 未被当前生效链路引用，可删除
- 若 phase 文档仍被活文档引用，则先吸收有效内容再删

## 4. 执行步骤

### Step 1: 冻结当前生效设计真源

目标：让团队知道哪些文档是“当前定义”，哪些只是历史记录。

交付：

- 本计划文档
- 必要时更新 `README.md` / consistency-check 对“真源文档”的说明

### Step 2: 升级仓库级静态校验

目标：让结构校验明确覆盖当前设计真源和主入口文档同步性。

交付：

- `.claude/scripts/validate-workflow.py`
- `.claude/scripts/validate-workflow.ps1`

### Step 3: 接入 S5 的 `test_contract` 判定来源

目标：让 `test_contract` 不只停留在 spec schema，而是进入运行验证总结。

交付：

- `.claude/skills/workflowprogram-validate/SKILL.md`
- `tools/runtime_smoke.py`
- 必要时补充新的验证摘要字段

### Step 4: 固化最小场景集

目标：让基础运行测试有稳定可复验输入，而不是依赖临时命令拼接。

交付：

- `tests/spec-fixtures/*`
- 对应 expectation / transcript 更新

### Step 5: 清理历史文档

目标：在不破坏追溯性和引用闭合的前提下，删除真正无效的历史文档。

交付：

- 删除候选清单
- 引用审计结果
- 必要的 README / design 引用修正

## 5. 验证矩阵

基础验证：

```bash
python3 tools/build_plugin.py
python3 .claude/scripts/validate-workflow.py
powershell.exe -ExecutionPolicy Bypass -File .claude/scripts/validate-workflow.ps1
python3 .claude/scripts/validate-workflow-spec.py --spec .claude/skills/workflow-spec-support/yaml-spec-template.md --json
```

动态验证：

```bash
python3 tools/runtime_smoke.py --fixture empty-project --runtime-provider command_adapter --provider-command 'python3 tools/mock_runtime_host.py' --json
python3 tools/runtime_smoke.py --fixture existing-workflow --runtime-provider command_adapter --provider-command 'python3 tools/mock_runtime_host.py' --json
python3 tools/runtime_smoke.py --fixture broken-workflow --runtime-provider command_adapter --provider-command 'python3 tools/mock_runtime_host.py' --json
```

负例验证：

```bash
python3 .claude/scripts/validate-workflow-spec.py --spec tests/spec-fixtures/invalid-entry.yaml --json
python3 .claude/scripts/workflow-runner.py run --spec tests/spec-fixtures/write-boundary-violation.yaml --run-root <tmp-run> --target-root <tmp-target> --intent develop --request "boundary" --auto-approve --json
```

## 6. 完成定义

满足以下条件即视为 Phase 7 完成：

1. 仓库级静态校验已纳入当前生效设计真源。
2. `/develop` 与 `workflowprogram-develop` 对 `runtime_contract / test_contract` 的定义同步。
3. `test_contract` 不只停留在 spec 校验，而能进入 S5 验证总结。
4. 成功、非法入口、越界写入、环境不足至少 4 类场景可固定复验。
5. 历史文档的保留或删除有清晰边界，不再混入当前真源。

## 7. 当前进度（2026-04-09）

已完成：

- 模板、spec validator、runner、fixtures 已统一到显式 `stage_slot: S1..S6` 六阶段模型。
- S5 主 judge 已收口为 `workflowprogram-validate` + `.claude/scripts/workflow-s5-judge.py`，`runtime_smoke.py` 复用同一判断链。
- `runtime_host.py` 已将运行宿主抽象为 `claude_cli / fixture_host / command_adapter`，`tools/mock_runtime_host.py` 提供了非 Claude provider 的参考实现。
- `tools/build_plugin.py` 已将 `workflow-s5-judge.py`、`runtime_host.py` 等脚本同步进 `dist/plugin/`，仓库级 Python validator 已覆盖 dist 关键载荷、command wrapper、source/dist 构建一致性和 build-manifest sha256。
- 固定场景已可稳定复验：`valid-minimal` runner PASS 为 6 次 transition；`write-boundary-violation` 稳定报 RUN_ROOT 边界错误；`empty-project` 与 `existing-workflow` 在 `command_adapter` 路径上稳定 PASS；`broken-workflow` 返回 `FAIL/EVIDENCE_FAILURE`；`invalid-entry` 返回 `FAIL/STRUCTURE_FAILURE`；`external-write` 返回 `FAIL/S5_BOUNDARY_TARGET_ROOT_BOUNDARY_CHANGES`；`managed-conflict` 返回 `FAIL/CONFLICT_FAILURE`。
- spec validator 已禁止旧的 `claude_cli_available / claude_cli_logged_in` 环境检查名，活动模板与运行时 check 口径已统一到 `runtime_host_*`。

已完成：

- `docs/workflowprogram-design-status.md` 已明确 active/supporting/historical 文档边界。
- `docs/workflowprogram-capability-matrix.json` 已落地，仓库级 validator 会按 capability matrix 校验关键能力口径。
- `workflow-entry.py` 已作为 develop 主链的确定性脚本入口，串起 spec/view/managed-assets/runner/state-validator。

仍待增强：

- 若需要接入真实第三方 API，可在 `command_adapter` 协议下补一个生产级 provider。

暂缓：

- Windows / PowerShell 平台侧复验不在当前范围内。
