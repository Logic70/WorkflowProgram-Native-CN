# Ch4: 编排主链 — 为什么要把编排逻辑沉到程序里

> 如果顺序只是写在提示词里，那它本质上还是建议，不是程序。

## 4.1 为什么不能只靠技能说明编排

技能说明擅长定义语义步骤，但不擅长做这些事：

- 确保脚本执行顺序固定
- 确保状态真的落盘
- 确保边界检查真的执行
- 确保失败时有一致的结构化结果

所以更稳的做法，是把编排拆成两层：

- 入口层
  - 负责把高层约定收成固定步骤顺序
- 控制层
  - 负责状态推进、边界检查和证据落盘

## 4.2 这两层在方案上各自负责什么

入口层负责回答：

- 这次应该先做哪一步，再做哪一步
- 哪些检查必须发生在写入之前
- 什么时候可以进入正式执行

控制层负责回答：

- 状态如何推进
- 哪些边界绝不能越过
- 最小证据有没有留下
- 失败时要落什么结构化结果

## 4.3 当前实现里的映射

在当前实现里，对应关系是：

- [workflow-entry.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/workflow-entry.py)
  - 入口层
  - 把脚本链串成固定顺序
- [workflow-runner.py](/mnt/d/Code/WorkflowProgram-CN/.claude/scripts/workflow-runner.py)
  - 控制层
  - 负责状态转移、边界校验、证据落盘和最小运行约束检查

当前入口链会固定调用：

1. `validate-workflow-spec.py`
2. `generate-workflow-view.py`
3. `generate-workflow-maintenance.py`
4. `generate-target-runtime.py`
5. `managed-assets.py plan/apply-staged`
6. `discover-host-capabilities.py`（按契约启用）
7. `probe-host-capabilities.py` / `apply-host-bootstrap.py`
8. `generate-environment-remediation.py`
9. `workflow-runner.py run`
10. `validate-run-state.py`

这意味着主入口已经不再依赖“模型记得下一步该做什么”。

其中有两个新边界值得记住：

- 入口层不只负责 `.claude/` 候选资产，还会把 `workflow-view.md`、`workflow-maintenance.md` 和目标侧 runtime 包一起准备好。
- 如果 workflow 依赖外部能力，入口层还要先完成“能力发现 -> 宿主探测 -> bootstrap -> 环境修复指引”，再进入 runner。

## 4.4 当前实现的价值

有了这两层，`workflowprogram-develop` 不再只是“一段很长的说明书”，而是一条确定性的产品入口链。

你可以把它记成：

- 入口层负责串步骤
- 控制层负责把运行管住
- 验证层负责最终判定

## 4.5 提炼模板

当你的 workflow 开始涉及：

- 多阶段切换
- 目标项目写入
- 运行证据
- 结构化验证

就应该考虑把“编排逻辑”从 prompt 里拆到确定性脚本里。

## 下一章

继续看 [Ch5: 受控写入](./05_managed_apply.md)。
