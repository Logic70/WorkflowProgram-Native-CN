# WorkflowProgram Plugin 架构迁移实施计划

**目标日期**: 2026-04-01  
**基础版本**: WorkflowProgram V3（当前 main 分支）  
**目标版本**: WorkflowProgram Plugin v1.0

---

## 1. 目标状态定义

### 1.1 架构转变

```
当前状态（项目模式）
===================
WorkflowProgram-CN/           ← 用户需要克隆到此路径
├── .claude/commands/develop.md   ← /develop 命令
├── .claude/commands/ship.md      ← /ship 命令
└── ...

用户工作流：
1. git clone WorkflowProgram-CN
2. cd WorkflowProgram-CN
3. /develop "需求"
4. /ship

目标状态（Plugin 模式）
======================
~/.claude/plugins/workflow-generator/   ← Plugin 安装路径
├── core/                               ← Framework 核心
│   ├── templates/                      ← 工作流模板
│   ├── generators/                     ← 生成逻辑
│   └── manifest.json                   ← Plugin 元数据
└── plugin-commands/                    ← 全局可用命令
    └── init-workflow.md

用户工作流：
1. 任意路径下："帮我创建一个抓取新闻的工作流"
2. 在当前路径生成 .claude/ 工作区配置
3. 后续迭代："改成每天早上8点执行"（直接在当前路径修改）
```

### 1.2 关键变化

| 维度 | 当前（V3） | 目标（Plugin） |
|------|-----------|---------------|
| **入口** | `/develop "需求"` | 自然语言识别 |
| **执行路径** | WorkflowProgram 项目路径 | 用户当前路径 |
| **交付** | `/ship` 独立命令 | 自动或自然语言触发 |
| **Framework 位置** | 项目路径下 | Plugin 目录中 |
| **用户项目内容** | 无（输出到外部） | 完整 `.claude/` 工作区 |

---

## 2. 实施阶段

### Phase 1: 准备工作（1-2 天）

#### 2.1.1 创建 Plugin 目录结构

**新增文件**: `plugin/manifest.json`

```json
{
  "name": "workflow-generator",
  "version": "1.0.0",
  "description": "基于自然语言创建和迭代 Claude Code 工作流",
  "entry": {
    "intent_detection": "core/intent-parser.md",
    "commands": ["plugin-commands/init-workflow.md"]
  },
  "framework": {
    "templates_path": "core/templates",
    "generators_path": "core/generators"
  }
}
```

**新增目录**:
```
plugin/
├── manifest.json
├── core/
│   ├── templates/
│   │   ├── workflow-spec-template.md   ← 从 .claude/skills/develop/ 移动
│   │   └── agent-templates/
│   ├── generators/
│   │   ├── stage1-analyzer.py          ← 需求解析
│   │   ├── stage2-spec-generator.py    ← 规格生成
│   │   ├── stage3-designer.py          ← 设计文档
│   │   └── stage4-file-generator.py    ← 文件生成
│   └── intent-parser.md                ← 自然语言意图识别
└── plugin-commands/
    └── init-workflow.md                ← 全局命令入口
```

#### 2.1.2 提取可复用逻辑

**从现有文件提取**:
- `.claude/commands/develop.md` → 拆分到 generators/
- `.claude/skills/develop/spec-template.md` → `core/templates/`
- `.claude/scripts/state-bus.py` → `core/utils/state-bus.py`

#### 2.1.3 更新构建脚本

**修改**: `tools/sync_plugin_assets.py`

```python
# 新增：构建 Plugin 包
"""
从 .claude/ 提取核心逻辑，构建 plugin/ 目录
保留原有功能：同步到根级目录（用于发布到 Plugin Registry）
新增功能：提取核心逻辑到 plugin/core/
"""

def build_plugin_package():
    """构建 Plugin 安装包"""
    # 1. 复制 templates
    # 2. 提取 generators 逻辑
    # 3. 生成 manifest.json
    pass
```

---

### Phase 2: 核心重构（3-4 天）

#### 2.2.1 开发自然语言入口

**新建**: `plugin/core/intent-parser.md`

```markdown
---
name: Intent Parser
description: 解析用户自然语言，识别工作流创建/迭代意图
---

## 识别规则

### 创建意图
触发词：创建、做一个、帮我弄、初始化、新建、生成
示例：
- "创建一个每天抓取新闻的工作流"
- "帮我做一个自动备份的脚本"
- "初始化一个代码审查工作流"

提取参数：
- 核心需求：抓取新闻 / 自动备份 / 代码审查
- 触发方式：每天 / 每小时 / 手动 / 文件变更
- 输出目标：当前路径

### 迭代意图
触发词：改成、修改为、优化、调整、更新
示例：
- "改成每天早上8点执行"
- "添加发送邮件的功能"

提取参数：
- 修改项：时间 / 动作 / 条件
- 新值：早上8点 / 发送邮件

### 交付意图
触发词：提交、保存、完成、ship、push
示例：
- "提交这个工作流"
- "保存到 git"
```

#### 2.2.2 重构 `/develop` 为 Generator 模块

**拆分现有逻辑**:

```
当前：.claude/commands/develop.md（单文件，Stage 1-4）

目标：plugin/core/generators/
├── __init__.py
├── stage1_analyzer.py      # 需求分析
├── stage2_spec_generator.py # workflow-spec.yaml 生成
├── stage3_designer.py       # workflow-view.md 生成
├── stage4_file_generator.py # 实际文件写入
└── orchestrator.py          # 统一调度
```

**关键变化**:
- 移除用户交互式阶段确认（改为自然语言驱动）
- 目标路径参数化（从当前工作目录获取）
- 移除 `/ship` 调用（交付由独立意图触发或自动完成）

#### 2.2.3 创建 Plugin 全局命令

**新建**: `plugin/plugin-commands/init-workflow.md`

```markdown
---
name: init-workflow
description: 在当前路径初始化工作流（由自然语言触发）
---

## Usage

用户自然语言触发后，此命令执行：

1. 检测当前路径是否已有 `.claude/` 目录
   - 如有 → 询问是迭代还是覆盖
   - 如无 → 继续创建

2. 调用 Intent Parser 提取参数
   - 核心需求
   - 触发方式
   - 特殊要求

3. 执行生成流水线
   - Stage 1: 需求分析
   - Stage 2: 规格生成
   - Stage 3: 设计文档
   - Stage 4: 文件生成（写入当前路径）

4. 输出结果
   - 生成的命令列表
   - 使用方法提示
   - 后续迭代建议
```

#### 2.2.4 内化 Ship 逻辑

**移除独立命令**: `.claude/commands/ship.md`（从 Plugin 模式移除）

**集成到 Generator**:

```python
# stage4_file_generator.py

def generate_and_commit(files, target_path, options=None):
    """
    生成文件并可选自动提交
    
    options:
        auto_commit: bool  # 是否自动 git commit
        commit_message: str
    """
    # 1. 写入文件
    write_files(files, target_path)
    
    # 2. 可选：自动交付
    if options and options.get('auto_commit'):
        commit_changes(target_path, options['commit_message'])
    
    # 3. 返回结果摘要
    return {
        'files_created': len(files),
        'git_committed': options.get('auto_commit', False)
    }
```

**新增自然语言交付触发**:

```markdown
# intent-parser.md 中添加

### 交付意图
用户说："提交这个工作流"、"保存到 git"

执行：
1. 检测当前路径是否有未提交的 .claude/ 变更
2. 如有 → 执行 git add + commit + push
3. 询问提交信息（或自动生成）
```

---

### Phase 3: 测试与验证（2-3 天）

#### 2.3.1 本地 Plugin 测试

**测试场景**:

```bash
# 场景1：从零创建工作流
cd ~/test-projects
mkdir news-demo
cd news-demo

# 用户输入：
"帮我创建一个每天抓取AI新闻的工作流"

# 期望结果：
# 1. 当前路径生成 .claude/settings.json
# 2. 当前路径生成 .claude/commands/fetch-news.md
# 3. 当前路径生成 .claude/skills/news-analysis.md

# 场景2：迭代工作流
# 在同一目录下，用户输入：
"改成每天早上8点执行，并添加发送到邮箱的功能"

# 期望结果：
# 1. 修改现有命令的触发时间
# 2. 新增邮件发送技能

# 场景3：交付工作流
# 用户输入：
"提交这个工作流到 git"

# 期望结果：
# 1. git init（如未初始化）
# 2. git add .claude/
# 3. git commit -m "feat: 添加新闻抓取工作流"
# 4. （如有远程）git push
```

#### 2.3.2 更新验证脚本

**修改**: `.claude/scripts/validate-workflow.py`

```python
# 新增 Plugin 模式验证

def validate_plugin_mode():
    """验证 Plugin 结构完整性"""
    checks = [
        ('manifest.json 存在', check_manifest_exists),
        ('core/ 目录结构完整', check_core_structure),
        ('generator 模块可导入', check_generators_importable),
        ('template 文件存在', check_templates_exist),
    ]
    return run_checks(checks)

def validate_plugin_installation():
    """验证 Plugin 可安装到 Claude Code"""
    # 模拟安装到 ~/.claude/plugins/
    # 验证全局命令注册
    pass
```

---

### Phase 4: 文档与发布（2 天）

#### 2.4.1 更新项目文档

**修改**: `README.md`

```markdown
# WorkflowProgram Plugin

## 安装

```bash
# 克隆到 Claude Code Plugin 目录
git clone https://github.com/yourname/WorkflowProgram-CN \
  ~/.claude/plugins/workflow-generator
```

## 使用

安装后，在任何项目路径下：

```
"帮我创建一个抓取新闻的工作流"
"改成每天早上8点执行"
"提交这个工作流"
```

## 架构

- `core/` - Framework 核心逻辑
- `plugin-commands/` - 全局可用命令
- 用户项目只包含生成的 `.claude/` 配置
```

**修改**: `CLAUDE.md`

更新架构说明，反映 Plugin 模式。

#### 2.4.2 创建迁移指南

**新建**: `docs/migration/v3-to-plugin.md`

```markdown
# 从 V3 项目模式迁移到 Plugin 模式

## 如果你是 V3 用户

1. 备份你的自定义模板
2. 删除旧的 WorkflowProgram 克隆
3. 按新方式安装 Plugin
4. 你的工作流项目无需修改（标准 .claude/ 结构兼容）

## 破坏性变更

- `/develop` 命令 → 自然语言触发
- `/ship` 命令 → 自然语言触发或自动交付
- 需要重新克隆到 Plugin 目录
```

---

## 3. 文件变更清单

### 新增文件

```
plugin/
├── manifest.json
├── core/
│   ├── __init__.py
│   ├── intent-parser.md
│   ├── generators/
│   │   ├── __init__.py
│   │   ├── stage1_analyzer.py
│   │   ├── stage2_spec_generator.py
│   │   ├── stage3_designer.py
│   │   ├── stage4_file_generator.py
│   │   └── orchestrator.py
│   ├── templates/
│   │   ├── workflow-spec-template.md
│   │   └── agent-templates/
│   │       ├── analyzer-agent.md
│   │       ├── designer-agent.md
│   │       └── reviewer-agent.md
│   └── utils/
│       └── state-bus.py
├── plugin-commands/
│   └── init-workflow.md
docs/
└── migration/
    └── v3-to-plugin.md
```

### 修改文件

```
.claude/commands/develop.md          # 标记为废弃，内容迁移到 generators/
.claude/commands/ship.md             # 标记为废弃，逻辑内化
.claude/scripts/validate-workflow.py # 添加 Plugin 模式验证
tools/sync_plugin_assets.py          # 添加 Plugin 构建功能
README.md                            # 更新为 Plugin 使用方式
CLAUDE.md                            # 更新架构说明
```

### 保留文件（无需修改）

```
.claude/skills/                      # Skill 定义保留，可被 Plugin 引用
.claude/rules/                       # 约束规则保留
.claude/scripts/state-bus.py         # 保留，同时复制到 Plugin
lessons.md                           # 保留
constraints.md                       # 保留
```

---

## 4. 风险与应对

| 风险 | 影响 | 应对策略 |
|------|------|---------|
| Claude Code Plugin API 不稳定 | 高 | 保持关注官方文档，预留适配层 |
| 自然语言意图识别不准确 | 中 | 初期保留 `/init-workflow` 显式命令作为 fallback |
| 用户习惯显式命令 | 中 | 文档中同时说明两种方式，渐进迁移 |
| 生成逻辑迁移引入 bug | 中 | 完整回归测试，保留 V3 分支可回滚 |

---

## 5. 验证标准

### 5.1 功能验证

- [ ] Plugin 安装到 `~/.claude/plugins/` 后全局命令可用
- [ ] 自然语言"创建工作流"触发生成流程
- [ ] 在当前路径生成标准 `.claude/` 工作区
- [ ] 自然语言"迭代工作流"修改现有配置
- [ ] 自然语言"提交工作流"执行 git 交付

### 5.2 兼容性验证

- [ ] 生成的 `.claude/` 结构与 V3 一致
- [ ] 现有 Skill 和 Agent 可在 Plugin 模式复用
- [ ] 验证脚本通过所有检查

### 5.3 性能验证

- [ ] 生成流程耗时与 V3 相当
- [ ] Plugin 加载不显著影响 Claude Code 启动

---

## 6. 后续迭代方向

1. **Web 界面**: 提供可视化工作流设计器
2. **模板市场**: 允许用户分享和下载工作流模板
3. **版本管理**: 工作流版本回滚和对比
4. **协作功能**: 多人协作开发工作流

---

**计划制定**: Claude Code  
**审核**: 待用户确认  
**开始时间**: 用户批准后
