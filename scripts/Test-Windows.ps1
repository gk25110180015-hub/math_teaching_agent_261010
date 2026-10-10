[CmdletBinding()]
param([ValidateSet('mock', 'browser', 'compile', 'reference', 'security', 'live')][string]$Suite = 'mock')
. (Join-Path $PSScriptRoot 'Common-Windows.ps1')
Assert-SupportedPowerShell
$projectRoot = Get-AgentRoot
$pythonExe = Get-AgentPython $projectRoot
$reportRoot = Join-Path $projectRoot 'reports\test-runs'
New-Item -ItemType Directory -Force -Path $reportRoot | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$logPath = Join-Path $reportRoot "$stamp-$Suite.log"
$xmlPath = Join-Path $reportRoot "$stamp-$Suite.xml"
$testWorkspace = Join-Path $projectRoot ('workspace\t\' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $testWorkspace) | Out-Null
if (Test-Path -LiteralPath $testWorkspace) { throw 'The test workspace already exists; refusing to reuse or delete it.' }
$marker = switch ($Suite) {
    'mock' { 'not real_api and not reference and not windows_compile and not e2e' }
    'browser' { 'e2e' }
    'compile' { 'windows_compile' }
    'reference' { 'reference' }
    'security' { 'security' }
    'live' { 'real_api' }
}
if ($Suite -eq 'live') {
    Import-AgentUserEnvironment
    if ($env:MATH_AGENT_LIVE_API_ENABLED -ne 'true' -or [string]::IsNullOrWhiteSpace($env:MATH_AGENT_API_KEY)) { throw 'Live tests are NOT_RUN: explicitly configure MATH_AGENT_LIVE_API_ENABLED=true and an API key in the environment.' }
}
$offlineNames = @('MATH_AGENT_API_KEY', 'MATH_AGENT_DEEPSEEK_API_KEY', 'MATH_AGENT_LIVE_API_ENABLED', 'MATH_AGENT_LLM_PROVIDER', 'MATH_AGENT_LLM_STREAMING')
$savedOfflineEnvironment = @{}
if ($Suite -ne 'live') {
    foreach ($name in $offlineNames) { $savedOfflineEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
    $env:MATH_AGENT_API_KEY = ''
    $env:MATH_AGENT_DEEPSEEK_API_KEY = ''
    $env:MATH_AGENT_LIVE_API_ENABLED = 'false'
    $env:MATH_AGENT_LLM_PROVIDER = 'mock'
    $env:MATH_AGENT_LLM_STREAMING = 'false'
}
Push-Location -LiteralPath $projectRoot
try {
    & $pythonExe -m pytest -q -m $marker "--junitxml=$xmlPath" "--basetemp=$testWorkspace" 2>&1 | Tee-Object -FilePath $logPath
    $exitCode = $LASTEXITCODE
    Write-AgentJson -Path (Join-Path $reportRoot "$stamp-$Suite.json") -Value @{ suite = $Suite; marker = $marker; exit_code = $exitCode; log = $logPath; junit = $xmlPath; test_workspace = $testWorkspace; executed_at = (Get-Date).ToUniversalTime().ToString('o'); human_visual_review = 'NOT_RUN'; note = 'Read JUnit/logs for PASSED, FAILED and SKIPPED. This command does not perform teacher visual acceptance.' }
    if ($exitCode -ne 0) { throw "Test command exited with $exitCode. Evidence preserved: $logPath" }
    Write-Host "Test command completed. Inspect skipped/blocked cases in $xmlPath. Human visual acceptance: NOT_RUN."
} finally {
    Pop-Location
    if ($Suite -ne 'live') {
        foreach ($name in $offlineNames) { [Environment]::SetEnvironmentVariable($name, $savedOfflineEnvironment[$name], 'Process') }
    }
}
