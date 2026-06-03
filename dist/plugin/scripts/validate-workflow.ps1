# AUTO-GENERATED FROM .claude/ - DO NOT EDIT DIRECTLY
﻿param(
    [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$passes = [System.Collections.Generic.List[string]]::new()
$errors = [System.Collections.Generic.List[string]]::new()

function Add-Pass {
    param([string]$Message)
    $passes.Add($Message)
}

function Add-Error {
    param([string]$Message)
    $errors.Add($Message)
}

function Parse-Frontmatter {
    param([string]$Path)

    $content = Get-Content -Raw -Path $Path
    if ($content -notmatch '(?s)^---\r?\n(.*?)\r?\n---') {
        throw "Missing YAML frontmatter: $Path"
    }

    $result = @{}
    foreach ($line in ($Matches[1] -split "\r?\n")) {
        if ($line -match '^\s*([^:#]+):\s*(.+?)\s*$') {
            $key = $Matches[1].Trim()
            $value = $Matches[2].Trim()
            $result[$key] = $value.Trim("'`"")
        }
    }
    return $result
}

$requiredPrimarySkills = @(
    'workflowprogram-orchestrate',
    'workflowprogram-develop',
    'workflowprogram-audit',
    'workflowprogram-iterate',
    'workflowprogram-validate'
)

$forbiddenLegacyPaths = @(
    'commands',
    'skills',
    'agents',
    'rules',
    'scripts',
    'tools\sync_plugin_assets.py'
)

$activeDesignDocs = @{
    "docs\workflowprogram-stage-highlevel-design.md" = @("runtime_contract", "test_contract", "generated_runtime_contract", "shared-control-plane-wrapper", "capability_discovery", "host-capability-candidates.json", "host-bootstrap-instructions.md", "host_capabilities", "agent_team_contract", "workflow-entry.py", "workflowprogram-validate", "runtime_smoke.py", "quality-gate.py", "validation-runtime-report.md", "s5-validation-summary.json")
    "docs\workflowprogram-stage-lowlevel-design.md" = @("runtime_contract", "test_contract", "generated_runtime_contract", "runtime_capabilities", "capability_discovery", "host_capabilities", "agent_team_contract", "discover-host-capabilities.py", "probe-host-capabilities.py", "apply-host-bootstrap.py", "control-plane helper", "workflow-entry.py", "runtime_contract.<field>", "implemented_now", "runner 只负责控制面", "workflowprogram-validate", "runtime_smoke.py", "quality-gate.py", "validation-runtime-report.md", "s5-validation-summary.json")
    "docs\workflowprogram-stage-consistency-check.md" = @("runtime_contract", "test_contract", "当前无显式冲突")
}

$activeEntryDocs = @{
    ".claude\commands\develop.md" = @("runtime_contract", "test_contract", "generated_runtime_contract", ".workflowprogram/runtime/", "generate-target-runtime.py", "discover-host-capabilities.py", "probe-host-capabilities.py", "apply-host-bootstrap.py", "control-plane helper", "workflow-entry.py", "runtime_contract.<field>", "workflowprogram-validate", "runtime_smoke.py", "s5-validation-summary.json")
    ".claude\skills\workflowprogram-develop\SKILL.md" = @("runtime_contract", "test_contract", "generated_runtime_contract", ".workflowprogram/runtime/", "generate-target-runtime.py", "discover-host-capabilities.py", "probe-host-capabilities.py", "apply-host-bootstrap.py", "control-plane helper", "workflow-entry.py", "implemented_now", "workflowprogram-validate", "runtime_smoke.py", "s5-validation-summary.json")
}

$forbiddenActiveDocSnippets = @{
    ".claude\commands\develop.md" = @("python3 `${CLAUDE_PLUGIN_ROOT}/scripts/stage-progress.py update ...")
    ".claude\skills\workflowprogram-develop\SKILL.md" = @("执行过程中必须通过 `${CLAUDE_PLUGIN_ROOT}/scripts/stage-progress.py` 写入进展与关键节点结果。")
    "docs\workflowprogram-stage-lowlevel-design.md" = @("python3 `${CLAUDE_PLUGIN_ROOT}/scripts/stage-progress.py update ...")
}

$activeTemplateDocs = @{
    ".claude\skills\workflow-spec-support\yaml-spec-template.md" = @("stage_slot: S5", "generated_runtime_contract", "runtime_capabilities", "capability_discovery", "host_capabilities", "agent_team_contract", "workflowprogram-validate", "validation-runtime-report.md", "test_contract")
}

$activePlanDocs = @{
    "docs\workflowprogram-test-change-plan.md" = @("P1", "workflowprogram-validate", "runtime_smoke.py", "workflowprogram-design-status.md", "capability matrix")
}

$activeStatusDocs = @{
    "docs\workflowprogram-design-status.md" = @("当前生效设计真源", "历史追溯文档", "已关闭决策", "workflow-entry.py", "shared-control-plane-wrapper", "capability_discovery")
}

$requiredPaths = @(
    "CLAUDE.md",
    "README.md",
    "lessons.md",
    "validation-report.md",
    ".claude\settings.json",
    ".claude\commands",
    ".claude\skills",
    ".claude\rules\constraints.md",
    ".claude\scripts\managed-assets.py",
    ".claude\scripts\route-intent.py",
    ".claude\scripts\runtime_host.py",
    ".claude\scripts\generate-target-runtime.py",
    ".claude\scripts\generate-workflow-view.py",
    ".claude\scripts\generate-workflow-maintenance.py",
    ".claude\scripts\generate-workflow-lowlevel.py",
    ".claude\scripts\build-native-iterate-evidence.py",
    ".claude\scripts\build-native-publish-evidence.py",
    ".claude\scripts\build-native-workflow-manifest.py",
    ".claude\scripts\validate-publish-qualification.py",
    ".claude\scripts\resolve-task-model-policy.py",
    ".claude\scripts\build-native-interactive-smoke.py",
    ".claude\scripts\probe-host-capabilities.py",
    ".claude\scripts\discover-host-capabilities.py",
    ".claude\scripts\apply-host-bootstrap.py",
    ".claude\scripts\lib\control_plane.py",
    ".claude\scripts\validate-generated-runtime.py",
    ".claude\scripts\stage-progress.py",
    ".claude\scripts\validate-workflow-maintenance.py",
    ".claude\scripts\validate-workflow-lowlevel.py",
    ".claude\scripts\validate-lessons-delta.py",
    ".claude\scripts\validate-run-state.py",
    ".claude\scripts\assess-native-legacy-retirement.py",
    ".claude\scripts\validate-workflow-draft.py",
    ".claude\scripts\validate-workflow-spec.py",
    ".claude\scripts\quality-gate.py",
    ".claude\scripts\validate-workflow.ps1",
    ".claude\scripts\validate-workflow.py",
    ".claude\scripts\workflow-entry.py",
    ".claude\scripts\workflow-runner.py",
    ".claude\scripts\workflow-s5-judge.py",
    ".claude-plugin\plugin.json",
    ".claude-plugin\marketplace.json",
    "tools\build_plugin.py",
    "tools\generate-view.py",
    "tools\mock_runtime_host.py",
    "tools\runtime_smoke.py",
    "tests\fixtures",
    "tests\spec-fixtures",
    "tests\expectations",
    "tests\transcripts",
    "docs\workflowprogram-stage-highlevel-design.md",
    "docs\workflowprogram-stage-lowlevel-design.md",
    "docs\workflowprogram-stage-consistency-check.md",
    "docs\workflowprogram-test-change-plan.md",
    "docs\workflowprogram-design-status.md",
    "docs\workflowprogram-capability-matrix.json",
    "docs\phase-07-implementation-plan.md",
    ".claude\skills\workflow-spec-support\yaml-spec-template.md"
)

foreach ($relativePath in $requiredPaths) {
    $fullPath = Join-Path $Root $relativePath
    if (Test-Path $fullPath) {
        Add-Pass "Found $relativePath"
    }
    else {
        Add-Error "Missing required path: $relativePath"
    }
}

foreach ($relativePath in $forbiddenLegacyPaths) {
    $fullPath = Join-Path $Root $relativePath
    if (Test-Path $fullPath) {
        Add-Error "Legacy compatibility path must not exist: $relativePath"
    }
    else {
        Add-Pass "Legacy compatibility path removed: $relativePath"
    }
}

foreach ($docPath in $activeDesignDocs.Keys) {
    $fullPath = Join-Path $Root $docPath
    if (-not (Test-Path $fullPath)) {
        Add-Error "Missing active design doc: $docPath"
        continue
    }

    Add-Pass "Active design doc present: $docPath"
    $content = Get-Content -Raw -Path $fullPath
    foreach ($marker in $activeDesignDocs[$docPath]) {
        if ($content -like "*$marker*") {
            Add-Pass "Active design doc '$docPath' includes '$marker'"
        }
        else {
            Add-Error "Active design doc '$docPath' is missing '$marker'"
        }
    }
}

foreach ($docPath in $activePlanDocs.Keys) {
    $fullPath = Join-Path $Root $docPath
    if (-not (Test-Path $fullPath)) {
        Add-Error "Missing active plan doc: $docPath"
        continue
    }

    Add-Pass "Active plan doc present: $docPath"
    $content = Get-Content -Raw -Path $fullPath
    foreach ($marker in $activePlanDocs[$docPath]) {
        if ($content -like "*$marker*") {
            Add-Pass "Active plan doc '$docPath' includes '$marker'"
        }
        else {
            Add-Error "Active plan doc '$docPath' is missing '$marker'"
        }
    }
}

foreach ($docPath in $activeStatusDocs.Keys) {
    $fullPath = Join-Path $Root $docPath
    if (-not (Test-Path $fullPath)) {
        Add-Error "Missing active status doc: $docPath"
        continue
    }

    Add-Pass "Active status doc present: $docPath"
    $content = Get-Content -Raw -Path $fullPath
    foreach ($marker in $activeStatusDocs[$docPath]) {
        if ($content -like "*$marker*") {
            Add-Pass "Active status doc '$docPath' includes '$marker'"
        }
        else {
            Add-Error "Active status doc '$docPath' is missing '$marker'"
        }
    }
}

foreach ($docPath in $activeEntryDocs.Keys) {
    $fullPath = Join-Path $Root $docPath
    if (-not (Test-Path $fullPath)) {
        Add-Error "Missing active entry doc: $docPath"
        continue
    }

    Add-Pass "Active entry doc present: $docPath"
    $content = Get-Content -Raw -Path $fullPath
    foreach ($marker in $activeEntryDocs[$docPath]) {
        if ($content -like "*$marker*") {
            Add-Pass "Active entry doc '$docPath' includes '$marker'"
        }
        else {
            Add-Error "Active entry doc '$docPath' is missing '$marker'"
        }
    }
}

foreach ($docPath in $activeTemplateDocs.Keys) {
    $fullPath = Join-Path $Root $docPath
    if (-not (Test-Path $fullPath)) {
        Add-Error "Missing active template doc: $docPath"
        continue
    }

    Add-Pass "Active template doc present: $docPath"
    $content = Get-Content -Raw -Path $fullPath
    foreach ($marker in $activeTemplateDocs[$docPath]) {
        if ($content -like "*$marker*") {
            Add-Pass "Active template doc '$docPath' includes '$marker'"
        }
        else {
            Add-Error "Active template doc '$docPath' is missing '$marker'"
        }
    }
}

foreach ($docPath in $forbiddenActiveDocSnippets.Keys) {
    $fullPath = Join-Path $Root $docPath
    if (-not (Test-Path $fullPath)) {
        Add-Error "Missing active doc for anti-regression check: $docPath"
        continue
    }

    $content = Get-Content -Raw -Path $fullPath
    foreach ($snippet in $forbiddenActiveDocSnippets[$docPath]) {
        if ($content -like "*$snippet*") {
            Add-Error "Active doc '$docPath' re-exposes fragile progress CLI assembly: '$snippet'"
        }
        else {
            Add-Pass "Active doc '$docPath' avoids fragile progress CLI snippet '$snippet'"
        }
    }
}

$settingsPath = Join-Path $Root ".claude\settings.json"
$settings = $null
try {
    $settings = Get-Content -Raw -Path $settingsPath | ConvertFrom-Json
    Add-Pass "Parsed .claude/settings.json"
}
catch {
    Add-Error "Invalid JSON in .claude/settings.json: $($_.Exception.Message)"
}

$commandFiles = Get-ChildItem -Path (Join-Path $Root ".claude\commands") -Filter *.md -File | Sort-Object Name
$registeredCommands = @{}

if ($settings -and $settings.commands) {
    foreach ($prop in $settings.commands.PSObject.Properties) {
        $registeredCommands[$prop.Name] = $prop.Value.file
        $commandPath = Join-Path $Root $prop.Value.file
        if (Test-Path $commandPath) {
            Add-Pass "Registered command '$($prop.Name)' points to an existing file"
        }
        else {
            Add-Error "Registered command '$($prop.Name)' points to a missing file: $($prop.Value.file)"
        }
    }
}

foreach ($file in $commandFiles) {
    $relative = ".claude/commands/$($file.Name)"
    $content = Get-Content -Raw -Path $file.FullName

    if ($content -match '(?m)^## Usage\s*$') {
        Add-Pass "Command '$($file.Name)' has a Usage section"
    }
    else {
        Add-Error "Command '$($file.Name)' is missing a Usage section"
    }

    if ($content -match '(?m)^## Stage \d+:') {
        Add-Pass "Command '$($file.Name)' uses staged structure"
    }
    else {
        Add-Error "Command '$($file.Name)' is missing numbered stages"
    }

    if (($content -match '\*\*Goal\*\*:') -and ($content -match '\*\*Verify\*\*:')) {
        Add-Pass "Command '$($file.Name)' defines Goal and Verify"
    }
    else {
        Add-Error "Command '$($file.Name)' is missing Goal or Verify"
    }

    if ($registeredCommands.Values -contains $relative) {
        Add-Pass "Command '$($file.Name)' is registered in settings.json"
    }
    else {
        Add-Error "Command '$($file.Name)' exists on disk but is not registered in settings.json"
    }
}

$skillDirs = Get-ChildItem -Path (Join-Path $Root ".claude\skills") -Directory | Sort-Object Name
$registeredSkills = @{}

if ($settings -and $settings.skills) {
    foreach ($prop in $settings.skills.PSObject.Properties) {
        $registeredSkills[$prop.Name] = $prop.Value.file
        $skillPath = Join-Path $Root $prop.Value.file
        if (Test-Path $skillPath) {
            Add-Pass "Registered skill '$($prop.Name)' points to an existing file"
        }
        else {
            Add-Error "Registered skill '$($prop.Name)' points to a missing file: $($prop.Value.file)"
        }
    }
}

foreach ($dir in $skillDirs) {
    $skillPath = Join-Path $dir.FullName "SKILL.md"
    if (-not (Test-Path $skillPath)) {
        Add-Error "Skill directory '$($dir.Name)' is missing SKILL.md"
        continue
    }

    try {
        $frontmatter = Parse-Frontmatter -Path $skillPath
        foreach ($requiredField in @("name", "description", "version")) {
            if ($frontmatter.ContainsKey($requiredField) -and $frontmatter[$requiredField]) {
                Add-Pass "Skill '$($dir.Name)' includes frontmatter field '$requiredField'"
            }
            else {
                Add-Error "Skill '$($dir.Name)' is missing frontmatter field '$requiredField'"
            }
        }

        $isInternal = $frontmatter.ContainsKey("internal") -and ($frontmatter["internal"].ToLower() -eq "true")
        $relativeSkill = ".claude/skills/$($dir.Name)/SKILL.md"
        if ($isInternal) {
            Add-Pass "Internal support skill '$($dir.Name)' is exempt from settings registration"
        }
        elseif ($registeredSkills.Values -contains $relativeSkill) {
            Add-Pass "Skill '$($dir.Name)' is registered in settings.json"
        }
        else {
            Add-Error "Skill '$($dir.Name)' exists on disk but is not registered in settings.json"
        }
    }
    catch {
        Add-Error $_.Exception.Message
    }
}

$requiredPrimarySkills | ForEach-Object {
    if ($settings -and $settings.skills -and $settings.skills.PSObject.Properties.Name -contains $_) {
        Add-Pass "Primary skill '$_' is registered in settings.json"
    }
    else {
        Add-Error "Missing required primary skill registration: $_"
    }
}

$constraintsPath = Join-Path $Root ".claude\rules\constraints.md"
if (Test-Path $constraintsPath) {
    $constraintsContent = Get-Content -Raw -Path $constraintsPath
    if (($constraintsContent -match 'ALWAYS') -and ($constraintsContent -match 'NEVER')) {
        Add-Pass "constraints.md includes BOTH ALWAYS and NEVER rules"
    }
    else {
        Add-Error "constraints.md must include BOTH ALWAYS and NEVER rules"
    }
}

$pluginMeta = $null
$pluginJsonPath = Join-Path $Root ".claude-plugin\plugin.json"
try {
    $pluginMeta = Get-Content -Raw -Path $pluginJsonPath | ConvertFrom-Json
    Add-Pass "Parsed .claude-plugin/plugin.json"
    foreach ($field in @("name", "version", "description")) {
        if ($pluginMeta.$field) {
            Add-Pass "plugin.json includes field '$field'"
        }
        else {
            Add-Error "plugin.json is missing field '$field'"
        }
    }
}
catch {
    Add-Error "Cannot parse .claude-plugin/plugin.json: $($_.Exception.Message)"
}

$marketplaceJsonPath = Join-Path $Root ".claude-plugin\marketplace.json"
try {
    $marketplaceMeta = Get-Content -Raw -Path $marketplaceJsonPath | ConvertFrom-Json
    Add-Pass "Parsed .claude-plugin/marketplace.json"
    if ($marketplaceMeta.plugins -and $marketplaceMeta.plugins.Count -gt 0) {
        Add-Pass "marketplace.json defines at least one plugin entry"
    }
    else {
        Add-Error "marketplace.json must define at least one plugin entry"
    }
}
catch {
    Add-Error "Cannot parse .claude-plugin/marketplace.json: $($_.Exception.Message)"
}

$distRoot = Join-Path $Root "dist\plugin"
if (Test-Path $distRoot) {
    foreach ($relativePath in @(
        "dist\plugin\.claude-plugin\plugin.json",
        "dist\plugin\.claude-plugin\marketplace.json",
        "dist\plugin\build-manifest.json",
        "dist\plugin\scripts\managed-assets.py",
        "dist\plugin\scripts\route-intent.py",
        "dist\plugin\scripts\runtime_host.py",
        "dist\plugin\scripts\generate-target-runtime.py",
        "dist\plugin\scripts\generate-workflow-view.py",
        "dist\plugin\scripts\generate-workflow-maintenance.py",
        "dist\plugin\scripts\generate-workflow-lowlevel.py",
        "dist\plugin\scripts\build-native-iterate-evidence.py",
        "dist\plugin\scripts\build-native-publish-evidence.py",
        "dist\plugin\scripts\build-native-workflow-manifest.py",
        "dist\plugin\scripts\validate-publish-qualification.py",
        "dist\plugin\scripts\resolve-task-model-policy.py",
        "dist\plugin\scripts\build-native-interactive-smoke.py",
        "dist\plugin\scripts\probe-host-capabilities.py",
        "dist\plugin\scripts\apply-host-bootstrap.py",
        "dist\plugin\scripts\stage-progress.py",
        "dist\plugin\scripts\quality-gate.py",
        "dist\plugin\scripts\validate-generated-runtime.py",
        "dist\plugin\scripts\validate-workflow-maintenance.py",
        "dist\plugin\scripts\validate-workflow-lowlevel.py",
        "dist\plugin\scripts\validate-lessons-delta.py",
        "dist\plugin\scripts\validate-run-state.py",
        "dist\plugin\scripts\validate-workflow-draft.py",
        "dist\plugin\scripts\validate-workflow-spec.py",
        "dist\plugin\scripts\workflow-entry.py",
        "dist\plugin\scripts\workflow-runner.py",
        "dist\plugin\scripts\workflow-s5-judge.py"
    )) {
        $fullPath = Join-Path $Root $relativePath
        if (Test-Path $fullPath) {
            Add-Pass "Build output contains $relativePath"
        }
        else {
            Add-Error "Build output is missing $relativePath"
        }
    }

    $buildManifestPath = Join-Path $distRoot "build-manifest.json"
    if (Test-Path $buildManifestPath) {
        try {
            $buildManifest = Get-Content -Raw -Path $buildManifestPath | ConvertFrom-Json
            Add-Pass "Parsed dist/plugin/build-manifest.json"
            foreach ($field in @("manifest_version", "generated_at", "plugin_name", "plugin_version", "files")) {
                if ($null -ne $buildManifest.$field) {
                    Add-Pass "build-manifest.json includes field '$field'"
                }
                else {
                    Add-Error "build-manifest.json is missing field '$field'"
                }
            }

            if ($pluginMeta) {
                if ($buildManifest.plugin_name -eq $pluginMeta.name) {
                    Add-Pass "build-manifest plugin_name matches source plugin.json"
                }
                else {
                    Add-Error "build-manifest plugin_name does not match source plugin.json"
                }

                if ($buildManifest.plugin_version -eq $pluginMeta.version) {
                    Add-Pass "build-manifest plugin_version matches source plugin.json"
                }
                else {
                    Add-Error "build-manifest plugin_version does not match source plugin.json"
                }
            }

            $hasManagedAssets = $false
            $hasRouteIntent = $false
            $hasRuntimeHost = $false
            $hasStageProgress = $false
            $hasQualityGate = $false
            $hasValidateRunState = $false
            $hasValidateWorkflowSpec = $false
            $hasWorkflowRunner = $false
            $hasWorkflowS5Judge = $false
            foreach ($fileEntry in @($buildManifest.files)) {
                if (-not $fileEntry.path) {
                    Add-Error "build-manifest contains an entry without path"
                    continue
                }
                if (-not $fileEntry.sha256 -or $fileEntry.sha256.Length -ne 64) {
                    Add-Error "build-manifest entry '$($fileEntry.path)' is missing a valid sha256"
                    continue
                }
                $builtFilePath = Join-Path $distRoot ($fileEntry.path -replace '/', '\')
                if (Test-Path $builtFilePath) {
                    Add-Pass "build-manifest file exists: $($fileEntry.path)"
                }
                else {
                    Add-Error "build-manifest references a missing file: $($fileEntry.path)"
                }
                if ($fileEntry.path -eq "scripts/managed-assets.py") {
                    $hasManagedAssets = $true
                }
                if ($fileEntry.path -eq "scripts/route-intent.py") {
                    $hasRouteIntent = $true
                }
                if ($fileEntry.path -eq "scripts/runtime_host.py") {
                    $hasRuntimeHost = $true
                }
                if ($fileEntry.path -eq "scripts/stage-progress.py") {
                    $hasStageProgress = $true
                }
                if ($fileEntry.path -eq "scripts/quality-gate.py") {
                    $hasQualityGate = $true
                }
                if ($fileEntry.path -eq "scripts/validate-run-state.py") {
                    $hasValidateRunState = $true
                }
                if ($fileEntry.path -eq "scripts/validate-workflow-spec.py") {
                    $hasValidateWorkflowSpec = $true
                }
                if ($fileEntry.path -eq "scripts/workflow-runner.py") {
                    $hasWorkflowRunner = $true
                }
                if ($fileEntry.path -eq "scripts/workflow-s5-judge.py") {
                    $hasWorkflowS5Judge = $true
                }
            }

            if ($hasManagedAssets) {
                Add-Pass "build-manifest tracks scripts/managed-assets.py"
            }
            else {
                Add-Error "build-manifest must include scripts/managed-assets.py"
            }

            if ($hasStageProgress) {
                Add-Pass "build-manifest tracks scripts/stage-progress.py"
            }
            else {
                Add-Error "build-manifest must include scripts/stage-progress.py"
            }

            if ($hasQualityGate) {
                Add-Pass "build-manifest tracks scripts/quality-gate.py"
            }
            else {
                Add-Error "build-manifest must include scripts/quality-gate.py"
            }

            if ($hasRouteIntent) {
                Add-Pass "build-manifest tracks scripts/route-intent.py"
            }
            else {
                Add-Error "build-manifest must include scripts/route-intent.py"
            }

            if ($hasRuntimeHost) {
                Add-Pass "build-manifest tracks scripts/runtime_host.py"
            }
            else {
                Add-Error "build-manifest must include scripts/runtime_host.py"
            }

            if ($hasValidateRunState) {
                Add-Pass "build-manifest tracks scripts/validate-run-state.py"
            }
            else {
                Add-Error "build-manifest must include scripts/validate-run-state.py"
            }

            if ($hasValidateWorkflowSpec) {
                Add-Pass "build-manifest tracks scripts/validate-workflow-spec.py"
            }
            else {
                Add-Error "build-manifest must include scripts/validate-workflow-spec.py"
            }

            if ($hasWorkflowRunner) {
                Add-Pass "build-manifest tracks scripts/workflow-runner.py"
            }
            else {
                Add-Error "build-manifest must include scripts/workflow-runner.py"
            }

            if ($hasWorkflowS5Judge) {
                Add-Pass "build-manifest tracks scripts/workflow-s5-judge.py"
            }
            else {
                Add-Error "build-manifest must include scripts/workflow-s5-judge.py"
            }
        }
        catch {
            Add-Error "Cannot parse dist/plugin/build-manifest.json: $($_.Exception.Message)"
        }
    }
}
else {
    Add-Pass "dist/plugin not present; build output validation skipped"
}

Write-Host "Workflow validation summary"
Write-Host "PASS: $($passes.Count)"
foreach ($item in $passes) {
    Write-Host "  [PASS] $item"
}

Write-Host "FAIL: $($errors.Count)"
foreach ($item in $errors) {
    Write-Host "  [FAIL] $item"
}

if ($errors.Count -gt 0) {
    exit 1
}

exit 0
