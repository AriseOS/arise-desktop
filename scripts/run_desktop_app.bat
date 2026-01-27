@echo off
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

REM Check if daemon is already running
netstat -ano | findstr ":8765" >nul 2>&1
IF NOT ERRORLEVEL 1 (
    echo [OK] Daemon is already running on port 8765
) ELSE (
    echo Starting daemon in background...
    start "Ami Daemon" /MIN cmd /c python "%PROJECT_ROOT%\src\clients\desktop_app\ami_daemon\daemon.py"

    REM Wait for daemon to start
    echo Waiting for daemon to be ready...
    timeout /t 5 /nobreak >nul

    REM Check if daemon started successfully
    netstat -ano | findstr ":8765" >nul 2>&1
    IF ERRORLEVEL 1 (
        echo [WARNING] Daemon may not have started properly. Continuing anyway...
    ) ELSE (
        echo [OK] Daemon is running on port 8765
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
