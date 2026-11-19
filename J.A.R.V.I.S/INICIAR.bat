@echo off
cd /d "%~dp0"
title J.A.R.V.I.S. MARK LXI
if not exist .venv (
  echo [JARVIS] Criando ambiente virtual...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
python -c "import PyQt6" 2>nul
if errorlevel 1 (
  echo [JARVIS] Instalando dependencias (primeira vez)...
  python -m pip install --upgrade pip
  pip install -r requirements.txt
)
if exist config\secrets.vault del /f /q config\secrets.vault
echo [JARVIS] Iniciando...
python -m main
pause
