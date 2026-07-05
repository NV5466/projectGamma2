$ErrorActionPreference = "Stop"

$repo = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
Set-Location $repo

python -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name Gamma `
  --icon assets\gamma_logo.ico `
  --add-data "assets\gamma_logo.png;assets" `
  --add-data "assets\gamma_logo.ico;assets" `
  --add-data "configs\default_thresholds.yaml;configs" `
  --add-data "relay_coil_inductive_kick\seed_manifest.json;relay_coil_inductive_kick" `
  --add-data "high_speed_input_bounce\seed_manifest.json;high_speed_input_bounce" `
  --add-data "missed_short_pulse\seed_manifest.json;missed_short_pulse" `
  gamma_desktop.py

Write-Host "Built dist\Gamma\Gamma.exe"
