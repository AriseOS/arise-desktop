@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM Start local Cloud Backend + Desktop App (Windows)

REM Resolve project root from this script location
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

REM Logging + health check configuration
set "AMI_LOG_DIR=%USERPROFILE%\.ami\logs"
if not exist "%AMI_LOG_DIR%" mkdir "%AMI_LOG_DIR%" >nul 2>&1
set "CLOUD_BOOT_LOG=%AMI_LOG_DIR%\cloud-backend-boot.log"
set "CLOUD_HOST=127.0.0.1"
set "CLOUD_PORT=9090"
set "CLOUD_HEALTH_URL=http://%CLOUD_HOST%:%CLOUD_PORT%/health"
set "CLOUD_TIMEOUT_SECONDS=12"

REM Resolve Python executable (AMI_PYTHON_EXE > local venv > shared venv > PATH)
call :resolve_python
echo Using Python: !PYTHON_EXE!
echo [%date% %time%] Using Python: !PYTHON_EXE!>>"%CLOUD_BOOT_LOG%"

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

REM Start Cloud Backend if not running (robust check: LISTENING + /health)
call :check_cloud_ready
if "!CLOUD_READY!"=="1" (
    echo [OK] Cloud Backend already healthy on port !CLOUD_PORT! ^(PID: !CLOUD_PID!^)
) else (
    echo Starting Cloud Backend on port !CLOUD_PORT!...
    echo [%date% %time%] Starting cloud backend from %PROJECT_ROOT%>>"%CLOUD_BOOT_LOG%"
    set "CLOUD_ENTRY=%PROJECT_ROOT%\src\cloud_backend\main.py"
    echo [%date% %time%] Launch cmd: "!PYTHON_EXE!" "!CLOUD_ENTRY!">>"%CLOUD_BOOT_LOG%"
    set "PYTHONUTF8=1"
    start "Ami Cloud Backend" /MIN cmd /s /c ""!PYTHON_EXE!" "!CLOUD_ENTRY!" 1>>"%CLOUD_BOOT_LOG%" 2>>&1"

    REM Wait for Cloud Backend to be ready
    echo Waiting for Cloud Backend to be ready ^(timeout: !CLOUD_TIMEOUT_SECONDS!s^)...
    call :wait_for_cloud_ready !CLOUD_TIMEOUT_SECONDS!

    if "!CLOUD_READY!"=="1" (
        echo [OK] Cloud Backend is healthy on port !CLOUD_PORT! ^(PID: !CLOUD_PID!^)
    ) else (
        echo [ERROR] Cloud Backend did not become ready within !CLOUD_TIMEOUT_SECONDS! seconds.
        echo [INFO] See boot log: "%CLOUD_BOOT_LOG%"
        call :print_port_owners !CLOUD_PORT!
    )
)

echo.

REM Start Desktop App with local cloud
pushd "%PROJECT_ROOT%" >nul
call "%PROJECT_ROOT%\scripts\run_desktop_app.bat" --local
popd >nul

goto :EOF

REM ===================================================================
REM Helpers
REM ===================================================================

:resolve_python
set "PYTHON_EXE="
set "PYTHON_SOURCE="

if defined AMI_PYTHON_EXE (
    if exist "%AMI_PYTHON_EXE%" (
        set "PYTHON_EXE=%AMI_PYTHON_EXE%"
        set "PYTHON_SOURCE=env"
    ) else (
        echo [WARNING] AMI_PYTHON_EXE is set but not found: %AMI_PYTHON_EXE%
    )
)

if not defined PYTHON_EXE if exist "%PROJECT_ROOT%\.venv312\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_ROOT%\.venv312\Scripts\python.exe"
    set "PYTHON_SOURCE=project-.venv312"
)

if not defined PYTHON_EXE if exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_ROOT%\.venv\Scripts\python.exe"
    set "PYTHON_SOURCE=project-.venv"
)

if not defined PYTHON_EXE if exist "%PROJECT_ROOT%\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_ROOT%\venv\Scripts\python.exe"
    set "PYTHON_SOURCE=project-venv"
)

if not defined PYTHON_EXE if exist "G:\Python_Workspace\venv\Scripts\python.exe" (
    set "PYTHON_EXE=G:\Python_Workspace\venv\Scripts\python.exe"
    set "PYTHON_SOURCE=shared-venv"
)

if not defined PYTHON_EXE (
    set "PYTHON_EXE=python"
    set "PYTHON_SOURCE=path"
)
goto :EOF

:check_cloud_ready
set "CLOUD_READY=0"
set "CLOUD_LISTENING=0"
set "CLOUD_HEALTHY=0"
set "CLOUD_PID="

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%CLOUD_PORT% .*LISTENING"') do (
    set "CLOUD_LISTENING=1"
    set "CLOUD_PID=%%P"
)

powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri '%CLOUD_HEALTH_URL%' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 set "CLOUD_HEALTHY=1"

if "!CLOUD_LISTENING!"=="1" if "!CLOUD_HEALTHY!"=="1" set "CLOUD_READY=1"
goto :EOF

:wait_for_cloud_ready
set /a "_timeout=%~1"
set /a "_elapsed=0"

:cloud_wait_loop
call :check_cloud_ready
if "!CLOUD_READY!"=="1" goto :EOF
if !_elapsed! GEQ !_timeout! goto :EOF
set /a "_elapsed+=1"
timeout /t 1 /nobreak >nul
goto :cloud_wait_loop

:print_port_owners
set "_port=%~1"
set "_found=0"

echo [INFO] LISTENING entries for port !_port!:
for /f "tokens=1,2,3,4,5" %%A in ('netstat -ano ^| findstr /R /C:":%_port% .*LISTENING"') do (
    set "_found=1"
    echo     %%A %%B %%C %%D %%E
    echo [INFO] Process for PID %%E:
    tasklist /FI "PID eq %%E"
)

if "!_found!"=="0" (
    echo [INFO] No LISTENING process found on port !_port!.
)
goto :EOF
