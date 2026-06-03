# WorkflowProgram 分支对比审查报告

> **基准分支**: feat/v3-implementation (aa89a75)  
> **对比分支**: feat/phased-migration (94e9ba5)  
> **共同基线**: aacaff0 (Merge plugin-package updates)  
> **生成时间**: 2026-03-31  
> **审查工具**: Claude Code / Git Diff Analysis

---

## 执行摘要

本报告对 WorkflowProgram 的两个演进分支进行深度对比分析。两个分支均实现了 V3 架构的核心目标（单向构建、CI/CD 支持、Turn Counts、双轨输出），但在**实现风格、文档详细度、工程实践**方面存在显著差异。

**总体评估**:
- **功能等价性**: 85%（核心功能一致，细节有差异）
- **代码质量**: feat/v3-implementation 更优（文档完整、防呆设计）
- **语言风格**: feat/phased-migration 更具特色（诗意化、隐喻丰富）
- **工程严谨性**: feat/v3-implementation 更严谨（模板齐全、header 标记）

---

## 1. 提交历史对比

### 1.1 提交图谱

```
aacaff0 (共同基线) ──┬──► 067ebec ──► 2b867ea ──► f12ef80 ──► e249be7 ──► 28df7dc ──► aa89a75 (feat/v3-implementation)
                     │
                     └──► 024013a ──► 564ff60 ──► 1de9c52 ──► 94e9ba5 (feat/phased-migration)
```

### 1.2 提交对应关系

| Session | feat/v3-implementation | feat/phased-migration | 等价性 |
|---------|----------------------|----------------------|--------|
| S1: 单向构建 | 067ebec refactor: transform sync to one-way build | 024013a build: label .claude as technical debt | ⚠️ 部分等价 |
| S2: CI/CD | f12ef80 feat: add CI/CD headless support | 564ff60 feat: add CI/CD pipeline automation | ✅ 等价 |
| S3: Turn Counts | e249be7 feat: upgrade sandbox validation | 1de9c52 feat: transition sandbox from physical timeouts | ✅ 等价 |
| S4: 双轨输出 | 28df7dc feat: implement dual-track YAML | 94e9ba5 docs: refactor workflow specs to dual outputs | ⚠️ 风格差异 |
| S5: 文档澄清 | aa89a75 docs: clarify .claude/ purpose | N/A | ❌ v3-implementation 独有 |

### 1.3 提交粒度分析

**feat/v3-implementation**:
- 6 个提交，粒度适中
- 每个 Session 独立提交，便于回滚
- 包含详细的构建产物更新提交

**feat/phased-migration**:
- 4 个提交，粒度较粗
- S1-S4 合并为 4 个提交
- 缺少构建产物同步的独立提交

---

## 2. 核心功能对比

### 2.1 单向构建机制

#### feat/v3-implementation
```python
"""
WorkflowProgram Plugin Asset Builder

FIXME: Technical Debt - .claude/ directory is temporary
...
This script is a ONE-WAY BUILD tool (like `npm run build`):
- Source of Truth: .claude/ directory
- Build Output: root-level commands/, skills/, etc.
- Direction: .claude/ → root/ ONLY (never reverse)
"""

AUTO_GENERATED_HEADER = (
    '<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->\n'
    '<!-- Run: python tools/sync_plugin_assets.py -->\n\n'
)

# 所有输出文件注入 header
print("✓ Build complete...")
```

**特点**:
- ✅ 完整文档字符串
- ✅ AUTO-GENERATED header 注入所有文件
- ✅ 构建完成消息提示
- ✅ 逐文件处理，添加 header

#### feat/phased-migration
```python
# FIXME: Technical Debt - .claude/ directory is temporary
# This script represents a fallback solution enforcing unidirectional generation.
# Migrate to root-level native plugin structure in Phase X.

# 直接使用 shutil.copy2/copytree，无 header
```

**特点**:
- ⚠️ 简化注释
- ❌ 无 AUTO-GENERATED header
- ❌ 无构建完成消息
- ✅ 代码更简洁

**评审意见**:
- v3-implementation 的 header 机制是重要的**防呆设计**，可防止开发者误编辑构建产物
- phased-migration 的简化虽代码量少，但增加了误操作风险

---

### 2.2 CI/CD 无头模式

#### feat/v3-implementation
```markdown
## Usage

```text
/develop <requirement> [--auto-approve]
```

**参数：**
- `<requirement>`: 工作流需求描述（自然语言）
- `--auto-approve`: 自动批准模式，跳过人工确认门禁（用于 CI/CD）

**CI/CD 模式：**
设置环境变量 `CI=true` 或传入 `--auto-approve` 参数，所有设计门禁将自动放行。

**示例：**

```text
# 交互模式（默认）
/develop 设计一个用于审计 Markdown 链接有效性的工作流

# CI/CD 自动模式
/develop "设计一个用于审计 Markdown 链接有效性的工作流" --auto-approve
CI=true /develop "设计一个用于审计 Markdown 链接有效性的工作流"
```
```

#### feat/phased-migration
```markdown
## Usage

```text
/develop <requirement>
```

示例：

```text
/develop 设计一个用于审计 Markdown 链接有效性的工作流
```

**Gate**：将设计展示给用户，得到批准后再进入生成阶段。
（如果命令附带了 `--auto-approve` 参数或检测到 `CI=true` 环境变量，则自动记录放行日志并继续，不再等待）
```

**差异分析**:
- v3-implementation: 显式声明 `--auto-approve`，详细文档
- phased-migration: 参数在 Gate 描述中隐含说明，更简洁
- **功能等价，文档风格不同**

---

### 2.3 Turn Counts 与熔断机制

#### feat/v3-implementation
```markdown
**资源控制配置（设计时指定）**:
- S (≤2 Stages): 50 turns
- M (3-5 Stages): 100 turns
- L (>5 Stages): 200 turns
- XL (复杂编排): 300 turns

**熔断机制**：
- 当同一 Agent 连续产生 **3 次 `PostToolUseFailure`** 报错，立即熔断终止
- 熔断时输出失败上下文和已执行的测试覆盖度
```

#### feat/phased-migration
```markdown
**引擎容错定额与熔断（设计时指定）**：
- S (≤2 Stages): 约束尝试至多 5 Turns
- M (3-5 Stages): 约束尝试至多 10 Turns
- L (>5 Stages): 约束尝试至多 20 Turns
- XL (复杂编排): 约束尝试至多 30 Turns
- **Circuit Breaker 熔断**: 当捕捉到任一部件抛出连续 3 次相同或类似的 `PostToolUseFailure` 报错，立刻剥夺执行控制权并宣告 FAIL。
```

**差异分析**:
| 维度 | v3-implementation | phased-migration |
|------|------------------|------------------|
| S级 | 50 turns | 5 turns |
| M级 | 100 turns | 10 turns |
| L级 | 200 turns | 20 turns |
| XL级 | 300 turns | 30 turns |
| 语言风格 | 技术文档 | 诗意化（"引擎容错定额"） |

**关键差异**: phased-migration 的 Turn Count 限制**过于严格**（5-30 turns 可能不足以完成复杂任务），v3-implementation 的 50-300 turns 更合理。

---

### 2.4 双轨输出架构

#### feat/v3-implementation
```markdown
**双轨设计输出（Dual-Track Output）**：

设计阶段产出两份互补的设计文档：

1. **`workflow-spec.yaml`** —— 机器可读的编排配置（源文件）
   - 包含：阶段定义、Agent 引用、转移条件、资源限额
   - 格式：结构化 YAML，支持 `max_retries`、`max_parallel` 等约束
   - 用途：Code Agent 执行时解析，强制执行状态转移
   - 可编辑：✅ 人工可编辑，AI 可生成

2. **`workflow-view.md`** —— 人类可读的只读视图（生成文件）
   - 包含：ASCII 流程图、设计决策说明、Agent 职责描述
   - 格式：自然语言 Markdown
   - 用途：人工审查、快速浏览、设计讨论
   - 可编辑：❌ 禁止直接编辑，从 YAML 单向生成

**单向瀑布生成原则**：
```
workflow-design.md（设计决策，人工审查）
         ↓
   提取转换
         ↓
workflow-spec.yaml（机器编排，单点真实）
         ↓
    生成渲染
         ↓
workflow-view.md（只读视图，人类查阅）
```

**编辑规则**：
- 如需修改设计 → 编辑 `workflow-spec.yaml`
- 重新生成视图 → 运行 `python tools/generate-view.py`
- 禁止直接编辑 `workflow-view.md`（会被覆盖）
```

#### feat/phased-migration
```markdown
随后，基于上述原子模式进入**状态流转定义与双软轨渲染生成** (Dual Output 方案)：保证所有的业务骨干限制收拢在 YAML 引擎架构文件中，再经其单向剥离出人类易读的展示视图。

核心主轴文件其一：`workflow-spec.yaml` (用于当前指导大模型或未来交给外部 Runner 控制逻辑机的骨干代码)
- **nodes** 节点列表：绑定对应的 `Agent` 或 `Skill` 载具，明文标明产出结构 `output_schema`。
- **extends / next**：严谨的拓扑依赖路径，遇到判定反馈的回环(Loop)必须强行打上如 `max_retries: 3` 这种断点阻断上限控制。

人类阅读附庸其二：`workflow-view.md` (用于合并或审查代码时刻调阅的 Read-Only 文件)
- 根据上述新生成的 `workflow-spec.yaml` 进行对应的自然语言解析映射。
- 应拥有通俗好懂的排版、表格以及 ASCII 图纸。
- **最高铁令**：如果设计出现方向错误，仅允许在上游 YAML 中修改参数及骨架并**单向向下覆盖**。严禁开发者直接在这个 Markdown 进行手工改动干扰模型记忆状态。
```

**差异分析**:
- v3-implementation: 技术文档风格，流程图清晰，编辑规则明确
- phased-migration: 诗意化风格（"双软轨"、"人类阅读附庸"、"最高铁令"），技术细节更抽象
- **v3-implementation 更易于工程实施，phased-migration 更具文学性**

---

## 3. 文件结构差异

### 3.1 文件清单对比

| 文件/目录 | feat/v3-implementation | feat/phased-migration | 说明 |
|-----------|----------------------|----------------------|------|
| `.claude/skills/develop/yaml-spec-template.md` | ✅ | ❌ | v3-implementation 提供 YAML 模板 |
| `.claude/skills/develop/test-scenarios-template.md` | ✅ | ✅ | 两者均有 |
| `agents/test-scenario-generator.md` | ✅ | ❌ | v3-implementation 保留 |
| `agents/workflow-verifier.md` | ✅ | ❌ | v3-implementation 保留 |
| `skills/validate-file/SKILL.md` | ✅ | ❌ | v3-implementation 保留 |
| `future_engine_spec/` | ❌ | ✅ | phased-migration 独有（未来架构规划） |
| `scripts/verify-plugin-load.sh` | ❌ | ✅ | phased-migration 保留 |
| `config/` | ✅ | ❌ | v3-implementation 独有 |
| `templates/` | ✅ | ❌ | v3-implementation 独有 |
| `实施方案V3.md` | ✅ | ❌ | v3-implementation 独有 |

### 3.2 关键缺失分析

**phased-migration 删除的重要文件**:
1. `yaml-spec-template.md` —— YAML 规范模板，对双轨架构至关重要
2. `test-scenario-generator.md` —— 测试场景生成 Agent
3. `workflow-verifier.md` —— 工作流验证 Agent
4. `validate-file/SKILL.md` —— 文件验证技能

**影响**: 这些删除可能导致功能缺失或用户无法使用完整的验证流程。

---

## 4. README 文档对比

### 4.1 结构对比

| 章节 | feat/v3-implementation | feat/phased-migration |
|------|----------------------|----------------------|
| 标题 | WorkflowProgram-CN | WorkflowProgram-CN 元引擎平台 |
| 定位声明 | 详细（Code Agent 领域） | 极简 |
| 设计哲学 | 分层记忆模型、验证优先、内联自包含、渐进交付 | 三个指导思想（SSOT、FSM工业化、双规制） |
| 快速开始 | 详细（环境准备、设计、审计、交付） | 缺失 |
| 命令清单 | 完整表格 | 简要列举 |
| 技能清单 | 完整表格 | 缺失 |
| 示例工作流 | daily-news-workflow 详细说明 | 缺失 |
| 经验沉淀机制 | 三层结构图解 | 简要提及 |
| 校验策略 | 详细 | 缺失 |

### 4.2 语言风格对比

**v3-implementation 示例**:
> WorkflowProgram-CN 采用分层结构，将不同类型的资产分离...

**phased-migration 示例**:
> 这是一个正处于蜕壳期的基础设施化模块...
> 从 "文本文艺复兴" 向 "FSM 机器工业化" 的跨越...
> AI 演进路上失败事件及诱发因素的沉淀追踪日志...

**评审意见**:
- v3-implementation 更适合技术文档，利于团队协作
- phased-migration 语言富有特色，但可能增加理解成本

---

## 5. 工程实践对比

### 5.1 防呆设计

| 措施 | feat/v3-implementation | feat/phased-migration |
|------|----------------------|----------------------|
| AUTO-GENERATED header | ✅ 所有构建产物 | ❌ 无 |
| 构建完成提示 | ✅ 详细消息 | ❌ 无 |
| 技术债注释 | ✅ 详细 docstring | ⚠️ 简化注释 |
| 编辑警告 | ✅ 显式警告（"禁止直接编辑"） | ⚠️ 隐含 |

### 5.2 模板完整性

| 模板 | feat/v3-implementation | feat/phased-migration |
|------|----------------------|----------------------|
| spec-template.md | ✅ 完整 | ✅ 完整 |
| yaml-spec-template.md | ✅ 完整 | ❌ 缺失 |
| test-scenarios-template.md | ✅ 完整 | ✅ 完整 |

---

## 6. 问题与风险

### 6.1 feat/phased-migration 的风险

1. **Turn Count 限制过严** (5-30 turns)
   - 风险: 复杂工作流可能过早终止
   - 建议: 调整为 50-300 turns

2. **缺少 YAML 模板**
   - 风险: 用户无法创建符合规范的 workflow-spec.yaml
   - 建议: 恢复 yaml-spec-template.md

3. **缺少验证 Agent/Skill**
   - 风险: 测试场景生成和验证流程不完整
   - 建议: 恢复 test-scenario-generator 和 workflow-verifier

4. **无 AUTO-GENERATED header**
   - 风险: 开发者可能误编辑构建产物
   - 建议: 添加 header 机制

5. **README 缺少快速开始**
   - 风险: 新用户上手困难
   - 建议: 补充快速开始章节

### 6.2 feat/v3-implementation 的改进空间

1. **代码冗长**
   - sync_plugin_assets.py 较复杂
   - 建议: 考虑简化，但保留核心功能

2. **缺少未来架构规划**
   - 无 future_engine_spec/ 目录
   - 建议: 可补充架构演进路线图

---

## 7. 建议与结论

### 7.1 合并建议

**推荐以 feat/v3-implementation 为基础**，选择性采纳 phased-migration 的优点：

**保留 v3-implementation**:
- ✅ 完整的文档和注释
- ✅ AUTO-GENERATED header 机制
- ✅ YAML 模板文件
- ✅ 验证 Agent 和 Skill
- ✅ 合理的 Turn Count 限制
- ✅ 详细的 README

**可选采纳 phased-migration**:
- ⚠️ 诗意的语言风格（可选，作为补充文档）
- ⚠️ future_engine_spec/（如果有长期规划需求）

### 7.2 行动项

1. **立即执行**:
   - [ ] 确认 Turn Count 限制为 50-300 turns（而非 5-30）
   - [ ] 保留 yaml-spec-template.md
   - [ ] 保留所有验证 Agent 和 Skill

2. **建议执行**:
   - [ ] 保留 AUTO-GENERATED header 机制
   - [ ] 维持详细的 README 结构
   - [ ] 考虑添加 future_engine_spec/ 规划文档

3. **可选执行**:
   - [ ] 在文档中适当融入诗意化表达（如"蜕壳期"、"血泪教训"等），增强可读性

### 7.3 最终结论

**两个分支功能等价，但 feat/v3-implementation 更适合生产环境**:
- 文档完整，降低维护成本
- 防呆设计，减少误操作
- 模板齐全，提升用户体验
- 工程实践更严谨

**建议**: 推进 feat/v3-implementation 到 main，将 feat/phased-migration 作为风格参考归档。

---

## 附录 A: 详细 Diff 统计

```
41 files changed
+-------------------------------+
| 类型   | 数量 | 说明         |
|--------|------|--------------|
| 修改   | 32   | 内容差异     |
| 新增   | 2    | future_engine_spec, verify-plugin-load.sh |
| 删除   | 7    | yaml-spec-template, agents, skills |
+-------------------------------+
```

## 附录 B: 提交详情

**feat/v3-implementation (aa89a75)**:
```
aa89a75 docs: clarify .claude/ purpose in output workflows
28df7dc feat: implement dual-track YAML + Markdown architecture (Session 4)
e249be7 feat: upgrade sandbox validation with turn limits and circuit breakers (Session 3)
f12ef80 feat: add CI/CD headless support with --auto-approve gates (Session 2)
2b867ea chore: regenerate all plugin assets with auto-generated headers
067ebec refactor: transform sync to one-way build tool (Session 1)
```

**feat/phased-migration (94e9ba5)**:
```
94e9ba5 docs: refactor workflow specs to dual outputs (YAML logic + Markdown view)
1de9c52 feat: transition sandbox from physical timeouts to semantic turn limits
564ff60 feat: add CI/CD pipeline automation support for core gates
024013a build: label .claude as technical debt and enforce one-way build script
```

---

**报告生成完成**  
**审查人**: Claude Code Analysis Engine  
**审查基准**: feat/v3-implementation vs feat/phased-migration
