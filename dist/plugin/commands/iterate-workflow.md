---
description: Compatibility lessons iteration entry; prefer workflowprogram-orchestrate
argument-hint: [--dry-run] [--apply] [workflow-path]
---

<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->

基于累积的 lessons 对工作流进行自我迭代。

这个命令采用“先草拟、后审批、再应用”的 DRAFT MODE，
避免未经确认就修改结构性工作流资产。

> Compatibility Note
>
> `/iterate-workflow` 作为历史兼容入口保留。普通用户应优先使用
> `/workflowprogram-cn:workflowprogram-orchestrate <需求>`，再由 orchestrate 路由到
> `workflowprogram-iterate`。

## Usage

```text
/iterate-workflow [--dry-run] [--apply] [<workflow-path>]
```

默认目标：当前工作流仓库。

选项：

- `--dry-run`：仅展示提议，不真正创建或修改文件
- `--apply`：在获得批准后应用变更
- `<workflow-path>`：指定目标工作流路径

## Stage 1: 分析 lessons

**Goal**: 从 `lessons.md` 中识别改进机会，并准备提取约束到 `constraints.md`。

1. 读取目标工作流的 `lessons.md`（只读取最近10条记录）
2. 解析：
   - What Did Not Work
   - **Constraints To Extract** ← 重点关注
   - Recommendations
   - Test Run 或校验结果
3. 将问题归类为：
   - 格式问题 → 自动修复
   - 结构问题 → 需审批
   - 模式问题 → 需审批
   - Agent 问题 → 需审批
   - **规则问题 → 提取到 constraints.md**
4. 提取 `Constraints To Extract` 中的 ALWAYS/NEVER 规则
5. 判断修复方式：
   - 自动修复：格式、空白、轻量规范
   - **规则提取**：合并到 `constraints.md`（需去重）
   - 需要审批：提示词、规则、架构

**Verify**: 问题都已被识别并归类，待提取的约束已整理。

**On failure**：若 `lessons.md` 不存在或为空，则提示先运行工作流积累经验。

## Stage 2: 生成草案

**Goal**: 在不立即应用的前提下，为每个问题生成清晰提案。

对每个问题产出：

- 变更名称
- 目标文件
- 变更类型（自动修复 / 需审批）
- 背景原因
- diff 预览或内容预览

草案应优先展示：

- 要改什么
- 为什么要改
- 不改会有什么影响

**Verify**: 所有提议都具备明确原因和预期效果。

**On failure**：保留已生成草案，并说明哪些问题还需要人工分析。

## Stage 3: 向用户展示

**Goal**: 以适合 CLI 阅读的方式展示所有变更。

展示结构建议：

1. 分析摘要
2. 可自动修复项
3. 需要审批的结构化变更
4. 预期收益
5. 下一步动作

对于需要审批的项，应逐条给出：

- diff 或预览
- 问题描述
- 修改理由
- 等待用户批准

**Verify**: 用户能清楚看见每项变更的内容、原因和影响。

**On failure**：缩减输出范围，但保留最关键的问题项。

## Stage 4: 应用批准项（仅在 --apply）

**Goal**: 仅应用用户已经批准的提案。

1. 自动应用低风险格式修复
2. **将批准的 `Constraints To Extract` 合并到 `constraints.md`**
   - 检查是否已存在（避免重复）
   - 添加来源标注（命令和日期）
   - 按类别组织（参考现有分类）
3. 对结构性改动逐项确认审批结果
4. 只对批准项落盘
5. 更新 `lessons.md`，标记已提炼或已处理的问题

**Verify**: 只有明确批准的变更被应用，约束已正确合并到 `constraints.md`。

**On failure**：停止后续应用，并保留审批状态说明。

## Stage 5: 重新校验

**Goal**: 确认应用后的工作流仍然自洽。

1. 运行仓库定义的验证命令
2. 检查：
   - 结构是否仍完整
   - 注册关系是否仍正确
   - 新规则是否与现有规则冲突

**Verify**: 变更后工作流通过校验。

**On failure**：展示失败项并回到草案层说明问题。

## Final Output

输出：

- 分析到的问题数量
- 自动修复项数量
- 待审批项数量
- 已应用项数量（若使用 `--apply`）
- 建议的下一步动作
