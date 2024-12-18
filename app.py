import streamlit as st
import requests
import pandas as pd
from collections import Counter
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import networkx as nx
import numpy as np

# Configure the page layout and style
st.set_page_config(
    page_title="Author Dashboard",
    page_icon="📚",
    layout="centered"
)

# Custom CSS to improve the appearance
st.markdown("""
    <style>
    .title {
        font-size: 64px !important;
        font-weight: bold !important;
        color: #E44242 !important;
        text-align: center !important;
        margin-bottom: 30px !important;
    }
    
    /* Style for the text input */
    .stTextInput input {
        font-size: 20px !important;
        padding: 15px !important;
        height: 40px !important;
    }

    /* Style for tables */
    .stDataFrame {
        width: 100% !important;
    }

    /* Handle text wrapping in table cells */
    .stDataFrame td, .stDataFrame th {
        white-space: normal !important;
        word-wrap: break-word !important;
        max-width: 200px !important;
        min-width: 50px !important;
        overflow-wrap: break-word !important;
        font-size: 14px !important;
    }

    /* Ensure table stays within container */
    [data-testid="stDataFrame"] > div {
        width: 100% !important;
        max-width: 100% !important;
        overflow: hidden !important;
    }

    /* Force table to stay within bounds */
    [data-testid="stDataFrame"] div[data-testid="StyledFullScreenFrame"] {
        width: 100% !important;
        max-width: 100% !important;
        min-width: 100% !important;
        overflow-x: hidden !important;
    }

    /* Adjust column widths for specific tables */
    [data-testid="stDataFrame"] table {
        table-layout: fixed !important;
        width: 100% !important;
    }

    /* Modify main container width */
    .block-container {
        max-width: 95% !important;
        padding-top: 1rem !important;
        padding-right: 1rem !important;
        padding-left: 1rem !important;
        padding-bottom: 1rem !important;
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=86400, show_spinner=False)  # Cache for 24 hours
def get_author_data(orcid):
    """Fetch author data from OpenAlex API"""
    base_url = f"https://api.openalex.org/authors/https://orcid.org/{orcid}"
    response = requests.get(base_url)
    if response.status_code == 200:
        return response.json()
    return None

@st.cache_data(ttl=86400, show_spinner=False)
def get_works(author_id):
    """Fetch all works by the author"""
    works = []
    page = 1
    per_page = 100
    
    while True:
        url = f"https://api.openalex.org/works?filter=author.id:{author_id}&page={page}&per-page={per_page}"
        response = requests.get(url)
        if response.status_code != 200:
            break
            
        data = response.json()
        works.extend(data['results'])
        
        if len(data['results']) < per_page:
            break
        page += 1
    
    return works


@st.cache_data(ttl=86400, show_spinner=False)
def get_citing_works_with_progress(works):
    """Wrapper function to show progress while fetching citing works"""
    citing_works = []
    work_ids = [work['id'] for work in works]
    total = len(work_ids)
    progress_bar = st.progress(0)
    
    for i, work_id in enumerate(work_ids):
        page = 1
        per_page = 100
        
        while True:
            url = f"https://api.openalex.org/works?filter=cites:{work_id}&page={page}&per-page={per_page}"
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                citing_works.extend(data['results'])
                
                # Check if there are more pages
                if len(data['results']) < per_page:
                    break
                page += 1
            else:
                break
        
        # Update progress
        progress = (i + 1) / total
        progress_bar.progress(progress)
    
    progress_bar.empty()
    return citing_works

@st.cache_data(ttl=86400, show_spinner=False)
def get_collaborators(works, author_id):
    """Extract unique collaborators from works, excluding the main author"""
    collaborators = []
    for work in works:
        for author in work.get('authorships', []):
            if (author.get('author') and 
                author['author'].get('id') != author_id):  # Exclude main author
                collaborators.append({
                    'name': author['author'].get('display_name'),
                    'id': author['author'].get('id')
                })
    return [c for c in collaborators if c['name'] is not None]

@st.cache_data(ttl=86400, show_spinner=False)
def get_institutions(affiliations):
    """Extract unique institutions from affiliations"""
    institutions = []
    for affiliation in affiliations:
        if affiliation.get('display_name') not in institutions:
            institutions.append(affiliation['institution'].get('display_name'))
            
    return institutions

@st.cache_data(ttl=86400, show_spinner=False)
def get_institutions_single(affiliations):
    """Extract unique institutions from affiliations"""
    
    try:
        insts = get_institutions(affiliations)
        
        if len(insts) == 0:
            return insts[0]
        
        if len(insts) > 2:
            return ", ".join(insts[:2])
        else:
            return ", ".join(insts)

    except:
        return 'Unknown institution'
    

@st.cache_data(ttl=86400, show_spinner=False)
def get_venue(work):
    """Extract venue from work"""
    try:
        venue = work.get('locations', {})[0]
        venue = venue.get('source', {})
        venue = venue.get('display_name', 'N/A')
        return venue
    except:
        return 'N/A'

def get_author_position(work, author_id):
    """Determine if author is first, last, or middle author"""
    authors = work.get('authorships', [])
    if not authors:
        return 'Unknown'
    
    author_positions = [i for i, author in enumerate(authors) 
                       if author.get('author', {}).get('id') == author_id]
    
    if not author_positions:
        return 'Unknown'
    
    position = author_positions[0]
    if position == 0:
        return 'First Author'
    elif position == len(authors) - 1:
        return 'Last Author'
    else:
        return 'Middle Author'

def create_publication_position_chart(works, author_id):
    """Create temporal chart of publications by author position"""
    # Extract year and position for each publication
    pub_data = []
    for work in works:
        year = work.get('publication_year')
        position = get_author_position(work, author_id)
        if year and position != 'Unknown':
            pub_data.append({'Year': year, 'Position': position})
    
    # Create DataFrame and count publications by year and position
    df = pd.DataFrame(pub_data)
    df_grouped = df.groupby(['Year', 'Position']).size().reset_index(name='Count')
    
    # Create the figure
    fig = px.bar(df_grouped, 
                 x='Year', 
                 y='Count',
                 color='Position',
                 title='Publications per Year by Author Position',
                 labels={'Count': 'Number of Publications'},
                 barmode='stack')
    
    fig.update_layout(
        xaxis_title="Year",
        yaxis_title="Number of Publications",
        legend_title="Author Position",
        plot_bgcolor='#0E1117',
        title_font_size=24  # Increase title font size
    )
    
    return fig

def create_citation_chart(citing_works, work_ids):
    """Create temporal chart of citations received"""

    cite_data = []
    for work in citing_works:
        year = work.get('publication_year')
        is_self = 'Self Citation' if work['id'] in works_ids else 'External Citation'
        if year:
            cite_data.append({'Year': year, 'Type': is_self})
    
    # Create DataFrame and count citations by year and type
    df = pd.DataFrame(cite_data)
    df_grouped = df.groupby(['Year', 'Type']).size().reset_index(name='Count')
    
    # Create the figure
    fig = px.bar(df_grouped, 
                 x='Year', 
                 y='Count',
                 color='Type',
                 title='Citations Received per Year',
                 labels={'Count': 'Number of Citations'},
                 barmode='stack')
    
    fig.update_layout(
        xaxis_title="Year",
        yaxis_title="Number of Citations",
        legend_title="Citation Type",
        plot_bgcolor='#0E1117',
        title_font_size=24  # Increase title font size
    )
    
    return fig

def create_unique_collaborators_chart(works, author_id):
    """Create chart showing number of unique collaborators per year"""
    # Track collaborators by year
    yearly_collaborators = {}
    
    # Sort works by year to track unique collaborators chronologically
    sorted_works = sorted(works, key=lambda x: x.get('publication_year', 0))
    
    for work in sorted_works:
        year = work.get('publication_year')
        if not year:
            continue
            
        if year not in yearly_collaborators:
            yearly_collaborators[year] = set()
            
        for author in work.get('authorships', []):
            if (author.get('author') and 
                author['author'].get('id') != author_id):
                yearly_collaborators[year].add(author['author'].get('id'))
    
    # Create data for plotting
    plot_data = pd.DataFrame([
        {'Year': year, 'Unique Collaborators': len(collaborators)}
        for year, collaborators in yearly_collaborators.items()
    ])
    
    fig = px.line(plot_data,
                  x='Year',
                  y='Unique Collaborators',
                  title='Number of Unique Collaborators per Year',
                  markers=True)
    
    fig.update_layout(
        xaxis_title="Year",
        yaxis_title="Number of Unique Collaborators",
        plot_bgcolor='#0E1117',
        title_font_size=24  # Increase title font size
    )
    
    return fig

def create_new_collaborators_chart(works, author_id):
    """Create chart showing mean number of new collaborators per paper per year"""
    # Track all known collaborators chronologically
    known_collaborators = set()
    yearly_new_collabs = {}
    yearly_paper_count = {}
    
    # Sort works by year
    sorted_works = sorted(works, key=lambda x: x.get('publication_year', 0))
    
    for work in sorted_works:
        year = work.get('publication_year')
        if not year:
            continue
            
        if year not in yearly_new_collabs:
            yearly_new_collabs[year] = 0
            yearly_paper_count[year] = 0
            
        new_collabs_this_paper = 0
        for author in work.get('authorships', []):
            if (author.get('author') and 
                author['author'].get('id') != author_id):
                author_id_current = author['author'].get('id')
                if author_id_current not in known_collaborators:
                    new_collabs_this_paper += 1
                    known_collaborators.add(author_id_current)
        
        yearly_new_collabs[year] += new_collabs_this_paper
        yearly_paper_count[year] += 1
    
    # Calculate mean new collaborators per paper
    plot_data = pd.DataFrame([
        {'Year': year,
         'Mean New Collaborators': yearly_new_collabs[year] / yearly_paper_count[year]}
        for year in yearly_new_collabs.keys()
    ])
    
    fig = px.line(plot_data,
                  x='Year',
                  y='Mean New Collaborators',
                  title='Average Number of New Collaborators per Paper per Year',
                  markers=True)
    
    fig.update_layout(
        xaxis_title="Year",
        yaxis_title="Mean New Collaborators per Paper",
        plot_bgcolor='#0E1117',
        title_font_size=24  # Increase title font size
    )
    
    return fig

def create_team_size_chart(works):
    """Create chart showing average team size per paper per year"""
    # Track team sizes by year
    yearly_team_sizes = {}
    yearly_paper_count = {}
    
    for work in works:
        year = work.get('publication_year')
        if not year:
            continue
            
        if year not in yearly_team_sizes:
            yearly_team_sizes[year] = 0
            yearly_paper_count[year] = 0
        
        team_size = len(work.get('authorships', []))
        yearly_team_sizes[year] += team_size
        yearly_paper_count[year] += 1
    
    # Calculate mean team size per year
    plot_data = pd.DataFrame([
        {'Year': year,
         'Mean Team Size': yearly_team_sizes[year] / yearly_paper_count[year]}
        for year in yearly_team_sizes.keys()
    ])
    
    plot_data = plot_data.sort_values('Year')
    
    fig = px.line(plot_data,
                  x='Year',
                  y='Mean Team Size',
                  title='Average Team Size per Paper per Year',
                  markers=True)
    
    fig.update_layout(
        xaxis_title="Year",
        yaxis_title="Mean Team Size",
        plot_bgcolor='#0E1117',
        title_font_size=24  # Increase title font size
    )
    
    return fig

def create_collaboration_distribution_chart(works, author_id):
    """Create histogram of collaboration frequencies"""
    # Get all collaborations
    collaborators = get_collaborators(works, author_id)
    collab_counts = Counter(c['name'] for c in collaborators)
    
    # Create frequency distribution
    freq_dist = Counter(collab_counts.values())
    
    # Convert to DataFrame for plotting
    plot_data = pd.DataFrame([
        {'Number of Collaborations': count, 'Frequency': freq}
        for count, freq in sorted(freq_dist.items())
    ])
    
    fig = px.bar(plot_data,
                 x='Number of Collaborations',
                 y='Frequency',
                 title='Distribution of Collaboration Frequencies',
                 labels={
                     'Number of Collaborations': 'Number of Times Collaborated',
                     'Frequency': 'Number of Collaborators'
                 })
    
    fig.update_layout(
        xaxis_title="Number of Times Collaborated",
        yaxis_title="Number of Collaborators",
        plot_bgcolor='#0E1117',
        paper_bgcolor='#0E1117',
        title_font_size=24
    )
    
    return fig

@st.cache_data(ttl=86400, show_spinner=False)
def get_institution_collaborations(works, author_id):
    """Extract institution collaborations from works"""
    institution_collabs = []
    for work in works:
        for author in work.get('authorships', []):
            if (not author.get('author') or 
                author['author'].get('id') == author_id):
                continue
                
            institutions = author.get('institutions', [])
            for inst in institutions:
                if inst.get('display_name'):
                    institution_collabs.append({
                        'name': inst.get('display_name'),
                        'id': inst.get('id')
                    })
    
    return [i for i in institution_collabs if i['name'] is not None]

def calculate_citation_concentration_index(citing_df):
    """Calculate the citation-concentration index"""
    # Get the list of citation counts
    citation_counts = citing_df['Incoming citations'].tolist()
    citation_counts.sort(reverse=True)
    
    # Find the largest number n where n papers cite >= n times
    n = 0
    for i, citations in enumerate(citation_counts, 1):
        if citations >= i:
            n = i
        else:
            break
    
    return n

@st.cache_data(ttl=86400, show_spinner=False)
def get_areas(author_data):
    """Extract research areas from author data"""
    topic = author_data.get('topics', [])
    topics = [t.get('subfield', {}).get('display_name', None) for t in topic]
    topics = [t for t in topics if t is not None]
    if len(topics) > 5:
        return list(set(topics[:5]))
    else:
        return list(set(topics))

@st.cache_data(ttl=86400, show_spinner=False)
def get_collaborator_network(works, author_id, author_name, max_depth=2):
    """Build a network of collaborators up to max_depth"""
    G = nx.Graph()
    processed_authors = set()
    
    # Add main author with provided name
    G.add_node(author_id, name=author_name, level=0)
    processed_authors.add(author_id)
    
    def add_collaborations(works, source_id, level):
        if level > max_depth:
            return
            
        # Create a single dictionary to track both counts and info
        author_data = {}
        
        # Single pass through works to collect all data
        for work in works:
            for authorship in work['authorships']:
                target_id = authorship['author'].get('id')
                if not target_id or target_id == source_id:
                    continue
                    
                if target_id not in author_data:
                    author_data[target_id] = {
                        'name': authorship['author'].get('display_name'),
                        'count': 1
                    }
                else:
                    author_data[target_id]['count'] += 1
        
        # Add nodes and edges for frequent collaborators
        frequent_collaborators = []
        for target_id, data in author_data.items():
            if data['count'] > 2:  # Only add frequent collaborators
                if target_id not in G:
                    G.add_node(target_id, name=data['name'], level=level)
                G.add_edge(source_id, target_id)
                frequent_collaborators.append(target_id)
        
        # Process next level
        if level < max_depth:
            # Batch API calls for next level
            for target_id in frequent_collaborators:
                if target_id not in processed_authors:
                    processed_authors.add(target_id)
                    collab_works_url = f"https://api.openalex.org/works?filter=author.id:{target_id}&per-page=100"
                    response = requests.get(collab_works_url)
                    if response.status_code == 200:
                        collab_works = response.json()['results']
                        add_collaborations(collab_works, target_id, level + 1)
    
    # Start building network
    add_collaborations(works, author_id, 1)
    return G

def create_network_graph(G, author_id):
    """Create interactive network visualization using Plotly"""
    pos = nx.spring_layout(G, k=1/np.sqrt(len(G.nodes())), iterations=50)
    
    # Calculate distances from main author
    distances = nx.single_source_shortest_path_length(G, author_id)
    
    edge_x = []
    edge_y = []
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])
    
    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=0.5, color='#888'),
        hoverinfo='none',
        mode='lines')
    
    node_x = []
    node_y = []
    node_colors = []
    node_sizes = []
    node_text = []
    
    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        
        # Color scheme based on distance
        if node == author_id:
            node_colors.append('#FFFF00')  # Yellow for main author
            node_sizes.append(20)
        else:
            # Dim nodes that are two edges away
            opacity = 1.0 if distances.get(node, 2) < 2 else 0.3
            node_colors.append(f'rgba(255,255,255,{opacity})')  # White with opacity
            node_sizes.append(15)
        
        # Hover text
        if node == author_id:
            node_text.append(f"Author: {G.nodes[node]['name']}<br>(Main Author)")
        else:
            node_text.append(f"Author: {G.nodes[node]['name']}")
    
    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers',
        hoverinfo='text',
        text=node_text,
        marker=dict(
            color=node_colors,
            size=node_sizes,
            line_width=2,
            line=dict(color='#000')
        ))
    
    fig = go.Figure(data=[edge_trace, node_trace],
                   layout=go.Layout(
                       showlegend=False,
                       hovermode='closest',
                       margin=dict(b=20, l=20, r=20, t=20),
                       plot_bgcolor='#0E1117',
                       paper_bgcolor='#0E1117',
                       xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                       yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                       height=800
                   ))
    
    return fig

# Add this function to search authors
@st.cache_data(ttl=86400, show_spinner=False)
def search_authors(query):
    """Search authors by name in OpenAlex"""
    if not query or len(query) < 3:  # Only search if query is meaningful
        return []
        
    url = f"https://api.openalex.org/authors?search={query}&per-page=10"
    response = requests.get(url)
    if response.status_code == 200:
        results = response.json()['results']
        # Format results for dropdown
        return [
            {
                'id': author['id'],
                'label': f"{author.get('display_name')} ({get_institutions_single(author.get('affiliations'))})",
                'display_name': author.get('display_name')
            }
            for author in results
            if author.get('display_name')
        ]
    return []

# Main title with custom styling
st.markdown('<p class="title">Citation Analytics Dashboard</p>', unsafe_allow_html=True)

# Add some spacing
st.write("")

# Create a container for the input field
with st.container():
    # Initialize session state for search
    if 'search_query' not in st.session_state:
        st.session_state.search_query = ''
    if 'selected_author' not in st.session_state:
        st.session_state.selected_author = None
    if 'search_results' not in st.session_state:
        st.session_state.search_results = []

    # Search input
    search_query = st.text_input(
        "Author Search",
        placeholder="Enter author name",
        help="Enter the name of the author you are interested in",
        key="author_search",
        label_visibility="collapsed"
    )

    # Update search results when query changes
    if search_query != st.session_state.search_query:
        st.session_state.search_query = search_query
        if len(search_query) >= 3:  # Only search if query is meaningful
            with st.spinner('Searching authors...'):
                st.session_state.search_results = search_authors(search_query)
                if not st.session_state.search_results:
                    st.error("No authors found matching your search query.")
        else:
            st.session_state.search_results = []
            st.session_state.selected_author = None

    # Show dropdown if we have results
    if st.session_state.search_results:
        options = {result['label']: result for result in st.session_state.search_results}
        # Add default option
        options = {"Select Author": None, **options}
        
        selected = st.selectbox(
            "Select Author",
            options.keys(),
            label_visibility="collapsed",
            index=0  # Show "Select Author" by default
        )
        
        if selected and selected != "Select Author":
            st.session_state.selected_author = options[selected]
        else:
            st.session_state.selected_author = None

    # Process selected author
    if st.session_state.selected_author:
        author_id = st.session_state.selected_author['id']
        # Get author data
        with st.spinner('Fetching author information...'):
            author_data = get_author_data(author_id)
            author_name = author_data.get('display_name')
            
        if author_data:
            # Display author info
            st.subheader("Author Information")
            st.markdown(f"## Name: {author_data.get('display_name')}")
            st.markdown(f"#### h-index: {author_data.get('summary_stats', {}).get('h_index', 'Not available')}")
            st.markdown(f"#### i10-index: {author_data.get('summary_stats', {}).get('i10_index', 'Not available')}")
            
            institutions = get_institutions(author_data['affiliations'])
            st.markdown(f"#### Institutions: {', '.join(institutions)}")
            
            areas = get_areas(author_data)
            st.markdown(f"#### Research Areas: {', '.join(areas)}")
            
            # Create an expander for all publication-related tables
            with st.expander("Publication Analytics", expanded=True):
                # Get and display works
                
                with st.spinner('Fetching publication data...'):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        works = get_works(author_data['id'])
                        works_ids = [work['id'] for work in works]
                        works_df = pd.DataFrame([{
                            'Title': w['title'],
                            'Year': str(w['publication_year']),  # Convert to string to prevent comma formatting
                            'Venue': get_venue(w),
                            'Citations': w.get('cited_by_count', 0)
                        } for w in works])
                    
                        st.subheader("Publications")
                        st.dataframe(
                            works_df.sort_values('Citations', ascending=False),
                            height=400,
                            hide_index=True
                        )
                        
                    with col2:
                        st.subheader("Top Collaborators")
                        collaborators = get_collaborators(works, author_data['id'])
                        collab_counts = Counter(c['name'] for c in collaborators)
                        collab_df = pd.DataFrame(
                            collab_counts.most_common(len(collab_counts)),
                            columns=['Collaborator', 'Number of Collaborations']
                        )
                        st.dataframe(collab_df, height=400, hide_index=True)
                    
                    # Display venues in second column
                    with col3:
                        st.subheader("Top Venues")
                        venue_counts = Counter(work['Venue'] for _, work in works_df.iterrows())
                        venue_df = pd.DataFrame(
                            venue_counts.most_common(len(venue_counts)),
                            columns=['Venue', 'Number of Publications']
                        )
                        venue_df = venue_df[venue_df['Venue'] != 'N/A']
                        st.dataframe(venue_df, height=400, hide_index=True)
                
                
                with st.spinner(f"Fetching what papers cited {author_name}'s {len(works)} papers... "):
                    col1, col2 = st.columns(2)
                    with col1:
                        citing_works = get_citing_works_with_progress(works)
                        citing_papers = [{
                            "ID": work['id'],
                            'Title': work['title'],
                            'Venue': get_venue(work),
                            'Is Self': 'True' if work['id'] in works_ids else 'False'
                        } for work in citing_works]
                        
                        citing_freq = Counter(d['ID'] for d in citing_papers)
                        
                        # Create DataFrame with ID counts and merge with paper details
                        citing_df = pd.DataFrame(
                            [(paper_id, count) for paper_id, count in citing_freq.most_common()],
                            columns=['ID', 'Incoming citations']
                        )
                        
                        # Add paper details by matching IDs
                        paper_details = pd.DataFrame(citing_papers)
                        citing_df = citing_df.merge(
                            paper_details[['ID', 'Title', 'Venue', 'Is Self']],
                            on='ID',
                            how='left'
                        )
                        # Reorder columns and drop ID
                        citing_df = citing_df[['Title', 'Venue', 'Incoming citations', 'Is Self']]
                        citing_df['Incoming citations'] = citing_df['Incoming citations'].astype(int)
                        
                        citing_df = citing_df.drop_duplicates()
                        st.subheader("Most Frequent Citing Papers")
                        st.dataframe(citing_df, height=400, hide_index=True)
                        
                        # Calculate and display citation-concentration index
                        c_index = calculate_citation_concentration_index(citing_df)
                        st.markdown(f"#### Citation-concentration index = {c_index}", help=f"This means there are {c_index} papers that each cite this author {c_index} or more times")
                        print(author_data.get('cited_by_count', 0))
                        print(author_data.get('summary_stats', {}).get('h_index', 1))
                        st.markdown(f"#### c/h² index = {author_data.get('cited_by_count', 0)/author_data.get('summary_stats', {}).get('h_index', 1)**2}", help=f"The c/h² index is a measure of the citation concentration of an author's papers. It is calculated by dividing the total number of citations by the square of the author's h-index. A lower c/h² index indicates that citations received by the author are concentrated in the papers which contribute to their h-index.")
                        st.markdown(f"#### Self-citation rate = {round(citing_df.loc[citing_df['Is Self'] == 'True']['Incoming citations'].sum() * 100/citing_df['Incoming citations'].sum(), 2)}%", help=f"The self-citation rate is the percentage of citations that are to the author's own papers. A higher self-citation rate indicates that the author cites their own papers more frequently.")
                    
                    with col2:
                        st.subheader("Most Frequent Institution Collaborations")
                        institution_collabs = get_institution_collaborations(works, author_data['id'])
                        inst_counts = Counter(i['name'] for i in institution_collabs)
                        inst_df = pd.DataFrame(
                            inst_counts.most_common(len(inst_counts)),
                            columns=['Institution', 'Number of Collaborations']
                        )
                        st.dataframe(inst_df, height=400, hide_index=True)
            # Create an expander for figures
            with st.expander("Figures", expanded=True):
                with st.spinner('Generating visualization charts...'):
                    # Publication position chart
                    col1, col2 = st.columns(2)
                    with col1:
                        pub_fig = create_publication_position_chart(works, author_data['id'])
                        st.plotly_chart(pub_fig, use_container_width=True)
                    
                    with col2:
                        cite_fig = create_citation_chart(citing_works, works_ids)
                        st.plotly_chart(cite_fig, use_container_width=True)
                    
                    col3, col4 = st.columns(2)
                    with col3:
                        # Unique collaborators chart
                        collab_fig = create_unique_collaborators_chart(works, author_data['id'])
                        st.plotly_chart(collab_fig, use_container_width=True)
                    
                    with col4:
                    # New collaborators chart
                        new_collab_fig = create_new_collaborators_chart(works, author_data['id'])
                        st.plotly_chart(new_collab_fig, use_container_width=True)
                    
                    
                    team_size_fig = create_team_size_chart(works)
                    
                    # Create two columns for team size and collaboration distribution
                    col5, col6 = st.columns(2)
                    
                    with col5:
                        st.plotly_chart(team_size_fig, use_container_width=True)
                    
                    with col6:
                        collab_dist_fig = create_collaboration_distribution_chart(works, author_data['id'])
                        st.plotly_chart(collab_dist_fig, use_container_width=True)
            
            with st.expander("Collaboration Network", expanded = True):                        # Add network visualization here
                st.subheader("Recent Collaboration Network")
                with st.spinner('Building collaboration network... this may take a while.'):
                    network = get_collaborator_network(works, author_data['id'], author_data.get('display_name'))
                    network_fig = create_network_graph(network, author_data['id'])
                    st.plotly_chart(network_fig, use_container_width=True, height=800)
            
        else:
            st.error("Could not find author with this ORCID ID") 

    # After creating the plot, add this JavaScript
    st.markdown("""
        <script>
        const graphDiv = document.querySelector('[id*="network_graph"]');
        if (graphDiv) {
            graphDiv.on('plotly_click', function(data) {
                if (!data || !data.points || !data.points[0]) return;
                
                const clickedNode = data.points[0].customdata;
                const graph = graphDiv.data[1];
                const colors = [];
                const neighbors = new Set();
                
                // Get neighbors of clicked node
                for (let i = 0; i < graphDiv.data[0].x.length; i += 3) {
                    const source = graphDiv.data[0].x[i];
                    const target = graphDiv.data[0].x[i + 1];
                    if (source === clickedNode) neighbors.add(target);
                    if (target === clickedNode) neighbors.add(source);
                }
                
                // Update colors
                for (let i = 0; i < graph.marker.color.length; i++) {
                    const nodeId = graph.customdata[i];
                    if (nodeId === clickedNode) {
                        colors.push('#FFFF00');  // Yellow for clicked node
                    } else if (neighbors.has(nodeId)) {
                        colors.push('#FFFFFF');  // White for neighbors
                    } else {
                        colors.push('rgba(255,255,255,0.3)');  // Dimmed for others
                    }
                }
                
                Plotly.restyle(graphDiv, {'marker.color': [colors]}, [1]);
            });
        }
        </script>
    """, unsafe_allow_html=True)