from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd
from nfl_data_py import import_pbp_data
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

# Global variable to store the data
pbp_data = None

def load_nfl_data():
    """Load and process NFL play-by-play data"""
    global pbp_data
    
    # 1) Fetch 2023 PBP (avoid downcasting so columns like wpa aren't dropped)
    pbp = import_pbp_data([2023], downcast=False, cache=False)

    # 2) Ensure WPA/WP_POST exist (recompute if wpa wasn't included)
    if 'wpa' not in pbp.columns:
        # next play's pre-play WP within the same game
        pbp['wp_post'] = pbp.groupby('game_id')['wp'].shift(-1)
        pbp['wpa'] = pbp['wp_post'] - pbp['wp']
    else:
        # provide wp_post for convenience
        pbp['wp_post'] = pbp['wp'] + pbp['wpa']

    # 3) Keep a tidy subset of useful columns (including ordering fields and descriptions)
    keep = [
        'game_id','play_id','season','week','posteam','defteam','home_team','away_team',
        'down','ydstogo','yardline_100','qtr','half_seconds_remaining','game_seconds_remaining',
        'score_differential','posteam_timeouts_remaining','defteam_timeouts_remaining',
        'roof','surface','temp','wind','play_type','field_goal_result','punt_blocked',
        'wp','wpa','wp_post','ep','epa','drive','fixed_drive','drive_play_count',
        'game_half','quarter_seconds_remaining',  # Additional time fields
        'desc','play_description','name','yards_gained','rushing_yards','passing_yards',
        'receiver','rusher','passer','interception','fumble','touchdown','safety',
        'first_down','penalty','penalty_type','penalty_yards'  # Description and outcome fields
    ]
    pbp = pbp[[c for c in keep if c in pbp.columns]].copy()
    
    # Check what time fields are actually available and use the best one for sorting
    time_field = None
    if 'game_seconds_remaining' in pbp.columns and pbp['game_seconds_remaining'].notna().any():
        time_field = 'game_seconds_remaining'
    elif 'quarter_seconds_remaining' in pbp.columns and pbp['quarter_seconds_remaining'].notna().any():
        time_field = 'quarter_seconds_remaining'
    elif 'half_seconds_remaining' in pbp.columns and pbp['half_seconds_remaining'].notna().any():
        time_field = 'half_seconds_remaining'
    
    # Sort by proper chronological order
    if time_field:
        pbp = pbp.sort_values([
            'game_id', 
            'qtr', 
            time_field
        ], ascending=[True, True, False])  # time descending (more time = earlier in game)
    else:
        # Fallback to basic sorting if no time field available
        pbp = pbp.sort_values(['game_id', 'qtr', 'play_id'])
    pbp_data = pbp
    
    return pbp

@app.route('/api/games')
def get_games():
    """Get list of all games"""
    if pbp_data is None:
        load_nfl_data()
    
    # Get unique games with basic info
    games = pbp_data.groupby('game_id').agg({
        'week': 'first',
        'home_team': 'first',
        'away_team': 'first',
        'season': 'first'
    }).reset_index()
    
    games_list = []
    for _, game in games.iterrows():
        games_list.append({
            'game_id': game['game_id'],
            'week': int(game['week']),
            'home_team': game['home_team'],
            'away_team': game['away_team'],
            'season': int(game['season']),
            'display_name': f"Week {int(game['week'])}: {game['away_team']} @ {game['home_team']}"
        })
    
    return jsonify(games_list)

@app.route('/api/games/<game_id>/plays')
def get_game_plays(game_id):
    """Get all plays for a specific game"""
    if pbp_data is None:
        load_nfl_data()
    
    game_plays = pbp_data[pbp_data['game_id'] == game_id].copy()
    
    # Ensure proper chronological ordering for this specific game
    # Use the best available time field
    time_field = None
    if 'game_seconds_remaining' in game_plays.columns and game_plays['game_seconds_remaining'].notna().any():
        time_field = 'game_seconds_remaining'
    elif 'quarter_seconds_remaining' in game_plays.columns and game_plays['quarter_seconds_remaining'].notna().any():
        time_field = 'quarter_seconds_remaining'
    elif 'half_seconds_remaining' in game_plays.columns and game_plays['half_seconds_remaining'].notna().any():
        time_field = 'half_seconds_remaining'
    
    if time_field:
        game_plays = game_plays.sort_values([
            'qtr', 
            time_field
        ], ascending=[True, False])  # Quarter ascending, time descending (more time = earlier)
    else:
        game_plays = game_plays.sort_values(['qtr', 'play_id'])
    
    # Convert to records and handle NaN values
    plays = []
    for _, play in game_plays.iterrows():
        play_dict = play.to_dict()
        # Convert NaN values to None for JSON serialization
        for key, value in play_dict.items():
            if pd.isna(value):
                play_dict[key] = None
            elif isinstance(value, (pd.Int64Dtype, pd.Float64Dtype)):
                play_dict[key] = None if pd.isna(value) else value
        plays.append(play_dict)
    
    return jsonify(plays)

@app.route('/api/games/<game_id>/plays/<int:play_index>')
def get_specific_play(game_id, play_index):
    """Get a specific play by index"""
    if pbp_data is None:
        load_nfl_data()
    
    game_plays = pbp_data[pbp_data['game_id'] == game_id].copy()
    
    # Ensure proper chronological ordering for this specific game
    # Use the best available time field
    time_field = None
    if 'game_seconds_remaining' in game_plays.columns and game_plays['game_seconds_remaining'].notna().any():
        time_field = 'game_seconds_remaining'
    elif 'quarter_seconds_remaining' in game_plays.columns and game_plays['quarter_seconds_remaining'].notna().any():
        time_field = 'quarter_seconds_remaining'
    elif 'half_seconds_remaining' in game_plays.columns and game_plays['half_seconds_remaining'].notna().any():
        time_field = 'half_seconds_remaining'
    
    if time_field:
        game_plays = game_plays.sort_values([
            'qtr', 
            time_field
        ], ascending=[True, False])  # Quarter ascending, time descending (more time = earlier)
    else:
        game_plays = game_plays.sort_values(['qtr', 'play_id'])
    
    if play_index < 0 or play_index >= len(game_plays):
        return jsonify({'error': 'Play index out of range'}), 404
    
    play = game_plays.iloc[play_index]
    play_dict = play.to_dict()
    
    # Convert NaN values to None for JSON serialization
    for key, value in play_dict.items():
        if pd.isna(value):
            play_dict[key] = None
    
    # Add metadata
    play_dict['play_index'] = play_index
    play_dict['total_plays'] = len(game_plays)
    
    return jsonify(play_dict)

@app.route('/api/data/raw')
def get_raw_data():
    """Get the raw DataFrame as JSON for pandas analysis"""
    if pbp_data is None:
        load_nfl_data()
    
    # Convert to JSON with proper handling of NaN values
    return jsonify(pbp_data.to_dict('records'))

@app.route('/api/data/csv')
def get_csv_data():
    """Get the raw DataFrame as CSV for easy pandas loading"""
    if pbp_data is None:
        load_nfl_data()
    
    from flask import Response
    import io
    
    # Create CSV string
    output = io.StringIO()
    pbp_data.to_csv(output, index=False)
    csv_string = output.getvalue()
    
    return Response(
        csv_string,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=nfl_pbp_2023.csv'}
    )

@app.route('/api/data/info')
def get_data_info():
    """Get information about the DataFrame structure"""
    if pbp_data is None:
        load_nfl_data()
    
    # Get basic info about the DataFrame
    info = {
        'shape': pbp_data.shape,
        'columns': list(pbp_data.columns),
        'dtypes': pbp_data.dtypes.astype(str).to_dict(),
        'null_counts': pbp_data.isnull().sum().to_dict(),
        'sample_data': pbp_data.head().to_dict('records')
    }
    
    return jsonify(info)

# Model Analysis Endpoints
@app.route('/api/model/sample-data')
def get_model_sample_data():
    """Get sample data for model analysis visualization"""
    if pbp_data is None:
        load_nfl_data()
    
    # Create sample feature importance data (this would come from your trained model)
    sample_features = [
        {'feature': 'field_position', 'importance': 0.25, 'description': 'Distance from opponent goal line'},
        {'feature': 'score_differential', 'importance': 0.18, 'description': 'Point difference between teams'},
        {'feature': 'game_seconds_remaining', 'importance': 0.15, 'description': 'Time left in game'},
        {'feature': 'down', 'importance': 0.12, 'description': 'Current down (1st, 2nd, 3rd, 4th)'},
        {'feature': 'ydstogo', 'importance': 0.10, 'description': 'Yards needed for first down'},
        {'feature': 'wp', 'importance': 0.08, 'description': 'Win probability before play'},
        {'feature': 'ep', 'importance': 0.06, 'description': 'Expected points from field position'},
        {'feature': 'qtr', 'importance': 0.04, 'description': 'Quarter of game'},
        {'feature': 'posteam_timeouts_remaining', 'importance': 0.02, 'description': 'Timeouts left for offense'}
    ]
    
    return jsonify({
        'feature_importance': sample_features,
        'model_metrics': {
            'accuracy': 0.847,
            'r2_score': 0.723,
            'mean_absolute_error': 0.156,
            'total_features': len(sample_features),
            'sample_size': len(pbp_data)
        }
    })

@app.route('/api/model/feature-analysis/<feature_name>')
def get_feature_analysis(feature_name):
    """Get detailed analysis for a specific feature"""
    if pbp_data is None:
        load_nfl_data()
    
    if feature_name not in pbp_data.columns:
        return jsonify({'error': f'Feature {feature_name} not found'}), 404
    
    feature_data = pbp_data[feature_name].dropna()
    
    # Calculate statistics
    analysis = {
        'feature_name': feature_name,
        'statistics': {
            'count': int(len(feature_data)),
            'mean': float(feature_data.mean()) if feature_data.dtype in ['int64', 'float64'] else None,
            'std': float(feature_data.std()) if feature_data.dtype in ['int64', 'float64'] else None,
            'min': float(feature_data.min()) if feature_data.dtype in ['int64', 'float64'] else str(feature_data.min()),
            'max': float(feature_data.max()) if feature_data.dtype in ['int64', 'float64'] else str(feature_data.max()),
            'unique_values': int(feature_data.nunique())
        }
    }
    
    # Add distribution data for visualization
    if feature_data.dtype in ['int64', 'float64']:
        # Numeric feature - create histogram data
        import numpy as np
        hist, bin_edges = np.histogram(feature_data, bins=20)
        analysis['distribution'] = {
            'type': 'histogram',
            'bins': bin_edges.tolist(),
            'counts': hist.tolist()
        }
    else:
        # Categorical feature - create frequency data
        value_counts = feature_data.value_counts().head(10)
        analysis['distribution'] = {
            'type': 'categorical',
            'categories': value_counts.index.tolist(),
            'counts': value_counts.values.tolist()
        }
    
    return jsonify(analysis)

@app.route('/api/model/predictions-sample')
def get_predictions_sample():
    """Get sample predictions vs actual values for visualization"""
    if pbp_data is None:
        load_nfl_data()
    
    # Create sample prediction data (this would come from your trained model)
    import numpy as np
    np.random.seed(42)
    
    sample_size = min(100, len(pbp_data))
    actual_values = pbp_data['wpa'].dropna().head(sample_size).values
    
    # Simulate predictions with some noise
    predictions = actual_values + np.random.normal(0, 0.1, len(actual_values))
    
    sample_data = []
    for i, (actual, pred) in enumerate(zip(actual_values, predictions)):
        sample_data.append({
            'id': i,
            'actual': float(actual),
            'predicted': float(pred),
            'residual': float(actual - pred),
            'abs_residual': float(abs(actual - pred))
        })
    
    return jsonify({
        'predictions': sample_data,
        'metrics': {
            'mae': float(np.mean(np.abs(actual_values - predictions))),
            'rmse': float(np.sqrt(np.mean((actual_values - predictions)**2))),
            'r2': float(np.corrcoef(actual_values, predictions)[0, 1]**2)
        }
    })

@app.route('/api/model/clustering-data')
def get_clustering_data():
    """Get data for clustering visualization"""
    if pbp_data is None:
        load_nfl_data()
    
    import numpy as np
    np.random.seed(42)
    
    # Get plays with required fields
    plays_data = pbp_data[['yardline_100', 'score_differential', 'game_seconds_remaining', 
                          'down', 'ydstogo', 'wp', 'wpa', 'play_type']].dropna()
    
    # Sample for visualization
    sample_size = min(300, len(plays_data))
    sample_plays = plays_data.sample(n=sample_size, random_state=42)
    
    # Create clusters based on game situation
    cluster_data = []
    for _, play in sample_plays.iterrows():
        # Simple clustering logic based on field position and score
        if play['yardline_100'] <= 20:
            cluster = 'Red Zone'
            color = '#e74c3c'
        elif play['yardline_100'] <= 50:
            cluster = 'Scoring Territory'  
            color = '#f39c12'
        elif play['score_differential'] > 7:
            cluster = 'Winning Big'
            color = '#27ae60'
        elif play['score_differential'] < -7:
            cluster = 'Losing Big'
            color = '#8e44ad'
        else:
            cluster = 'Competitive'
            color = '#3498db'
            
        cluster_data.append({
            'x': float(play['yardline_100']),
            'y': float(play['score_differential']),
            'z': float(play['wp']) if not pd.isna(play['wp']) else 0.5,
            'cluster': cluster,
            'color': color,
            'down': int(play['down']) if not pd.isna(play['down']) else 1,
            'ydstogo': float(play['ydstogo']) if not pd.isna(play['ydstogo']) else 10,
            'wpa': float(play['wpa']) if not pd.isna(play['wpa']) else 0,
            'play_type': str(play['play_type']) if not pd.isna(play['play_type']) else 'unknown'
        })
    
    return jsonify({
        'clusters': cluster_data,
        'cluster_info': {
            'Red Zone': {'color': '#e74c3c', 'description': 'Plays near the goal line (0-20 yards)'},
            'Scoring Territory': {'color': '#f39c12', 'description': 'Good field position (21-50 yards)'},
            'Winning Big': {'color': '#27ae60', 'description': 'Team ahead by more than 7 points'},
            'Losing Big': {'color': '#8e44ad', 'description': 'Team behind by more than 7 points'},
            'Competitive': {'color': '#3498db', 'description': 'Close game situations'}
        }
    })

@app.route('/api/model/feature-correlation')
def get_feature_correlation():
    """Get feature correlation data for heatmap visualization"""
    if pbp_data is None:
        load_nfl_data()
    
    # Select numeric features for correlation
    numeric_features = ['yardline_100', 'score_differential', 'game_seconds_remaining', 
                       'down', 'ydstogo', 'wp', 'ep', 'wpa', 'qtr']
    
    correlation_data = pbp_data[numeric_features].corr()
    
    # Convert to format suitable for heatmap
    heatmap_data = []
    features = correlation_data.columns.tolist()
    
    for i, feature1 in enumerate(features):
        for j, feature2 in enumerate(features):
            correlation_value = correlation_data.loc[feature1, feature2]
            if not pd.isna(correlation_value):
                heatmap_data.append({
                    'x': j,
                    'y': i,
                    'feature1': feature1,
                    'feature2': feature2,
                    'correlation': float(correlation_value),
                    'abs_correlation': float(abs(correlation_value))
                })
    
    return jsonify({
        'correlations': heatmap_data,
        'features': features,
        'description': 'Feature correlation matrix showing relationships between variables'
    })

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