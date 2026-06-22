import os, json

# Core Configuration Rule: Safe evaluation of system environment flags
IS_PORTFOLIO = os.environ.get("PORTFOLIO_MODE", "False").strip().title() == "True"

def get_collection_criteria(slug):
    """
    Maps the sidebar slug to specific filtering logic.
    Refined logic as of Feb 14. [cite: 2026-02-14]
    """
    mapping = {
        'originals': {
            'logic': 'and', 'variety': 0, 'cats': [2, 3, 6, 10, 11],
            'sections': [
                {'label': 'Series', 'cats': [2]},
                {'label': 'Podcast', 'cats': [6]},
                {'label': 'Survival Shows', 'cats': [10]},
                {'label': 'Original Stuff', 'cats': [3, 11]}
            ]
        },
        'variety':   {
            'logic': 'variety_special', 'variety': 1, 'cats': [1, 4, 5, 6, 9],
            'sections': [
                {'label': 'TV Shows', 'cats': [1]},
                {'label': 'Youtube Shows', 'cats': [4]},
                {'label': 'Radio', 'cats': [5]},
                {'label': 'Podcast', 'cats': [6]},
                {'label': 'ISAC', 'cats': [9]}
            ]
        },
        'music':     {
            'logic': 'simple', 'cats': [7, 13, 14, 15, 21],
            'sections': [
                {'label': 'Music Shows', 'cats': [7]},
                {'label': 'Comeback Specials', 'cats': [14]},
                {'label': 'Concerts', 'cats': [15]},
                {'label': 'Concert DVD', 'cats': [13, 15]},
                {'label': 'K-Events', 'cats': [21]}
            ]
        },
        'kdrama':    {'logic': 'simple', 'cats': [8]},
        'moviedvd':  {'logic': 'owner_split', 'cats': [13]},
        'series':    {'logic': 'status_split', 'cats': [17]},
        'movies':    {'logic': 'simple', 'cats': [18]},
        'misc':      {
            'logic': 'simple', 'cats': [16, 19, 20],
            'sections': [
                {'label': 'Misc', 'cats': [16]},
                {'label': 'Others', 'cats': [19, 20]}
            ]
        }
    }
    return mapping.get(slug)


def _get_portfolio_collection_data(criteria):
    """
    Independent snapshot aggregator tracking exact variety/category partitions 
    from the data.json stack without modifying live storage connection pools.
    """
    sectioned_data = {}
    
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            snapshot = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return sectioned_data

    shows = snapshot.get('showtitle', [])
    ownership = snapshot.get('showownership', [])
    kgroups = snapshot.get('kgroups', [])
    showtitle_category = snapshot.get('showtitle_category', [])
    
    # Pre-map mappings for performant memory fetches
    group_map = {g['group_id']: g['group_name'] for g in kgroups}
    owner_map = {o['title_id']: group_map.get(o['group_id']) for o in ownership}

    show_to_categories_map = {}
    for sc in showtitle_category:
        t_id = int(sc['title_id'])
        c_id = int(sc['category_id'])
        show_to_categories_map.setdefault(t_id, set()).add(c_id)

    cat_set = set(criteria.get('cats', []))
    logic = criteria.get('logic')
    all_shows = []

    # Emulate complex database query where clauses safely
    for s in shows:
        if s.get('webstatus') != 'show':
            continue
            
        t_id = int(s['title_id'])
        item_cats = show_to_categories_map.get(t_id, set())
        
        # Verify intersection matches criteria categories array definitions
        if not item_cats.intersection(cat_set) and not (logic == 'variety_special' and 1 in item_cats):
            continue

        # Map aggregate properties mimicking MAX() and GROUP_CONCAT()
        show_copy = dict(s)
        show_copy['owner_name'] = owner_map.get(s['title_id'])
        show_copy['item_cats'] = ",".join(map(str, item_cats))
        
        variety_flag = s.get('variety', 0)

        if logic == 'and' and variety_flag == 0:
            all_shows.append(show_copy)
        elif logic == 'variety_special' and (1 in item_cats or (variety_flag == 1)):
            all_shows.append(show_copy)
        elif logic not in ['and', 'variety_special']:
            all_shows.append(show_copy)

    all_shows.sort(key=lambda x: str(x.get('title', '')).lower())

    # Apply identical specialized matrix rules splits
    if logic == 'owner_split':
        for s in all_shows:
            name = s['owner_name'] if s['owner_name'] else "Other"
            if name not in sectioned_data:
                sectioned_data[name] = []
            sectioned_data[name].append(s)
            
    elif logic == 'status_split':
        sectioned_data['Shows'] = [s for s in all_shows if s.get('watchStatus') is None]
        sectioned_data['Series'] = [s for s in all_shows if s.get('watchStatus') in ('Watching', 'Finished')]
        
    elif 'sections' in criteria:
        seen_ids = set()
        temp_storage = {}
        
        # 1. LOGIC PRIORITY: Claim duplicates for 'Concert DVD' first
        logic_ordered_sections = sorted(criteria['sections'], key=lambda x: x['label'] != 'Concert DVD')

        for sec in logic_ordered_sections:
            label = sec['label']
            temp_storage[label] = []
            
            for s in all_shows:
                if s['title_id'] in seen_ids:
                    continue
                
                item_cat_ids = {int(c) for c in s['item_cats'].split(',')}
                
                if label == 'Concert DVD' and 13 in item_cat_ids and 15 in item_cat_ids:
                    temp_storage[label].append(s)
                    seen_ids.add(s['title_id'])
                elif label == 'Concerts' and 15 in item_cat_ids and 13 not in item_cat_ids:
                    temp_storage[label].append(s)
                    seen_ids.add(s['title_id'])
                elif label not in ['Concert DVD', 'Concerts'] and any(int(c) in sec['cats'] for c in item_cat_ids):
                    temp_storage[label].append(s)
                    seen_ids.add(s['title_id'])

        # 2. DISPLAY PRIORITY: Match initial criteria sequence mappings
        for sec in criteria['sections']:
            label = sec['label']
            sectioned_data[label] = temp_storage.get(label, [])
    else:
        sectioned_data['All Titles'] = all_shows

    return sectioned_data


def fetch_collection_data(cursor, criteria):
    """
    Constructs the SQL based on the refined variety/category rules. [cite: 2026-02-14]
    """
    cat_list = ",".join(map(str, criteria.get('cats', [])))
    logic = criteria.get('logic')

    # Base query includes ownership and status for the sub-criteria splits [cite: 2026-02-14]
    query_base = """
        SELECT DISTINCT s.title_id, s.title, s.title_img, s.watchStatus, s.webstatus,
               MAX(k.group_name) as owner_name,
               GROUP_CONCAT(DISTINCT sc.category_id) as item_cats
        FROM showtitle s
        LEFT JOIN showtitle_category sc ON s.title_id = sc.title_id
        LEFT JOIN showownership sho ON s.title_id = sho.title_id
        LEFT JOIN kgroups k ON sho.group_id = k.group_id
    """

    if logic == 'and':
        where = f"WHERE s.webstatus = 'show' AND s.variety = 0 AND sc.category_id IN ({cat_list})"
    elif logic == 'variety_special':
        where = f"WHERE s.webstatus = 'show' AND ( (sc.category_id = 1) OR (s.variety = 1 AND sc.category_id IN ({cat_list})) )"
    else:
        where = f"WHERE s.webstatus = 'show' AND sc.category_id IN ({cat_list})"

    cursor.execute(f"{query_base} {where} GROUP BY s.title_id ORDER BY s.title ASC")
    all_shows = cursor.fetchall()

    sectioned_data = {}

    # Logic for specialized splits [cite: 2026-02-14]
    if logic == 'owner_split':
        # Group by group_name. If null, use 'Other'
        for s in all_shows:
            name = s['owner_name'] if s['owner_name'] else "Other"
            if name not in sectioned_data:
                sectioned_data[name] = []
            sectioned_data[name].append(s)
            
    elif logic == 'status_split':
        # Shows: Strictly NULL/None
        sectioned_data['Shows'] = [s for s in all_shows if s['watchStatus'] is None]
        # Series: Strictly Watching or Finished
        sectioned_data['Series'] = [s for s in all_shows if s['watchStatus'] in ('Watching', 'Finished')]
        
    elif 'sections' in criteria:
        seen_ids = set()
        temp_storage = {} # Temporary bucket to hold results
        
        # 1. LOGIC PRIORITY: Always process 'Concert DVD' first to claim the duplicates
        # We sort the sections so 'Concert DVD' logic runs before 'Concerts' logic
        logic_ordered_sections = sorted(
            criteria['sections'], 
            key=lambda x: x['label'] != 'Concert DVD'
        )

        for sec in logic_ordered_sections:
            label = sec['label']
            temp_storage[label] = []
            
            for s in all_shows:
                if s['title_id'] in seen_ids:
                    continue
                
                item_cat_ids = {int(c) for c in s['item_cats'].split(',')}
                
                # Logic: Claim Concert DVDs
                if label == 'Concert DVD':
                    if 13 in item_cat_ids and 15 in item_cat_ids:
                        temp_storage[label].append(s)
                        seen_ids.add(s['title_id'])
                
                # Logic: Claim standard Concerts (strictly no 13)
                elif label == 'Concerts':
                    if 15 in item_cat_ids and 13 not in item_cat_ids:
                        temp_storage[label].append(s)
                        seen_ids.add(s['title_id'])

                # Logic: Standard mapping
                elif any(int(c) in sec['cats'] for c in item_cat_ids):
                    temp_storage[label].append(s)
                    seen_ids.add(s['title_id'])
        
        # 2. DISPLAY PRIORITY: Put them back in the order they appear in get_collection_criteria
        for sec in criteria['sections']:
            label = sec['label']
            sectioned_data[label] = temp_storage.get(label, [])
    else:
        sectioned_data['All Titles'] = all_shows

    return sectioned_data