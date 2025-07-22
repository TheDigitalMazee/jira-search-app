# app.py - No Secrets Version
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
PROJECT_LIST = ["BCC", "RBOC", "BDATAS", "CSR"]  # Your projects
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
def extract_text(image_url, auth):
    try:
        response = requests.get(image_url, auth=auth, timeout=15)
        img = Image.open(io.BytesIO(response.content))
        return pytesseract.image_to_string(img)
    except Exception as e:
        st.error(f"OCR Error: {str(e)}")
        return ""

# ========== STREAMLIT UI ==========
def main():
    st.title("🔍 Jira Search with OCR (No Secrets)")
    
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
                
                # OCR Processing
                if search_images and 'attachment' in issue['fields']:
                    for att in issue['fields']['attachment']:
                        if att['mimeType'].startswith('image/'):
                            with st.spinner(f"Scanning {att['filename']}..."):
                                text = extract_text(att['content'], auth)
                                if query.lower() in text.lower():
                                    cols = st.columns([1, 3])
                                    with cols[0]:
                                        st.image(att['content'], width=200)
                                    with cols[1]:
                                        st.text_area("Extracted Text", text, height=150)
                                        st.download_button(
                                            "Download Image",
                                            data=requests.get(att['content'], auth=auth).content,
                                            file_name=att['filename']
                                        )
                                elif st.button(f"Run OCR on {att['filename']}"):
                                    text = extract_text(att['content'], auth)
                                    st.text_area("OCR Results", text, height=150)

if __name__ == "__main__":
    main()
