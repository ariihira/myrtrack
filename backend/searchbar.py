from db_connect import connection
import os, json, re


# Core Configuration Rule: Handle portfolio execution flags safely
IS_PORTFOLIO = os.environ.get("PORTFOLIO_MODE", "False").strip().title() == "True"


def highlight_title(title, search_term):
    """
    Finds and wraps the search term in <b> tags within the title, ignoring case.
    """
    if not search_term or not title:
        return title
    
    search_regex = re.escape(search_term)
    pattern = re.compile(f'({search_regex})', re.IGNORECASE)
    return pattern.sub(r'<b>\1</b>', title)


def _get_portfolio_search(query):
    """
    In-memory substring snapshot search. Scans frozen tables safely 
    without triggering relational database execution faults.
    """

    empty_results = {'shows': [], 'videos': []}
    
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            snapshot = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return empty_results

    # Extract tables
    shows = snapshot.get('showtitle', snapshot.get('shows', []))
    videos = snapshot.get('videos', [])
    
    query_clean = query.lower()

    # Substring lookup matching across primary keys
    matching_shows = [
        s for s in shows 
        if query_clean in str(s.get('title', '')).lower() 
        or query_clean in str(s.get('synopsis', '')).lower()
    ]
    
    matching_videos = [
        v for v in videos 
        if query_clean in str(v.get('video_name', '')).lower()
    ]

    return {
        'shows': matching_shows,
        'videos': matching_videos
    }


def global_search(search_term):
    db, cursor = connection()

    """
    Searches for Show Titles and Videos based on text matches or 
    relational connections (ownership, hosts, guests, MCs).
    """

    if IS_PORTFOLIO:
        return _get_portfolio_search(search_term)
    
    if not search_term:
        return {"shows": [], "videos": []}
        
    like_term = f"%{search_term}%"
    
    # --- QUERY 1: SHOW TITLES (Matches title, owning group, or owning member) ---
    show_query = """
        SELECT DISTINCT
            st.title_id,
            st.title,
            st.title_img,
            st.webstatus
        FROM showtitle st
        LEFT JOIN showownership so ON st.title_id = so.title_id
        LEFT JOIN kgroups g ON so.group_id = g.group_id
        LEFT JOIN members m ON so.member_id = m.member_id
        WHERE st.webstatus = 'show'
          AND (
               st.title LIKE %s
               OR g.group_name LIKE %s
               OR m.member_name LIKE %s
          )
        ORDER BY st.title ASC;
    """
    
    # --- QUERY 2: VIDEOS (Matches title, hosts, guests, tinyguests, or music show MCs) ---
    video_query = """
        SELECT 
            v.video_id,
            v.releaseDate AS eventDate,
            IFNULL(v.season, '') AS season,
            IFNULL(v.episodeNumber, '') AS episodeNumber,
            v.video_title AS title,
            v.title_extras AS ext,
            v.is_variety AS var,
            IFNULL(v.video_notes, '') AS notes,
            v.webstatus,

            GROUP_CONCAT(DISTINCT s.title ORDER BY s.title SEPARATOR ', ') AS show_titles,
            GROUP_CONCAT(DISTINCT sc.category_id) AS category_ids,
            
            EXISTS (SELECT 1 FROM videohost vh WHERE vh.video_id = v.video_id) AS is_host,
            (SELECT g2.group_name FROM videohost vh2 
             JOIN kgroups g2 ON vh2.group_id = g2.group_id 
             WHERE vh2.video_id = v.video_id LIMIT 1) AS host_group_name,

            EXISTS (SELECT 1 FROM videomushowmc vmc WHERE vmc.video_id = v.video_id) AS has_mc,
            (SELECT GROUP_CONCAT(DISTINCT g3.group_name SEPARATOR ', ') 
             FROM videomushowmc vmc2 
             JOIN kgroups g3 ON vmc2.group_id = g3.group_id 
             WHERE vmc2.video_id = v.video_id) AS mc_group_names,

            IFNULL(GROUP_CONCAT(DISTINCT g.group_name ORDER BY g.group_name SEPARATOR ', '), '') AS owning_groups

        FROM video v
        LEFT JOIN video_showtitle vs ON v.video_id = vs.video_id
        LEFT JOIN showtitle s ON vs.title_id = s.title_id
        LEFT JOIN showtitle_category sc ON s.title_id = sc.title_id
        LEFT JOIN showownership so ON s.title_id = so.title_id
        LEFT JOIN kgroups g ON so.group_id = g.group_id
        
        LEFT JOIN videohost vh ON v.video_id = vh.video_id
        LEFT JOIN kgroups hg ON vh.group_id = hg.group_id
        LEFT JOIN members hm ON vh.member_id = hm.member_id
        LEFT JOIN videoguest vg ON v.video_id = vg.video_id
        LEFT JOIN kgroups gg ON vg.group_id = gg.group_id
        LEFT JOIN members gm ON vg.member_id = gm.member_id
        LEFT JOIN tinyguest tg ON v.video_id = tg.video_id
        LEFT JOIN kgroups tgg ON tg.group_id = tgg.group_id
        LEFT JOIN members tgm ON tg.member_id = tgm.member_id
        LEFT JOIN videomushowmc vmc ON v.video_id = vmc.video_id
        LEFT JOIN kgroups mcg ON vmc.group_id = mcg.group_id
        LEFT JOIN members mcm ON vmc.member_id = mcm.member_id
        
        WHERE v.releaseDate IS NOT NULL 
          AND v.webstatus = 'show'
          AND (
               v.video_title LIKE %s
               OR hg.group_name LIKE %s OR hm.member_name LIKE %s
               OR gg.group_name LIKE %s OR gm.member_name LIKE %s
               OR tgg.group_name LIKE %s OR tgm.member_name LIKE %s
               OR mcg.group_name LIKE %s OR mcm.member_name LIKE %s
          )
        GROUP BY v.video_id
        ORDER BY v.releaseDate DESC, v.video_id DESC;
    """

    try:
        # 1. Fetch Shows
        cursor.execute(show_query, (like_term, like_term, like_term))
        shows = cursor.fetchall()
        
        # 2. Fetch Videos
        cursor.execute(video_query, (
            like_term, 
            like_term, like_term, 
            like_term, like_term, 
            like_term, like_term, 
            like_term, like_term
        ))
        videos = cursor.fetchall()
        
        # --- TIMELINE COMPATIBILITY: FETCH GUEST GROUPS & MEMBERS ---
        categories_to_clear_owner = [1, 7, 9]

        for video in videos:
            # 1. Clean 'season' field (Non-numeric check)
            season_value = video['season']
            if season_value and not season_value.strip().isdigit():
                video['season'] = ''
                
            # 2. Clear 'owning_groups' if categories 1, 7, or 9 are present
            category_ids_str = video.pop('category_ids') 
            if category_ids_str:
                fetched_categories = set(int(cid) for cid in category_ids_str.split(',') if cid.isdigit())
                if fetched_categories.intersection(categories_to_clear_owner):
                    video['owning_groups'] = ''        

        # Step 2: Fetch all guests for these videos
        video_ids = [v['video_id'] for v in videos]
        video_guest_map = {}
        if video_ids:
            format_strings = ','.join(['%s'] * len(video_ids))
            cursor.execute(f"""
                SELECT vg.video_id, m.member_name, g1.group_name AS member_group, g2.group_name AS guest_group
                FROM videoguest vg
                LEFT JOIN members m ON vg.member_id = m.member_id
                LEFT JOIN member_groups mg ON m.member_id = mg.member_id
                LEFT JOIN kgroups g1 ON mg.group_id = g1.group_id
                LEFT JOIN kgroups g2 ON vg.group_id = g2.group_id
                WHERE vg.video_id IN ({format_strings})
            """, tuple(video_ids))
            guest_rows = cursor.fetchall()

            # Attach guests to videos
            for row in guest_rows:
                vid = row['video_id']
                if vid not in video_guest_map:
                    video_guest_map[vid] = {'members': [], 'groups': []}

                guest_group = row['guest_group']

                if row['member_name']:
                    if not guest_group or row['member_group'] == guest_group:
                        video_guest_map[vid]['members'].append({
                            'name': row['member_name'],
                            'group': row['member_group']
                        })
                elif guest_group:
                    if guest_group not in video_guest_map[vid]['groups']:
                        video_guest_map[vid]['groups'].append(guest_group)

            # Build guest display string and attach to video dicts
            for v in videos:
                v_g_data = video_guest_map.get(v['video_id'], {'members': [], 'groups': []})
        
                g_group_map = {}
                for m in v_g_data['members']:
                    g_group_map.setdefault(m['group'], []).append(m['name'])
        
                g_parts = []
        
                for g_name in sorted(g_group_map):
                    m_names = g_group_map[g_name]
                    if len(m_names) > 1:
                        g_parts.append(f"{g_name} ({', '.join(m_names)})")
                    else:
                        g_parts.append(f"{g_name} {m_names[0]}")
        
                g_parts.extend(v_g_data['groups'])
                v['guest_display'] = ' • '.join(g_parts)

        # --- EXACT PRIORITY LOGIC ---
        for v in videos:
            # 1. HOST PRIORITY (Rules 1, 2, 3)
            if v.get('is_host'):
                v['display_group'] = v.get('host_group_name') or v.get('owning_groups', '').split(',')[0]

            # 2. MC PRIORITY (Rule 5)
            elif v.get('has_mc'):
                v['display_group'] = v.get('mc_group_names') or v.get('owning_groups')

            # 3. GUEST PRIORITY (Rule 4)
            elif v.get('guest_display'):
                unique_groups = set()
                v_g_data = video_guest_map.get(v['video_id'], {'members': [], 'groups': []})

                known_groups = set(v_g_data['groups'])
                for m in v_g_data['members']:
                    known_groups.add(m['group'])

                segments = v['guest_display'].split(' • ')
        
                for segment in segments:
                    segment = segment.strip()

                    if segment in known_groups:
                        unique_groups.add(segment)
                        continue

                    if "(" in segment:
                        group_name = segment.split('(')[0].strip()
                        unique_groups.add(group_name)
                
                    elif " " in segment:
                        found_known = False
                        for group in known_groups:
                            if segment.startswith(group):
                                unique_groups.add(group)
                                found_known = True
                                break

                        if not found_known:
                            parts = segment.rsplit(' ', 1)
                            unique_groups.add(parts[0].strip())
                
                    else:
                        unique_groups.add(segment)

                v['display_group'] = ', '.join(sorted(list(unique_groups)))

            # 4. OWNER FALLBACK (Rule 6)
            else:
                v['display_group'] = v.get('owning_groups')

        # --- HIGHLIGHTING & POST PROCESSING ---
        for s in shows:
            s['title'] = highlight_title(s['title'], search_term)

        for v in videos:
            v['title'] = highlight_title(v['title'], search_term)
            if v['show_titles']:
                names = v['show_titles'].split(', ')
                v['show_titles'] = ', '.join([highlight_title(name, search_term) for name in names])

        return {"shows": shows, "videos": videos}
        
    except Exception as e:
        print(f"Database error during search service processing: {e}")
        return {"shows": [], "videos": []}

    finally:
        db.close()