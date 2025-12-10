# -*- mode: python ; coding: utf-8 -*-

"""
PyInstaller spec file for Ami daemon
Compiles daemon.py and all dependencies into a single binary executable
"""

import sys
import os
from pathlib import Path

# Project root (ami/)
# In spec files, use SPECPATH which is the directory containing the spec file
spec_dir = Path(SPECPATH)
project_root = spec_dir.parent.parent
sys.path.insert(0, str(project_root))

# Find Playwright browsers directory
# Note: We will NOT bundle Chromium directly in PyInstaller due to codesign issues
# Instead, we'll copy it to Tauri resources and reference it there
playwright_browsers = []
print("Skipping Playwright Chromium bundling in PyInstaller (will be handled by Tauri)")
print("Chromium will be copied to Tauri resources directory separately")

block_cipher = None

a = Analysis(
    ['daemon.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        # Config files
        ('config/app-backend.yaml', 'config'),

        # Browser tools from base_app
        (str(project_root / 'src/clients/base_app/base_app/base_agent/tools'), 'base_app/base_agent/tools'),

        # Browser session manager
        (str(project_root / 'src/clients/base_app/base_app/base_agent/core'), 'base_app/base_agent/core'),

        # Workflows (if any default workflows need to be bundled)
        (str(project_root / 'src/clients/base_app/base_app/base_agent/workflows'), 'base_app/base_agent/workflows'),
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

        # App backend services
        'src.app_backend.services.storage_manager',
        'src.app_backend.services.browser_manager',
        'src.app_backend.services.workflow_executor',
        'src.app_backend.services.cdp_recorder',
        'src.app_backend.services.cloud_client',
        'src.app_backend.services.browser_window_manager',

        # App backend core
        'src.app_backend.core.config_service',
        'src.app_backend.models.execution',

        # Common modules
        'src.common.config_service',
        'src.common.llm.anthropic_provider',
        'src.common.llm.openai_provider',

        # Base app components
        'src.clients.base_app.base_app.base_agent.core.base_agent',
        'src.clients.base_app.base_app.base_agent.core.schemas',
        'src.clients.base_app.base_app.base_agent.agents.text_agent',
        'src.clients.base_app.base_app.base_agent.agents.tool_agent',
        'src.clients.base_app.base_app.base_agent.agents.browser_agent',
        'src.clients.base_app.base_app.base_agent.agents.storage_agent',
        'src.clients.base_app.base_app.base_agent.agents.variable_agent',
        'src.clients.base_app.base_app.base_agent.tools.browser_session_manager',
        'src.clients.base_app.base_app.base_agent.memory.kv_storage',

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
        'setuptools._vendor.packaging.licenses',  # Optional module causing warnings
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ami-daemon',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console for logging during development, change to False for production
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
