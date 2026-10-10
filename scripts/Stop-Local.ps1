[CmdletBinding()]
param([string]$Workspace = '')
. (Join-Path $PSScriptRoot 'Common-Windows.ps1')
Assert-SupportedPowerShell
$projectRoot = Get-AgentRoot
$workspaceRoot = Get-AgentWorkspace -ProjectRoot $projectRoot -Workspace $Workspace
$pidFile = Get-AgentWorkspace -ProjectRoot $projectRoot -Workspace (Join-Path $workspaceRoot 'runtime\local-processes.json')
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Host 'No process record exists for this workspace.'; return }
$savedState = Get-Content -Raw -Encoding UTF8 -LiteralPath $pidFile | ConvertFrom-Json
Assert-AgentProcessState -State $savedState -ProjectRoot $projectRoot -WorkspaceRoot $workspaceRoot
$taskkillPath = Join-Path $env:SystemRoot 'System32\taskkill.exe'
foreach ($record in $savedState.processes) {
    if (Test-AgentProcess $record) {
        & $taskkillPath /PID ([string]$record.pid) /T /F
        if ($LASTEXITCODE -ne 0) { throw "Could not stop project process $($record.pid); process record retained." }
    } else { Write-Host "Skipping exited or identity-mismatched PID $($record.pid)." }
}
$archivePath = Get-AgentWorkspace -ProjectRoot $projectRoot -Workspace (Join-Path (Split-Path -Parent $pidFile) ('stopped-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json'))
Move-Item -LiteralPath $pidFile -Destination $archivePath
Write-Host 'Workspace server and worker stopped. Database, checkpoints, artifacts and logs are preserved.'
