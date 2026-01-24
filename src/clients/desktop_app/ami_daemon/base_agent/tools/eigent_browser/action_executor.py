"""
ActionExecutor - Executes high-level actions on a Playwright Page.

Ported from CAMEL-AI/Eigent project.
Supports actions based on element references [ref=eN].
"""

import asyncio
import datetime
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from .config_loader import ConfigLoader

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger(__name__)

# Debug mode - enabled via AMI_DEBUG environment variable
DEBUG_MODE = os.environ.get("AMI_DEBUG", "").lower() in ("1", "true", "yes")

# Debug screenshot directory
DEBUG_SCREENSHOT_DIR = Path.home() / ".ami" / "debug_screenshots"


class ActionExecutor:
    """Executes high-level actions (click, type, etc.) on a Playwright Page."""

    def __init__(
        self,
        page: "Page",
        session: Optional[Any] = None,
        default_timeout: Optional[int] = None,
        short_timeout: Optional[int] = None,
        max_scroll_amount: Optional[int] = None,
        debug: bool = False,
    ):
        self.page = page
        self.session = session  # Browser session instance for tab management
        self.debug = debug or DEBUG_MODE

        # Configure timeouts using the config file with optional overrides
        self.default_timeout = ConfigLoader.get_action_timeout(default_timeout)
        self.short_timeout = ConfigLoader.get_short_timeout(short_timeout)
        self.max_scroll_amount = ConfigLoader.get_max_scroll_amount(max_scroll_amount)

    def _debug_log(self, message: str, **kwargs) -> None:
        """Log debug message if debug mode is enabled."""
        if self.debug:
            extra_info = " ".join(f"{k}={v}" for k, v in kwargs.items()) if kwargs else ""
            msg = f"[DEBUG ActionExecutor] {message} {extra_info}".strip()
            print(msg)  # Print to terminal
            logger.info(msg)  # Also log to file

    async def _save_debug_screenshot(self, action_type: str, ref: str = "", error: str = "") -> Optional[str]:
        """Save a debug screenshot when an action fails."""
        if not self.debug:
            return None

        try:
            DEBUG_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{action_type}_{ref}_{error[:20]}.png".replace(" ", "_").replace(":", "_")
            filepath = DEBUG_SCREENSHOT_DIR / filename
            await self.page.screenshot(path=str(filepath))
            msg = f"[DEBUG] Screenshot saved: {filepath}"
            print(msg)
            logger.info(msg)
            return str(filepath)
        except Exception as e:
            logger.warning(f"Failed to save debug screenshot: {e}")
            return None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    async def execute(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an action and return detailed result information."""
        if not action:
            return {
                "success": False,
                "message": "No action to execute",
                "details": {},
            }

        action_type = action.get("type")
        if not action_type:
            return {
                "success": False,
                "message": "Error: action has no type",
                "details": {},
            }

        try:
            handler = {
                "click": self._click,
                "type": self._type,
                "select": self._select,
                "wait": self._wait,
                "extract": self._extract,
                "scroll": self._scroll,
                "enter": self._enter,
                "mouse_control": self._mouse_control,
                "mouse_drag": self._mouse_drag,
                "press_key": self._press_key,
                "navigate": self._navigate,
                "back": self._back,
                "forward": self._forward,
            }.get(action_type)

            if handler is None:
                return {
                    "success": False,
                    "message": f"Error: Unknown action type '{action_type}'",
                    "details": {"action_type": action_type},
                }

            result = await handler(action)
            return {
                "success": True,
                "message": result["message"],
                "details": result.get("details", {}),
            }
        except Exception as exc:
            logger.error(f"Action execution failed: {exc}")
            return {
                "success": False,
                "message": f"Error executing {action_type}: {exc}",
                "details": {"action_type": action_type, "error": str(exc)},
            }

    # ------------------------------------------------------------------
    # Internal handlers
    # ------------------------------------------------------------------
    async def _click(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle click actions with new tab support.

        Click strategy (following Eigent's design):
        1. Always try Ctrl+Click first - this opens links in new tabs
        2. If new tab opens → automatically switch to it (LLM sees new page)
        3. If no new tab (timeout) → click succeeded on same page
        4. If Ctrl+Click fails → fallback to normal force click
        """
        ref = action.get("ref")
        text = action.get("text")
        selector = action.get("selector")
        if not (ref or text or selector):
            return {
                "message": "Error: click requires ref/text/selector",
                "details": {"error": "missing_selector"},
            }

        # Build strategies in priority order
        strategies = []
        if ref:
            strategies.append(f"[aria-ref='{ref}']")
        if selector:
            strategies.append(selector)
        if text:
            strategies.append(f'text="{text}"')

        # Log current page info
        current_url = self.page.url
        self._debug_log(f"Click action started", url=current_url, ref=ref, text=text)

        details: Dict[str, Any] = {
            "ref": ref,
            "selector": selector,
            "text": text,
            "page_url": current_url,
            "strategies_tried": [],
            "successful_strategy": None,
            "click_method": None,
            "new_tab_created": False,
        }

        # Find the first valid selector
        found_selector = None
        for sel in strategies:
            count = await self.page.locator(sel).count()
            self._debug_log(f"Trying selector: {sel}", count=count)
            details['strategies_tried'].append({
                'selector': sel,
                'count': count,
            })
            if count > 0:
                found_selector = sel
                break

        if not found_selector:
            details['error'] = "element_not_found"
            details['failure_reason'] = "No matching element found with any strategy"

            # If searching by ref, collect available refs on the page for debugging
            if ref:
                available_refs = await self._get_available_refs_sample()
                details['available_refs_sample'] = available_refs
                self._debug_log(
                    f"Click failed: ref '{ref}' not found",
                    available_refs_count=available_refs.get('total_count', 0),
                    sample=available_refs.get('sample', [])[:5]
                )
            else:
                self._debug_log("Click failed: element not found", strategies=strategies)

            # If searching by text, try to find similar text on page
            if text:
                similar_texts = await self._find_similar_texts(text)
                if similar_texts:
                    details['similar_texts_on_page'] = similar_texts
                    self._debug_log(f"Similar texts found on page", similar=similar_texts[:3])

            await self._save_debug_screenshot("click", ref or text or "", "element_not_found")
            return {
                "message": f"Error: Click failed - element not found. Tried: {strategies}",
                "details": details,
            }

        element = self.page.locator(found_selector).first
        details['successful_strategy'] = found_selector

        # Get element info for debugging
        try:
            element_info = await self._get_element_debug_info(element)
            details['element_info'] = element_info
            self._debug_log(f"Element found", **element_info)
        except Exception as e:
            self._debug_log(f"Could not get element info: {e}")

        # Check for blocking modals before clicking
        modal_info = await self._detect_blocking_modal()
        if modal_info['has_modal']:
            details['blocking_modal'] = modal_info
            self._debug_log(f"Blocking modal detected", **modal_info)

        # Strategy 1: Always try Ctrl+Click first (Eigent's approach)
        # This handles links that open in new tabs AND regular clicks
        if self.session:
            try:
                self._debug_log("Attempting ctrl+click (always try first)")
                async with self.page.context.expect_page(
                    timeout=self.short_timeout
                ) as new_page_info:
                    await element.click(modifiers=["ControlOrMeta"])
                # New tab was created
                new_page = await new_page_info.value
                await new_page.wait_for_load_state('domcontentloaded')
                new_tab_index = await self.session.register_page(new_page)
                if new_tab_index is not None:
                    await self.session.switch_to_tab(new_tab_index)
                    self.page = new_page
                details.update(
                    {
                        "click_method": "ctrl_click_new_tab",
                        "new_tab_created": True,
                        "new_tab_index": new_tab_index,
                    }
                )
                self._debug_log("Ctrl+click opened new tab, auto-switched", tab=new_tab_index)
                return {
                    "message": f"Clicked element, opened in new tab {new_tab_index}",
                    "details": details,
                }
            except asyncio.TimeoutError:
                # No new tab was opened - Ctrl+Click may not have triggered JS handlers
                # Fall through to try normal click for JavaScript-based navigation links
                self._debug_log("Ctrl+click timeout - no new tab opened (likely SPA link)")
                details['strategies_tried'].append({
                    'selector': found_selector,
                    'method': 'ctrl_click',
                    'result': 'timeout_no_new_tab',
                    'reason': 'SPA/JavaScript link does not open new tab with Ctrl+Click',
                })
            except Exception as e:
                error_msg = str(e)
                failure_reason = self._analyze_click_error(error_msg)
                self._debug_log(f"Ctrl+click failed: {failure_reason}", error=error_msg[:200])
                details['strategies_tried'].append({
                    'selector': found_selector,
                    'method': 'ctrl_click',
                    'error': error_msg[:500],
                    'failure_reason': failure_reason,
                })
                # Fall through to fallback

        # Strategy 2: Fallback to normal force click if ctrl+click fails
        try:
            self._debug_log("Attempting force click (fallback)")
            await element.click(force=True, timeout=self.default_timeout)
            details["click_method"] = "force_click"

            # Check if URL changed after click
            new_url = self.page.url
            url_changed = new_url != current_url
            details['url_changed'] = url_changed
            details['new_url'] = new_url if url_changed else None

            self._debug_log("Force click succeeded", url_changed=url_changed)
            return {
                "message": f"Clicked element (fallback): {found_selector}",
                "details": details,
            }
        except Exception as e:
            error_msg = str(e)
            failure_reason = self._analyze_click_error(error_msg)
            self._debug_log(f"Force click failed: {failure_reason}", error=error_msg[:200])
            await self._save_debug_screenshot("click", ref or text or "", "all_failed")
            details["click_method"] = "all_failed"
            details["error"] = error_msg[:500]
            details["failure_reason"] = failure_reason
            return {
                "message": f"Error: Click failed - {failure_reason}",
                "details": details,
            }

    async def _get_element_debug_info(self, element) -> Dict[str, Any]:
        """Get debug information about an element."""
        info = {}
        try:
            # Get bounding box
            box = await element.bounding_box()
            if box:
                info['bounding_box'] = {
                    'x': round(box['x'], 1),
                    'y': round(box['y'], 1),
                    'width': round(box['width'], 1),
                    'height': round(box['height'], 1),
                }
                info['is_visible'] = box['width'] > 0 and box['height'] > 0
            else:
                info['is_visible'] = False
                info['bounding_box'] = None

            # Check if element is in viewport
            if box:
                viewport = self.page.viewport_size
                if viewport:
                    in_viewport = (
                        box['x'] >= 0 and
                        box['y'] >= 0 and
                        box['x'] + box['width'] <= viewport['width'] and
                        box['y'] + box['height'] <= viewport['height']
                    )
                    info['in_viewport'] = in_viewport

            # Get tag name and some attributes
            tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
            info['tag_name'] = tag_name

            # Get href if it's a link
            if tag_name == 'a':
                href = await element.get_attribute('href')
                info['href'] = href

            # Check if element is enabled/disabled
            is_disabled = await element.is_disabled()
            info['is_disabled'] = is_disabled

        except Exception as e:
            info['error'] = str(e)

        return info

    async def _detect_blocking_modal(self) -> Dict[str, Any]:
        """Detect if there's a modal/dialog blocking the page."""
        modal_selectors = [
            '[role="dialog"]',
            '[role="alertdialog"]',
            '[aria-modal="true"]',
            '.modal',
            '.popup',
            '[data-state="open"]',
        ]

        result = {
            'has_modal': False,
            'modal_type': None,
            'modal_selector': None,
        }

        for selector in modal_selectors:
            try:
                count = await self.page.locator(selector).count()
                if count > 0:
                    # Check if the modal is actually visible
                    modal = self.page.locator(selector).first
                    is_visible = await modal.is_visible()
                    if is_visible:
                        result['has_modal'] = True
                        result['modal_selector'] = selector

                        # Try to get modal info
                        try:
                            box = await modal.bounding_box()
                            if box:
                                result['modal_size'] = {
                                    'width': round(box['width'], 1),
                                    'height': round(box['height'], 1),
                                }
                        except:
                            pass

                        # Check for close button
                        close_selectors = [
                            f'{selector} button[aria-label*="close"]',
                            f'{selector} button[aria-label*="Close"]',
                            f'{selector} button:has-text("×")',
                            f'{selector} button:has-text("Close")',
                            f'{selector} [aria-label*="dismiss"]',
                        ]
                        for close_sel in close_selectors:
                            try:
                                close_count = await self.page.locator(close_sel).count()
                                if close_count > 0:
                                    result['has_close_button'] = True
                                    result['close_button_selector'] = close_sel
                                    break
                            except:
                                pass

                        break
            except:
                pass

        return result

    def _analyze_click_error(self, error_msg: str) -> str:
        """Analyze click error message and return a human-readable reason."""
        error_lower = error_msg.lower()

        if "intercepts pointer events" in error_lower:
            # Extract the intercepting element info
            if "dialog" in error_lower:
                return "BLOCKED_BY_MODAL: A dialog/modal is blocking the element"
            elif "overlay" in error_lower or "backdrop" in error_lower:
                return "BLOCKED_BY_OVERLAY: An overlay/backdrop is blocking the element"
            else:
                return "BLOCKED_BY_ELEMENT: Another element is blocking the click target"

        if "timeout" in error_lower:
            if "waiting for element" in error_lower:
                return "TIMEOUT_ELEMENT_NOT_READY: Element not ready within timeout"
            elif "waiting for event" in error_lower:
                return "TIMEOUT_NO_NEW_TAB: Ctrl+click didn't open new tab (likely SPA)"
            else:
                return "TIMEOUT_GENERAL: Operation timed out"

        if "element is not visible" in error_lower:
            return "ELEMENT_NOT_VISIBLE: Element exists but is not visible"

        if "element is not enabled" in error_lower or "disabled" in error_lower:
            return "ELEMENT_DISABLED: Element is disabled"

        if "detached" in error_lower:
            return "ELEMENT_DETACHED: Element was removed from DOM"

        if "outside" in error_lower and "viewport" in error_lower:
            return "ELEMENT_OUTSIDE_VIEWPORT: Element is outside the visible area"

        return f"UNKNOWN_ERROR: {error_msg[:100]}"

    async def _get_available_refs_sample(self) -> Dict[str, Any]:
        """Get a sample of available aria-ref elements on the page for debugging."""
        result = {
            'total_count': 0,
            'sample': [],
            'ref_range': None,
        }

        try:
            # Get all elements with aria-ref attribute
            refs_data = await self.page.evaluate("""
                () => {
                    const elements = document.querySelectorAll('[aria-ref]');
                    const refs = [];
                    const allRefNumbers = [];

                    elements.forEach((el, idx) => {
                        const ref = el.getAttribute('aria-ref');
                        const refNum = parseInt(ref.replace('e', ''), 10);
                        if (!isNaN(refNum)) {
                            allRefNumbers.push(refNum);
                        }

                        // Only collect sample (first 20 and last 10)
                        if (idx < 20 || idx >= elements.length - 10) {
                            refs.push({
                                ref: ref,
                                tag: el.tagName.toLowerCase(),
                                text: (el.textContent || '').trim().substring(0, 50),
                                visible: el.offsetParent !== null,
                            });
                        }
                    });

                    // Sort ref numbers to get range
                    allRefNumbers.sort((a, b) => a - b);

                    return {
                        total: elements.length,
                        sample: refs,
                        minRef: allRefNumbers.length > 0 ? allRefNumbers[0] : null,
                        maxRef: allRefNumbers.length > 0 ? allRefNumbers[allRefNumbers.length - 1] : null,
                    };
                }
            """)

            result['total_count'] = refs_data.get('total', 0)
            result['sample'] = refs_data.get('sample', [])
            if refs_data.get('minRef') is not None:
                result['ref_range'] = f"e{refs_data['minRef']} - e{refs_data['maxRef']}"

        except Exception as e:
            result['error'] = str(e)
            self._debug_log(f"Failed to get available refs: {e}")

        return result

    async def _find_similar_texts(self, target_text: str, max_results: int = 5) -> list:
        """Find similar text content on the page when exact match fails."""
        try:
            # Normalize the target text
            target_lower = target_text.lower().strip()

            # Search for elements containing parts of the text
            similar_texts = await self.page.evaluate("""
                (args) => {
                    const { targetLower, maxResults } = args;
                    const results = [];

                    // Get all text-containing elements
                    const textElements = document.querySelectorAll('a, button, [role="button"], [role="link"], h1, h2, h3, h4, p, span, div');

                    for (const el of textElements) {
                        if (results.length >= maxResults) break;

                        const text = (el.textContent || '').trim();
                        if (!text || text.length > 200) continue;

                        const textLower = text.toLowerCase();

                        // Check for partial matches
                        const targetWords = targetLower.split(/\\s+/).filter(w => w.length > 2);
                        const matchedWords = targetWords.filter(word => textLower.includes(word));

                        if (matchedWords.length > 0 && matchedWords.length >= targetWords.length * 0.3) {
                            results.push({
                                text: text.substring(0, 100),
                                tag: el.tagName.toLowerCase(),
                                ref: el.getAttribute('aria-ref'),
                                matchedWords: matchedWords,
                                matchRatio: matchedWords.length / targetWords.length,
                            });
                        }
                    }

                    // Sort by match ratio
                    results.sort((a, b) => b.matchRatio - a.matchRatio);

                    return results.slice(0, maxResults);
                }
            """, {'targetLower': target_lower, 'maxResults': max_results})

            return similar_texts

        except Exception as e:
            self._debug_log(f"Failed to find similar texts: {e}")
            return []

    async def _type(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle typing text into input fields."""
        ref = action.get("ref")
        selector = action.get("selector")
        text = action.get("text", "")
        if not (ref or selector):
            return {
                "message": "Error: type requires ref/selector",
                "details": {"error": "missing_selector"},
            }

        target = selector or f"[aria-ref='{ref}']"
        details = {
            "ref": ref,
            "selector": selector,
            "target": target,
            "text": text,
            "text_length": len(text),
        }

        try:
            await self.page.fill(target, text, timeout=self.short_timeout)
            return {
                "message": f"Typed '{text}' into {target}",
                "details": details,
            }
        except Exception as exc:
            details["error"] = str(exc)
            return {"message": f"Type failed: {exc}", "details": details}

    async def _select(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle selecting options from dropdowns."""
        ref = action.get("ref")
        selector = action.get("selector")
        value = action.get("value", "")
        if not (ref or selector):
            return {
                "message": "Error: select requires ref/selector",
                "details": {"error": "missing_selector"},
            }

        target = selector or f"[aria-ref='{ref}']"
        details = {
            "ref": ref,
            "selector": selector,
            "target": target,
            "value": value,
        }

        try:
            await self.page.select_option(
                target, value, timeout=self.default_timeout
            )
            return {
                "message": f"Selected '{value}' in {target}",
                "details": details,
            }
        except Exception as exc:
            details["error"] = str(exc)
            return {"message": f"Select failed: {exc}", "details": details}

    async def _wait(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle wait actions."""
        details: Dict[str, Any] = {
            "wait_type": None,
            "timeout": None,
            "selector": None,
        }

        if "timeout" in action:
            ms = int(action["timeout"])
            details["wait_type"] = "timeout"
            details["timeout"] = ms
            await asyncio.sleep(ms / 1000)
            return {"message": f"Waited {ms}ms", "details": details}
        if "selector" in action:
            sel = action["selector"]
            details["wait_type"] = "selector"
            details["selector"] = sel
            await self.page.wait_for_selector(
                sel, timeout=self.default_timeout
            )
            return {"message": f"Waited for {sel}", "details": details}
        return {
            "message": "Error: wait requires timeout/selector",
            "details": details,
        }

    async def _extract(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle text extraction from elements."""
        ref = action.get("ref")
        if not ref:
            return {
                "message": "Error: extract requires ref",
                "details": {"error": "missing_ref"},
            }

        target = f"[aria-ref='{ref}']"
        details = {"ref": ref, "target": target}

        await self.page.wait_for_selector(target, timeout=self.default_timeout)
        txt = await self.page.text_content(target)

        details["extracted_text"] = txt
        details["text_length"] = len(txt) if txt else 0

        return {
            "message": f"Extracted: {txt[:100] if txt else 'None'}",
            "details": details,
        }

    async def _scroll(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle page scrolling with safe parameter validation."""
        direction = action.get("direction", "down")
        amount = action.get("amount", 300)

        details = {
            "direction": direction,
            "requested_amount": amount,
            "actual_amount": None,
            "scroll_offset": None,
        }

        # Validate inputs to prevent injection
        if direction not in ("up", "down"):
            return {
                "message": "Error: direction must be 'up' or 'down'",
                "details": details,
            }

        try:
            # Safely convert amount to integer and clamp to reasonable range
            amount_int = int(amount)
            amount_int = max(
                -self.max_scroll_amount,
                min(self.max_scroll_amount, amount_int),
            )  # Clamp to max_scroll_amount range
            details["actual_amount"] = amount_int
        except (ValueError, TypeError):
            return {
                "message": "Error: amount must be a valid number",
                "details": details,
            }

        # Use safe evaluation with bound parameters
        scroll_offset = amount_int if direction == "down" else -amount_int
        details["scroll_offset"] = scroll_offset

        await self.page.evaluate(
            "offset => window.scrollBy(0, offset)", scroll_offset
        )
        await asyncio.sleep(0.5)
        return {
            "message": f"Scrolled {direction} by {abs(amount_int)}px",
            "details": details,
        }

    async def _enter(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle Enter key press on the currently focused element."""
        details = {"action_type": "enter", "target": "focused_element"}

        # Press Enter on whatever element currently has focus
        await self.page.keyboard.press("Enter")
        return {
            "message": "Pressed Enter on focused element",
            "details": details,
        }

    async def _mouse_control(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle mouse_control action based on the coordinates"""
        control = action.get("control", "click")
        x_coord = action.get("x", 0)
        y_coord = action.get("y", 0)

        details = {
            "action_type": "mouse_control",
            "target": f"coordinates : ({x_coord}, {y_coord})",
        }
        try:
            if not self._valid_coordinates(x_coord, y_coord):
                raise ValueError(
                    "Invalid coordinates, outside viewport bounds :"
                    f"({x_coord}, {y_coord})"
                )
            if control == "click":
                await self.page.mouse.click(x_coord, y_coord)
                message = "Action 'click' performed on the target"
            elif control == "right_click":
                await self.page.mouse.click(
                    x_coord, y_coord, button="right"
                )
                message = "Action 'right_click' performed on the target"
            elif control == "dblclick":
                await self.page.mouse.dblclick(x_coord, y_coord)
                message = "Action 'dblclick' performed on the target"
            else:
                return {
                    "message": f"Invalid control action {control}",
                    "details": details,
                }

            return {"message": message, "details": details}
        except Exception as e:
            return {"message": f"Action failed: {e}", "details": details}

    async def _mouse_drag(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle mouse_drag action using ref IDs"""
        from_ref = action.get("from_ref")
        to_ref = action.get("to_ref")

        if not from_ref or not to_ref:
            return {
                "message": "Error: mouse_drag requires from_ref and to_ref",
                "details": {"error": "missing_refs"},
            }

        from_selector = f"[aria-ref='{from_ref}']"
        to_selector = f"[aria-ref='{to_ref}']"

        details = {
            "action_type": "mouse_drag",
            "from_ref": from_ref,
            "to_ref": to_ref,
            "from_selector": from_selector,
            "to_selector": to_selector,
        }

        try:
            # Get the source element
            from_element = self.page.locator(from_selector)
            from_count = await from_element.count()
            if from_count == 0:
                raise ValueError(
                    f"Source element with ref '{from_ref}' not found"
                )

            # Get the target element
            to_element = self.page.locator(to_selector)
            to_count = await to_element.count()
            if to_count == 0:
                raise ValueError(
                    f"Target element with ref '{to_ref}' not found"
                )

            # Get bounding boxes
            from_box = await from_element.first.bounding_box()
            to_box = await to_element.first.bounding_box()

            if not from_box:
                raise ValueError(
                    f"Could not get bounding box for source element "
                    f"with ref '{from_ref}'"
                )
            if not to_box:
                raise ValueError(
                    f"Could not get bounding box for target element "
                    f"with ref '{to_ref}'"
                )

            # Calculate center coordinates
            from_x = from_box['x'] + from_box['width'] / 2
            from_y = from_box['y'] + from_box['height'] / 2
            to_x = to_box['x'] + to_box['width'] / 2
            to_y = to_box['y'] + to_box['height'] / 2

            details.update(
                {
                    "from_coordinates": {"x": from_x, "y": from_y},
                    "to_coordinates": {"x": to_x, "y": to_y},
                }
            )

            # Perform the drag operation
            await self.page.mouse.move(from_x, from_y)
            await self.page.mouse.down()
            # Destination coordinates
            await self.page.mouse.move(to_x, to_y)
            await self.page.mouse.up()

            return {
                "message": (
                    f"Dragged from element [ref={from_ref}] to element "
                    f"[ref={to_ref}]"
                ),
                "details": details,
            }
        except Exception as e:
            return {"message": f"Action failed: {e}", "details": details}

    async def _press_key(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle press_key action by combining the keys in a list."""
        keys = action.get("keys", [])
        if not keys:
            return {
                "message": "Error: No keys specified",
                "details": {"action_type": "press_key", "keys": ""},
            }
        combined_keys = "+".join(keys)
        details = {"action_type": "press_key", "keys": combined_keys}
        try:
            await self.page.keyboard.press(combined_keys)
            return {
                "message": "Pressed keys in the browser",
                "details": details,
            }
        except Exception as e:
            return {"message": f"Action failed: {e}", "details": details}

    async def _navigate(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle navigation to a URL."""
        url = action.get("url")
        if not url:
            return {
                "message": "Error: navigate requires url",
                "details": {"error": "missing_url"},
            }

        details = {"action_type": "navigate", "url": url}
        try:
            await self.page.goto(url, timeout=ConfigLoader.get_navigation_timeout())
            await self.page.wait_for_load_state('domcontentloaded')
            return {
                "message": f"Navigated to {url}",
                "details": details,
            }
        except Exception as e:
            details["error"] = str(e)
            return {"message": f"Navigation failed: {e}", "details": details}

    async def _back(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle browser back navigation."""
        details = {"action_type": "back"}
        try:
            await self.page.go_back(timeout=ConfigLoader.get_navigation_timeout())
            return {
                "message": "Navigated back",
                "details": details,
            }
        except Exception as e:
            details["error"] = str(e)
            return {"message": f"Back navigation failed: {e}", "details": details}

    async def _forward(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle browser forward navigation."""
        details = {"action_type": "forward"}
        try:
            await self.page.go_forward(timeout=ConfigLoader.get_navigation_timeout())
            return {
                "message": "Navigated forward",
                "details": details,
            }
        except Exception as e:
            details["error"] = str(e)
            return {"message": f"Forward navigation failed: {e}", "details": details}

    # utilities
    async def _wait_dom_stable(self) -> None:
        """Wait for DOM to become stable before executing actions."""
        try:
            # Wait for basic DOM content loading
            await self.page.wait_for_load_state(
                'domcontentloaded', timeout=self.short_timeout
            )

            # Try to wait for network idle briefly
            try:
                await self.page.wait_for_load_state(
                    'networkidle', timeout=self.short_timeout
                )
            except Exception:
                pass  # Network idle is optional

        except Exception:
            pass  # Don't fail if wait times out

    def _valid_coordinates(self, x_coord: float, y_coord: float) -> bool:
        """Validate given coordinates against viewport bounds."""
        viewport = self.page.viewport_size
        if not viewport:
            raise ValueError("Viewport size not available from current page.")

        return (
            0 <= x_coord <= viewport['width']
            and 0 <= y_coord <= viewport['height']
        )

    # static helpers
    @staticmethod
    def should_update_snapshot(action: Dict[str, Any]) -> bool:
        """Determine if an action requires a snapshot update."""
        change_types = {
            "click",
            "type",
            "select",
            "scroll",
            "navigate",
            "enter",
            "back",
            "forward",
        }
        return action.get("type") in change_types
