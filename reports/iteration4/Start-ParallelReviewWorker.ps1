[CmdletBinding()]
param([string]$Workspace = 'workspace\iteration2-live')
. (Join-Path $PSScriptRoot '..\..\scripts\Common-Windows.ps1')
Assert-SupportedPowerShell
Import-AgentUserEnvironment
$projectRoot = Get-AgentRoot
$workspaceRoot = Get-AgentWorkspace -ProjectRoot $projectRoot -Workspace $Workspace
$pythonExe = Get-AgentPython $projectRoot
$pidFile = Join-Path $workspaceRoot 'runtime\local-processes.json'
$state = Get-Content -LiteralPath $pidFile -Raw -Encoding UTF8 | ConvertFrom-Json
Assert-AgentProcessState -State $state -ProjectRoot $projectRoot -WorkspaceRoot $workspaceRoot
if (-not @($state.processes | Where-Object { $_.role -eq 'server' -and (Test-AgentProcess $_) }).Count) {
    throw 'Start the managed local application before adding a one-shot worker.'
}
if (@($state.processes | Where-Object { $_.role -eq 'worker-once' -and (Test-AgentProcess $_) }).Count) {
    throw 'A managed one-shot worker is already active.'
}
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 6)
$backup = Join-Path $PSScriptRoot ('before-parallel-worker-' + $stamp + '.json')
Copy-Item -LiteralPath $pidFile -Destination $backup
$saved = @{}
$values = @{
    MATH_AGENT_WORKSPACE = $workspaceRoot
    MATH_AGENT_LLM_CONNECT_TIMEOUT_SECONDS = '30'
    MATH_AGENT_LLM_READ_TIMEOUT_SECONDS = '600'
    MATH_AGENT_LLM_TOTAL_TIMEOUT_SECONDS = '600'
}
try {
    foreach ($name in $values.Keys) {
        $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $values[$name], 'Process')
    }
    $logRoot = Join-Path $workspaceRoot 'logs'
    $stdout = Join-Path $logRoot ($stamp + '-worker-once.stdout.log')
    $stderr = Join-Path $logRoot ($stamp + '-worker-once.stderr.log')
    $argumentLine = (@('-m', 'math_agent.cli', 'worker', '--once') | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' '
    $process = Start-Process -FilePath $pythonExe -ArgumentList $argumentLine -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $record = @{ pid = $process.Id; executable = $pythonExe; start_time_utc_ticks = $process.StartTime.ToUniversalTime().Ticks; role = 'worker-once'; stdout = $stdout; stderr = $stderr }
    $state.processes = @($state.processes) + @($record)
    Write-AgentJson -Path $pidFile -Value $state
    Write-Host ('Registered one-shot worker PID ' + $process.Id)
    Write-Host ('Process state: ' + $pidFile)
} finally {
    foreach ($name in $saved.Keys) {
        [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process')
    }
}
