[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)][int]$Port = 8765,
    [string]$Workspace = '',
    [switch]$OpenBrowser,
    [ValidateRange(1, 120)][int]$ConnectSeconds = 30,
    [ValidateRange(1, 600)][int]$ReadSeconds = 600,
    [ValidateRange(1, 900)][int]$TotalSeconds = 600
)
# Start the usual app with longer per-attempt waits for complete chapter reviews.
# Credentials remain in environment variables; this script never reads their values.
$reviewProfile = @{
    MATH_AGENT_LLM_CONNECT_TIMEOUT_SECONDS = [string]$ConnectSeconds
    MATH_AGENT_LLM_READ_TIMEOUT_SECONDS = [string]$ReadSeconds
    MATH_AGENT_LLM_TOTAL_TIMEOUT_SECONDS = [string]$TotalSeconds
}
$previousReviewValues = @{}
try {
    foreach ($name in $reviewProfile.Keys) {
        $previousReviewValues[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $reviewProfile[$name], 'Process')
    }
    & (Join-Path $PSScriptRoot 'Run-Local.ps1') -Port $Port -Workspace $Workspace -OpenBrowser:$OpenBrowser
    Write-Host "Review waits per model attempt: connect=$ConnectSeconds s; read=$ReadSeconds s; total=$TotalSeconds s."
} finally {
    foreach ($name in $previousReviewValues.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previousReviewValues[$name], 'Process')
    }
}
