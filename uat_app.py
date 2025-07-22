import requests
from requests.auth import HTTPBasicAuth
import streamlit as st
from PIL import Image
import pytesseract
import io
from datetime import datetime, timedelta, timezone
import base64

# Configure Tesseract path for Streamlit Cloud
pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

# ========== CONSTANTS ==========
PROJECT_LIST = ["BCC", "RBOC", "BDATAS", "CSR"]
TIME_FRAMES = {
    "Last 7 days": 7,
    "Last 30 days": 30,
    "Last year": 365
}

# ========== SESSION STATE MANAGEMENT ==========
def init_session_state():
    if 'zoom_image' not in st.session_state:
        st.session_state.zoom_image = None
    if 'search_results' not in st.session_state:
        st.session_state.search_results = None
    if 'auth' not in st.session_state:
        st.session_state.auth = None

# ========== CORE FUNCTIONS ==========
def search_jira(base_url, auth, query, projects, time_frame):
    jql = f'text ~ "{query}"'
    if projects:
        jql += f' AND project IN ({",".join(projects)})'
    if time_frame in TIME_FRAMES:
        jql += f' AND created >= -{TIME_FRAMES[time_frame]}d'
    
    try:
        response = requests.get(
            f"{base_url}/rest/api/2/search",
            auth=auth,
            params={
                "jql": jql,
                "maxResults": 50,
                "fields": "summary,description,attachment,created,updated"
            },
            timeout=15
        )
        response.raise_for_status()
        return response.json().get("issues", [])
    except Exception as e:
        st.error(f"Jira API Error: {str(e)}")
        return []

@st.cache_data(show_spinner=False)
def extract_text(_auth_token, image_url):
    try:
        username, password = _auth_token.split("|")
        auth = HTTPBasicAuth(username, password)
        
        response = requests.get(image_url, auth=auth, timeout=15)
        img = Image.open(io.BytesIO(response.content))
        return pytesseract.image_to_string(img)
    except Exception as e:
        st.error(f"OCR Error: {str(e)}")
        return ""

# ========== IMAGE HANDLING ==========
def get_image_base64(image_url, auth):
    """Get base64 encoded image with error handling"""
    try:
        response = requests.get(image_url, auth=auth, timeout=10)
        return base64.b64encode(response.content).decode("utf-8")
    except Exception as e:
        st.error(f"Failed to load image: {str(e)}")
        return None

def show_image_with_zoom(image_base64, filename, key_suffix):
    """Display image with reliable zoom functionality"""
    if not image_base64:
        return
    
    # Create unique keys for each image
    modal_key = f"modal_{key_suffix}"
    zoom_key = f"zoom_{key_suffix}"
    
    # Check if we should show zoomed view
    if st.session_state.get(zoom_key, False):
        # Display the zoomed image with a close button
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("◄ Back", key=f"back_{key_suffix}"):
                st.session_state[zoom_key] = False
                st.rerun()
        with col2:
            st.image(base64.b64decode(image_base64), use_column_width=True)
    else:
        # Display thumbnail that can be clicked to zoom
        if st.image(base64.b64decode(image_base64), width=200, 
                   caption=f"Click to zoom: {filename}"):
            st.session_state[zoom_key] = True
            st.rerun()

# ========== MAIN UI ==========
def show_search_page():
    st.title("🔍 Jira Search with OCR")
    
    with st.form("search_form"):
        base_url = st.text_input("Jira URL", placeholder="https://your-domain.atlassian.net")
        username = st.text_input("Username/Email")
        password = st.text_input("Password", type="password")
        
        query = st.text_input("Search term")
        projects = st.multiselect("Projects", PROJECT_LIST)
        time_frame = st.selectbox("Timeframe", list(TIME_FRAMES.keys()))
        search_images = st.checkbox("Search text in images (OCR)", True)
        
        if st.form_submit_button("Search"):
            if base_url and username and password and query:
                st.session_state.auth = HTTPBasicAuth(username, password)
                with st.spinner("Searching Jira..."):
                    st.session_state.search_results = search_jira(
                        base_url,
                        st.session_state.auth,
                        query,
                        projects,
                        time_frame
                    )
            else:
                st.warning("Please fill all required fields")

def show_results_page():
    st.title("🔍 Search Results")
    
    if st.button("◄ Back to Search"):
        st.session_state.search_results = None
        st.rerun()
    
    if not st.session_state.search_results:
        st.warning("No results to display")
        return
    
    st.success(f"Found {len(st.session_state.search_results)} issues")
    auth_token = f"{st.session_state.auth.username}|{st.session_state.auth.password}"
    
    for issue in st.session_state.search_results:
        with st.expander(f"{issue['key']}: {issue['fields']['summary']}"):
            st.write(f"**Created:** {issue['fields']['created'][:10]}")
            st.write(issue['fields'].get('description', 'No description'))
            
            if 'attachment' in issue['fields']:
                st.subheader("Attachments")
                for att in issue['fields']['attachment']:
                    if att['mimeType'].startswith('image/'):
                        with st.container(border=True):
                            st.write(f"**{att['filename']}**")
                            
                            # Get image data
                            image_base64 = get_image_base64(att['content'], st.session_state.auth)
                            
                            # Display image with zoom
                            if image_base64:
                                show_image_with_zoom(
                                    image_base64, 
                                    att['filename'],
                                    att['id']  # Unique key suffix
                                )
                            
                            # OCR functionality
                            if search_images:
                                if st.button(f"Run OCR on {att['filename']}", 
                                           key=f"ocr_{att['id']}"):
                                    with st.spinner("Extracting text..."):
                                        text = extract_text(auth_token, att['content'])
                                        st.text_area("Extracted Text", 
                                                    text, 
                                                    height=150,
                                                    key=f"text_{att['id']}")
                            
                            # Download button
                            if image_base64:
                                st.download_button(
                                    f"Download {att['filename']}",
                                    data=base64.b64decode(image_base64),
                                    file_name=att['filename'],
                                    key=f"dl_{att['id']}"
                                )

# ========== APP CONTROL ==========
def main():
    init_session_state()
    
    if st.session_state.search_results is None:
        show_search_page()
    else:
        show_results_page()

if __name__ == "__main__":
    main()
