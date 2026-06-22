import os, json
from db_connect import connection


# Core Configuration Rule: Handle environment flags safely
IS_PORTFOLIO = os.environ.get("PORTFOLIO_MODE", "False").strip().title() == "True"

def _clean_none_str(val):
    """
    Normalizes any database NULLs, Python Nones, or explicit literal 'None' strings
    into a clean, empty string to prevent visual leakages on the template engine.
    """
    if val is None:
        return ""
    s = str(val).strip()
    if s.lower() in ("none", "null", ""):
        return ""
    return s


def _get_portfolio_show_details(show_id, group_id, scope):
    """
    In-memory structural tracking engine. Emulates complex parallel relational table lookups,
    release date tether anchors, and child tie-breaker array ordering algorithms.
    """
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            snapshot = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    # 1. EMULATE METADATA AGGREGATIONS
    shows = snapshot.get('showtitle', [])
    show_obj = next((s for s in shows if int(s.get('title_id', 0)) == int(show_id)), None)
    if not show_obj or show_obj.get('webstatus') != 'show':
        return None

    show = dict(show_obj)
    
    if isinstance(show.get('category_ids'), str):
        show['category_ids'] = [int(x) for x in show['category_ids'].split(',') if x.strip()]
    elif not show.get('category_ids'):
        show['category_ids'] = [int(show.get('category_id', 0))] if show.get('category_id') else []

    # Map category names array metadata
    st_cats = snapshot.get('showtitle_category', [])
    show['category_ids'] = [
        int(sc['category_id']) for sc in st_cats 
        if int(sc.get('title_id', 0)) == int(show_id) and sc.get('category_id') is not None
    ]

    categories_table = snapshot.get('category', [])
    cat_lookup = {int(c['category_id']): c['category_name'] for c in categories_table}
    show_cat_names = [cat_lookup[int(sc['category_id'])] for sc in st_cats if int(sc['title_id']) == int(show_id) if int(sc['category_id']) in cat_lookup]
    show['category_names'] = ", ".join(show_cat_names) if show_cat_names else ""

    # Map season name dictionaries
    seasons = snapshot.get('season_names', [])
    show['season_names'] = {
        int(sn['season_number']): sn['season_name'] 
        for sn in seasons if int(sn.get('title_id', 0)) == int(show_id)
    }

    # 2. FILTER ALL LINKED VIDEOS
    v_showtitle = snapshot.get('video_showtitle', [])
    linked_video_ids = {int(vs['video_id']) for vs in v_showtitle if int(vs.get('title_id', 0)) == int(show_id)}
    
    videos_table = snapshot.get('video', [])
    all_videos = [
        dict(v) for v in videos_table 
        if int(v.get('video_id', 0)) in linked_video_ids and v.get('webstatus') == 'show'
    ]

    video_ids = [int(v['video_id']) for v in all_videos]

    # Map Songs Extension Matrix Lookups
    music_recs = snapshot.get('video_music_recs', [])
    songs_table = snapshot.get('songs', [])
    songs_map = {int(s['song_id']): s for s in songs_table}
    
    video_music_map = {}
    for vmr in music_recs:
        vid = int(vmr.get('video_id', 0))
        if vid in video_ids:
            song_obj = songs_map.get(int(vmr.get('song_id', 0)))
            if song_obj:
                row = dict(vmr)
                row.update(song_obj)
                video_music_map.setdefault(vid, []).append(row)

    for v in all_videos:
        v['songs'] = video_music_map.get(int(v['video_id']), [])

    # 3. CLEANING & DATE OVERRIDE ALGORITHMS
    raw_order = show.get('season_order') or ""
    manual_order = [x.strip() for x in raw_order.split(',') if x.strip()]

    def get_season_weight(video_node):
        s = video_node.get('season')
        if not s or str(s).strip().lower() in ('none', 'null', ''): return (3, 0)
        if manual_order and str(s).strip() in manual_order:
            return (0, manual_order.index(str(s).strip()))
        try:
            return (1, float(s))
        except (ValueError, TypeError):
            return (2, str(s).strip().upper())

    parent_dates = {}
    for v in all_videos:
        curr_s = str(v.get('season') or '').strip()
        if curr_s.lower() in ('none', 'null'): curr_s = ''
        curr_e = str(v.get('episodeNumber') or '').strip().upper()
        if curr_e.lower() in ('none', 'null'): curr_e = ''
        
        if curr_e.isdigit() and not v.get('title_extras'):
            parent_dates[(curr_s, curr_e)] = v.get('releaseDate', '9999-99-99')

    for v in all_videos:
        curr_s = str(v.get('season') or '').strip()
        if curr_s.lower() in ('none', 'null'): curr_s = ''
        curr_e = str(v.get('episodeNumber') or '').strip().upper()
        if curr_e.lower() in ('none', 'null'): curr_e = ''
        
        v['season'] = curr_s
        v['episodeNumber'] = curr_e
        
        try:
            if curr_s: float(curr_s); v['is_numeric_season'] = True
        except: v['is_numeric_season'] = False
        try:
            if curr_e: float(curr_e); v['is_numeric_episode'] = True
        except: v['is_numeric_episode'] = False

        real_date = v.get('releaseDate') if v.get('releaseDate') else '9999-99-99'
        is_child = bool(v.get('title_extras') and curr_e.isdigit())

        if is_child and (curr_s, curr_e) in parent_dates:
            v['sort_date'] = str(parent_dates[(curr_s, curr_e)])
        else:
            v['sort_date'] = str(real_date)

        if not v.get('title_extras') and curr_e.isdigit():
            v['tie_break'] = 0
        elif curr_e == 'SPE':
            v['tie_break'] = 1
        elif is_child:
            v['tie_break'] = 2
        else:
            v['tie_break'] = 3

    all_videos.sort(key=lambda x: (
        get_season_weight(x),
        x['sort_date'],   
        x['tie_break'],   
        (0, int(x['episodeNumber'])) if x['episodeNumber'].isdigit() else (1, x['episodeNumber']),
        int(x['video_id'])
    ))

    # 4. GUEST / PARTICIPANTS DISPLAY MATRICES
    members_table = snapshot.get('members', [])
    kgroups = snapshot.get('kgroups', [])
    member_map = {int(m['member_id']): m['member_name'] for m in members_table if m.get('member_id') is not None}
    group_map = {int(g['group_id']): g['group_name'] for g in kgroups if g.get('group_id') is not None}
    
    # Track ALL possible groups a member belongs to instead of overwriting them into a single string
    member_groups = snapshot.get('member_groups', [])
    m_groups_collection = {}
    for mg in member_groups:
        if mg.get('member_id') is not None and mg.get('group_id') is not None:
            m_groups_collection.setdefault(int(mg['member_id']), set()).add(int(mg['group_id']))

    # E_Guests lookups with explicit row-level pairing filters
    v_guests = snapshot.get('videoguest', [])
    video_guest_map = {}
    for vg in v_guests:
        vid = int(vg.get('video_id', 0))
        if vid in video_ids:
            video_guest_map.setdefault(vid, {'members': [], 'groups': []})
            m_id = vg.get('member_id')
            g_id = vg.get('group_id')
            
            if m_id and str(m_id).strip().lower() not in ('none', 'null', ''):
                m_id_int = int(m_id)
                # If row defines group context explicitly, use it. Else check options mapping.
                assigned_gid = int(g_id) if (g_id and str(g_id).strip().lower() not in ('none', 'null', '')) else None
                
                # Relational Parity: Match group context exactly like SQL joins do
                possible_gids = m_groups_collection.get(m_id_int, set())
                final_gid = assigned_gid if (assigned_gid in possible_gids) else (list(possible_gids)[0] if possible_gids else None)
                
                video_guest_map[vid]['members'].append({
                    'name': member_map.get(m_id_int),
                    'group': group_map.get(final_gid) if final_gid else None
                })
            elif g_id and str(g_id).strip().lower() not in ('none', 'null', ''):
                video_guest_map[vid]['groups'].append(group_map.get(int(g_id)))

    # E_Hosts lookups with explicit row-level pairing filters
    v_hosts = snapshot.get('videohost', [])
    video_host_map = {}
    for vh in v_hosts:
        vid = int(vh.get('video_id', 0))
        if vid in video_ids:
            video_host_map.setdefault(vid, {'members': [], 'groups': []})
            m_id = vh.get('member_id')
            g_id = vh.get('group_id')
            
            if m_id and str(m_id).strip().lower() not in ('none', 'null', ''):
                m_id_int = int(m_id)
                assigned_gid = int(g_id) if (g_id and str(g_id).strip().lower() not in ('none', 'null', '')) else None
                
                possible_gids = m_groups_collection.get(m_id_int, set())
                final_gid = assigned_gid if (assigned_gid in possible_gids) else (list(possible_gids)[0] if possible_gids else None)
                
                video_host_map[vid]['members'].append({
                    'name': member_map.get(m_id_int),
                    'group': group_map.get(final_gid) if final_gid else None
                })
            elif g_id and str(g_id).strip().lower() not in ('none', 'null', ''):
                video_host_map[vid]['groups'].append(group_map.get(int(g_id)))

    # Livestream Tags and MC pairs lookups
    v_tags = snapshot.get('videolivetags', [])
    tag_names = {int(t['tag_id']): t['tag_name'] for t in snapshot.get('livestreamtags', []) if t.get('tag_id') is not None}
    video_tag_map = {}
    for vt in v_tags:
        vid = int(vt.get('video_id', 0))
        if vid in video_ids:
            video_tag_map.setdefault(vid, []).append(tag_names.get(int(vt.get('tag_id', 0))))

    v_mc = snapshot.get('videomushowmc', [])
    mc_pairs = {int(p['mc_id']): p['mc_pairname'] for p in snapshot.get('musicshowmc', []) if p.get('mc_id') is not None}
    video_mc_map = {}
    for vmc in v_mc:
        vid = int(vmc.get('video_id', 0))
        if vid in video_ids:
            video_mc_map.setdefault(vid, {'pairing': mc_pairs.get(int(vmc.get('mc_id', 0))), 'names': []})
            mc_entry = {'name': member_map.get(int(vmc.get('member_id', 0))), 'group': group_map.get(int(vmc.get('group_id', 0)))}
            if mc_entry not in video_mc_map[vid]['names']:
                video_mc_map[vid]['names'].append(mc_entry)

    # 5. RESOLVE SCOPES AND CONTEXT HIGHLIGHTS
    target_group_ids = []
    if group_id is not None:
        try:
            gid = int(group_id)
            if gid: target_group_ids.append(gid)
            if scope == 'full':
                parent_match = next((g.get('parent_id') for g in kgroups if int(g.get('group_id', 0)) == gid), None)
                brandparent_id = int(parent_match) if (parent_match and str(parent_match).strip().lower() not in ('none', 'null', '')) else gid
                
                target_group_ids = []
                for g in kgroups:
                    curr_gid = int(g.get('group_id', 0))
                    raw_pid = g.get('parent_id')
                    curr_pid = int(raw_pid) if (raw_pid and str(raw_pid).strip().lower() not in ('none', 'null', '')) else None
                    
                    if curr_gid == brandparent_id or curr_pid == brandparent_id:
                        target_group_ids.append(curr_gid)
        except:
            pass

    ownership_table = snapshot.get('showownership', [])
    group_ownership = any(int(o.get('title_id', 0)) == int(show_id) and int(o.get('group_id', 0)) in target_group_ids for o in ownership_table)

    owners_list = [group_map[int(so['group_id'])] for so in ownership_table if int(so['title_id']) == int(show_id) if so.get('group_id')]
    show['ownership_groups'] = ", ".join(owners_list) if owners_list else ""

    show_variety = show.get('variety', 0)
    for v in all_videos:
        vid = int(v['video_id'])
        v['livestream_tags'] = video_tag_map.get(vid, [])
        
        mc_info = video_mc_map.get(vid)
        if mc_info:
            v['mc_pairing'] = mc_info['pairing']
            v['mc_names'] = mc_info['names']

        v_g_data = video_guest_map.get(vid, {'members': [], 'groups': []})
        g_group_map = {}
        for m in v_g_data['members']:
            if m['name']: g_group_map.setdefault(m['group'], []).append(m['name'])
        g_parts = [f"{g} ({', '.join(g_group_map[g])})" if len(g_group_map[g]) > 1 else f"{g} {g_group_map[g][0]}" for g in sorted(g_group_map)]
        g_parts.extend([g for g in v_g_data['groups'] if g])
        v['guest_display'] = ' • '.join(g_parts)

        v_h_data = video_host_map.get(vid, {'members': [], 'groups': []})
        h_group_map = {}
        for m in v_h_data['members']:
            if m['name']: h_group_map.setdefault(m['group'], []).append(m['name'])
        h_parts = []
        if show_variety == 0:
            unique_members = list(dict.fromkeys([m['name'] for m in v_h_data['members'] if m['name']]))
            if unique_members: h_parts.append(' • '.join(unique_members))
        else:
            h_parts = [f"{g} ({', '.join(h_group_map[g])})" if len(h_group_map[g]) > 1 else f"{g} {h_group_map[g][0]}" for g in sorted(h_group_map)]
        h_parts.extend([g for g in v_h_data['groups'] if g])
        v['host_display'] = ' • '.join(h_parts)

        is_related = False
        if target_group_ids:
            h_matched = any(int(h.get('video_id', 0)) == vid and int(h.get('group_id', 0)) in target_group_ids for h in v_hosts)
            g_matched = any(int(g.get('video_id', 0)) == vid and int(g.get('group_id', 0)) in target_group_ids for g in v_guests)
            t_matched = any(int(t.get('video_id', 0)) == vid and int(t.get('group_id', 0)) in target_group_ids for t in snapshot.get('tinyguest', []))
            m_matched = vid in video_mc_map and any(int(mc.get('group_id', 0)) in target_group_ids for mc in v_mc if int(mc.get('video_id', 0)) == vid)

            if m_matched: is_related = True
            elif scope != 'full' and int(show_id) in [44, 105, 108, 115, 122]: is_related = (h_matched or g_matched or t_matched)
            elif group_ownership:
                if any(cat in show['category_ids'] for cat in (1, 5)): is_related = (h_matched or g_matched or t_matched)
                else: is_related = (g_matched or t_matched)
            elif v.get('is_variety') == 1: is_related = (h_matched or g_matched or t_matched)

        v['is_group_context'] = is_related

    return {"show": show, "videos": all_videos, "extras": []}


def get_show_details(show_id, group_id=None, scope='main'):
    """
    Assembles complete nested episode and tracking metrics indices.
    Bypasses live engine blocks instantly when IS_PORTFOLIO configuration active.
    """
    if IS_PORTFOLIO:
        return _get_portfolio_show_details(show_id, group_id, scope)

    db, cursor = connection()
    
    try:
        # 1. FETCH SHOW METADATA
        cursor.execute("""
            SELECT s.title_id, s.title, s.releaseYear, s.totalSeasons, s.totalEpisodes, s.variety,
                   s.title_img, s.watchStatus, s.season_order, s.webstatus,
                   GROUP_CONCAT(DISTINCT sc.category_id) AS category_ids,
                   IFNULL(GROUP_CONCAT(DISTINCT c.category_name SEPARATOR ', '), '') AS category_names,
                   IFNULL(GROUP_CONCAT(DISTINCT g.group_name SEPARATOR ', '), '') AS ownership_groups,
                   IFNULL(GROUP_CONCAT(DISTINCT m.member_name SEPARATOR ', '), '') AS ownership_members,
                   IFNULL(GROUP_CONCAT(DISTINCT tg.group_name SEPARATOR ', '), '') AS guest_groups
            FROM showtitle s
            LEFT JOIN showtitle_category sc ON s.title_id = sc.title_id
            LEFT JOIN category c ON sc.category_id = c.category_id
            LEFT JOIN showownership so ON s.title_id = so.title_id
            LEFT JOIN kgroups g ON so.group_id = g.group_id
            LEFT JOIN members m ON so.member_id = m.member_id
            LEFT JOIN titleguest tgu ON s.title_id = tgu.title_id
            LEFT JOIN kgroups tg ON tgu.group_id = tg.group_id
            WHERE s.title_id = %s AND s.webstatus = 'show'
            GROUP BY s.title_id
        """, (show_id,))
        show = cursor.fetchone()

        if not show:
            return None
        
        # --- Manual Season Sequence Parsing ---
        raw_order = show.get('season_order') or ""
        manual_order = [x.strip() for x in raw_order.split(',') if x.strip()]

        # Clean up category IDs
        if show['category_ids']:
            show['category_ids'] = [int(cid) for cid in show['category_ids'].split(',')]
        else:
            show['category_ids'] = []

        # Map Season Names
        cursor.execute("SELECT season_number, season_name FROM season_names WHERE title_id = %s", (show_id,))
        season_names_rows = cursor.fetchall()
        show['season_names'] = {row['season_number']: row['season_name'] for row in season_names_rows}

        # 2. FETCH ALL VIDEOS (NORMAL & EXTRAS)
        cursor.execute("""
            SELECT
                v.video_id, v.season, v.episodeNumber, v.video_title,
                v.releaseDate, v.title_extras, v.video_notes, v.webstatus, v.is_variety
            FROM video v
            JOIN video_showtitle vs ON v.video_id = vs.video_id
            WHERE vs.title_id = %s AND v.webstatus = 'show'
        """, (show_id,))
        all_videos = cursor.fetchall()

        video_ids = [v['video_id'] for v in all_videos]

        # fetching songs
        video_music_map = {}
        if video_ids:
            format_strings = ','.join(['%s'] * len(video_ids))
            cursor.execute(f"""
                SELECT vmr.video_id, s.songtitle, s.artist, s.spotify_link, s.youtube_link, vmr.sort_order
                FROM video_music_recs vmr
                JOIN songs s ON vmr.song_id = s.song_id
                WHERE vmr.video_id IN ({format_strings})
                ORDER BY vmr.sort_order ASC
            """, tuple(video_ids))
            for row in cursor.fetchall():
                vid = row['video_id']
                video_music_map.setdefault(vid, []).append(row)
        
        # Add the songs list to each video object
        for v in all_videos:
            v['songs'] = video_music_map.get(v['video_id'], [])

        # --- 3. CLEANING & DATE OVERRIDE ---
        def get_season_weight(v):
            s = v['season']
            if not s: return (3, 0)
            if manual_order and s in manual_order:
                return (0, manual_order.index(s))
            try:
                return (1, float(s))
            except (ValueError, TypeError):
                return (2, s.upper())

        # FIRST PASS: Map main episodes to their release dates to create the "tether"
        parent_dates = {}
        for v in all_videos:
            curr_s = str(v.get('season') or '').strip()
            curr_e = str(v.get('episodeNumber') or '').strip().upper()
            # Only map if it's a numeric episode and NOT an extra/behind
            if curr_e.isdigit() and not v.get('title_extras'):
                parent_dates[(curr_s, curr_e)] = v['releaseDate']

        # SECOND PASS: Assign Sort Anchors
        for v in all_videos:
            curr_s = str(v.get('season') or '').strip()
            curr_e = str(v.get('episodeNumber') or '').strip().upper()
            v['season'] = curr_s
            v['episodeNumber'] = curr_e
            
            # Numeric flags for the template
            try:
                if curr_s: float(curr_s); v['is_numeric_season'] = True
            except: v['is_numeric_season'] = False
            try:
                if curr_e: float(curr_e); v['is_numeric_episode'] = True
            except: v['is_numeric_episode'] = False

            # --- THE ANCHOR LOGIC ---
            real_date = v['releaseDate'] if v['releaseDate'] else '9999-99-99'
            is_child = bool(v.get('title_extras') and curr_e.isdigit())

            if is_child and (curr_s, curr_e) in parent_dates:
                # OVERRIDE: Use parent's date so it sticks to the episode
                v['sort_date'] = str(parent_dates[(curr_s, curr_e)])
            else:
                # STANDALONE: Use its own date
                v['sort_date'] = str(real_date)

            # Tie-break: Ep (0), SPE (1), Behind/Extra (2), Standalone on same day (3)
            if not v.get('title_extras') and curr_e.isdigit():
                v['tie_break'] = 0
            elif curr_e == 'SPE':
                v['tie_break'] = 1
            elif is_child:
                v['tie_break'] = 2
            else:
                v['tie_break'] = 3

        # FINAL SORT
        all_videos.sort(key=lambda x: (
            get_season_weight(x),
            x['sort_date'],   
            x['tie_break'],   
            int(x['episodeNumber']) if x['episodeNumber'].isdigit() else x['episodeNumber'],
            x['video_id']
        ))

        video_ids = [v['video_id'] for v in all_videos]

        # 5. GUEST DISPLAY LOGIC
        video_guest_map = {}
        video_host_map = {}
        video_tag_map = {}
        video_mc_map = {}

        if video_ids:
            format_strings = ','.join(['%s'] * len(video_ids))
            params = tuple(video_ids)

            # GUEST QUERY
            cursor.execute(f"""
                SELECT vg.video_id, m.member_name, g1.group_name AS member_group, g2.group_name AS guest_group
                FROM videoguest vg
                LEFT JOIN members m ON vg.member_id = m.member_id
                LEFT JOIN member_groups mg ON m.member_id = mg.member_id
                LEFT JOIN kgroups g1 ON mg.group_id = g1.group_id
                LEFT JOIN kgroups g2 ON vg.group_id = g2.group_id
                WHERE vg.video_id IN ({format_strings})
            """, tuple(video_ids))
            for row in cursor.fetchall():
                vid = row['video_id']
                video_guest_map.setdefault(vid, {'members': [], 'groups': []})
                if row['member_name']:
                    if not row['guest_group'] or row['member_group'] == row['guest_group']:
                        video_guest_map[vid]['members'].append({'name': row['member_name'], 'group': row['member_group']})
                elif row['guest_group']:
                    if row['guest_group'] not in video_guest_map[vid]['groups']:
                        video_guest_map[vid]['groups'].append(row['guest_group'])

            # HOST QUERY
            cursor.execute(f"""
                SELECT vh.video_id, m.member_name, g1.group_name AS member_group, g2.group_name AS host_group
                FROM videohost vh
                LEFT JOIN members m ON vh.member_id = m.member_id
                LEFT JOIN member_groups mg ON m.member_id = mg.member_id
                LEFT JOIN kgroups g1 ON mg.group_id = g1.group_id
                LEFT JOIN kgroups g2 ON vh.group_id = g2.group_id
                WHERE vh.video_id IN ({format_strings})
            """, tuple(video_ids))
            for row in cursor.fetchall():
                vid = row['video_id']
                video_host_map.setdefault(vid, {'members': [], 'groups': []})
                if row['member_name']:
                    video_host_map[vid]['members'].append({'name': row['member_name'], 'group': row['member_group']})
                elif row['host_group']:
                    if row['host_group'] not in video_host_map[vid]['groups']:
                        video_host_map[vid]['groups'].append(row['host_group'])

            # LIVESTREAM TAGS QUERY
            cursor.execute(f"""
                SELECT vlt.video_id, lt.tag_name
                FROM videolivetags vlt
                JOIN livestreamtags lt ON vlt.tag_id = lt.tag_id
                WHERE vlt.video_id IN ({format_strings})
            """, params)
            for row in cursor.fetchall():
                video_tag_map.setdefault(row['video_id'], []).append(row['tag_name'])

            # MC QUERY FOR MUSIC SHOWS --- Updated to include Group Names
            cursor.execute(f"""
                SELECT 
                    vmc.video_id, 
                    ms.mc_pairname, 
                    m.member_name,
                    g.group_name
                FROM videomushowmc vmc
                JOIN musicshowmc ms ON vmc.mc_id = ms.mc_id
                JOIN members m ON vmc.member_id = m.member_id
                LEFT JOIN kgroups g ON vmc.group_id = g.group_id
                WHERE vmc.video_id IN ({format_strings})
            """, params)
            
            video_mc_map = {}
            for row in cursor.fetchall():
                vid = row['video_id']
                if vid not in video_mc_map:
                    video_mc_map[vid] = {'pairing': row['mc_pairname'], 'names': []}
    
                # Check for duplicates in case a member is in 5 groups 
                # but we only want the one relevant to this MC spot
                mc_entry = {'name': row['member_name'], 'group': row['group_name']}
                if mc_entry not in video_mc_map[vid]['names']:
                    video_mc_map[vid]['names'].append(mc_entry)


        # 6. OWNERSHIP MAPPING
        group_ownership = False
        host_map = set()
        guest_map = set()
        tiny_map = set()
        mc_map = set()

        # PHASE 1: Build the ID list based on Scope
        target_group_ids = []

        if group_id is not None:
            try:
                gid = int(group_id)

                if gid: # This prevents 0 or None from being added
                    target_group_ids.append(gid)
                
                # If scope is 'full', find all "siblings" and "parents"
                if scope == 'full':
                    # 1. Get the parent_id of the current group
                    cursor.execute("SELECT parent_id FROM kgroups WHERE group_id = %s", (gid,))
                    res = cursor.fetchone()
                    brandparent_id = res['parent_id'] if res and res['parent_id'] else gid
                    
                    # 2. Get all groups that share that parent (including the parent itself)
                    cursor.execute("""
                        SELECT group_id FROM kgroups 
                        WHERE group_id = %s OR parent_id = %s
                    """, (brandparent_id, brandparent_id))
                    
                    rows = cursor.fetchall()
                    target_group_ids = [int(row['group_id']) for row in rows if row['group_id'] is not None]
            
            except(ValueError, TypeError):
                target_group_ids = []

        # PHASE 2: THE MAPS
        # Now use 'target_group_ids' for your SQL queries instead of just one ID
        if target_group_ids and len(target_group_ids) > 0:
            clean_vids = [int(v) for v in video_ids]
            #v_place = ','.join(['%s'] * len(clean_vids))
            g_place = ','.join(['%s'] * len(target_group_ids))

            # Use a flat tuple for parameters
            own_params = tuple([show_id] + target_group_ids)
        
            # Check if this group "owns" the entire show
            cursor.execute(f"""
                SELECT 1 FROM showownership
                WHERE title_id = %s AND group_id IN ({g_place})
                LIMIT 1
            """, own_params)
            group_ownership = cursor.fetchone() is not None

            # ONLY run video mapping queries if there are actually videos present
            if clean_vids:
                v_place = ','.join(['%s'] * len(clean_vids))
                mapping_params = tuple(clean_vids) + tuple(target_group_ids)

                # HOST
                cursor.execute(f"SELECT video_id FROM videohost WHERE video_id IN ({v_place}) AND group_id IN ({g_place})", mapping_params)
                host_map = {int(row['video_id']) for row in cursor.fetchall()}
                    
                # GUEST
                cursor.execute(f"SELECT video_id FROM videoguest WHERE video_id IN ({v_place}) AND group_id IN ({g_place})", mapping_params)
                guest_map = {int(row['video_id']) for row in cursor.fetchall()}    

                # TINY
                cursor.execute(f"SELECT video_id FROM tinyguest WHERE video_id IN ({v_place}) AND group_id IN ({g_place})", mapping_params)
                tiny_map = {int(row['video_id']) for row in cursor.fetchall()}    
                    
                # MC
                cursor.execute(f"SELECT DISTINCT video_id FROM videomushowmc WHERE video_id IN ({v_place}) AND group_id IN ({g_place})", mapping_params)
                mc_map = {int(row['video_id']) for row in cursor.fetchall()}

        

        def is_group_related(video):
            # CRITICAL: Force video_id to int for the set check
            try:
                vid = int(video['video_id'])
            except:
                return False

            # If no group selected → no highlight
            if not target_group_ids:
                return False
            
            # Priority 1: MC always highlights
            if vid in mc_map:
                return True
            
            # NEW Check: Specific Show IDs - ONLY if scope is NOT 'full'
            if scope != 'full' and show_id in [44, 105, 108, 115, 122]:
                return vid in host_map or vid in guest_map or vid in tiny_map
            
            # Priority 2: If group owns the show, only highlight Guest/Tiny appearances
            if group_ownership:
                # If it's a tv series (Category 1), check for Hosts too
                if any(cat in show.get('category_ids', []) for cat in (1, 5)):
                    return vid in host_map or vid in guest_map or vid in tiny_map
                # Otherwise, stick to standard ownership rules (Guests/Tiny)
                return vid in guest_map or vid in tiny_map
            
            # If group does NOT own the show, highlight all tagged appearance
            if video.get('is_variety') == 1:
                return (
                    vid in host_map or
                    vid in guest_map or
                    vid in tiny_map
                )
            
            return False


        # 7. FINAL DISPLAY PROCESSING
        show_variety = show.get('variety', 0)

        for v in all_videos:
            vid = v['video_id']
            # Attach Livestream Tags
            v['livestream_tags'] = video_tag_map.get(vid, [])
            
            # Attach MC Data
            mc_info = video_mc_map.get(vid)
            if mc_info:
                v['mc_pairing'] = mc_info['pairing']
                v['mc_names'] = mc_info['names']

            # Guests
            v_g_data = video_guest_map.get(v['video_id'], {'members': [], 'groups': []})
            g_group_map = {}
            for m in v_g_data['members']:
                g_group_map.setdefault(m['group'], []).append(m['name'])
            
            g_parts = []
            for g_name in sorted(g_group_map):
                m_names = g_group_map[g_name]
                g_parts.append(f"{g_name} ({', '.join(m_names)})" if len(m_names) > 1 else f"{g_name} {m_names[0]}")
            g_parts.extend(v_g_data['groups'])
            v['guest_display'] = ' • '.join(g_parts)

            # Hosts
            v_h_data = video_host_map.get(v['video_id'], {'members': [], 'groups': []})
            h_group_map = {}
            for m in v_h_data['members']:
                h_group_map.setdefault(m['group'], []).append(m['name'])
            
            h_parts = []
            if show_variety == 0:
                unique_members = []
                seen_members = set()
                for g_name in sorted(h_group_map):
                    for name in h_group_map[g_name]:
                        if name not in seen_members:
                            unique_members.append(name)
                            seen_members.add(name)
                if unique_members:
                    h_parts.append(' • '.join(unique_members))
            else:
                for h_name in sorted(h_group_map):
                    m_names = h_group_map[h_name]
                    h_parts.append(f"{h_name} ({', '.join(m_names)})" if len(m_names) > 1 else f"{h_name} {m_names[0]}")
            h_parts.extend(v_h_data['groups'])
            v['host_display'] = ' • '.join(h_parts)

            # Ownership Highlight
            v['is_group_context'] = is_group_related(v)

        return {
            "show": show,
            "videos": all_videos,
            "extras": []
        }

    finally:
        db.close()
