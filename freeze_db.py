import json
import os
import sys

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
# Core Import Parity: Pointing directly to your active connection framework
from db_connect import connection

def freeze_entire_database():
    print("🥶 Initiating absolute Database Freeze Strategy...")
    os.environ['PORTFOLIO_MODE'] = 'False'
    
    try:
        # Correctly unpack the connection and operational cursor tuple bundle
        db, cursor = connection()
    except Exception as e:
        print(f"❌ Error: Could not establish connection via db_connect. Details: {str(e)}")
        return

    snapshot = {
        "category": [],
        "kgroups": [],
        "members": [],
        "showtitle": [],
        "video": [],
        "mc_members_list": [],
        "musicshowmc": [],
        "livestreamtags": [],
        "songs": [],
        "mc_pairings": [],
        "season_names": [],
        "member_groups": [],       
        "mc_members": [],          
        "mushow_mcs": [],          
        "video_showtitle": [],
        "showtitle_category": [],
        "showownership": [],
        "titleguest": [],  
        "videohost": [],
        "videoguest": [],
        "tinyguest": [],
        "videomushowmc": [],
        "videolivetags": [],
        "video_music_recs": []
    }

    try:
        print(" -> Packaging independent catalogs...")
        cursor.execute("SELECT category_id, category_name FROM category ORDER BY category_id ASC")
        snapshot["category"] = cursor.fetchall()

        cursor.execute("SELECT group_id, group_name, group_desc, grouptype, parent_id, debutdate FROM kgroups ORDER BY group_name ASC")
        snapshot["kgroups"] = cursor.fetchall()

        cursor.execute("""
            SELECT m.member_id, m.member_name, GROUP_CONCAT(g.group_name SEPARATOR ', ') AS `groups`
            FROM members m
            LEFT JOIN member_groups mg ON m.member_id = mg.member_id
            LEFT JOIN kgroups g ON mg.group_id = g.group_id
            GROUP BY m.member_id, m.member_name
            ORDER BY m.member_name ASC
        """)
        snapshot["members"] = cursor.fetchall()

        cursor.execute("SELECT title_id, title, releaseYear, totalSeasons, totalEpisodes, watchStatus, title_img, variety, sort_date, season_order, webstatus FROM showtitle ORDER BY title ASC")
        snapshot["showtitle"] = cursor.fetchall()

        cursor.execute("SELECT video_id, season, episodeNumber, video_title, releaseDate, title_extras, video_notes, is_variety, webstatus FROM video ORDER BY video_id ASC")
        snapshot["video"] = cursor.fetchall()

        cursor.execute("""
            SELECT m.member_id, m.member_name, g.group_name, g.group_id
            FROM members m
            JOIN member_groups mg ON m.member_id = mg.member_id
            JOIN kgroups g ON mg.group_id = g.group_id
            ORDER BY g.group_name, m.member_name
        """)
        snapshot["mc_members_list"] = cursor.fetchall()

        cursor.execute("SELECT mc_id, mc_pairname FROM musicshowmc ORDER BY mc_pairname ASC")
        snapshot["musicshowmc"] = cursor.fetchall()

        cursor.execute("SELECT tag_id, tag_name, member_id, group_id FROM livestreamtags ORDER BY tag_name ASC")
        snapshot["livestreamtags"] = cursor.fetchall()

        cursor.execute("SELECT song_id, songtitle, artist, album, track_number, spotify_link, youtube_link FROM songs ORDER BY artist ASC, album ASC, track_number ASC")
        snapshot["songs"] = cursor.fetchall()

        cursor.execute("""
            SELECT mc.mc_id, mc.mc_pairname, st.title, st.title_id,
                   GROUP_CONCAT(m.member_name SEPARATOR ', ') AS member_names,
                   GROUP_CONCAT(m.member_id SEPARATOR ',') AS member_ids
            FROM musicshowmc mc
            LEFT JOIN mushow_mcs mm ON mc.mc_id = mm.mc_id
            LEFT JOIN showtitle st ON mm.mushow_id = st.title_id
            LEFT JOIN mc_members mcm ON mc.mc_id = mcm.mc_id
            LEFT JOIN members m ON mcm.member_id = m.member_id
            GROUP BY mc.mc_id, mc.mc_pairname, st.title, st.title_id
            ORDER BY mc.mc_pairname ASC
        """)
        snapshot["mc_pairings"] = cursor.fetchall()

        cursor.execute("SELECT title_id, season_number, season_name FROM season_names")
        snapshot["season_names"] = cursor.fetchall()

        print(" -> Packaging core junction maps with target relational IDs...")
        
        cursor.execute("SELECT member_id, group_id FROM member_groups")
        snapshot["member_groups"] = cursor.fetchall()

        cursor.execute("SELECT mc_id, member_id FROM mc_members")
        snapshot["mc_members"] = cursor.fetchall()

        cursor.execute("SELECT mushow_id, mc_id FROM mushow_mcs")
        snapshot["mushow_mcs"] = cursor.fetchall()

        cursor.execute("SELECT video_id, title_id FROM video_showtitle")
        snapshot["video_showtitle"] = cursor.fetchall()

        cursor.execute("SELECT title_id, category_id FROM showtitle_category")
        snapshot["showtitle_category"] = cursor.fetchall()

        cursor.execute("SELECT title_id, group_id, member_id FROM showownership")
        snapshot["showownership"] = cursor.fetchall()

        cursor.execute("SELECT title_id, group_id FROM titleguest")
        snapshot["titleguest"] = cursor.fetchall()

        cursor.execute("SELECT host_id, video_id, group_id, member_id FROM videohost")
        snapshot["videohost"] = cursor.fetchall()

        cursor.execute("SELECT video_id, group_id, member_id FROM videoguest")
        snapshot["videoguest"] = cursor.fetchall()

        cursor.execute("SELECT video_id, group_id, member_id FROM tinyguest")
        snapshot["tinyguest"] = cursor.fetchall()

        cursor.execute("SELECT video_id, mc_id, member_id, group_id FROM videomushowmc")
        snapshot["videomushowmc"] = cursor.fetchall()

        cursor.execute("SELECT video_id, tag_id FROM videolivetags")
        snapshot["videolivetags"] = cursor.fetchall()

        cursor.execute("SELECT video_id, song_id, sort_order FROM video_music_recs")
        snapshot["video_music_recs"] = cursor.fetchall()

        output_dest = os.path.join(os.path.dirname(__file__), 'data.json')
        with open(output_dest, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, indent=4, default=str)

        print("\n" + "="*60)
        print("✅ DATABASE CONFIGURATION FROZEN SUCCESSFULLY WITH 100% SCHEMA PARITY!")
        print(f"📁 Destination Asset: {output_dest}")
        print("="*60 + "\n")

    except Exception as e:
        print(f"❌ Freeze Failed due to query mapping exception: {str(e)}")
    finally:
        # Safely shut down active connections pools
        cursor.close()
        db.close()

if __name__ == "__main__":
    freeze_entire_database()