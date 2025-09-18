from selenium.webdriver.chrome.options import Options
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException
import requests, time, json, logging, os, signal, sys, threading
from bs4 import BeautifulSoup
import datetime
from PIL import Image
import io

# Set up logging with file rotation
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs_prudhvi/class_joiner.log'),
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

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global running, driver, screenshot_thread
    logger.info(f"Received signal {signum}. Shutting down gracefully...")
    running = False
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
    """Login and get session token"""
    url = BASE_URL + "/r/l/p"
    data = f"i={username}&p={password}"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": config["myclass_url"],
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.post(url, headers=headers, data=data, timeout=30)
        if response.status_code == 200:
            cookie = response.headers.get("Set-Cookie", "")
            if cookie:
                logger.info("Login successful")
                return cookie
            else:
                logger.error("Login successful but no session cookie received")
                return ""
        else:
            logger.error(f"Login failed with status code: {response.status_code}")
            return ""
    except requests.exceptions.RequestException as e:
        logger.error(f"Login request failed: {e}")
        return ""

def fetch_meetings(wtj_token):
    """Fetch active meetings"""
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
        response = requests.post(url, headers=headers, data=data, timeout=30)
        if response.status_code == 200:
            meetings_data = response.json()
            meetings = meetings_data.get("ref", [])
            for meeting in meetings:
                if meeting.get("status") == "started":
                    logger.info(f"Found active meeting: {meeting.get('title')}")
                    return (meeting.get("_id"), meeting.get("title"))
            logger.debug("No active meetings found")
        else:
            logger.error(f"Failed to fetch meetings: {response.status_code} - {response.text}")
            # Token might be expired
            if response.status_code == 401 or response.status_code == 403:
                return "TOKEN_EXPIRED", None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching meetings: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing meeting response: {e}")

    return None, None

def fetch_meeting(cookie, meeting_id):
    """Fetch meeting details"""
    url = BASE_URL + "/secure/tla/jnr.jsp?m=" + meeting_id
    headers = {
        "cookie": cookie,
        "Referer": BASE_URL + "/secure/tla/mi.jsp",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            return response.content.decode('utf-8')
        else:
            logger.error(f"Failed to fetch meeting details: {response.status_code}")
    except requests.exceptions.RequestException as e:
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
    """Get session token from URL redirect"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        response = requests.head(url, allow_redirects=False, timeout=30, headers=headers)
        location = response.headers.get('location')
        if location:
            logger.debug(f"Got session redirect URL: {location}")
            return location
        else:
            logger.error("No redirect location found in response headers")
    except requests.exceptions.RequestException as e:
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

def connect2class(driver, url):
    """Connect to class session with improved error handling"""
    try:
        logger.info(f"Navigating to session URL")
        driver.get(url)
        time.sleep(10)  # Wait for page load

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
        return True

    except Exception as e:
        logger.error(f"Error connecting to class: {e}")
        return False

def cleanup_driver(driver):
    """Safely cleanup the WebDriver"""
    if driver:
        try:
            driver.quit()
            logger.info("WebDriver cleaned up successfully")
        except Exception as e:
            logger.error(f"Error during driver cleanup: {e}")

def take_screenshot(driver, description="status"):
    """Take a screenshot and save it with timestamp"""
    try:
        if not driver:
            logger.warning("No driver available for screenshot")
            return None

        # Try multiple screenshot directories in order of preference
        screenshot_dirs = [
            '/app/logs_prudhvi/screenshots',
            '/app/logs_prudhvi',
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
    screenshot_request_file = '/app/logs_prudhvi/take_screenshot'
    if os.path.exists(screenshot_request_file):
        try:
            os.remove(screenshot_request_file)
            return True
        except:
            pass
    return False

def cleanup_old_screenshots():
    """Clean up screenshots older than 2 minutes"""
    try:
        screenshot_dirs = ['/app/logs/screenshots', '/app/logs', '/tmp/screenshots', '/tmp']
        current_time = time.time()
        deleted_count = 0

        for dir_path in screenshot_dirs:
            if os.path.exists(dir_path):
                for filename in os.listdir(dir_path):
                    if filename.startswith('screenshot_') and filename.endswith('.png'):
                        filepath = os.path.join(dir_path, filename)
                        try:
                            file_age = current_time - os.path.getctime(filepath)
                            if file_age > 120:  # 2 minutes = 120 seconds
                                os.remove(filepath)
                                deleted_count += 1
                                logger.info(f"Deleted old screenshot: {filename}")
                        except (OSError, PermissionError) as e:
                            logger.debug(f"Could not delete {filename}: {e}")

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} old screenshots")

    except Exception as e:
        logger.error(f"Error in screenshot cleanup: {e}")

def screenshot_monitor():
    """Background thread to monitor for screenshot requests every 5 seconds"""
    global running, driver
    logger.info("Screenshot monitor started - checking every 5 seconds")

    while running:
        try:
            if check_for_screenshot_request() and driver:
                logger.info("Screenshot request detected")
                take_screenshot(driver, "manual_request")

            # Clean up old screenshots every check
            cleanup_old_screenshots()

            time.sleep(5)  # Check every 5 seconds
        except Exception as e:
            logger.error(f"Error in screenshot monitor: {e}")
            time.sleep(5)

    logger.info("Screenshot monitor stopped")

def main():
    """Main execution loop with improved error handling"""
    global json_token, driver, running, screenshot_thread

    logger.info("Starting Auto Class Joiner...")
    logger.info(f"Target university: {config['university_name_codetantra']}")
    logger.info(f"Username: {USERNAME}")
    logger.info(f"Refresh interval: {config['refresh_time']} seconds")
    logger.info("Screenshot requests will be checked every 5 seconds")

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
        return

    try:
        # Start screenshot monitoring thread
        screenshot_thread = threading.Thread(target=screenshot_monitor, daemon=True)
        screenshot_thread.start()

        # Initial login
        json_token = login(USERNAME, PASSWORD)
        if not json_token:
            logger.error("Initial login failed. Exiting.")
            return

        consecutive_errors = 0
        max_consecutive_errors = 5

        while running:
            try:
                logger.info("Fetching meetings...")
                mid, title = fetch_meetings(json_token)

                # Handle token expiration
                if mid == "TOKEN_EXPIRED":
                    logger.info("Token expired, re-authenticating...")
                    json_token = login(USERNAME, PASSWORD)
                    if not json_token:
                        logger.error("Re-authentication failed")
                        time.sleep(60)
                        continue
                    else:
                        continue

                if (mid, title) != (None, None) and mid not in active_sessions:
                    logger.info(f"Live meeting found: {title}")
                    consecutive_errors = 0  # Reset error counter

                    meeting_data = fetch_meeting(json_token, mid)
                    if not meeting_data:
                        logger.error("Failed to fetch meeting data")
                        time.sleep(30)
                        continue

                    logger.info("Getting session URL...")
                    sess_url = get_session_url(meeting_data)
                    if not sess_url:
                        logger.error("Failed to extract session URL")
                        time.sleep(30)
                        continue

                    sess_token_url = get_session_token(sess_url)
                    if not sess_token_url:
                        logger.error("Failed to get session token URL")
                        time.sleep(30)
                        continue
                    take_screenshot(driver, "connecting_to_class")
                    logger.info("Connecting to the class...")
                    if connect2class(driver, sess_token_url):
                        active_sessions.append(mid)
                        logger.info("Connected successfully!")
                        take_screenshot(driver, "connected_successfully")
                        logger.info("Maintaining connection...")
                        time.sleep(300)
                        take_screenshot(driver, "before_disconnect")
                    else:
                        take_screenshot(driver, "connection_failed")
                else:
                    if consecutive_errors == 0:  # Only log this message after successful operations
                        logger.info(f"No new live meetings. Next check in {config['refresh_time']}s")

                time.sleep(config["refresh_time"])

            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt")
                break
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Error in main loop (#{consecutive_errors}): {e}")

                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Too many consecutive errors ({max_consecutive_errors}). Restarting driver...")
                    cleanup_driver(driver)
                    time.sleep(30)
                    driver = setup_headless_driver()
                    if not driver:
                        logger.error("Failed to restart driver. Exiting.")
                        break
                    consecutive_errors = 0
                else:
                    time.sleep(min(30 * consecutive_errors, 300))  # Exponential backoff, max 5 minutes

    except Exception as e:
        logger.error(f"Fatal error in main function: {e}")
    finally:
        cleanup_driver(driver)
        logger.info("Application shutdown complete")

if __name__ == '__main__':
    main()