[CmdletBinding()]
param([ValidateRange(1024, 65535)][int]$Port = 8765, [switch]$OpenBrowser, [string]$Workspace = '')
. (Join-Path $PSScriptRoot 'Common-Windows.ps1')
Assert-SupportedPowerShell
Import-AgentUserEnvironment
$projectRoot = Get-AgentRoot
$pythonExe = Get-AgentPython $projectRoot
$workspaceRoot = Get-AgentWorkspace -ProjectRoot $projectRoot -Workspace $Workspace
$runtimeRoot = Get-AgentWorkspace -ProjectRoot $projectRoot -Workspace (Join-Path $workspaceRoot 'runtime')
$logRoot = Get-AgentWorkspace -ProjectRoot $projectRoot -Workspace (Join-Path $workspaceRoot 'logs')
New-Item -ItemType Directory -Force -Path $runtimeRoot, $logRoot | Out-Null
$pidFile = Get-AgentWorkspace -ProjectRoot $projectRoot -Workspace (Join-Path $runtimeRoot 'local-processes.json')
if (Test-Path -LiteralPath $pidFile) {
    $oldState = Get-Content -Raw -Encoding UTF8 -LiteralPath $pidFile | ConvertFrom-Json
    Assert-AgentProcessState -State $oldState -ProjectRoot $projectRoot -WorkspaceRoot $workspaceRoot
    $liveProcesses = @($oldState.processes | Where-Object { Test-AgentProcess $_ })
    if ($liveProcesses.Count -gt 0) { throw 'This workspace still has a running server or worker. Run Stop-Local.ps1 with the same -Workspace before restarting.' }
}
$listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $Port)
try { $listener.Start() } catch { throw "Loopback port $Port is unavailable. Choose -Port or stop the owning service." } finally { $listener.Stop() }
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$records = @()
$savedState = @{ project_root = $projectRoot; workspace_root = $workspaceRoot; port = $Port; started_at = (Get-Date).ToUniversalTime().ToString('o'); processes = $records }
$previousWorkspace = [Environment]::GetEnvironmentVariable('MATH_AGENT_WORKSPACE', 'Process')
try {
    [Environment]::SetEnvironmentVariable('MATH_AGENT_WORKSPACE', $workspaceRoot, 'Process')
    foreach ($role in @('server', 'worker')) {
        if ($role -eq 'server') { $nativeArgs = @('-m', 'math_agent.cli', 'serve', '--host', '127.0.0.1', '--port', [string]$Port) }
        else { $nativeArgs = @('-m', 'math_agent.cli', 'worker', '--concurrency', '1') }
        $argumentLine = ($nativeArgs | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' '
        $stdoutPath = Join-Path $logRoot "$stamp-$role.stdout.log"
        $stderrPath = Join-Path $logRoot "$stamp-$role.stderr.log"
        $process = Start-Process -FilePath $pythonExe -ArgumentList $argumentLine -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
        $records += @{ pid = $process.Id; executable = $pythonExe; start_time_utc_ticks = $process.StartTime.ToUniversalTime().Ticks; role = $role; stdout = $stdoutPath; stderr = $stderrPath }
        $savedState.processes = $records
        Write-AgentJson -Path $pidFile -Value $savedState
    }
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        foreach ($record in $records) { if (-not (Test-AgentProcess $record)) { throw "The $($record.role) process exited. Inspect $($record.stderr)." } }
        try {
            $null = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 1
            $ready = $true; break
        } catch { Start-Sleep -Milliseconds 400 }
    }
    if (-not $ready) { throw "Server did not become ready. Inspect $logRoot; process state is preserved at $pidFile." }
    Write-Host "Math teaching agent: http://127.0.0.1:$Port"
    Write-Host "Process records: $pidFile"
    Write-Host "Logs: $logRoot"
    Write-Host "Workspace: $workspaceRoot"
    Write-Host 'Stop using .\scripts\Stop-Local.ps1 with the same -Workspace argument (omit it for the default workspace).'
    if ($OpenBrowser) { Start-Process -FilePath "http://127.0.0.1:$Port" }
} catch {
    Write-Warning 'Startup did not complete. Logs and process records were preserved; Stop-Local.ps1 with the same -Workspace can clean up this workspace.'
    throw
} finally {
    [Environment]::SetEnvironmentVariable('MATH_AGENT_WORKSPACE', $previousWorkspace, 'Process')
}
