[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)][int]$Port = 8765,
    [string]$Workspace = 'workspace',
    [switch]$OpenBrowser,
    [switch]$Setup
)

# Install this file in the copied repository's scripts directory.
# Model values are loaded only into this process and inherited by its children.
. (Join-Path $PSScriptRoot 'Common-Windows.ps1')
Assert-SupportedPowerShell
$snapshotProjectRoot = Get-AgentRoot
$snapshotWorkspaceRoot = Get-AgentWorkspace -ProjectRoot $snapshotProjectRoot -Workspace $Workspace
$snapshotRuntimeRoot = Get-AgentWorkspace -ProjectRoot $snapshotProjectRoot -Workspace (Join-Path $snapshotWorkspaceRoot 'runtime')
$snapshotPidFile = Get-AgentWorkspace -ProjectRoot $snapshotProjectRoot -Workspace (Join-Path $snapshotRuntimeRoot 'local-processes.json')
$snapshotConfigPath = Join-Path $snapshotProjectRoot 'snapshot\model-environment.json'
if (-not (Test-Path -LiteralPath $snapshotConfigPath -PathType Leaf)) {
    $snapshotConfigPath = Join-Path $snapshotProjectRoot 'snapshot\model-environment.example.json'
}
$snapshotAllowedNames = @(
    'MATH_AGENT_API_KEY',
    'MATH_AGENT_API_BASE_URL',
    'MATH_AGENT_DEEPSEEK_API_KEY',
    'MATH_AGENT_DEEPSEEK_API_BASE_URL',
    'MATH_AGENT_MODEL',
    'MATH_AGENT_LLM_PROVIDER',
    'MATH_AGENT_LIVE_API_ENABLED',
    'MATH_AGENT_LLM_STREAMING',
    'MATH_AGENT_LLM_CONNECT_TIMEOUT_SECONDS',
    'MATH_AGENT_LLM_READ_TIMEOUT_SECONDS',
    'MATH_AGENT_LLM_TOTAL_TIMEOUT_SECONDS',
    'MATH_AGENT_MAX_REQUESTS_PER_RUN',
    'MATH_AGENT_REQUEST_BUDGET_HARD_CAP',
    'MATH_AGENT_MAX_NETWORK_RETRIES',
    'MATH_AGENT_MAX_SCHEMA_REPAIR_ATTEMPTS',
    'MATH_AGENT_MAX_LOCAL_REPAIR_ATTEMPTS',
    'MATH_AGENT_MAX_GLOBAL_REPAIR_ROUNDS',
    'MATH_AGENT_COMPILE_MODE',
    'MATH_AGENT_REQUIRE_INPUT_TRUST_CONFIRMATION',
    'MATH_AGENT_LEASE_SECONDS'
)
$snapshotValues = @{}
if (Test-Path -LiteralPath $snapshotConfigPath -PathType Leaf) {
    try {
        $snapshotConfig = Get-Content -Raw -Encoding UTF8 -LiteralPath $snapshotConfigPath | ConvertFrom-Json
    } catch {
        throw 'snapshot/model-environment.json could not be read as JSON.'
    }
    if ($null -eq $snapshotConfig -or $snapshotConfig -isnot [System.Management.Automation.PSCustomObject]) {
        throw 'snapshot/model-environment.json must contain an object of environment variable names and scalar values.'
    }
    foreach ($snapshotProperty in $snapshotConfig.PSObject.Properties) {
        if ($snapshotAllowedNames -cnotcontains $snapshotProperty.Name) {
            throw ('Unsupported environment variable in snapshot/model-environment.json: ' + $snapshotProperty.Name)
        }
        if ($null -eq $snapshotProperty.Value -or $snapshotProperty.Value -is [System.Management.Automation.PSCustomObject] -or $snapshotProperty.Value -is [System.Array]) {
            throw ('A scalar environment value is required for ' + $snapshotProperty.Name)
        }
        $snapshotValues[$snapshotProperty.Name] = [string]$snapshotProperty.Value
    }
}

$snapshotPreviousEnvironment = @{}
foreach ($snapshotName in ($snapshotAllowedNames + @('MATH_AGENT_REFERENCE_ROOT', 'MATH_AGENT_WORKSPACE', 'PYTHONPATH'))) {
    $snapshotPreviousEnvironment[$snapshotName] = [Environment]::GetEnvironmentVariable($snapshotName, 'Process')
}
try {
    foreach ($snapshotName in $snapshotValues.Keys) {
        [Environment]::SetEnvironmentVariable($snapshotName, $snapshotValues[$snapshotName], 'Process')
    }
    [Environment]::SetEnvironmentVariable('MATH_AGENT_REFERENCE_ROOT', (Join-Path $snapshotProjectRoot 'reference_data'), 'Process')
    [Environment]::SetEnvironmentVariable('MATH_AGENT_WORKSPACE', $snapshotWorkspaceRoot, 'Process')
    $snapshotPythonPath = Join-Path $snapshotProjectRoot 'src'
    if (-not [string]::IsNullOrWhiteSpace($snapshotPreviousEnvironment['PYTHONPATH'])) {
        $snapshotPythonPath += [IO.Path]::PathSeparator + $snapshotPreviousEnvironment['PYTHONPATH']
    }
    [Environment]::SetEnvironmentVariable('PYTHONPATH', $snapshotPythonPath, 'Process')

    if ($Setup) {
        & (Join-Path $PSScriptRoot 'Setup-Windows.ps1')
    }

    # A copied process record refers to the original machine/project. Preserve it
    # as an imported record without inspecting, terminating, or reusing its PIDs.
    if (Test-Path -LiteralPath $snapshotPidFile -PathType Leaf) {
        try {
            $snapshotProcessState = Get-Content -Raw -Encoding UTF8 -LiteralPath $snapshotPidFile | ConvertFrom-Json
            if ($null -eq $snapshotProcessState -or -not $snapshotProcessState.PSObject.Properties['project_root'] -or [string]::IsNullOrWhiteSpace([string]$snapshotProcessState.project_root)) {
                throw 'Missing project root.'
            }
            $snapshotRecordedRoot = [IO.Path]::GetFullPath([string]$snapshotProcessState.project_root).TrimEnd('\', '/')
        } catch {
            throw 'The existing local-processes.json has an invalid project root; the record was preserved.'
        }
        if (-not $snapshotRecordedRoot.Equals($snapshotProjectRoot.TrimEnd('\', '/'), [StringComparison]::OrdinalIgnoreCase)) {
            $snapshotImportedName = 'local-processes.imported-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fffffff') + '.json'
            $snapshotImportedPath = Get-AgentWorkspace -ProjectRoot $snapshotProjectRoot -Workspace (Join-Path $snapshotRuntimeRoot $snapshotImportedName)
            Move-Item -LiteralPath $snapshotPidFile -Destination $snapshotImportedPath -ErrorAction Stop
        }
    }

    $snapshotRunArguments = @{
        Port = $Port
        Workspace = $snapshotWorkspaceRoot
        OpenBrowser = $OpenBrowser
    }
    # Preserve explicit snapshot timeouts; otherwise use ExtendedReview defaults.
    $snapshotTimeoutArguments = @{
        MATH_AGENT_LLM_CONNECT_TIMEOUT_SECONDS = 'ConnectSeconds'
        MATH_AGENT_LLM_READ_TIMEOUT_SECONDS = 'ReadSeconds'
        MATH_AGENT_LLM_TOTAL_TIMEOUT_SECONDS = 'TotalSeconds'
    }
    foreach ($snapshotName in $snapshotTimeoutArguments.Keys) {
        if ($snapshotValues.ContainsKey($snapshotName)) {
            $snapshotTimeoutValue = 0
            if (-not [int]::TryParse($snapshotValues[$snapshotName], [ref]$snapshotTimeoutValue)) {
                throw ('An integer timeout is required for ' + $snapshotName)
            }
            $snapshotRunArguments[$snapshotTimeoutArguments[$snapshotName]] = $snapshotTimeoutValue
        }
    }
    & (Join-Path $PSScriptRoot 'Run-ExtendedReview.ps1') @snapshotRunArguments
} finally {
    foreach ($snapshotName in $snapshotPreviousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($snapshotName, $snapshotPreviousEnvironment[$snapshotName], 'Process')
    }
}
