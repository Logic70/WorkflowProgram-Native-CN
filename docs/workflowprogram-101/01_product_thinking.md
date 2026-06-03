# Ch1: 设计哲学 — Workflow 不是 Prompt，而是产品

> 能跑起来不等于可维护。WorkflowProgram 关心的是“能不能长期稳定地跑”。

## 1.1 为什么不能只靠 prompt

如果一个 workflow 只有 prompt 和人工约定，通常会有这些隐患：

- 机器可读真源缺失
- 步骤顺序依赖模型“自己记得”
- 失败后无法判断哪一层出了问题
- 经验只能留在聊天记录里

这类 workflow 在单人、一次性使用时问题不大，但一旦要共享、交付和演进，就会开始失控。

## 1.2 WorkflowProgram 的产品化回答

当前实现给出的答案是四层：

1. 真源：`workflow-spec.yaml`
2. 控制面：`workflow-entry.py` + `workflow-runner.py`
3. 验证层：`workflowprogram-validate`
4. 闭环层：`S6 lessons & constraints`

这四层对应的不是不同文档，而是不同职责。

## 1.3 当前实现里的关键判断

在 [workflowprogram-stage-highlevel-design.md](/mnt/d/Code/WorkflowProgram-CN/docs/workflowprogram-stage-highlevel-design.md) 里，最值得注意的是这些结论：

- `workflow-spec.yaml` 是控制面真源
- runner 只负责控制面，不负责 S5 主判定
- `workflowprogram-validate` 负责 workflow 级 verdict
- S6 负责 lessons 与约束候选

也就是说，`WorkflowProgram` 不接受“一段大 prompt 同时负责设计、执行、验证和总结”。

## 1.4 用一个问题检验你的 workflow

如果你在设计自己的 workflow，可以先问这 4 个问题：

1. 机器可读真源是什么
2. 控制面是谁负责
3. 最终验证由谁给结论
4. 失败经验沉淀到哪里

有任何一条答不上来，就说明还没真正产品化。

## 1.5 提炼模板

判断一个 workflow 是否成熟，不要只看“文件有没有生成”，而要看：

- 有没有明确真源
- 有没有程序化控制面
- 有没有独立验证层
- 有没有经验闭环

## 下一章

继续看 [Ch2: 三层目录模型](./02_three_roots.md)。

