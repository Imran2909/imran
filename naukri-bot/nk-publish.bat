@echo off
REM Publish fresh dashboard numbers: regenerates data.json, commits, pushes.
REM GitHub Actions then redeploys the public site automatically.
cd /d "%~dp0"
python -c "from src.tools.dashboard import export_dashboard; print(export_dashboard())"
cd ..
git add naukri-bot/dashboard/data.json
git commit -m "dashboard data refresh" || echo "nothing new to publish"
git push origin main
