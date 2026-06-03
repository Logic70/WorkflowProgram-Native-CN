在正式评审或交付前执行一次完整预检查。

与 `/ship` 不同，`/preflight` 会优先并行执行检查并汇总结果，
以更快判断当前变更是否达到“可进入下一步”的状态；它不会创建提交。

> Compatibility Note
>
> `/preflight` 保留为当前仓库的就绪性检查命令，不是 WorkflowProgram 在目标项目中的主产品入口。面向 `TARGET_ROOT` 的 workflow 级验证应优先使用 `workflowprogram-validate`。
> 普通 workflow 请求统一从 `/workflowprogram-cn:workflowprogram-orchestrate <需求>` 进入。

## Usage

```text
/preflight [<scope>]
```

默认目标：当前分支相对 `main` 的变更。

## Stage 1: 识别范围

**Goal**: 明确要检查的 diff 范围。

1. 将 `$ARGUMENTS` 解析为检查目标。
2. 若未指定范围，则运行 `git diff main...HEAD --stat` 查看受影响文件。
3. 若没有相关变更，则直接停止。

**Verify**: 目标范围能解析为非空 diff。

**On failure**：输出 `Nothing to check.` 并停止。

## Stage 2: 并行检查

**Goal**: 并行运行仓库就绪性检查。

在一条 Task 消息中同时启动以下检查：

- 安全检查
- 代码审查（逻辑 + 风格）
- 测试/校验验证
- 文档完整性检查

要求：

- 子代理提示词必须完整内联
- 总 fan-out 数量不超过 4
- 测试/校验阶段默认使用 `python3 .claude/scripts/quality-gate.py commit`
- 若范围触及 runtime、runner、finalizer、schema、生成器、publish/package 或测试 harness，则测试/校验阶段升级为 `python3 .claude/scripts/quality-gate.py integration`
- 只有插件版本发布前才使用 `python3 .claude/scripts/quality-gate.py release`

**Verify**: 每条检查链路都返回可被聚合的结果。

**On failure**：将并行执行问题记录到 `lessons.md` 并停止。

## Stage 3: 汇总结果

**Goal**: 生成统一的就绪性报告。

将所有结果汇总为：

```text
## Preflight Report

### Security: PASS / FAIL (N issues)
### Review: PASS / FAIL (N issues)
### Tests: PASS / FAIL
### Docs: PASS / FAIL (N missing items)
### Overall Verdict: READY / NOT READY
```

`READY` 的前提：

- 没有 critical 安全问题
- 校验成功

warning 和文档问题会报告，但不阻塞 READY 判定。

**Verify**: 报告覆盖所有检查链路，并给出最终结论。

**On failure**：解释是哪一部分结果缺失或格式不合法。

Target：`$ARGUMENTS`
