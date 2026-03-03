from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import json
import os
import unicodedata

app = Flask(__name__)
CORS(app)

# ── Data-file serving (for hosted deployment) ──
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'players')
_MANIFEST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'manifest.json')
_DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend', 'dist')

# In-memory index: {game_id: filename} for fast shot chart lookups from data files
_shot_chart_index = {}


def _slugify(name):
    """Convert player name to URL-safe slug."""
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


def _build_shot_chart_index():
    """Build an in-memory index of game_id → data file for fast shot chart lookups."""
    global _shot_chart_index
    if not os.path.isdir(_DATA_DIR):
        return
    for fn in os.listdir(_DATA_DIR):
        if not fn.endswith('.json'):
            continue
        path = os.path.join(_DATA_DIR, fn)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for game_id in data.get('shot_charts', {}):
                _shot_chart_index[game_id] = fn
        except Exception:
            pass
    if _shot_chart_index:
        print(f"[DataFiles] Indexed {len(_shot_chart_index)} shot charts from {len(os.listdir(_DATA_DIR))} player files")


# Build index on import
_build_shot_chart_index()

# ── NBA Analysis Endpoints ───────────────────────────────────────────────────

from nba_analysis import (
    run_full_analysis,
    run_betting_analysis,
    analyze_stat_correlation,
    find_player,
    get_player_game_logs,
    build_game_features,
    enrich_with_opponent_context,
    get_team_context,
    compute_z_scores,
    test_distribution,
    analyze_factors,
    get_player_synergy_data,
    get_team_synergy_data,
    get_opponent_scheme_matchup,
    parse_game_pbp,
    enrich_games_with_scheme_context,
    run_das_analysis,
    fetch_game_shot_chart,
    get_top_players_by_stat,
    DiskCache,
    PLAY_TYPES,
    PLAY_TYPE_LABELS,
)

# Cache for NBA endpoint results (persists to disk)
_nba_cache = DiskCache('nba_endpoints', write_every=1)

@app.route('/api/nba/analyze', methods=['GET'])
def nba_analyze_player():
    """
    Full z-score + factor analysis for a player stat.

    Query params:
        player: player name (e.g. "Nikola Jokic")
        stat: stat column (e.g. "AST", "PTS", "REB")
        season: NBA season (e.g. "2024-25"), defaults to current
    """
    from flask import request

    player_name = request.args.get('player', 'Nikola Jokic')
    stat = request.args.get('stat', 'AST')
    season = request.args.get('season', '2024-25')
    per_minute = request.args.get('per_minute', 'false').lower() == 'true'

    cache_key = f"{player_name}|{stat}|{season}|pm={per_minute}"
    if cache_key in _nba_cache:
        return jsonify(_nba_cache[cache_key])

    try:
        result = run_full_analysis(player_name, stat, season, per_minute=per_minute)
        try:
            result['games'] = enrich_games_with_scheme_context(result['games'], season)
        except Exception:
            pass  # non-critical
        _nba_cache[cache_key] = result
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500


@app.route('/api/nba/players/search', methods=['GET'])
def nba_search_players():
    """Search for NBA players by name (diacritics-insensitive)."""
    import unicodedata
    from flask import request
    from nba_api.stats.static import players as nba_players

    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])

    def strip_diacritics(s):
        return ''.join(
            c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn'
        ).lower()

    q_norm = strip_diacritics(query)
    active = nba_players.get_active_players()
    matches = [
        {'id': p['id'], 'name': p['full_name'], 'team': ''}
        for p in active
        if q_norm in strip_diacritics(p['full_name'])
    ][:20]

    return jsonify(matches)


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


@app.route('/api/nba/play-types/player', methods=['GET'])
def nba_player_play_types():
    """
    Synergy play type breakdown for a player's team.

    Query params:
        player: player name (e.g. "Nikola Jokic")
        season: NBA season (e.g. "2024-25")
    """
    from flask import request

    player_name = request.args.get('player', 'Nikola Jokic')
    season = request.args.get('season', '2024-25')

    cache_key = f"synergy_player|{player_name}|{season}"
    if cache_key in _nba_cache:
        return jsonify(_nba_cache[cache_key])

    try:
        result = get_player_synergy_data(player_name, season)
        _nba_cache[cache_key] = result
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Play type fetch failed: {str(e)}'}), 500


@app.route('/api/nba/play-types/team', methods=['GET'])
def nba_team_play_types():
    """
    Synergy play type breakdown for a team (offensive + defensive).

    Query params:
        team: team abbreviation (e.g. "DEN", "LAL")
        season: NBA season (e.g. "2024-25")
    """
    from flask import request

    team_abbr = request.args.get('team', 'DEN')
    season = request.args.get('season', '2024-25')

    cache_key = f"synergy_team|{team_abbr}|{season}"
    if cache_key in _nba_cache:
        return jsonify(_nba_cache[cache_key])

    try:
        result = get_team_synergy_data(team_abbr, season)
        _nba_cache[cache_key] = result
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Team play type fetch failed: {str(e)}'}), 500


@app.route('/api/nba/play-types/matchup', methods=['GET'])
def nba_scheme_matchup():
    """
    Cross-reference player stat output vs opponent defensive scheme weaknesses.

    Query params:
        player: player name
        stat: stat column (e.g. "AST", "PTS")
        season: NBA season
    """
    from flask import request

    player_name = request.args.get('player', 'Nikola Jokic')
    stat = request.args.get('stat', 'AST')
    season = request.args.get('season', '2024-25')

    cache_key = f"synergy_matchup|{player_name}|{stat}|{season}"
    if cache_key in _nba_cache:
        return jsonify(_nba_cache[cache_key])

    try:
        result = get_opponent_scheme_matchup(player_name, stat, season)
        _nba_cache[cache_key] = result
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Matchup analysis failed: {str(e)}'}), 500


@app.route('/api/nba/play-types/list', methods=['GET'])
def nba_play_types_list():
    """Return available Synergy play types."""
    return jsonify([
        {'key': pt, 'label': PLAY_TYPE_LABELS[pt]}
        for pt in PLAY_TYPES
    ])


@app.route('/api/nba/betting/analyze', methods=['GET'])
def nba_betting_analyze():
    """
    Full prop line analysis for betting.

    Query params:
        player: player name
        stat: stat column (AST, PTS, etc.)
        line: numeric betting line (e.g. 8.5)
        season: NBA season (default 2024-25)
        odds_over: American odds for over (default -110)
        odds_under: American odds for under (default -110)
    """
    from flask import request

    player_name = request.args.get('player', 'Nikola Jokic')
    stat = request.args.get('stat', 'AST')
    line = request.args.get('line', '0')
    season = request.args.get('season', '2024-25')
    odds_over = request.args.get('odds_over', '-110')
    odds_under = request.args.get('odds_under', '-110')
    per_minute = request.args.get('per_minute', 'false').lower() == 'true'

    try:
        line_f = float(line)
    except ValueError:
        return jsonify({'error': 'Invalid line value'}), 400

    cache_key = f"betting|{player_name}|{stat}|{line}|{season}|{odds_over}|{odds_under}|pm={per_minute}"
    if cache_key in _nba_cache:
        return jsonify(_nba_cache[cache_key])

    try:
        result = run_betting_analysis(
            player_name, stat, line_f, season,
            odds_over=int(odds_over), odds_under=int(odds_under),
            per_minute=per_minute,
        )
        try:
            result['games'] = enrich_games_with_scheme_context(result['games'], season)
        except Exception:
            pass  # non-critical
        _nba_cache[cache_key] = result
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Betting analysis failed: {str(e)}'}), 500


@app.route('/api/nba/betting/correlation', methods=['GET'])
def nba_stat_correlation():
    """
    Analyze correlation between two stats for parlay assessment.

    Query params:
        player: player name
        stat_a: first stat (e.g. PTS)
        stat_b: second stat (e.g. AST)
        line_a: optional line for stat A
        line_b: optional line for stat B
        season: NBA season
    """
    from flask import request

    player_name = request.args.get('player', 'Nikola Jokic')
    stat_a = request.args.get('stat_a', 'PTS')
    stat_b = request.args.get('stat_b', 'AST')
    line_a = request.args.get('line_a')
    line_b = request.args.get('line_b')
    season = request.args.get('season', '2024-25')

    cache_key = f"corr|{player_name}|{stat_a}|{stat_b}|{line_a}|{line_b}|{season}"
    if cache_key in _nba_cache:
        return jsonify(_nba_cache[cache_key])

    try:
        player = find_player(player_name)
        game_logs = get_player_game_logs(player['id'], season=season)
        if game_logs.empty:
            raise ValueError(f"No game data for {player_name} in {season}")
        df = build_game_features(game_logs)

        result = analyze_stat_correlation(
            df, stat_a.upper(), stat_b.upper(),
            line_a=float(line_a) if line_a else None,
            line_b=float(line_b) if line_b else None,
        )
        result['player'] = player['full_name']
        result['season'] = season
        _nba_cache[cache_key] = result
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Correlation analysis failed: {str(e)}'}), 500


@app.route('/api/nba/game/pbp-detail', methods=['GET'])
def nba_game_pbp_detail():
    """
    On-demand play-by-play action classification for a player in a specific game.

    Query params:
        game_id: NBA game ID (e.g. "0022401193")
        player_id: NBA player ID (e.g. 203999)
    """
    from flask import request

    game_id = request.args.get('game_id', '')
    player_id = request.args.get('player_id', '')

    if not game_id or not player_id:
        return jsonify({'error': 'game_id and player_id required'}), 400

    try:
        player_id_int = int(player_id)
    except ValueError:
        return jsonify({'error': 'Invalid player_id'}), 400

    cache_key = f"pbp_detail|{game_id}|{player_id}"
    if cache_key in _nba_cache:
        return jsonify(_nba_cache[cache_key])

    try:
        result = parse_game_pbp(game_id, player_id_int)
        _nba_cache[cache_key] = result
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'PBP fetch failed: {str(e)}'}), 500


@app.route('/api/nba/defensive-attention', methods=['GET'])
def nba_defensive_attention():
    """
    Compute Defensive Attention Score (DAS) for a player/stat.

    Query params:
        player: player name (e.g. "Nikola Jokic")
        stat: stat column (e.g. "PTS")
        season: NBA season (e.g. "2024-25"), defaults to current
        per_minute: "true" to use per-minute normalization
    """
    from flask import request
    player = request.args.get('player')
    stat = request.args.get('stat', 'PTS')
    season = request.args.get('season', '2024-25')
    per_minute = request.args.get('per_minute', 'false').lower() == 'true'

    if not player:
        return jsonify({'error': 'Missing "player" parameter'}), 400

    # Check pre-exported data files first (for hosted deployment)
    slug = _slugify(player)
    data_path = os.path.join(_DATA_DIR, f'{slug}.json')
    if os.path.isfile(data_path):
        try:
            with open(data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Remove shot_charts from DAS response (they're served separately)
            data.pop('shot_charts', None)
            return jsonify(data)
        except Exception:
            pass  # Fall through to live computation

    cache_key = f'das|{player}|{stat}|{season}|pm={per_minute}'
    if cache_key in _nba_cache:
        return jsonify(_nba_cache[cache_key])

    try:
        result = run_das_analysis(player, stat, season=season, per_minute=per_minute)
        _nba_cache[cache_key] = result
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'DAS analysis failed: {str(e)}'}), 500


@app.route('/api/nba/game/shot-chart', methods=['GET'])
def nba_game_shot_chart():
    """
    Shot chart data (x,y locations) for a player in a specific game.

    Query params:
        game_id: NBA game ID
        player_id: NBA player ID
        team_id: NBA team ID
    """
    from flask import request
    game_id = request.args.get('game_id', '')
    player_id = request.args.get('player_id', '')
    team_id = request.args.get('team_id', '')

    if not game_id or not player_id or not team_id:
        return jsonify({'error': 'game_id, player_id, and team_id required'}), 400

    # Check pre-exported data files first (for hosted deployment)
    if game_id in _shot_chart_index:
        try:
            fn = _shot_chart_index[game_id]
            with open(os.path.join(_DATA_DIR, fn), 'r', encoding='utf-8') as f:
                pdata = json.load(f)
            sc = pdata.get('shot_charts', {}).get(game_id)
            if sc:
                return jsonify(sc)
        except Exception:
            pass  # Fall through to live fetch

    cache_key = f'shot_chart|{game_id}|{player_id}'
    if cache_key in _nba_cache:
        return jsonify(_nba_cache[cache_key])

    try:
        result = fetch_game_shot_chart(game_id, int(player_id), int(team_id))
        _nba_cache[cache_key] = result
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'Shot chart failed: {str(e)}'}), 500


@app.route('/api/nba/top-players', methods=['GET'])
def nba_top_players():
    """
    Get top N players by a stat for a season.

    Query params:
        stat: stat column (e.g. "PTS", "AST")
        season: NBA season (e.g. "2025-26")
        limit: number of players (default 20)
    """
    from flask import request
    stat = request.args.get('stat', 'PTS')
    season = request.args.get('season', '2024-25')
    limit = request.args.get('limit', '20')

    try:
        limit_int = int(limit)
    except ValueError:
        return jsonify({'error': 'Invalid limit'}), 400

    cache_key = f'top_players|{stat}|{season}|{limit}'
    if cache_key in _nba_cache:
        return jsonify(_nba_cache[cache_key])

    try:
        result = get_top_players_by_stat(stat, season, limit_int)
        _nba_cache[cache_key] = result
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Top players fetch failed: {str(e)}'}), 500


@app.route('/api/nba/cache/clear', methods=['POST'])
def nba_clear_cache():
    """Clear the NBA data cache."""
    _nba_cache.clear()
    return jsonify({'status': 'cache cleared'})


@app.route('/api/nba/available-players', methods=['GET'])
def nba_available_players():
    """Return list of pre-exported players available for instant analysis."""
    if os.path.isfile(_MANIFEST_PATH):
        try:
            with open(_MANIFEST_PATH, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        except Exception:
            pass
    return jsonify({'players': []})


# ── Serve built frontend (production) ──
# This must be LAST so it doesn't shadow /api routes
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    """Serve the built React frontend (production mode)."""
    if not os.path.isdir(_DIST_DIR):
        return jsonify({'error': 'Frontend not built. Run: cd frontend && npm run build'}), 404

    # Serve static files (JS, CSS, images)
    full_path = os.path.join(_DIST_DIR, path)
    if path and os.path.isfile(full_path):
        return send_from_directory(_DIST_DIR, path)

    # SPA fallback: serve index.html for all other routes
    return send_from_directory(_DIST_DIR, 'index.html')


if __name__ == '__main__':
    print("Starting NBA Factor Analysis Platform...")
    print("NBA endpoints ready (data fetched on demand)")
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'
    app.run(debug=debug, host='0.0.0.0', port=port)