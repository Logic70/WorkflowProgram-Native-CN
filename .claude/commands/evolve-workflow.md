通用工作流审计与演进命令。

这个命令用于系统化分析、验证并改进 Claude Code 风格的工作流仓库。

> Compatibility Note
>
> `/evolve-workflow` 作为历史兼容入口保留。普通用户应优先使用
> `/workflowprogram-cn:workflowprogram-orchestrate <需求>`，再由 orchestrate 路由到
> `workflowprogram-audit` 或 `workflowprogram-develop`。

## Usage

```text
/evolve-workflow [options] <workflow-path>
```

示例：

```text
/evolve-workflow ../target-workflow
/evolve-workflow --fix ../target-workflow
/evolve-workflow --extract-constraints ../target-workflow
/evolve-workflow --all
```

选项：

- `--fix`：自动修复格式和基础结构问题
- `--extract-constraints`：从 `lessons.md` 中提炼规则
- `--all`：审计当前目录下的所有同级工作流目录
- `--strict`：将 warning 视为错误
- `--report <file>`：将详细报告写入指定文件

## Stage 1: 结构审计

**Goal**: 确认目标工作流符合标准目录结构。

1. 检查以下结构：

```text
<workflow>/
|-- CLAUDE.md
|-- README.md
|-- lessons.md
|-- validation-report.md
`-- .claude/
    |-- settings.json
    |-- commands/
    |-- skills/
    |-- agents/
    `-- rules/
```

2. 校验关键文件：
   - `CLAUDE.md`：必须存在，且能说明仓库用途
   - `README.md`：必须存在，且包含使用示例
   - `.claude/settings.json`：必须是合法 JSON
   - `.claude/commands/*.md`：应包含 `Usage`
   - `.claude/skills/*/SKILL.md`：应包含 YAML frontmatter
3. 检查命名规范是否一致。

**Verify**: 必需文件存在，且目录结构与命名规范可被接受。

**On failure**：记录缺失项和结构问题。

## Stage 2: 模式审计

**Goal**: 确认工作流模式与仓库约定一致。

1. 检查命令模式：
   - 是否有分阶段结构
   - 是否有 `Goal`
   - 是否有 `Verify`
   - 是否定义失败处理
   - 是否支持 lessons 沉淀
2. 检查 agent 使用模式：
   - 子代理提示词是否内联
   - 单阶段并行代理是否不超过 4
   - 输出格式是否统一
3. 检查 skills：
   - 是否具备 frontmatter
   - 是否具备明确输入输出
4. 对比当前 WorkflowProgram 的做法，识别偏离点。

**Verify**: 目标工作流与基线模式整体兼容，偏离点被明确说明。

**On failure**：记录无法解释的模式冲突。

## Stage 3: Agent 质量审计

**Goal**: 确认代理提示词质量与自包含性。

1. 读取目标仓库的命令文件并提取子代理定义。
2. 检查：
   - 是否引用了外部 agent 文件
   - 是否具备清晰角色定义
   - 是否给出明确输出格式
   - 是否覆盖无问题场景
3. 对相似角色进行一致性对比。

**Verify**: 代理提示词自包含、清晰、可独立运行。

**On failure**：列出不自包含或输出不清的代理定义。

## Stage 4: 约束审计

**Goal**: 确认约束被记录且被遵守。

1. 查找 `.claude/rules/` 下的规则文件。
2. 检查是否覆盖：
   - 运行期约束
   - 架构约束
   - 领域约束
3. 结合命令与文件结构验证规则是否被执行。
4. 检查 `lessons.md` 是否存在可提炼但尚未沉淀的规则。

**Verify**: 规则覆盖关键问题域，并与现状一致。

**On failure**：说明规则缺口或规则与现实冲突之处。

## Stage 5: 演进分析

**Goal**: 从 `lessons.md` 中提炼演进机会。

1. 读取 `lessons.md`
2. 找出高频问题、成功模式和未收敛建议
3. 评估每个问题的频率、影响和是否适合提炼为规则
4. 生成约束候选和工作流改进建议

**Verify**: 所有高价值 lessons 都被转化为候选改进项。

**On failure**：指出缺失的 lessons 输入或不可解释的模式。

## Stage 6: 自动修复（如启用 --fix）

**Goal**: 自动修复低风险结构问题。

在启用 `--fix` 时，可以自动处理：

- 缺失的基础模板文件
- Markdown 结构问题
- JSON 语法问题
- YAML frontmatter 缺失字段
- 明显的内部引用断链

不要自动处理：

- 代理逻辑改写
- 规则语义变更
- 架构层级重大调整
- 文件删除

**Verify**: 自动修复仅覆盖低风险变更，并记录所有修改。

**On failure**：停止自动修复并输出未处理部分。

## Stage 7: 约束提炼（如启用 --extract-constraints）

**Goal**: 把 lessons 中的重复问题沉淀为规则。

1. 分析 `lessons.md` 中的 recurring patterns
2. 将可复用模式转成 `ALWAYS` 或 `NEVER` 规则
3. 写入目标仓库的规则文件
4. 可选地在 `validation-report.md` 中记录本次提炼结果

**Verify**: 提炼出的规则具体、可执行、能映射回 lessons 来源。

**On failure**：保留候选规则草稿并向用户说明。

## Final Output

输出：

- 结构问题摘要
- 模式与 Agent 质量问题
- 约束缺口
- 自动修复结果（若启用）
- 建议的下一步动作
