$ErrorActionPreference='Stop'
$references=@('System.dll','System.Core.dll','System.Drawing.dll','System.Windows.Forms.dll','System.Web.Extensions.dll','WindowsBase.dll','UIAutomationClient.dll','UIAutomationTypes.dll')
$paths = @()
foreach ($name in $references) { $assembly = [Reflection.Assembly]::LoadWithPartialName([IO.Path]::GetFileNameWithoutExtension($name)); if ($null -eq $assembly) { throw ('Missing Windows assembly: ' + $name) }; $paths += $assembly.Location }
Add-Type -Path (Join-Path $PSScriptRoot 'Native.cs') -ReferencedAssemblies $paths
foreach ($name in @('bridge.ps1','check.ps1')) {
    $tokens=$null;$errors=$null
    $null=[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $name),[ref]$tokens,[ref]$errors)
    if ($errors.Count -gt 0) { throw ($errors | Out-String) }
}
Write-Output 'C# compilation and PowerShell syntax passed; no desktop input sent.'
