@echo off
REM Dashboard + bot remote. Run:  nk-dash
REM Opens the server in its own window, then the dashboard in your browser.
REM The Start/Stop buttons work only on that http:// page, not on index.html opened as a file.
REM Close the server window to stop it.
cd /d "%~dp0"
start "Naukri Dashboard Server" python -m src.tools.server
echo Waiting for server...
timeout /t 4 /nobreak >nul
start "" http://127.0.0.1:8765
echo Dashboard opening. Keep the server window open; close it to stop.
