@echo off
:: start.bat — Start the Vantyx local server on Windows
:: Double-click this file or run from Command Prompt

cd /d "%~dp0"

if exist ".env" (
    echo [Vantyx] Loading credentials from .env...
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        set "line=%%a"
        if not "!line:~0,1!"=="#" (
            set "%%a=%%b"
        )
    )
) else (
    echo [Vantyx] WARNING: .env not found.
    echo [Vantyx] Copy .env.example to .env and fill in your credentials.
    echo.
)

echo.
echo ==============================================
echo   Vantyx Local Server
echo   Website:   http://localhost:8080/
echo   LOI Form:  http://localhost:8080/loi
echo   Dashboard: http://localhost:8080/dashboard
echo ==============================================
echo.

python server.py
pause
