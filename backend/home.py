import os, json
from db_connect import connection
from collections import Counter


# Core Configuration Rule: Safe evaluation of system environment flags
IS_PORTFOLIO = os.environ.get("PORTFOLIO_MODE", "False").strip().title() == "True"


def _get_portfolio_home():
    """
    Computes home metrics, active counters, and leaderboard statistics dynamically
    by scanning the raw snapshot arrays dumped from freeze_db.py.
    Deduplicates item relationships exactly like SQL's COUNT(DISTINCT) behavior.
    """
    import json
    from collections import defaultdict

    empty_payload = {
        'records': {
            'group_most_videos': {'label': 'None', 'count': 0},
            'group_most_owned': {'label': 'None', 'count': 0},
            'group_most_mc': {'label': 'None', 'count': 0},
            'group_most_live': {'label': 'None', 'count': 0},
            'member_most_guest': {'label': 'None', 'count': 0},
            'member_most_videos': {'label': 'None', 'count': 0},
            'member_most_live': {'label': 'None', 'count': 0},
            'most_stamped_song': {'label': 'None', 'count': 0}
        },
        'counts': {'bg': 0, 'gg': 0, 'band': 0, 'coed': 0, 'solo': 0},
        'total_members': 0,
        'total_videos': 0,
        'category_stats': []
    }

    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            snapshot = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return empty_payload

    # Extract clean base catalogs
    categories = snapshot.get('category', [])
    kgroups = snapshot.get('kgroups', [])
    members = snapshot.get('members', [])
    showtitle = snapshot.get('showtitle', [])
    videos = snapshot.get('video', [])
    
    # Cast all reference data key mappings to safe uniform integers
    group_lookup = {int(g['group_id']): g['group_name'] for g in kgroups if g.get('group_id') is not None}
    member_lookup = {int(m['member_id']): m['member_name'] for m in members if m.get('member_id') is not None}

    # Extract raw junction collections
    video_showtitle = snapshot.get('video_showtitle', [])
    showtitle_category = snapshot.get('showtitle_category', [])
    showownership = snapshot.get('showownership', [])
    videohost = snapshot.get('videohost', [])
    videoguest = snapshot.get('videoguest', [])
    tinyguest = snapshot.get('tinyguest', [])
    videomushowmc = snapshot.get('videomushowmc', [])
    video_music_recs = snapshot.get('video_music_recs', [])

    # Map categories to show IDs for lookups
    show_cats = defaultdict(set)
    for sc in showtitle_category:
        if sc.get('title_id') is not None and sc.get('category_id') is not None:
            show_cats[int(sc['title_id'])].add(int(sc['category_id']))

    # Map videos to show IDs
    show_to_vids = defaultdict(set)
    for vs in video_showtitle:
        if vs.get('title_id') is not None and vs.get('video_id') is not None:
            show_to_vids[int(vs['title_id'])].add(int(vs['video_id']))

    # Emulate the shared live presence filter state
    active_g_ids = set()
    for vh in videohost:
        if vh.get('group_id') is not None: active_g_ids.add(int(vh['group_id']))
    for vg in videoguest:
        if vg.get('group_id') is not None: active_g_ids.add(int(vg['group_id']))
    for tg in tinyguest:
        if tg.get('group_id') is not None: active_g_ids.add(int(tg['group_id']))
    for so in showownership:
        if so.get('group_id') is not None:
            t_id = int(so['title_id'])
            show_obj = next((s for s in showtitle if int(s['title_id']) == t_id), None)
            if show_obj and show_obj.get('variety') == 0 and show_obj.get('webstatus') == 'show':
                active_g_ids.add(int(so['group_id']))

    # 1. Record Tracker: Group with the most related videos (Deduplicated via Sets)
    g_vids_distinct = defaultdict(set)
    cat_7_shows = {int(sc['title_id']) for sc in showtitle_category if int(sc['category_id']) == 7}
    
    for so in showownership:
        if so.get('group_id') is not None and int(so['title_id']) not in cat_7_shows:
            for v_id in show_to_vids[int(so['title_id'])]:
                g_vids_distinct[int(so['group_id'])].add(v_id)
                
    for vh in videohost:
        if vh.get('group_id') is not None: g_vids_distinct[int(vh['group_id'])].add(int(vh['video_id']))
    for vg in videoguest:
        if vg.get('group_id') is not None: g_vids_distinct[int(vg['group_id'])].add(int(vg['video_id']))
    for vm in videomushowmc:
        if vm.get('group_id') is not None: g_vids_distinct[int(vm['group_id'])].add(int(vm['video_id']))

    top_g_vid_id, top_g_vid_count = None, 0
    for g_id, v_set in g_vids_distinct.items():
        if len(v_set) > top_g_vid_count or (len(v_set) == top_g_vid_count and top_g_vid_id and group_lookup.get(g_id, '') < group_lookup.get(top_g_vid_id, '')):
            top_g_vid_count = len(v_set)
            top_g_vid_id = g_id

    # 2. Record Tracker: Group with the most showtitles owned
    g_owned_distinct = defaultdict(set)
    allowed_owned_cats = {2, 3, 4, 5, 6, 8, 11, 12, 13, 14, 15}
    for so in showownership:
        if so.get('group_id') is not None:
            t_id = int(so['title_id'])
            if show_cats[t_id].intersection(allowed_owned_cats):
                g_owned_distinct[int(so['group_id'])].add(t_id)
                
    top_g_owned_id, top_g_owned_count = None, 0
    for g_id, t_set in g_owned_distinct.items():
        if len(t_set) > top_g_owned_count or (len(t_set) == top_g_owned_count and top_g_owned_id and group_lookup.get(g_id, '') < group_lookup.get(top_g_owned_id, '')):
            top_g_owned_count = len(t_set)
            top_g_owned_id = g_id

    # 3. Record Tracker: Group with the most MC videos
    g_mc_distinct = defaultdict(set)
    for vm in videomushowmc:
        if vm.get('group_id') is not None: g_mc_distinct[int(vm['group_id'])].add(int(vm['video_id']))
        
    top_g_mc_id, top_g_mc_count = None, 0
    for g_id, v_set in g_mc_distinct.items():
        if len(v_set) > top_g_mc_count or (len(v_set) == top_g_mc_count and top_g_mc_id and group_lookup.get(g_id, '') < group_lookup.get(top_g_mc_id, '')):
            top_g_mc_count = len(v_set)
            top_g_mc_id = g_id

    # 4. Record Tracker: Group with the most livestream videos (Category 12)
    g_live_distinct = defaultdict(set)
    for so in showownership:
        if so.get('group_id') is not None and 12 in show_cats[int(so['title_id'])]:
            for v_id in show_to_vids[int(so['title_id'])]:
                g_live_distinct[int(so['group_id'])].add(v_id)
                
    top_g_live_id, top_g_live_count = None, 0
    for g_id, v_set in g_live_distinct.items():
        if len(v_set) > top_g_live_count or (len(v_set) == top_g_live_count and top_g_live_id and group_lookup.get(g_id, '') < group_lookup.get(top_g_live_id, '')):
            top_g_live_count = len(v_set)
            top_g_live_id = g_id

    # 5. Record Tracker: Member with the most guest appearances
    m_guest_distinct = defaultdict(set)
    for vg in videoguest:
        if vg.get('member_id') is not None: m_guest_distinct[int(vg['member_id'])].add(int(vg['video_id']))
        
    top_m_guest_id, top_m_guest_count = None, 0
    for m_id, v_set in m_guest_distinct.items():
        # Clean count logic aligns with live database row outputs
        if len(v_set) > top_m_guest_count or (len(v_set) == top_m_guest_count and top_m_guest_id and member_lookup.get(m_id, '') < member_lookup.get(top_m_guest_id, '')):
            top_m_guest_count = len(v_set)
            top_m_guest_id = m_id

    # 6. Record Tracker: Member with the most related videos
    m_vids_distinct = defaultdict(set)
    for so in showownership:
        if so.get('member_id') is not None and int(so['title_id']) not in cat_7_shows:
            for v_id in show_to_vids[int(so['title_id'])]:
                m_vids_distinct[int(so['member_id'])].add(v_id)
                
    for vh in videohost:
        if vh.get('member_id') is not None: m_vids_distinct[int(vh['member_id'])].add(int(vh['video_id']))
    for vg in videoguest:
        if vg.get('member_id') is not None: m_vids_distinct[int(vg['member_id'])].add(int(vg['video_id']))
    for vm in videomushowmc:
        if vm.get('member_id') is not None: m_vids_distinct[int(vm['member_id'])].add(int(vm['video_id']))

    top_m_vid_id, top_m_vid_count = None, 0
    for m_id, v_set in m_vids_distinct.items():
        if len(v_set) > top_m_vid_count or (len(v_set) == top_m_vid_count and top_m_vid_id and member_lookup.get(m_id, '') < member_lookup.get(top_m_vid_id, '')):
            top_m_vid_count = len(v_set)
            top_m_vid_id = m_id

    # 7. Record Tracker: Member with the most livestream videos
    m_live_distinct = defaultdict(set)
    for so in showownership:
        if so.get('member_id') is not None and 12 in show_cats[int(so['title_id'])]:
            for v_id in show_to_vids[int(so['title_id'])]:
                m_live_distinct[int(so['member_id'])].add(v_id)
                
    top_m_live_id, top_m_live_count = None, 0
    for m_id, v_set in m_live_distinct.items():
        if len(v_set) > top_m_live_count or (len(v_set) == top_m_live_count and top_m_live_id and member_lookup.get(m_id, '') < member_lookup.get(top_m_live_id, '')):
            top_m_live_count = len(v_set)
            top_m_live_id = m_id

    # 8. Record Tracker: Song most mentioned
    song_distinct = defaultdict(set)
    for vmr in video_music_recs:
        if vmr.get('song_id') is not None: song_distinct[int(vmr['song_id'])].add(int(vmr['video_id']))
        
    top_song_id, top_song_count = None, 0
    for s_id, v_set in song_distinct.items():
        if len(v_set) > top_song_count or (len(v_set) == top_song_count and top_song_id and str(s_id) < str(top_song_id)):
            top_song_count = len(v_set)
            top_song_id = s_id
            
    song_label = 'None'
    if top_song_id:
        s_obj = next((s for s in snapshot.get('songs', []) if int(s['song_id']) == top_song_id), None)
        if s_obj: song_label = f"{s_obj['songtitle']} by {s_obj['artist']}"

    # Build final standardized response layout payload
    records = {
        'group_most_videos': {'label': group_lookup.get(top_g_vid_id, 'None'), 'count': top_g_vid_count},
        'group_most_owned': {'label': group_lookup.get(top_g_owned_id, 'None'), 'count': top_g_owned_count},
        'group_most_mc': {'label': group_lookup.get(top_g_mc_id, 'None'), 'count': top_g_mc_count},
        'group_most_live': {'label': group_lookup.get(top_g_live_id, 'None'), 'count': top_g_live_count},
        'member_most_guest': {'label': member_lookup.get(top_m_guest_id, 'None'), 'count': top_m_guest_count},
        'member_most_videos': {'label': member_lookup.get(top_m_vid_id, 'None'), 'count': top_m_vid_count},
        'member_most_live': {'label': member_lookup.get(top_m_live_id, 'None'), 'count': top_m_live_count},
        'most_stamped_song': {'label': song_label, 'count': top_song_count}
    }

    # Group counts summaries definitions
    type_counts = defaultdict(int)
    for g in kgroups:
        if g.get('parent_id') is None and int(g['group_id']) in active_g_ids:
            type_counts[g['grouptype']] += 1
            
    total_active_members = len({int(m['member_id']) for m in snapshot.get('mc_members_list', []) if int(m['group_id']) in active_g_ids})
    actual_videos = sum(1 for v in videos if v.get('title_extras') is None and v.get('webstatus') == 'show')
    special_shows = len({int(sc['title_id']) for sc in showtitle_category if int(sc['category_id']) in (13, 14, 15, 18, 21)})
    
    cat_counts = defaultdict(int)
    for sc in showtitle_category:
        t_id = int(sc['title_id'])
        show_obj = next((s for s in showtitle if int(s['title_id']) == t_id), None)
        if show_obj and show_obj.get('webstatus') == 'show':
            cat_counts[int(sc['category_id'])] += 1
            
    category_stats = []
    for c in categories:
        category_stats.append({
            'category_id': int(c['category_id']),
            'category_name': c['category_name'],
            'show_count': cat_counts[int(c['category_id'])]
        })
    category_stats.sort(key=lambda x: x['category_id'], reverse=False)

    return {
        'records': records,
        'counts': type_counts,
        'total_members': total_active_members,
        'total_videos': actual_videos + special_shows,
        'category_stats': category_stats
    }



def get_home():
    """
    Fetches processed statistical matrices and bento leaderboards.
    Intelligently branches execution environments without altering core route definitions.
    """
    if IS_PORTFOLIO:
        return _get_portfolio_home()

    db, cursor = connection()
    
    #1. Records
    records = {}

    # Record 1: Group with the most related videos (Ownership without host [excl. cat 7], host/guest, or MC videos)
    cursor.execute("""
        SELECT group_name, COUNT(DISTINCT video_id) AS total_count
        FROM (
            SELECT g.group_name, v_st.video_id 
            FROM kgroups g
            JOIN showownership sho ON g.group_id = sho.group_id
            JOIN video_showtitle v_st ON sho.title_id = v_st.title_id
            WHERE sho.title_id NOT IN (
                SELECT title_id FROM showtitle_category WHERE category_id = 7
            )
            UNION ALL
            SELECT g.group_name, vh.video_id 
            FROM kgroups g
            JOIN videohost vh ON g.group_id = vh.group_id
            UNION ALL
            SELECT g.group_name, vg.video_id 
            FROM kgroups g
            JOIN videoguest vg ON g.group_id = vg.group_id
            UNION ALL
            SELECT g.group_name, vmc.video_id
            FROM kgroups g
            JOIN videomushowmc vmc ON g.group_id = vmc.group_id
        ) AS combined_group_videos
        GROUP BY group_name
        ORDER BY total_count DESC, group_name ASC
        LIMIT 1
    """)
    res = cursor.fetchone()
    records['group_most_videos'] = {'label': res['group_name'] if res else 'None', 'count': res['total_count'] if res else 0}

    # Record 2: Group with the most showtitles owned (categories 2, 3, 4, 5, 6, 8, 11, 12, 13, 14, 15)
    cursor.execute("""
        SELECT g.group_name, COUNT(DISTINCT sho.title_id) AS total_count
        FROM kgroups g
        JOIN showownership sho ON g.group_id = sho.group_id
        JOIN showtitle_category sc ON sho.title_id = sc.title_id
        WHERE sc.category_id IN (2, 3, 4, 5, 6, 8, 11, 12, 13, 14, 15)
        GROUP BY g.group_id
        ORDER BY total_count DESC, g.group_name ASC
        LIMIT 1
    """)
    res = cursor.fetchone()
    records['group_most_owned'] = {'label': res['group_name'] if res else 'None', 'count': res['total_count'] if res else 0}

    # Record 3: Group with the most MC videos (counting member associations in videomushowmc)
    cursor.execute("""
        SELECT g.group_name, COUNT(DISTINCT vmc.video_id) AS total_count
        FROM videomushowmc vmc
        JOIN kgroups g ON vmc.group_id = g.group_id
        GROUP BY g.group_id
        ORDER BY total_count DESC, g.group_name ASC
        LIMIT 1
    """)
    res = cursor.fetchone()
    records['group_most_mc'] = {'label': res['group_name'] if res else 'None', 'count': res['total_count'] if res else 0}

    # Record 4: Group with the most livestream videos (category_id = 12)
    cursor.execute("""
        SELECT g.group_name, COUNT(DISTINCT v_st.video_id) AS total_count
        FROM kgroups g
        JOIN showownership sho ON g.group_id = sho.group_id
        JOIN showtitle_category sc ON sho.title_id = sc.title_id
        JOIN video_showtitle v_st ON sho.title_id = v_st.title_id
        WHERE sc.category_id = 12
        GROUP BY g.group_id
        ORDER BY total_count DESC, g.group_name ASC
        LIMIT 1
    """)
    res = cursor.fetchone()
    records['group_most_live'] = {'label': res['group_name'] if res else 'None', 'count': res['total_count'] if res else 0}

    # Record 5: Member with the most non-fullgroup guest appearances
    cursor.execute("""
        SELECT m.member_name, COUNT(vg.video_id) AS total_count
        FROM videoguest vg
        JOIN members m ON vg.member_id = m.member_id
        GROUP BY m.member_id
        ORDER BY total_count DESC, m.member_name ASC
        LIMIT 1
    """)
    res = cursor.fetchone()
    records['member_most_guest'] = {'label': res['member_name'] if res else 'None', 'count': res['total_count'] if res else 0}

    # Record 6: Member with the most related videos (Ownership without host [excl. cat 7], host/guest, or MC videos)
    cursor.execute("""
        SELECT member_name, COUNT(DISTINCT video_id) AS total_count
        FROM (
            SELECT m.member_name, v_st.video_id 
            FROM members m
            JOIN showownership sho ON m.member_id = sho.member_id
            JOIN video_showtitle v_st ON sho.title_id = v_st.title_id
            WHERE sho.title_id NOT IN (
                SELECT title_id FROM showtitle_category WHERE category_id = 7
            )
            UNION ALL
            SELECT m.member_name, vh.video_id 
            FROM members m
            JOIN videohost vh ON m.member_id = vh.member_id
            UNION ALL
            SELECT m.member_name, vg.video_id 
            FROM members m
            JOIN videoguest vg ON m.member_id = vg.member_id
            UNION ALL
            SELECT m.member_name, vmc.video_id
            FROM members m
            JOIN videomushowmc vmc ON m.member_id = vmc.member_id
        ) AS combined_member_videos
        GROUP BY member_name
        ORDER BY total_count DESC, member_name ASC
        LIMIT 1
    """)
    res = cursor.fetchone()
    records['member_most_videos'] = {'label': res['member_name'] if res else 'None', 'count': res['total_count'] if res else 0}

    # Record 7: Member with the most livestream videos (showownership and category_id = 12)
    cursor.execute("""
        SELECT m.member_name, COUNT(DISTINCT v_st.video_id) AS total_count
        FROM members m
        JOIN showownership sho ON m.member_id = sho.member_id
        JOIN showtitle_category sc ON sho.title_id = sc.title_id
        JOIN video_showtitle v_st ON sho.title_id = v_st.title_id
        WHERE sc.category_id = 12
        GROUP BY m.member_id
        ORDER BY total_count DESC, m.member_name ASC
        LIMIT 1
    """)
    res = cursor.fetchone()
    records['member_most_live'] = {'label': res['member_name'] if res else 'None', 'count': res['total_count'] if res else 0}

    # Record 8: Song title & Artist most mentioned across all video_music_recs
    cursor.execute("""
        SELECT s.songtitle, s.artist, COUNT(vmr.video_id) AS total_count
        FROM video_music_recs vmr
        JOIN songs s ON vmr.song_id = s.song_id
        GROUP BY s.song_id
        ORDER BY total_count DESC, s.songtitle ASC
        LIMIT 1
    """)
    res = cursor.fetchone()
    records['most_stamped_song'] = {
        'label': f'{res["songtitle"]} by {res["artist"]}' if res else 'None',
        'count': res['total_count'] if res else 0
    }


    # 2. Active Group Stats
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

    cursor.execute("""
        SELECT grouptype, COUNT(DISTINCT g.group_id) as active_group_count
        FROM kgroups g
        WHERE g.parent_id IS NULL AND """ + presence_filter + """
        GROUP BY grouptype
    """)
    # Logic to turn the SQL list into a dictionary for the HTML .get() calls
    type_counts = {row['grouptype']: row['active_group_count'] for row in cursor.fetchall()}

    # 3. Total Member Count for Active Groups Only
    cursor.execute("""
        SELECT COUNT(DISTINCT mg.member_id) as total_active_members
        FROM member_groups mg
        JOIN kgroups g ON mg.group_id = g.group_id
        WHERE """ + presence_filter)
    total_members = cursor.fetchone()['total_active_members']

    # 4. Total Video Count
    # Part A: Count videos that ARE NOT 'DVD'
    cursor.execute("SELECT COUNT(*) AS vid_count FROM video WHERE title_extras IS NULL AND webstatus = 'show'")
    actual_videos = cursor.fetchone()['vid_count']

    # Part B: Count unique shows in categories 13, 14, 15, 18, 21
    cursor.execute("""
        SELECT COUNT(DISTINCT title_id) AS cat_show_count 
        FROM showtitle_category 
        WHERE category_id IN (13, 14, 15, 18, 21)
    """)
    special_shows = cursor.fetchone()['cat_show_count']
    
    total_videos = actual_videos + special_shows

    # 5. Showtitles per Category
    cursor.execute("""
        SELECT c.category_name, COUNT(sc.title_id) as show_count
        FROM category c
        LEFT JOIN showtitle_category sc ON c.category_id = sc.category_id
        GROUP BY c.category_id
    """)
    category_stats = cursor.fetchall()
    
    db.close()

    return {
        'records': records,
        'counts': type_counts,
        'total_members': total_members,
        'total_videos': total_videos,
        'category_stats': category_stats
    }
    