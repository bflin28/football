"""
Export team defensive impact analysis to JSON for deployment.
Computes how each team's defense suppresses opponent stats by position group.

Usage:
    python export_team_defense.py                    # All 30 teams
    python export_team_defense.py --team HOU         # Single team
    python export_team_defense.py --season 2024-25   # Different season
"""

import sys, io, os, json, time, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import numpy as np
from nba_api.stats.endpoints import leaguedashplayerstats
from nba_api.stats.static import teams as nba_teams

from nba_analysis import (
    get_team_defense_profiles,
    get_team_synergy_data,
    get_team_context,
    DiskCache,
    _safe_float,
    PLAY_TYPE_LABELS,
)

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'teams')
INDEX_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'team_index.json')

_nba_cache = DiskCache('nba_endpoints', write_every=1)

POSITIONS = ['G', 'F', 'C']
POSITION_LABELS = {'G': 'Guards', 'F': 'Wings', 'C': 'Bigs'}

# Stats to compute deviations for
IMPACT_STATS = ['PTS', 'REB', 'AST', 'STL', 'BLK', 'TOV',
                'FG_PCT', 'FG3_PCT', 'FGM', 'FGA', 'FG3M', 'FG3A',
                'FTM', 'FTA', 'OREB', 'DREB', 'MIN']

# Core stats shown prominently in the UI
DISPLAY_STATS = ['PTS', 'REB', 'AST', 'STL', 'FG_PCT', 'FG3_PCT']

SEASON = '2025-26'


class SafeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


# ── Data Fetching ──

def fetch_position_stats(position, season, opponent_team_id=0):
    """
    Fetch per-player stats filtered by position and optionally by opponent.
    opponent_team_id=0 means league-wide (no opponent filter).
    Returns a DataFrame with per-game averages.
    """
    cache_key = f"team_def_pos|{position}|{opponent_team_id}|{season}"
    if cache_key in _nba_cache:
        return _nba_cache[cache_key]

    for attempt in range(3):
        try:
            time.sleep(0.6)
            kwargs = dict(
                season=season,
                per_mode_detailed='PerGame',
                player_position_abbreviation_nullable=position,
                season_type_all_star='Regular Season',
                timeout=60,
            )
            if opponent_team_id:
                kwargs['opponent_team_id'] = opponent_team_id

            data = leaguedashplayerstats.LeagueDashPlayerStats(**kwargs)
            df = data.get_data_frames()[0]

            # Convert to list of dicts for caching
            records = df.to_dict('records')
            _nba_cache[cache_key] = records
            return records
        except Exception as e:
            if attempt < 2:
                print(f"    Retry {attempt+1}/2 after error: {e}")
                time.sleep(2)
            else:
                print(f"    Failed after 3 attempts: {e}")
                return []


def records_to_player_map(records, min_gp=1):
    """Convert a list of player stat records to a dict keyed by PLAYER_ID."""
    result = {}
    for r in records:
        pid = r.get('PLAYER_ID')
        gp = r.get('GP', 0) or 0
        if pid and gp >= min_gp:
            result[pid] = r
    return result


# ── Deviation Computation ──

def compute_position_deviations(league_records, vs_team_records):
    """
    Compute per-player deviations and aggregate for a position group.
    Returns: {
        'sample_size': {'total_player_games': N, 'unique_players': N},
        'deviations': {'PTS': {'value': -2.8, ...}, ...},
        'top_affected_players': [...]
    }
    """
    league_map = records_to_player_map(league_records, min_gp=10)
    vs_map = records_to_player_map(vs_team_records, min_gp=1)

    # Only include players who appear in BOTH datasets
    common_pids = set(league_map.keys()) & set(vs_map.keys())
    if not common_pids:
        return None

    # Per-player deviations
    player_devs = []
    for pid in common_pids:
        league = league_map[pid]
        vs = vs_map[pid]
        gp_vs = vs.get('GP', 1) or 1

        devs = {}
        for stat in IMPACT_STATS:
            league_val = _safe_float(league.get(stat))
            vs_val = _safe_float(vs.get(stat))
            if league_val is not None and vs_val is not None:
                devs[stat] = vs_val - league_val

        player_devs.append({
            'player_id': pid,
            'player_name': vs.get('PLAYER_NAME', league.get('PLAYER_NAME', '')),
            'team': vs.get('TEAM_ABBREVIATION', ''),
            'gp': gp_vs,
            'season_avg': {s: _safe_float(league.get(s)) for s in DISPLAY_STATS},
            'vs_team_avg': {s: _safe_float(vs.get(s)) for s in DISPLAY_STATS},
            'deviations': {s: round(devs.get(s, 0), 3) for s in DISPLAY_STATS},
        })

    if not player_devs:
        return None

    # Weighted aggregate deviation (weighted by GP vs team)
    total_gp = sum(p['gp'] for p in player_devs)
    agg_devs = {}
    for stat in IMPACT_STATS:
        weighted_sum = 0
        weight_sum = 0
        for p in player_devs:
            league = league_map[p['player_id']]
            vs = vs_map[p['player_id']]
            league_val = _safe_float(league.get(stat))
            vs_val = _safe_float(vs.get(stat))
            if league_val is not None and vs_val is not None:
                weighted_sum += (vs_val - league_val) * p['gp']
                weight_sum += p['gp']
        if weight_sum > 0:
            agg_devs[stat] = round(weighted_sum / weight_sum, 3)
        else:
            agg_devs[stat] = 0.0

    # Top affected players: sort by PTS deviation (most suppressed first)
    player_devs_sorted = sorted(
        [p for p in player_devs if p['gp'] >= 2],
        key=lambda p: p['deviations'].get('PTS', 0)
    )[:15]

    return {
        'sample_size': {
            'total_player_games': total_gp,
            'unique_players': len(common_pids),
        },
        'deviations': {s: {'value': agg_devs.get(s, 0)} for s in IMPACT_STATS},
        'top_affected_players': player_devs_sorted,
    }


def compute_all_team_rankings(all_team_data):
    """
    Rank all 30 teams by each stat deviation for each position.
    Lower deviation = better defense (more suppressive) = lower rank number.
    Mutates team data in place to add 'rank' and 'pctile' to each deviation.
    """
    for pos in POSITIONS:
        for stat in IMPACT_STATS:
            # Collect (team_abbr, deviation_value) for this stat+position
            team_vals = []
            for abbr, tdata in all_team_data.items():
                pos_data = tdata.get('position_impact', {}).get(pos)
                if pos_data and pos_data.get('deviations', {}).get(stat):
                    val = pos_data['deviations'][stat]['value']
                    team_vals.append((abbr, val))

            if not team_vals:
                continue

            # Sort ascending — most negative = best at suppressing = rank 1
            team_vals.sort(key=lambda x: x[1])

            for rank_idx, (abbr, val) in enumerate(team_vals):
                rank = rank_idx + 1
                pctile = round((1 - rank_idx / max(len(team_vals) - 1, 1)) * 100)
                pos_data = all_team_data[abbr]['position_impact'][pos]
                pos_data['deviations'][stat]['rank'] = rank
                pos_data['deviations'][stat]['pctile'] = pctile


# ── Insight Generation ──

def generate_insights(team_data):
    """Auto-generate notable findings from the team's defensive data."""
    insights = []
    pos_impact = team_data.get('position_impact', {})

    for pos in POSITIONS:
        pos_data = pos_impact.get(pos)
        if not pos_data:
            continue
        label = POSITION_LABELS[pos]
        devs = pos_data.get('deviations', {})

        # PTS suppression
        pts = devs.get('PTS', {})
        if pts.get('value', 0) < -1.5:
            rank = pts.get('rank')
            rank_text = f", #{rank} most suppressive in the league" if rank else ""
            insights.append({
                'type': 'position_suppression',
                'severity': 'high' if rank and rank <= 5 else 'medium',
                'text': f"{label} score {abs(pts['value']):.1f} fewer PPG{rank_text}.",
            })

        # FG% impact
        fg = devs.get('FG_PCT', {})
        if fg.get('value', 0) < -0.02:
            rank = fg.get('rank')
            rank_text = f", #{rank} in the NBA" if rank else ""
            insights.append({
                'type': 'shooting_impact',
                'severity': 'high' if rank and rank <= 5 else 'medium',
                'text': f"Opposing {label.lower()} shoot {abs(fg['value'])*100:.1f}% worse from the field{rank_text}.",
            })

        # 3PT% impact
        fg3 = devs.get('FG3_PCT', {})
        if fg3.get('value', 0) < -0.025:
            rank = fg3.get('rank')
            rank_text = f", #{rank} in the NBA" if rank else ""
            insights.append({
                'type': 'three_point_impact',
                'severity': 'high' if rank and rank <= 5 else 'medium',
                'text': f"Opposing {label.lower()} shoot {abs(fg3['value'])*100:.1f}% worse from three{rank_text}.",
            })

        # REB suppression (most relevant for Bigs)
        reb = devs.get('REB', {})
        if reb.get('value', 0) < -1.0:
            rank = reb.get('rank')
            rank_text = f", #{rank} in rebound suppression" if rank else ""
            insights.append({
                'type': 'rebounding_dominance',
                'severity': 'high' if rank and rank <= 5 else 'medium',
                'text': f"Opposing {label.lower()} grab {abs(reb['value']):.1f} fewer RPG{rank_text}.",
            })

        # AST suppression
        ast = devs.get('AST', {})
        if ast.get('value', 0) < -0.8:
            rank = ast.get('rank')
            rank_text = f", #{rank} in assist suppression" if rank else ""
            insights.append({
                'type': 'playmaking_disruption',
                'severity': 'medium',
                'text': f"Opposing {label.lower()} dish {abs(ast['value']):.1f} fewer APG{rank_text}.",
            })

    # Scheme insights from synergy
    synergy_def = team_data.get('scheme_fingerprint', {}).get('synergy_defensive', [])
    for pt in synergy_def[:3]:  # Top 3 by possessions
        pctile = pt.get('percentile') or 0
        if pctile >= 0.75:
            insights.append({
                'type': 'scheme_strength',
                'severity': 'high' if pctile >= 0.90 else 'medium',
                'text': f"Ranks in the {int(pctile*100)}th percentile defending {pt['label']} plays ({pt['ppp']:.2f} PPP allowed).",
            })

    # Sort by severity
    severity_order = {'high': 0, 'medium': 1, 'low': 2}
    insights.sort(key=lambda x: severity_order.get(x.get('severity', 'low'), 2))

    return insights[:8]  # Limit to top 8 insights


# ── Export ──

def export_team(team_abbr, team_id, team_name, position_impact, scheme, ratings, season):
    """Build and write a single team's defense JSON."""
    team_data = {
        'team': {
            'abbreviation': team_abbr,
            'full_name': team_name,
            'id': team_id,
        },
        'season': season,
        'ratings': ratings,
        'position_impact': position_impact,
        'scheme_fingerprint': scheme,
        'insights': [],  # Filled after rankings
    }
    return team_data


def write_team_json(team_data, team_abbr):
    """Write team JSON to disk."""
    os.makedirs(DATA_DIR, exist_ok=True)
    out_path = os.path.join(DATA_DIR, f'{team_abbr}.json')
    with open(out_path, 'w') as f:
        json.dump(team_data, f, cls=SafeEncoder, separators=(',', ':'))
    size_kb = os.path.getsize(out_path) / 1024
    print(f"  Wrote {out_path} ({size_kb:.1f} KB)")
    return size_kb


def write_team_index(entries, season):
    """Write team_index.json."""
    from datetime import datetime, timezone
    index = {
        'teams': entries,
        'season': season,
        'exported_at': datetime.now(timezone.utc).isoformat(),
    }
    with open(INDEX_PATH, 'w') as f:
        json.dump(index, f, cls=SafeEncoder, indent=2)
    print(f"\nWrote {INDEX_PATH} ({len(entries)} teams)")


# ── Main ──

def main():
    parser = argparse.ArgumentParser(description='Export team defense analysis')
    parser.add_argument('--team', type=str, default=None, help='Single team abbreviation (e.g. HOU)')
    parser.add_argument('--season', type=str, default=SEASON, help='NBA season (e.g. 2025-26)')
    args = parser.parse_args()

    season = args.season
    all_teams = nba_teams.get_teams()
    team_lookup = {t['abbreviation']: t for t in all_teams}

    if args.team:
        if args.team not in team_lookup:
            print(f"Error: Unknown team '{args.team}'")
            print(f"Valid: {', '.join(sorted(team_lookup.keys()))}")
            sys.exit(1)
        target_teams = [team_lookup[args.team]]
    else:
        target_teams = all_teams

    print(f"═══ Team Defense Export ({season}) ═══")
    print(f"Teams to export: {len(target_teams)}")

    # Step 1: Fetch league-wide season averages by position
    print(f"\n─── Fetching league-wide averages by position ───")
    league_by_pos = {}
    for pos in POSITIONS:
        print(f"  {POSITION_LABELS[pos]} ({pos})...", end=' ')
        records = fetch_position_stats(pos, season, opponent_team_id=0)
        league_by_pos[pos] = records
        print(f"{len(records)} players")

    # Step 2: Fetch team context (ratings)
    print(f"\n─── Fetching team ratings ───")
    team_context_raw = get_team_context(season)
    print(f"  Got ratings for {len(team_context_raw)} teams")

    # Build name-to-abbreviation mapping (get_team_context keys may be full names)
    name_to_abbr = {}
    for t in all_teams:
        name_to_abbr[t['full_name']] = t['abbreviation']
        name_to_abbr[t['abbreviation']] = t['abbreviation']

    # Re-key team_context by abbreviation
    team_context = {}
    for key, val in team_context_raw.items():
        abbr = name_to_abbr.get(key, key)
        team_context[abbr] = val

    # Compute def rating ranks
    rated_teams = sorted(team_context.items(), key=lambda x: x[1].get('def_rating') or 999)
    def_rank_map = {}
    for i, (abbr, ctx) in enumerate(rated_teams):
        def_rank_map[abbr] = i + 1

    # Step 3: Fetch team defense profiles (contest + hustle)
    print(f"\n─── Fetching defensive profiles ───")
    defense_profiles = get_team_defense_profiles(season)
    print(f"  Got profiles for {len(defense_profiles)} teams")

    # Step 4: For each team, fetch opponent-filtered stats and compute deviations
    print(f"\n─── Computing position impact for {len(target_teams)} teams ───")
    all_team_data = {}

    for team in target_teams:
        abbr = team['abbreviation']
        team_id = team['id']
        team_name = team['full_name']
        print(f"\n  {abbr} ({team_name})")

        # Fetch opponent-filtered stats by position
        position_impact = {}
        for pos in POSITIONS:
            print(f"    {POSITION_LABELS[pos]}...", end=' ')
            vs_records = fetch_position_stats(pos, season, opponent_team_id=team_id)
            print(f"{len(vs_records)} players")

            result = compute_position_deviations(league_by_pos[pos], vs_records)
            if result:
                result['label'] = POSITION_LABELS[pos]
                position_impact[pos] = result
            else:
                position_impact[pos] = {
                    'label': POSITION_LABELS[pos],
                    'sample_size': {'total_player_games': 0, 'unique_players': 0},
                    'deviations': {},
                    'top_affected_players': [],
                }

        # Build scheme fingerprint
        scheme = {
            'synergy_defensive': [],
            'contest_profile': {},
            'hustle': {},
        }

        # Synergy defensive play types
        try:
            synergy = get_team_synergy_data(abbr, season)
            scheme['synergy_defensive'] = synergy.get('defensive', [])
        except Exception as e:
            print(f"    Synergy failed: {e}")

        # Contest profile + hustle from defense profiles
        profile = defense_profiles.get(abbr, {})
        scheme['contest_profile'] = profile.get('contest_profile', {})
        scheme['hustle'] = profile.get('hustle', {})

        # Ratings
        ctx = team_context.get(abbr, {})
        ratings = {
            'def_rating': ctx.get('def_rating'),
            'off_rating': ctx.get('off_rating'),
            'net_rating': ctx.get('net_rating'),
            'pace': ctx.get('pace'),
            'def_rating_rank': def_rank_map.get(abbr, 30),
        }

        team_data = export_team(abbr, team_id, team_name, position_impact, scheme, ratings, season)
        all_team_data[abbr] = team_data

    # Step 5: Compute rankings across all teams
    print(f"\n─── Computing rankings ───")
    if len(all_team_data) > 1:
        compute_all_team_rankings(all_team_data)
        print(f"  Ranked {len(all_team_data)} teams across {len(POSITIONS)} positions × {len(IMPACT_STATS)} stats")
    else:
        # Single team mode — still useful but no ranking
        print(f"  Single team mode — skipping cross-team ranking")
        for abbr, tdata in all_team_data.items():
            for pos in POSITIONS:
                pos_data = tdata.get('position_impact', {}).get(pos, {})
                for stat in IMPACT_STATS:
                    dev = pos_data.get('deviations', {}).get(stat)
                    if dev:
                        dev['rank'] = None
                        dev['pctile'] = None

    # Step 6: Generate insights and write files
    print(f"\n─── Writing JSON files ───")
    index_entries = []

    for abbr, team_data in sorted(all_team_data.items()):
        team_data['insights'] = generate_insights(team_data)
        size_kb = write_team_json(team_data, abbr)

        # Build headline for index
        headline_parts = []
        for pos in POSITIONS:
            pos_data = team_data.get('position_impact', {}).get(pos, {})
            pts = pos_data.get('deviations', {}).get('PTS', {})
            if pts.get('value', 0) < -1.0:
                rank = pts.get('rank', '')
                headline_parts.append(f"{POSITION_LABELS[pos]} PTS {pts['value']:+.1f} (#{rank})")
            reb = pos_data.get('deviations', {}).get('REB', {})
            if reb.get('value', 0) < -1.0:
                rank = reb.get('rank', '')
                headline_parts.append(f"{POSITION_LABELS[pos]} REB {reb['value']:+.1f} (#{rank})")

        index_entries.append({
            'abbreviation': abbr,
            'full_name': team_data['team']['full_name'],
            'id': team_data['team']['id'],
            'def_rating': team_data['ratings'].get('def_rating'),
            'def_rating_rank': team_data['ratings'].get('def_rating_rank'),
            'file': f'{abbr}.json',
            'headline': ' | '.join(headline_parts[:3]) if headline_parts else '',
            'file_size_kb': round(size_kb, 1),
        })

    write_team_index(index_entries, season)

    print(f"\n═══ Done! Exported {len(all_team_data)} teams ═══")


if __name__ == '__main__':
    main()
