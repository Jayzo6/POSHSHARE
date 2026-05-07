import os
import sys
from playwright.sync_api import sync_playwright
from typing import Optional


def _setup_frozen_browser_path():
    """When running as a frozen exe: use bundled browsers if present, else folder next to exe."""
    if not getattr(sys, "frozen", False):
        return
    # 1) Prefer browsers bundled inside the exe (extracted to _MEIPASS at runtime)
    if hasattr(sys, "_MEIPASS"):
        bundled = os.path.join(sys._MEIPASS, "browsers")
        if os.path.isdir(bundled):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = bundled
            return
    # 2) Fallback: "browsers" folder next to the exe
    if hasattr(sys, "executable"):
        exe_dir = os.path.dirname(sys.executable)
        browsers_dir = os.path.join(exe_dir, "browsers")
        if os.path.isdir(browsers_dir):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_dir


class BrowserManager:
    """Handles browser setup, context creation, and cleanup"""
    
    def __init__(self, headful: bool = False, slowmo_ms: int = 0):
        self.headful = headful
        self.slowmo_ms = slowmo_ms
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
    
    def __enter__(self):
        """Context manager entry - setup browser"""
        _setup_frozen_browser_path()
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=not self.headful, 
            slow_mo=self.slowmo_ms
        )
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        return self.page
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup browser"""
        try:
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass
    
    def get_page(self) -> Optional[object]:
        """Get the current page object"""
        return self.page
    
    def is_running(self) -> bool:
        """Check if browser is running"""
        return self.browser is not None and not self.browser.is_closed()
