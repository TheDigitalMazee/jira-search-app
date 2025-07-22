import requests
from requests.auth import HTTPBasicAuth
import streamlit as st
from PIL import Image
import pytesseract
import io
import base64

# Configure Tesseract path for Streamlit Cloud
pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

# ========== CONSTANTS ==========
PROJECT_LIST = [
    "BCC", "RBOC", "BDATAS", "CSR", "SELF", "NOD", "BDM", "BBIS", "RTM",
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
    if 'selected_projects' not in st.session_state:
        st.session_state.selected_projects = PROJECT_LIST.copy()
    if 'selected_statuses' not in st.session_state:
        st.session_state.selected_statuses = []

# ========== CORE FUNCTIONS ==========
def search_jira(base_url, auth, query, projects, time_frame, statuses=None):
    jql = f'project IN ({",".join(f"\"{p}\"" for p in projects)})'
    
    if query:
        jql += f' AND text ~ "{query}"'
    
    if statuses:
        jql += f' AND status IN ({",".join(f"\"{s}\"" for s in statuses)})'
    
    if time_frame in TIME_FRAMES and TIME_FRAMES[time_frame]:
        jql += f' AND created >= -{TIME_FRAMES[time_frame]}d'
    
    jql += ' ORDER BY created DESC'
    
    try:
        response = requests.get(
            f"{base_url}/rest/api/2/search",
            auth=auth,
            params={
                "jql": jql,
                "maxResults": 100,
                "fields": "summary,description,attachment,created,updated,status,assignee,project"
            },
            timeout=15
        )
        response.raise_for_status()
        return response.json().get("issues", [])
    except Exception as e:
        st.error(f"Jira API Error: {str(e)}")
        return []

def get_available_statuses(issues):
    """Extract unique statuses from search results"""
    statuses = set()
    for issue in issues:
        statuses.add(issue['fields']['status']['name'])
    return sorted(statuses)

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
            st.image(base64.b64decode(image_base64), use_container_width=True)
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
        
        query = st.text_input("Search term (leave blank for all issues)")
        st.session_state.selected_projects = st.multiselect(
            "Projects to search",
            PROJECT_LIST,
            default=st.session_state.get('selected_projects', PROJECT_LIST)
        )
        time_frame = st.selectbox("Timeframe", list(TIME_FRAMES.keys()))
        search_images = st.checkbox("Search text in images (OCR)", True)
        
        if st.form_submit_button("Search"):
            if base_url and username and password:
                st.session_state.auth = HTTPBasicAuth(username, password)
                st.session_state.search_params = {
                    "search_images": search_images,
                    "base_url": base_url,
                    "query": query,
                    "time_frame": time_frame,
                    "selected_projects": st.session_state.selected_projects,
                    "selected_statuses": []  # Initialize empty, will populate after first search
                }
                with st.spinner("Searching Jira..."):
                    st.session_state.search_results = search_jira(
                        base_url,
                        st.session_state.auth,
                        query,
                        st.session_state.selected_projects,
                        time_frame
                    )
                    # Initialize status filters after first search
                    if st.session_state.search_results:
                        st.session_state.available_statuses = get_available_statuses(
                            st.session_state.search_results
                        )
                        st.session_state.selected_statuses = st.session_state.available_statuses.copy()
            else:
                st.warning("Please provide Jira URL and credentials")

def show_results_page():
    st.title("🔍 Search Results")
    
    # Keep the search form visible on results page
    with st.expander("🔍 Modify Search", expanded=True):
        with st.form("refine_search"):
            new_query = st.text_input(
                "Search term", 
                value=st.session_state.search_params.get("query", "")
            )
            
            col1, col2 = st.columns(2)
            with col1:
                new_selected_projects = st.multiselect(
                    "Projects",
                    PROJECT_LIST,
                    default=st.session_state.search_params.get("selected_projects", PROJECT_LIST)
                )
                new_time_frame = st.selectbox(
                    "Timeframe", 
                    list(TIME_FRAMES.keys()),
                    index=list(TIME_FRAMES.keys()).index(
                        st.session_state.search_params.get("time_frame", "Last 7 days")
                    )
                )
            with col2:
                if hasattr(st.session_state, 'available_statuses'):
                    new_selected_statuses = st.multiselect(
                        "Statuses",
                        st.session_state.available_statuses,
                        default=st.session_state.get('selected_statuses', [])
                    )
                else:
                    new_selected_statuses = []
                
                new_search_images = st.checkbox(
                    "Search text in images (OCR)",
                    value=st.session_state.search_params.get("search_images", True)
                )
            
            if st.form_submit_button("Refine Search"):
                st.session_state.search_params = {
                    "search_images": new_search_images,
                    "base_url": st.session_state.search_params["base_url"],
                    "query": new_query,
                    "time_frame": new_time_frame,
                    "selected_projects": new_selected_projects,
                    "selected_statuses": new_selected_statuses
                }
                st.session_state.selected_statuses = new_selected_statuses
                
                with st.spinner("Searching Jira..."):
                    st.session_state.search_results = search_jira(
                        st.session_state.search_params["base_url"],
                        st.session_state.auth,
                        new_query,
                        new_selected_projects,
                        new_time_frame,
                        new_selected_statuses
                    )
                st.rerun()
    
    if not st.session_state.search_results:
        st.warning("No results to display")
        return
    
    # Filter results by status if needed (client-side filtering as fallback)
    filtered_results = st.session_state.search_results
    if hasattr(st.session_state, 'selected_statuses') and st.session_state.selected_statuses:
        filtered_results = [
            issue for issue in filtered_results 
            if issue['fields']['status']['name'] in st.session_state.selected_statuses
        ]
    
    st.success(f"Showing {len(filtered_results)} of {len(st.session_state.search_results)} issues")
    
    auth_token = f"{st.session_state.auth.username}|{st.session_state.auth.password}"
    search_images = st.session_state.search_params.get("search_images", False)
    
    for issue in filtered_results:
        with st.expander(f"{issue['key']}: {issue['fields']['summary']}"):
            # Basic issue info
            cols = st.columns(3)
            with cols[0]:
                st.write(f"**Project:** {issue['key'].split('-')[0]}")
            with cols[1]:
                st.write(f"**Created:** {issue['fields']['created'][:10]}")
            with cols[2]:
                status = issue['fields']['status']['name']
                color = "green" if status == "Done" else "orange" if status == "In Progress" else "gray"
                st.markdown(f"**Status:** <span style='color:{color}'>{status}</span>", 
                           unsafe_allow_html=True)
            
            # Description
            st.write("**Description:**")
            st.write(issue['fields'].get('description', 'No description'))
            
            # Attachments
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
