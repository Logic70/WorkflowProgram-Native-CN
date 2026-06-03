# Phase 2 Step 1 入口职责边界审计

> Historical Note
>
> 本文档保留为 Phase 2 的边界审计记录，不再单独定义当前入口契约。
> 当前真源和已关闭决策见 [workflowprogram-design-status.md](/mnt/d/Code/WorkflowProgram-CN/docs/workflowprogram-design-status.md)。

## 1. 目的

本审计只回答三个问题：

1. 当前哪些入口是真正的 WorkflowProgram 主能力。
2. 当前哪些入口只是通用复用能力或仓库维护能力。
3. 新的 `workflowprogram-*` skills 应该覆盖哪些能力，不应该吞并哪些能力。

## 2. 当前入口盘点

### 2.1 Commands

当前公开 commands 共 6 个：

- `develop`
- `ship`
- `preflight`
- `hotfix`
- `evolve-workflow`
- `iterate-workflow`

### 2.2 Skills

当前公开 skills 共 6 个：

- `review`
- `test`
- `commit`
- `doc`
- `workflow-audit`
- `validate-file`

另有 1 个内部支持 skill：

- `develop` 目录，对外名称为 `workflow-spec-support`

## 3. 现有入口分类

### 3.1 WorkflowProgram 主能力入口

这一类直接定义“如何为目标项目开发、审计和迭代工作流”。

- `develop`
  - 当前角色：工作流设计主入口
  - 面向对象：目标项目工作流资产
  - 后续去向：迁移为 `workflowprogram-develop`

- `evolve-workflow`
  - 当前角色：工作流审计主入口
  - 面向对象：目标工作流仓库
  - 后续去向：迁移为 `workflowprogram-audit`

- `iterate-workflow`
  - 当前角色：基于 lessons 的工作流迭代主入口
  - 面向对象：目标工作流仓库
  - 后续去向：迁移为 `workflowprogram-iterate`

### 3.2 仓库维护/交付入口

这一类更接近“维护当前仓库变更”的交付流程，不是目标项目工作流开发的核心 API。

- `ship`
  - 当前角色：对当前变更执行审查、校验、提交准备
  - 典型对象：当前仓库 diff
  - 结论：保留为兼容/维护命令，不迁移为 `workflowprogram-*` 主入口

- `preflight`
  - 当前角色：对当前变更执行并行就绪检查
  - 典型对象：当前仓库 diff
  - 结论：保留为兼容/维护命令，不迁移为 `workflowprogram-*` 主入口

- `hotfix`
  - 当前角色：对当前仓库变更执行热修复流程
  - 典型对象：当前仓库分支和 diff
  - 结论：保留为兼容/维护命令，不迁移为 `workflowprogram-*` 主入口

### 3.3 复用能力型 skills

这一类不是 WorkflowProgram 的对外总控入口，而是可被主入口调用的能力模块。

- `review`
  - 作用：并行代码审查
  - 后续定位：保留为底层复用 skill

- `test`
  - 作用：运行关联测试或校验
  - 后续定位：保留为底层复用 skill

- `commit`
  - 作用：生成提交信息
  - 后续定位：保留为底层复用 skill

- `doc`
  - 作用：更新文档
  - 后续定位：保留为底层复用 skill

- `workflow-audit`
  - 作用：提供审计检查清单
  - 后续定位：作为 `workflowprogram-audit` 的底层复用能力

- `validate-file`
  - 作用：验证单个 workflow 文件
  - 后续定位：作为 `workflowprogram-validate` 的底层复用能力

### 3.4 内部支持资产

- `.claude/skills/develop/`
  - 实际名称：`workflow-spec-support`
  - 作用：给 `develop` 类流程提供规格模板
  - 结论：保留为内部支持资产，不对外升级为主入口

## 4. 关键冲突与约束

### 4.1 `develop` 命名冲突

当前已经有：

- command: `develop`
- support skill 目录：`.claude/skills/develop/`

如果新主入口也叫 `develop` skill，会同时造成：

- 对外入口名称混淆
- 目录职责混淆
- 后续构建产物中难以区分公开能力和内部支持资产

结论：

- 新主入口必须统一使用 `workflowprogram-*` 前缀

### 4.2 `preflight` 与 `workflowprogram-validate` 的边界

两者都带“验证”属性，但对象不同：

- `preflight`
  - 验证当前仓库 diff 是否 ready
- `workflowprogram-validate`
  - 验证目标项目中的 workflow 资产是否符合结构与约束

结论：

- `preflight` 不是 `workflowprogram-validate` 的别名
- 两者并存，但职责分层必须在文档中写清楚

### 4.3 `workflow-audit` 与 `workflowprogram-audit` 的边界

两者都涉及审计，但粒度不同：

- `workflow-audit`
  - 提供可复用的审计清单和检查标准
- `workflowprogram-audit`
  - 面向用户的完整审计入口，负责组织流程、读取目标、输出结论

结论：

- `workflow-audit` 保持底层 skill
- `workflowprogram-audit` 作为新的用户主入口

### 4.4 `validate-file` 与 `workflowprogram-validate` 的边界

两者都涉及验证，但作用范围不同：

- `validate-file`
  - 单文件级验证
- `workflowprogram-validate`
  - 目标项目 workflow 级验证

结论：

- `validate-file` 不应直接当成用户主入口
- `workflowprogram-validate` 应负责组织多文件/多资产验证

## 5. 新旧入口映射

| 当前入口 | 当前类型 | 后续角色 | 处理动作 |
|---|---|---|---|
| `develop` | command | `workflowprogram-develop` 的兼容入口 | 更新 |
| `evolve-workflow` | command | `workflowprogram-audit` 的兼容入口 | 更新 |
| `iterate-workflow` | command | `workflowprogram-iterate` 的兼容入口 | 更新 |
| `ship` | command | 维护型兼容入口 | 更新 |
| `preflight` | command | 维护型兼容入口 | 更新 |
| `hotfix` | command | 维护型兼容入口 | 更新 |
| `review` | skill | 底层复用能力 | 保留 |
| `test` | skill | 底层复用能力 | 保留 |
| `commit` | skill | 底层复用能力 | 保留 |
| `doc` | skill | 底层复用能力 | 保留 |
| `workflow-audit` | skill | `workflowprogram-audit` 的底层能力 | 保留 |
| `validate-file` | skill | `workflowprogram-validate` 的底层能力 | 保留 |
| `workflow-spec-support` | internal skill | `workflowprogram-develop` 的内部支持资产 | 保留 |

## 6. 建议的新 skills-first 集合

Phase 2 应新增 5 个对外 skills：

- `workflowprogram-orchestrate`
  - 总控入口
  - 负责根据用户自然语言请求路由到 develop / audit / iterate / validate

- `workflowprogram-develop`
  - 工作流设计主入口
  - 目标是为 `TARGET_ROOT/.claude/` 生成或更新工作流资产

- `workflowprogram-audit`
  - 工作流审计主入口
  - 目标是对目标项目现有 workflow 资产进行结构和模式审计

- `workflowprogram-iterate`
  - 工作流迭代主入口
  - 目标是基于 `lessons.md` 和审计结果生成改进方案

- `workflowprogram-validate`
  - 工作流验证主入口
  - 目标是对目标项目 workflow 资产执行结构化验证

## 7. 对后续实现的约束

### 7.1 不要把仓库维护命令错误纳入主产品 API

`ship`、`preflight`、`hotfix` 需要保留，但不应被包装成 WorkflowProgram 在目标项目里的主要对外能力。

### 7.2 不要把底层 skill 直接升级成主入口

`workflow-audit`、`validate-file` 是能力模块，不是完整产品入口。

### 7.3 skill 文案必须显式区分路径

新的 `workflowprogram-*` skills 需要显式区分：

- `PLUGIN_ROOT`
- `TARGET_ROOT`
- 必要时的 `RUN_ROOT`

### 7.4 旧 commands 不能继续像主入口一样叙述

Phase 2 后，旧 commands 应保留兼容调用方式，但文案定位必须明确降级。

## 8. 审计结论

Phase 2 的核心不是“把所有 command 改写成 skill”，而是：

1. 把真正属于 WorkflowProgram 产品能力的入口提炼成 `workflowprogram-*` skills。
2. 把仓库维护型命令与产品主入口分离。
3. 把底层复用 skill 与用户主入口分离。
4. 用新的命名体系避免 `develop` 这类历史入口与内部支持资产冲突。
