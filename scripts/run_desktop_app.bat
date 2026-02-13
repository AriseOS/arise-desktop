@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM Quick start script for Ami Desktop App - Electron (Windows)

REM Parse arguments
SET "USE_LOCAL_CLOUD=false"
FOR %%A IN (%*) DO (
    IF "%%A"=="--local" (
        SET "USE_LOCAL_CLOUD=true"
    )
)

REM Ensure daemon sees local cloud setting before it starts
IF "%USE_LOCAL_CLOUD%"=="true" (
    SET "APP_BACKEND_CLOUD_API_URL=http://localhost:9090"
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
    echo    Mode: Using LOCAL Cloud Backend (http://localhost:9090^)
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
    cd ..\..\..
)

REM Start the app in development mode
echo Starting Electron app (Development Mode)...
echo    AMI_DEV_MODE=1 -^> Using Python source code

echo.

REM Set environment variables and run
IF "%USE_LOCAL_CLOUD%"=="true" (
    echo    APP_BACKEND_CLOUD_API_URL=http://localhost:9090
    echo.
    set AMI_DEV_MODE=1
    set APP_BACKEND_CLOUD_API_URL=http://localhost:9090
    cd src\clients\desktop_app
    call npm run electron:dev
    cd ..\..\..
) ELSE (
    echo.
    set AMI_DEV_MODE=1
    cd src\clients\desktop_app
    call npm run electron:dev
    cd ..\..\..
)

goto :EOF
