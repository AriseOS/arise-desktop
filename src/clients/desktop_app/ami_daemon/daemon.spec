# -*- mode: python ; coding: utf-8 -*-

"""
PyInstaller spec file for Ami daemon
Compiles daemon.py and all dependencies into a macOS .app bundle
Following industry best practices for code signing and notarization
"""

import sys
import os
import platform
from pathlib import Path

# Project root (Ami/)
# daemon.spec is at: src/clients/desktop_app/ami_daemon/daemon.spec
# Need 4 parents: ami_daemon -> desktop_app -> clients -> src -> Ami
spec_dir = Path(SPECPATH)
project_root = spec_dir.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Chromium is NOT bundled - will be auto-installed on first launch
playwright_browsers = []
print("Skipping Playwright Chromium bundling (will be handled separately)")

block_cipher = None

a = Analysis(
    ['daemon.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        # Config files
        ('config/app-backend.yaml', 'config'),

        # JavaScript files for browser behavior tracking
        (str(project_root / 'src/clients/desktop_app/ami_daemon/base_agent/tools/browser_use/user_behavior/behavior_tracker.js'),
         'src/clients/desktop_app/ami_daemon/base_agent/tools/browser_use/user_behavior'),

        # Automation hooks JS
        (str(project_root / 'src/clients/desktop_app/ami_daemon/base_agent/tools/browser_use/automation_hooks.js'),
         'src/clients/desktop_app/ami_daemon/base_agent/tools/browser_use'),

        # Bundled browser extensions (avoid downloading from Google in China)
        (str(project_root / 'deploy/bundled_extensions'), 'bundled_extensions'),
    ] + playwright_browsers,
    hiddenimports=[
        # Uvicorn and FastAPI
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',

        # Playwright and browser automation
        'playwright',
        'playwright.async_api',
        'playwright._impl',
        'playwright._impl._api_types',
        'websockets',
        'websockets.client',
        'websockets.server',

        # Ami daemon services
        'src.clients.desktop_app.ami_daemon.services.storage_manager',
        'src.clients.desktop_app.ami_daemon.services.browser_manager',
        'src.clients.desktop_app.ami_daemon.services.cdp_recorder',
        'src.clients.desktop_app.ami_daemon.services.cloud_client',
        'src.clients.desktop_app.ami_daemon.services.browser_window_manager',

        # Ami daemon core
        'src.clients.desktop_app.ami_daemon.core.config_service',
        'src.clients.desktop_app.ami_daemon.models.execution',

        # Common modules
        'src.common.config_service',
        'src.common.llm.anthropic_provider',
        'src.common.llm.openai_provider',
        'src.common.services.simple_sync',
        'src.common.services.metadata_generator',
        'src.common.services.resource_manager',

        # Base agent components
        'src.clients.desktop_app.ami_daemon.base_agent.core.base_agent',
        'src.clients.desktop_app.ami_daemon.base_agent.core.schemas',
        'src.clients.desktop_app.ami_daemon.base_agent.agents.text_agent',
        'src.clients.desktop_app.ami_daemon.base_agent.agents.browser_agent',
        'src.clients.desktop_app.ami_daemon.base_agent.agents.storage_agent',
        'src.clients.desktop_app.ami_daemon.base_agent.agents.variable_agent',
        'src.clients.desktop_app.ami_daemon.base_agent.memory.kv_storage',

        # Database
        'aiosqlite',
        'sqlalchemy',
        'sqlalchemy.ext',
        'sqlalchemy.ext.asyncio',

        # YAML
        'yaml',

        # HTTP clients
        'httpx',
        'aiohttp',

        # Pydantic
        'pydantic',
        'pydantic_settings',

        # File sync utilities
        'pathspec',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unused packages to reduce size
        'pytest',
        'pytest_asyncio',
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
        'jupyter',
        'IPython',
        'setuptools._vendor.packaging.licenses',

        # Heavy libraries not needed at runtime
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        'cv2',
        'numpy',
        'mypy',
        'Cython',
        'h5py',
        'astropy',
        'numba',
        'torch',
        'tensorflow',
        'keras',
        'sklearn',
        'PIL.ImageQt',

        # Claude Code SDK (no longer used)
        'claude_agent_sdk',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher
)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,  # onedir mode - binaries go to COLLECT
    name='ami-daemon',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    target_arch=None,
    # Note: We don't sign here because Tauri will overwrite it anyway
    # Final signing happens in build.sh after Tauri bundles the app
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ami-daemon'
)

# macOS only: Create a proper .app bundle
# Following Apple's bundle structure guidelines for notarization
import platform
if platform.system() == 'Darwin':
    app = BUNDLE(
        coll,
        name='ami-daemon.app',
        icon=None,
        bundle_identifier='com.arise.ami-daemon',
        info_plist={
            'CFBundleName': 'ami-daemon',
            'CFBundleDisplayName': 'Ami Daemon',
            'CFBundleIdentifier': 'com.arise.ami-daemon',
            'CFBundleVersion': '0.1.0',
            'CFBundleShortVersionString': '0.1.0',
            'CFBundleExecutable': 'ami-daemon',
            'CFBundlePackageType': 'APPL',
            'LSBackgroundOnly': True,
            'LSUIElement': True,
            'NSHighResolutionCapable': True,
        },
        # Note: We don't sign here because Tauri will overwrite it anyway
        # Final signing happens in build.sh after Tauri bundles the app
        codesign_identity=None,
        entitlements_file=None,
    )
