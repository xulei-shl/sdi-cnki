"""Faithful reproduction of src.utils.playwright_page helpers from the prototype."""

from __future__ import annotations

import logging
import time as _time
from typing import Optional

from playwright.sync_api import Locator, Page


def click_first_available(
    page: Page,
    selectors: list[str],
    timeout_ms: int = 500,
) -> bool:
    """Click the first visible/interactable element from a selector list."""
    for selector in selectors:
        for attempt in range(2):
            try:
                locator = page.locator(selector).first
                if locator.count() > 0:
                    locator.wait_for(state="visible", timeout=timeout_ms)
                    locator.click()
                    return True
            except Exception:
                _time.sleep(0.2)
    return False


def click_first_available_on_page(
    page: Page,
    selectors: list[str],
    timeout_ms: int = 500,
) -> bool:
    """Same as click_first_available but accepts explicit page."""
    return click_first_available(page, selectors, timeout_ms)


def disable_checkbox(
    page: Page,
    selector: str,
    logger: Optional[logging.Logger] = None,
    verify_unchecked: bool = True,
) -> None:
    """Uncheck a checkbox, with JS fallback."""
    log = logger or logging.getLogger(__name__)
    try:
        cb = page.locator(selector).first
        if cb.count() == 0:
            return
        if not cb.is_checked():
            return
        try:
            cb.uncheck(force=True)
        except Exception as e:
            log.debug(f"disable_checkbox: force uncheck failed for '{selector}': {e}")
            cb.evaluate("(el) => { el.checked = false; el.dispatchEvent(new Event('change', {bubbles: true})); }")
        if verify_unchecked:
            _time.sleep(0.1)
    except Exception as e:
        log.debug(f"disable_checkbox: error for '{selector}': {e}")


def enable_checkbox(
    page: Page,
    selector: str,
    logger: Optional[logging.Logger] = None,
) -> None:
    """Check a checkbox, with JS fallback."""
    log = logger or logging.getLogger(__name__)
    try:
        cb = page.locator(selector).first
        if cb.count() == 0:
            return
        if cb.is_checked():
            return
        try:
            cb.check(force=True)
        except Exception as e:
            log.debug(f"enable_checkbox: force check failed for '{selector}': {e}")
            cb.evaluate("""
                (el) => {
                    el.checked = true;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    el.dispatchEvent(new Event('click', {bubbles: true}));
                }
            """)
    except Exception as e:
        log.debug(f"enable_checkbox: error for '{selector}': {e}")


def first_visible_locator(
    page: Page,
    selectors: list[str],
    timeout_ms: int = 500,
) -> Optional[Locator]:
    """Return the first visible locator from a selector list."""
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0:
                locator.wait_for(state="visible", timeout=timeout_ms)
                return locator
        except Exception:
            continue
    return None


def set_input_value(locator: Locator, value: str) -> None:
    """Set an input element's value."""
    try:
        locator.fill(value)
    except Exception:
        try:
            locator.evaluate(f"(el) => {{ el.value = '{value}'; el.dispatchEvent(new Event('input', {{bubbles: true}})); }}")
        except Exception:
            pass


def wait_for_any_selector(
    page: Page,
    selectors: list[str],
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 0.2,
    wait_timeout_ms: int = 300,
) -> None:
    """Poll until any selector matches a visible element."""
    deadline = _time.time() + timeout_seconds
    while _time.time() < deadline:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.count() > 0:
                    locator.wait_for(state="visible", timeout=wait_timeout_ms)
                    return
            except Exception:
                continue
        _time.sleep(poll_interval_seconds)
    raise TimeoutError(f"None of the selectors became visible: {selectors}")


def ensure_checkbox_checked(
    page: Page,
    checkbox: Locator,
    selector: str = "",
    action_timeout_ms: int = 10000,
) -> None:
    """Stably check a checkbox with JS fallback. Faithful to _ensure_checkbox_checked."""
    try:
        if checkbox.is_checked():
            return
    except Exception:
        pass
    try:
        checkbox.scroll_into_view_if_needed(timeout=action_timeout_ms)
    except Exception:
        pass
    try:
        checkbox.check(force=True, timeout=action_timeout_ms)
    except Exception:
        checkbox.evaluate("""
            (element) => {
                element.checked = true;
                element.dispatchEvent(new Event('input', { bubbles: true }));
                element.dispatchEvent(new Event('change', { bubbles: true }));
                element.dispatchEvent(new Event('click', { bubbles: true }));
            }
        """)
    try:
        if checkbox.is_checked():
            return
    except Exception:
        pass
