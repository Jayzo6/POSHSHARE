import time
import random
from typing import List, Optional

try:
    from poshshare.models import jitter
except ImportError:
    from models import jitter


CLOSET_URL = "https://poshmark.com/closet/{}"


class SharingLogic:
    """Handles the core sharing functionality"""
    
    def __init__(self, log_callback, stop_event, captcha_solver=None):
        self.log = log_callback
        self.stop_event = stop_event
        self.captcha_solver = captcha_solver  # Optional 2captcha solver instance

    def detect_and_wait_for_captcha(self, page, check_interval_seconds: float = 5.0, max_wait_seconds: int = 900) -> bool:
        """Detect the 'Oh the HUMAN-ity' reCAPTCHA dialog and wait until it's cleared.
        
        Automatically clicks the CAPTCHA checkbox when detected, then waits for completion.
        Returns True if no captcha is currently blocking or it was cleared.
        Returns False if stop was requested while waiting.
        """
        try:
            # Fast checks for common signals
            def is_captcha_visible() -> bool:
                try:
                    content = (page.content() or "").lower()
                except Exception:
                    content = ""

                if any(k in content for k in [
                    "oh the human-ity", "human-ity", "captcha", "recaptcha", "i'm not a robot"
                ]):
                    return True

                try:
                    # reCAPTCHA iframes/buttons
                    if page.locator("iframe[title*='recaptcha' i]").count() > 0:
                        return True
                except Exception:
                    pass

                try:
                    if page.locator("[role='dialog'] :text-matches('human|captcha|robot', 'i')").count() > 0:
                        return True
                except Exception:
                    pass
                
                # Check for the specific checkbox element
                try:
                    checkbox = page.locator("#recaptcha-anchor")
                    if checkbox.count() > 0 and checkbox.is_visible(timeout=1000):
                        return True
                except Exception:
                    pass

                return False
            
            def is_captcha_checkbox_unchecked() -> bool:
                """Check if the CAPTCHA checkbox exists and is unchecked"""
                try:
                    checkbox = page.locator("#recaptcha-anchor")
                    if checkbox.count() > 0 and checkbox.is_visible(timeout=1000):
                        # Check if it has the unchecked class or aria-checked="false"
                        aria_checked = checkbox.get_attribute("aria-checked")
                        class_attr = checkbox.get_attribute("class") or ""
                        if aria_checked == "false" or "recaptcha-checkbox-unchecked" in class_attr:
                            return True
                except Exception:
                    pass
                return False

            if not is_captcha_visible():
                return True

            self.log("[!] reCAPTCHA detected: 'Oh the HUMAN-ity'.")
            
            # Try to solve using 2captcha if available
            if self.captcha_solver:
                try:
                    # Extract site key from the page
                    site_key = None
                    try:
                        # Look for data-sitekey attribute in g-recaptcha div
                        recaptcha_div = page.locator('.g-recaptcha[data-sitekey], [data-sitekey]')
                        if recaptcha_div.count() > 0:
                            site_key = recaptcha_div.first.get_attribute("data-sitekey")
                            self.log(f"    Found site key: {site_key[:20]}...")
                    except Exception as e:
                        self.log(f"    Could not extract site key: {e}")
                    
                    if site_key:
                        page_url = page.url
                        self.log(f"    Using 2captcha to solve CAPTCHA...")
                        token = self.captcha_solver.solve_recaptcha_v2(site_key, page_url)
                        
                        if token:
                            # Inject the solution token into the page
                            try:
                                # Find the g-recaptcha-response textarea and set its value
                                response_textarea = page.locator("#g-recaptcha-response")
                                if response_textarea.count() > 0:
                                    # Use evaluate to set the value directly
                                    page.evaluate(f"""
                                        document.getElementById('g-recaptcha-response').innerHTML = '{token}';
                                        document.getElementById('g-recaptcha-response').value = '{token}';
                                    """)
                                    
                                    # Trigger the callback if it exists
                                    page.evaluate("""
                                        if (typeof validateResponse === 'function') {
                                            validateResponse(arguments[0]);
                                        }
                                    """, token)
                                    
                                    self.log("    ✓ CAPTCHA solution token injected successfully")
                                    time.sleep(2)
                                    
                                    # Check if CAPTCHA is now cleared
                                    if not is_captcha_visible():
                                        self.log("    ✓ CAPTCHA cleared by 2captcha solution!")
                                        return True
                                    else:
                                        self.log("    Token injected but CAPTCHA still visible, waiting...")
                                else:
                                    self.log("    Could not find g-recaptcha-response textarea")
                            except Exception as e:
                                self.log(f"    Error injecting token: {e}")
                    else:
                        self.log("    Could not extract site key, falling back to manual click")
                except Exception as e:
                    self.log(f"    2captcha solving failed: {e}, falling back to manual click")
            
            # Fallback: Try to automatically click the checkbox inside the iframe
            checkbox_clicked = False
            
            # Based on the HTML structure: iframe with title="reCAPTCHA" contains #recaptcha-anchor
            # Try multiple approaches to find and click the checkbox
            iframe_selectors = [
                'iframe[title="reCAPTCHA"]',  # Exact match for the title
                'iframe[title*="reCAPTCHA" i]',  # Case-insensitive partial match
                'iframe[src*="recaptcha/enterprise/anchor" i]',  # Match the src pattern
                '.g-recaptcha iframe',  # Find iframe inside g-recaptcha container
                'iframe[src*="recaptcha" i]'  # Fallback: any iframe with recaptcha in src
            ]
            
            for iframe_sel in iframe_selectors:
                try:
                    # Check if iframe exists on the page
                    iframe_count = page.locator(iframe_sel).count()
                    if iframe_count > 0:
                        self.log(f"    Found reCAPTCHA iframe using: {iframe_sel}")
                        
                        # Use frame_locator to access the iframe content
                        iframe_frame = page.frame_locator(iframe_sel)
                        checkbox = iframe_frame.locator("#recaptcha-anchor")
                        
                        # Wait for checkbox to be visible and check its state
                        if checkbox.is_visible(timeout=3000):
                            try:
                                aria_checked = checkbox.get_attribute("aria-checked")
                                class_attr = checkbox.get_attribute("class") or ""
                                
                                # Check if it's unchecked
                                if aria_checked == "false" or "recaptcha-checkbox-unchecked" in class_attr:
                                    self.log("    Automatically clicking CAPTCHA checkbox...")
                                    checkbox.click(timeout=5000)
                                    checkbox_clicked = True
                                    time.sleep(3)  # Wait for CAPTCHA to process
                                    self.log("    ✓ Checkbox clicked. Waiting for CAPTCHA to complete...")
                                    break
                                else:
                                    self.log(f"    Checkbox already checked (aria-checked={aria_checked})")
                                    checkbox_clicked = True  # Already checked, consider it done
                                    break
                            except Exception as e:
                                self.log(f"    Error checking checkbox state: {e}")
                                # Try clicking anyway
                                try:
                                    self.log("    Attempting to click checkbox anyway...")
                                    checkbox.click(timeout=5000)
                                    checkbox_clicked = True
                                    time.sleep(3)
                                    self.log("    ✓ Checkbox clicked. Waiting for CAPTCHA to complete...")
                                    break
                                except Exception as e2:
                                    self.log(f"    Click failed: {e2}")
                                    continue
                        else:
                            self.log(f"    Checkbox not visible in iframe with selector: {iframe_sel}")
                except Exception as e:
                    self.log(f"    Attempt with {iframe_sel} failed: {e}")
                    continue
            
            if not checkbox_clicked:
                self.log("    Could not auto-click checkbox. Please solve the CAPTCHA manually in the browser.")
            
            self.log("    The bot will pause here and resume automatically once solved.")

            waited = 0.0
            while is_captcha_visible():
                if self.stop_event.is_set():
                    self.log("    [•] Stop requested while waiting for CAPTCHA.")
                    return False
                time.sleep(check_interval_seconds)
                waited += check_interval_seconds
                if int(waited) % 30 == 0:
                    self.log("    Still waiting for CAPTCHA to be solved...")

                if max_wait_seconds and waited >= max_wait_seconds:
                    self.log("    [!] Waited too long for CAPTCHA. Continuing attempt anyway.")
                    break

            self.log("    ✓ CAPTCHA cleared. Resuming.")
            time.sleep(1.0)
            return True
        except Exception as e:
            # If detection fails for any reason, do not block the flow
            self.log(f"    [!] CAPTCHA detection error (continuing): {e}")
            return True
    
    def load_more_items(self, page, target_count=60, max_scrolls=50):
        """Load more items by scrolling, ensuring we have enough shareable items"""
        self.log(f"    Loading items...")

        last_height = 0
        no_change_count = 0
        max_no_change = 3

        for i in range(max_scrolls):
            if self.stop_event.is_set():
                return

            page.mouse.wheel(0, 3000)
            time.sleep(0.8)

            cards = page.locator("[data-et-name='listing'], a[data-et-name='listing'], .tile")
            try:
                card_count = cards.count()
            except Exception:
                card_count = 0

            share_buttons = page.locator(
                ".social-action-bar__share, [class*='social-action-bar__share']"
            )
            try:
                share_count = share_buttons.count()
            except Exception:
                share_count = 0

            # Never log "Found 0..." — counts are often 0 until listings/share bars hydrate.
            if share_count > 0 and ((i > 0 and i % 10 == 0) or share_count >= target_count):
                self.log(f"    Found {share_count} shareable items...")

            if share_count >= target_count:
                self.log(f"    ✓ Loaded {share_count} shareable items")
                break

            try:
                height = page.evaluate("document.body.scrollHeight")
                if height == last_height:
                    no_change_count += 1
                    if no_change_count >= max_no_change:
                        self.log(f"    No more items to load")
                        break
                else:
                    no_change_count = 0
                    last_height = height
            except Exception:
                no_change_count += 1
                if no_change_count >= max_no_change:
                    break

        time.sleep(2)

        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        final_shares = page.locator(".social-action-bar__share, [class*='social-action-bar__share']")

        try:
            final_share_count = final_shares.count()
            if final_share_count < target_count and final_share_count < 20:
                self.log(f"    Trying to load more items...")
                for _ in range(5):
                    page.mouse.wheel(0, 4000)
                    time.sleep(1.0)

                final_shares_after = page.locator(
                    ".social-action-bar__share, [class*='social-action-bar__share']"
                )
                try:
                    final_share_count_after = final_shares_after.count()
                    if final_share_count_after > final_share_count:
                        final_share_count = final_share_count_after
                except Exception:
                    pass
        except Exception:
            pass

    def find_share_buttons(self, page, max_items=None):
        """Find share buttons on the page"""
        page.wait_for_load_state("networkidle", timeout=10000)

        CARD_SEL = "[data-et-name='listing'], a[data-et-name='listing'], .tile"
        cards = page.locator(CARD_SEL)
        count = cards.count()
        target = min(count, max_items) if max_items else count

        try:
            all_share_buttons = page.locator(
                ".social-action-bar__share, [class*='social-action-bar__share'], div.social-action-bar__action.social-action-bar__share"
            )
            direct_count = all_share_buttons.count()
            if direct_count >= target:
                return [all_share_buttons.nth(i) for i in range(min(target, direct_count))]
        except Exception:
            pass

        share_buttons = []
        for i in range(target):
            try:
                card = cards.nth(i)
                card.scroll_into_view_if_needed(timeout=4000)

                try:
                    card.hover(timeout=1500)
                except Exception:
                    pass

                share = None

                try:
                    share = card.locator(
                        "div.social-action-bar__action.social-action-bar__share"
                    ).first
                    if share.count() > 0:
                        share_buttons.append(share)
                        continue
                except Exception:
                    pass

                try:
                    share = card.locator(
                        ".social-action-bar__share, [class*='social-action-bar__share']"
                    ).first
                    if share.count() > 0:
                        share_buttons.append(share)
                        continue
                except Exception:
                    pass

                try:
                    share = card.locator("[class*='social-action-bar__share']").first
                    if share.count() > 0:
                        share_buttons.append(share)
                        continue
                except Exception:
                    pass

            except Exception as e:
                continue

        if share_buttons:
            return share_buttons

        fallback_selectors = [
            ".social-action-bar__share",
            "[class*='social-action-bar__share']",
            "div.social-action-bar__action.social-action-bar__share",
            "[class*='social-action-bar__action'][class*='social-action-bar__share']",
        ]

        for sel in fallback_selectors:
            try:
                btns = page.locator(sel)
                count = btns.count()
                if count > 0:
                    return btns
            except Exception:
                continue

        try:
            fallback = page.locator("[class*='share'], [class*='Share']")
            count = fallback.count()
            if count > 0:
                return fallback
        except Exception:
            pass

        return page.locator("[class*='share'], [class*='Share']")

    def _close_modal_and_wait(self, page, modal_selector):
        """Helper function to close modal and wait for it to disappear"""
        try:
            try:
                close_buttons = page.locator(
                    "button:has-text('Done'), button:has-text('Close'), .modal__close-btn, [class*='close']"
                )
                for i in range(close_buttons.count()):
                    try:
                        close_btn = close_buttons.nth(i)
                        if close_btn.is_visible(timeout=1000):
                            close_btn.click(timeout=2000)
                            self.log("Clicked close button to ensure modal is closed")
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            try:
                page.keyboard.press("Escape")
                self.log("Pressed Escape key to close modal")
                time.sleep(1.0)
            except Exception:
                pass

            try:
                page.mouse.click(100, 100)
                self.log("Clicked outside modal to close it")
                time.sleep(1.0)
            except Exception:
                pass

            self.log("Waiting for modal to disappear...")
            for attempt in range(10):
                try:
                    if modal_selector in ["fallback-modal", "overlay-fallback"]:
                        visible_modals = (
                            page.locator("[class*='modal'], [class*='popup'], [class*='dialog']")
                            .filter(lambda el: el.is_visible())
                            .count()
                        )
                        if visible_modals == 0:
                            self.log("Modal has disappeared")
                            break
                    else:
                        if not page.locator(modal_selector).is_visible(timeout=1000):
                            self.log("Modal has disappeared")
                            break
                except Exception:
                    pass

                time.sleep(1)
                if attempt == 9:
                    self.log("Modal may still be visible, but proceeding...")

            self.log("Ensuring page is ready for next share...")
            time.sleep(2.0)

            return True
        except Exception as e:
            self.log(f"Error in _close_modal_and_wait: {e}")
            return False

    def share_current_dialog(self, page):
        """Handle the share dialog that appears after clicking a share button"""
        try:
            self.log("Waiting for share modal to appear...")
            time.sleep(1.5)

            try:
                page_content = page.content()
                if "followers" in page_content.lower():
                    self.log("Page contains 'followers' text")
                if "share" in page_content.lower():
                    self.log("Page contains 'share' text")
                if "modal" in page_content.lower():
                    self.log("Page contains 'modal' text")
            except Exception:
                pass

            modal_selectors = [
                "#app > main > div:nth-child(1) > div.share-modal > div > div.modal.simple-modal.modal--in",
                ".share-modal .modal.simple-modal.modal--in",
                ".share-modal .modal",
                ".modal.simple-modal.modal--in",
                ".modal.simple-modal",
                "[data-test='modal']",
                "[role='dialog']",
                ".modal",
                ".share-modal",
            ]

            modal = None
            modal_selector = None

            for selector in modal_selectors:
                try:
                    self.log(f"Trying modal selector: {selector}")
                    element = page.locator(selector).first
                    if element.is_visible(timeout=3000):
                        modal = element
                        modal_selector = selector
                        self.log(f"Found visible modal using selector: {selector}")
                        break
                    else:
                        self.log(f"Selector found but not visible: {selector}")
                except Exception as e:
                    self.log(f"Selector failed: {selector} - {e}")
                    continue

            if not modal:
                self.log("No modal found with any selector, trying alternative approach...")
                try:
                    modal_candidates = page.locator(
                        "[class*='modal'], [class*='popup'], [class*='dialog']"
                    ).all()
                    self.log(f"Found {len(modal_candidates)} potential modal candidates")

                    for i, candidate in enumerate(modal_candidates):
                        try:
                            if candidate.is_visible():
                                text = candidate.text_content() or ""
                                class_attr = candidate.get_attribute("class") or ""
                                self.log(
                                    f"Modal candidate {i+1}: class='{class_attr}', text='{text[:100]}...'"
                                )

                            if "followers" in text.lower() or "share" in text.lower():
                                modal = candidate
                                modal_selector = "fallback-modal"
                                self.log("Found modal using fallback detection")
                                break
                        except Exception as e:
                            self.log(f"Error examining modal candidate {i+1}: {e}")
                            continue

                except Exception as e:
                    self.log(f"Fallback modal detection failed: {e}")

                if not modal:
                    self.log("No modal found at all, trying one more approach...")
                    try:
                        overlays = page.locator(
                            "[class*='overlay'], [class*='backdrop'], [class*='popup'], [style*='z-index']"
                        ).all()
                        self.log(f"Found {len(overlays)} potential overlay elements")

                        for i, overlay in enumerate(overlays):
                            try:
                                if overlay.is_visible():
                                    text = overlay.text_content() or ""
                                    class_attr = overlay.get_attribute("class") or ""
                                    style_attr = overlay.get_attribute("style") or ""
                                    self.log(
                                        f"Overlay {i+1}: class='{class_attr}', style='{style_attr}', text='{text[:100]}...'"
                                    )

                                if "followers" in text.lower() or "share" in text.lower():
                                    modal = overlay
                                    modal_selector = "overlay-fallback"
                                    self.log("Found modal using overlay detection")
                                    break
                            except Exception as e:
                                self.log(f"Error examining overlay {i+1}: {e}")
                                continue
                    except Exception as e:
                        self.log(f"Overlay detection failed: {e}")

                    if not modal:
                        self.log("No modal found at all, cannot proceed")
                        return False

            self.log("Specifically searching for 'to my followers' buttons...")

            try:
                clickable_followers = page.locator(
                    "a:has-text('followers'), button:has-text('followers'), [role='button']:has-text('followers')"
                )

                for i in range(clickable_followers.count()):
                    try:
                        element = clickable_followers.nth(i)
                        if element.is_visible():
                            text = (
                                element.text_content().strip() if element.text_content() else ""
                            )
                            tag_name = element.evaluate("el => el.tagName.toLowerCase()")
                            class_attr = element.get_attribute("class") or ""

                            if (
                                tag_name in ["a", "button"]
                                or "btn" in class_attr.lower()
                                or element.get_attribute("role") == "button"
                                or element.get_attribute("onclick")
                                or element.get_attribute("data-et-name")
                            ):
                                self.log(
                                    f"Found actual clickable 'to my followers' element: {text}"
                                )
                                self.log(
                                    f"Element type: {tag_name}, classes: {class_attr}"
                                )

                                element.click()
                                self.log(
                                    "Successfully clicked actual 'to my followers' button!"
                                )

                                self.log("Waiting for modal to close automatically...")
                                time.sleep(5.0)

                                try:
                                    if not page.locator(modal_selector).is_visible(timeout=2000):
                                        self.log("Modal closed automatically - perfect!")
                                        return True
                                    else:
                                        self.log("Modal still visible, will close manually...")
                                except Exception:
                                    self.log("Could not check modal visibility, proceeding...")

                                return self._close_modal_and_wait(page, modal_selector)
                    except Exception as e:
                        self.log(
                            f"Error with clickable followers element {i+1}: {e}"
                        )
                        continue
            except Exception as e:
                self.log(f"Error searching for clickable followers: {e}")

            followers_selectors = [
                "a.btn.btn--primary.btn--full:has-text('To My Followers')",
                "a.btn.btn--primary.btn--full:has-text('to my followers')",
                "a.btn.btn--primary.btn--full:has-text('followers')",
                "a[data-et-name='share_to_followers']",
                "a.btn.btn--primary:has-text('followers')",
                "button:has-text('To My Followers')",
                "button:has-text('to my followers')",
                "button:has-text('followers')",
                "[role='button']:has-text('To My Followers')",
                "[role='button']:has-text('to my followers')",
                "[role='button']:has-text('followers')",
                "text=To My Followers",
                "text=to my followers",
                "text=followers",
                "[aria-label*='followers' i]",
                "[title*='followers' i]",
                "[data-testid*='followers' i]",
                ".btn--primary:has-text('followers')",
                ".btn--full:has-text('followers')",
                "button.btn--primary",
                "button.btn--full",
                "[role='button'].btn--primary",
                "[role='button'].btn--full",
            ]

            for selector in followers_selectors:
                try:
                    if modal_selector in ["fallback-modal", "overlay-fallback"]:
                        element = page.locator(selector).first
                    else:
                        element = page.locator(f"{modal_selector} {selector}").first

                    if element.is_visible():
                        self.log(
                            f"Found 'to my followers' element using selector: {selector}"
                        )
                        element.click()
                        self.log("Successfully clicked 'to my followers' button!")
                        return True
                except Exception:
                    continue

            self.log(
                "No specific 'to my followers' button found, enumerating all elements in modal..."
            )

            try:
                if modal_selector in ["fallback-modal", "overlay-fallback"]:
                    all_elements = page.locator("button, a, [role='button'], [data-test]").all()
                else:
                    all_elements = page.locator(
                        f"{modal_selector} button, {modal_selector} a, {modal_selector} [role='button'], {modal_selector} [data-test]"
                    ).all()

                self.log(f"Dialog contains {len(all_elements)} buttons/clickable elements")

                for i, element in enumerate(all_elements):
                    try:
                        if element.is_visible():
                            text = (
                                element.text_content().strip()
                                if element.text_content()
                                else ""
                            )
                            aria_label = element.get_attribute("aria-label") or ""
                            title = element.get_attribute("title") or ""
                            data_testid = element.get_attribute("data-testid") or ""
                            class_attr = element.get_attribute("class") or ""

                            self.log(
                                f"Button {i+1}: '{text}' [aria-label: '{aria_label}', title: '{title}', data-testid: '{data_testid}', class: '{class_attr}']"
                            )

                            if (
                                ("followers" in text.lower() or "to my" in text.lower())
                                and (
                                    "btn" in class_attr.lower()
                                    or "button" in class_attr.lower()
                                    or element.evaluate("el => el.tagName.toLowerCase()")
                                    in ["a", "button"]
                                    or element.get_attribute("role") == "button"
                                    or element.get_attribute("onclick")
                                    or element.get_attribute("data-et-name")
                                )
                            ):
                                self.log(
                                    f"Found clickable 'to my followers' element: {text}"
                                )
                                tag_name = element.evaluate("el => el.tagName.toLowerCase()")
                                self.log(f"Element type: {tag_name}, classes: {class_attr}")
                                element.click()
                                self.log(
                                    "Successfully clicked 'to my followers' button!"
                                )

                                self.log(
                                    "Waiting for modal to close and page to reset..."
                                )
                                time.sleep(3.0)

                                try:
                                    close_buttons = page.locator(
                                        "button:has-text('Done'), button:has-text('Close'), .modal__close-btn, [class*='close']"
                                    )
                                    for i in range(close_buttons.count()):
                                        try:
                                            close_btn = close_buttons.nth(i)
                                            if close_btn.is_visible(timeout=1000):
                                                close_btn.click(timeout=2000)
                                                self.log(
                                                    "Clicked close button to ensure modal is closed"
                                                )
                                                break
                                        except Exception:
                                            continue
                                except Exception:
                                    pass

                                try:
                                    page.keyboard.press("Escape")
                                    self.log("Pressed Escape key to close modal")
                                    time.sleep(1.0)
                                except Exception:
                                    pass

                                try:
                                    page.mouse.click(100, 100)
                                    self.log("Clicked outside modal to close it")
                                    time.sleep(1.0)
                                except Exception:
                                    pass

                                self.log("Waiting for modal to disappear...")
                                for attempt in range(10):
                                    try:
                                        if modal_selector in ["fallback-modal", "overlay-fallback"]:
                                            visible_modals = (
                                                page.locator(
                                                    "[class*='modal'], [class*='close'], [class*='dialog']"
                                                )
                                                .filter(lambda el: el.is_visible())
                                                .count()
                                            )
                                            if visible_modals == 0:
                                                self.log("Modal has disappeared")
                                                break
                                        else:
                                            if not page.locator(modal_selector).is_visible(timeout=1000):
                                                self.log("Modal has disappeared")
                                                break
                                    except Exception:
                                        pass

                                    time.sleep(1)
                                    if attempt == 9:
                                        self.log(
                                            "Modal may still be visible, but proceeding..."
                                        )

                                self.log(
                                    "Ensuring page is ready for next share..."
                                )
                                time.sleep(2.0)

                                return True
                        else:
                            self.log(f"Button {i+1}: [not visible]")
                    except Exception as e:
                        self.log(f"Error examining button {i+1}: {e}")
                        continue

            except Exception as e:
                self.log(f"Error enumerating elements: {e}")

            try:
                if modal_selector in ["fallback-modal", "overlay-fallback"]:
                    dialog_text = page.text_content()
                else:
                    dialog_text = page.locator(modal_selector).text_content()

                if "followers" in dialog_text.lower():
                    self.log("Dialog contains 'followers' text")
                if "share" in dialog_text.lower():
                    self.log("Dialog contains 'share' text")
            except Exception:
                pass

            try:
                self.log("Looking for 'to my followers' button...")

                if modal_selector in ["fallback-modal", "overlay-fallback"]:
                    followers_elements = page.locator("*:has-text('followers')").all()
                else:
                    followers_elements = page.locator(
                        f"{modal_selector} *:has-text('followers')"
                    ).all()

                for element in followers_elements:
                    try:
                        clickable_parent = element.locator(
                            "xpath=ancestor::button | ancestor::a | ancestor::*[@role='button'] | ancestor::*[@data-test]"
                        ).first
                        if clickable_parent and clickable_parent.is_visible():
                            self.log(
                                f"Found clickable parent of 'followers' text: {clickable_parent.text_content()}"
                            )
                            clickable_parent.click()
                            self.log("Successfully clicked parent of 'followers' text!")
                            return True
                    except Exception:
                        continue

                try:
                    if modal_selector in ["fallback-modal", "overlay-fallback"]:
                        first_button = page.locator("button, a, [role='button']").first
                    else:
                        first_button = page.locator(
                            f"{modal_selector} button, {modal_selector} a, {modal_selector} [role='button']"
                        ).first

                    if first_button and first_button.is_visible():
                        button_text = (
                            first_button.text_content().strip()
                            if first_button.text_content()
                            else ""
                        )
                        self.log(
                            f"Last resort: clicking first visible button: '{button_text}'"
                        )
                        first_button.click()
                        self.log("Last resort button click successful!")
                        return True
                except Exception as e:
                    self.log(f"Last resort button click failed: {e}")

            except Exception as e:
                self.log(f"Error in last resort search: {e}")

            self.log("[ERROR] Could not find or click any appropriate share button!")
            return False

        except Exception as e:
            self.log(f"Error handling share dialog: {e}")
            return False

    def share_items_in_closet(
        self, page, closet_user: str, max_items: int, party: Optional[str], 
        pause_every=15, on_closet_completed=None
    ):
        """Share items in a specific closet"""
        self.log(f"[*] Processing closet: @{closet_user}")
        page.goto(CLOSET_URL.format(closet_user), wait_until="domcontentloaded")

        # If a CAPTCHA is shown on arrival, wait for it to be solved
        if not self.detect_and_wait_for_captcha(page):
            return 0

        self.load_more_items(page, target_count=max_items if max_items > 0 else 80)

        shared = 0
        target = max_items if max_items > 0 else 10

        while shared < target:
            if self.stop_event.is_set():
                self.log("    [•] Stop requested.")
                break

            # Check for CAPTCHA before interacting
            if not self.detect_and_wait_for_captcha(page):
                break

            btns = self.find_share_buttons(page, target - shared)
            try:
                total = len(btns) if isinstance(btns, list) else btns.count()
            except Exception:
                total = 0

            if total == 0:
                self.log(f"    No more shareable items found in @{closet_user}")
                break

            if isinstance(btns, list):
                btn = btns[0]
            else:
                btn = btns.nth(0)

            try:
                btn.scroll_into_view_if_needed(timeout=3000)
                btn.click(timeout=4000)
            except Exception:
                try:
                    page.evaluate("(el)=>el.click()", btn)
                except Exception:
                    self.log(f"    [!] Failed to click share button, skipping...")
                    continue

            time.sleep(0.5)

            ok = self.share_current_dialog(page)

            if ok:
                shared += 1
                self.log(f"    [✓] Shared item {shared}/{target}")

                time.sleep(10.0)

                jitter(4.0, 8.0)

                if shared % 20 == 0:
                    long_nap = random.uniform(40, 55)
                    self.log(f"    [•] Major milestone reached! Pausing for {long_nap:.1f}s...")
                    if self.stop_event.wait(timeout=long_nap):
                        break
                elif shared % pause_every == 0:
                    nap = random.uniform(12, 22)
                    self.log(f"    [•] Pausing for {nap:.1f}s...")
                    if self.stop_event.wait(timeout=nap):
                        break
            else:
                for label in ["close", "cancel", "dismiss", "x"]:
                    try:
                        page.get_by_role(
                            "button", name=lambda n: n and label in n.lower()
                        ).first.click(timeout=1000)
                        break
                    except Exception:
                        pass
                continue

        self.log(f"    [✓] @{closet_user}: {shared}/{target} items shared")

        # Call completion callback for all closets (including those with 0 items)
        if on_closet_completed:
            try:
                if shared > 0:
                    self.log(f"    [*] Calling completion callback for @{closet_user} ({shared} items shared)")
                else:
                    self.log(f"    [*] Calling completion callback for @{closet_user} (no shareable items found)")
                on_closet_completed(closet_user, shared)
            except Exception as e:
                self.log(f"    [!] Error calling closet completion callback: {e}")

        return shared
