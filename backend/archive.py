import os, json
from db_connect import connection


# Core Configuration Rule: Safe evaluation of system environment flags
IS_PORTFOLIO = os.environ.get("PORTFOLIO_MODE", "False").strip().title() == "True"


def _get_portfolio_archive(target_id, scope):
    """
    Simulates the multi-phased database category filtration and matrix routing 
    by reading directly from the frozen static data.json schema arrays.
    """
    archive_results = {
        "gseries": [], "gvariety": [], "goriginals": [], "gtvshow": [],
        "glive": [], "gcomeback": [], "gcon": [], "gmove": [],
        "gradpod": [], "gmushow": [], "gdrama": [], "gevents": [],
        "gothers": []
    }
    
    snapshot_path = 'data.json'
    if not os.path.exists(snapshot_path):
        snapshot_path = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(__file__))), 'data.json')
        
    try:
        with open(snapshot_path, 'r', encoding='utf-8') as f:
            snapshot = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return archive_results

    # --- PHASE 1 EMULATION: RESOLVE SCOPE ---
    target_id = int(target_id)
    group_ids = [target_id]
    
    kgroups = snapshot.get('kgroups', [])
    parent_group = next((g for g in kgroups if int(g.get('group_id', 0)) == target_id), None)
    
    integrated_map = {'NCT': ['NCT U']}
    
    if scope == 'main' and parent_group and parent_group.get('group_name') in integrated_map:
        subunits_to_include = integrated_map[parent_group['group_name']]
        child_ids = [
            int(g['group_id']) for g in kgroups 
            if g.get('parent_id') is not None and int(g['parent_id']) == target_id and g.get('group_name') in subunits_to_include
        ]
        group_ids.extend(child_ids)
    elif scope == 'full':
        child_ids = [int(g['group_id']) for g in kgroups if g.get('parent_id') is not None and int(g['parent_id']) == target_id]
        group_ids.extend(child_ids)

    group_ids_set = set(group_ids)

    # Load raw schema tables from database freeze snap
    shows = snapshot.get('showtitle', [])
    categories_table = snapshot.get('category', [])
    showtitle_category = snapshot.get('showtitle_category', [])
    showownership = snapshot.get('showownership', [])
    titleguest = snapshot.get('titleguest', [])
    tinyguest = snapshot.get('tinyguest', [])
    videomushowmc = snapshot.get('videomushowmc', [])
    videohost = snapshot.get('videohost', [])
    video_showtitle = snapshot.get('video_showtitle', [])

    # Map category names correctly
    category_name_lookup = {int(c['category_id']): c['category_name'] for c in categories_table if c.get('category_id') is not None}

    # Map collections of category names grouped by Title ID
    show_cats = {}
    for sc in showtitle_category:
        t_id = int(sc['title_id'])
        c_id = int(sc['category_id'])
        c_name = category_name_lookup.get(c_id)
        if c_name:
            show_cats.setdefault(t_id, set()).add(c_name)

    # Map matching video collections to parent show codes
    show_vids = {}
    for vs in video_showtitle:
        show_vids.setdefault(int(vs['title_id']), set()).add(int(vs['video_id']))

    # --- RELATIONAL LOOKUP FIX ---
    # Multi-row grouping prevents duplicate overwrites and supports stable multi-owner conditions
    show_owners_map = {}
    for o in showownership:
        if o.get('group_id') is not None:
            show_owners_map.setdefault(int(o['title_id']), set()).add(int(o['group_id']))

    show_guests_map = {}
    for tg in titleguest:
        if tg.get('group_id') is not None:
            show_guests_map.setdefault(int(tg['title_id']), set()).add(int(tg['group_id']))

    # Video level proof trackers maps
    v_tiny_groups = {}
    for tiny in tinyguest:
        if tiny.get('group_id') is not None:
            v_tiny_groups.setdefault(int(tiny['video_id']), set()).add(int(tiny['group_id']))

    v_mc_groups = {}
    for mc in videomushowmc:
        if mc.get('group_id') is not None:
            v_mc_groups.setdefault(int(mc['video_id']), set()).add(int(mc['group_id']))

    v_host_groups = {}
    for vh in videohost:
        if vh.get('group_id') is not None:
            v_host_groups.setdefault(int(vh['video_id']), set()).add(int(vh['group_id']))

    for show in shows:
        t_id = int(show.get('title_id', 0))
        webstatus = show.get('webstatus', 'hidden')
        watch_status = show.get('watchStatus', '')
        
        if webstatus != 'show' or watch_status == 'Not Started':
            continue

        # Evaluate constraints securely against multiple row groups sets
        owned_by_group = bool(show_owners_map.get(t_id, set()).intersection(group_ids_set))
        is_title_guest = bool(show_guests_map.get(t_id, set()).intersection(group_ids_set))

        categories = show_cats.get(t_id, set())
        linked_vids = show_vids.get(t_id, set())

        # Check subquery EXISTS equivalents accurately over grouped sets across linked entries
        has_host_proof = any(bool(v_host_groups.get(v, set()).intersection(group_ids_set)) for v in linked_vids)
        has_mc_proof = any(bool(v_mc_groups.get(v, set()).intersection(group_ids_set)) for v in linked_vids)
        has_tiny_proof = any(bool(v_tiny_groups.get(v, set()).intersection(group_ids_set)) for v in linked_vids)

        # --- PHASE 3: THE DYNAMIC FETCHERS ENGINES ---
        
        # Series
        if any(c in ['Series', 'Youtube Shows', 'Survival Shows'] for c in categories) and owned_by_group:
            archive_results['gseries'].append(show)
            
        # Originals
        if any(c in ['Original Stuff', 'Mini Series'] for c in categories) and owned_by_group:
            archive_results['goriginals'].append(show)
            
        # TV Shows
        if any(c in ['TV Shows', 'ISAC', 'Others'] for c in categories) and owned_by_group:
            if 'TV Shows' in categories and 'ISAC' in categories:
                if has_host_proof:
                    archive_results['gtvshow'].append(show)
            else:
                archive_results['gtvshow'].append(show)

        # Livestreams
        if 'Livestream' in categories and owned_by_group:
            archive_results['glive'].append(show)
            
        # Comeback Specials
        if 'Comeback Specials' in categories and owned_by_group:
            archive_results['gcomeback'].append(show)
            
        # Movie/DVD
        if 'Movie/DVD' in categories and owned_by_group:
            archive_results['gmove'].append(show)
            
        # Concerts
        if 'Concert' in categories and owned_by_group and 'Movie/DVD' not in categories:
            archive_results['gcon'].append(show)
            
        # Radio & Podcast
        if any(c in ['Radio', 'Podcast'] for c in categories) and owned_by_group and has_host_proof:
            archive_results['gradpod'].append(show)
            
        # Music Shows
        if 'Music Shows' in categories and owned_by_group and has_mc_proof:
            archive_results['gmushow'].append(show)
            
        # Dramas
        if any(c in ['K-Drama', 'Dramas'] for c in categories) and owned_by_group:
            archive_results['gdrama'].append(show)
            
        # Events
        if 'K-Events' in categories and (owned_by_group or is_title_guest):
            archive_results['gevents'].append(show)
            
        # Variety (Guest Specific Matrix Routing Rule)
        if any(c in ['TV Shows','Youtube Shows','Radio','Podcast','K-Drama','Survival Shows'] for c in categories):
            if is_title_guest and ('TV Shows' in categories or not owned_by_group):
                archive_results['gvariety'].append(show)

        # Misc/Others Business Filtering Rules (Rule 1-4 pipeline)
        if not owned_by_group:
            if 'TV Shows' in categories and has_host_proof and not is_title_guest:
                archive_results['gothers'].append(show)
            elif any(c in ['Series', 'Mini Series', 'K-Drama', 'Original Stuff', 'Others'] for c in categories) and has_tiny_proof:
                archive_results['gothers'].append(show)
            elif 'Music Shows' in categories and has_mc_proof:
                archive_results['gothers'].append(show)
            elif any(c in ['Misc', 'Non-K Shows'] for c in categories) and (is_title_guest or has_tiny_proof or has_host_proof or has_mc_proof):
                archive_results['gothers'].append(show)

    # Deduplicate arrays and apply correct presentation sorts
    for key in archive_results:
        archive_results[key] = list({s['title_id']: s for s in archive_results[key]}.values())
        archive_results[key].sort(key=lambda x: (str(x.get('title', '')).lower(), int(x.get('title_id', 0))))
        
    # ─── 🔍 DROP THIS DIAGNOSTIC PRINT BLOCK HERE ───
    print(f"\n🧩 [PORTFOLIO DEBUG] Target Group ID: {target_id} | Scope: {scope}")
    print(f"👥 Active Group Filter IDs: {group_ids_set}")
    for k, v in archive_results.items():
        print(f"  ▪️ {k}: {len(v)} shows found")
    print("="*40 + "\n")
    # ───────────────────────────────────────────────
    
    
    return archive_results


def _get_portfolio_subunits(parent_id):
    """
    Simulates subunit presence checking matrices using file-based snapshot lookup filters.
    """
    import json
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            snapshot = json.load(f)
    except:
        return []

    kgroups = snapshot.get('kgroups', [])
    shows = snapshot.get('showtitle', [])
    showownership = snapshot.get('showownership', [])
    video_showtitle = snapshot.get('video_showtitle', [])
    
    subunits = [
        {'group_id': int(g['group_id']), 'group_name': g['group_name'], 'shows': []}
        for g in kgroups 
        if g.get('parent_id') is not None and int(g['parent_id']) == int(parent_id) and g.get('group_name') != 'NCT U'
    ]
    
    shows_map = {int(s['title_id']): s for s in shows if s.get('webstatus') == 'show'}
    
    show_latest_vid = {}
    for vs in video_showtitle:
        t_id = int(vs['title_id'])
        v_id = int(vs['video_id'])
        if t_id in shows_map:
            show_latest_vid[t_id] = max(show_latest_vid.get(t_id, 0), v_id)

    for sub in subunits:
        sub_id = sub['group_id']
        owned_title_ids = {int(o['title_id']) for o in showownership if o.get('group_id') is not None and int(o['group_id']) == sub_id}
        
        sub_shows = []
        for t_id in owned_title_ids:
            if t_id in shows_map and t_id in show_latest_vid:
                show_data = shows_map[t_id]
                sub_shows.append({
                    'title': show_data.get('title'),
                    'title_img': show_data.get('title_img'),
                    'title_id': show_data.get('title_id'),
                    'webstatus': show_data.get('webstatus'),
                    'latest_vid': show_latest_vid[t_id]
                })
                
        sub_shows.sort(key=lambda x: x['latest_vid'], reverse=True)
        sub['shows'] = sub_shows[:5]

    return subunits



def get_archive(target_id, scope='main'):
    """
    target_id: The group_id we are looking at.
    scope: 'main' (Parent only), 'full' (Parent + Subunits), 'subunit' (Specific child)
    """
    if IS_PORTFOLIO:
        return _get_portfolio_archive(target_id, scope)
    
    db, cursor = connection()
    target_id = int(target_id)
    
    # --- PHASE 1: RESOLVE SCOPE ---
    # Determine which IDs to include based on the brand relationship
    group_ids = [target_id]
    
    # Manual Configuration Mapping -> for subunit only in main
    integrated_map = {
        'NCT': ['NCT U'],
        # If you add more later: 'TripleS': ['TripleS NXT', 'TripleS Aria'],
    }

    if scope == 'main':
        # Get the group name for the target_id to check against the map
        cursor.execute("SELECT group_name FROM kgroups WHERE group_id = %s", (target_id,))
        parent_data = cursor.fetchone()
        
        if parent_data and parent_data['group_name'] in integrated_map:
            # Find the IDs for the subunits listed in the map
            subunits_to_include = integrated_map[parent_data['group_name']]
            
            format_strings = ','.join(['%s'] * len(subunits_to_include))
            cursor.execute(f"""
                SELECT group_id FROM kgroups 
                WHERE parent_id = %s AND group_name IN ({format_strings})
            """, (target_id, *subunits_to_include))
            
            rows = cursor.fetchall()
            group_ids.extend([row['group_id'] for row in rows])
            
    elif scope == 'full':
        # Standard: Parent + All Subunits
        cursor.execute("SELECT group_id FROM kgroups WHERE parent_id = %s", (target_id,))
        children = cursor.fetchall()
        group_ids.extend([c['group_id'] for c in children])

    # --- PHASE 2: DEFINE CONTENT GROUPS ---
    # Map specific logic groups to their database categories
    categories = {
        "gseries": ['Series', 'Youtube Shows', 'Survival Shows'],
        "gvariety": ['TV Shows','Youtube Shows','Radio','Podcast','K-Drama','Survival Shows'],
        "goriginals": ['Original Stuff', 'Mini Series'],
        "gtvshow": ['TV Shows', 'ISAC', 'Others'],
        "glive": ['Livestream'],
        "gcomeback": ['Comeback Specials'],
        "gcon": ['Concert'],
        "gmove": ['Movie/DVD'],
        "gradpod": ['Radio', 'Podcast'],
        "gmushow": ['Music Shows'],
        "gdrama": ['K-Drama', 'Dramas'],
        "gevents": ['K-Events']
    }

    # --- PHASE 3: THE DYNAMIC FETCHERS ---
    def fetch_data(cat_list, logic_type):
        placeholders = ','.join(['%s'] * len(cat_list))
        id_placeholders = ','.join(['%s'] * len(group_ids))
        
        # If we are looking at TV Shows, we strictly want shows where the group HOSTED a video
        if 'TV Shows' in cat_list and 'ISAC' in cat_list:
            query = f"""
                SELECT DISTINCT st.title_id, st.title, st.title_img, st.webstatus
                FROM showtitle st
                JOIN showtitle_category stc ON st.title_id = stc.title_id
                JOIN category c ON stc.category_id = c.category_id
                WHERE c.category_name IN ({placeholders})
                  AND (st.watchStatus != 'Not Started' OR st.watchStatus IS NULL)
                  AND st.webstatus = 'show'
                  AND EXISTS (
                      SELECT 1 FROM video_showtitle vs
                      JOIN videohost vh ON vs.video_id = vh.video_id
                      WHERE vs.title_id = st.title_id AND vh.group_id IN ({id_placeholders})
                  )
                ORDER BY st.title ASC, st.title_id ASC
            """
            cursor.execute(query, cat_list + group_ids)

        # Base query structure for OWNED shows (Series, Originals, etc.)
        elif logic_type == "owned":
            exclude_clause = ""
            # If we are fetching Concerts, exclude titles that are also Movies
            if 'Concert' in cat_list:
                exclude_clause = """
                    AND st.title_id NOT IN (
                        SELECT title_id FROM showtitle_category stc
                        JOIN category c ON stc.category_id = c.category_id
                        WHERE c.category_name = 'Movie/DVD'
                    )
                """

            # Proof of Content filter for rotating host categories
            proof_filter = ""
            if 'Radio' in cat_list:
                proof_filter = f"""
                    AND EXISTS (
                        SELECT 1 FROM video_showtitle vs
                        JOIN videohost vh ON vs.video_id = vh.video_id
                        WHERE vs.title_id = st.title_id AND vh.group_id IN ({id_placeholders})
                    )
                """
            elif 'Music Shows' in cat_list:
                proof_filter = f"""
                    AND EXISTS (
                        SELECT 1 FROM video_showtitle vs
                        JOIN videomushowmc vmc ON vs.video_id = vmc.video_id
                        WHERE vs.title_id = st.title_id AND vmc.group_id IN ({id_placeholders})
                    )
                """

            query = f"""
                SELECT DISTINCT st.title_id, st.title, st.title_img, st.webstatus
                FROM showtitle st
                JOIN showtitle_category stc ON st.title_id = stc.title_id
                JOIN category c ON stc.category_id = c.category_id
                WHERE c.category_name IN ({placeholders})
                  AND st.webstatus = 'show'
                  AND (st.watchStatus != 'Not Started' OR st.watchStatus IS NULL)
                  {exclude_clause}
                  {proof_filter}
                  AND EXISTS (
                      SELECT 1 FROM showownership so
                      WHERE so.title_id = st.title_id AND so.group_id IN ({id_placeholders})
                  )
                ORDER BY st.title ASC, st.title_id ASC
            """
            # If proof_filter is active, we need group_ids twice
            if proof_filter:
                params = cat_list + group_ids + group_ids
            else:
                params = cat_list + group_ids
        
            cursor.execute(query, params)
            
        # Logic for GUEST shows (Excluding owned content except for TV Shows)
        elif logic_type == "guest":
            query = f"""
                SELECT DISTINCT st.title_id, st.title, st.title_img, st.webstatus 
                FROM showtitle st
                JOIN showtitle_category stc ON st.title_id = stc.title_id
                JOIN category c ON stc.category_id = c.category_id
                WHERE c.category_name IN ({placeholders})
                  AND st.webstatus = 'show'
                  AND (st.watchStatus != 'Not Started' OR st.watchStatus IS NULL)
                  AND EXISTS (SELECT 1 FROM titleguest tg WHERE tg.title_id = st.title_id AND tg.group_id IN ({id_placeholders}))
                  AND (c.category_name = 'TV Shows' OR NOT EXISTS (
                      SELECT 1 FROM showownership so WHERE so.title_id = st.title_id AND so.group_id IN ({id_placeholders})
                  ))
                ORDER BY st.title ASC, st.title_id ASC
            """
            params = cat_list + group_ids + group_ids
            cursor.execute(query, params)
            return cursor.fetchall()

        # Logic for EVENTS (Host OR Guest)
        elif logic_type == "event":
            query = f"""
                SELECT DISTINCT st.title_id, st.title, st.title_img, st.webstatus
                FROM showtitle st
                JOIN showtitle_category stc ON st.title_id = stc.title_id
                JOIN category c ON stc.category_id = c.category_id
                WHERE c.category_name IN ({placeholders})
                  AND (
                      EXISTS (SELECT 1 FROM showownership so WHERE so.title_id = st.title_id AND so.group_id IN ({id_placeholders}))
                      OR EXISTS (SELECT 1 FROM titleguest tg WHERE tg.title_id = st.title_id AND tg.group_id IN ({id_placeholders}))
                  )
                  AND st.webstatus = 'show'
                ORDER BY st.title ASC, st.title_id ASC
            """
            cursor.execute(query, cat_list + group_ids + group_ids)
            
        return cursor.fetchall()
    
    # --- PHASE 4: SECURE MISC LOGIC ---
    def fetch_misc_data():
        id_placeholders = ','.join(['%s'] * len(group_ids))
        misc_shows = {}

        # ---------------------------------------------------------------------
        # STEP 1: Gather ALL shows where the group has ANY type of guest footprint
        # ---------------------------------------------------------------------
        raw_guest_query = f"""
            SELECT DISTINCT st.title_id, st.title, st.title_img, c.category_name
            FROM showtitle st
            JOIN showtitle_category stc ON st.title_id = stc.title_id
            JOIN category c ON stc.category_id = c.category_id
            LEFT JOIN video_showtitle vs ON st.title_id = vs.title_id
            WHERE st.webstatus = 'show'
              AND (st.watchStatus != 'Not Started' OR st.watchStatus IS NULL)
              AND (
                  -- Path A: Show-level title guest
                  EXISTS (SELECT 1 FROM titleguest tg WHERE tg.title_id = st.title_id AND tg.group_id IN ({id_placeholders}))
                  OR 
                  -- Path B: Video-level tiny guest
                  EXISTS (SELECT 1 FROM tinyguest tiny WHERE tiny.video_id = vs.video_id AND tiny.group_id IN ({id_placeholders}))
                  OR
                  -- Path C: Video-level host appearance
                  EXISTS (SELECT 1 FROM videohost vh WHERE vh.video_id = vs.video_id AND vh.group_id IN ({id_placeholders}))
                  OR
                  -- Path D: Music show MC tracking footprint
                  EXISTS (SELECT 1 FROM videomushowmc vmc WHERE vmc.video_id = vs.video_id AND vmc.group_id IN ({id_placeholders}))
              )
        """
        cursor.execute(raw_guest_query, group_ids * 4)
        candidates = cursor.fetchall()

        if not candidates:
            return []

        # ---------------------------------------------------------------------
        # STEP 2: Gather all show titles that this group explicitly OWNS
        # ---------------------------------------------------------------------
        candidate_ids = list(set([row['title_id'] for row in candidates]))
        title_placeholders = ','.join(['%s'] * len(candidate_ids))
        
        cursor.execute(f"""
            SELECT DISTINCT title_id FROM showownership 
            WHERE title_id IN ({title_placeholders}) AND group_id IN ({id_placeholders})
        """, candidate_ids + group_ids)
        owned_ids = {row['title_id'] for row in cursor.fetchall()}

        # ---------------------------------------------------------------------
        # STEP 3: Gather show-level title guest records to check Rule 1 & Rule 2 exclusions
        # ---------------------------------------------------------------------
        cursor.execute(f"""
            SELECT DISTINCT title_id FROM titleguest 
            WHERE title_id IN ({title_placeholders}) AND group_id IN ({id_placeholders})
        """, candidate_ids + group_ids)
        titleguest_ids = {row['title_id'] for row in cursor.fetchall()}

        # ---------------------------------------------------------------------
        # STEP 4: Gather specific video-level footprints for validation rules
        # ---------------------------------------------------------------------
        cursor.execute(f"""
            SELECT DISTINCT vs.title_id FROM video_showtitle vs
            JOIN tinyguest tiny ON vs.video_id = tiny.video_id
            WHERE vs.title_id IN ({title_placeholders}) AND tiny.group_id IN ({id_placeholders})
        """, candidate_ids + group_ids)
        tinyguest_ids = {row['title_id'] for row in cursor.fetchall()}

        cursor.execute(f"""
            SELECT DISTINCT vs.title_id FROM video_showtitle vs
            JOIN videomushowmc vmc ON vs.video_id = vmc.video_id
            WHERE vs.title_id IN ({title_placeholders}) AND vmc.group_id IN ({id_placeholders})
        """, candidate_ids + group_ids)
        musicmc_ids = {row['title_id'] for row in cursor.fetchall()}

        # ---------------------------------------------------------------------
        # STEP 5: Apply your exact Business Rules logic filters safely in Python
        # ---------------------------------------------------------------------
        for show in candidates:
            t_id = show['title_id']
            cat = show['category_name']

            # If the group explicitly OWNS the show title, it can never be in Misc
            if t_id in owned_ids:
                continue

            # Rule 1: 'TV Shows' -> Must have a footprint, but NOT titleguest
            if cat == 'TV Shows':
                if t_id not in titleguest_ids:
                    misc_shows[t_id] = show

            # Rule 2: 'Series', 'Mini Series', 'K-Drama', 'Original Stuff', 'Others' -> Must be tinyguest
            elif cat in ['Series', 'Mini Series', 'K-Drama', 'Original Stuff', 'Others']:
                if t_id in tinyguest_ids:
                    misc_shows[t_id] = show

            # Rule 3: 'Music Shows' -> Must be in videomushowmc table
            elif cat == 'Music Shows':
                if t_id in musicmc_ids:
                    misc_shows[t_id] = show

            # Rule 4: 'Misc', 'Non-K Shows' -> Simply must be a guest (passed Step 1 validation)
            elif cat in ['Misc', 'Non-K Shows']:
                misc_shows[t_id] = show

        # Final Presentation Formatting & Sorting
        final_misc_list = list(misc_shows.values())
        final_misc_list.sort(key=lambda x: (x['title'].lower(), x['title_id']))
        return final_misc_list

        

        

    # --- PHASE 5: EXECUTE AND ORGANIZE ---
    archive_results = {
        "gseries": fetch_data(categories["gseries"], "owned"),
        "gvariety": fetch_data(categories["gvariety"], "guest"),
        "goriginals": fetch_data(categories["goriginals"], "owned"),
        "gtvshow": fetch_data(categories["gtvshow"], "owned"),
        "glive": fetch_data(categories["glive"], "owned"),
        "gcomeback": fetch_data(categories["gcomeback"], "owned"),
        "gcon": fetch_data(categories["gcon"], "owned"),
        "gmove": fetch_data(categories["gmove"], "owned"),
        "gradpod": fetch_data(categories["gradpod"], "owned"),
        "gmushow": fetch_data(categories["gmushow"], "owned"),
        "gdrama": fetch_data(categories["gdrama"], "owned"),
        "gevents": fetch_data(categories["gevents"], "event"),
        "gothers": fetch_misc_data()
    }

    db.close()
    return archive_results


#get a glimpse of each subunits in the main page
def get_top_active_subunits(parent_id):

    if IS_PORTFOLIO:
        return _get_portfolio_subunits(parent_id)
    
    db, cursor = connection()
    
    # Use our standard Presence Filter
    presence_filter = """
        (
            EXISTS (
                SELECT 1
                FROM video v
                WHERE v.webstatus = 'show'
                AND (
                    EXISTS (SELECT 1 FROM videohost vh WHERE vh.video_id = v.video_id AND vh.group_id = g.group_id)
                    OR EXISTS (SELECT 1 FROM videoguest vg WHERE vg.video_id = v.video_id AND vg.group_id = g.group_id)
                    OR EXISTS (SELECT 1 FROM tinyguest tg WHERE tg.video_id = v.video_id AND tg.group_id = g.group_id)
                )
            )
            OR
            EXISTS (
                SELECT 1
                FROM showownership sho
                JOIN showtitle st ON sho.title_id = st.title_id
                WHERE sho.group_id = g.group_id
                  AND st.variety = 0
                  AND st.webstatus = 'show'
            )
        )
    """
    
    # Identify the subunits
    query = f"""
        SELECT g.group_id, g.group_name 
        FROM kgroups g 
        WHERE g.parent_id = %s 
            AND g.group_name != 'NCT U'
            AND {presence_filter} 
    """
    
    cursor.execute(query, (parent_id,))
    subunits = cursor.fetchall()

    # Fetch the content for each unit
    for sub in subunits:
        cursor.execute("""
            SELECT st.title, st.title_img, st.title_id, st.webstatus, MAX(vs.video_id) as latest_vid
            FROM showtitle st
            JOIN showownership so ON st.title_id = so.title_id
            JOIN video_showtitle vs ON st.title_id = vs.title_id
            JOIN video v ON vs.video_id = v.video_id
            WHERE so.group_id = %s AND st.webstatus = 'show' AND v.webstatus = 'show'
            GROUP BY st.title_id
            ORDER BY latest_vid DESC
            LIMIT 5
        """, (sub['group_id'],))
        # Store the show data directly in the subunit dictionary
        sub['shows'] = cursor.fetchall()

    db.close()
    return subunits