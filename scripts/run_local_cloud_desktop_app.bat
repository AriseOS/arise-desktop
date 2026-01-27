@echo off
REM Start local Cloud Backend + Desktop App (Windows)

REM Resolve project root from this script location
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

echo.
echo ============================================================
echo Starting local Cloud Backend + Desktop App
echo ============================================================
echo Project root: %PROJECT_ROOT%
echo.

REM Validate project structure
if not exist "%PROJECT_ROOT%\src\cloud_backend\main.py" (
    echo Error: Cloud Backend entrypoint not found.
    echo    Expected: %PROJECT_ROOT%\src\cloud_backend\main.py
    exit /b 1
)
if not exist "%PROJECT_ROOT%\scripts\run_desktop_app.bat" (
    echo Error: Desktop App script not found.
    echo    Expected: %PROJECT_ROOT%\scripts\run_desktop_app.bat
    exit /b 1
)

REM Start Cloud Backend if not running
netstat -ano | findstr ":9000" >nul 2>&1
if not errorlevel 1 (
    echo [OK] Cloud Backend already running on port 9000
) else (
    echo Starting Cloud Backend on port 9000...
    start "Ami Cloud Backend" /MIN cmd /c python "%PROJECT_ROOT%\src\cloud_backend\main.py"

    REM Wait for Cloud Backend to be ready
    echo Waiting for Cloud Backend to be ready...
    timeout /t 5 /nobreak >nul

    netstat -ano | findstr ":9000" >nul 2>&1
    if errorlevel 1 (
        echo [WARNING] Cloud Backend may not have started properly. Continuing anyway...
    ) else (
        echo [OK] Cloud Backend is running on port 9000
    )
)

echo.

REM Start Desktop App with local cloud
pushd "%PROJECT_ROOT%" >nul
call "%PROJECT_ROOT%\scripts\run_desktop_app.bat" --local
popd >nul
