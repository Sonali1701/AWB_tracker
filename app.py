import streamlit as st
import pandas as pd
import os
import json
import base64
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import Flow, InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.keys import Keys
import re
from urllib.parse import urlparse, parse_qs

# OAuth2 configuration
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
TOKEN_PICKLE = 'token.pickle'

# Initialize session state
if 'credentials' not in st.session_state:
    st.session_state.credentials = None
if 'sheet_id' not in st.session_state:
    st.session_state.sheet_id = ""
if 'auth_url' not in st.session_state:
    st.session_state.auth_url = ""


def show_auth_ui():
    """Show authentication UI and handle authentication state."""
    st.sidebar.title("🔐 Authentication")
    
    # Initialize session state variables if they don't exist
    if 'auth_initialized' not in st.session_state:
        st.session_state.auth_initialized = True
        st.session_state.auth_url = ""
        st.session_state.credentials = None
        st.session_state.sheet_id = ""
        st.session_state.sheet_name = "Sheet1"
    
    # Get or create auth URL if needed
    if not st.session_state.get('auth_url') and not st.session_state.get('credentials'):
        try:
            flow = get_flow()
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                prompt='consent',
                include_granted_scopes='true'
            )
            st.session_state.auth_url = auth_url
        except Exception as e:
            st.error(f"Error initializing authentication: {str(e)}")
            return "", ""
    
    # Handle sign out
    if st.session_state.get('credentials') and st.sidebar.button("Sign out"):
        st.session_state.credentials = None
        st.session_state.sheet_id = ""
        st.session_state.auth_url = ""
        st.session_state.sheet_name = "Sheet1"
        st.query_params.clear()
        st.rerun()
    
    # Show authentication status and controls
    if st.session_state.get('credentials'):
        st.sidebar.success("✅ Signed in with Google")
    else:
        st.sidebar.warning("Not signed in")
        if st.session_state.get('auth_url'):
            st.sidebar.markdown(f"""
                <a href="{st.session_state.auth_url}" target="_self">
                    <button style="width: 100%; background-color: #4285F4; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; margin: 0.5rem 0;">
                        🔑 Sign in with Google
                    </button>
                </a>
            """, unsafe_allow_html=True)
    
    st.sidebar.markdown("---")
    
    # Show Google Sheet settings if authenticated
    if st.session_state.get('credentials'):
        st.sidebar.title("📋 Google Sheet Settings")
        
        # Sheet ID input
        sheet_id = st.sidebar.text_input(
            "Google Sheet ID",
            value=st.session_state.get('sheet_id', ''),
            help="The ID from your Google Sheet URL (the long string in the URL after /d/ and before /edit)",
            key="sheet_id_input"
        )
        
        # Sheet name input
        sheet_name = st.sidebar.text_input(
            "Sheet Name",
            value=st.session_state.get('sheet_name', 'Sheet1'),
            help="The name of the sheet tab in your Google Sheet",
            key="sheet_name_input"
        )
        
        # Update session state if values changed
        if sheet_id != st.session_state.get('sheet_id', ''):
            st.session_state.sheet_id = sheet_id
            st.rerun()
            
        if sheet_name != st.session_state.get('sheet_name', 'Sheet1'):
            st.session_state.sheet_name = sheet_name
            st.rerun()
        
        return sheet_id, sheet_name
    
    return "", ""


def get_flow():
    """Create and return a Flow instance for OAuth2."""
    try:
        # For Streamlit Cloud
        client_config = {
            "web": {
                "client_id": st.secrets["GOOGLE_CLIENT_ID"],
                "client_secret": st.secrets["GOOGLE_CLIENT_SECRET"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [st.secrets.get("REDIRECT_URI", "http://localhost:8501")]
            }
        }
        return Flow.from_client_config(
            client_config,
            scopes=SCOPES,
            redirect_uri=st.secrets.get("REDIRECT_URI", "http://localhost:8501")
        )
    except Exception as e:
        st.error("Error initializing OAuth flow. Please check your configuration.")
        st.stop()


def get_credentials():
    """Get valid user credentials from session state or prompt user to log in."""
    # Debug: Print current session state
    st.session_state.debug = st.session_state.get('debug', {})
    
    # Check if we have valid credentials in session state
    if st.session_state.get('credentials') and st.session_state.credentials.get('token'):
        try:
            creds = Credentials(
                token=st.session_state.credentials['token'],
                refresh_token=st.session_state.credentials.get('refresh_token'),
                token_uri=st.session_state.credentials.get('token_uri'),
                client_id=st.session_state.credentials.get('client_id'),
                client_secret=st.session_state.credentials.get('client_secret'),
                scopes=st.session_state.credentials.get('scopes')
            )

            # Refresh token if expired
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    st.session_state.credentials = {
                        'token': creds.token,
                        'refresh_token': creds.refresh_token or st.session_state.credentials.get('refresh_token'),
                        'token_uri': creds.token_uri,
                        'client_id': creds.client_id,
                        'client_secret': creds.client_secret,
                        'scopes': creds.scopes
                    }
                    st.session_state.debug['last_refresh'] = 'Token refreshed successfully'
                except Exception as e:
                    st.session_state.debug['refresh_error'] = str(e)
                    st.session_state.credentials = None
                    st.session_state.auth_url = ""
                    st.rerun()

            st.session_state.debug['auth_status'] = 'Using existing credentials'
            return creds
            
        except Exception as e:
            st.session_state.debug['init_error'] = str(e)
            st.session_state.credentials = None
            st.session_state.auth_url = ""
            st.rerun()

    # Handle OAuth2 callback
    query_params = st.query_params
    if 'code' in query_params:
        try:
            # Get the authorization code
            code = query_params['code']
            st.session_state.debug['oauth_flow'] = 'Processing OAuth callback'
            
            # Get the flow and exchange the code for tokens
            flow = get_flow()
            flow.fetch_token(code=code)
            creds = flow.credentials
            
            # Store the credentials in session state
            st.session_state.credentials = {
                'token': creds.token,
                'refresh_token': creds.refresh_token,
                'token_uri': creds.token_uri,
                'client_id': creds.client_id,
                'client_secret': creds.client_secret,
                'scopes': creds.scopes
            }
            
            # Clear the code from the URL and force a rerun
            st.session_state.debug['oauth_success'] = 'Authentication successful'
            st.query_params.clear()
            st.rerun()
            
        except Exception as e:
            st.session_state.debug['oauth_error'] = str(e)
            st.session_state.credentials = None
            st.session_state.auth_url = ""
            st.rerun()
    
    # If we get here, we need to authenticate
    if not st.session_state.get('auth_url'):
        try:
            flow = get_flow()
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                prompt='consent',
                include_granted_scopes='true'
            )
            st.session_state.auth_url = auth_url
            st.session_state.debug['auth_flow'] = 'Generated new auth URL'
        except Exception as e:
            st.session_state.debug['auth_url_error'] = str(e)
    
    # Debug information (comment out in production)
    if st.session_state.debug:
        with st.sidebar.expander("Debug Info"):
            st.json(st.session_state.debug)
    
    return None


def setup_driver():
    """Set up and return an Edge WebDriver instance using local WebDriver."""
    try:
        # Path to the local WebDriver
        driver_dir = os.path.join(os.path.dirname(__file__), 'drivers')
        driver_path = os.path.join(driver_dir, 'msedgedriver.exe')

        # Check if WebDriver exists
        if not os.path.exists(driver_path):
            raise FileNotFoundError(
                f"msedgedriver.exe not found in {driver_dir}. "
                "Please download it from: https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/"
            )

        # Set up Edge options
        edge_options = EdgeOptions()

        # Add arguments for better compatibility
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("--disable-dev-shm-usage")
        edge_options.add_argument("--disable-gpu")
        edge_options.add_argument("--window-size=1920,1080")

        # Run in non-headless mode for debugging
        # edge_options.add_argument("--headless")

        # Set the path to Edge browser
        edge_binary = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        if os.path.exists(edge_binary):
            edge_options.binary_location = edge_binary

        # Initialize the WebDriver with local path
        service = Service(executable_path=driver_path)
        driver = webdriver.Edge(service=service, options=edge_options)

        # Set page load timeout
        driver.set_page_load_timeout(30)

        return driver

    except Exception as e:
        st.error("Failed to initialize Edge WebDriver. Please try the following:")
        st.error(f"Error details: {str(e)}")
        st.info("1. Ensure Microsoft Edge is installed and up to date")
        st.info("2. Make sure 'msedgedriver.exe' is in the 'drivers' folder")
        st.info(
            "3. Download the correct WebDriver version from: https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/")
        if "This version of EdgeDriver only supports Edge version" in str(e):
            st.info(
                "\nIt looks like there's a version mismatch. Please update your Edge browser to the latest version.")
        raise


def get_sheet_data(sheet_id, sheet_name, range_name):
    """Fetch data from Google Sheets."""
    if not sheet_id:
        st.warning("Please enter a Google Sheet ID")
        return None

    creds = get_credentials()
    if not creds:
        return None

    try:
        service = build('sheets', 'v4', credentials=creds)
        sheet = service.spreadsheets()
        result = sheet.values().get(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!{range_name}"
        ).execute()
        values = result.get('values', [])

        if not values:
            st.info("No data found in the specified range.")
            return pd.DataFrame()

        # If we have headers in the first row
        if len(values) > 1:
            return pd.DataFrame(values[1:], columns=values[0])
        return pd.DataFrame(values)
    except Exception as e:
        st.error(f"Error accessing Google Sheet: {str(e)}")
        return None


def update_sheet(sheet_id, sheet_name, range_name, values):
    """Update Google Sheet with new values."""
    if not sheet_id:
        st.warning("Please enter a Google Sheet ID")
        return False

    creds = get_credentials()
    if not creds:
        return False

    try:
        service = build('sheets', 'v4', credentials=creds)
        body = {'values': values}
        result = service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{sheet_name}!{range_name}",
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        st.success("Successfully updated Google Sheet!")
        return True
    except Exception as e:
        st.error(f"Error updating Google Sheet: {str(e)}")
        return False


def track_ups_package(awb_number):
    """Track a package on UPS website and return the status using Edge WebDriver."""
    driver = None
    try:
        driver = setup_driver()
        driver.get("https://www.ups.com/track")

        # Accept cookies if the banner appears
        try:
            accept_cookies = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "banner-button-accept"))
            )
            accept_cookies.click()
            time.sleep(2)  # Wait for the cookie banner to disappear
        except (TimeoutException, NoSuchElementException):
            pass  # Cookie banner not found, continue

        # Wait for the page to be fully loaded
        time.sleep(3)

        # Try to find and close any popups or overlays
        try:
            overlays = driver.find_elements(By.CSS_SELECTOR, ".overlay, .modal, [role='dialog'], .popup")
            for overlay in overlays:
                try:
                    if overlay.is_displayed():
                        close_buttons = overlay.find_elements(By.CSS_SELECTOR,
                                                              "[aria-label='Close'], .close, .btn-close")
                        for btn in close_buttons:
                            if btn.is_displayed():
                                driver.execute_script("arguments[0].click();", btn)
                                time.sleep(1)
                except:
                    continue
        except:
            pass

        # Find and fill the tracking number input
        try:
            # First, try to find the tracking input field
            tracking_input = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, "stApp_trackingNumber"))
            )

            # Scroll to the input field and clear it
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", tracking_input)
            time.sleep(1)

            # Clear the input field and enter the AWB number
            tracking_input.clear()
            tracking_input.send_keys(awb_number)

            # Find and click the Track button
            track_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.ups-cta_primary, #stApp_btnTrack"))
            )

            # Scroll to the button and click it
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", track_button)
            time.sleep(1)

            # Try to click using JavaScript if normal click doesn't work
            try:
                track_button.click()
            except:
                driver.execute_script("arguments[0].click();", track_button)

        except Exception as e:
            st.warning(f"Could not find tracking input: {str(e)}")
            return f"Error: Could not find tracking input"

        # Wait for the tracking results to load
        time.sleep(5)

        try:
            # Wait for the status element to appear - looking for the delivered status
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR,
                                                "track-details-estimation, .ups-txt_teal.ups-txt_bold, [id^='st_App_']"))
            )

            # Try to get the delivered status first
            try:
                # Look for the "Delivered On" status
                status_element = driver.find_element(By.CSS_SELECTOR,
                                                     "#st_App_DelvdLabel, .ups-txt_teal.ups-txt_bold")
                status = status_element.text.strip()

                # If we found "Delivered On", try to get the date and time
                if "Delivered" in status:
                    try:
                        date_element = driver.find_element(By.CSS_SELECTOR,
                                                           "#st_App_PkgStsMonthNum")
                        date_text = date_element.text.strip()
                        status = f"{status} {date_text}"
                    except:
                        pass

            except NoSuchElementException:
                # If not delivered, look for other status indicators
                try:
                    status_element = driver.find_element(By.CSS_SELECTOR,
                                                         ".ups-track-status-details, .status, .status-ribbon, [class*='status-']")
                    status = status_element.text.strip()
                except:
                    status = "Status found but could not be determined"

            # Take a screenshot for debugging
            screenshot_path = os.path.join(os.path.dirname(__file__), f"ups_success_{awb_number}.png")
            driver.save_screenshot(screenshot_path)

            return f"UPS: {status}"

        except (TimeoutException, NoSuchElementException):
            # If we can't find the status, take a screenshot for debugging
            screenshot_path = os.path.join(os.path.dirname(__file__), f"ups_debug_{awb_number}.png")
            driver.save_screenshot(screenshot_path)

            # Try to get any error message
            error_messages = driver.find_elements(By.CSS_SELECTOR,
                                                  ".error-message, .error, .alert.alert-danger, .notification--error, "
                                                  "[role='alert'], .tracking-error, .status-text--error"
                                                  )

            if error_messages:
                status = f"Error: {error_messages[0].text.strip()}"
            else:
                # Try to get the page text as a last resort
                body_text = driver.find_element(By.TAG_NAME, 'body').text
                if "not found" in body_text.lower() or "no information" in body_text.lower():
                    status = "Package not found"
                elif "invalid" in body_text.lower():
                    status = "Invalid tracking number"
                else:
                    status = f"Status not found. Check {screenshot_path} for details"

            st.warning(f"Status not found. Debug screenshot saved to: {screenshot_path}")
            return f"UPS: {status}"

    except Exception as e:
        # Save screenshot on error
        if driver:
            error_screenshot = os.path.join(os.path.dirname(__file__), f"ups_error_{awb_number}.png")
            driver.save_screenshot(error_screenshot)
            st.error(f"Error screenshot saved to: {error_screenshot}")

        st.error(f"Error tracking UPS package {awb_number}: {str(e)}")
        return f"Error: {str(e)}"
    finally:
        if driver:
            try:
                # Add a small delay before quitting to see the result
                time.sleep(2)
                driver.quit()
            except:
                pass


def track_fedex_package(awb_number):
    """Track a package on FedEx website and return the status using Edge WebDriver."""
    driver = None
    try:
        driver = setup_driver()

        # Use the main FedEx India homepage
        driver.get("https://www.fedex.com/en-in/home.html")
        time.sleep(5)  # Give it time to load

        # Handle the cookie banner
        try:
            # Wait for the page to load
            time.sleep(3)

            # Scroll to the bottom where the cookie banner is
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)

            # Try to find and click the "ACCEPT ALL COOKIES" button
            try:
                # First try with the exact button text
                accept_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'ACCEPT ALL COOKIES')]"))
                )
                # Scroll the button into view and click it
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", accept_button)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", accept_button)
                print("Clicked 'ACCEPT ALL COOKIES' button")
                time.sleep(2)
            except Exception as e:
                print(f"Could not find 'ACCEPT ALL COOKIES' button: {str(e)}")

                # Try finding the cookie banner container and then the button inside it
                try:
                    cookie_banner = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-test-id='fxg-cookie-banner']"))
                    )
                    # Scroll the banner into view
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cookie_banner)
                    time.sleep(1)

                    # Try to find the accept button inside the banner
                    try:
                        accept_btn = cookie_banner.find_element(By.XPATH,
                                                                ".//button[contains(., 'ACCEPT ALL COOKIES')]")
                        driver.execute_script("arguments[0].click();", accept_btn)
                        print("Clicked 'ACCEPT ALL COOKIES' button inside banner")
                        time.sleep(2)
                    except:
                        # If we can't find the exact button, try any button in the banner
                        try:
                            buttons = cookie_banner.find_elements(By.TAG_NAME, "button")
                            if buttons:
                                driver.execute_script("arguments[0].click();", buttons[-1])  # Click the last button
                                print("Clicked a button in the cookie banner")
                                time.sleep(2)
                        except Exception as e:
                            print(f"Could not click any button in the banner: {str(e)}")
                            raise
                except Exception as e:
                    print(f"Could not find cookie banner: {str(e)}")
                    # Take a screenshot to see what's on the screen
                    driver.save_screenshot("fedex_cookie_error.png")
                    print("Saved screenshot as fedex_cookie_error.png")
        except Exception as e:
            print(f"Error handling cookies: {str(e)}")
            # Continue execution even if cookie handling fails

        # Navigate to tracking page
        try:
            tracking_link = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a[data-test-id='fxg-link-/en-in/tracking.html']"))
            )
            driver.execute_script("arguments[0].click();", tracking_link)
            time.sleep(3)
        except Exception as e:
            print(f"Could not navigate to tracking page: {str(e)}")
            driver.get("https://www.fedex.com/en-in/tracking.html")
            time.sleep(3)
            # Wait for the page to load and handle any popups
        time.sleep(3)

        # Find and fill the tracking number input
        try:
            tracking_input = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.ID, "trackingnumber"))
            )

            # Clear and enter the tracking number
            tracking_input.clear()
            tracking_input.send_keys(awb_number)

            # Find and click the track button
            track_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit'], .btn-primary, .track-button"))
            )
            driver.execute_script("arguments[0].click();", track_button)

            # Wait for results to load
            time.sleep(5)

            # Try to get the status
            try:
                # Wait for the tracking status to appear
                status_element = WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[data-test-id='tracking-status']"))
                )

                # Get the status text
                status = status_element.text.strip()

                # Try to get additional details if available
                try:
                    details = driver.find_elements(By.CSS_SELECTOR, "[data-test-id='tracking-details']")
                    if details:
                        status += " - " + " ".join([d.text.strip() for d in details if d.text.strip()])
                except:
                    pass

                # Take a screenshot for reference
                screenshot_path = os.path.join(os.path.dirname(__file__), f"fedex_status_{awb_number}.png")
                driver.save_screenshot(screenshot_path)

                return f"FedEx: {status}"

            except TimeoutException:
                # If we can't find the status element, try to get any error message
                try:
                    error_element = driver.find_element(By.CSS_SELECTOR, "[data-test-id='error-message']")
                    return f"FedEx Error: {error_element.text.strip()}"
                except:
                    pass

                # Take a screenshot of the current page for debugging
                error_screenshot = os.path.join(os.path.dirname(__file__), f"fedex_error_{awb_number}.png")
                driver.save_screenshot(error_screenshot)

                # Try to get the page source for debugging
                page_source = driver.page_source[:500]  # Get first 500 chars of page source
                return f"FedEx: Could not determine status. Check {error_screenshot} for details"

        except Exception as e:
            # Save screenshot of the error
            if driver:
                error_screenshot = os.path.join(os.path.dirname(__file__), f"fedex_error_{awb_number}.png")
                driver.save_screenshot(error_screenshot)
                return f"FedEx Error: {str(e)}. Screenshot saved to {error_screenshot}"
            return f"FedEx Error: {str(e)}"

    except Exception as e:
        return f"FedEx Error: {str(e)}"

    finally:
        if driver:
            try:
                time.sleep(2)
                driver.quit()
            except:
                pass


def track_dhl_package(awb_number):
    """Track a package on DHL website and return the status using Edge WebDriver."""
    driver = None
    try:
        driver = setup_driver()
        driver.get("https://www.dhl.com/in-en/home/tracking.html")

        # Accept cookies if the banner appears
        try:
            accept_cookies = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
            )
            accept_cookies.click()
            time.sleep(2)  # Wait for the cookie banner to disappear
        except (TimeoutException, NoSuchElementException):
            pass  # Cookie banner not found, continue

        # Wait for the page to be fully loaded
        time.sleep(3)

        # Try to find and close any popups or overlays
        try:
            overlays = driver.find_elements(By.CSS_SELECTOR, ".overlay, .modal, [role='dialog'], .popup")
            for overlay in overlays:
                try:
                    if overlay.is_displayed():
                        close_buttons = overlay.find_elements(By.CSS_SELECTOR,
                                                              "[aria-label='Close'], .close, .btn-close")
                        for btn in close_buttons:
                            if btn.is_displayed():
                                driver.execute_script("arguments[0].click();", btn)
                                time.sleep(1)
                except:
                    continue
        except:
            pass

        # Wait for the tracking input field and enter AWB number
        tracking_input = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "input.js--tracking--input-field, #tracking-number, [name='tracking-number']"))
        )

        # Scroll to the input field and clear it
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'})", tracking_input)
        time.sleep(1)

        # Clear the input field and enter the AWB number
        tracking_input.clear()
        tracking_input.send_keys(awb_number)

        # Find and click the track button using JavaScript
        try:
            # First try to find and click the track button directly
            track_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR,
                                            "button[type='submit'], "
                                            "button.js--tracking--input-submit, "
                                            "#tracking-button, "
                                            ".tracking-form button[type='submit']"))
            )
            driver.execute_script("arguments[0].click();", track_button)
        except:
            # If direct click fails, try submitting the form
            try:
                track_form = driver.find_element(By.CSS_SELECTOR,
                                                 "form.js--tracking--input-form, form[action*='track']")
                driver.execute_script("arguments[0].submit();", track_form)
            except Exception as e:
                st.warning(f"Could not submit form: {str(e)}")

        # Wait for the tracking results to load
        time.sleep(5)  # Give the page time to load results

        try:
            # Wait for the status element to appear with the specific class from the screenshot
            status_element = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR,
                                                "h2.c-tracking-result--status-copy-message"))
            )

            # Get the status text and clean it up
            status = status_element.text.strip()

            # Remove the tracking code part if it exists
            if "Tracking Code:" in status:
                status = status.split("Tracking Code:")[0].strip()

            # If status is still empty, try to get text from the element itself
            if not status:
                status = status_element.get_attribute('textContent').strip()

            # Take a screenshot for debugging
            screenshot_path = os.path.join(os.path.dirname(__file__), f"dhl_success_{awb_number}.png")
            driver.save_screenshot(screenshot_path)

            return f"DHL: {status}"

        except (TimeoutException, NoSuchElementException):
            # If we can't find the status, take a screenshot for debugging
            screenshot_path = os.path.join(os.path.dirname(__file__), f"dhl_debug_{awb_number}.png")
            driver.save_screenshot(screenshot_path)

            # Try to get any error message
            error_messages = driver.find_elements(By.CSS_SELECTOR,
                                                  ".error-message, .error, .alert.alert-danger, .notification--error, "
                                                  "[role='alert'], .tracking-error, .status-text--error"
                                                  )

            if error_messages:
                status = f"Error: {error_messages[0].text.strip()}"
            else:
                # Try to get the page text as a last resort
                body_text = driver.find_element(By.TAG_NAME, 'body').text
                if "not found" in body_text.lower():
                    status = "Package not found"
                elif "invalid" in body_text.lower():
                    status = "Invalid tracking number"
                else:
                    status = f"Status not found. Check {screenshot_path} for details"

            st.warning(f"Status not found. Debug screenshot saved to: {screenshot_path}")
            return f"DHL: {status}"

    except Exception as e:
        # Save screenshot on error
        if driver:
            error_screenshot = os.path.join(os.path.dirname(__file__), f"dhl_error_{awb_number}.png")
            driver.save_screenshot(error_screenshot)
            st.error(f"Error screenshot saved to: {error_screenshot}")

        st.error(f"Error tracking package {awb_number}: {str(e)}")
        return f"Error: {str(e)}"
    finally:
        if driver:
            try:
                # Add a small delay before quitting to see the result
                time.sleep(2)
                driver.quit()
            except:
                pass


def main():
    # Set page config
    st.set_page_config(
        page_title="DHL Tracking Automation",
        page_icon="🚚",
        layout="wide"
    )

    # Process OAuth callback FIRST, before showing UI
    # This ensures credentials are stored in session state before display
    if 'code' in st.query_params:
        get_credentials()
        # After successful auth, get_credentials() clears query_params and reruns
        # So if we reach here on the callback rerun, credentials should be set

    # Show authentication UI
    sheet_id, sheet_name = show_auth_ui()

    # Main app
    st.title("🚚 DHL Tracking Automation")
    st.write("Track your DHL packages and update Google Sheets automatically.")

    # Only show the rest of the app if we're authenticated and have a sheet ID
    if not st.session_state.credentials:
        st.warning("Please sign in with Google to continue")
        if st.session_state.auth_url:
            st.link_button("🔑 Sign in with Google", st.session_state.auth_url)
        st.stop()

    if not sheet_id:
        st.info("👈 Please enter your Google Sheet ID in the sidebar")
        st.stop()

    # Test connection to Google Sheet
    if st.sidebar.button("🔍 Test Connection"):
        with st.spinner("Testing connection to Google Sheet..."):
            df = get_sheet_data(sheet_id, sheet_name, "A1:Z1")
            if df is not None:
                st.sidebar.success("✅ Successfully connected to Google Sheet!")
            else:
                st.sidebar.error(
                    "❌ Could not connect to Google Sheet. Please check your Sheet ID and sharing settings.")

    st.markdown("---")

    # Main tracking interface
    st.header("📦 Track Package")

    # Add tabs for different carriers
    tab1, tab2, tab3 = st.tabs(["DHL", "UPS", "FedEx"])

    with tab1:
        st.subheader("DHL Package Tracking")
        dhl_awb = st.text_input("Enter DHL AWB Number:", key="dhl_awb")
        if st.button("Track DHL Package"):
            if dhl_awb:
                with st.spinner(f"Tracking DHL package {dhl_awb}..."):
                    result = track_dhl_package(dhl_awb)
                    if result and 'status' in result:
                        st.success(f"Status: {result['status']}")
                        # Update Google Sheet
                        if st.session_state.credentials and sheet_id:
                            update_sheet(
                                sheet_id,
                                sheet_name,
                                "A1",
                                [["AWB", "Status", "Last Updated"],
                                 [dhl_awb, result['status'], pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')]]
                            )
            else:
                st.warning("Please enter a DHL AWB number")

    with tab2:
        st.subheader("UPS Package Tracking")
        ups_awb = st.text_input("Enter UPS Tracking Number:", key="ups_awb")
        if st.button("Track UPS Package"):
            if ups_awb:
                with st.spinner(f"Tracking UPS package {ups_awb}..."):
                    result = track_ups_package(ups_awb)
                    if result and 'status' in result:
                        st.success(f"Status: {result['status']}")
                        # Update Google Sheet
                        if st.session_state.credentials and sheet_id:
                            update_sheet(
                                sheet_id,
                                sheet_name,
                                "A1",
                                [["AWB", "Status", "Last Updated"],
                                 [ups_awb, result['status'], pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')]]
                            )
            else:
                st.warning("Please enter a UPS tracking number")

    with tab3:
        st.subheader("FedEx Package Tracking")
        fedex_awb = st.text_input("Enter FedEx Tracking Number:", key="fedex_awb")
        if st.button("Track FedEx Package"):
            if fedex_awb:
                with st.spinner(f"Tracking FedEx package {fedex_awb}..."):
                    result = track_fedex_package(fedex_awb)
                    if result and 'status' in result:
                        st.success(f"Status: {result['status']}")
                        # Update Google Sheet
                        if st.session_state.credentials and sheet_id:
                            update_sheet(
                                sheet_id,
                                sheet_name,
                                "A1",
                                [["AWB", "Status", "Last Updated"],
                                 [fedex_awb, result['status'], pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')]]
                            )
            else:
                st.warning("Please enter a FedEx tracking number")

    # Show recent tracking data
    st.markdown("---")
    st.header("📋 Recent Tracking Data")

    if st.button("🔄 Refresh Data"):
        st.experimental_rerun()

    df = get_sheet_data(sheet_id, sheet_name, "A1:Z1000")
    if df is not None and not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No tracking data found in the sheet. Track a package to get started!")


if __name__ == "__main__":
    # Check if we're running on Streamlit Cloud
    if os.environ.get('STREAMLIT_SERVER_RUNNING', '').lower() == 'true':
        # On Streamlit Cloud, we'll use the secrets
        if not all(key in st.secrets for key in ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"]):
            st.error("""
                Missing required Google OAuth2 configuration. Please set the following secrets in Streamlit Cloud:
                - GOOGLE_CLIENT_ID
                - GOOGLE_CLIENT_SECRET
                - REDIRECT_URI (optional, defaults to the app's URL)

                Follow the setup instructions in the README to configure these values.
            """)
            st.stop()
    else:
        main()
