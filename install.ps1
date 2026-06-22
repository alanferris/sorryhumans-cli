<#
  Sorry, humans — one line and your Windows joins the hive. NO Git Bash: runs in PowerShell.

    & ([scriptblock]::Create((irm https://sorryhumans.dev/install.ps1))) -Project t_xxxx

  (without -Project it asks for the role). Installs the connector in an isolated venv, the
  /sorryhumans skill, connects via browser (no API keys pasted) and opens Claude Code.

  It is the PowerShell equivalent of install.sh (which requires sh/Git Bash).
#>
param(
  [string]$Project = ""
)

# Allows passing the project via env var (for the 'irm | iex' shortcut without a scriptblock).
if (-not $Project -and $env:SORRYHUMANS_PROJECT) { $Project = $env:SORRYHUMANS_PROJECT }

$Dist  = "https://storage.googleapis.com/sorryhumans-dist"
$Wheel = "sorryhumans_cli-0.1.28-py3-none-any.whl"
$Root  = $env:USERPROFILE
$ShDir = Join-Path $Root ".sorryhumans"
$Venv  = Join-Path $ShDir "venv"

Write-Host ""
Write-Host "Sorry, humans." -ForegroundColor DarkYellow
Write-Host "Setting up your machine (PowerShell)..."
Write-Host ""

# 1) Python 3.11+. On Windows it's usually the 'py' launcher or 'python'. We decide by RUNNING IT
#    (the Microsoft Store stubs don't print a version, so they get discarded).
$Py = $null
foreach ($cand in @(@("py","-3"), @("python"), @("python3"))) {
  $exe = $cand[0]
  if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
  $pre = @(); if ($cand.Count -gt 1) { $pre = $cand[1..($cand.Count - 1)] }
  try {
    $v = (& $exe @pre "-c" "import sys;print(sys.version_info[0]*100+sys.version_info[1])" 2>$null)
    if ($LASTEXITCODE -eq 0 -and $v -and ([int]($v -replace '\D','') -ge 311)) { $Py = $cand; break }
  } catch {}
}
if (-not $Py) {
  Write-Host "  No Python 3.11+ found on PATH." -ForegroundColor Red
  Write-Host "  Install it, then re-run this command:"
  Write-Host "    winget install Python.Python.3.12" -ForegroundColor DarkYellow
  Write-Host "    (or https://www.python.org/downloads/ -> tick 'Add python.exe to PATH', then open a NEW PowerShell)"
  return
}
$PyExe = $Py[0]
$PyPre = @(); if ($Py.Count -gt 1) { $PyPre = $Py[1..($Py.Count - 1)] }

# 2) Isolated venv (brings its own pip). On Windows the binaries go in Scripts\.
New-Item -ItemType Directory -Force -Path $ShDir | Out-Null
$VenvPy = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
  & $PyExe @PyPre "-m" "venv" $Venv
}
if (-not (Test-Path $VenvPy)) {
  Write-Host "  Could not create the venv (Python without the venv module?)." -ForegroundColor Red
  return
}
$VenvExe = Join-Path $Venv "Scripts\sorryhumans.exe"

# 3) Install the connector from the bucket.
try {
  & $VenvPy "-m" "pip" "install" "--quiet" "--upgrade" "--no-cache-dir" "$Dist/$Wheel"
  if ($LASTEXITCODE -ne 0) { throw "pip install exited with code $LASTEXITCODE" }
  Write-Host "  Connector installed."
} catch {
  Write-Host "  pip install failed: $_" -ForegroundColor Red
  return
}

# 4) Install the /sorryhumans skill for Claude Code.
$SkillDir = Join-Path $Root ".claude\skills\sorryhumans"
New-Item -ItemType Directory -Force -Path $SkillDir | Out-Null
try {
  Invoke-WebRequest -UseBasicParsing "$Dist/SKILL.md" -OutFile (Join-Path $SkillDir "SKILL.md")
  Write-Host "  Skill /sorryhumans installed for Claude Code."
} catch {}

# 5) Ensure Claude Code (connect wires its MCP and we launch it).
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
  Write-Host ""
  Write-Host "  Claude Code isn't installed. Installing..."
  try { irm https://claude.ai/install.ps1 | iex }
  catch { Write-Host "  Couldn't auto-install Claude Code. Get it at https://claude.ai/download and re-run." }
  # The native installer puts 'claude' in ~\.local\bin
  $env:Path = (Join-Path $Root ".local\bin") + ";" + $env:Path
}

# 6) Connect: browser login (no key pasting). With -Project it joins as agent directly.
Write-Host ""
$role = "agent"
if (-not $Project) {
  $ans = Read-Host "Is this machine the leader (orchestrator) or an agent? [agent]"
  if ($ans -eq "leader") { $role = "leader" }
}
if ($Project) { & $VenvExe connect --role $role $Project }
else          { & $VenvExe connect --role $role }

# 7) Remember autonomy (free mode) and launch Claude Code, bound to the project.
if ($Project) { $env:SORRYHUMANS_PROJECT = $Project }
try { & $VenvExe set-autonomy $Project 1 2>$null } catch {}
if (Get-Command claude -ErrorAction SilentlyContinue) {
  Write-Host ""
  Write-Host 'Opening Claude Code...' -ForegroundColor White
  Write-Host '(say "check the hive" once it loads)'
  Start-Sleep -Seconds 1
  & claude --dangerously-skip-permissions
} else {
  Write-Host ""
  Write-Host "You're in the hive. Run:  claude --dangerously-skip-permissions   and say 'check the hive'."
}
