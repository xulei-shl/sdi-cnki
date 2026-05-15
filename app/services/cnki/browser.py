"""Browser and session management for CNKI.
Adapted from docs/cnki-search/scripts/browser.py
"""

import json
import time
from pathlib import Path
from typing import Optional

from camoufox.sync_api import NewBrowser
from playwright.sync_api import sync_playwright

from app.config import get_settings
from .exceptions import BrowserError

settings = get_settings()

COOKIES_DIR = Path(settings.cookies_dir)
COOKIES_DIR.mkdir(parents=True, exist_ok=True)
COOKIES_FILE = COOKIES_DIR / "cnki_cookies.json"


class CnkiBrowser:
    """Camoufox browser lifecycle and session persistence."""

    HOME_URL = "https://www.cnki.net/"
    ADVANCED_SEARCH_URL = "https://kns.cnki.net/kns8s/AdvSearch?classid=YSTT4HG0"

    def __init__(self, headless: bool = True, cookies_file: Optional[Path] = None):
        self.headless = headless
        self._cookies_file = cookies_file or COOKIES_FILE
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    @property
    def page(self):
        return self._page

    @property
    def context(self):
        return self._context

    def start(self):
        self._reset_asyncio_loop()
        self._playwright = sync_playwright().start()
        try:
            self._browser = NewBrowser(
                self._playwright,
                headless=self.headless,
                geoip=False,
            )
        except TypeError:
            self._browser = self._playwright.firefox.launch(headless=self.headless)
        self._context = self._browser.new_context(
            locale="zh-CN",
            accept_downloads=True,
        )
        self._context.set_default_timeout(30000)
        self._page = self._context.new_page()
        self._load_cookies()

    def close(self):
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None
        if self._context:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        self._reset_asyncio_loop()

    def goto(self, url: str, timeout: int = 60000):
        self._page.goto(url, timeout=timeout, wait_until="domcontentloaded")

    def save_session(self):
        try:
            cookies = self._context.cookies()
            self._cookies_file.parent.mkdir(parents=True, exist_ok=True)
            self._cookies_file.write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            print(f"  [browser] Save cookies failed: {e}")

    def _load_cookies(self) -> bool:
        if not self._cookies_file.exists():
            return False
        try:
            cookies = json.loads(self._cookies_file.read_text(encoding="utf-8"))
            if cookies:
                self._context.add_cookies(cookies)
            return True
        except Exception:
            return False

    def is_captcha_visible(self) -> bool:
        try:
            return self._page.evaluate("""
                () => {
                    const el = document.querySelector('#tcaptcha_transform_dy');
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    return r.top >= 0 && r.width > 0 && r.height > 0;
                }
            """)
        except Exception:
            return False

    def wait_for_captcha_completion(self, timeout: int = 120) -> bool:
        if not self.is_captcha_visible():
            return True
        print("\n[CNKI] Captcha detected. Please complete it in the browser window.")
        print(f"  Waiting up to {timeout}s... (press Enter after completion)")
        import threading
        confirmed = threading.Event()
        def _wait_input():
            try:
                input()
                confirmed.set()
            except Exception:
                pass
        threading.Thread(target=_wait_input, daemon=True).start()
        start = time.time()
        while time.time() - start < timeout:
            if confirmed.is_set():
                time.sleep(2)
                return not self.is_captcha_visible()
            if not self.is_captcha_visible():
                time.sleep(2)
                return True
            time.sleep(2)
        return not self.is_captcha_visible()

    def _reset_asyncio_loop(self):
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop and not loop.is_closed():
                loop.close()
            asyncio.set_event_loop(None)
        except RuntimeError:
            pass

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.close()
