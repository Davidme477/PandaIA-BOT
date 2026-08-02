param([string]$Python = "python", [switch]$Clean)
$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
Set-Location $project
& $Python -m pip install -r requirements.txt -r requirements-build.txt
$arguments = @("-m", "PyInstaller", "--noconfirm")
if ($Clean) { $arguments += "--clean" }
$arguments += "packaging/PandaIA.spec"
& $Python @arguments
if ($LASTEXITCODE -ne 0) { throw "PyInstaller no pudo construir PandaIA." }
Write-Host "Portable creada en $project\dist\PandaIA"
