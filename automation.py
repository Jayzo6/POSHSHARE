import time
import threading
from typing import List, Optional

try:
    from poshshare.browser_manager import BrowserManager
    from poshshare.login_handler import LoginHandler
    from poshshare.sharing_logic import SharingLogic
    from poshshare.models import ClosetTarget
    from poshshare.captcha_solver import TwoCaptchaSolver
except ImportError:
    from browser_manager import BrowserManager
    from login_handler import LoginHandler
    from sharing_logic import SharingLogic
    from models import ClosetTarget
    try:
        from captcha_solver import TwoCaptchaSolver
    except ImportError:
        TwoCaptchaSolver = None


class Sharer:
    """Main orchestrator for Poshmark sharing automation"""
    
    def __init__(self, log, stop_event: threading.Event, on_closet_completed=None, twofa_callback=None):
        self.log = log
        self.stop_event = stop_event
        self.on_closet_completed = on_closet_completed
        self.twofa_callback = twofa_callback
        
        # Initialize components (captcha_solver will be set in run() if API key provided)
        self.login_handler = LoginHandler(log, twofa_callback)
        self.sharing_logic = None  # Will be initialized in run() with captcha_solver

    def run(
        self,
        username: str,
        password: str,
        targets: List[ClosetTarget],
        party: Optional[str],
        headful: bool,
        slowmo_ms: int,
        total_shares_limit: str,
        twocaptcha_api_key: str = "",
    ):
        """Main execution method"""
        total_shared = 0
        closet_count = 0
        
        # Initialize 2captcha solver if API key provided
        captcha_solver = None
        if twocaptcha_api_key and twocaptcha_api_key.strip():
            if TwoCaptchaSolver:
                try:
                    captcha_solver = TwoCaptchaSolver(twocaptcha_api_key.strip(), self.log)
                    balance = captcha_solver.get_balance()
                    if balance is not None:
                        self.log(f"[*] 2captcha API key configured. Balance: ${balance:.2f}")
                    else:
                        self.log(f"[*] 2captcha API key configured (balance check failed)")
                except Exception as e:
                    self.log(f"[!] Failed to initialize 2captcha solver: {e}")
            else:
                self.log("[!] 2captcha module not available")
        
        # Initialize sharing logic with captcha solver
        self.sharing_logic = SharingLogic(self.log, self.stop_event, captcha_solver=captcha_solver)
        
        # Parse total shares limit if provided
        max_total_shares = None
        if total_shares_limit and total_shares_limit.strip():
            try:
                max_total_shares = int(total_shares_limit.strip())
                self.log(f"[*] Total shares limit set to: {max_total_shares}")
            except ValueError:
                self.log(f"[!] Invalid total shares limit: {total_shares_limit}")
        
        self.log(f"[*] Starting to process {len(targets)} closets...")
        
        # Use browser manager for clean browser handling
        with BrowserManager(headful=headful, slowmo_ms=slowmo_ms) as page:
            # Attempt to login
            if not self.login_handler.login(page, username, password):
                self.log("[!] Login failed! Stopping bot.")
                return

            self.log("[*] Login successful, proceeding with sharing...")

            # Process each closet
            for t in targets:
                if self.stop_event.is_set():
                    break
                    
                # Check if we've hit the total shares limit
                if max_total_shares and total_shared >= max_total_shares:
                    self.log(f"[*] Reached total shares limit of {max_total_shares}. Stopping.")
                    break
                    
                closet_count += 1
                self.log(f"[*] Processing closet {closet_count}/{len(targets)}: @{t.user}")
                
                try:
                    closet_shares = self.sharing_logic.share_items_in_closet(
                        page, t.user, t.max_items, party, on_closet_completed=self.on_closet_completed
                    )
                    total_shared += closet_shares
                    
                    # Show closet summary
                    self.log(f"[✓] Closet {closet_count}/{len(targets)}: @{t.user} - {closet_shares} items shared")
                    self.log(f"[*] Total shares so far: {total_shared}")
                    
                    # Check if we're approaching the limit
                    if max_total_shares:
                        remaining = max_total_shares - total_shared
                        if remaining <= 0:
                            self.log(f"[*] Reached total shares limit of {max_total_shares}. Stopping.")
                            break
                        elif remaining <= 10:
                            self.log(f"[!] Only {remaining} shares remaining before limit")
                            
                except Exception as e:
                    self.log(f"[!] Error on closet {t.user}: {e}")
                    time.sleep(2.5)
            
        # Final summary
        self.log(f"[*] ===== SHARING COMPLETE =====")
        self.log(f"[*] Total closets processed: {closet_count}")
        self.log(f"[*] Total items shared: {total_shared}")
        if max_total_shares:
            self.log(f"[*] Shares limit: {max_total_shares}")
            if total_shared >= max_total_shares:
                self.log(f"[*] Limit reached successfully!")
        self.log(f"[*] =========================")
