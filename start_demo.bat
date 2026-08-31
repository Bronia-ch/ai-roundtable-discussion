@echo off
setlocal
set "ROOT=%~dp0"

echo Starting AI Roundtable backend and frontend...
start "AI Roundtable Backend" cmd /k "cd /d ""%ROOT%backend"" && ""%ROOT%.venv\Scripts\python.exe"" -m uvicorn app.main:app --port 8000"
start "AI Roundtable Frontend" cmd /k "cd /d ""%ROOT%frontend"" && npm run dev"

echo Waiting for the web page to become available...
timeout /t 4 /nobreak >nul
start "" "http://localhost:5173"

echo.
echo Backend:  http://localhost:8000
echo Frontend: http://localhost:5173
echo The browser will open automatically when the frontend is ready.
echo Keep both windows open while demonstrating.
endlocal
