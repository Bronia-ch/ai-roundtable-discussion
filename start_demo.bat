@echo off
setlocal
set "ROOT=%~dp0"

echo Starting AI Roundtable backend and frontend...
start "AI Roundtable Backend" cmd /k "cd /d "%ROOT%backend" && "%ROOT%.venv\Scripts\python.exe" -m uvicorn app.main:app --port 8000"
start "AI Roundtable Frontend" cmd /k "cd /d "%ROOT%frontend" && npm run dev"

echo Waiting for the web page to become available...
start "" powershell.exe -NoProfile -WindowStyle Hidden -Command "$url='http://localhost:5173'; for ($i=0; $i -lt 30; $i++) { try { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1 ^| Out-Null; Start-Process $url; exit } catch { Start-Sleep -Seconds 1 } }; Start-Process $url"

echo.
echo Backend:  http://localhost:8000
echo Frontend: http://localhost:5173
echo The browser will open automatically when the frontend is ready.
echo Keep both windows open while demonstrating.
endlocal
