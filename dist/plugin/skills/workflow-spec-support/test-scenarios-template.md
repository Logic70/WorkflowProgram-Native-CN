<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->

# Test Scenarios Template

本模板用于 `/develop` 命令生成 `test-scenarios.md`。

## 使用方式

`test-scenario-generator` 子代理读取此模板，结合工作流设计生成具体测试场景。

---

# Test Scenarios for /{command-name}

## Metadata

- **Generated From**: workflow-spec.md, design-doc.md
- **Complexity Level**: {S|M|L|XL}
- **Generation Date**: {timestamp}

## Coverage Matrix

| Stage | Happy Path | Edge Case | Error Case | Status |
|-------|------------|-----------|------------|--------|
| Stage 1 | TC-001 | TC-002 | TC-003 | ☐ |
| Stage 2 | TC-004 | TC-005 | TC-006 | ☐ |
| Stage 3 | TC-007 | TC-008 | TC-009 | ☐ |

## Complexity Configuration

```yaml
level: {S|M|L|XL}
based_on:
  stages: {count}
  patterns: [{patterns}]
  sub_agents: {true|false}
timeout:
  minutes: {3|5|10|15}
  max_retries: 3
```

---

## TC-{NNN}: {Stage N} {Case Type} - {Description}

**Target Stage**: Stage {N}: {name}
**Case Type**: {Happy Path|Edge Case|Error Case}
**Prerequisites**: {conditions}

### Input
```
{command or input}
```

### Execution Steps
1. {step 1}
2. {step 2}
3. {step 3}

### Expected Output
- {output 1}
- {output 2}

### Validation Points（明确判定条件）

#### 自动生成

| 检查项 | 判定命令 | 预期结果 | 类型 |
|--------|---------|---------|------|
| 文件存在 | `test -f <path>` | 返回 0 | 自动 |
| Frontmatter完整 | `yq '.name' <path>` | 非空 | 自动 |
| JSON合法 | `jq '.' <path>` | 成功解析 | 自动 |
| 命令注册 | `jq '.commands.<name>' .claude/settings.json` | 非空 | 自动 |

#### 设计者补充（Stage 3）

| 检查项 | 判定命令 | 预期结果 | 类型 |
|--------|---------|---------|------|
| {custom check} | {command} | {result} | 手动 |

### Cleanup
- {cleanup step 1}
- {cleanup step 2}

---

## Validation Points Format Specification

### 自动类型

自动验证点必须包含可实际执行的命令：

```markdown
| 检查项 | 判定命令 | 预期结果 | 类型 |
|--------|---------|---------|------|
| 文件存在 | `test -f workflow-spec.md` | 返回 0 | 自动 |
| 非空检查 | `test -s workflow-spec.md` | 返回 0 | 自动 |
| YAML解析 | `yq '.name' workflow-spec.md` | 非空字符串 | 自动 |
| JSON解析 | `jq '.commands' .claude/settings.json` | 成功 | 自动 |
| 模式匹配 | `grep -q "Goal:" command.md` | 返回 0 | 自动 |
| 行数检查 | `wc -l < file.md` | <expected> | 自动 |
```

### 手动类型

手动验证点需要人工检查：

```markdown
| 检查项 | 判定命令 | 预期结果 | 类型 |
|--------|---------|---------|------|
| 内容合理性 | 人工检查 | 符合业务逻辑 | 手动 |
| 输出质量 | 人工检查 | 达到预期标准 | 手动 |
```

### 复合验证

复杂验证可组合多个命令：

```markdown
| 检查项 | 判定命令 | 预期结果 | 类型 |
|--------|---------|---------|------|
| 文件完整性 | `test -f file.md && yq '.name' file.md` | 非空 | 自动 |
```

---

## Stage-Specific Templates

### Stage 1: 理解需求 (Explore)

```markdown
## TC-001: Stage 1 Happy Path - Normal Requirement

**Target Stage**: Stage 1: 理解需求
**Case Type**: Happy Path
**Prerequisites**: 工作区已初始化 git

### Input
```
/develop {clear requirement}
```

### Execution Steps
1. 解析需求
2. 生成澄清问题（如需要）
3. 生成 workflow-spec.md

### Expected Output
- workflow-spec.md 存在
- 所有字段有明确值
- 无 TBD

### Validation Points

| 检查项 | 判定命令 | 预期结果 | 类型 |
|--------|---------|---------|------|
| 文件存在 | `test -f workflow-spec.md` | 返回 0 | 自动 |
| Frontmatter完整 | `yq '.name' workflow-spec.md` | 非空 | 自动 |
| 无TBD | `! grep -i "TBD" workflow-spec.md` | 返回 0 | 自动 |
| 需求覆盖 | 人工检查 | 覆盖用户所有需求 | 手动 |

### Cleanup
- `rm workflow-spec.md`
```

### Stage 2: 领域研究 (Explore)

```markdown
## TC-004: Stage 2 Happy Path - Context Analysis

**Target Stage**: Stage 2: 领域研究
**Case Type**: Happy Path
**Prerequisites**: workflow-spec.md 存在

### Input
```
{自动触发，基于 Stage 1 输出}
```

### Execution Steps
1. 分析现有 .claude/ 资产
2. 分析 CLAUDE.md 约定
3. 生成领域上下文报告

### Expected Output
- 领域上下文报告存在
- 列出可复用资产和缺口

### Validation Points

| 检查项 | 判定命令 | 预期结果 | 类型 |
|--------|---------|---------|------|
| 报告存在 | `test -f context-report.md` | 返回 0 | 自动 |
| 资产清单 | `grep -c "可复用" context-report.md` | >0 | 自动 |
| 缺口识别 | `grep -c "缺口" context-report.md` | >0 | 自动 |
| 覆盖度 | 人工检查 | 覆盖 workflow-spec 所有领域 | 手动 |

### Cleanup
- `rm context-report.md`
```

### Stage 3: 工作流设计 (Specialized Agent)

```markdown
## TC-007: Stage 3 Happy Path - Complete Design

**Target Stage**: Stage 3: 工作流设计
**Case Type**: Happy Path
**Prerequisites**: 领域上下文报告存在

### Input
```
{自动触发，基于 Stage 2 输出}
```

### Execution Steps
1. 选择模式组合
2. 定义 Agent/Skill/Hook 清单
3. 生成设计文档

### Expected Output
- design-doc.md 存在
- 包含 ASCII 流程图
- Agent 清单完整
- 复杂度级别已定义

### Validation Points

| 检查项 | 判定命令 | 预期结果 | 类型 |
|--------|---------|---------|------|
| 文件存在 | `test -f design-doc.md` | 返回 0 | 自动 |
| 流程图 | `grep -c "```" design-doc.md` | >0 | 自动 |
| Agent清单 | `grep -c "Agent 清单" design-doc.md` | >0 | 自动 |
| 复杂度级别 | `grep -c "级别:" design-doc.md` | >0 | 自动 |
| 设计合理性 | 人工检查 | 用户批准 | 手动 |

### Cleanup
- 保留 design-doc.md（用户已批准）
```

### Stage 4: 生成文件 (Sequential)

```markdown
## TC-010: Stage 4 Happy Path - File Generation

**Target Stage**: Stage 4: 生成文件
**Case Type**: Happy Path
**Prerequisites**: design-doc.md 已批准

### Input
```
{自动触发，基于设计文档}
```

### Execution Steps
1. 生成 agents/*.md
2. 生成 skills/*/SKILL.md
3. 生成 commands/*.md
4. 更新 settings.json

### Expected Output
- 所有设计中的文件存在
- 通过 validate-file 检查

### Validation Points

| 检查项 | 判定命令 | 预期结果 | 类型 |
|--------|---------|---------|------|
| Agent文件 | `test -f .claude/agents/{name}.md` | 返回 0 | 自动 |
| Skill文件 | `test -f .claude/skills/{name}/SKILL.md` | 返回 0 | 自动 |
| Command文件 | `test -f .claude/commands/{name}.md` | 返回 0 | 自动 |
| Settings | `jq '.' .claude/settings.json` | 成功 | 自动 |
| 即时检查 | `/validate-file <file>` | PASS | 自动 |

### Cleanup
- 保留所有生成的文件
```

### Stage 5: 运行时验证 (Test-Driven)

```markdown
## TC-013: Stage 5 Happy Path - Runtime Validation

**Target Stage**: Stage 5: 运行时验证
**Case Type**: Happy Path
**Prerequisites**: 所有文件已生成并通过静态检查

### Input
```
{自动触发，test-scenarios.md}
```

### Execution Steps
1. 生成测试场景
2. 启动沙盒环境
3. 异步执行验证
4. 生成验证报告

### Expected Output
- test-scenarios.md 存在
- validation-runtime-report.md 存在
- 无 CRITICAL 问题

### Validation Points

| 检查项 | 判定命令 | 预期结果 | 类型 |
|--------|---------|---------|------|
| 测试场景 | `test -f test-scenarios.md` | 返回 0 | 自动 |
| 验证报告 | `test -f validation-runtime-report.md` | 返回 0 | 自动 |
| 无关键问题 | `! grep -i "CRITICAL" validation-runtime-report.md` | 返回 0 | 自动 |
| 覆盖率 | `grep -c "PASS" validation-runtime-report.md` | >0 | 自动 |

### Cleanup
- 保留报告，清理沙盒环境
```

### Error Case Templates

```markdown
## TC-003: Stage 1 Error Case - User Cancels

**Target Stage**: Stage 1: 理解需求
**Case Type**: Error Case

### Input
用户拒绝回答澄清问题

### Execution Steps
1. 生成澄清问题
2. 用户取消
3. 执行 On failure

### Expected Output
- 记录到 lessons.md
- 优雅退出
- 无不完整文件

### Validation Points

| 检查项 | 判定命令 | 预期结果 | 类型 |
|--------|---------|---------|------|
| 记录存在 | `grep -c "用户取消" lessons.md` | >0 | 自动 |
| 无残留 | `! test -f workflow-spec.md` | 返回 0 | 自动 |
| 错误信息 | `grep "需改进需求收集方式" lessons.md` | 存在 | 自动 |

### Cleanup
- 已处理
```

---

## Rules for Template Usage

1. **必须替换的占位符**:
   - `{command-name}`: 实际命令名称
   - `{N}`: 实际 Stage 编号
   - `{S|M|L|XL}`: 实际复杂度级别
   - `{count}`: 实际数量

2. **必须保留的结构**:
   - Coverage Matrix
   - Complexity Configuration
   - Validation Points 表格格式
   - Cleanup 部分

3. **扩展点**:
   - 可在 "设计者补充" 部分添加业务特定验证
   - 可添加额外的测试场景
   - 可调整执行步骤

4. **生成约束**:
   - 每个 Stage 至少 3 个场景
   - 每个场景必须有明确的 Validation Points
   - 判定命令必须可实际执行
