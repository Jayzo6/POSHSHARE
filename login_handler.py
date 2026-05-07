import time
import tkinter as tk
from tkinter import messagebox
from playwright.sync_api import TimeoutError as PWTimeout


LOGIN_URL = "https://poshmark.com/login"


class LoginHandler:
    """Handles Poshmark login process"""
    
    def __init__(self, log_callback, twofa_callback=None):
        self.log = log_callback
        self.twofa_callback = twofa_callback
    
    def login(self, page, user: str, pw: str) -> bool:
        """Perform login to Poshmark"""
        self.log("[*] Starting login process...")

        try:
            # Navigate to login page
            self.log("    Navigating to login page...")
            page.goto(LOGIN_URL, wait_until="domcontentloaded")
            time.sleep(2)

            # Handle consent popups
            self._handle_consent_popups(page)

            # Wait for login form
            self.log("    Waiting for login form...")
            page.wait_for_load_state("networkidle", timeout=10000)
            time.sleep(2)

            # Check if already logged in
            if self._check_already_logged_in(page):
                return True

            # Fill username
            if not self._fill_username(page, user):
                return False

            # Fill password
            if not self._fill_password(page, pw):
                return False

            # Submit form
            if not self._submit_login(page):
                return False

            # Wait for login completion
            if not self._wait_for_login_completion(page):
                return False

            # Handle 2FA if needed
            self._handle_2fa(page)

            # Final verification
            return self._verify_login_success(page)

        except Exception as e:
            self.log(f"[ERROR] Login process failed: {e}")
            return False

    def _handle_consent_popups(self, page):
        """Handle cookie/consent popups"""
        self.log("    Checking for consent popups...")
        for _ in range(3):
            for label in ["accept", "agree", "close", "got it", "ok", "continue"]:
                try:
                    buttons = page.get_by_role("button", name=lambda n: n and label in n.lower())
                    if buttons.count() > 0:
                        buttons.first.click(timeout=2000)
                        self.log(f"        Clicked '{label}' button")
                        time.sleep(1)
                except Exception:
                    pass

            # Try common popup selectors
            popup_selectors = [
                "[data-testid='cookie-banner-accept']",
                ".cookie-banner button",
                ".modal button",
                ".popup button",
                "[class*='cookie'] button",
                "[class*='consent'] button",
            ]
            for sel in popup_selectors:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=1000):
                        btn.click(timeout=2000)
                        self.log(f"        Clicked popup button using selector: {sel}")
                        time.sleep(1)
                        break
                except Exception:
                    pass

    def _check_already_logged_in(self, page) -> bool:
        """Check if already logged in"""
        try:
            page_title = page.title()
            self.log(f"    Page title: {page_title}")

            if "login" not in page.url.lower() and "poshmark.com" in page.url:
                self.log("    Already logged in or redirected!")
                return True
        except Exception as e:
            self.log(f"    Error checking page state: {e}")
        return False

    def _fill_username(self, page, user: str) -> bool:
        """Fill username/email field"""
        self.log("    Looking for username/email field...")
        
        username_selectors = [
            "input[name='login_form[username_email]']",
            "input[name='username']",
            "input[name='email']",
            "input[type='email']",
            "input[placeholder*='Email' i]",
            "input[placeholder*='Username' i]",
            "#username",
            "#email",
            "[data-testid='username-input']",
            "[data-testid='email-input']",
        ]

        for sel in username_selectors:
            try:
                field = page.locator(sel).first
                if field.is_visible(timeout=2000):
                    field.clear()
                    field.fill(user, timeout=3000)
                    self.log(f"        Filled username using selector: {sel}")
                    time.sleep(0.5)
                    return True
            except Exception:
                continue

        # Fallback approaches
        if self._fill_username_by_label(page, user):
            return True
        
        if self._fill_username_by_fallback(page, user):
            return True

        self.log("    [ERROR] Could not find or fill username field!")
        return False

    def _fill_username_by_label(self, page, user: str) -> bool:
        """Try to fill username using label approach"""
        try:
            field = page.get_by_label("Username", exact=False).first
            if field.is_visible(timeout=2000):
                field.clear()
                field.fill(user, timeout=3000)
                self.log("        Filled username using label approach")
                time.sleep(0.5)
                return True
        except Exception:
            pass
        return False

    def _fill_username_by_fallback(self, page, user: str) -> bool:
        """Try to fill username using fallback approach"""
        try:
            inputs = page.locator("input")
            for i in range(min(10, inputs.count())):
                try:
                    inp = inputs.nth(i)
                    if inp.is_visible(timeout=1000):
                        placeholder = inp.get_attribute("placeholder") or ""
                        name = inp.get_attribute("name") or ""
                        type_attr = inp.get_attribute("type") or ""

                        if (
                            any(keyword in placeholder.lower() for keyword in ["email", "username", "user"])
                            or any(keyword in name.lower() for keyword in ["email", "username", "user"])
                            or type_attr == "email"
                        ):
                            inp.clear()
                            inp.fill(user, timeout=3000)
                            self.log(f"        Filled username using fallback input #{i+1}")
                            time.sleep(0.5)
                            return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _fill_password(self, page, pw: str) -> bool:
        """Fill password field"""
        self.log("    Looking for password field...")
        
        password_selectors = [
            "input[name='login_form[password]']",
            "input[name='password']",
            "input[type='password']",
            "input[placeholder*='Password' i]",
            "#password",
            "[data-testid='password-input']",
        ]

        for sel in password_selectors:
            try:
                field = page.locator(sel).first
                if field.is_visible(timeout=2000):
                    field.clear()
                    field.fill(pw, timeout=3000)
                    self.log(f"        Filled password using selector: {sel}")
                    time.sleep(0.5)
                    return True
            except Exception:
                continue

        # Fallback: try label-based approach
        try:
            field = page.get_by_label("Password", exact=False).first
            if field.is_visible(timeout=2000):
                field.clear()
                field.fill(pw, timeout=3000)
                self.log("        Filled password using label approach")
                time.sleep(0.5)
                return True
        except Exception:
            pass

        self.log("    [ERROR] Could not find or fill password field!")
        return False

    def _submit_login(self, page) -> bool:
        """Submit the login form"""
        self.log("    Looking for login button...")
        
        login_button_selectors = [
            "button:has-text('Log in')",
            "button:has-text('Login')",
            "button:has-text('Sign in')",
            "button:has-text('Sign In')",
            "input[type='submit']",
            "[data-testid='login-button']",
            "[data-testid='signin-button']",
        ]

        for sel in login_button_selectors:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=2000):
                    btn.click(timeout=3000)
                    self.log(f"        Clicked login button using selector: {sel}")
                    return True
            except Exception:
                continue

        # Fallback: try role-based search
        try:
            btn = page.get_by_role(
                "button",
                name=lambda n: n and any(keyword in n.lower() for keyword in ["log in", "login", "sign in", "signin"]),
            ).first
            if btn.is_visible(timeout=2000):
                btn.click(timeout=3000)
                self.log("        Clicked login button using role-based search")
                return True
        except Exception:
            pass

        self.log("    [ERROR] Could not find or click login button!")
        return False

    def _wait_for_login_completion(self, page) -> bool:
        """Wait for login to complete or 2FA prompt to appear.

        This now actively polls every 2 seconds instead of doing a single
        long wait, so 2FA is detected as soon as it shows up.
        """
        self.log("    Waiting for login or 2FA prompt (checking every 2 seconds)...")

        max_wait_seconds = 30
        poll_interval = 2  # how often we re-check for login / 2FA
        start_time = time.time()

        # Small initial pause to let the page react to the login click
        time.sleep(2)

        while time.time() - start_time < max_wait_seconds:
            try:
                current_url = page.url
            except Exception:
                current_url = ""

            # If we've been redirected off the login URL, treat that as success
            if current_url and "poshmark.com" in current_url and "/login" not in current_url:
                self.log("        URL changed - login appears successful")
                return True

            # Otherwise, inspect page content for 2FA or a logged-in state
            try:
                page_content = page.content().lower()
            except Exception:
                page_content = ""

            # Early-detect 2FA / verification pages
            if any(
                keyword in page_content
                for keyword in ["code", "verification", "2fa", "two-factor", "authenticate", "otp"]
            ):
                self.log("        Detected 2FA/verification page while waiting")
                return True

            # Or detect that we appear logged in even if URL didn't change much
            if any(
                keyword in page_content
                for keyword in ["dashboard", "closet", "poshmark"]
            ):
                self.log("        Appears to be logged in based on page content")
                return True

            # Still on login page; wait a bit and re-check
            time.sleep(poll_interval)

        # If we exit the loop, neither login nor 2FA was detected in time
        self.log("        Login/2FA not detected within timeout - still on login page, login may have failed")
        return False

    def _handle_2fa(self, page):
        """Handle 2FA if present"""
        try:
            # Check for 2FA modal using the provided selectors
            twofa_modal_selector = "#content > div:nth-child(3) > div.modal.simple-modal.modal--in.modal--top.modal--small"
            twofa_input_selector = "#content > div:nth-child(3) > div.modal.simple-modal.modal--in.modal--top.modal--small > div.modal__body.otp-modal__body > div > div > input"
            twofa_submit_selector = "#content > div:nth-child(3) > div.modal.simple-modal.modal--in.modal--top.modal--small > div.modal__footer.modal__footer--borderless > div > button"
            
            # Wait a moment for any modals to appear
            time.sleep(2)
            
            # Check if 2FA modal is present
            try:
                twofa_modal = page.locator(twofa_modal_selector)
                if twofa_modal.is_visible(timeout=3000):
                    self.log("[!] 2FA verification code required")
                    self.log("        Using primary 2FA modal selector")
                    
                    # Find the input field within the modal
                    twofa_input = page.locator(twofa_input_selector)
                    if not twofa_input.is_visible(timeout=2000):
                        self.log("        Could not find 2FA input field within modal")
                        return
                    
                    # Prompt user for 2FA code
                    code = self._prompt_for_2fa_code()
                    if not code:
                        self.log("[!] No 2FA code provided, skipping...")
                        return
                    
                    self.log(f"        Received 2FA code: {'*' * len(code)}")
                    
                    # Enter the 2FA code using the specific submit button
                    if self._enter_2fa_code_with_submit(page, twofa_input, twofa_submit_selector, code):
                        self.log("        2FA code entered and submitted successfully")
                        
                        # Wait for 2FA to complete
                        if self._wait_for_2fa_completion(page):
                            self.log("        2FA completed successfully")
                        else:
                            self.log("        Warning: 2FA completion not detected")
                    else:
                        self.log("        Failed to enter or submit 2FA code")
                    return
            except Exception as e:
                self.log(f"        Primary 2FA modal selector failed: {e}")
                pass
            
            # Fallback: check page content for 2FA indicators
            page_content = page.content().lower()
            if any(
                keyword in page_content
                for keyword in ["code", "verification", "2fa", "two-factor", "authenticate", "otp"]
            ):
                self.log("[!] 2FA/Verification detected in page content")
                
                # Try to find 2FA input using the specific selectors first
                try:
                    twofa_input = page.locator(twofa_input_selector)
                    twofa_submit = page.locator(twofa_submit_selector)
                    if twofa_input.is_visible(timeout=2000) and twofa_submit.is_visible(timeout=2000):
                        self.log("        Found 2FA elements using specific selectors in fallback")
                        code = self._prompt_for_2fa_code()
                        if code:
                            if self._enter_2fa_code_with_submit(page, twofa_input, twofa_submit_selector, code):
                                self.log("        2FA code entered and submitted successfully")
                                self._wait_for_2fa_completion(page)
                            else:
                                self.log("        Failed to enter/submit 2FA code")
                        return
                except Exception:
                    pass
                
                # Try to find 2FA input using common selectors
                twofa_input = self._find_2fa_input_field(page)
                if twofa_input:
                    code = self._prompt_for_2fa_code()
                    if code:
                        if self._enter_2fa_code(page, twofa_input, code):
                            self.log("        2FA code entered successfully")
                            self._wait_for_2fa_completion(page)
                        else:
                            self.log("        Failed to enter 2FA code")
                else:
                    self.log("        Could not find 2FA input field, showing manual prompt")
                    messagebox.showinfo(
                        "Poshmark 2FA/Verification",
                        "Please enter your verification code in the browser, then click OK to continue.",
                    )
                    time.sleep(5)
                    
        except Exception as e:
            self.log(f"        Error handling 2FA: {e}")

    def _prompt_for_2fa_code(self) -> str:
        """Prompt user for 2FA code"""
        try:
            if self.twofa_callback:
                # Use the GUI callback for 2FA prompt
                return self.twofa_callback()
            else:
                # Fallback to console input
                self.log("        Please enter your 2FA code in the console below:")
                code = input("2FA Code: ")
                return code.strip() if code else ""
        except Exception as e:
            self.log(f"        Error getting 2FA code: {e}")
            return ""

    def _find_2fa_input_field(self, page):
        """Find 2FA input field using common selectors"""
        twofa_selectors = [
            # Primary Poshmark 2FA selectors
            "#content > div:nth-child(3) > div.modal.simple-modal.modal--in.modal--top.modal--small > div.modal__body.otp-modal__body > div > div > input",
            # Fallback selectors
            "input[type='text'][placeholder*='code' i]",
            "input[type='text'][placeholder*='verification' i]",
            "input[type='text'][placeholder*='otp' i]",
            "input[name*='code' i]",
            "input[name*='verification' i]",
            "input[name*='otp' i]",
            "input[data-testid*='code' i]",
            "input[data-testid*='verification' i]",
            "input[data-testid*='otp' i]",
            ".otp-input input",
            ".verification-code input",
            ".two-factor input",
            "[class*='otp'] input",
            "[class*='verification'] input",
            "[class*='two-factor'] input",
        ]
        
        for selector in twofa_selectors:
            try:
                field = page.locator(selector).first
                if field.is_visible(timeout=2000):
                    self.log(f"        Found 2FA input using selector: {selector}")
                    return field
            except Exception:
                continue
        
        return None

    def _enter_2fa_code_with_submit(self, page, input_field, submit_selector: str, code: str) -> bool:
        """Enter 2FA code and submit using the specific submit button"""
        try:
            # Clear and fill the input field
            input_field.clear()
            input_field.fill(code, timeout=3000)
            time.sleep(0.5)
            
            # Find and click the specific submit button
            submit_btn = page.locator(submit_selector)
            if submit_btn.is_visible(timeout=2000):
                submit_btn.click(timeout=3000)
                self.log(f"        Clicked 2FA submit button using selector: {submit_selector}")
                time.sleep(1)
                return True
            else:
                self.log("        Could not find 2FA submit button")
                # Fallback: try pressing Enter
                input_field.press("Enter")
                time.sleep(1)
                return True
            
        except Exception as e:
            self.log(f"        Error entering/submitting 2FA code: {e}")
            return False

    def _enter_2fa_code(self, page, input_field, code: str) -> bool:
        """Enter 2FA code into the input field (fallback method)"""
        try:
            # Clear and fill the input field
            input_field.clear()
            input_field.fill(code, timeout=3000)
            time.sleep(0.5)
            
            # Try to submit the form by pressing Enter
            input_field.press("Enter")
            time.sleep(1)
            
            # Alternative: look for submit button
            submit_selectors = [
                "button[type='submit']",
                "button:has-text('Verify')",
                "button:has-text('Submit')",
                "button:has-text('Continue')",
                "button:has-text('Confirm')",
                "[data-testid*='submit']",
                "[data-testid*='verify']",
                ".modal button:has-text('Verify')",
                ".modal button:has-text('Submit')",
            ]
            
            for selector in submit_selectors:
                try:
                    submit_btn = page.locator(selector).first
                    if submit_btn.is_visible(timeout=1000):
                        submit_btn.click(timeout=2000)
                        self.log(f"        Clicked submit button using selector: {selector}")
                        break
                except Exception:
                    continue
            
            return True
            
        except Exception as e:
            self.log(f"        Error entering 2FA code: {e}")
            return False

    def _wait_for_2fa_completion(self, page) -> bool:
        """Wait for 2FA to complete successfully"""
        try:
            # Wait for URL to change away from login/2FA pages
            try:
                page.wait_for_url(lambda url: "poshmark.com" in url and "/login" not in url and "verification" not in url.lower(), timeout=30000)
                return True
            except PWTimeout:
                pass
            
            # Check if 2FA modal disappeared
            try:
                twofa_modal_selector = "#content > div:nth-child(3) > div.modal.simple-modal.modal--in.modal--top.modal--small"
                twofa_modal = page.locator(twofa_modal_selector)
                if not twofa_modal.is_visible(timeout=2000):
                    return True
            except Exception:
                pass
            
            # Check page content for success indicators
            page_content = page.content().lower()
            if any(
                keyword in page_content
                for keyword in ["dashboard", "closet", "profile", "welcome"]
            ):
                return True
            
            # Wait a bit more and check again
            time.sleep(5)
            page_content = page.content().lower()
            if any(
                keyword in page_content
                for keyword in ["dashboard", "closet", "profile", "welcome"]
            ):
                return True
                
            return False
            
        except Exception as e:
            self.log(f"        Error waiting for 2FA completion: {e}")
            return False

    def _verify_login_success(self, page) -> bool:
        """Final verification that we're logged in"""
        try:
            final_url = page.url
            if "/login" not in final_url and "poshmark.com" in final_url:
                self.log("[*] Login successful!")
                return True
            else:
                self.log(f"[ERROR] Still on login page: {final_url}")
                return False
        except Exception as e:
            self.log(f"        Error in final verification: {e}")
            return False
