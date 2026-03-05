@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM Quick start script for Arise Desktop App - Electron (Windows)

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
set "ARISE_LOG_DIR=%USERPROFILE%\.arise\logs"
if not exist "%ARISE_LOG_DIR%" mkdir "%ARISE_LOG_DIR%" >nul 2>&1
set "DAEMON_BOOT_LOG=%ARISE_LOG_DIR%\daemon-boot.log"
set "DAEMON_HOST=127.0.0.1"
set "DAEMON_DEFAULT_PORT=8765"
set "DAEMON_HEALTH_PATH=/api/v1/health"
set "DAEMON_PORT_FILE=%USERPROFILE%\.arise\daemon.port"
set "DAEMON_TIMEOUT_SECONDS=12"

REM Resolve project root from script location
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"

echo.
echo Starting Arise Desktop App...
IF "%USE_LOCAL_CLOUD%"=="true" (
    echo    Mode: Using LOCAL Cloud Backend (http://localhost:9090^)
) ELSE (
    echo    Mode: Using REMOTE Cloud Backend
)
echo.

REM Check if node_modules exists
IF NOT EXIST "%PROJECT_ROOT%\node_modules" (
    echo Installing dependencies...
    pushd "%PROJECT_ROOT%"
    call npm install
    popd
)

REM Check if daemon-ts node_modules exists
IF NOT EXIST "%PROJECT_ROOT%\daemon-ts\node_modules" (
    echo Installing daemon-ts dependencies...
    pushd "%PROJECT_ROOT%\daemon-ts"
    call npm install
    popd
)

REM Ensure daemon-ts dist exists for Windows startup
set "DAEMON_DIST_SERVER=%PROJECT_ROOT%\daemon-ts\dist\server.js"
set "DAEMON_DIST_BROWSER_SCRIPTS=%PROJECT_ROOT%\daemon-ts\dist\browser\scripts"

IF NOT EXIST "%DAEMON_DIST_SERVER%" (
    echo Building daemon-ts dist for Windows startup...
    pushd "%PROJECT_ROOT%\daemon-ts"
    call npx tsc
    IF ERRORLEVEL 1 (
        echo ERROR: Failed to compile daemon-ts via TypeScript compiler.
        popd
        exit /b 1
    )

    if not exist "dist\browser\scripts" mkdir "dist\browser\scripts" >nul 2>&1
    robocopy "src\browser\scripts" "dist\browser\scripts" /E >nul
    IF !ERRORLEVEL! GEQ 8 (
        echo ERROR: Failed to copy daemon browser scripts into dist.
        popd
        exit /b 1
    )
    popd
) ELSE IF NOT EXIST "%DAEMON_DIST_BROWSER_SCRIPTS%" (
    echo Copying daemon browser scripts into dist...
    pushd "%PROJECT_ROOT%\daemon-ts"
    if not exist "dist\browser\scripts" mkdir "dist\browser\scripts" >nul 2>&1
    robocopy "src\browser\scripts" "dist\browser\scripts" /E >nul
    IF !ERRORLEVEL! GEQ 8 (
        echo ERROR: Failed to copy daemon browser scripts into dist.
        popd
        exit /b 1
    )
    popd
)

REM Start the app in development mode
echo Starting Electron app (Development Mode)...
echo    ARISE_DEV_MODE=1 -^> Windows uses compiled daemon dist first (tsx fallback)

echo.

REM Set environment variables and run
pushd "%PROJECT_ROOT%"
IF "%USE_LOCAL_CLOUD%"=="true" (
    echo    APP_BACKEND_CLOUD_API_URL=http://localhost:9090
    echo.
    set ARISE_DEV_MODE=1
    set APP_BACKEND_CLOUD_API_URL=http://localhost:9090
    call npm run electron:dev
) ELSE (
    echo.
    set ARISE_DEV_MODE=1
    call npm run electron:dev
)
popd

goto :EOF
