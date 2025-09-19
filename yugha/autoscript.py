from selenium.webdriver.chrome.options import Options
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException
import requests, time, json, logging, os, signal, sys, threading, random, glob
from bs4 import BeautifulSoup
import datetime
from PIL import Image
import io
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Set up logging with file rotation
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs_yugha/class_joiner.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Global variables
json_token = ""
active_sessions = []
driver = None
running = True
screenshot_thread = None
cleanup_thread = None
meeting_screenshot_thread = None
current_meeting_active = False
current_meeting_info = {}
app_status = "Starting"

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global running, driver, screenshot_thread, cleanup_thread, meeting_screenshot_thread
    logger.info(f"Received signal {signum}. Shutting down gracefully...")
    running = False
    update_app_status("Shutting down")
    if driver:
        try:
            driver.quit()
            logger.info("WebDriver closed successfully")
        except Exception as e:
            logger.error(f"Error closing WebDriver: {e}")
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def update_app_status(status, meeting_info=None):
    """Update application status for dashboard"""
    global app_status, current_meeting_info
    app_status = status
    if meeting_info:
        current_meeting_info = meeting_info
    
    # Write status to a file for the dashboard to read
    try:
        status_data = {
            "status": app_status,
            "timestamp": datetime.datetime.now().isoformat(),
            "meeting_info": current_meeting_info
        }
        with open('/app/logs_yugha/app_status.json', 'w') as f:
            json.dump(status_data, f)
    except Exception as e:
        logger.error(f"Error writing status file: {e}")

def cleanup_logs_on_startup():
    """Clean up logs on startup only"""
    try:
        # Clean up log files only on startup
        log_dirs = ['/app/logs_yugha', '/app/logs']
        for log_dir in log_dirs:
            if os.path.exists(log_dir):
                log_files = glob.glob(os.path.join(log_dir, '*.log'))
                for log_file in log_files:
                    try:
                        with open(log_file, 'w') as f:
                            f.write('')  # Clear the log file
                        logger.info(f"Cleared log file on startup: {log_file}")
                    except Exception as e:
                        logger.error(f"Could not clear log file {log_file}: {e}")

    except Exception as e:
        logger.error(f"Error in cleanup_logs_on_startup: {e}")

def cleanup_screenshots_on_startup():
    """Clean up all screenshots on startup only"""
    try:
        # Clean up all screenshots only on startup
        screenshot_dirs = [
            '/app/screenshots_yugha',
            '/app/logs_yugha/screenshots',
            '/app/logs_yugha',
            '/tmp/screenshots',
            '/tmp'
        ]
        
        deleted_count = 0
        for dir_path in screenshot_dirs:
            if os.path.exists(dir_path):
                screenshot_files = glob.glob(os.path.join(dir_path, 'screenshot_*.png'))
                for screenshot_file in screenshot_files:
                    try:
                        os.remove(screenshot_file)
                        deleted_count += 1
                    except Exception as e:
                        logger.debug(f"Could not delete screenshot {screenshot_file}: {e}")

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} screenshot files on startup")

    except Exception as e:
        logger.error(f"Error in cleanup_screenshots_on_startup: {e}")

def cleanup_old_screenshots():
    """Clean up screenshots older than 12 hours"""
    try:
        screenshot_dirs = [
            '/app/screenshots_yugha',
            '/app/logs_yugha/screenshots',
            '/app/logs_yugha',
            '/tmp/screenshots',
            '/tmp'
        ]
        current_time = time.time()
        deleted_count = 0

        for dir_path in screenshot_dirs:
            if os.path.exists(dir_path):
                for filename in os.listdir(dir_path):
                    if filename.startswith('screenshot_') and filename.endswith('.png'):
                        filepath = os.path.join(dir_path, filename)
                        try:
                            file_age = current_time - os.path.getctime(filepath)
                            if file_age > 43200:  # 12 hours = 43200 seconds
                                os.remove(filepath)
                                deleted_count += 1
                                logger.info(f"Deleted old screenshot: {filename}")
                        except (OSError, PermissionError) as e:
                            logger.debug(f"Could not delete {filename}: {e}")

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old screenshots")

    except Exception as e:
        logger.error(f"Error in screenshot cleanup: {e}")

def cleanup_old_logs():
    """Clear all log files"""
    try:
        log_dirs = ['/app/logs_yugha', '/app/logs']
        for log_dir in log_dirs:
            if os.path.exists(log_dir):
                log_files = glob.glob(os.path.join(log_dir, '*.log'))
                for log_file in log_files:
                    try:
                        with open(log_file, 'w') as f:
                            f.write('')  # Clear the log file
                        logger.info(f"Cleared log file: {log_file}")
                    except Exception as e:
                        logger.error(f"Could not clear log file {log_file}: {e}")

    except Exception as e:
        logger.error(f"Error in cleanup_old_logs: {e}")

def periodic_cleanup():
    """Background thread to perform logs and screenshots cleanup every 12 hours"""
    global running
    logger.info("Periodic cleanup started - cleaning logs and screenshots every 12 hours")
    
    # Initial cleanup on startup - logs and screenshots
    cleanup_logs_on_startup()
    cleanup_screenshots_on_startup()
    
    while running:
        try:
            # Wait for 12 hours (43200 seconds)
            for _ in range(4320):  # Check every 10 seconds for shutdown
                if not running:
                    break
                time.sleep(10)
            
            if running:
                logger.info("Performing periodic cleanup - logs and screenshots (12-hour interval)")
                cleanup_old_logs()
                cleanup_old_screenshots()
                
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}")
            time.sleep(60)

    logger.info("Periodic cleanup stopped")

# Load configuration
try:
    with open("/app/config.json", "r") as f:
        config = json.load(f)
    logger.info("Configuration loaded successfully")
except FileNotFoundError:
    logger.error("config.json not found in /app/. Please mount the configuration file.")
    sys.exit(1)
except json.JSONDecodeError as e:
    logger.error(f"Invalid JSON in config file: {e}")
    sys.exit(1)

BASE_URL = f"https://{config['university_name_codetantra']}.codetantra.com"
USERNAME = config["username"]
PASSWORD = config["password"]

def create_session_with_retry():
    """Create a requests session with retry strategy and SSL handling"""
    session = requests.Session()
    
    # Retry strategy - use allowed_methods instead of method_whitelist
    retry_strategy = Retry(
        total=3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
        backoff_factor=1
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    # Disable SSL verification to handle certificate issues
    session.verify = False
    
    return session

def setup_headless_driver():
    """Set up Chrome driver optimized for Docker container"""
    try:
        # Use the pre-installed ChromeDriver
        service = Service('/usr/local/bin/chromedriver')

        chrome_options = Options()

        # Essential Docker/headless options
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--ignore-ssl-errors=yes")
        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_argument("--ignore-ssl-errors-spki-list")
        chrome_options.add_argument("--disable-extensions-http-throttling")

        # Fix for DevToolsActivePort issue
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument("--run-all-compositor-stages-before-draw")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-ipc-flooding-protection")
        chrome_options.add_argument("--disable-hang-monitor")
        chrome_options.add_argument("--disable-client-side-phishing-detection")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--disable-prompt-on-repost")
        chrome_options.add_argument("--disable-domain-reliability")
        chrome_options.add_argument("--disable-component-update")
        chrome_options.add_argument("--disable-background-downloads")
        chrome_options.add_argument("--disable-breakpad")
        chrome_options.add_argument("--disable-component-extensions-with-background-pages")
        chrome_options.add_argument("--disable-back-forward-cache")
        chrome_options.add_argument("--disable-ipc-flooding-protection")
        chrome_options.add_argument("--enable-features=NetworkService,NetworkServiceLogging")
        chrome_options.add_argument("--force-fieldtrials=*BackgroundTracing/default/")
        chrome_options.add_argument("--enable-automation")
        chrome_options.add_argument("--disable-browser-side-navigation")
        chrome_options.add_argument("--disable-single-click-autofill")

        # Memory and performance optimizations for containers
        chrome_options.add_argument("--memory-pressure-off")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--disable-default-apps")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-sync")
        chrome_options.add_argument("--disable-translate")
        chrome_options.add_argument("--hide-scrollbars")
        chrome_options.add_argument("--metrics-recording-only")
        chrome_options.add_argument("--mute-audio")
        chrome_options.add_argument("--no-first-run")
        chrome_options.add_argument("--safebrowsing-disable-auto-update")
        chrome_options.add_argument("--disable-logging")
        chrome_options.add_argument("--disable-permissions-api")

        # Window size for headless mode
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--start-maximized")

        # Media stream options
        chrome_options.add_argument("--use-fake-ui-for-media-stream")
        chrome_options.add_argument("--use-fake-device-for-media-stream")
        chrome_options.add_argument("--allow-running-insecure-content")

        # User data directory (create a temporary directory to avoid permission issues)
        chrome_options.add_argument("--user-data-dir=/tmp/chrome-user-data")

        # Additional stability options (simplified)
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        driver = webdriver.Chrome(options=chrome_options, service=service)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        logger.info("Chrome driver initialized successfully in headless mode")
        return driver

    except Exception as e:
        logger.error(f"Failed to initialize Chrome driver: {e}")
        return None

def login(username, password):
    """Login and get session token with SSL error handling"""
    update_app_status("Logging in")
    url = BASE_URL + "/r/l/p"
    data = f"i={username}&p={password}"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": config["myclass_url"],
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        session = create_session_with_retry()
        response = session.post(url, headers=headers, data=data, timeout=30)
        
        if response.status_code == 200:
            cookie = response.headers.get("Set-Cookie", "")
            if cookie:
                logger.info("Login successful")
                update_app_status("Logged in - Waiting for meetings")
                return cookie
            else:
                logger.error("Login successful but no session cookie received")
                update_app_status("Login failed - No session cookie")
                return ""
        else:
            logger.error(f"Login failed with status code: {response.status_code}")
            update_app_status(f"Login failed - Status {response.status_code}")
            return ""
    except Exception as e:
        logger.error(f"Login request failed: {e}")
        update_app_status(f"Login error: {str(e)[:50]}")
        return ""

def fetch_meetings(wtj_token):
    """Fetch active meetings with SSL error handling"""
    url = BASE_URL + "/secure/rest/dd/mf"
    time_curr = int(time.time() * 1000)
    data = json.dumps({
        "minDate": time_curr - (15 * 3600000),
        "maxDate": time_curr + (15 * 3600000),
        "filters": {
            "showSelf": True,
            "status": "started,ended,scheduled"
        }
    })

    headers = {
        "cookie": wtj_token,
        "Referer": BASE_URL + "/secure/tla/mi.jsp",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        session = create_session_with_retry()
        response = session.post(url, headers=headers, data=data, timeout=30)
        
        if response.status_code == 200:
            # Check if response content is empty or not JSON
            response_text = response.text.strip()
            if not response_text:
                logger.error("Empty response received from meetings API")
                return "TOKEN_EXPIRED", None
            
            # Check if response looks like JSON
            if not response_text.startswith('{') and not response_text.startswith('['):
                logger.error(f"Non-JSON response received: {response_text[:200]}...")
                return "TOKEN_EXPIRED", None
            
            try:
                meetings_data = response.json()
                meetings = meetings_data.get("ref", [])
                for meeting in meetings:
                    if meeting.get("status") == "started":
                        logger.info(f"Found active meeting: {meeting.get('title')}")
                        meeting_info = {
                            "id": meeting.get("_id"),
                            "title": meeting.get("title"),
                            "status": "found",
                            "instructor": meeting.get("instructor", "Unknown"),
                            "start_time": meeting.get("startTime"),
                            "end_time": meeting.get("endTime")
                        }
                        return (meeting.get("_id"), meeting.get("title"), meeting_info)
                logger.debug("No active meetings found")
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}. Response: {response_text[:200]}...")
                return "TOKEN_EXPIRED", None
                
        else:
            logger.error(f"Failed to fetch meetings: {response.status_code} - {response.text[:200]}...")
            # Token might be expired or SSL issue
            if response.status_code == 401 or response.status_code == 403:
                return "TOKEN_EXPIRED", None
    except requests.exceptions.SSLError as e:
        logger.error(f"SSL Error fetching meetings: {e}")
        return "SSL_ERROR", None
    except Exception as e:
        logger.error(f"Error fetching meetings: {e}")
        # Check if it's an SSL-related error in the string
        if "SSL" in str(e) or "certificate" in str(e).lower():
            return "SSL_ERROR", None

    return None, None, None

def fetch_meeting(cookie, meeting_id):
    """Fetch meeting details with SSL error handling"""
    url = BASE_URL + "/secure/tla/jnr.jsp?m=" + meeting_id
    headers = {
        "cookie": cookie,
        "Referer": BASE_URL + "/secure/tla/mi.jsp",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        session = create_session_with_retry()
        response = session.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            return response.content.decode('utf-8')
        else:
            logger.error(f"Failed to fetch meeting details: {response.status_code}")
    except Exception as e:
        logger.error(f"Error fetching meeting details: {e}")
    return ""

def get_session_url(raw_data):
    """Extract session URL from meeting data"""
    try:
        soup = BeautifulSoup(raw_data, "html.parser")
        frame = soup.find("iframe", {"id": "frame"})
        if frame:
            src = frame.get("src")
            logger.debug(f"Found iframe src: {src}")
            return src
        logger.error("No iframe with id 'frame' found")
    except Exception as e:
        logger.error(f"Error parsing meeting data: {e}")
    return None

def get_session_token(url):
    """Get session token from URL redirect with SSL handling"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        session = create_session_with_retry()
        response = session.head(url, allow_redirects=False, timeout=30, headers=headers)
        location = response.headers.get('location')
        if location:
            logger.debug(f"Got session redirect URL: {location}")
            return location
        else:
            logger.error("No redirect location found in response headers")
    except Exception as e:
        logger.error(f"Error getting session token: {e}")
    return None

def safe_click_element(driver, xpath, timeout=30, description="element"):
    """Safely click an element with better error handling"""
    try:
        wait = WebDriverWait(driver, timeout)
        element = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))

        # Scroll element into view
        driver.execute_script("arguments[0].scrollIntoView(true);", element)
        time.sleep(1)

        # Try normal click first
        try:
            element.click()
        except WebDriverException:
            # If normal click fails, try JavaScript click
            driver.execute_script("arguments[0].click();", element)

        logger.info(f"Successfully clicked {description}")
        return True

    except TimeoutException:
        logger.error(f"Timeout waiting for {description}: {xpath}")
        return False
    except WebDriverException as e:
        logger.error(f"WebDriver exception clicking {description}: {e}")
        return False

def connect2class(driver, url, meeting_info):
    """Connect to class session with improved error handling"""
    global current_meeting_active, current_meeting_info
    try:
        logger.info(f"Navigating to session URL")
        update_app_status("Connecting to meeting", meeting_info)
        driver.get(url)
        time.sleep(10)  # Wait for page load

        # Mark meeting as active for screenshot monitoring
        current_meeting_active = True
        current_meeting_info = meeting_info
        current_meeting_info["status"] = "connecting"

        # Define the sequence of elements to click
        click_sequence = [
            ("/html/body/div[2]/div/div/div[1]/div/div/span/button[1]", "permission dialog button 1"),
            ("/html/body/div[2]/div/div/div[1]/div/span/button[1]", "permission dialog button 2"),
            ("/html/body/div/main/section/div/header/div/div[1]/div[1]/button", "main interface button"),
            ("/html/body/div[1]/main/section/div[1]/div/div/div[2]/div[1]/div[2]/div/div/div/div/div/div[2]/span", "final connect button")
        ]

        for xpath, description in click_sequence:
            logger.info(f"Attempting to click {description}")
            if not safe_click_element(driver, xpath, timeout=60, description=description):
                # Try alternative selectors or continue
                logger.warning(f"Failed to click {description}, attempting to continue...")
                time.sleep(5)
            else:
                time.sleep(5)  # Wait between successful clicks

        logger.info("Class connection sequence completed")
        current_meeting_info["status"] = "connected"
        update_app_status("Connected to meeting", current_meeting_info)
        return True

    except Exception as e:
        logger.error(f"Error connecting to class: {e}")
        current_meeting_active = False
        current_meeting_info["status"] = "error"
        update_app_status("Connection failed", current_meeting_info)
        return False

def cleanup_driver(driver):
    """Safely cleanup the WebDriver"""
    global current_meeting_active, current_meeting_info
    current_meeting_active = False  # Stop meeting screenshot monitoring
    current_meeting_info = {}
    update_app_status("Driver cleanup")
    
    if driver:
        try:
            driver.quit()
            logger.info("WebDriver cleaned up successfully")
        except Exception as e:
            logger.error(f"Error during driver cleanup: {e}")
    
    # Give threads time to recognize driver is gone
    time.sleep(2)

def take_screenshot(driver, description="status"):
    """Take a screenshot and save it with timestamp"""
    try:
        if not driver:
            logger.warning("No driver available for screenshot")
            return None
            
        # Check if driver is still alive
        try:
            driver.current_url  # Simple check to see if driver is responsive
        except Exception as e:
            logger.warning(f"Driver not responsive for screenshot: {e}")
            return None

        # Try multiple screenshot directories in order of preference
        screenshot_dirs = [
            '/app/screenshots_yugha',
            '/app/logs_yugha/screenshots',
            '/app/logs_yugha',
            '/tmp/screenshots',
            '/tmp'
        ]

        screenshot_dir = None
        for dir_path in screenshot_dirs:
            try:
                os.makedirs(dir_path, exist_ok=True)
                # Test write permissions
                test_file = os.path.join(dir_path, 'test_write.tmp')
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
                screenshot_dir = dir_path
                break
            except (OSError, PermissionError):
                logger.debug(f"Cannot write to directory: {dir_path}")
                continue

        if not screenshot_dir:
            logger.error("No writable directory found for screenshots")
            return None

        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"screenshot_{description}_{timestamp}.png"
        filepath = os.path.join(screenshot_dir, filename)

        screenshot = driver.get_screenshot_as_png()
        with open(filepath, 'wb') as f:
            f.write(screenshot)
        logger.info(f"Screenshot saved: {filepath}")
        return filepath

    except Exception as e:
        logger.error(f"Error taking screenshot: {e}")
        return None

def check_for_screenshot_request():
    """Check if user wants a screenshot"""
    screenshot_request_files = [
        '/app/logs_yugha/take_screenshot',
        '/app/logs/take_screenshot'
    ]
    
    for screenshot_request_file in screenshot_request_files:
        if os.path.exists(screenshot_request_file):
            try:
                os.remove(screenshot_request_file)
                return True
            except:
                pass
    return False

def screenshot_monitor():
    """Background thread to monitor for screenshot requests every 5 seconds"""
    global running, driver
    logger.info("Screenshot monitor started - checking every 5 seconds")

    while running:
        try:
            # Check if driver exists and is responsive before taking screenshot
            if check_for_screenshot_request() and driver:
                try:
                    # Quick check if driver is still alive
                    driver.current_url
                    logger.info("Screenshot request detected")
                    take_screenshot(driver, "manual_request")
                except Exception as e:
                    logger.warning(f"Cannot take screenshot, driver not responsive: {e}")

            time.sleep(5)  # Check every 5 seconds
        except Exception as e:
            logger.error(f"Error in screenshot monitor: {e}")
            time.sleep(5)

    logger.info("Screenshot monitor stopped")

def meeting_screenshot_monitor():
    """Background thread to take screenshots every 15 minutes during active meetings"""
    global running, driver, current_meeting_active
    logger.info("Meeting screenshot monitor started - screenshots every 15 minutes during meetings")

    while running:
        try:
            if current_meeting_active and driver:
                # Take a screenshot every 15 minutes (900 seconds)
                wait_time = 900  # 15 minutes
                
                # Count down in smaller increments so we can check status more frequently
                for i in range(wait_time):
                    if not running or not current_meeting_active:
                        break
                    time.sleep(1)
                
                # Only take screenshot if meeting is still active after waiting
                if current_meeting_active and driver and running:
                    try:
                        # Quick check if driver is still alive
                        driver.current_url
                        take_screenshot(driver, "meeting_15min_auto")
                        logger.info("Automatic 15-minute meeting screenshot taken")
                    except Exception as e:
                        logger.warning(f"Cannot take meeting screenshot, driver not responsive: {e}")
            else:
                time.sleep(10)  # Check every 10 seconds when no meeting is active
                
        except Exception as e:
            logger.error(f"Error in meeting screenshot monitor: {e}")
            time.sleep(10)

    logger.info("Meeting screenshot monitor stopped")

def main():
    """Main execution loop with improved error handling"""
    global json_token, driver, running, screenshot_thread, cleanup_thread, meeting_screenshot_thread, current_meeting_active, current_meeting_info

    logger.info("Starting Auto Class Joiner...")
    logger.info(f"Target university: {config['university_name_codetantra']}")
    logger.info(f"Username: {USERNAME}")
    logger.info(f"Refresh interval: {config['refresh_time']} seconds")
    logger.info("Screenshot requests will be checked every 5 seconds")
    logger.info("Meeting screenshots will be taken every 15 minutes during active meetings")
    logger.info("Periodic cleanup will run every 12 hours")

    update_app_status("Initializing")

    # Create necessary directories
    os.makedirs('/app/logs_yugha', exist_ok=True)
    os.makedirs('/app/screenshots_yugha', exist_ok=True)

    # Start cleanup thread
    cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
    cleanup_thread.start()

    # Initialize driver
    max_retries = 3
    for attempt in range(max_retries):
        driver = setup_headless_driver()
        if driver:
            break
        logger.error(f"Driver initialization attempt {attempt + 1}/{max_retries} failed")
        if attempt < max_retries - 1:
            time.sleep(10)

    if not driver:
        logger.error("Failed to initialize driver after all attempts. Exiting.")
        update_app_status("Failed to initialize driver")
        return

    try:
        # Start screenshot monitoring threads
        screenshot_thread = threading.Thread(target=screenshot_monitor, daemon=True)
        screenshot_thread.start()
        
        meeting_screenshot_thread = threading.Thread(target=meeting_screenshot_monitor, daemon=True)
        meeting_screenshot_thread.start()

        # Initial login
        json_token = login(USERNAME, PASSWORD)
        if not json_token:
            logger.error("Initial login failed. Exiting.")
            update_app_status("Initial login failed")
            return

        consecutive_errors = 0
        max_consecutive_errors = 5
        ssl_error_count = 0
        max_ssl_errors = 3

        while running:
            try:
                logger.info("Fetching meetings...")
                result = fetch_meetings(json_token)
                
                if len(result) == 3:
                    mid, title, meeting_info = result
                else:
                    mid, title = result
                    meeting_info = None

                # Handle token expiration
                if mid == "TOKEN_EXPIRED":
                    logger.info("Token expired, re-authenticating...")
                    update_app_status("Token expired - Re-authenticating")
                    json_token = login(USERNAME, PASSWORD)
                    if not json_token:
                        logger.error("Re-authentication failed")
                        update_app_status("Re-authentication failed")
                        time.sleep(60)
                        continue
                    else:
                        consecutive_errors = 0
                        ssl_error_count = 0
                        continue

                # Handle SSL errors
                if mid == "SSL_ERROR":
                    ssl_error_count += 1
                    logger.warning(f"SSL error encountered ({ssl_error_count}/{max_ssl_errors}). Re-authenticating...")
                    update_app_status(f"SSL error ({ssl_error_count}/{max_ssl_errors})")
                    
                    if ssl_error_count >= max_ssl_errors:
                        logger.info("Too many SSL errors. Performing full re-authentication...")
                        time.sleep(30)  # Wait before retrying
                    
                    # Try to re-authenticate
                    json_token = login(USERNAME, PASSWORD)
                    if not json_token:
                        logger.error("Re-authentication after SSL error failed")
                        time.sleep(60)
                        continue
                    else:
                        logger.info("Re-authentication after SSL error successful")
                        ssl_error_count = 0  # Reset SSL error count on successful login
                        consecutive_errors = 0
                        continue

                if mid and title and mid not in active_sessions:
                    logger.info(f"Live meeting found: {title}")
                    consecutive_errors = 0  # Reset error counter
                    ssl_error_count = 0  # Reset SSL error counter

                    # Update meeting info with found status
                    if meeting_info:
                        meeting_info["status"] = "found"
                        update_app_status("Meeting found - Fetching details", meeting_info)

                    meeting_data = fetch_meeting(json_token, mid)
                    if not meeting_data:
                        logger.error("Failed to fetch meeting data")
                        if meeting_info:
                            meeting_info["status"] = "fetch_failed"
                            update_app_status("Failed to fetch meeting details", meeting_info)
                        time.sleep(30)
                        continue

                    logger.info("Getting session URL...")
                    sess_url = get_session_url(meeting_data)
                    if not sess_url:
                        logger.error("Failed to extract session URL")
                        if meeting_info:
                            meeting_info["status"] = "url_failed"
                            update_app_status("Failed to extract session URL", meeting_info)
                        time.sleep(30)
                        continue

                    sess_token_url = get_session_token(sess_url)
                    if not sess_token_url:
                        logger.error("Failed to get session token URL")
                        if meeting_info:
                            meeting_info["status"] = "token_failed"
                            update_app_status("Failed to get session token", meeting_info)
                        time.sleep(30)
                        continue
                    
                    take_screenshot(driver, "connecting_to_class")
                    logger.info("Connecting to the class...")
                    
                    if connect2class(driver, sess_token_url, meeting_info or {"title": title, "id": mid}):
                        active_sessions.append(mid)
                        logger.info("Connected successfully!")
                        take_screenshot(driver, "connected_successfully")
                        logger.info("Maintaining connection...")
                        
                        # Stay connected for 5 minutes with periodic status updates
                        connection_time = 300  # 5 minutes
                        start_time = time.time()
                        
                        while time.time() - start_time < connection_time and running:
                            time.sleep(30)  # Check every 30 seconds
                            # Update status to show connection time remaining
                            remaining = int(connection_time - (time.time() - start_time))
                            if current_meeting_info:
                                current_meeting_info["connection_remaining"] = remaining
                                update_app_status("Connected to meeting", current_meeting_info)
                        
                        logger.info("Meeting session completed")
                        current_meeting_active = False
                        current_meeting_info = {}
                        update_app_status("Meeting session completed")
                    else:
                        take_screenshot(driver, "connection_failed")
                        current_meeting_active = False
                        current_meeting_info = {}
                        update_app_status("Failed to connect to meeting")
                else:
                    if consecutive_errors == 0 and ssl_error_count == 0:  # Only log this message after successful operations
                        logger.info(f"No new live meetings. Next check in {config['refresh_time']}s")
                        update_app_status("Waiting for meetings - No active meetings found")

                time.sleep(config["refresh_time"])

            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt")
                break
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error in main loop (#{consecutive_errors}): {e}")
                update_app_status(f"Error in main loop: {str(e)[:50]}")

                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Too many consecutive errors ({max_consecutive_errors}). Restarting driver...")
                    cleanup_driver(driver)
                    current_meeting_active = False
                    current_meeting_info = {}
                    update_app_status("Restarting driver due to errors")
                    time.sleep(30)
                    driver = setup_headless_driver()
                    if not driver:
                        logger.error("Failed to restart driver. Exiting.")
                        update_app_status("Failed to restart driver")
                        break
                    consecutive_errors = 0
                else:
                    time.sleep(min(30 * consecutive_errors, 300))  # Exponential backoff, max 5 minutes

    except Exception as e:
        logger.error(f"Fatal error in main function: {e}")
        update_app_status(f"Fatal error: {str(e)[:50]}")
    finally:
        current_meeting_active = False
        current_meeting_info = {}
        cleanup_driver(driver)
        update_app_status("Application shutdown")
        logger.info("Application shutdown complete")

if __name__ == '__main__':
    main()