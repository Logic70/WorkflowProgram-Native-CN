<!-- AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY -->

# WorkflowProgram High-Level Design Review Checklist

Apply this after the general `$highlevel-design` checklist.

## Domain Review

- Are product entrypoints and intent-routing decisions explicit?
- Does each Stage define input, output, gate, failure condition, and evidence?
- Are authoring-time and runtime assets separated?
- Is the authoritative target-workflow artifact explicit?
- Are agent prompts correctly classified as inline or reusable?
- Are skills treated as reusable capabilities rather than forced entrypoints?
- Are installation and publication boundaries explicit when applicable?

## Native Workflow JS Review

- Is every retained custom-runtime capability justified by a verified need?
- Are L1 structural, L2 orchestration, and L3 domain validation separated?
- Is the smoke-test contract retained?
- Are interactive and non-interactive support boundaries explicit?
- Are resume and cache retained only when the target scenario requires them?
