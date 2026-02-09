"""
ActionExecutor - Executes high-level actions on a Playwright Page.

Ported from CAMEL-AI/Eigent project.
Supports actions based on element references [ref=eN].
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, Optional

from .config_loader import ConfigLoader

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Executes high-level actions (click, type, etc.) on a Playwright Page."""

    def __init__(
        self,
        page: "Page",
        session: Optional[Any] = None,
        default_timeout: Optional[int] = None,
        short_timeout: Optional[int] = None,
        max_scroll_amount: Optional[int] = None,
    ):
        self.page = page
        self.session = session  # Browser session instance for tab management

        # Configure timeouts using the config file with optional overrides
        self.default_timeout = ConfigLoader.get_action_timeout(default_timeout)
        self.short_timeout = ConfigLoader.get_short_timeout(short_timeout)
        self.max_scroll_amount = ConfigLoader.get_max_scroll_amount(max_scroll_amount)

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
        2. If new tab opens → automatically switch to it
        3. If no new tab (timeout) → click succeeded on same page
        4. If Ctrl+Click fails → fallback to force click
        """
        ref = action.get("ref")

        if not ref:
            return {
                "message": "Error: click requires ref",
                "details": {"error": "missing_ref"},
            }

        target = f"[aria-ref='{ref}']"
        strategies = [target]

        details: Dict[str, Any] = {
            "ref": ref,
            "strategies_tried": [],
            "successful_strategy": None,
            "click_method": None,
            "new_tab_created": False,
        }

        # Find the first valid selector
        found_selector = None
        for sel in strategies:
            if await self.page.locator(sel).count() > 0:
                found_selector = sel
                break

        if not found_selector:
            details['error'] = "element_not_found"
            return {
                "message": "Error: Click failed, element not found",
                "details": details,
            }

        element = self.page.locator(found_selector).first
        details['successful_strategy'] = found_selector

        click_target = element
        click_target_kind = "element"

        # Log current tab count before click
        if self.session:
            tab_count_before = len(self.session._pages)
            logger.debug(f"Click starting: selector={found_selector}, tabs_before={tab_count_before}, short_timeout={self.short_timeout}ms")

        # Collect extra element diagnostics (best-effort) before click
        element_diag = None
        try:
            element_diag = await element.evaluate(
                """el => {
                    const text = (el.innerText || el.textContent || '').trim();
                    const rect = el.getBoundingClientRect();
                    const inViewport =
                        rect.width > 0 &&
                        rect.height > 0 &&
                        rect.bottom >= 0 &&
                        rect.right >= 0 &&
                        rect.top <= (window.innerHeight || document.documentElement.clientHeight) &&
                        rect.left <= (window.innerWidth || document.documentElement.clientWidth);
                    const closestLink = el.closest('a');
                    const descendantLinks = el.querySelectorAll('a[href]');
                    const descendantLink = descendantLinks.length === 1 ? descendantLinks[0] : null;
                    const descendantText = descendantLink ? (descendantLink.innerText || descendantLink.textContent || '').trim() : '';
                    const onclickAttr = el.getAttribute('onclick');
                    const onclickProp = typeof el.onclick === 'function';
                    return {
                        tag: el.tagName,
                        href: el.getAttribute('href'),
                        closestHref: closestLink ? closestLink.getAttribute('href') : null,
                        role: el.getAttribute('role'),
                        ariaLabel: el.getAttribute('aria-label'),
                        text: text ? text.slice(0, 200) : '',
                        descendantHref: descendantLink ? descendantLink.getAttribute('href') : null,
                        descendantText: descendantText ? descendantText.slice(0, 200) : '',
                        descendantCount: descendantLinks.length,
                        onclick: !!onclickAttr || onclickProp,
                        rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
                        inViewport
                    };
                }"""
            )
            element_diag.update({
                "visible": await element.is_visible(),
                "enabled": await element.is_enabled(),
                "page_url": self.page.url if self.page else None,
            })
            logger.debug(f"Click element diagnostics: {element_diag}")
        except Exception as e:
            logger.debug(f"Click diagnostics failed: {e}")

        # Conservative redirect: if a container wraps a single link, prefer that link
        try:
            if element_diag:
                tag = element_diag.get("tag")
                href = element_diag.get("href")
                closest_href = element_diag.get("closestHref")
                role = element_diag.get("role")
                has_onclick = element_diag.get("onclick")
                descendant_count = element_diag.get("descendantCount")
                descendant_href = element_diag.get("descendantHref")
                source_text = (element_diag.get("text") or "").strip()
                descendant_text = (element_diag.get("descendantText") or "").strip()
                role_is_link = (role or "").lower() == "link"
                if (
                    tag in {"LI", "DIV", "SPAN"}
                    and not href
                    and not closest_href
                    and not role_is_link
                    and not has_onclick
                    and descendant_count == 1
                    and descendant_href
                    and source_text
                    and descendant_text
                    and (source_text.lower() in descendant_text.lower() or descendant_text.lower() in source_text.lower())
                ):
                    descendant_locator = element.locator(":scope a[href]").first
                    if await descendant_locator.count() > 0 and await descendant_locator.is_visible() and await descendant_locator.is_enabled():
                        click_target = descendant_locator
                        click_target_kind = "descendant_a"
                        details["redirected_click_target"] = click_target_kind
                        details["descendant_href"] = descendant_href
                        details["descendant_text"] = descendant_text[:200]
                        logger.debug(f"Redirecting click to descendant <a>: href={descendant_href}")
        except Exception as e:
            logger.debug(f"Descendant link check failed: {e}")

        # Strategy 1: Ctrl+Click (always try first)
        try:
            if self.session:
                context = self.page.context
                context_pages_before = len(context.pages)
                logger.debug(f"Attempting Ctrl+Click with expect_page... context={context}, context_pages_before={context_pages_before}")
                t0 = time.perf_counter()
                async with context.expect_page(
                    timeout=self.short_timeout
                ) as new_page_info:
                    await click_target.click(modifiers=["ControlOrMeta"])
                    logger.debug("Click executed, waiting for page event...")
                # New tab was created
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                logger.debug("expect_page succeeded - new tab detected")
                new_page = await new_page_info.value
                await new_page.wait_for_load_state('domcontentloaded')
                new_tab_index = await self.session.register_page(new_page)
                if new_tab_index is not None:
                    await self.session.switch_to_tab(new_tab_index)
                    # Bug #20 fix: Update self.page from session to ensure consistency
                    # switch_to_tab creates a new ActionExecutor in session.executor,
                    # but we're still in this method, so sync our page reference
                    self.page = self.session._page
                tab_count_after = len(self.session._pages)
                logger.debug(f"New tab registered: {new_tab_index}, tabs_after={tab_count_after}")
                details.update({
                    "click_method": "ctrl_click_new_tab",
                    "new_tab_created": True,
                    "new_tab_index": new_tab_index,
                    "ctrl_click_elapsed_ms": elapsed_ms,
                })
                return {
                    "message": f"Clicked element, opened in new tab {new_tab_index}",
                    "details": details,
                }
            else:
                t0 = time.perf_counter()
                await click_target.click(modifiers=["ControlOrMeta"])
                details["click_method"] = "ctrl_click_no_session"
                details["ctrl_click_elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
                return {
                    "message": f"Clicked element (ctrl click): {found_selector}",
                    "details": details,
                }
        except (asyncio.TimeoutError, TimeoutError) as e:
            # No new tab was opened within timeout, click may have still worked
            # Note: Playwright raises TimeoutError (builtin), not asyncio.TimeoutError
            elapsed_ms = None
            try:
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
            except Exception:
                pass
            tab_count_after = len(self.session._pages) if self.session else 0
            context_pages_after = len(self.page.context.pages) if self.page else 0
            logger.debug(f"[TIMEOUT CAUGHT] expect_page timeout after {self.short_timeout}ms (elapsed={elapsed_ms}ms) - session_tabs={tab_count_after}, context_pages={context_pages_after}")
            details["click_method"] = "ctrl_click_same_tab"
            if elapsed_ms is not None:
                details["ctrl_click_elapsed_ms"] = elapsed_ms
            return {
                "message": f"Clicked element (same tab): {found_selector}",
                "details": details,
            }
        except Exception as e:
            # Log full exception info to understand why it's not caught above
            logger.debug(f"[EXCEPTION CAUGHT] type={type(e)}, mro={type(e).__mro__}, name={type(e).__name__}: {e}")
            details['strategies_tried'].append({
                'selector': found_selector,
                'method': 'ctrl_click',
                'error': str(e),
            })
            # Fall through to fallback

        # Strategy 2: Force click as fallback
        logger.debug("Falling back to force click...")
        try:
            await click_target.click(force=True, timeout=self.default_timeout)
            tab_count_after = len(self.session._pages) if self.session else 0
            logger.debug(f"Force click succeeded, tabs_after={tab_count_after}")
            details["click_method"] = "force_click"
            return {
                "message": f"Clicked element (force): {found_selector}",
                "details": details,
            }
        except Exception as e:
            logger.debug(f"Force click also failed: {e}")
            details["click_method"] = "all_failed"
            details["error"] = str(e)
            return {
                "message": f"Error: All click strategies failed for {found_selector}",
                "details": details,
            }

    async def _type(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Handle typing text into input fields."""
        ref = action.get("ref")
        text = action.get("text", "")

        if not ref:
            return {
                "message": "Error: type requires ref",
                "details": {"error": "missing_ref"},
            }

        target = f"[aria-ref='{ref}']"
        details = {
            "ref": ref,
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
        value = action.get("value", "")

        if not ref:
            return {
                "message": "Error: select requires ref",
                "details": {"error": "missing_ref"},
            }

        target = f"[aria-ref='{ref}']"
        details = {
            "ref": ref,
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
