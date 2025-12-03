# Tauri Resources Directory

This directory contains bundled resources for the Tauri application.

## Contents

- `ami-daemon` (macOS/Linux) or `ami-daemon.exe` (Windows): Compiled Python backend binary

## Building

To generate the daemon binary:

```bash
cd /path/to/project/root
./scripts/build_daemon.sh
```

The build script will automatically copy the compiled binary to this directory.

## Development vs Production

- **Development mode**: Tauri app will use `python3 src/app_backend/daemon.py` if the binary is not found
- **Production mode**: Tauri app will use the bundled binary from this directory

This allows seamless development without needing to rebuild the binary every time.
