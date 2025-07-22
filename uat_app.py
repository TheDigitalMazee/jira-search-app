import requests
from requests.auth import HTTPBasicAuth
import streamlit as st
from PIL import Image
import pytesseract
import io
import base64
import re
from datetime import datetime, timedelta, timezone

# Configure Tesseract path for Streamlit Cloud
pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

# ========== CONSTANTS ==========
PROJECT_LIST = [
    "RBOC", "BCC", "BDATAS", "CSR", "SELF", "NOD", "BDM", "BBIS", "RTM",
    "RTMPS", "RTMP", "ASRMT", "EXTSD", "DDP", "CASE", "BISVC", "BAPPS",
    "BZD", "ENCP", "MCC", "NET", "OMNI2", "OSA", "OTS", "PNP", "BNRPS",
    "RPCSA", "RPHQ", "SSI"
]
TIME_FRAMES = {
    "Last 7 days": 7,
    "Last 30 days": 30,
    "Last 90 days": 90,
    "Last 6 months": 180,
    "Last year": 365,
    "All time": None
}

# ========== SESSION STATE MANAGEMENT ==========
def init_session_state():
    if 'zoom_image' not in st.session_state:
        st.session_state.zoom_image = None
    if 'search_results' not in st.session_state:
        st.session_state.search_results = None
    if 'auth' not in st.session_state:
        st.session_state.auth = None
    if 'search_params' not in st.session_state:
        st.session_state.search_params = {}
    if 'available_statuses' not in st.session_state:
        st.session_state.available_statuses = []
    if 'available_platforms' not in st.session_state:
        st.session_state.available_platforms = []
    if 'page' not in st.session_state:
        st.session_state.page = 1

# ========== CORE FUNCTIONS ==========
def sanitize_jql(query):
    """Handle special characters in JQL queries"""
    if '"' in query:
        query = query.replace('"', '\\"')
    return query

def search_jira(base_url, auth, query, projects, time_frame, statuses=None, platform=None):
    jql = f'project IN ({",".join(f"\"{p}\"" for p in projects)})'
    
    if query:
        sanitized_query = sanitize_jql(query)
        jql += f' AND (text ~ "{sanitized_query}" OR attachmentContent ~ "{sanitized_query}")'
    
    if statuses:
        jql += f' AND status IN ({",".join(f"\"{s}\"" for s in statuses)})'
    
    if platform:
        jql += f' AND "Platform" ~ "{platform}"'
    
    if time_frame in TIME_FRAMES and TIME_FRAMES[time_frame]:
        jql += f' AND created >= -{TIME_FRAMES[time_frame]}d'
    
    jql += ' ORDER BY created DESC, project ASC'  # RBOC first due to project ordering
    
    try:
        response = requests.get(
            f"{base_url}/rest/api/2/search",
            auth=auth,
            params={
                "jql": jql,
                "maxResults": 200,
                "fields": "summary,description,attachment,created,updated,status,assignee,project,customfield_12345"  # customfield_12345 for platform
            },
            timeout=20
        )
        response.raise_for_status()
        return response.json().get("issues", [])
    except Exception as e:
        st.error(f"Jira API Error: {str(e)}")
        return []

def get_available_filters(issues):
    """Extract unique statuses and platforms from search results"""
    statuses = set()
    platforms = set()
    
    for issue in issues:
        statuses.add(issue['fields']['status']['name'])
        # Extract platform from custom field if available
        if 'customfield_12345' in issue['fields'] and issue['fields']['customfield_12345']:
            platforms.add(issue['fields']['customfield_12345']['value'])
    
    return {
        'statuses': sorted(statuses),
        'platforms': sorted(platforms)
    }

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

# ========== UI COMPONENTS ==========
def show_project_filter():
    col1, col2 = st.columns([4, 1])
    with col1:
        selected = st.multiselect(
            "Projects",
            PROJECT_LIST,
            default=st.session_state.search_params.get("selected_projects", PROJECT_LIST)
        )
    with col2:
        st.write("")
        st.write("")
        if st.button("All"):
            selected = PROJECT_LIST
        if st.button("None"):
            selected = []
    return selected

def show_image_with_zoom(image_base64, filename, key_suffix):
    if not image_base64:
        return
    
    zoom_key = f"zoom_{key_suffix}"
    
    if st.session_state.get(zoom_key, False):
        st.image(base64.b64decode(image_base64), use_container_width=True)
        if st.button("◄ Back", key=f"back_{key_suffix}"):
            st.session_state[zoom_key] = False
            st.rerun()
    else:
        if st.image(base64.b64decode(image_base64), width=200, 
                  caption=f"Click to zoom: {filename}"):
            st.session_state[zoom_key] = True
            st.rerun()

# ========== MAIN UI ==========
def main():
    st.title("🔍 Jira Search Pro+")
    init_session_state()
    
    # Search Form
    with st.expander("🔍 Search Panel", expanded=True):
        with st.form("search_form"):
            base_url = st.text_input(
                "Jira URL", 
                value=st.session_state.search_params.get("base_url", ""),
                placeholder="https://your-domain.atlassian.net"
            )
            username = st.text_input("Username/Email")
            password = st.text_input("Password", type="password")
            
            query = st.text_input("Search term", value=st.session_state.search_params.get("query", ""))
            
            col1, col2 = st.columns(2)
            with col1:
                selected_projects = show_project_filter()
                time_frame = st.selectbox(
                    "Timeframe", 
                    list(TIME_FRAMES.keys()),
                    index=list(TIME_FRAMES.keys()).index(
                        st.session_state.search_params.get("time_frame", "Last 7 days")
                    )
                )
            with col2:
                if st.session_state.available_statuses:
                    selected_statuses = st.multiselect(
                        "Statuses",
                        st.session_state.available_statuses,
                        default=st.session_state.search_params.get("selected_statuses", st.session_state.available_statuses)
                    )
                else:
                    selected_statuses = []
                
                if st.session_state.available_platforms:
                    selected_platform = st.selectbox(
                        "Platform", 
                        [""] + st.session_state.available_platforms,
                        index=0
                    )
                else:
                    selected_platform = ""
            
            search_images = st.checkbox(
                "Search text in images (OCR)",
                value=st.session_state.search_params.get("search_images", True)
            )
            
            if st.form_submit_button("Search"):
                if base_url and username and password:
                    st.session_state.auth = HTTPBasicAuth(username, password)
                    st.session_state.page = 1  # Reset to first page
                    
                    with st.spinner("Searching Jira..."):
                        results = search_jira(
                            base_url,
                            st.session_state.auth,
                            query,
                            selected_projects,
                            time_frame,
                            selected_statuses,
                            selected_platform if selected_platform else None
                        )
                        
                        if results:
                            st.session_state.search_results = results
                            filters = get_available_filters(results)
                            st.session_state.available_statuses = filters['statuses']
                            st.session_state.available_platforms = filters['platforms']
                            
                            # Store search parameters
                            st.session_state.search_params = {
                                "base_url": base_url,
                                "query": query,
                                "selected_projects": selected_projects,
                                "time_frame": time_frame,
                                "selected_statuses": selected_statuses,
                                "search_images": search_images,
                                "platform": selected_platform
                            }
                        else:
                            st.session_state.search_results = None
                            st.warning("No results found")
                else:
                    st.warning("Please provide Jira URL and credentials")

    # Results Display
    if st.session_state.search_results:
        # Filter results
        filtered_results = [
            issue for issue in st.session_state.search_results 
            if (not st.session_state.search_params.get("selected_statuses") or 
                issue['fields']['status']['name'] in st.session_state.search_params["selected_statuses"])
        ]
        
        # Pagination
        RESULTS_PER_PAGE = 10
        total_pages = (len(filtered_results) + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
        start_idx = (st.session_state.page - 1) * RESULTS_PER_PAGE
        end_idx = start_idx + RESULTS_PER_PAGE
        
        st.success(f"Found {len(st.session_state.search_results)} issues ({len(filtered_results)} after filtering)")
        
        # Show platform filter if available
        if st.session_state.available_platforms:
            platform = st.selectbox(
                "Filter by Platform", 
                ["All Platforms"] + st.session_state.available_platforms
            )
            if platform != "All Platforms":
                filtered_results = [
                    issue for issue in filtered_results 
                    if 'customfield_12345' in issue['fields'] and 
                       issue['fields']['customfield_12345'] and 
                       issue['fields']['customfield_12345']['value'] == platform
                ]
        
        # Display paginated results
        for issue in filtered_results[start_idx:end_idx]:
            with st.expander(f"{issue['key']}: {issue['fields']['summary']}", expanded=True):
                cols = st.columns([3, 1])
                with cols[0]:
                    st.write(f"**Project:** {issue['key'].split('-')[0]}")
                    st.write(f"**Created:** {issue['fields']['created'][:10]}")
                    
                    status = issue['fields']['status']['name']
                    color = "green" if status == "Done" else "orange" if status == "In Progress" else "gray"
                    st.markdown(f"**Status:** <span style='color:{color}'>{status}</span>", unsafe_allow_html=True)
                    
                    if 'customfield_12345' in issue['fields'] and issue['fields']['customfield_12345']:
                        st.write(f"**Platform:** {issue['fields']['customfield_12345']['value']}")
                    
                    st.markdown(f"[Open in Jira ↗]({base_url}/browse/{issue['key']})", unsafe_allow_html=True)
                
                with cols[1]:
                    st.write("**Description:**")
                    st.write(issue['fields'].get('description', 'No description')[:500] + ("..." if len(issue['fields'].get('description', '')) > 500 else ""))
                
                # Attachments handling
                if 'attachment' in issue['fields']:
                    st.subheader("Attachments")
                    for att in issue['fields']['attachment']:
                        if att['mimeType'].startswith('image/'):
                            with st.container(border=True):
                                image_base64 = get_image_base64(att['content'], st.session_state.auth)
                                if image_base64:
                                    show_image_with_zoom(image_base64, att['filename'], att['id'])
                                    
                                    if st.session_state.search_params.get("search_images", False):
                                        if st.button(f"Run OCR on {att['filename']}", key=f"ocr_{att['id']}"):
                                            with st.spinner("Extracting text..."):
                                                auth_token = f"{username}|{password}"
                                                text = extract_text(auth_token, att['content'])
                                                st.text_area("Extracted Text", text, height=150)
                                    
                                    st.download_button(
                                        f"Download {att['filename']}",
                                        data=base64.b64decode(image_base64),
                                        file_name=att['filename']
                                    )
        
        # Pagination controls
        if total_pages > 1:
            st.write("---")
            col1, col2, col3 = st.columns([1, 2, 1])
            with col1:
                if st.button("◀ Previous") and st.session_state.page > 1:
                    st.session_state.page -= 1
                    st.rerun()
            with col2:
                st.markdown(f"**Page {st.session_state.page} of {total_pages}**", unsafe_allow_html=True)
            with col3:
                if st.button("Next ▶") and st.session_state.page < total_pages:
                    st.session_state.page += 1
                    st.rerun()

if __name__ == "__main__":
    main()
