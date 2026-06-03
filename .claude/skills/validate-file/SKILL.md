---
name: validate-file
description: Validate generated workflow files (agents, skills, commands, settings)
version: 1.0.0
---

验证生成的工作流文件是否符合格式和约束要求。

## Usage

```
/validate-file <file-path> [--type=agent|skill|command|settings]
```

## 验证规则

### Agent 文件 (.claude/agents/*.md)

| 检查项 | 命令/方式 | 预期结果 |
|--------|----------|---------|
| 文件可读 | `test -r <file>` | 返回 0 |
| Markdown 结构 | 解析 frontmatter | 成功解析 |
| 自包含提示词 | 检查是否包含"读取外部文件"、"查看 xxx.md"等模式 | 不包含 |
| 必要章节 | 检查是否有明确的职责描述 | 存在 |

### Skill 文件 (.claude/skills/*/SKILL.md)

| 检查项 | 命令/方式 | 预期结果 |
|--------|----------|---------|
| 文件可读 | `test -r <file>` | 返回 0 |
| YAML frontmatter | `yq '.' <file>` | 成功解析 |
| 必需字段 | 检查 name, description, version | 全部存在 |
| 无外部依赖 | 检查提示词是否自包含 | 不包含外部文件引用 |

### Command 文件 (.claude/commands/*.md)

| 检查项 | 命令/方式 | 预期结果 |
|--------|----------|---------|
| 文件可读 | `test -r <file>` | 返回 0 |
| 有 Usage 段 | 检查 `## Usage` | 存在 |
| 有 Stage 结构 | 检查 `## Stage \d+:` | 存在 |
| 有 Goal | 检查 `**Goal**:` | 每个 Stage 都有 |
| 有 Verify | 检查 `**Verify**:` | 每个 Stage 都有 |

### Settings 文件 (.claude/settings.json)

| 检查项 | 命令/方式 | 预期结果 |
|--------|----------|---------|
| 合法 JSON | `jq '.' <file>` | 成功解析 |
| 命令注册一致性 | 检查 commands 中引用的文件是否存在 | 全部存在 |
| Skill 注册一致性 | 检查 skills 中引用的文件是否存在 | 全部存在 |
| 无重复名称 | 检查 commands/skills/agent 是否有重复 | 无重复 |

## 输出格式

```json
{
  "file": "<path>",
  "type": "agent|skill|command|settings",
  "status": "PASS|FAIL",
  "checks": [
    {"check": "<name>", "status": "PASS|FAIL", "message": "<details>"}
  ],
  "fixable": true|false,
  "suggestion": "<fix suggestion>"
}
```

## On Failure

1. 输出失败的检查项
2. 提供修复建议（如果可自动修复）
3. 返回非零退出码

## Rules

- 严格检查，不通过模糊问题
- 提供明确的修复指引
- 区分可自动修复和需人工介入的问题
