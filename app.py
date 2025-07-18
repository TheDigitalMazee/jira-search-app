import requests
from requests.auth import HTTPBasicAuth
import streamlit as st
from datetime import datetime, timedelta
import pandas as pd

# ========== PAGE CONFIG ==========
st.set_page_config(
    page_title="Jira Search Pro+",
    layout="wide",
    page_icon="🔍"
)

# ========== CONSTANTS ==========
RESULTS_PER_PAGE = 10

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
def search_jira(base_url, query, auth, max_results=100):
    jql = f'text ~ "{query}" ORDER BY updated DESC'
    url = f"{base_url}/rest/api/2/search"
    params = {
        "jql": jql,
        "maxResults": max_results,
        "fields": "summary,description,status,labels,project,updated,attachment,key"
    }
    response = requests.get(url, params=params, auth=auth, timeout=30)
    response.raise_for_status()
    return response.json().get("issues", [])

def parse_jira_date(date_str):
    """Handle Jira's date format which sometimes includes milliseconds and timezone"""
    try:
        # Try ISO format first
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except ValueError:
        # Fallback for non-standard formats
        return datetime.strptime(date_str.split('.')[0], "%Y-%m-%dT%H:%M:%S")

# ========== UI COMPONENTS ==========
def show_search_form():
    with st.form("main_search"):
        query = st.text_input("Search Query", placeholder="Enter error code or keywords", key="search_query")
        submit = st.form_submit_button("Search Jira")
        
        if submit and query:
            return query.strip()
    return None

def show_results_filters(issues):
    with st.expander("🔍 Filter Results", expanded=True):
        # Extract all unique project types from results
        projects = sorted(list({issue['key'].split('-')[0] for issue in issues}))
        
        col1, col2, col3 = st.columns(3)
        with col1:
            selected_projects = st.multiselect(
                "Project Types",
                options=projects,
                default=projects
            )
        with col2:
            date_options = st.selectbox(
                "Updated Timeframe",
                options=["All", "Last 7 days", "Last 30 days", "Last 90 days", "Last 1 year"],
                index=0
            )
        with col3:
            statuses = sorted(list({issue['fields']['status']['name'] for issue in issues}))
            selected_statuses = st.multiselect(
                "Status",
                options=statuses,
                default=statuses
            )
        
        # Apply filters
        filtered = issues
        if selected_projects:
            filtered = [i for i in filtered if i['key'].split('-')[0] in selected_projects]
        if date_options != "All":
            days_map = {
                "Last 7 days": 7,
                "Last 30 days": 30,
                "Last 90 days": 90,
                "Last 1 year": 365
            }
            days = days_map[date_options]
            cutoff = datetime.now() - timedelta(days=days)
            filtered = [i for i in filtered if parse_jira_date(i['fields']['updated']) > cutoff]
        if selected_statuses:
            filtered = [i for i in filtered if i['fields']['status']['name'] in selected_statuses]
        
        return filtered

def display_results(issues, base_url):
    start = (st.session_state.page - 1) * RESULTS_PER_PAGE
    end = start + RESULTS_PER_PAGE
    
    for issue in issues[start:end]:
        project = issue['key'].split('-')[0]
        status = issue['fields']['status']['name']
        
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
                
            with cols[1]:
                updated_date = parse_jira_date(issue['fields']['updated'])
                st.markdown(f"**Updated:** {updated_date.strftime('%Y-%m-%d')}")
                st.markdown(f"[Open in Jira ↗]({base_url}/browse/{issue['key']})", unsafe_allow_html=True)

def show_pagination(total_items):
    total_pages = (total_items + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
    if total_pages > 1:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            if st.button("◀ Previous") and st.session_state.page > 1:
                st.session_state.page -= 1
        with col2:
            st.markdown(f"**Page {st.session_state.page} of {total_pages}**", unsafe_allow_html=True)
        with col3:
            if st.button("Next ▶") and st.session_state.page < total_pages:
                st.session_state.page += 1

# ========== MAIN APP ==========
def main():
    st.title("🔍 Jira Search Pro+")
    
    # Authentication - no need to press enter
    base_url = st.text_input("Jira URL", placeholder="https://your-company.atlassian.net", key="jira_url")
    username = st.text_input("Username", key="jira_user")
    password = st.text_input("Password", type="password", key="jira_pass")
    
    # Store auth state when all fields are filled
    if base_url and username and password:
        auth = HTTPBasicAuth(username, password)
        st.session_state.auth_verified = True
    else:
        st.session_state.auth_verified = False
    
    # Main search
    query = show_search_form()
    
    if query and st.session_state.auth_verified:
        with st.spinner(f"Searching for '{query}'..."):
            try:
                issues = search_jira(base_url, query, auth)
                st.session_state.raw_results = issues
                st.session_state.filtered_results = issues
                st.session_state.page = 1  # Reset to first page
            except Exception as e:
                st.error(f"Search failed: {str(e)}")
                return
    
    # Show filters and results if available
    if st.session_state.raw_results:
        st.session_state.filtered_results = show_results_filters(st.session_state.raw_results)
        st.markdown(f"**Found {len(st.session_state.raw_results)} results** ({len(st.session_state.filtered_results)} after filtering)")
        
        if st.session_state.filtered_results:
            display_results(st.session_state.filtered_results, base_url)
            show_pagination(len(st.session_state.filtered_results))
        else:
            st.warning("No results match your filters")

if __name__ == "__main__":
    main()
