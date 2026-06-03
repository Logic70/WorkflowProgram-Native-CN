# Ch2: 三层目录模型 — 为什么一定要区分 PLUGIN_ROOT、TARGET_ROOT、RUN_ROOT

> 一旦输入、输出、证据混在一起，workflow 就很难治理。

## 2.1 三个 root 分别是什么

`WorkflowProgram` 当前实现把目录分成三层：

- `PLUGIN_ROOT`
  - 插件载荷和参考资产
- `TARGET_ROOT`
  - 最终交付给用户项目的目录
- `RUN_ROOT`
  - 单次运行的证据和中间产物目录

这是整个系统的基础边界。

## 2.2 为什么要这样分

如果不分层，最常见的问题有两个：

1. 插件资产和目标资产混在一起，无法判断谁是输入谁是输出
2. 运行证据直接落在目标交付目录里，后续既难追溯也难清理

所以 `WorkflowProgram` 把“运行时发生了什么”明确放进 `RUN_ROOT`。

## 2.3 当前实现中的具体形态

关键目录关系在 [README.md](/mnt/d/Code/WorkflowProgram-CN/README.md) 和 [phase-03-step-02-runtime-evidence-spec.md](/mnt/d/Code/WorkflowProgram-CN/docs/phase-03-step-02-runtime-evidence-spec.md) 里写得很清楚：

```text
TARGET_ROOT/
├── .claude/                        # 最终交付
└── .workflowprogram/
    ├── managed-files.json
    └── runs/<run-id>/              # RUN_ROOT
```

`RUN_ROOT` 最小证据至少包括：

- `context.json`
- `state.json`
- `events.jsonl`
- `transcript.md`
- `validation-runtime-report.md`

## 2.4 这对使用者意味着什么

如果你要理解一次运行到底发生了什么，优先看 `RUN_ROOT`，不是先看 `.claude/` 最终产物。

因为：

- `.claude/` 只能告诉你“最后留下了什么”
- `RUN_ROOT` 才能告诉你“为什么留下这些东西”

## 2.5 提炼模板

以后设计自己的 workflow 时，先把 3 个问题写清楚：

1. 参考资产从哪读
2. 最终交付往哪写
3. 运行证据留在哪

不先回答这 3 个问题，后面所有边界设计都会模糊。

## 下一章

继续看 [Ch3: 阶段模型](./03_stage_model.md)。

