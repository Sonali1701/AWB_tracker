# First, let's update the imports at the top of the file
import os
import streamlit as st
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
import google.oauth2.credentials
import json
import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import re
from urllib.parse import urlparse, parse_qs
from typing import Optional, Tuple, Dict, Any

# OAuth2 configuration
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
TOKEN_PICKLE = 'token.pickle'

# Initialize session state
if 'credentials' not in st.session_state:
    st.session_state.credentials = None
if 'sheet_id' not in st.session_state:
    st.session_state.sheet_id = ""
if 'sheet_name' not in st.session_state:
    st.session_state.sheet_name = "Sheet1"


def get_flow() -> Flow:
    """Create and return a Flow instance for OAuth2."""
    # For Streamlit Cloud
    if os.environ.get('STREAMLIT_SERVER_RUNNING', '').lower() == 'true':
        # Get the current URL for the redirect_uri
        current_url = st.query_params.get('_path', '')
        redirect_uri = f"https://sonali1701-awb-tracker-app-mzkwie.streamlit.app{current_url}"

        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": st.secrets["google_oauth"]["client_id"],
                    "client_secret": st.secrets["google_oauth"]["client_secret"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [redirect_uri]
                }
            },
            scopes=SCOPES,
            redirect_uri=redirect_uri
        )
        return flow
    else:
        # Local development
        return Flow.from_client_secrets_file(
            'client_secret.json',
            scopes=SCOPES,
            redirect_uri='http://localhost:8501'
        )


def handle_oauth_callback():
    """Handle the OAuth callback and store credentials."""
    if 'code' in st.query_params and not st.session_state.get('processing_callback', False):
        st.session_state.processing_callback = True
        try:
            flow = get_flow()
            flow.fetch_token(authorization_response=st.query_params.url)
            st.session_state.credentials = {
                'token': flow.credentials.token,
                'refresh_token': flow.credentials.refresh_token,
                'token_uri': flow.credentials.token_uri,
                'client_id': flow.credentials.client_id,
                'client_secret': flow.credentials.client_secret,
                'scopes': flow.credentials.scopes
            }
            # Clear the code from URL to prevent re-processing
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Authentication failed: {str(e)}")
            st.session_state.processing_callback = False
            st.stop()


def show_auth_ui() -> Tuple[str, str]:
    """Show authentication UI and handle authentication state."""
    st.sidebar.title("🔐 Authentication")

    # Check if we're authenticated
    if st.session_state.get('credentials'):
        st.sidebar.success("✅ Signed in with Google")
        if st.sidebar.button("Sign out"):
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()
        return st.session_state.get('sheet_id', ""), st.session_state.get('sheet_name', "Sheet1")

    # If not authenticated, show sign in button
    st.sidebar.warning("Not signed in")
    try:
        flow = get_flow()
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            prompt='consent',
            include_granted_scopes='true'
        )
        st.session_state.auth_url = auth_url
    except Exception as e:
        st.sidebar.error(f"Error initializing authentication: {str(e)}")
        return "", ""

    if st.sidebar.button("🔑 Sign in with Google"):
        st.session_state.processing_auth = True
        st.rerun()

    return "", ""


def main():
    # Set page config with additional security configurations
    st.set_page_config(
        page_title="DHL Tracking Automation",
        page_icon="🚚",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Add CSP headers to handle security policies
    st.markdown("""
        <meta http-equiv="Content-Security-Policy" 
              content="default-src 'self' https: 'unsafe-inline' 'unsafe-eval' 
                      https://*.googleapis.com https://*.google.com https://*.segment.com https://*.google-analytics.com;
                      img-src 'self' https: data:;
                      media-src 'self' https: data:;
                      frame-src 'self' https: data:;">
    """, unsafe_allow_html=True)

    # Handle OAuth callback first
    if 'code' in st.query_params:
        handle_oauth_callback()

    # Show authentication UI
    sheet_id, sheet_name = show_auth_ui()

    # Only show the rest of the app if we're authenticated
    if not st.session_state.get('credentials'):
        st.warning("Please sign in with Google to continue")
        if st.session_state.get('auth_url'):
            st.link_button("🔑 Sign in with Google", st.session_state.auth_url)
        st.stop()

    # Rest of your main function...
    st.title("🚚 DHL Tracking Automation")
    st.write("Track your DHL packages and update Google Sheets automatically.")

    # Add your existing app code here...
    # Make sure to update any references to credentials to use st.session_state.credentials


if __name__ == "__main__":
    main()
