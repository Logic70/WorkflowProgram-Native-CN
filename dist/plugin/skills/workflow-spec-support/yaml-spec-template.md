<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->

# Workflow Specification Template
# Code Agent 编排专用格式

meta:
  name: example-workflow
  version: "1.0.0"
  target_platform: claude_code
  source_design: outputs/stages/target-design-overview.md
  complexity: M  # S/M/L/XL - 用于 Stage 5 Turn Count 配置

# 目标工作流设计源引用：RUN_ROOT refs 用于本轮 S5，persistent refs 用于完成后的目标工作流自描述。
# 完整设计推理不要塞进 YAML；YAML 只作为 target runtime map / projection index。
design_refs:
  schema_version: 2
  naming: target_design_v1
  requirements: outputs/stages/target-requirements.yaml
  question_backlog: outputs/stages/target-question-backlog.json
  requirement_logic_map: outputs/stages/target-requirement-logic-map.json
  context_findings: outputs/stages/target-context-findings.yaml
  design_overview: outputs/stages/target-design-overview.md
  design_detail: outputs/stages/target-design-detail.md
  implementation_plan: outputs/stages/target-implementation-plan.md
  acceptance_tests: outputs/stages/target-acceptance-tests.yaml
  traceability_matrix: outputs/stages/target-traceability-matrix.json
  # 复杂、loop、工具重、逆向/安全或多下游节点才需要 node_designs；文件内容应符合 target-node-design-template.md。
  # node_designs:
  #   build_dfd: outputs/stages/target-node-designs/build_dfd.md
  node_design_policy:
    required_for_complex_nodes: true
    exemption_field: node_design_exemption
  persistent:
    requirements: .workflowprogram/design/source/target-requirements.yaml
    question_backlog: .workflowprogram/design/source/target-question-backlog.json
    requirement_logic_map: .workflowprogram/design/source/target-requirement-logic-map.json
    context_findings: .workflowprogram/design/source/target-context-findings.yaml
    design_overview: .workflowprogram/design/source/target-design-overview.md
    design_detail: .workflowprogram/design/source/target-design-detail.md
    implementation_plan: .workflowprogram/design/source/target-implementation-plan.md
    acceptance_tests: .workflowprogram/design/source/target-acceptance-tests.yaml
    traceability_matrix: .workflowprogram/design/source/target-traceability-matrix.json
    # node_designs:
    #   build_dfd: .workflowprogram/design/source/target-node-designs/build_dfd.md

# 阶段定义
stages:
  - id: requirement
    stage_slot: S1
    name: 需求澄清
    pattern: Explore
    agent_ref: requirement_analyst
    input: $ARGUMENTS
    output: |
      workflow-spec.md
      outputs/stages/target-requirements.yaml
      outputs/stages/target-question-backlog.json
      outputs/stages/target-requirement-logic-map.json
    gate: user_approval
    max_retries: 3
    on_approve: context
    on_reject: abort

  - id: context
    stage_slot: S2
    name: 领域研究
    pattern: Explore
    agent_ref: requirement_analyst
    input: |
      workflow-spec.md
      outputs/stages/target-requirements.yaml
      outputs/stages/target-question-backlog.json
      outputs/stages/target-requirement-logic-map.json
    output: |
      outputs/stages/s2-context-report.md
      outputs/stages/target-context-findings.yaml
    max_retries: 3

  - id: design
    stage_slot: S3
    name: 工作流设计
    pattern: Specialized
    agent_ref: workflow_designer
    input: |
      outputs/stages/target-requirements.yaml
      outputs/stages/target-question-backlog.json
      outputs/stages/target-requirement-logic-map.json
      outputs/stages/s2-context-report.md
      outputs/stages/target-context-findings.yaml
    output: |
      outputs/stages/target-design-overview.md
      outputs/stages/target-design-detail.md
      outputs/stages/target-implementation-plan.md
      outputs/stages/target-acceptance-tests.yaml
      outputs/stages/target-traceability-matrix.json
      workflow-spec.yaml
      workflow-view.md
      workflow-maintenance.md
    gate: user_approval
    auto_approve_cond: "--auto-approve or CI=true"
    max_retries: 3
    on_approve: generate
    on_reject: requirement

  - id: generate
    stage_slot: S4
    name: 文件生成
    pattern: Sequential
    steps:
      - action: generate_agents
        from_yaml: agents
      - action: generate_skills
        from_yaml: skills
      - action: generate_commands
        from_yaml: commands
      - action: update_settings
        from_yaml: registry
    output: |
      outputs/candidate/.claude
      outputs/candidate/.workflowprogram/design
      outputs/candidate/.workflowprogram/runtime
      outputs/managed-change-plan.json
      outputs/managed-change-result.json
      .claude/agents/*.md
      .claude/skills/*/SKILL.md
      .claude/commands/*.md
      .claude/settings.json
      .workflowprogram/design/workflow-spec.yaml
      .workflowprogram/design/workflow-view.md
      .workflowprogram/design/workflow-maintenance.md
      .workflowprogram/design/source/**
      .workflowprogram/runtime/workflow-entry.py
      .workflowprogram/runtime/workflow-runner.py
      .workflowprogram/runtime/validate-run-state.py
      .workflowprogram/runtime/runtime-manifest.json

  - id: validate
    stage_slot: S5
    name: 运行时验证
    pattern: Test-Driven
    agent_ref: workflowprogram-validate
    input: outputs/managed-change-result.json
    resources:
      max_turn_count: 100  # M 复杂度默认 100 turns
      circuit_breaker:
        trigger: PostToolUseFailure
        threshold: 3
    max_retries: 3
    output: |
      validation-runtime-report.md
      outputs/stages/s5-validation-summary.json
    feedback:
      on_fail_design: design  # 设计缺陷 → 回到 Stage 3
      on_fail_impl: generate  # 实现缺陷 → 回到 Stage 4

  - id: lessons
    stage_slot: S6
    name: 约束演进
    pattern: Sequential
    actions:
      - extract_lessons
      - update_constraints
    output: |
      outputs/stages/s6-lessons-delta.md
      .claude/rules/constraints.md

# 意图到阶段流映射（逻辑阶段真源）
intent_flows:
  develop:
    required_stage_slots:
      - S1
      - S2
      - S3
      - S4
      - S5
      - S6
    optional_stage_slots: []
  audit:
    required_stage_slots:
      - S5
      - S6
    optional_stage_slots: []
  iterate:
    required_stage_slots:
      - S6
    optional_stage_slots:
      - S5
  validate:
    required_stage_slots:
      - S5
    optional_stage_slots:
      - S6

# 目标工作流图：描述“生成出来的目标工作流”自己的节点与转移。
# 注意：上面的 stages/intent_flows 属于 WorkflowProgram 自身 S0-S6 控制面；
# workflow_graph 不要求套用 S1-S6，可按用户需求使用任意业务节点 id。
workflow_graph:
  schema_version: 1
  templates_used:
    - clarify-design-generate-validate
  entrypoints:
    - name: example
      node: collect_input
  nodes:
    - id: collect_input
      role: intake
      template: clarify-design-generate-validate
      input_refs:
        - "$ARGUMENTS"
      output_refs:
        - outputs/target-workflow/intake-summary.md
      gate: none
      owner: example-skill
    - id: produce_result
      role: implementation
      template: clarify-design-generate-validate
      input_refs:
        - outputs/target-workflow/intake-summary.md
      output_refs:
        - outputs/target-workflow/result.md
      gate: user_approval
      owner: example-skill
      # Ralph-style loop 只用于目标工作流业务节点，不替换 WorkflowProgram 自身 S1-S6。
      # 适合逆向分析、迁移修复、报告收敛、TDD 实现等 verifier/test 可判定任务。
      # loop_policy:
      #   enabled: true
      #   mode: ralph
      #   goal_source: model_subgoal # user | model_subgoal
      #   parent_goal_ref: user_goal.example
      #   max_iterations: 5
      #   fresh_context_each_iteration: true
      #   prompt_package: .workflowprogram/loops/produce_result/prompt-package.md
      #   tdd_policy:
      #     enabled: true
      #     test_first_required: true
      #     red_green_refactor: true
      #   feedback_commands:
      #     - id: validate_result
      #       kind: test # validator | verifier | test
      #       argv: [python3, -m, pytest, tests/workflow]
      #       timeout_seconds: 120
      #       failure_effect: feedback # feedback | gate | hard_fail
      #   stop_conditions:
      #     success: [verifier_passed]
      #     max_iterations: fail
      #     no_progress_iterations: 2
      #   evidence_outputs:
      #     - outputs/stages/loops/produce_result/loop-plan.json
      #     - outputs/stages/loops/produce_result/iteration-summary.jsonl
      #     - outputs/stages/loops/produce_result/final-verdict.json
  transitions:
    - from: collect_input
      to: produce_result
      condition: input_ready
    - from: produce_result
      to: done

# Agent 引用列表（指向 .claude/agents/*.md）
agent_refs:
  - requirement_analyst
  - workflow_designer
  - workflow_verifier
  - workflowprogram-validate
  - security-reviewer
  - performance-reviewer
  - style-reviewer
  - logic-reviewer

# 技能引用列表
skills:
  - name: validate-file
    internal: true
  - name: validate-settings
    internal: true

# 命令注册表
registry:
  commands:
    - name: example
      file: .claude/commands/example.md
  skills:
    - name: example-skill
      file: .claude/skills/example/SKILL.md
  agents:
    - name: example-agent
      file: .claude/agents/example-agent.md
  hooks:
    - name: example-hook
      file: .claude/hooks/example-hook.json
  runtime_assets:
    - name: workflow-entry
      file: .workflowprogram/runtime/workflow-entry.py

# 约束规则（将写入 constraints.md）
constraints:
  always:
    - "为用户可见命令保留 ## Usage 段"
    - "将命令组织为编号阶段，提供 Goal 与 Verify"
    - "子代理提示词内联，不依赖外部文件"
  never:
    - "在单个 fan-out 阶段中超过 4 个并行代理"
    - "让子代理运行时依赖外部 agent 文件"
    - "在未经验证的情况下声明工作流创建完成"

# 资源限额配置
resource_limits:
  max_parallel_agents: 4
  max_retries_per_stage: 3
  max_validation_loops: 10

# 运行契约（支撑完整运行测试）
runtime_contract:
  # runner 只负责控制面与证据边界，不承担 S5 主判定
  # 允许写入路径边界（相对各 root）
  write_boundaries:
    target_root_allow:
      - "CLAUDE.md"
      - ".claude/**"
      - ".workflowprogram/**"
    run_root_allow:
      - "context.json"
      - "state.json"
      - "events.jsonl"
      - "transcript.md"
      - "validation-runtime-report.md"
      - "workflow-spec.yaml"
      - "workflow-*.md"
      - "workflow-view.md"
      - "outputs/**"
    temp_root_allow:
      - "**"
    deny:
      - "**/.git/**"
      - "**/node_modules/**"

  # 最小运行证据集（必须保留）
  required_evidence:
    - "context.json"
    - "state.json"
    - "events.jsonl"
    - "outputs/progress/current-progress.json"
    - "outputs/progress/milestones.jsonl"
    - "outputs/progress/user-progress.md"
    - "outputs/stages/s0-route.json"
    - "outputs/stages/runner-summary.json"

  # 失败类别枚举（运行态必须从这里取值）
  failure_kinds:
    - none
    - design
    - implementation
    - environment
    - conflict

  # 环境 skip 条件（命中后输出 ENVIRONMENT-SKIP）
  environment_skip:
    - code: RUNTIME_HOST_MISSING
      check: runtime_host_available
      message: "运行宿主不可用，跳过运行态验证"
    - code: TARGET_NOT_WRITABLE
      check: target_root_writable
      message: "TARGET_ROOT 无写权限，跳过运行态验证"
    - code: RUNTIME_HOST_NOT_READY
      check: runtime_host_ready
      message: "运行宿主未就绪，跳过运行态验证"

generated_runtime_contract:
  runtime_root: .workflowprogram/runtime
  design_spec_path: .workflowprogram/design/workflow-spec.yaml
  entry_script: .workflowprogram/runtime/workflow-entry.py
  runner_script: .workflowprogram/runtime/workflow-runner.py
  state_validator_script: .workflowprogram/runtime/validate-run-state.py
  runtime_manifest: .workflowprogram/runtime/runtime-manifest.json
  run_root_dir: .workflowprogram/runs
  mode: shared-control-plane-wrapper
  runtime_capabilities:
    - state_transitions
    - run_state_validation
    - target_managed_runtime
    - target_atomic_publish
    # - capability_discovery
    # - host_capability_probe
    # - team_orchestration
    # - node_loop_execution

target_runtime_policy:
  mode: managed_runtime
  entry_mode: wrapper_only
  graph_source: workflow_graph
  lifecycle_events_required: true
  owner_resolution_failure: terminal
  output_contract_failure: retry_then_terminal
  max_retries_per_node: 3
  artifact_provenance_required: true
  immutable_during_run:
    - .claude/**
    - .workflowprogram/design/**
    - .workflowprogram/runtime/**
    - config/scripts/**

target_executor_policy:
  # 不假设本机存在可用的 claude -p。ClaudeCode 当前会话/第三方模型场景默认走 current_agent 证据模式。
  default_provider: current_agent
  allowed_providers:
    - fixture_host
    - command_adapter
    - current_agent
    - manual
  evidence_dir: outputs/stages/executor-evidence
  unsupported_provider_verdict: FAIL

target_publish_policy:
  enabled: true
  run_scoped_outputs_required: true
  publish_root: outputs/target-workflow
  latest_marker: outputs/target-workflow/.workflowprogram-latest.json
  manifest_path: outputs/target-workflow/run-manifest.json
  atomic: true
  required_run_artifacts:
    - target-state.json
    - node-results.json
    - artifact-provenance.json
  required_reports:
    - path: outputs/stages/target-runtime-summary.json
      status_field: status
      pass_values:
        - PASS
        - BLOCKED
  publish_artifacts: []
  # Final manifest/latest marker are owned by target-runtime-finalizer.py.
  # Do not list manifest_path or latest_marker in required_reports.
  # Do not reference manifest_path/latest_marker from workflow_graph node refs.
  # validate-target-publish-state.py rejects hand-written COMPLETE manifests,
  # stale latest markers, and target-state/report/provenance mismatches.

target_claude_guard:
  # 这是目标项目 CLAUDE.md 的提示层防绕过约束；可信边界仍由 runner/finalizer/validator/doctor 保证。
  enabled: true
  file: CLAUDE.md
  mode: managed_block
  block_id: workflowprogram-runtime-guard
  required_for:
    - managed_runtime
    - target_publish_policy
  merge_policy:
    if_missing_file: create
    if_existing_no_block: append_after_title
    if_existing_block: replace_managed_block
    if_broken_block: conflict
  content:
    runtime_entry: .workflowprogram/runtime/workflow-entry.py
    allowed_actions:
      - run
      - status
      - resume
      - diagnose
    blocked_behavior: current_node_evidence_only
    failed_behavior: diagnose_only
    trusted_publisher: target-runtime-finalizer.py
    forbidden_operations:
      - handwrite_final_report
      - write_final_manifest
      - write_latest_marker
      - copy_run_outputs_to_final
      - continue_after_runtime_fail

# 可选能力搜索与推荐契约
# capability_discovery:
#   enabled: true
#   domains:
#     - reverse_engineering
#   include_local_installed: true
#   include_curated_profiles: true
#   infer_from_request: true
#   # 可选：对领域 profile 做显式裁剪或替换；用户显式选择优先于 profile 默认值
#   profile_overrides:
#     exclude_capability_ids:
#       - radare2_cli
#     replace_capabilities:
#       - replaces: ghidra_cli
#         id: binary_ninja_cli
#         kind: external_binary
#         name: Binary Ninja CLI
#         probe:
#           binary: binaryninja
#         summary: Prefer Binary Ninja over Ghidra CLI
#         manual_steps:
#           - Ensure Binary Ninja CLI is installed and available in PATH
#     disable_team_default: false

# 可选宿主能力契约
# host_capabilities:
#   - id: ghidra_mcp
#     kind: mcp_server
#     name: Ghidra MCP
#     required: true
#     probe:
#       server_name: ghidra
#     bootstrap:
#       scope: host_global
#       summary: Install and configure Ghidra MCP
#       project_local_outputs: []
#       # 若 scope=host_global，WorkflowProgram 只生成 plan；不会自动执行宿主全局变更
#       # adapter:
#       #   type: symlink_binary   # symlink_binary | uv_tool | pipx_install | npm_global
#       #   source_binary: workflowprogram-python
#       #   target_path: /tmp/workflowprogram-host-global/bin/ghidra-wrapper
#       # 若 scope=project_local，可选声明声明式 bootstrap 资产
#       # assets:
#       #   - path: .workflowprogram/bootstrap/bin/ghidra-wrapper.sh
#       #     format: shell
#       #     executable: true
#       #     content: |
#       #       #!/usr/bin/env bash
#       #       exec ghidraRun "$@"
#     approval_required: true

# 可选 agent team 契约
# agent_team_contract:
#   enabled: true
#   max_fan_out: 2
#   join_policy: all_must_pass
#   roles:
#     - id: reviewer
#       responsibility: review generated assets
#       ownership_stage_slots: [S5]
#       output_patterns:
#         - outputs/stages/team/S5/reviewer/review-report.md
#       required: true
#   execution:
#     - stage_slot: S5
#       role_ids:
#         - reviewer
#       join_role: reviewer

# 测试契约（支撑基础运行测试判定；引用 runtime_contract，不复制执行约束）
test_contract:
  # 主消费方：workflowprogram-validate；runtime_smoke.py 仅作为动态 harness
  entry:
    main_entry: example
    entry_type: slash_command
    required_args:
      - "$ARGUMENTS"
    missing_arg_verdict: FAIL
    invalid_entry_verdict: FAIL

  boundary:
    write_boundaries_ref: runtime_contract.write_boundaries
    managed_overwrite_policy: reject-unmanaged-overwrite
    conflict_expectation: keep-candidate-and-report
    external_write_policy: deny

  flow:
    required_stages:
      - requirement
      - context
      - design
      - generate
      - validate
      - lessons
    skippable_stages: []
    failure_recovery:
      design: design
      implementation: generate
    terminal_conditions:
      PASS: done
      WARN: blocked
      FAIL: failed
      ENVIRONMENT-SKIP: done

  artifacts:
    deliverables:
      - .claude/settings.json
      - .claude/rules/constraints.md
      - .workflowprogram/design/workflow-spec.yaml
      - .workflowprogram/design/workflow-view.md
      - .workflowprogram/design/workflow-maintenance.md
      - .workflowprogram/design/source/**
      - .workflowprogram/runtime/workflow-entry.py
      - .workflowprogram/runtime/workflow-runner.py
      - .workflowprogram/runtime/validate-run-state.py
      - .workflowprogram/runtime/runtime-manifest.json
      - .workflowprogram/managed-files.json
    evidence_ref: runtime_contract.required_evidence
    optional_outputs:
      - .claude/commands/*.md

  failure:
    failure_kinds_ref: runtime_contract.failure_kinds
    environment_skip_ref: runtime_contract.environment_skip
    # 仅用于测试期望；不得反向改变 runner verdict / failure_kind 语义
    implemented_now:
      - none
      - environment
