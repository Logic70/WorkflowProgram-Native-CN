# Ch7: 经验积累 — 为什么 S6 不是可有可无的附录

> 不会学习的 workflow，迟早会重复踩同样的坑。

## 7.1 S6 在当前实现里负责什么

`WorkflowProgram` 明确把经验积累收进 `S6`，而不是把它当成“流程外总结”。

S6 的目标是：

- 提炼 lessons
- 形成约束候选
- 给出下一轮改进建议

这意味着经验积累本身也是 workflow 的一部分。

## 7.2 两层记忆模型

当前设计里，经验分两层：

- `lessons.md`
  - 追加式日志
  - 记录失败经验、冲突、待提取约束
- `.claude/rules/constraints.md`
  - 长期规则
  - 用 `ALWAYS/NEVER` 固化稳定经验

这是 [CLAUDE.md](/mnt/d/Code/WorkflowProgram-CN/CLAUDE.md) 里明确写出来的三层记忆模型中的核心部分。

## 7.3 当前已经硬化到脚本的部分

现在已经做成 machine-check 的，是 S6 的最小闭环：

- `RUN_ROOT/outputs/stages/s6-lessons-delta.md` 必须存在
- 必须包含本次 `run_id`
- 必须包含本次 `failure_kind`
- 必须包含约束候选或显式“无新增约束”
- `user-progress.md` 必须含“历史关键节点结果”

这部分由 [validate-lessons-delta.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/validate-lessons-delta.py) 校验。

## 7.4 为什么 WorkflowProgram 自己就是最好案例

`WorkflowProgram-CN` 自己就在实践这套模型：

- 维护自己的 `lessons.md`
- 维护自己的 `constraints.md`
- 用设计真源和能力矩阵避免漂移

所以它不是“只要求别人做闭环”，而是“自己也按这套闭环在运行”。

## 7.5 提炼模板

一个会学习的 workflow，至少要回答：

1. 失败记录在哪
2. 哪些经验只是日志，哪些要变规则
3. 新会话默认加载什么
4. 哪些经验会进入下一轮约束

如果没有这一层，workflow 只有执行，没有演进。

## 下一章

继续看 [Ch8: 迁移到你的项目](./08_apply_to_your_project.md)。

