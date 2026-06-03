---
name: workflow-audit
description: Audit workflow structure patterns and quality
version: 1.0.0
---

<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->


# Workflow Audit Skill

为工作流仓库提供系统化的结构与质量审计能力。

## When to Use

- 审计新建或已有工作流的质量
- 验证工作流结构是否符合约定
- 从 lessons 中提炼规则
- 将目标工作流与当前架构标准进行对比
- 根据累计经验持续演进工作流

## 审计清单

### 结构校验

- [ ] `CLAUDE.md` 存在且说明仓库用途
- [ ] `README.md` 存在且包含使用示例
- [ ] `.claude/settings.json` 为合法 JSON
- [ ] `.claude/commands/` 存在且包含命令文件
- [ ] `.claude/skills/` 存在且技能目录中包含 `SKILL.md`
- [ ] `.claude/rules/` 存在并包含约束文件
- [ ] `lessons.md` 存在以支持自我迭代

### 模式校验

- [ ] 命令采用 Stage N 的分阶段结构
- [ ] 每个阶段都包含 `Goal`
- [ ] 每个阶段都包含 `Verify`
- [ ] 有明确的失败处理说明
- [ ] 支持 lessons 沉淀
- [ ] 子代理提示词内联，不依赖外部文件
- [ ] 单阶段并行代理数不超过 4
- [ ] 并行代理输出格式一致

### 质量检查

- [ ] 没有硬编码的绝对路径依赖
- [ ] 错误信息清晰
- [ ] TDD 循环清晰可见
- [ ] 文档完整
- [ ] 内部交叉引用有效

## 快速参考

### 推荐目录结构

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

### 命令结构模板

```markdown
## Usage

说明如何调用命令。

## Stage 1: 名称

**Goal**: 阶段目标。

1. 步骤一
2. 步骤二

**Verify**: 可判断是否完成的标准。

**On failure**: 失败时记录什么。
```

### Skill 结构模板

```markdown
---
name: skill-name
description: Explain the skill purpose
version: 1.0.0
---
```

## 常用检查点

1. 检查命令是否具备 `Usage`
2. 检查阶段是否具备 `Goal` 和 `Verify`
3. 检查 Skills 是否具备 frontmatter
4. 检查 settings 是否与磁盘文件一致
5. 检查 lessons 与 rules 是否形成闭环

## 输出建议

审计结果建议至少包含：

- 结构问题
- 模式问题
- 规则缺口
- 自动修复建议
- 推荐下一步
