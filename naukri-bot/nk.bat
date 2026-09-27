@echo off
REM Type 'nk' (via PowerShell profile) or 'nk.bat' here to run the Naukri auto-apply bot.
cd /d "%~dp0"
python -m src.orchestrator.run %*
