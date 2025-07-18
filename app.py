import requests
from requests.auth import HTTPBasicAuth
import streamlit as st
from datetime import datetime, timedelta, timezone

# ========== PAGE CONFIG ==========
st.set_page_config(
    page_title="Jira Search Pro+",
    layout="wide",
    page_icon="🔍"
)

# ========== CONSTANTS ==========
RESULTS_PER_PAGE = 10
DEBUG = False  # Set to True for development

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
def build_jql(query, project_filter=None, date_filter=None):
    """Simplified and reliable JQL builder"""
    jql_parts = []
    
    # Handle exact phrase searches
    if '"' in query:
        text_query = query
        jql_parts.append(f'(summary ~ {text_query} OR description ~ {text_query} OR comment ~ {text_query})')
    else:
        # Process terms with proper escaping
        terms = []
        for word in query.split():
            if word.isdigit():
                terms.append(word)  # Numbers without quotes
            else:
                terms.append(f'"{word}"')  # Words with quotes
        
        # Combine terms with AND for precision
        if terms:
            term_string = " AND ".join(terms)
            jql_parts.append(f'(summary ~ {term_string} OR description ~ {term_string} OR comment ~ {term_string})')
    
    # Add filters if specified
    if project_filter:
        jql_parts.append(f'project in ({",".join(project_filter)})')
    if date_filter:
        jql_parts.append(f'updated >= "{date_filter}"')
    
    # Build final query
    jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"
    
    # Debug output
    if DEBUG:
        st.sidebar.code(f"Generated JQL:\n{jql}")
    
    return jql

def search_jira(base_url, query, auth, max_results=100):
    try:
        jql = build_jql(query)
        url = f"{base_url}/rest/api/2/search"
        params = {
            "jql": jql,
            "maxResults": max_results,
            "fields": "summary,description,status,labels,project,updated,attachment,key,comment"
        }
        response = requests.get(url, params=params, auth=auth, timeout=30)
        response.raise_for_status()
        return response.json().get("issues", [])
    except Exception as e:
        st.error(f"Search error: {str(e)}")
        if DEBUG:
            st.sidebar.error(f"Failed JQL: {jql}")
        raise

def parse_jira_date(date_str):
    """Robust Jira date parser with timezone support"""
    try:
        # Handle various Jira date formats
        date_str = date_str.replace('Z', '+00:00')  # Convert Zulu time
        if '.' in date_str:  # Contains milliseconds
            date_str = date_str.split('.')[0] + date_str[-6:]  # Keep timezone
        return datetime.fromisoformat(date_str).astimezone()
    except ValueError:
        return datetime.now(timezone.utc)

# ========== UI COMPONENTS ==========
def show_search_form():
    with st.form("main_search"):
        col1, col2 = st.columns([4, 1])
        with col1:
            query = st.text_input("Search", placeholder='Try: error 2400 or "exact phrase"')
        with col2:
            st.text("")  # Vertical spacer
            submit = st.form_submit_button("Search")
        return query.strip() if submit else None

def show_results_filters(issues):
    with st.expander("🔍 Filter Results", expanded=True):
        # Get unique values from results
        projects = sorted({issue['key'].split('-')[0] for issue in issues})
        statuses = sorted({issue['fields']['status']['name'] for issue in issues})
        
        cols = st.columns(3)
        with cols[0]:
            selected_projects = st.multiselect(
                "Projects", projects, default=projects,
                help="Filter by project type (RBOC, OMNI, etc.)")
        with cols[1]:
            date_filter = st.selectbox(
                "Updated Within",
                ["All time", "Last 7 days", "30 days", "90 days", "1 year"],
                index=0)
        with cols[2]:
            selected_statuses = st.multiselect(
                "Status", statuses, default=statuses)
        
        # Apply filters
        filtered = issues
        if selected_projects:
            filtered = [i for i in filtered if i['key'].split('-')[0] in selected_projects]
        if date_filter != "All time":
            days = {"Last 7 days":7, "30 days":30, "90 days":90, "1 year":365}[date_filter]
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            filtered = [i for i in filtered if parse_jira_date(i['fields']['updated']) > cutoff]
        if selected_statuses:
            filtered = [i for i in filtered if i['fields']['status']['name'] in selected_statuses]
        
        return filtered

def display_issue(issue, base_url):
    """Display a single issue with enhanced formatting"""
    project = issue['key'].split('-')[0]
    status = issue['fields']['status']['name']
    updated = parse_jira_date(issue['fields']['updated'])
    
    with st.container(border=True):
        # Header
        st.markdown(f"""
        <div style="display:flex; justify-content:space-between; margin-bottom:0.5rem;">
            <h3 style="margin:0;">{issue['key']}: {issue['fields']['summary']}</h3>
            <div>
                <span style="background:#e0e0e0; padding:2px 8px; border-radius:4px; font-size:0.9em;">
                    {project}
                </span>
                <span style="color:{'green' if status == 'Done' else 'orange'}; margin-left:8px;">
                    {status}
                </span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Metadata
        cols = st.columns([3,1])
        with cols[0]:
            if 'labels' in issue['fields'] and issue['fields']['labels']:
                st.caption(f"Labels: {', '.join(issue['fields']['labels'])}")
        with cols[1]:
            st.caption(f"Updated: {updated.strftime('%Y-%m-%d')}")
        
        # Description
        desc = issue['fields'].get('description')
        if desc:
            if "||" in desc:  # Jira table
                st.code(desc, language="markdown")
            else:
                st.text(desc[:300] + ("..." if len(desc) > 300 else ""))
        
        # Attachments
        if 'attachment' in issue['fields'] and issue['fields']['attachment']:
            with st.expander(f"📎 Attachments ({len(issue['fields']['attachment'])})"):
                for att in issue['fields']['attachment'][:3]:  # Show first 3
                    if att['mimeType'].startswith('image'):
                        st.image(att['content'], caption=att['filename'], width=200)
                    else:
                        st.markdown(f"[{att['filename']}]({att['content']})")
        
        # Footer
        st.markdown(f"[Open in Jira ↗]({base_url}/browse/{issue['key']})", unsafe_allow_html=True)

def show_pagination(total_items):
    total_pages = (total_items + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
    if total_pages > 1:
        cols = st.columns([1,2,1])
        with cols[0]:
            if st.button("◀ Previous", disabled=st.session_state.page <= 1):
                st.session_state.page -= 1
        with cols[1]:
            st.markdown(f"**Page {st.session_state.page} of {total_pages}**", unsafe_allow_html=True)
        with cols[2]:
            if st.button("Next ▶", disabled=st.session_state.page >= total_pages):
                st.session_state.page += 1

# ========== MAIN APP ==========
def main():
    st.title("🔍 Jira Search Pro+")
    
    # Authentication
    with st.sidebar:
        st.subheader("Credentials")
        base_url = st.text_input("Jira URL", placeholder="https://your-company.atlassian.net")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        
        if base_url and username and password:
            auth = HTTPBasicAuth(username, password)
            st.session_state.auth_verified = True
        else:
            st.session_state.auth_verified = False
    
    # Main search
    query = show_search_form()
    
    if query and st.session_state.auth_verified:
        with st.spinner("Searching..."):
            try:
                issues = search_jira(base_url, query, auth)
                st.session_state.raw_results = issues
                st.session_state.filtered_results = issues
                st.session_state.page = 1
            except Exception as e:
                st.error(f"Search failed: {str(e)}")
                return
    
    # Display results
    if st.session_state.raw_results:
        st.session_state.filtered_results = show_results_filters(st.session_state.raw_results)
        st.write(f"**{len(st.session_state.filtered_results)} results** (from {len(st.session_state.raw_results)} total)")
        
        if st.session_state.filtered_results:
            start = (st.session_state.page - 1) * RESULTS_PER_PAGE
            for issue in st.session_state.filtered_results[start:start+RESULTS_PER_PAGE]:
                display_issue(issue, base_url)
            show_pagination(len(st.session_state.filtered_results))
        else:
            st.warning("No matching results after filtering")

if __name__ == "__main__":
    main()
