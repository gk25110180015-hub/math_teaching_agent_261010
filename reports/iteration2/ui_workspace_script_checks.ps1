[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
. (Join-Path $projectRoot 'scripts\Common-Windows.ps1')
$checks = @()
function Require-Check([bool]$Condition, [string]$Name) {
    if (-not $Condition) { throw "FAILED: $Name" }
    $script:checks += $Name
}
function Require-Throw([scriptblock]$Action, [string]$Name) {
    $threw = $false
    try { & $Action | Out-Null } catch { $threw = $true }
    Require-Check $threw $Name
}
foreach ($name in @('Common-Windows.ps1','Run-Local.ps1','Stop-Local.ps1')) {
    $parseTokens = $null; $parseErrors = $null
    $null = [Management.Automation.Language.Parser]::ParseFile((Join-Path $projectRoot ('scripts\' + $name)), [ref]$parseTokens, [ref]$parseErrors)
    Require-Check ($parseErrors.Count -eq 0) ('syntax-' + $name)
}
$defaultRoot = Get-AgentWorkspace -ProjectRoot $projectRoot
Require-Check ($defaultRoot -eq (Join-Path $projectRoot 'workspace')) 'default-workspace-unchanged'
$relativeRoot = 'workspace\t\ws-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
$testRoot = Get-AgentWorkspace -ProjectRoot $projectRoot -Workspace $relativeRoot
Require-Check ($testRoot -eq (Join-Path $projectRoot $relativeRoot)) 'relative-workspace-resolved-from-project'
Require-Check ((Get-AgentWorkspace -ProjectRoot $projectRoot -Workspace $testRoot) -eq $testRoot) 'absolute-contained-workspace-accepted'
Require-Throw { Get-AgentWorkspace -ProjectRoot $projectRoot -Workspace '..\outside' } 'parent-escape-rejected'
Require-Throw { Get-AgentWorkspace -ProjectRoot $projectRoot -Workspace 'workspace-other\fake' } 'prefix-lookalike-rejected'
Require-Throw { Get-AgentWorkspace -ProjectRoot $projectRoot -Workspace 'workspace\..\reports' } 'normalized-escape-rejected'
$legacy = [pscustomobject]@{ project_root = $projectRoot; processes = @() }
Assert-AgentProcessState -State $legacy -ProjectRoot $projectRoot -WorkspaceRoot $defaultRoot
Require-Check $true 'legacy-default-state-compatible'
Require-Throw { Assert-AgentProcessState -State $legacy -ProjectRoot $projectRoot -WorkspaceRoot $testRoot } 'legacy-nondefault-state-rejected'

# Only command shims are used: no server, worker, browser or taskkill is started.
$global:workspaceScriptStarts = @()
$global:workspaceScriptTime = Get-Date
$global:workspaceScriptPython = Get-AgentPython $projectRoot
function global:Start-Process {
    [CmdletBinding()]
    param($FilePath, $ArgumentList, $WorkingDirectory, $WindowStyle, [switch]$PassThru, $RedirectStandardOutput, $RedirectStandardError)
    $global:workspaceScriptStarts += [pscustomobject]@{
        workspace = $env:MATH_AGENT_WORKSPACE; working_directory = $WorkingDirectory
        stdout = $RedirectStandardOutput; stderr = $RedirectStandardError; window_style = $WindowStyle
    }
    return [pscustomobject]@{ Id = 2147483647; StartTime = $global:workspaceScriptTime }
}
function global:Get-Process {
    [CmdletBinding()]
    param([int]$Id)
    return [pscustomobject]@{ Path = $global:workspaceScriptPython; StartTime = $global:workspaceScriptTime }
}
function global:Invoke-RestMethod {
    [CmdletBinding()]
    param($Uri, $TimeoutSec)
    return @{ status = 'mock-health-only' }
}
$oldWorkspace = [Environment]::GetEnvironmentVariable('MATH_AGENT_WORKSPACE', 'Process')
try {
    [Environment]::SetEnvironmentVariable('MATH_AGENT_WORKSPACE', 'retained-workspace-marker', 'Process')
    $probe = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, 0)
    $probe.Start(); $testPort = $probe.LocalEndpoint.Port; $probe.Stop()
    & (Join-Path $projectRoot 'scripts\Run-Local.ps1') -Workspace $relativeRoot -Port $testPort
    Require-Check ($global:workspaceScriptStarts.Count -eq 2) 'two-start-commands-mocked'
    Require-Check ($env:MATH_AGENT_WORKSPACE -eq 'retained-workspace-marker') 'parent-process-workspace-restored'
    foreach ($start in $global:workspaceScriptStarts) {
        Require-Check ($start.workspace -eq $testRoot) 'child-workspace-explicit'
        Require-Check ($start.stdout.StartsWith($testRoot + '\logs\') -and $start.stderr.StartsWith($testRoot + '\logs\')) 'logs-use-selected-workspace'
        Require-Check ($start.window_style -eq 'Hidden') 'child-window-hidden'
    }
} finally {
    [Environment]::SetEnvironmentVariable('MATH_AGENT_WORKSPACE', $oldWorkspace, 'Process')
    Remove-Item -LiteralPath Function:\Start-Process,Function:\Get-Process,Function:\Invoke-RestMethod
}
$recordFile = Join-Path $testRoot 'runtime\local-processes.json'
$state = Get-Content -Raw -Encoding UTF8 -LiteralPath $recordFile | ConvertFrom-Json
Require-Check ($state.project_root -eq $projectRoot -and $state.workspace_root -eq $testRoot) 'pid-record-project-and-workspace'
$state.workspace_root = $defaultRoot
Write-AgentJson -Path $recordFile -Value $state
Require-Throw { & (Join-Path $projectRoot 'scripts\Stop-Local.ps1') -Workspace $relativeRoot } 'stop-mismatched-workspace-rejected'
Require-Check (Test-Path -LiteralPath $recordFile) 'mismatch-retains-process-record'
$state.workspace_root = $testRoot
$state.project_root = Split-Path -Parent $projectRoot
Write-AgentJson -Path $recordFile -Value $state
Require-Throw { & (Join-Path $projectRoot 'scripts\Stop-Local.ps1') -Workspace $relativeRoot } 'stop-mismatched-project-rejected'
$state.project_root = $projectRoot
Write-AgentJson -Path $recordFile -Value $state
# This impossible PID does not exist, so real Stop must skip it and never taskkill.
& (Join-Path $projectRoot 'scripts\Stop-Local.ps1') -Workspace $relativeRoot
Require-Check (-not (Test-Path -LiteralPath $recordFile)) 'stopped-record-archived'
Require-Check (@(Get-ChildItem -LiteralPath (Join-Path $testRoot 'runtime') -Filter 'stopped-*.json').Count -eq 1) 'archive-within-selected-workspace'
$report = @{ status = 'PASS'; checks = $checks; workspace = $testRoot; test_port = $testPort
    process_commands = 'MOCK'; application_started = $false; real_api = 'NOT_RUN'; teacher_visual = 'NOT_RUN'
    default_workspace_touched = $false; timestamp = (Get-Date).ToUniversalTime().ToString('o') }
Write-AgentJson -Path (Join-Path $PSScriptRoot 'ui_workspace_script_checks.json') -Value $report
$report | ConvertTo-Json -Depth 6
