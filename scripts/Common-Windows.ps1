# Shared helpers. Compatible with Windows PowerShell 5.1 and PowerShell 7.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-SupportedPowerShell {
    if ($PSVersionTable.PSVersion.Major -lt 5) { throw 'PowerShell 5.1 or 7 is required.' }
    if ($env:OS -ne 'Windows_NT') { throw 'This script is for Windows. Use the documented CLI on other systems.' }
}

function Get-AgentRoot {
    return [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
}

function Get-AgentWorkspace {
    param([string]$ProjectRoot, [string]$Workspace = '')
    $allowedRoot = [IO.Path]::GetFullPath((Join-Path $ProjectRoot 'workspace')).TrimEnd('\', '/')
    if ([string]::IsNullOrWhiteSpace($Workspace)) { $target = $allowedRoot }
    elseif ([IO.Path]::IsPathRooted($Workspace)) { $target = [IO.Path]::GetFullPath($Workspace).TrimEnd('\', '/') }
    else { $target = [IO.Path]::GetFullPath((Join-Path $ProjectRoot $Workspace)).TrimEnd('\', '/') }
    if (-not ($target.Equals($allowedRoot, [StringComparison]::OrdinalIgnoreCase) -or $target.StartsWith($allowedRoot + '\', [StringComparison]::OrdinalIgnoreCase))) {
        throw 'Workspace must be the project workspace directory or a directory beneath it.'
    }
    # Refuse junctions/symlinks so a lexically contained path cannot redirect
    # process records, logs, or the worker database outside the project.
    $cursor = $target
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Workspace paths cannot contain reparse points.' }
        }
        $parent = [IO.Path]::GetDirectoryName($cursor)
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
    return $target
}

function Assert-AgentProcessState {
    param($State, [string]$ProjectRoot, [string]$WorkspaceRoot)
    if (-not $State.PSObject.Properties['project_root'] -or [IO.Path]::GetFullPath([string]$State.project_root) -ne $ProjectRoot) {
        throw 'Process record belongs to a different project; refusing to use it.'
    }
    if ($State.PSObject.Properties['workspace_root']) {
        if ([string]::IsNullOrWhiteSpace([string]$State.workspace_root) -or (Get-AgentWorkspace -ProjectRoot $ProjectRoot -Workspace ([string]$State.workspace_root)) -ne $WorkspaceRoot) {
            throw 'Process record belongs to a different workspace; refusing to use it.'
        }
    } elseif ($WorkspaceRoot -ne (Get-AgentWorkspace -ProjectRoot $ProjectRoot)) {
        throw 'Legacy process records are valid only in the default workspace.'
    }
}

function Import-AgentUserEnvironment {
    # Process overrides take precedence. No files, CLI literals, or browser secrets.
    foreach ($name in @('MATH_AGENT_API_KEY', 'MATH_AGENT_LIVE_API_ENABLED', 'MATH_AGENT_API_BASE_URL', 'MATH_AGENT_MODEL', 'MATH_AGENT_LLM_STREAMING', 'MATH_AGENT_DEEPSEEK_API_KEY', 'MATH_AGENT_DEEPSEEK_API_BASE_URL')) {
        if (-not [Environment]::GetEnvironmentVariable($name, 'Process')) {
            $value = [Environment]::GetEnvironmentVariable($name, 'User')
            if ($value) { [Environment]::SetEnvironmentVariable($name, $value, 'Process') }
        }
    }
}

function Get-AgentPython {
    param([string]$ProjectRoot)
    $pythonPath = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
        throw 'Project virtual environment is missing. Run scripts\Setup-Windows.ps1 first.'
    }
    return (Resolve-Path -LiteralPath $pythonPath).Path
}

function ConvertTo-NativeArgument {
    param([string]$Value)
    # Windows CreateProcess argument quoting; arguments are never evaluated as shell code.
    if ($Value -notmatch '[\s"]' -and $Value.Length -gt 0) { return $Value }
    return '"' + ([regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1')) + '"'
}

function Write-AgentJson {
    param([string]$Path, $Value)
    $text = $Value | ConvertTo-Json -Depth 12
    [IO.File]::WriteAllText($Path, $text, (New-Object Text.UTF8Encoding($false)))
}

function Test-AgentProcess {
    param($Record)
    $process = Get-Process -Id ([int]$Record.pid) -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $false }
    try {
        return (($process.Path -eq [string]$Record.executable) -and ($process.StartTime.ToUniversalTime().Ticks -eq [long]$Record.start_time_utc_ticks))
    } catch { return $false }
}

function Invoke-AgentCommand {
    param([string]$ProjectRoot, [string[]]$Arguments)
    $pythonPath = Get-AgentPython $ProjectRoot
    Import-AgentUserEnvironment
    Push-Location -LiteralPath $ProjectRoot
    try {
        & $pythonPath -m math_agent.cli @Arguments
        if ($LASTEXITCODE -ne 0) { throw "math-agent exited with code $LASTEXITCODE" }
    } finally { Pop-Location }
}
