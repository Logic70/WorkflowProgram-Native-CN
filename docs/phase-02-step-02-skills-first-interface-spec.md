# Phase 2 Step 2 Skills-First 接口规范

## 1. 目的

本规范用于固定 Phase 2 中新增 `workflowprogram-*` skills 的命名、职责边界、输入输出和与旧入口的映射关系。

本文件是后续创建 skill 文件和更新 `.claude/settings.json` 的直接依据。

## 2. 命名规则

### 2.1 对外主入口命名

新的用户主入口统一采用：

- `workflowprogram-orchestrate`
- `workflowprogram-develop`
- `workflowprogram-audit`
- `workflowprogram-iterate`
- `workflowprogram-validate`

规则：

- 一律使用 `workflowprogram-` 前缀
- 一律为公开 skills
- 一律面向 `TARGET_ROOT`
- 一律可以在目标项目目录中直接调用

### 2.2 非主入口能力命名

以下对象不纳入 `workflowprogram-*` 命名体系：

- `review`
- `test`
- `commit`
- `doc`
- `workflow-audit`
- `validate-file`
- `workflow-spec-support`

它们的角色分别是：

- 通用复用能力
- 文件/结构级底层能力
- 内部支持资产

## 3. 技能分类模型

### 3.1 L1: 产品主入口 skills

面向用户直接调用：

- `workflowprogram-orchestrate`
- `workflowprogram-develop`
- `workflowprogram-audit`
- `workflowprogram-iterate`
- `workflowprogram-validate`

### 3.2 L2: 复用能力 skills

由 L1 主入口调用或引用：

- `review`
- `test`
- `commit`
- `doc`
- `workflow-audit`
- `validate-file`

### 3.3 L3: 内部支持资产

只给特定流程提供模板或静态支撑：

- `workflow-spec-support`

## 4. 五个新主入口的接口定义

### 4.1 `workflowprogram-orchestrate`

**角色**

- 总控入口
- 根据用户自然语言请求决定应进入哪个主流程

**典型输入**

- “帮我给当前项目设计一个 Claude Code 工作流”
- “审计当前项目里的 workflow 结构”
- “根据 lessons 给当前项目 workflow 提改进方案”
- “验证当前项目的 workflow 是否合规”

**主要职责**

- 识别当前请求属于 develop / audit / iterate / validate 哪一类
- 显式区分 `PLUGIN_ROOT` 与 `TARGET_ROOT`
- 将用户导向正确主 skill
- 在无法自动判断时，收缩为最小澄清问题

**不负责**

- 直接承担完整工作流设计/审计细节
- 直接替代 `ship` / `preflight` / `hotfix`

**主要输出**

- 路由决策
- 下一步要调用的主 skill
- 必要的参数补充项

### 4.2 `workflowprogram-develop`

**角色**

- 目标项目工作流设计主入口

**典型输入**

- 用户需求描述
- 可选的约束条件、触发方式、输出要求

**主要职责**

- 解析工作流需求
- 使用 `workflow-spec-support` 生成规格草案
- 为 `TARGET_ROOT/.claude/` 设计或更新工作流资产
- 产出设计结论和后续验证建议

**依赖能力**

- `workflow-spec-support`
- 必要时调用 `workflow-audit` / `validate-file`

**主要输出**

- 面向 `TARGET_ROOT/.claude/` 的工作流资产计划或变更
- 规格文档与设计摘要

### 4.3 `workflowprogram-audit`

**角色**

- 目标项目工作流审计主入口

**典型输入**

- 当前项目目录
- 指定的 workflow 根目录
- 审计选项（严格模式、只检查结构等）

**主要职责**

- 审计目标工作流结构、模式、质量
- 汇总风险、偏离点、改进机会
- 在必要时调用底层审计与文件验证能力

**依赖能力**

- `workflow-audit`
- `validate-file`

**主要输出**

- 工作流审计报告
- 按严重度分类的问题清单
- 建议的下一步动作

### 4.4 `workflowprogram-iterate`

**角色**

- 基于 lessons 的工作流迭代主入口

**典型输入**

- 当前项目目录
- 目标 workflow 路径
- `--dry-run` / `--apply` 类语义参数

**主要职责**

- 读取 `lessons.md` 中可复用经验
- 结合现有 workflow 结构提出改进草案
- 明确哪些变更需要审批，哪些只是建议

**依赖能力**

- `workflow-audit`
- `validate-file`
- 必要时引用 `doc`

**主要输出**

- 结构化改进草案
- 需要审批的变更说明
- 可提取到规则层的候选项

### 4.5 `workflowprogram-validate`

**角色**

- 目标项目 workflow 资产验证主入口

**典型输入**

- 当前项目目录
- 指定 workflow 路径
- 验证范围说明

**主要职责**

- 组织 workflow 级结构化验证
- 对多个关键文件和目录执行验证
- 输出统一结论，而不是单文件结果碎片

**依赖能力**

- `validate-file`
- 必要时调用 `test`

**主要输出**

- workflow 级验证结论
- 失败项汇总
- 建议修复路径

## 5. 与旧入口的映射

| 新主入口 | 主要替代对象 | 是否完全替代 | 说明 |
|---|---|---|---|
| `workflowprogram-orchestrate` | 无 | 否 | 新增总控层，负责路由 |
| `workflowprogram-develop` | `develop` | 否 | `develop` 保留为兼容入口 |
| `workflowprogram-audit` | `evolve-workflow` | 否 | `evolve-workflow` 保留为兼容入口 |
| `workflowprogram-iterate` | `iterate-workflow` | 否 | `iterate-workflow` 保留为兼容入口 |
| `workflowprogram-validate` | 无直接替代 | 否 | 新增 workflow 级验证入口，不等同于 `preflight` |

## 6. 明确不纳入 Phase 2 主入口集的对象

### 6.1 `ship`

原因：

- 面向当前仓库交付流程
- 目标是 diff 审查、验证和提交
- 不属于目标项目 workflow 开发主流程

### 6.2 `preflight`

原因：

- 面向当前仓库 ready 检查
- 不是目标 workflow 级验证入口

### 6.3 `hotfix`

原因：

- 面向当前仓库热修复流程
- 不应作为 WorkflowProgram 产品主 API 暴露给目标项目

## 7. skill 文本必须满足的约束

每个新的 `workflowprogram-*` skill 都必须满足：

1. frontmatter 完整，至少包含 `name`、`description`、`version`
2. 文本中显式说明：
   - 当前操作对象是 `TARGET_ROOT`
   - 插件资源读取来自 `PLUGIN_ROOT`
3. 明确区分：
   - 主入口职责
   - 依赖的底层能力
   - 不负责的范围
4. 避免直接把旧 command 内容原封不动复制为新 skill
5. 避免把仓库维护命令误写成目标项目能力

## 8. 对 `.claude/settings.json` 的要求

Phase 2 落地后，`skills` 注册表至少要新增：

- `workflowprogram-orchestrate`
- `workflowprogram-develop`
- `workflowprogram-audit`
- `workflowprogram-iterate`
- `workflowprogram-validate`

并保持：

- 旧 commands 继续注册
- 现有 utility skills 继续注册
- 内部 support skill 不公开注册

## 9. 结论

Phase 2 的技能优先化不是“把原有 commands 改名”，而是重新定义三层关系：

- 用户主入口：`workflowprogram-*`
- 复用能力：`review/test/doc/workflow-audit/validate-file/...`
- 内部支持：`workflow-spec-support`

后续任何 skill 文件创建或命名，如果偏离这三层关系，都应视为超出本阶段范围。
