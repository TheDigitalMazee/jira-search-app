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
    """Enhanced JQL builder with term boosting"""
    # Boost exact matches and important terms
    if '"' not in query:  # Not an exact phrase search
        terms = []
        for word in query.split():
            if word.lower() in ['error', 'fail', 'crash', 'bug']:
                terms.append(f'"{word}"^3')
            elif len(word) > 3:  # Boost longer terms more
                terms.append(f'"{word}"^2')
            else:
                terms.append(f'"{word}"')
        text_query = " AND ".join(terms)
    else:
        text_query = query
    
    jql_parts = [
        f'(summary ~ "{text_query}"^3 OR description ~ "{text_query}"^2 OR comment ~ "{text_query}")'
    ]
    
    if project_filter:
        jql_parts.append(f'project in ({",".join(project_filter)})')
    
    if date_filter:
        jql_parts.append(f'updated >= "{date_filter}"')
    
    return " AND ".join(jql_parts) + " ORDER BY updated DESC"

def search_jira(base_url, query, auth, max_results=100):
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

def parse_jira_date(date_str):
    """Handle Jira's date format with timezone awareness"""
    try:
        if '.' in date_str:
            date_str = date_str.split('.')[0] + date_str[-6:]  # Keep timezone
        if date_str.endswith('Z'):
            return datetime.fromisoformat(date_str[:-1] + '+00:00').astimezone()
        elif '+' in date_str or '-' in date_str[-6:]:
            return datetime.fromisoformat(date_str).astimezone()
        return datetime.fromisoformat(date_str + '+00:00').astimezone()
    except ValueError:
        return datetime.now(timezone.utc)

def format_description(desc):
    """Improved description formatting with table support"""
    if not desc:
        return "No description available"
    
    # Format Jira tables as code blocks
    if "||" in desc or "|" in desc:
        return f"```\n{desc}\n```"
    
    # Truncate long descriptions
    return desc[:500] + ("..." if len(desc) > 500 else "")

# ========== UI COMPONENTS ==========
def show_search_form():
    with st.form("main_search"):
        query = st.text_input("Search Query", 
                            placeholder="Try: 'error 2001' or \"exact phrase\"", 
                            key="search_query")
        submit = st.form_submit_button("🔍 Search Jira")
        return query.strip() if submit else None

def show_results_filters(issues):
    with st.expander("🔍 Filter Results", expanded=True):
        projects = sorted({issue['key'].split('-')[0] for issue in issues})
        
        col1, col2, col3 = st.columns(3)
        with col1:
            selected_projects = st.multiselect(
                "Project Types", options=projects, default=projects)
        with col2:
            date_filter = st.selectbox(
                "Updated Timeframe",
                options=["All", "Last 7 days", "Last 30 days", "Last 90 days", "Last 1 year"])
        with col3:
            statuses = sorted({issue['fields']['status']['name'] for issue in issues})
            selected_statuses = st.multiselect("Status", options=statuses, default=statuses)
        
        # Apply filters
        filtered = issues
        if selected_projects:
            filtered = [i for i in filtered if i['key'].split('-')[0] in selected_projects]
        if date_filter != "All":
            days = {"Last 7 days":7, "Last 30 days":30, "Last 90 days":90, "Last 1 year":365}[date_filter]
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            filtered = [i for i in filtered if parse_jira_date(i['fields']['updated']) > cutoff]
        if selected_statuses:
            filtered = [i for i in filtered if i['fields']['status']['name'] in selected_statuses]
        
        return filtered

def display_attachments(attachments):
    """Preview attachments with image support"""
    if not attachments:
        return
    
    with st.expander(f"📎 Attachments ({len(attachments)})"):
        for att in attachments[:3]:  # Show first 3 attachments
            col1, col2 = st.columns([1, 4])
            with col1:
                if att['mimeType'].startswith('image'):
                    st.image(att['content'], caption=att['filename'], width=150)
                else:
                    st.markdown(f"`{att['filename']}`")
            with col2:
                st.markdown(f"[View full content ↗]({att['content']})")

def display_results(issues, base_url):
    start = (st.session_state.page - 1) * RESULTS_PER_PAGE
    end = start + RESULTS_PER_PAGE
    
    for issue in issues[start:end]:
        project = issue['key'].split('-')[0]
        status = issue['fields']['status']['name']
        updated = parse_jira_date(issue['fields']['updated'])
        
        with st.container(border=True):
            # Header with project and status
            st.markdown(f"""
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <div>
                    <span style="font-size:18px; font-weight:bold;">{issue['key']}: {issue['fields']['summary']}</span>
                    <span style="background:#e0e0e0; padding:2px 8px; border-radius:4px; margin-left:8px; font-size:12px;">
                        {project}
                    </span>
                </div>
                <span style="color:{'green' if status == 'Done' else 'orange'};">
                    {status} • {updated.strftime('%Y-%m-%d')}
                </span>
            </div>
            """, unsafe_allow_html=True)
            
            # Description with improved formatting
            st.markdown(format_description(issue['fields'].get('description')))
            
            # Labels and comments count
            cols = st.columns(3)
            if 'labels' in issue['fields'] and issue['fields']['labels']:
                cols[0].markdown(f"**Labels:** {', '.join(issue['fields']['labels'])}")
            if 'comment' in issue['fields']:
                cols[1].markdown(f"**Comments:** {len(issue['fields']['comment']['comments'])}")
            cols[2].markdown(f"[Open in Jira ↗]({base_url}/browse/{issue['key']})", unsafe_allow_html=True)
            
            # Attachments preview
            if 'attachment' in issue['fields']:
                display_attachments(issue['fields']['attachment'])

def show_pagination(total_items):
    total_pages = (total_items + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
    if total_pages > 1:
        cols = st.columns([1, 2, 1])
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
    base_url = st.text_input("Jira URL", placeholder="https://your-company.atlassian.net")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    # Verify auth when all fields are filled
    if base_url and username and password:
        auth = HTTPBasicAuth(username, password)
        st.session_state.auth_verified = True
    else:
        st.session_state.auth_verified = False
    
    # Main search
    query = show_search_form()
    
    if query and st.session_state.auth_verified:
        with st.spinner(f"🔍 Searching for '{query}'..."):
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
        st.markdown(f"**Found {len(st.session_state.raw_results)} results** ({len(st.session_state.filtered_results)} after filtering)")
        
        if st.session_state.filtered_results:
            display_results(st.session_state.filtered_results, base_url)
            show_pagination(len(st.session_state.filtered_results))
        else:
            st.warning("No results match your filters")

if __name__ == "__main__":
    main()
