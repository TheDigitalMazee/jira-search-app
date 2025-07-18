import os
import requests
from requests.auth import HTTPBasicAuth
import streamlit as st
from PIL import Image
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
import fitz  # PyMuPDF
import traceback
import time
from functools import wraps
from tenacity import retry, stop_after_attempt, wait_exponential

# ========== PAGE CONFIG ==========
st.set_page_config(
    page_title="Jira Search Pro",
    layout="centered",
    page_icon="🔍"
)

# ========== DEBUGGING SETUP ==========
DEBUG = False  # Set to False in production

def debug_log(message):
    if DEBUG:
        with st.sidebar.expander("Debug Log", expanded=False):
            st.write(message)

# ========== CONFIGURATION ==========
ENABLE_SEMANTIC_SEARCH = True
ENABLE_OCR = False
MAX_REQUESTS_PER_MINUTE = 30  # Jira Cloud standard rate limit

# ========== INITIALIZATION ==========
try:
    if ENABLE_SEMANTIC_SEARCH:
        from sentence_transformers import SentenceTransformer, util
        SEMANTIC_SEARCH_AVAILABLE = True
        
        @st.cache_resource
        def load_model():
            debug_log("Loading ML model...")
            return SentenceTransformer('all-MiniLM-L6-v2')
    else:
        SEMANTIC_SEARCH_AVAILABLE = False
except Exception as e:
    debug_log(f"Model loading failed: {str(e)}")
    SEMANTIC_SEARCH_AVAILABLE = False

# ========== RATE LIMITING DECORATOR ==========
def rate_limited(max_per_minute):
    interval = 60.0 / float(max_per_minute)
    def decorator(func):
        last_time = [0.0]
        @wraps(func)
        def rate_limited_function(*args, **kwargs):
            elapsed = time.time() - last_time[0]
            wait_time = interval - elapsed
            if wait_time > 0:
                time.sleep(wait_time)
            last_time[0] = time.time()
            return func(*args, **kwargs)
        return rate_limited_function
    return decorator

# ========== CORE FUNCTIONS ==========
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
@rate_limited(MAX_REQUESTS_PER_MINUTE)
@st.cache_data(ttl=3600)
def search_jira_issues(base_url, query, auth_credentials, max_results=50):
    debug_log(f"Searching Jira with query: {query}")
    try:
        session = requests.Session()
        session.auth = HTTPBasicAuth(auth_credentials['username'], auth_credentials['password'])
        session.headers.update({
            "Accept": "application/json",
            "User-Agent": "JiraSearchPro/1.0"
        })
        
        url = f"{base_url}/rest/api/2/search"
        params = {
            "jql": f'text~"{query}" ORDER BY updated DESC',
            "maxResults": max_results,
            "fields": "summary,description,comment,status,attachment,labels"
        }
        
        debug_log(f"Request URL: {url}")
        debug_log(f"Params: {params}")
        
        response = session.get(url, params=params, timeout=30)
        
        # Handle specific error cases
        if response.status_code == 403:
            debug_log(f"403 Forbidden - Response: {response.text}")
            st.cache_data.clear()  # Clear cached results on auth failure
            st.error("Access denied. Please check your API token and permissions.")
            return []
        elif response.status_code == 429:
            debug_log("Rate limit exceeded")
            st.warning("Jira rate limit exceeded. Please wait a minute and try again.")
            return []
            
        response.raise_for_status()
        
        debug_log(f"Response status: {response.status_code}")
        return response.json().get("issues", [])
        
    except requests.exceptions.RequestException as e:
        debug_log(f"Search error: {traceback.format_exc()}")
        if isinstance(e, requests.exceptions.HTTPError):
            if e.response.status_code == 403:
                st.error("Access denied. Please verify your API token has proper permissions.")
            else:
                st.error(f"HTTP Error: {str(e)}")
        else:
            st.error(f"Search failed: {str(e)}")
        return []
    except Exception as e:
        debug_log(f"Unexpected error: {traceback.format_exc()}")
        st.error(f"An unexpected error occurred: {str(e)}")
        return []

# ========== UI COMPONENTS ==========
def show_search_form():
    with st.form("search_form"):
        base_url = st.text_input("Jira Base URL", placeholder="https://your-company.atlassian.net")
        username = st.text_input("Username or Email")
        api_token = st.text_input("API Token", type="password")
        query = st.text_input("Search Query")
        submitted = st.form_submit_button("Search")
        
        if submitted:
            if not all([base_url, username, api_token, query]):
                st.warning("Please fill all fields")
                return None
            return {
                "base_url": base_url,
                "auth_credentials": {
                    'username': username,
                    'password': api_token
                },
                "query": query
            }
    return None

def get_status_color(status_name):
    """Returns a color based on status name"""
    status_name = status_name.lower()
    if 'done' in status_name or 'complete' in status_name:
        return "🟢"  # Green circle
    elif 'progress' in status_name or 'in progress' in status_name:
        return "🟡"  # Yellow circle
    elif 'backlog' in status_name or 'todo' in status_name:
        return "⚪"  # White circle
    elif 'blocked' in status_name or 'stop' in status_name:
        return "🔴"  # Red circle
    else:
        return "🔵"  # Blue circle for other statuses

def display_results(issues, base_url):
    if not issues:
        st.info("No issues found")
        return
    
    debug_log(f"Displaying {len(issues)} results")
    
    for issue in issues[:10]:  # Show top 10 results
        status_name = issue['fields']['status']['name']
        status_emoji = get_status_color(status_name)
        
        with st.expander(f"{status_emoji} {issue['key']}: {issue['fields']['summary']} ({status_name})"):
            col1, col2 = st.columns([1, 3])
            with col1:
                st.write(f"**Status:** {status_name}")
                if 'labels' in issue['fields'] and issue['fields']['labels']:
                    st.write(f"**Labels:** {', '.join(issue['fields']['labels'])}")
            with col2:
                st.markdown(f"[Open in Jira ↗]({base_url}/browse/{issue['key']})", unsafe_allow_html=True)
            
            st.divider()
            st.subheader("Description")
            st.write(issue['fields'].get('description', 'No description provided'))
            
            if 'comment' in issue['fields'] and issue['fields']['comment']['comments']:
                st.divider()
                st.subheader("Recent Comments")
                for comment in issue['fields']['comment']['comments'][-3:]:  # Show last 3 comments
                    st.write(f"**{comment['author']['displayName']}** ({comment['updated'][:10]}):")
                    st.write(comment['body'])

# ========== MAIN APP ==========
def main():
    st.title("🔍 Jira Search Pro")
    
    # Show debug info if enabled
    if DEBUG:
        with st.sidebar:
            st.subheader("Debug Information")
            st.write(f"Semantic Search: {'Enabled' if SEMANTIC_SEARCH_AVAILABLE else 'Disabled'}")
            st.write(f"Rate Limit: {MAX_REQUESTS_PER_MINUTE} requests/minute")
    
    # Search form
    search_params = show_search_form()
    
    # Process search
    if search_params:
        with st.spinner("Searching Jira..."):
            try:
                debug_log("Starting search...")
                
                # First verify credentials with a simple request
                test_session = requests.Session()
                test_session.auth = HTTPBasicAuth(
                    search_params['auth_credentials']['username'],
                    search_params['auth_credentials']['password']
                )
                test_url = f"{search_params['base_url']}/rest/api/2/myself"
                
                try:
                    test_response = test_session.get(test_url, timeout=10)
                    if test_response.status_code == 403:
                        st.cache_data.clear()
                        st.error("Authentication failed. Please check your credentials and API token.")
                        return
                    test_response.raise_for_status()
                except requests.exceptions.RequestException as e:
                    st.cache_data.clear()
                    st.error(f"Authentication test failed: {str(e)}")
                    return
                
                # If auth test passed, proceed with search
                issues = search_jira_issues(
                    search_params["base_url"],
                    search_params["query"],
                    search_params["auth_credentials"]
                )
                
                display_results(issues, search_params["base_url"])
                
            except Exception as e:
                debug_log(f"Main execution error: {traceback.format_exc()}")
                st.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()
