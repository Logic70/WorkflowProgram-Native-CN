# Sample Migration Capability Disposition

| Legacy capability | Native sample disposition | Evidence |
|---|---|---|
| Python runtime runner | Replaced by explicit JS phase order | `phase('Intake') -> phase('Review') -> phase('Decide')` |
| Workflow graph fan-out | Replaced by `pipeline()` and nested `parallel()` | `workflowprogram-native-sample-migration.js` |
| Structured result validation | Kept as Agent schema | each review Agent schema |
| Stage gate | Replaced by JS condition | `blocked.length > 0` |
| Shared Agent files | Removed | review Agents are workflow-local and inline |
| `workflow-spec.yaml` | Removed by default | `authoring-spec.json` has no supporting assets |
| `.workflowprogram/runtime/` | Removed | target tree contains only `.claude/workflows/*.js` |
| Managed apply | Kept in authoring phase | generated through `generate-native-workflow.py --apply` when needed |
| External fact validator | Not required for this read-only sample | add `.claude/scripts/*` only for workflows that need one |
| Resume/cache and finalizer | Not required for this read-only sample | high-risk side-effect workflows still need dedicated smoke |
