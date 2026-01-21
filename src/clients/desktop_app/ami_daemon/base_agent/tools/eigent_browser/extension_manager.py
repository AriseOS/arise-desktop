"""
Extension Manager for browser automation.

Downloads and manages Chrome extensions to make the browser appear more like
a real user's browser. Based on browser-use library's approach.
"""

import logging
import os
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Default extensions for anti-detection
# These make the browser appear more like a real user's browser
DEFAULT_EXTENSIONS = [
    {
        'name': 'uBlock Origin',
        'id': 'cjpalhdlnbpafiamejdnhcphjbkeiagm',
        'url': 'https://clients2.google.com/service/update2/crx?response=redirect&prodversion=133&acceptformat=crx3&x=id%3Dcjpalhdlnbpafiamejdnhcphjbkeiagm%26uc',
    },
    {
        'name': "I still don't care about cookies",
        'id': 'edibdbjcniadpccecjdfdjjppcpchdlm',
        'url': 'https://clients2.google.com/service/update2/crx?response=redirect&prodversion=133&acceptformat=crx3&x=id%3Dedibdbjcniadpccecjdfdjjppcpchdlm%26uc',
    },
    {
        'name': 'ClearURLs',
        'id': 'lckanjgmijmafbedllaakclkaicjfmnk',
        'url': 'https://clients2.google.com/service/update2/crx?response=redirect&prodversion=133&acceptformat=crx3&x=id%3Dlckanjgmijmafbedllaakclkaicjfmnk%26uc',
    },
    # Note: Force Background Tab not included - not needed for our use case
]


class ExtensionManager:
    """Manages Chrome extension downloading, caching, and loading."""

    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize ExtensionManager.

        Args:
            cache_dir: Directory to cache extensions. Defaults to ~/.ami/extensions
        """
        if cache_dir is None:
            cache_dir = Path.home() / '.ami' / 'extensions'
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def ensure_extensions_downloaded(
        self,
        extensions: Optional[List[dict]] = None
    ) -> List[str]:
        """Ensure extensions are downloaded and return their paths.

        Args:
            extensions: List of extension configs. Uses DEFAULT_EXTENSIONS if None.

        Returns:
            List of paths to extension directories.
        """
        if extensions is None:
            extensions = DEFAULT_EXTENSIONS

        extension_paths = []
        loaded_names = []

        for ext in extensions:
            ext_dir = self.cache_dir / ext['id']
            crx_file = self.cache_dir / f"{ext['id']}.crx"

            # Check if already extracted
            if ext_dir.exists() and (ext_dir / 'manifest.json').exists():
                logger.debug(f"Using cached extension: {ext['name']}")
                extension_paths.append(str(ext_dir))
                loaded_names.append(ext['name'])
                continue

            try:
                # Download if needed
                if not crx_file.exists():
                    logger.info(f"Downloading extension: {ext['name']}...")
                    self._download_extension(ext['url'], crx_file)

                # Extract
                logger.info(f"Extracting extension: {ext['name']}...")
                self._extract_extension(crx_file, ext_dir)

                extension_paths.append(str(ext_dir))
                loaded_names.append(ext['name'])

            except Exception as e:
                logger.warning(f"Failed to setup extension {ext['name']}: {e}")
                continue

        if extension_paths:
            logger.info(f"Extensions loaded ({len(extension_paths)}): {loaded_names}")
        else:
            logger.warning("No extensions could be loaded")

        return extension_paths

    def _download_extension(self, url: str, output_path: Path) -> None:
        """Download extension .crx file.

        Args:
            url: URL to download from
            output_path: Path to save the .crx file
        """
        try:
            # Add headers to avoid being blocked
            request = urllib.request.Request(
                url,
                headers={
                    'User-Agent': (
                        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/131.0.0.0 Safari/537.36'
                    ),
                    'Accept': '*/*',
                }
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                with open(output_path, 'wb') as f:
                    f.write(response.read())
            logger.debug(f"Downloaded extension to {output_path}")
        except Exception as e:
            raise Exception(f"Failed to download extension: {e}")

    def _extract_extension(self, crx_path: Path, extract_dir: Path) -> None:
        """Extract .crx file to directory.

        Args:
            crx_path: Path to .crx file
            extract_dir: Directory to extract to
        """
        # Remove existing directory
        if extract_dir.exists():
            shutil.rmtree(extract_dir)

        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Try to extract as ZIP first (CRX files are ZIP files with a header)
            with zipfile.ZipFile(crx_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            # Verify manifest exists
            if not (extract_dir / 'manifest.json').exists():
                raise Exception('No manifest.json found in extension')

        except zipfile.BadZipFile:
            # CRX files have a header before the ZIP data
            # Skip the CRX header and extract the ZIP part
            with open(crx_path, 'rb') as f:
                magic = f.read(4)
                if magic != b'Cr24':
                    raise Exception('Invalid CRX file format')

                version = int.from_bytes(f.read(4), 'little')
                if version == 2:
                    pubkey_len = int.from_bytes(f.read(4), 'little')
                    sig_len = int.from_bytes(f.read(4), 'little')
                    f.seek(16 + pubkey_len + sig_len)
                elif version == 3:
                    header_len = int.from_bytes(f.read(4), 'little')
                    f.seek(12 + header_len)
                else:
                    raise Exception(f'Unsupported CRX version: {version}')

                zip_data = f.read()

            # Write ZIP data to temp file and extract
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_zip:
                temp_zip.write(zip_data)
                temp_zip.flush()

                with zipfile.ZipFile(temp_zip.name, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)

                os.unlink(temp_zip.name)

            # Verify manifest exists
            if not (extract_dir / 'manifest.json').exists():
                raise Exception('No manifest.json found in extension')

    def get_extension_args(self, extension_paths: Optional[List[str]] = None) -> List[str]:
        """Get Chrome launch arguments for loading extensions.

        Args:
            extension_paths: List of extension directory paths.
                           If None, downloads and uses default extensions.

        Returns:
            List of Chrome arguments for extension loading.
        """
        if extension_paths is None:
            extension_paths = self.ensure_extensions_downloaded()

        if not extension_paths:
            return []

        args = [
            '--enable-extensions',
            '--disable-extensions-file-access-check',
            '--disable-extensions-http-throttling',
        ]

        if extension_paths:
            args.append(f'--load-extension={",".join(extension_paths)}')

        return args

    def clear_cache(self) -> None:
        """Clear the extension cache directory."""
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Extension cache cleared")


# Global instance for convenience
_extension_manager: Optional[ExtensionManager] = None


def get_extension_manager() -> ExtensionManager:
    """Get the global ExtensionManager instance."""
    global _extension_manager
    if _extension_manager is None:
        _extension_manager = ExtensionManager()
    return _extension_manager
