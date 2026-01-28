"""
Configuration for browser automation including stealth mode and timeouts.

Ported from CAMEL-AI/Eigent project.
Enhanced with browser-use library anti-detection techniques.
"""

import os
import platform
from typing import Any, Dict, List, Optional


# Disabled Chrome features for stealth mode (from browser-use library)
CHROME_DISABLED_COMPONENTS = [
    # Playwright defaults
    'AcceptCHFrame',
    'AutoExpandDetailsElement',
    'AvoidUnnecessaryBeforeUnloadCheckSync',
    'CertificateTransparencyComponentUpdater',
    'DestroyProfileOnBrowserClose',
    'DialMediaRouteProvider',
    'ExtensionManifestV2Disabled',
    'GlobalMediaControls',
    'HttpsUpgrades',
    'ImprovedCookieControls',
    'LazyFrameLoading',
    'LensOverlay',
    'MediaRouter',
    'PaintHolding',
    'ThirdPartyStoragePartitioning',
    'Translate',
    # Anti-detection additions
    'AutomationControlled',
    'BackForwardCache',
    'OptimizationHints',
    'ProcessPerSiteUpToMainFrameThreshold',
    'InterestFeedContentSuggestions',
    'CalculateNativeWinOcclusion',
    'HeavyAdPrivacyMitigations',
    'PrivacySandboxSettings4',
    'AutofillServerCommunication',
    'CrashReporting',
    'OverscrollHistoryNavigation',
    'InfiniteSessionRestore',
]


class BrowserConfig:
    """Configuration class for browser settings including stealth mode and timeouts."""

    # Default timeout values (in milliseconds)
    DEFAULT_ACTION_TIMEOUT = 3000
    DEFAULT_SHORT_TIMEOUT = 5000  # Increased from 1000 to allow more time for new tab detection
    DEFAULT_NAVIGATION_TIMEOUT = 10000
    DEFAULT_NETWORK_IDLE_TIMEOUT = 5000
    DEFAULT_SCREENSHOT_TIMEOUT = 15000
    DEFAULT_PAGE_STABILITY_TIMEOUT = 1500
    DEFAULT_DOM_CONTENT_LOADED_TIMEOUT = 5000

    # Default action limits
    DEFAULT_MAX_SCROLL_AMOUNT = 5000  # Maximum scroll distance in pixels

    # Default config limits
    DEFAULT_MAX_LOG_LIMIT = 1000

    @staticmethod
    def get_timeout_config() -> Dict[str, int]:
        """Get timeout configuration with environment variable support."""
        return {
            'default_timeout': int(
                os.getenv(
                    'HYBRID_BROWSER_DEFAULT_TIMEOUT',
                    BrowserConfig.DEFAULT_ACTION_TIMEOUT,
                )
            ),
            'short_timeout': int(
                os.getenv(
                    'HYBRID_BROWSER_SHORT_TIMEOUT',
                    BrowserConfig.DEFAULT_SHORT_TIMEOUT,
                )
            ),
            'navigation_timeout': int(
                os.getenv(
                    'HYBRID_BROWSER_NAVIGATION_TIMEOUT',
                    BrowserConfig.DEFAULT_NAVIGATION_TIMEOUT,
                )
            ),
            'network_idle_timeout': int(
                os.getenv(
                    'HYBRID_BROWSER_NETWORK_IDLE_TIMEOUT',
                    BrowserConfig.DEFAULT_NETWORK_IDLE_TIMEOUT,
                )
            ),
            'screenshot_timeout': int(
                os.getenv(
                    'HYBRID_BROWSER_SCREENSHOT_TIMEOUT',
                    BrowserConfig.DEFAULT_SCREENSHOT_TIMEOUT,
                )
            ),
            'page_stability_timeout': int(
                os.getenv(
                    'HYBRID_BROWSER_PAGE_STABILITY_TIMEOUT',
                    BrowserConfig.DEFAULT_PAGE_STABILITY_TIMEOUT,
                )
            ),
            'dom_content_loaded_timeout': int(
                os.getenv(
                    'HYBRID_BROWSER_DOM_CONTENT_LOADED_TIMEOUT',
                    BrowserConfig.DEFAULT_DOM_CONTENT_LOADED_TIMEOUT,
                )
            ),
        }

    @staticmethod
    def get_action_limits() -> Dict[str, int]:
        """Get action limits configuration with environment variable support."""
        return {
            'max_scroll_amount': int(
                os.getenv(
                    'HYBRID_BROWSER_MAX_SCROLL_AMOUNT',
                    BrowserConfig.DEFAULT_MAX_SCROLL_AMOUNT,
                )
            ),
        }

    @staticmethod
    def get_log_limits() -> Dict[str, int]:
        """Get log limits configuration with environment variable support."""
        return {
            'max_log_limit': int(
                os.getenv(
                    'HYBRID_BROWSER_MAX_LOG_LIMIT',
                    BrowserConfig.DEFAULT_MAX_LOG_LIMIT,
                )
            ),
        }

    @staticmethod
    def get_action_timeout(override: Optional[int] = None) -> int:
        """Get action timeout with optional override."""
        if override is not None:
            return override
        return BrowserConfig.get_timeout_config()['default_timeout']

    @staticmethod
    def get_short_timeout(override: Optional[int] = None) -> int:
        """Get short timeout with optional override."""
        if override is not None:
            return override
        return BrowserConfig.get_timeout_config()['short_timeout']

    @staticmethod
    def get_navigation_timeout(override: Optional[int] = None) -> int:
        """Get navigation timeout with optional override."""
        if override is not None:
            return override
        return BrowserConfig.get_timeout_config()['navigation_timeout']

    @staticmethod
    def get_network_idle_timeout(override: Optional[int] = None) -> int:
        """Get network idle timeout with optional override."""
        if override is not None:
            return override
        return BrowserConfig.get_timeout_config()['network_idle_timeout']

    @staticmethod
    def get_max_scroll_amount(override: Optional[int] = None) -> int:
        """Get maximum scroll amount with optional override."""
        if override is not None:
            return override
        return BrowserConfig.get_action_limits()['max_scroll_amount']

    @staticmethod
    def get_max_log_limit(override: Optional[int] = None) -> int:
        """Get maximum log limit with optional override."""
        if override is not None:
            return override
        return BrowserConfig.get_log_limits()['max_log_limit']

    @staticmethod
    def get_screenshot_timeout(override: Optional[int] = None) -> int:
        """Get screenshot timeout with optional override."""
        if override is not None:
            return override
        return BrowserConfig.get_timeout_config()['screenshot_timeout']

    @staticmethod
    def get_page_stability_timeout(override: Optional[int] = None) -> int:
        """Get page stability timeout with optional override."""
        if override is not None:
            return override
        return BrowserConfig.get_timeout_config()['page_stability_timeout']

    @staticmethod
    def get_dom_content_loaded_timeout(override: Optional[int] = None) -> int:
        """Get DOM content loaded timeout with optional override."""
        if override is not None:
            return override
        return BrowserConfig.get_timeout_config()['dom_content_loaded_timeout']

    @staticmethod
    def get_launch_args() -> List[str]:
        """Get Chrome launch arguments for stealth mode.

        Based on browser-use library's comprehensive anti-detection args.
        These args hide automation indicators while maintaining browser functionality.
        """
        system = platform.system()

        args = [
            # Core anti-detection
            '--disable-blink-features=AutomationControlled',
            f'--disable-features={",".join(CHROME_DISABLED_COMPONENTS)}',

            # Hide automation indicators
            '--disable-infobars',  # Hide "Chrome is being controlled by automated software"
            '--disable-background-networking',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-back-forward-cache',  # Avoid surprises during navigation
            '--disable-breakpad',
            '--disable-client-side-phishing-detection',
            '--disable-component-extensions-with-background-pages',
            '--disable-component-update',
            '--disable-hang-monitor',
            '--disable-ipc-flooding-protection',
            '--disable-popup-blocking',
            '--disable-prompt-on-repost',
            '--disable-renderer-backgrounding',
            '--disable-sync',
            '--disable-domain-reliability',
            '--disable-field-trial-config',  # Disable field trials
            '--disable-window-activation',  # Don't steal focus
            '--disable-session-crashed-bubble',  # Prevent focus-stealing dialogs
            '--disable-restore-session-state',  # Prevent restore dialogs
            '--disable-features=GlobalMediaControls',  # Prevent media control popups

            # Performance and stability
            '--metrics-recording-only',
            '--no-first-run',
            '--no-default-browser-check',
            '--no-service-autorun',
            '--no-pings',

            # Network features
            '--enable-features=NetworkService,NetworkServiceInProcess',
            '--enable-network-information-downlink-max',

            # GPU/rendering - important for fingerprint
            '--test-type=gpu',

            # Extension support
            '--allow-legacy-extension-manifests',
            '--extensions-on-chrome-urls',
            '--disable-extensions-http-throttling',
            '--disable-default-apps',

            # Miscellaneous
            '--export-tagged-pdf',
            '--disable-search-engine-choice-screen',
            '--unsafely-disable-devtools-self-xss-warnings',
            '--allow-pre-commit-input',
            '--disable-focus-on-load',
            '--generate-pdf-document-outline',
            '--ash-no-nudges',
            '--hide-crash-restore-bubble',
            '--suppress-message-center-popups',
            '--disable-datasaver-prompt',
            '--disable-speech-synthesis-api',
            '--disable-speech-api',
            '--disable-print-preview',
            '--safebrowsing-disable-auto-update',
            '--disable-external-intent-requests',
            '--disable-desktop-notifications',
            '--noerrdialogs',
            '--silent-debugger-extension-api',
            '--log-level=2',

            # Simulate outdated browser (no auto-update prompts)
            '--simulate-outdated-no-au=Tue, 31 Dec 2099 23:59:59 GMT',
        ]

        # Platform-specific args
        if system == "Linux":
            # Linux/Docker specific
            args.extend([
                '--no-sandbox',
                '--disable-gpu-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--no-zygote',
            ])
        elif system == "Darwin":
            # macOS specific - minimal extra args
            pass
        elif system == "Windows":
            # Windows specific
            args.append('--disable-dev-shm-usage')

        return args

    @staticmethod
    def get_ignore_default_args() -> List[str]:
        """Get args that should be ignored from Playwright's defaults.

        These are args that Playwright adds by default that reveal automation
        or conflict with our custom settings.

        Based on browser-use library's configuration.
        """
        args = [
            # Critical! This is what shows the automation banner
            '--enable-automation',
            # Allow browser extensions (we load our own)
            '--disable-extensions',
            # Keep scrollbars visible for more realistic fingerprint
            '--hide-scrollbars',
            # We set our own --disable-features, ignore Playwright's version
            '--disable-features=AcceptCHFrame,AutoExpandDetailsElement,AvoidUnnecessaryBeforeUnloadCheckSync,CertificateTransparencyComponentUpdater,DeferRendererTasksAfterInput,DestroyProfileOnBrowserClose,DialMediaRouteProvider,ExtensionManifestV2Disabled,GlobalMediaControls,HttpsUpgrades,ImprovedCookieControls,LazyFrameLoading,LensOverlay,MediaRouter,PaintHolding,ThirdPartyStoragePartitioning,Translate',
        ]

        # On macOS, --no-sandbox is not supported and causes warnings
        if platform.system() == "Darwin":
            args.append('--no-sandbox')

        return args

    @staticmethod
    def get_context_options() -> Dict[str, Any]:
        """Get browser context options for stealth mode.

        Uses platform-appropriate user agent. Matching platform is important.
        """
        system = platform.system()

        if system == "Darwin":
            user_agent = (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/131.0.0.0 Safari/537.36'
            )
            sec_ch_ua_platform = '"macOS"'
        elif system == "Windows":
            user_agent = (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/131.0.0.0 Safari/537.36'
            )
            sec_ch_ua_platform = '"Windows"'
        else:
            user_agent = (
                'Mozilla/5.0 (X11; Linux x86_64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/131.0.0.0 Safari/537.36'
            )
            sec_ch_ua_platform = '"Linux"'

        return {
            'user_agent': user_agent,
            'viewport': {'width': 1920, 'height': 1080},
            'locale': 'en-US',
            'extra_http_headers': {
                'Sec-Ch-Ua-Platform': sec_ch_ua_platform,
            },
            # Don't set timezone/geolocation - let it use system defaults
        }

    @staticmethod
    def get_http_headers() -> Dict[str, str]:
        """Get HTTP headers for stealth mode."""
        system = platform.system()

        if system == "Darwin":
            sec_ch_ua_platform = '"macOS"'
        elif system == "Windows":
            sec_ch_ua_platform = '"Windows"'
        else:
            sec_ch_ua_platform = '"Linux"'

        return {
            'Accept': (
                'text/html,application/xhtml+xml,application/xml;q=0.9,'
                'image/avif,image/webp,image/apng,*/*;q=0.8,'
                'application/signed-exchange;v=b3;q=0.7'
            ),
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Cache-Control': 'max-age=0',
            'Sec-Ch-Ua': (
                '"Google Chrome";v="131", "Chromium";v="131", '
                '"Not=A?Brand";v="24"'
            ),
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': sec_ch_ua_platform,
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        }

    @staticmethod
    def get_stealth_script() -> Optional[str]:
        """Get JavaScript to inject for hiding automation detection.

        Returns None - stealth is fully handled by Chrome launch args
        (--disable-blink-features=AutomationControlled, etc.).
        JS injection can actually trigger detection.
        """
        return None

    @staticmethod
    def get_stealth_config(enable_extensions: bool = True) -> Dict[str, Any]:
        """Get stealth configuration.

        Args:
            enable_extensions: Whether to enable extension loading for anti-detection.
        """
        config = {
            'launch_args': BrowserConfig.get_launch_args(),
            'ignore_default_args': BrowserConfig.get_ignore_default_args(),
            'context_options': BrowserConfig.get_context_options(),
            'http_headers': BrowserConfig.get_http_headers(),
            'stealth_script': BrowserConfig.get_stealth_script(),
            'enable_extensions': enable_extensions,
        }

        # Add extension args if enabled
        if enable_extensions:
            from .extension_manager import get_extension_manager
            ext_manager = get_extension_manager()
            extension_paths = ext_manager.ensure_extensions_downloaded()
            if extension_paths:
                extension_args = ext_manager.get_extension_args(extension_paths)
                config['launch_args'].extend(extension_args)
                config['extension_paths'] = extension_paths

        return config

    @staticmethod
    def get_all_config() -> Dict[str, Any]:
        """Get all browser configuration including stealth, timeouts, and action limits."""
        return {
            'timeouts': BrowserConfig.get_timeout_config(),
            'action_limits': BrowserConfig.get_action_limits(),
            'stealth': BrowserConfig.get_stealth_config(),
        }


# ConfigLoader class for compatibility
class ConfigLoader:
    """Wrapper for BrowserConfig - maintained for backward compatibility."""

    @classmethod
    def get_browser_config(cls):
        """Get the BrowserConfig class."""
        return BrowserConfig

    @classmethod
    def get_stealth_config(cls):
        """Get the StealthConfig class (alias)."""
        return BrowserConfig

    @classmethod
    def get_timeout_config(cls) -> Dict[str, int]:
        """Get timeout configuration."""
        return BrowserConfig.get_timeout_config()

    @classmethod
    def get_action_timeout(cls, override: Optional[int] = None) -> int:
        """Get action timeout with optional override."""
        return BrowserConfig.get_action_timeout(override)

    @classmethod
    def get_short_timeout(cls, override: Optional[int] = None) -> int:
        """Get short timeout with optional override."""
        return BrowserConfig.get_short_timeout(override)

    @classmethod
    def get_navigation_timeout(cls, override: Optional[int] = None) -> int:
        """Get navigation timeout with optional override."""
        return BrowserConfig.get_navigation_timeout(override)

    @classmethod
    def get_network_idle_timeout(cls, override: Optional[int] = None) -> int:
        """Get network idle timeout with optional override."""
        return BrowserConfig.get_network_idle_timeout(override)

    @classmethod
    def get_max_scroll_amount(cls, override: Optional[int] = None) -> int:
        """Get maximum scroll amount with optional override."""
        return BrowserConfig.get_max_scroll_amount(override)

    @classmethod
    def get_max_log_limit(cls, override: Optional[int] = None) -> int:
        """Get maximum log limit with optional override."""
        return BrowserConfig.get_max_log_limit(override)

    @classmethod
    def get_screenshot_timeout(cls, override: Optional[int] = None) -> int:
        """Get screenshot timeout with optional override."""
        return BrowserConfig.get_screenshot_timeout(override)

    @classmethod
    def get_page_stability_timeout(cls, override: Optional[int] = None) -> int:
        """Get page stability timeout with optional override."""
        return BrowserConfig.get_page_stability_timeout(override)

    @classmethod
    def get_dom_content_loaded_timeout(cls, override: Optional[int] = None) -> int:
        """Get DOM content loaded timeout with optional override."""
        return BrowserConfig.get_dom_content_loaded_timeout(override)


# Backward compatibility aliases
StealthConfig = BrowserConfig
