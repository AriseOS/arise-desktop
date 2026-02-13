# Desktop App Packaging Size Analysis

## Problem

Two issues found comparing macOS (117MB DMG) vs Windows (66MB ZIP) builds:

1. **macOS bloated by ~127MB** — stale `browser-use` residual packages in cached `venv-build`
2. **Both platforms missing toolkit dependencies** — lazy imports not detected by PyInstaller

## Build Comparison (v0.2.2)

### Overall Size

| Platform | Compressed | Uncompressed | Format |
|----------|-----------|-------------|--------|
| macOS | 117MB (DMG) | 301MB (Ami.app) | `.app` bundle in UDZO DMG |
| Windows | 66MB (ZIP) | 159MB (portable dir) | Flat directory in ZIP |

### Component Breakdown

#### Shared Components (both platforms)

| Component | macOS | Windows | Notes |
|-----------|-------|---------|-------|
| Playwright `node` binary | 111MB | 86MB | arm64 Mach-O vs x64 PE, biggest single item |
| Playwright `driver/package` | 12MB | 12MB | JS source, same |
| pydantic_core | 4MB | 5.2MB | Native extension |
| aiohttp | 832K | 476K | Native extension |
| Tauri shell (exe) | ~6MB | 4.3MB | Ami binary itself |

### Issue 1: macOS-only `browser-use` residual packages (NOT needed)

Pulled in by `browser-use` (removed from `pyproject.toml`) but lingering in macOS `venv-build` cache.

| Package | Size | Used by our code? |
|---------|------|-------------------|
| `googleapiclient` (discovery_cache: 568 JSON files) | **91MB** | **NO** |
| `PIL` (Pillow) — partially needed, see below | **11MB** | Only as reportlab dep |
| `cryptography` + `libcrypto.3.dylib` + `libssl.3.dylib` | **15.2MB** | **NO** |
| `httplib2` | 136K | **NO** |
| **Total waste** | **~117MB** | |

**Root cause**: CI caches `venv-build` with `restore-keys: ${{ runner.os }}-venv-` fallback. When `pyproject.toml` changed (browser-use removed), the old cache was restored and `pip install` only added new packages without removing stale ones.

### Issue 2: Missing toolkit dependencies (BOTH platforms)

These packages are used via lazy imports (`import X` inside function body), so PyInstaller cannot detect them. They were missing from both `pyproject.toml` and `daemon.spec` hiddenimports.

| Package | Used by | macOS had it? | Windows had it? |
|---------|---------|--------------|----------------|
| `reportlab` | file_toolkit (Markdown → PDF) | Yes (via browser-use) | **NO** |
| `python-docx` | file_toolkit (Markdown → DOCX) | Yes (via browser-use) | **NO** |
| `markdown` | file_toolkit (Markdown → HTML) | **NO** | **NO** |
| `pypdf` | quick_task_service (PDF reading) | **NO** | **NO** |
| `beautifulsoup4` | file_toolkit (HTML parsing) | **NO** | **NO** |
| `lxml` | python-docx dependency | Yes (via browser-use) | **NO** |
| `Pillow` | reportlab dependency | Yes (via browser-use) | **NO** |
| `openpyxl` | excel_toolkit | **NO** | **NO** |
| `python-pptx` | pptx_toolkit | **NO** | **NO** |
| `markitdown` | markitdown_toolkit | **NO** | **NO** |

### Windows-only stale packages

| Package | Size | Notes |
|---------|------|-------|
| `surrealdb` | **11MB** | From `[memory]` extra. Cloud backend only, not needed by daemon |
| `pytz` | 2.5MB | Transitive dep. Not imported by our code |

## Fixes Applied

### 1. `pyproject.toml` — added missing desktop dependencies

```toml
desktop = [
    # ... existing deps ...

    # Document generation (file_toolkit: Markdown -> PDF/DOCX)
    "reportlab>=4.0.0",
    "python-docx>=1.0.0",
    "markdown>=3.5.0",
    "pypdf>=4.0.0",
    "Pillow>=10.0.0",
    "beautifulsoup4>=4.12.0",
    "lxml>=5.0.0",

    # Office toolkits (excel_toolkit, pptx_toolkit)
    "openpyxl>=3.1.0",
    "python-pptx>=0.6.23",

    # Document conversion (markitdown_toolkit)
    "markitdown>=0.1.0",
]
```

### 2. `daemon.spec` — added hiddenimports for lazy imports

PyInstaller cannot detect `import X` inside function bodies. Added all toolkit packages to `hiddenimports`.

### 3. `daemon.spec` — added excludes for packages that should never be bundled

```python
excludes=[
    # Google API (not used by daemon, 91MB discovery_cache)
    'googleapiclient', 'google.api_core', 'google.auth',
    'google_auth_oauthlib', 'google_auth_httplib2', 'httplib2',

    # Cloud/memory-only packages
    'surrealdb', 'neo4j', 'networkx',
]
```

### 4. Required: Delete stale venv-build caches

Both local and CI caches must be cleared before next build:

```bash
# Local
rm -rf src/clients/desktop_app/ami_daemon/venv-build

# CI: delete GitHub Actions cache via gh CLI
gh cache delete --all
```
