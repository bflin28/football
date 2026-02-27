"""
Lightweight Flask API for Vercel serverless deployment.

Serves pre-exported player data from data/players/*.json.
No heavy dependencies (pandas, scipy, nba_api) — just Flask + JSON file reads.
"""

from flask import Flask, jsonify, request
import json
import os
import unicodedata

app = Flask(__name__)

# ── Paths (relative to api/ directory) ──
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'players')
_MANIFEST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'manifest.json')

# ── In-memory caches (persist across warm invocations) ──
_shot_chart_index = None   # {game_id: filename}
_player_data_cache = {}    # {slug: data_dict} — avoid re-reading files
_manifest_cache = None     # cached manifest


def _slugify(name):
    """Convert player name to URL-safe slug: 'Nikola Jokić' → 'nikola-jokic'"""
    normalized = ''.join(
        c for c in unicodedata.normalize('NFD', name)
        if unicodedata.category(c) != 'Mn'
    )
    slug = ''
    for c in normalized.lower():
        if c.isalnum():
            slug += c
        elif slug and slug[-1] != '-':
            slug += '-'
    return slug.strip('-')


def _get_manifest():
    """Load manifest with caching."""
    global _manifest_cache
    if _manifest_cache is not None:
        return _manifest_cache
    if os.path.isfile(_MANIFEST_PATH):
        try:
            with open(_MANIFEST_PATH, 'r', encoding='utf-8') as f:
                _manifest_cache = json.load(f)
                return _manifest_cache
        except Exception:
            pass
    return {'players': []}


def _get_player_data(slug):
    """Load a player's data file with caching."""
    if slug in _player_data_cache:
        return _player_data_cache[slug]
    path = os.path.join(_DATA_DIR, f'{slug}.json')
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _player_data_cache[slug] = data
            return data
        except Exception:
            pass
    return None


def _get_shot_chart_index():
    """Build shot chart index: {game_id: slug} — lazy, cached."""
    global _shot_chart_index
    if _shot_chart_index is not None:
        return _shot_chart_index

    _shot_chart_index = {}
    if not os.path.isdir(_DATA_DIR):
        return _shot_chart_index

    for fn in os.listdir(_DATA_DIR):
        if not fn.endswith('.json'):
            continue
        slug = fn[:-5]  # strip .json
        path = os.path.join(_DATA_DIR, fn)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Cache the data while we're at it
            _player_data_cache[slug] = data
            for game_id in data.get('shot_charts', {}):
                _shot_chart_index[game_id] = slug
        except Exception:
            pass

    return _shot_chart_index


# ── API Routes ──

@app.route('/api/nba/available-players', methods=['GET'])
def nba_available_players():
    """Return list of pre-exported players available for instant analysis."""
    return jsonify(_get_manifest())


@app.route('/api/nba/stats-list', methods=['GET'])
def nba_stats_list():
    """Return available stats that can be analyzed."""
    return jsonify([
        {'key': 'AST', 'label': 'Assists'},
        {'key': 'PTS', 'label': 'Points'},
        {'key': 'REB', 'label': 'Rebounds'},
        {'key': 'STL', 'label': 'Steals'},
        {'key': 'BLK', 'label': 'Blocks'},
        {'key': 'TOV', 'label': 'Turnovers'},
        {'key': 'FG3M', 'label': '3-Pointers Made'},
        {'key': 'FGM', 'label': 'Field Goals Made'},
        {'key': 'FGA', 'label': 'Field Goals Attempted'},
        {'key': 'FTM', 'label': 'Free Throws Made'},
        {'key': 'FTA', 'label': 'Free Throws Attempted'},
        {'key': 'OREB', 'label': 'Offensive Rebounds'},
        {'key': 'DREB', 'label': 'Defensive Rebounds'},
        {'key': 'PF', 'label': 'Personal Fouls'},
        {'key': 'PLUS_MINUS', 'label': 'Plus/Minus'},
    ])


@app.route('/api/nba/players/search', methods=['GET'])
def nba_search_players():
    """Search available players by name (data-only mode)."""
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])

    def strip_diacritics(s):
        return ''.join(
            c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn'
        ).lower()

    q_norm = strip_diacritics(query)
    manifest = _get_manifest()
    matches = [
        {'id': p.get('id', ''), 'name': p['name'], 'team': ''}
        for p in manifest.get('players', [])
        if q_norm in strip_diacritics(p['name'])
    ]
    return jsonify(matches[:10])


@app.route('/api/nba/defensive-attention', methods=['GET'])
def nba_defensive_attention():
    """Return pre-exported DAS data for a player."""
    player = request.args.get('player')
    if not player:
        return jsonify({'error': 'Missing "player" parameter'}), 400

    slug = _slugify(player)
    data = _get_player_data(slug)
    if data is None:
        return jsonify({'error': f'No data available for "{player}". Try one of the quick-pick players.'}), 404

    # Return DAS data without shot_charts (they're served separately)
    result = {k: v for k, v in data.items() if k != 'shot_charts'}
    return jsonify(result)


@app.route('/api/nba/game/shot-chart', methods=['GET'])
def nba_game_shot_chart():
    """Return pre-exported shot chart for a specific game."""
    game_id = request.args.get('game_id', '')
    if not game_id:
        return jsonify({'error': 'game_id required'}), 400

    index = _get_shot_chart_index()
    slug = index.get(game_id)
    if not slug:
        return jsonify({'error': f'No shot chart data for game {game_id}'}), 404

    data = _get_player_data(slug)
    if data is None:
        return jsonify({'error': 'Data file not found'}), 404

    sc = data.get('shot_charts', {}).get(game_id)
    if sc is None:
        return jsonify({'error': f'Shot chart not found for game {game_id}'}), 404

    return jsonify(sc)
