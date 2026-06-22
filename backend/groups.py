#queries for "all groups" page
import os, json
from db_connect import connection


# Core Configuration Rule: Handle environment flags safely
IS_PORTFOLIO = os.environ.get("PORTFOLIO_MODE", "False").strip().title() == "True"

def _get_portfolio_groups_directory():
    """
    In-memory dual-pass grouping emulator. Processes parent-child structures
    out of the frozen json array snapshot matching live presence matrix filters.
    """
    import json
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            snapshot = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    # Pull tables needed to satisfy structural checks
    groups = snapshot.get('kgroups', [])
    hosts = {int(h.get('group_id', 0)) for h in snapshot.get('videohost', [])}
    guests = {int(g.get('group_id', 0)) for g in snapshot.get('videoguest', [])}
    tinyguests = {int(t.get('group_id', 0)) for t in snapshot.get('tinyguest', [])}
    
    shows = snapshot.get('showtitle', snapshot.get('shows', []))
    ownership = snapshot.get('showownership', [])
    non_variety_show_ids = {int(s['title_id']) for s in shows if s.get('variety') == 0}
    owners = {int(o['group_id']) for o in ownership if int(o.get('title_id', 0)) in non_variety_show_ids}

    active_groups = []
    
    # 1. Apply active presence filter rule natively over snapshots
    for g in groups:
        g_id = int(g.get('group_id', 0))
        if g.get('group_name') == 'NCT U':
            continue
            
        has_presence = (g_id in hosts or g_id in guests or g_id in tinyguests or g_id in owners)
        if has_presence:
            # Shallow copy dictionary item to safely extend lists without contaminating snapshot caches
            active_groups.append(dict(g))

    # Sort alphabetical initially by name matching live ordering defaults
    active_groups.sort(key=lambda x: str(x.get('group_name', '')).lower())

    structured_groups = []
    lookup = {}

    # First Pass: Isolate Parent groups
    for row in active_groups:
        if row.get('parent_id') is None:
            row['subunits'] = []
            lookup[int(row['group_id'])] = row
            structured_groups.append(row)

    # Second Pass: Bind Child Subunits to their mapped structural parent lookups
    for row in active_groups:
        p_id = row.get('parent_id')
        if p_id is not None and int(p_id) in lookup:
            lookup[int(p_id)]['subunits'].append(row)

    # Ensure subunit nodes maintain ascending numeric sequence parity
    for parent in structured_groups:
        parent['subunits'].sort(key=lambda x: int(x.get('group_id', 0)))

    return structured_groups


def get_groups_directory():
    """
    Assembles structural nested parent-subunit dictionary indices.
    Switches environments dynamically safe from relational db network bottlenecks.
    """
    if IS_PORTFOLIO:
        return _get_portfolio_groups_directory()
    
    try:
        db, cursor = connection() 

        # 1. Define our Presence Filter logic
        # Host OR Guest OR Cameo OR Owns a Non-Variety Show
        presence_filter = """
            (EXISTS (SELECT 1 FROM videohost vh WHERE vh.group_id = g.group_id) OR
             EXISTS (SELECT 1 FROM videoguest vg WHERE vg.group_id = g.group_id) OR
             EXISTS (SELECT 1 FROM tinyguest tiny WHERE tiny.group_id = g.group_id) OR
             EXISTS (
                SELECT 1 FROM showownership sho 
                JOIN showtitle st ON sho.title_id = st.title_id 
                WHERE sho.group_id = g.group_id AND st.variety = 0
             ))
        """
        
        # 2. Updated Query: Pull only active groups
        query = f"""
            SELECT g.group_id, g.group_name, g.parent_id, g.grouptype
            FROM kgroups g
            WHERE g.group_name != 'NCT U' 
            AND {presence_filter}
            ORDER BY g.group_name ASC
        """
        
        cursor.execute(query)
        groups = cursor.fetchall() 
        
        # Organize data into a nested structure: { parent: [subunits] }
        structured_groups = []
        lookup = {}

        # First pass: Identify parents and initialize subunit lists
        for row in groups:
            if row['parent_id'] is None:
                row['subunits'] = []
                lookup[row['group_id']] = row
                structured_groups.append(row)
        
        # Second pass: Assign subunits to their respective parents
        # Note: A subunit will only show up if IT specifically has content
        for row in groups:
            if row['parent_id'] is not None and row['parent_id'] in lookup:
                lookup[row['parent_id']]['subunits'].append(row)

        # Sort subunits for each group by group_id
        for parent in structured_groups:
            parent['subunits'].sort(key=lambda x: x['group_id'])
        
        cursor.close()
        db.close()
        return structured_groups
    
    except Exception as e:
        print(f"Error: {e}")
        return []
    


