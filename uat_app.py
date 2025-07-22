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
    """Get base64 encoded image to avoid Streamlit media storage issues"""
    try:
        response = requests.get(image_url, auth=auth, timeout=10)
        return base64.b64encode(response.content).decode("utf-8")
    except Exception as e:
        st.error(f"Failed to load image: {str(e)}")
        return None

def show_image_with_zoom(image_base64, filename):
    """Display image with zoom capability using base64 encoding"""
    if not image_base64:
        return
    
    # Display thumbnail
    thumbnail_html = f"""
    <div style="cursor:pointer;" onclick="document.getElementById('{filename}_modal').style.display='block'">
        <img src="data:image/png;base64,{image_base64}" width="200" alt="{filename}">
    </div>
    """
    st.markdown(thumbnail_html, unsafe_allow_html=True)
    
    # Modal for zoomed view
    modal_html = f"""
    <div id="{filename}_modal" style="display:none;position:fixed;z-index:100;left:0;top:0;width:100%;height:100%;background-color:rgba(0,0,0,0.9);">
        <span style="position:absolute;top:20px;right:35px;color:white;font-size:40px;font-weight:bold;cursor:pointer;" 
              onclick="document.getElementById('{filename}_modal').style.display='none'">&times;</span>
        <div style="display:flex;justify-content:center;align-items:center;height:100%;">
            <img src="data:image/png;base64,{image_base64}" style="max-width:90%;max-height:90%;">
        </div>
    </div>
    """
    st.markdown(modal_html, unsafe_allow_html=True)

# ========== STREAMLIT UI ==========
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
                                
                                # Get and display image
                                image_base64 = get_image_base64(att['content'], auth)
                                if image_base64:
                                    show_image_with_zoom(image_base64, att['filename'])
                                
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
                                st.download_button(
                                    f"Download {att['filename']}",
                                    data=base64.b64decode(image_base64) if image_base64 else b"",
                                    file_name=att['filename'],
                                    key=f"dl_{att['id']}"
                                )

if __name__ == "__main__":
    main()
