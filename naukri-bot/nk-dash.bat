@echo off
REM Dashboard + bot remote: opens the dashboard and starts the control server.
REM Buttons on the page start/stop the Naukri bot. Close this window to stop the server.
cd /d "%~dp0"
start "" http://127.0.0.1:8765
python -m src.tools.server
