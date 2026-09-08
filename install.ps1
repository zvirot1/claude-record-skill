# Windows installer: copies skills\* into %USERPROFILE%\.claude\skills and installs Python deps.
# Run from the repo root:  Set-ExecutionPolicy -Scope Process Bypass; .\install.ps1
$ErrorActionPreference = "Stop"
$root = Join-Path $env:USERPROFILE ".claude\skills"
New-Item -ItemType Directory -Force -Path $root | Out-Null
Get-ChildItem -Directory (Join-Path $PSScriptRoot "skills") | ForEach-Object {
  $dest = Join-Path $root $_.Name
  if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
  Copy-Item -Recurse $_.FullName $dest
  Write-Host "[install] $($_.Name) -> $dest"
}
$py = $null; $v = ""
foreach ($c in @("py -3", "python", "python3")) {
  try { $v = (& cmd /c "$c --version 2>&1"); if ("$v" -match "Python 3") { $py = $c; break } } catch {}
}
if (-not $py) {
  Write-Host "[install] Python 3 not found. Run: winget install Python.Python.3.12   (then re-run this script)"
  exit 1
}
Write-Host "[install] using $py ($v)"
& cmd /c "$py -m pip install --user --quiet mss pynput pillow"
$rs = Join-Path $root "record-skill\scripts"
& cmd /c "$py `"$rs\save_skill.py`" --list"
Write-Host ""
Write-Host "[install] done. Tests:"
Write-Host "  $py `"$rs\record.py`" --no-input --duration 5        (screenshots only)"
Write-Host "  $py `"$rs\record.py`" --duration 30                   (mouse+keyboard, stop with Ctrl+Shift+Q)"
