import os
import requests
from requests.auth import HTTPBasicAuth
import streamlit as st
from PIL import Image
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
import fitz  # PyMuPDF
import traceback

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

# ========== CORE FUNCTIONS ==========
@st.cache_data(ttl=3600)
def search_jira_issues(base_url, query, _auth, max_results=50):
    debug_log(f"Searching Jira with query: {query}")
    try:
        url = f"{base_url}/rest/api/2/search"
        headers = {"Accept": "application/json"}
        params = {
            "jql": f'text~"{query}" ORDER BY updated DESC',
            "maxResults": max_results,
            "fields": "summary,description,comment,status,attachment,labels"
        }
        
        debug_log(f"Request URL: {url}")
        debug_log(f"Params: {params}")
        
        response = requests.get(url, headers=headers, params=params, auth=_auth, timeout=30)
        response.raise_for_status()
        
        debug_log(f"Response status: {response.status_code}")
        return response.json().get("issues", [])
        
    except Exception as e:
        debug_log(f"Search error: {traceback.format_exc()}")
        st.error(f"Search failed: {str(e)}")
        return []

# ========== UI COMPONENTS ==========
def show_search_form():
    with st.form("search_form"):
        base_url = st.text_input("Jira Base URL", placeholder="https://your-company.atlassian.net")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        query = st.text_input("Search Query")
        submitted = st.form_submit_button("Search")
        
        if submitted:
            if not all([base_url, username, password, query]):
                st.warning("Please fill all fields")
                return None
            return {
                "base_url": base_url,
                "auth": HTTPBasicAuth(username, password),
                "query": query
            }
    return None

def display_results(issues, base_url):
    if not issues:
        st.info("No issues found")
        return
    
    debug_log(f"Displaying {len(issues)} results")
    
    for issue in issues[:10]:  # Show top 10 results
        with st.expander(f"{issue['key']}: {issue['fields']['summary']}"):
            st.write(f"Status: {issue['fields']['status']['name']}")
            st.write(issue['fields'].get('description', 'No description'))
            st.markdown(f"[Open in Jira]({base_url}/browse/{issue['key']})")

# ========== MAIN APP ==========
def main():
    st.title("🔍 Jira Search Pro")
    
    # Show debug info if enabled
    if DEBUG:
        with st.sidebar:
            st.subheader("Debug Information")
            st.write(f"Semantic Search: {'Enabled' if SEMANTIC_SEARCH_AVAILABLE else 'Disabled'}")
    
    # Search form
    search_params = show_search_form()
    
    # Process search
    if search_params:
        with st.spinner("Searching Jira..."):
            try:
                debug_log("Starting search...")
                issues = search_jira_issues(
                    search_params["base_url"],
                    search_params["query"],
                    search_params["auth"]
                )
                
                display_results(issues, search_params["base_url"])
                
            except Exception as e:
                debug_log(f"Main execution error: {traceback.format_exc()}")
                st.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()
