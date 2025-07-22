import requests
from requests.auth import HTTPBasicAuth
import streamlit as st
from datetime import datetime, timedelta, timezone
import pandas as pd
from io import BytesIO
from PIL import Image

# ========== PAGE CONFIG ==========
st.set_page_config(
    page_title="Jira Search Pro+",
    layout="wide",
    page_icon="🔍"
)

# ========== CONSTANTS ==========
RESULTS_PER_PAGE = 10
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
    "Last 1 year": 365,
    "All time": None
}
SORT_OPTIONS = {
    "Newest first": "DESC",
    "Oldest first": "ASC",
    "Most recently updated": "updated DESC",
    "Least recently updated": "updated ASC"
}

# ========== SESSION STATE ==========
if 'raw_results' not in st.session_state:
    st.session_state.raw_results = []
if 'filtered_results' not in st.session_state:
    st.session_state.filtered_results = []
if 'page' not in st.session_state:
    st.session_state.page = 1
if 'auth_verified' not in st.session_state:
    st.session_state.auth_verified = False

# ========== CORE FUNCTIONS ==========
def search_jira(base_url, query, auth, projects, time_frame, sort_order, max_results=100):
    """Searches both text fields AND attachment contents"""
    jql_parts = []
    
    # Project filter
    if projects:
        projects_str = ', '.join(f'"{p}"' for p in projects)
        jql_parts.append(f"project IN ({projects_str})")
    
    # Enhanced text search (now includes attachment content)
    if query:
        jql_parts.append(f'(text ~ "{query}" OR attachmentContent ~ "{query}")')
    
    # Time frame filter
    if time_frame and time_frame in TIME_FRAMES and TIME_FRAMES[time_frame]:
        days = TIME_FRAMES[time_frame]
        jql_parts.append(f"created >= -{days}d")
    
    # Combine all parts
    jql = ' AND '.join(jql_parts)
    
    # Add sorting
    if sort_order in SORT_OPTIONS:
        jql += f" ORDER BY {SORT_OPTIONS[sort_order]}"
    
    url = f"{base_url}/rest/api/2/search"
    params = {
        "jql": jql,
        "maxResults": max_results,
        "fields": "summary,description,status,labels,project,updated,created,attachment,key,assignee"
    }
    
    try:
        response = requests.get(url, params=params, auth=auth, timeout=30)
        response.raise_for_status()
        return response.json().get("issues", [])
    except requests.exceptions.RequestException as e:
        st.error(f"Jira API Error: {str(e)}")
        return []

def get_attachment_images(issue, auth):
    """Fetches all image attachments with error handling"""
    images = []
    if 'attachment' in issue['fields']:
        for attachment in issue['fields']['attachment']:
            if attachment['mimeType'].startswith('image/'):
                try:
                    response = requests.get(
                        attachment['content'],
                        auth=auth,
                        timeout=10
                    )
                    if response.status_code == 200:
                        img = Image.open(BytesIO(response.content))
                        images.append({
                            'name': attachment['filename'],
                            'image': img,
                            'url': attachment['content'],
                            'contains_error': attachment['filename'].lower().find("error") != -1  # Simple filename check
                        })
                except Exception as e:
                    st.warning(f"Couldn't load image {attachment['filename']}: {str(e)}")
    return images

# ========== UI COMPONENTS ==========
def show_search_form():
    with st.form("main_search"):
        col1, col2 = st.columns([3, 2])
        
        with col1:
            query = st.text_input("Search Query", placeholder="Error Code: 5011", key="search_query")
        
        with col2:
            selected_projects = st.multiselect(
                "Projects",
                options=PROJECT_LIST,
                default=PROJECT_LIST[:5],
                key="projects"
            )
        
        col3, col4 = st.columns(2)
        with col3:
            time_frame = st.selectbox(
                "Time Frame",
                options=list(TIME_FRAMES.keys()),
                index=4,
                key="time_frame"
            )
        
        with col4:
            sort_order = st.selectbox(
                "Sort By",
                options=list(SORT_OPTIONS.keys()),
                index=0,
                key="sort_order"
            )
        
        submit = st.form_submit_button("🔍 Search Jira (Including Attachments)")
        
        if submit and (query or selected_projects):
            return query.strip(), selected_projects, time_frame, sort_order
    return None, None, None, None

def display_results(issues, base_url, auth):
    start = (st.session_state.page - 1) * RESULTS_PER_PAGE
    end = start + RESULTS_PER_PAGE
    
    for issue in issues[start:end]:
        project = issue['key'].split('-')[0]
        status = issue['fields']['status']['name']
        updated_date = parse_jira_date(issue['fields']['updated'])
        created_date = parse_jira_date(issue['fields']['created'])
        assignee = issue['fields'].get('assignee', {}).get('displayName', 'Unassigned')
        images = get_attachment_images(issue, auth)
        
        with st.container(border=True):
            # Header
            st.markdown(f"""
            <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                <h3 style="margin: 0;">{issue['key']}: {issue['fields']['summary']}</h3>
                <div>
                    <span style="background: #e0e0e0; padding: 3px 8px; border-radius: 4px;">
                        {project}
                    </span>
                    <span style="color: {'green' if status == 'Done' else 'orange'}; margin-left: 10px;">
                        {status}
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Body
            cols = st.columns([3, 1])
            with cols[0]:
                desc = issue['fields'].get('description', 'No description available')
                st.text(desc[:250] + ("..." if len(desc) > 250 else ""))
                
                if 'labels' in issue['fields'] and issue['fields']['labels']:
                    st.text("Labels: " + ", ".join(issue['fields']['labels']))
                
                st.text(f"Assignee: {assignee}")
                
                # Display images if found
                if images:
                    st.subheader("📎 Attachments")
                    for img in images:
                        expander = st.expander(f"🖼️ {img['name']} {'🔍 (Possible error)' if img['contains_error'] else ''}")
                        with expander:
                            st.image(img['image'], use_column_width=True)
                            st.markdown(f"[View original]({img['url']})")
            
            with cols[1]:
                st.markdown(f"**Created:** {created_date.strftime('%Y-%m-%d')}")
                st.markdown(f"**Updated:** {updated_date.strftime('%Y-%m-%d')}")
                st.markdown(f"[Open in Jira ↗]({base_url}/browse/{issue['key']})", unsafe_allow_html=True)

# ========== MAIN APP ==========
def main():
    st.title("🔍 Jira Search Pro+ (Attachment Content)")
    
    # Authentication
    base_url = st.text_input("Jira URL", placeholder="https://your-company.atlassian.net", key="jira_url")
    username = st.text_input("Username", key="jira_user")
    password = st.text_input("Password", type="password", key="jira_pass")
    
    if base_url and username and password:
        auth = HTTPBasicAuth(username, password)
        st.session_state.auth_verified = True
    else:
        st.session_state.auth_verified = False
    
    # Main search
    query, projects, time_frame, sort_order = show_search_form()
    
    if (query or projects) and st.session_state.auth_verified:
        with st.spinner(f"Searching Jira (including attachments)..."):
            issues = search_jira(base_url, query, auth, projects, time_frame, sort_order)
            st.session_state.raw_results = issues
            st.session_state.filtered_results = issues
            st.session_state.page = 1
    
    # Display results
    if st.session_state.raw_results:
        st.markdown(f"**Found {len(st.session_state.raw_results)} results**")
        display_results(st.session_state.raw_results, base_url, auth)
        show_pagination(len(st.session_state.raw_results))

if __name__ == "__main__":
    main()
