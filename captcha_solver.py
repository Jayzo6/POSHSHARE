"""
2captcha API integration for solving reCAPTCHA v2
"""
import time
import requests
from typing import Optional


class TwoCaptchaSolver:
    """Handles 2captcha API integration for solving reCAPTCHA"""
    
    API_URL = "http://2captcha.com"
    
    def __init__(self, api_key: str, log_callback=None):
        """
        Initialize 2captcha solver
        
        Args:
            api_key: Your 2captcha API key
            log_callback: Optional callback function for logging messages
        """
        self.api_key = api_key
        self.log = log_callback or (lambda msg: None)
    
    def solve_recaptcha_v2(self, site_key: str, page_url: str, timeout: int = 120) -> Optional[str]:
        """
        Solve a reCAPTCHA v2 challenge using 2captcha API
        
        Args:
            site_key: The reCAPTCHA site key (found in data-sitekey attribute)
            page_url: The URL of the page with the CAPTCHA
            timeout: Maximum time to wait for solution (seconds)
            
        Returns:
            The solution token if successful, None otherwise
        """
        if not self.api_key:
            self.log("[!] 2captcha API key not provided")
            return None
        
        try:
            # Step 1: Submit CAPTCHA to 2captcha
            self.log(f"[*] Submitting CAPTCHA to 2captcha (site_key: {site_key[:20]}...)")
            submit_url = f"{self.API_URL}/in.php"
            submit_data = {
                "key": self.api_key,
                "method": "userrecaptcha",
                "googlekey": site_key,
                "pageurl": page_url,
                "json": 1
            }
            
            response = requests.post(submit_url, data=submit_data, timeout=30)
            result = response.json()
            
            if result.get("status") != 1:
                error_msg = result.get("request", "Unknown error")
                self.log(f"[!] Failed to submit CAPTCHA to 2captcha: {error_msg}")
                return None
            
            captcha_id = result.get("request")
            self.log(f"[*] CAPTCHA submitted successfully. ID: {captcha_id}")
            self.log(f"[*] Waiting for solution (timeout: {timeout}s)...")
            
            # Step 2: Poll for solution
            get_url = f"{self.API_URL}/res.php"
            start_time = time.time()
            poll_interval = 5  # Check every 5 seconds
            
            while time.time() - start_time < timeout:
                time.sleep(poll_interval)
                
                get_params = {
                    "key": self.api_key,
                    "action": "get",
                    "id": captcha_id,
                    "json": 1
                }
                
                response = requests.get(get_url, params=get_params, timeout=30)
                result = response.json()
                
                if result.get("status") == 1:
                    token = result.get("request")
                    self.log(f"[✓] CAPTCHA solved successfully!")
                    return token
                elif result.get("request") == "CAPCHA_NOT_READY":
                    elapsed = int(time.time() - start_time)
                    self.log(f"    Still solving... ({elapsed}s elapsed)")
                    continue
                else:
                    error_msg = result.get("request", "Unknown error")
                    self.log(f"[!] Error getting solution: {error_msg}")
                    return None
            
            self.log(f"[!] Timeout waiting for CAPTCHA solution ({timeout}s)")
            return None
            
        except requests.exceptions.RequestException as e:
            self.log(f"[!] Network error communicating with 2captcha: {e}")
            return None
        except Exception as e:
            self.log(f"[!] Unexpected error solving CAPTCHA: {e}")
            return None
    
    def get_balance(self) -> Optional[float]:
        """Get account balance from 2captcha"""
        try:
            url = f"{self.API_URL}/res.php"
            params = {
                "key": self.api_key,
                "action": "getbalance",
                "json": 1
            }
            response = requests.get(url, params=params, timeout=10)
            result = response.json()
            if result.get("status") == 1:
                return float(result.get("request", 0))
            return None
        except Exception:
            return None
