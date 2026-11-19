#Requires -Version 5.1
<#
.SYNOPSIS
  J.A.R.V.I.S. — instalação modo 24/7 no Windows (energia, venv, watchdog, startup, task).

.NOTES
  Execute na pasta do projeto (onde estão main.py e requirements.txt), em PowerShell:
    Set-ExecutionPolicy -Scope Process Bypass -Force
    .\install_24h.ps1

  Requer: Python 3.11+ no PATH. Alguns passos (schtasks/startup) podem pedir Admin.
#>
$ErrorActionPreference = "Continue"
$Root = $PSScriptRoot
if (-not $Root) { $Root = Get-Location }
Set-Location $Root

Write-Host "== J.A.R.V.I.S. install 24/7 ==" -ForegroundColor Cyan

# 1. Energia — nunca suspender / desligar tela / hibernar na tomada
Write-Host "`n[1/6] powercfg (AC)..." -ForegroundColor Yellow
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
if ($LASTEXITCODE -ne 0) {
  Write-Host "  Aviso: powercfg retornou codigo $LASTEXITCODE (pode precisar de Admin)." -ForegroundColor DarkYellow
} else {
  Write-Host "  OK: standby/monitor/hibernate AC = 0" -ForegroundColor Green
}

# 2. venv + dependencias
Write-Host "`n[2/6] ambiente virtual + pip..." -ForegroundColor Yellow
if (-Not (Test-Path ".venv")) {
  python -m venv .venv
  if ($LASTEXITCODE -ne 0) { Write-Host "Falha ao criar .venv — verifique o Python." -ForegroundColor Red; exit 1 }
}
& .\.venv\Scripts\python.exe -m 
# Node.js / npx for MCP servers
if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
  Write-Host "[JARVIS] Instalando Node.js LTS (MCP)..." -ForegroundColor Cyan
  winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
  $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
} else {
  Write-Host "[JARVIS] Node.js/npx OK" -ForegroundColor Green
}

pip install --upgrade pip
& .\.venv\Scripts\pip.exe install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
  Write-Host "  Aviso: pip install retornou erro — revise requirements.txt." -ForegroundColor DarkYellow
} else {
  Write-Host "  OK: requirements instalados no .venv" -ForegroundColor Green
}

# 3. Watchdog 24h
Write-Host "`n[3/6] rodar_jarvis_24h.bat..." -ForegroundColor Yellow
$batContent = @"
@echo off
title J.A.R.V.I.S. - Servidor 24h
cd /d "%~dp0"

:loop
echo [%date% %time%] Iniciando J.A.R.V.I.S. (Modo 24/7)...
call .venv\Scripts\activate.bat
python -m main
echo [%date% %time%] Processo encerrado. Reiniciando em 3 segundos...
timeout /t 3 /nobreak >nul
goto loop
"@
Set-Content -Path "rodar_jarvis_24h.bat" -Value $batContent -Encoding ASCII
Write-Host "  OK: rodar_jarvis_24h.bat" -ForegroundColor Green

# 4. Atalho na Inicializacao do Windows
Write-Host "`n[4/6] atalho shell:startup..." -ForegroundColor Yellow
try {
  $WshShell = New-Object -ComObject WScript.Shell
  $StartupPath = [Environment]::GetFolderPath('Startup')
  $Shortcut = $WshShell.CreateShortcut("$StartupPath\JARVIS_24h.lnk")
  $Shortcut.TargetPath = Join-Path $Root "rodar_jarvis_24h.bat"
  $Shortcut.WorkingDirectory = $Root
  $Shortcut.WindowStyle = 7
  $Shortcut.Save()
  Write-Host "  OK: $StartupPath\JARVIS_24h.lnk" -ForegroundColor Green
} catch {
  Write-Host "  Aviso: nao foi possivel criar atalho de startup: $_" -ForegroundColor DarkYellow
}

# 5. Reinicio preventivo diario 04:00 (mata python — ajuste se rodar outros scripts)
Write-Host "`n[5/6] schtasks manutencao 04:00..." -ForegroundColor Yellow
schtasks /create /tn "JARVIS_Manutencao_Diaria" /tr "taskkill /f /im python.exe" /sc daily /st 04:00 /f
if ($LASTEXITCODE -ne 0) {
  Write-Host "  Aviso: schtasks falhou (Admin?). Crie manualmente se necessario." -ForegroundColor DarkYellow
} else {
  Write-Host "  OK: tarefa JARVIS_Manutencao_Diaria" -ForegroundColor Green
}

# 6. Inicia agora
Write-Host "`n[6/6] iniciando watchdog..." -ForegroundColor Yellow
Start-Process -FilePath (Join-Path $Root "rodar_jarvis_24h.bat")
Write-Host "`n[OK] J.A.R.V.I.S. configurado para 24/7 (energia + startup + loop + task 04:00)." -ForegroundColor Green
Write-Host "AudioRelay sobe no boot do main.py se estiver instalado." -ForegroundColor DarkGray
