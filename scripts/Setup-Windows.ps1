[CmdletBinding()]
param([string]$PythonPath = '')
. (Join-Path $PSScriptRoot 'Common-Windows.ps1')
Assert-SupportedPowerShell
$projectRoot = Get-AgentRoot
$cacheRoot = Join-Path $projectRoot '.uv-cache'
Push-Location -LiteralPath $projectRoot
try {
    $bundledUv = Join-Path $projectRoot '.tools\bin\uv.exe'
    $uvExecutable = $null
    if (Test-Path -LiteralPath $bundledUv -PathType Leaf) { $uvExecutable = $bundledUv }
    else {
        $uvCommand = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue
        if ($null -ne $uvCommand) { $uvExecutable = $uvCommand.Source }
    }
    if ($null -ne $uvExecutable) {
        if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'uv.lock'))) { throw 'uv.lock is missing; installation cannot claim a locked dependency set.' }
        & $uvExecutable sync --locked --extra dev --cache-dir $cacheRoot
        if ($LASTEXITCODE -ne 0) { throw "uv sync failed: $LASTEXITCODE" }
    } else {
        if ([string]::IsNullOrWhiteSpace($PythonPath)) {
            $pythonCommand = Get-Command python -CommandType Application -ErrorAction SilentlyContinue
            if ($null -eq $pythonCommand) { throw 'Python is missing. Install Python 3.12 from https://www.python.org/downloads/windows/ or pass -PythonPath.' }
            $PythonPath = $pythonCommand.Source
        }
        if (-not [IO.Path]::IsPathRooted($PythonPath)) { throw '-PythonPath must be an absolute executable path.' }
        & $PythonPath -c 'import sys; assert (3,12) <= sys.version_info[:2] < (3,14), "Python 3.12 or 3.13 is required"'
        if ($LASTEXITCODE -ne 0) { throw 'The selected Python version is unsupported.' }
        if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
            & $PythonPath -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
        }
        $pythonExe = Get-AgentPython $projectRoot
        & $pythonExe -c 'import importlib.util,sys; sys.exit(0 if importlib.util.find_spec("pip") else 1)'
        if ($LASTEXITCODE -ne 0) {
            & $pythonExe -m ensurepip
            if ($LASTEXITCODE -ne 0) { throw 'Installing pip into the project virtual environment failed.' }
        }
        & $pythonExe -m pip install uv
        if ($LASTEXITCODE -ne 0) { throw 'Installing uv into the project environment failed.' }
        & $pythonExe -m uv sync --locked --extra dev --cache-dir $cacheRoot
        if ($LASTEXITCODE -ne 0) { throw 'Locked dependency installation failed.' }
    }
    Write-Host 'Dependencies installed. No global Python, PATH, or execution policy was changed.'
    Invoke-AgentCommand -ProjectRoot $projectRoot -Arguments @('doctor')
} finally { Pop-Location }
