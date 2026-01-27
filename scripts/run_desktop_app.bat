@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM Quick start script for Ami Desktop App (Windows)

REM Parse arguments
SET "USE_LOCAL_CLOUD=false"
FOR %%A IN (%*) DO (
    IF "%%A"=="--local" (
        SET "USE_LOCAL_CLOUD=true"
    )
)

REM Ensure daemon sees local cloud setting before it starts
IF "%USE_LOCAL_CLOUD%"=="true" (
    SET "APP_BACKEND_CLOUD_API_URL=http://localhost:9000"
)

REM Logging + daemon health check configuration
set "AMI_LOG_DIR=%USERPROFILE%\.ami\logs"
if not exist "%AMI_LOG_DIR%" mkdir "%AMI_LOG_DIR%" >nul 2>&1
set "DAEMON_BOOT_LOG=%AMI_LOG_DIR%\daemon-boot.log"
set "DAEMON_HOST=127.0.0.1"
set "DAEMON_DEFAULT_PORT=8765"
set "DAEMON_HEALTH_PATH=/api/v1/health"
set "DAEMON_PORT_FILE=%USERPROFILE%\.ami\daemon.port"
set "DAEMON_TIMEOUT_SECONDS=12"

echo.
echo Starting Ami Desktop App...
IF "%USE_LOCAL_CLOUD%"=="true" (
    echo    Mode: Using LOCAL Cloud Backend (http://localhost:9000^)
) ELSE (
    echo    Mode: Using REMOTE Cloud Backend
)
echo.

REM Check if we're in the right directory
IF NOT EXIST "src\clients\desktop_app" (
    echo Error: Please run this script from the project root directory
    echo    Current directory: %CD%
    EXIT /B 1
)

REM Check if node_modules exists
IF NOT EXIST "src\clients\desktop_app\node_modules" (
    echo Installing dependencies...
    cd src\clients\desktop_app
    call npm install

    REM Install Tauri CLI
    echo Installing Tauri CLI...
    call npm install --save-dev @tauri-apps/cli

    cd ..\..\..
)

REM Check if Tauri CLI is installed
IF NOT EXIST "src\clients\desktop_app\node_modules\@tauri-apps" (
    echo Installing Tauri CLI...
    cd src\clients\desktop_app
    call npm install --save-dev @tauri-apps/cli
    cd ..\..\..
)

REM Start the app in development mode
echo Starting Tauri app (Development Mode)...
echo    AMI_DEV_MODE=1 -^> Using Python source code

echo.
echo ============================================================
echo NOTE: First-time compilation may take 5-15 minutes
echo       Compiling Rust backend (this is normal)...
echo       Subsequent runs will be much faster.
echo ============================================================
echo.

REM Start Python daemon first (for Windows compatibility)
echo.
echo ============================================================
echo Starting Python daemon...
echo ============================================================

REM Get the project root absolute path
SET "PROJECT_ROOT=%CD%"

REM Resolve Python executable (AMI_PYTHON_EXE > local venv > shared venv > PATH)
call :resolve_python
echo Using Python: !PYTHON_EXE!
echo [%date% %time%] Using Python: !PYTHON_EXE!>>"%DAEMON_BOOT_LOG%"

REM Check if daemon is already running (robust check: LISTENING + /api/v1/health)
call :detect_daemon_ready
IF "!DAEMON_READY!"=="1" (
    if /I "!DAEMON_SOURCE!"=="port-file" (
        echo [OK] Daemon already healthy on port !DAEMON_PORT! ^(via port file, PID: !DAEMON_PID!^)
    ) else (
        echo [OK] Daemon already healthy on port !DAEMON_PORT! ^(PID: !DAEMON_PID!^)
    )
) ELSE (
    call :read_port_file
    if defined DAEMON_PORT_FROM_FILE (
        echo [INFO] Found daemon port file ^(!DAEMON_PORT_FROM_FILE!^) but it is not healthy. Continuing...
    )

    echo Starting daemon in background...
    echo [%date% %time%] Starting daemon from %PROJECT_ROOT%>>"%DAEMON_BOOT_LOG%"
    start "Ami Daemon" /MIN cmd /c "chcp 65001>nul & set PYTHONUTF8=1& ""!PYTHON_EXE!"" "%PROJECT_ROOT%\src\clients\desktop_app\ami_daemon\daemon.py" 1>>"%DAEMON_BOOT_LOG%" 2>>&1"

    REM Wait for daemon to start
    echo Waiting for daemon to be ready ^(timeout: !DAEMON_TIMEOUT_SECONDS!s^)...
    call :wait_for_daemon_ready !DAEMON_TIMEOUT_SECONDS!

    REM Check if daemon started successfully
    IF "!DAEMON_READY!"=="1" (
        echo [OK] Daemon is healthy on port !DAEMON_PORT! ^(PID: !DAEMON_PID!^)
    ) ELSE (
        echo [ERROR] Daemon did not become ready within !DAEMON_TIMEOUT_SECONDS! seconds.
        echo [INFO] See boot log: "%DAEMON_BOOT_LOG%"
        call :print_port_owners !DAEMON_DEFAULT_PORT!
        call :read_port_file
        if defined DAEMON_PORT_FROM_FILE if not "!DAEMON_PORT_FROM_FILE!"=="!DAEMON_DEFAULT_PORT!" (
            call :print_port_owners !DAEMON_PORT_FROM_FILE!
        )
    )
)

echo.

REM Set environment variables and run
IF "%USE_LOCAL_CLOUD%"=="true" (
    echo    APP_BACKEND_CLOUD_API_URL=http://localhost:9000
    echo.
    set AMI_DEV_MODE=1
    set APP_BACKEND_CLOUD_API_URL=http://localhost:9000
    cd src\clients\desktop_app
    call npm run tauri dev
    cd ..\..\..
) ELSE (
    echo.
    set AMI_DEV_MODE=1
    cd src\clients\desktop_app
    call npm run tauri dev
    cd ..\..\..
)

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

:read_port_file
set "DAEMON_PORT_FROM_FILE="
if exist "%DAEMON_PORT_FILE%" (
    for /f "usebackq tokens=1" %%P in ("%DAEMON_PORT_FILE%") do set "DAEMON_PORT_FROM_FILE=%%P"
)
goto :EOF

:check_port_listening
set "_port=%~1"
set "PORT_LISTENING=0"
set "PORT_PID="

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%_port% .*LISTENING"') do (
    set "PORT_LISTENING=1"
    set "PORT_PID=%%P"
)
goto :EOF

:check_daemon_health
set "_port=%~1"
set "DAEMON_HEALTHY=0"
set "DAEMON_HEALTH_URL=http://%DAEMON_HOST%:%_port%%DAEMON_HEALTH_PATH%"

powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri '%DAEMON_HEALTH_URL%' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 set "DAEMON_HEALTHY=1"
goto :EOF

:check_ready_on_port
set "_port=%~1"
set "READY_ON_PORT=0"
set "PORT_LISTENING=0"
set "PORT_PID="
set "DAEMON_HEALTHY=0"

call :check_port_listening %_port%
call :check_daemon_health %_port%

if "!PORT_LISTENING!"=="1" if "!DAEMON_HEALTHY!"=="1" set "READY_ON_PORT=1"
goto :EOF

:detect_daemon_ready
set "DAEMON_READY=0"
set "DAEMON_PORT="
set "DAEMON_PID="
set "DAEMON_SOURCE="

call :read_port_file
if defined DAEMON_PORT_FROM_FILE (
    call :check_ready_on_port %DAEMON_PORT_FROM_FILE%
    if "!READY_ON_PORT!"=="1" (
        set "DAEMON_READY=1"
        set "DAEMON_PORT=%DAEMON_PORT_FROM_FILE%"
        set "DAEMON_PID=!PORT_PID!"
        set "DAEMON_SOURCE=port-file"
        goto :EOF
    )
)

call :check_ready_on_port %DAEMON_DEFAULT_PORT%
if "!READY_ON_PORT!"=="1" (
    set "DAEMON_READY=1"
    set "DAEMON_PORT=%DAEMON_DEFAULT_PORT%"
    set "DAEMON_PID=!PORT_PID!"
    set "DAEMON_SOURCE=default-port"
)
goto :EOF

:wait_for_daemon_ready
set /a "_timeout=%~1"
set /a "_elapsed=0"

:daemon_wait_loop
call :detect_daemon_ready
if "!DAEMON_READY!"=="1" goto :EOF
if !_elapsed! GEQ !_timeout! goto :EOF
set /a "_elapsed+=1"
timeout /t 1 /nobreak >nul
goto :daemon_wait_loop

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
