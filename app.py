import os, json
from flask import Flask, render_template, request, redirect, url_for
from db_connect import connection

# core configuration rule
IS_PORTFOLIO = os.environ.get("PORTFOLIO_MODE", "False").strip().title() == "True"

# import the helper function
import backend.groups as allgroups 
import backend.home as home
import backend.archive as archive
import backend.showtitle as showtitle
import backend.collections as collections
import backend.searchbar as searchbar


def load_portfolio_data(key=None):
    """
    Helper to read data from the frozen data.json snapshot file during Portfolio Mode.
    """

    try:
        # assumes data.json lives in root workspace folder
        with open('data.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            raw_list = data.get(key, []) if key else data
            
            # If the rows come back as raw lists instead of dicts, map them to explicit dict profiles
            if raw_list and isinstance(raw_list, list) and isinstance(raw_list[0], list):
                if key == 'songs':
                    return [{'song_id': r[0], 'songtitle': r[1], 'artist': r[2], 'album': r[3]} for r in raw_list]
                if key == 'showtitle':
                    return [{'title_id': r[0], 'title': r[1], 'releaseYear': r[2]} for r in raw_list]
            return raw_list
    except Exception:
        return []
    

app = Flask(__name__)


# Make IS_PORTFOLIO flag universally available inside Jinja templates
@app.context_processor
def inject_environment_status():
    return dict(is_portfolio=IS_PORTFOLIO)


@app.route('/')
def dashboard():
    # Fetch all processed data from the helper function
    data = home.get_home()
    return render_template('home.html', **data)

@app.route('/search', methods=['GET'])
def search():
    """
    Listens for GET requests from the search input element form name parameter.
    """
    # Pulls search from input 'name="q"' inside your base html top bar layout
    query = request.args.get('q', '').strip() 
    
    if not query:
        return redirect(url_for('dashboard'))  # Redirect to your home view if blank
        
    # Call the detached search processing module 
    search_data = searchbar.global_search(query)
    
    # Return layout to the template engine along with highlighted dictionary keys
    return render_template('search.html', query=query, shows=search_data['shows'], 
        videos=search_data['videos'])

@app.route('/collection/<slug>')
def view_collection(slug):
    display_title = slug.replace('kdrama', 'K-Drama').replace('moviedvd', 'Movie/DVD').title()

    if IS_PORTFOLIO:
        criteria = collections.get_collection_criteria(slug)
        if not criteria:
            return "Collection not found", 404
        shows = collections._get_portfolio_collection_data(criteria)
    else:
        criteria = collections.get_collection_criteria(slug)
        if not criteria:
            return "Collection not found", 404

        db, cursor = connection()
        shows = collections.fetch_collection_data(cursor, criteria)
        db.close()
        
    return render_template('collections.html', sectioned_data=shows, title=display_title)

@app.route('/kpopgroups')
def show_all_groups():
    # Fetch the sorted list
    all_groups = allgroups.get_groups_directory()
    # Send it to the template
    return render_template('kpopgroups.html', groups=all_groups)


@app.route('/group/<int:id>')
def group_page(id):
    # 1. READ THE URL PARAMETER
    view_scope = request.args.get('view', 'main') 
    
    # 2. FETCH THE ARCHIVE CATEGORY (Dual-mode internally managed)
    archive_results = archive.get_archive(id, scope=view_scope)

    # 3. GET DYNAMIC COLUMN GLIMPSES
    active_subunits = []
    if view_scope == 'main':
        active_subunits = archive.get_top_active_subunits(id)

    # 4. RESOLVE THE METADATA HEADER NAME
    if IS_PORTFOLIO:
        all_groups = load_portfolio_data('kgroups')
        group_info = next((g for g in all_groups if int(g.get('group_id', 0)) == id), None)
        group_name = group_info['group_name'] if group_info else "Archive"
    else:
        db, cursor = connection()
        cursor.execute("SELECT group_name FROM kgroups WHERE group_id = %s", (id,))
        group_info = cursor.fetchone()
        db.close()
        group_name = group_info['group_name'] if group_info else "Archive"
        
    # 5. RENDER THE MACRO TEMPLATE
    return render_template(
        'archive.html',
        target_id=id, 
        group=group_name,
        scope=view_scope,
        previews=active_subunits,
        **archive_results
    )

@app.route('/show/<int:show_id>')
def show_detail(show_id):
    # Call the logic
    group_id = request.args.get('group_id', type=int)
    scope = request.args.get('scope', 'main')
    data = showtitle.get_show_details(show_id, group_id=group_id, scope=scope)

    if not data or not data['show']:
        return f"Show ID {show_id} not found", 404
        
    return render_template('showtitle.html', **data)


if __name__ == '__main__':
    app.run(debug=True, port=5001)