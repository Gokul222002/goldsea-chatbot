@echo off
cd /d "%~dp0"
echo Starting GoldSea AI Chatbot...
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run_server.py
) else (
    python run_server.py
)
pause
