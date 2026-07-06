$ErrorActionPreference = "Stop"

$repo = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
Set-Location $repo

$pyinstallerArgs = @(
  "--noconfirm",
  "--clean",
  "--windowed",
  "--name", "Gamma",
  "--icon", "assets\gamma_logo.ico",
  "--add-data", "assets\gamma_logo.png;assets",
  "--add-data", "assets\gamma_logo.ico;assets",
  "--add-data", "configs\default_thresholds.yaml;configs",
  "--add-data", "seed_registry.yaml;.",
  "--hidden-import", "seed_adapters",
  "--add-data", "relay_coil_inductive_kick\seed_manifest.json;relay_coil_inductive_kick",
  "--add-data", "high_speed_input_bounce\seed_manifest.json;high_speed_input_bounce",
  "--add-data", "missed_short_pulse\seed_manifest.json;missed_short_pulse"
)

$seedDirs = Get-ChildItem -Path $repo -Directory | Where-Object { Test-Path (Join-Path $_.FullName "seed_manifest.json") }
foreach ($dir in $seedDirs) {
  $manifest = Join-Path $dir.FullName "seed_manifest.json"
  $relativeManifest = $manifest.Substring($repo.Path.Length + 1)
  if ($relativeManifest -notin @(
      "relay_coil_inductive_kick\seed_manifest.json",
      "high_speed_input_bounce\seed_manifest.json",
      "missed_short_pulse\seed_manifest.json"
    )) {
    $pyinstallerArgs += "--add-data"
    $pyinstallerArgs += "$relativeManifest;$($dir.Name)"
  }
  $pyinstallerArgs += "--collect-submodules"
  $pyinstallerArgs += $dir.Name
}

& python -m PyInstaller @pyinstallerArgs gamma_desktop.py

Write-Host "Built dist\Gamma\Gamma.exe"
