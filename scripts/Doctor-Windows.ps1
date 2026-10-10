[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'Common-Windows.ps1')
Assert-SupportedPowerShell
Invoke-AgentCommand -ProjectRoot (Get-AgentRoot) -Arguments @('doctor')
