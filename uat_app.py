# app.py - Enhanced with Image Zoom and Better Error Handling
import requests
from requests.auth import HTTPBasicAuth
import streamlit as st
from PIL import Image
import pytesseract
import io
from datetime import datetime, timedelta, timezone

# Configure Tesseract path for Streamlit Cloud
pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

# ========== CONSTANTS ==========
PROJECT_LIST = ["BCC", "RBOC", "BDATAS", "CSR"]
TIME_FRAMES = {
    "Last 7 days": 7,
    "Last 30 days": 30,
    "Last year": 365
}

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
def extract_text(image_url, _auth_token):
    try:
        username, password = _auth_token.split("|")
        auth = HTTPBasicAuth(username, password)
        
        response = requests.get(image_url, auth=auth, timeout=15)
        img = Image.open(io.BytesIO(response.content))
        return pytesseract.image_to_string(img)
    except Exception as e:
        st.error(f"OCR Error: {str(e)}")
        return ""

# ========== STREAMLIT UI ==========
def show_image_zoomable(image_url, auth, width=200):
    """Displays a clickable/zoomable image"""
    try:
        response = requests.get(image_url, auth=auth, timeout=10)
        img = Image.open(io.BytesIO(response.content))
        
        # Create two columns - one for thumbnail, one for zoomed view
        col1, col2 = st.columns([1, 3])
        
        with col1:
            # Clickable thumbnail
            clicked = st.image(img, width=width, caption="Click to enlarge")
            
        with col2:
            # Only show zoomed view if thumbnail is clicked
            if st.session_state.get(f"zoom_{image_url}", False):
                st.image(img, caption="Zoomed View")
                if st.button("Close Zoom", key=f"close_{image_url}"):
                    st.session_state[f"zoom_{image_url}"] = False
            elif clicked:  # If thumbnail is clicked
                st.session_state[f"zoom_{image_url}"] = True
                st.rerun()
                
    except Exception as e:
        st.error(f"Failed to load image: {str(e)}")

def main():
    st.title("🔍 Jira Search with OCR ")
    
    # Credential Input
    with st.expander("🔑 Jira Credentials", expanded=True):
        base_url = st.text_input("Jira URL", placeholder="https://your-domain.atlassian.net")
        username = st.text_input("Username/Email")
        password = st.text_input("Password", type="password")
    
    # Search Form
    with st.form("search_form"):
        query = st.text_input("Search term")
        projects = st.multiselect("Projects", PROJECT_LIST)
        time_frame = st.selectbox("Timeframe", list(TIME_FRAMES.keys()))
        search_images = st.checkbox("Search text in images (OCR)", True)
        submitted = st.form_submit_button("Search")
    
    if submitted and query and base_url and username and password:
        auth = HTTPBasicAuth(username, password)
        auth_token = f"{username}|{password}"
        
        with st.spinner("Searching Jira..."):
            issues = search_jira(base_url, auth, query, projects, time_frame)
            
        if not issues:
            st.warning("No issues found")
            return
            
        st.success(f"Found {len(issues)} issues")
        
        for issue in issues:
            with st.expander(f"{issue['key']}: {issue['fields']['summary']}"):
                # Basic Info
                st.write(f"**Created:** {issue['fields']['created'][:10]}")
                st.write(issue['fields'].get('description', 'No description'))
                
                # Attachments
                if 'attachment' in issue['fields']:
                    st.subheader("Attachments")
                    for att in issue['fields']['attachment']:
                        if att['mimeType'].startswith('image/'):
                            with st.container(border=True):
                                st.write(f"**{att['filename']}**")
                                
                                # Image display with zoom
                                show_image_zoomable(att['content'], auth)
                                
                                # OCR functionality
                                if search_images:
                                    if st.button(f"Run OCR on {att['filename']}", 
                                               key=f"ocr_{att['id']}"):
                                        with st.spinner("Extracting text..."):
                                            text = extract_text(att['content'], auth_token)
                                            st.text_area("Extracted Text", 
                                                        text, 
                                                        height=150,
                                                        key=f"text_{att['id']}")
                                        
                                st.download_button(
                                    f"Download {att['filename']}",
                                    data=requests.get(att['content'], auth=auth).content,
                                    file_name=att['filename'],
                                    key=f"dl_{att['id']}"
                                )

if __name__ == "__main__":
    if 'zoom_' not in st.session_state:
        st.session_state.update({f"zoom_{k}": False for k in st.session_state.keys() 
                               if k.startswith('zoom_')})
    main()
