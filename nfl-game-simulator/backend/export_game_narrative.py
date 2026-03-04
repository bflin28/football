"""
Export game narrative (play-by-play) data for top DAS games.
Pre-computes timestamped PBP, key moments, and scoring timelines
so the frontend can show them without live API calls.

Usage:
    python export_game_narrative.py                    # Top 15 games by DAS
    python export_game_narrative.py --top 20           # Top 20 games
    python export_game_narrative.py --game 0022500005 --player "Shai Gilgeous-Alexander"
"""

import sys
import io
import os
import json
import re
import time
import argparse
import unicodedata

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from nba_api.stats.endpoints import playbyplayv3
import numpy as np


def _safe_int(val):
    """Safely convert a value to int, returning None on failure."""
    if val is None or val == '' or (isinstance(val, float) and np.isnan(val)):
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
PLAYERS_DIR = os.path.join(DATA_DIR, 'players')
GAMES_DIR = os.path.join(DATA_DIR, 'games')
MANIFEST_PATH = os.path.join(DATA_DIR, 'manifest.json')
INDEX_PATH = os.path.join(DATA_DIR, 'game_index.json')


def slugify(name):
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


def parse_clock(clock_str):
    """Convert 'PT11M01.00S' to '11:01' and return (display_str, total_seconds)."""
    m = re.match(r'PT(\d+)M([\d.]+)S', clock_str or '')
    if not m:
        return '0:00', 0
    minutes = int(m.group(1))
    seconds = int(float(m.group(2)))
    return f'{minutes}:{seconds:02d}', minutes * 60 + seconds


def get_top_das_games(top_n=15):
    """Read all player JSONs and return top N games by DAS."""
    if not os.path.isfile(MANIFEST_PATH):
        print('  No manifest.json found')
        return []

    with open(MANIFEST_PATH, 'r') as f:
        manifest = json.load(f)

    all_games = []
    for player_entry in manifest.get('players', []):
        slug = player_entry['slug']
        player_path = os.path.join(PLAYERS_DIR, f'{slug}.json')
        if not os.path.isfile(player_path):
            continue

        with open(player_path, 'r') as f:
            data = json.load(f)

        player_info = data.get('player', {})
        player_name = player_info.get('full_name') or player_info.get('name', slug)
        player_id = player_info.get('id')

        for game in data.get('das', {}).get('per_game', []):
            das = game.get('das')
            if das is None:
                continue
            all_games.append({
                'game_id': game['game_id'],
                'player_name': player_name,
                'player_id': player_id,
                'player_slug': slug,
                'das': das,
                'game_meta': game,
            })

    all_games.sort(key=lambda g: g['das'], reverse=True)
    return all_games[:top_n]


def detect_key_moments(actions, is_home):
    """Flag key moments in the player's action list."""
    key_moments = []
    scoring = [a for a in actions if a['points'] > 0]

    # 1. Scoring bursts: 6+ points in under 2 minutes same period
    seen_bursts = set()
    for i, start in enumerate(scoring):
        burst_pts = start['points']
        burst_end_idx = start['idx']
        for j in range(i + 1, len(scoring)):
            nxt = scoring[j]
            if nxt['period'] != start['period']:
                break
            time_diff = start['clock_seconds'] - nxt['clock_seconds']
            if time_diff > 120:
                break
            burst_pts += nxt['points']
            burst_end_idx = nxt['idx']
        if burst_pts >= 6 and burst_end_idx != start['idx']:
            burst_key = (start['idx'], burst_end_idx)
            if burst_key not in seen_bursts:
                seen_bursts.add(burst_key)
                time_diff = start['clock_seconds'] - actions[burst_end_idx]['clock_seconds'] if burst_end_idx < len(actions) else 0
                key_moments.append({
                    'type': 'scoring_burst',
                    'action_index': start['idx'],
                    'end_index': burst_end_idx,
                    'label': f'{burst_pts}-pt burst',
                    'description': f'{burst_pts} points in {abs(time_diff)}s span',
                })

    # 2. Clutch plays: scoring in last 2 min of Q4 or any OT
    for a in scoring:
        is_clutch = (a['period'] == 4 and a['clock_seconds'] <= 120) or a['period'] > 4
        if is_clutch:
            key_moments.append({
                'type': 'clutch',
                'action_index': a['idx'],
                'label': 'Clutch',
            })

    # 3. Go-ahead baskets
    for a in actions:
        if a['points'] > 0 and a.get('went_ahead'):
            key_moments.append({
                'type': 'go_ahead',
                'action_index': a['idx'],
                'label': 'Go-ahead',
            })

    # 4. Three-pointers
    for a in actions:
        if a.get('shot_value') == 3 and a.get('made'):
            key_moments.append({
                'type': 'three_pointer',
                'action_index': a['idx'],
                'label': '3PT',
            })

    # 5. And-ones: made shot followed within 3 indices by FT 1 of 1
    for i, a in enumerate(actions):
        if a.get('made') and a['action_type'] == 'Made Shot':
            for j in range(i + 1, min(i + 4, len(actions))):
                nxt = actions[j]
                if nxt['action_type'] == 'Free Throw' and '1 of 1' in nxt.get('description', ''):
                    if 'MISS' not in nxt.get('description', ''):
                        key_moments.append({
                            'type': 'and_one',
                            'action_index': a['idx'],
                            'label': 'And-1',
                        })
                    break

    return key_moments


def compute_play_impact_scores(actions, key_moments, is_home):
    """Compute Play Impact Score (PIS) for each action.

    PIS = Base Value + Leverage + Difficulty + Moment Bonus

    Base: points scored (3PT=3, 2PT=2, FT=1, miss=0.3, steal/block=1.5, TO=-0.5)
    Leverage: closeness × time_factor (tight game late = max, blowout early = near zero)
    Difficulty: made shots only — distance bonus + shot type complexity bonus
    Moment: additive bonuses for clutch, go-ahead, and-1, scoring burst
    """
    # Build moment lookup: action idx → list of moment types
    moment_map = {}
    for km in key_moments:
        idx = km['action_index']
        if idx not in moment_map:
            moment_map[idx] = []
        moment_map[idx].append(km['type'])

    for action in actions:
        # ── Base Value ──
        atype = action['action_type']
        desc = (action.get('description') or '').upper()

        if atype == 'Made Shot':
            base = action.get('shot_value') or 2
        elif atype == 'Free Throw' and action.get('made'):
            base = 1.0
        elif atype == 'Free Throw' and not action.get('made'):
            base = 0.2
        elif atype == 'Missed Shot':
            base = 0.3
        elif 'STEAL' in desc:
            base = 1.5
        elif 'BLOCK' in desc:
            base = 1.5
        elif atype == 'Rebound':
            # Offensive rebound if Off count > 0 and follows a miss
            off_match = re.search(r'Off:(\d+)', action.get('description', ''))
            off_count = int(off_match.group(1)) if off_match else 0
            base = 1.0 if off_count > 0 else 0.3
        elif atype == 'Turnover':
            base = -0.5
        else:
            base = 0.0

        # ── Leverage (closeness × time_factor) ──
        if is_home:
            player_score = action['score_home']
            opp_score = action['score_away']
        else:
            player_score = action['score_away']
            opp_score = action['score_home']
        margin = abs(player_score - opp_score)

        if margin <= 3:
            closeness = 1.0
        elif margin <= 6:
            closeness = 0.7
        elif margin <= 10:
            closeness = 0.4
        elif margin <= 15:
            closeness = 0.15
        else:
            closeness = 0.05

        period = action['period']
        clock_s = action['clock_seconds']

        if period > 4:  # OT — every second is high leverage
            time_factor = 5.0 if clock_s <= 60 else (4.0 if clock_s <= 180 else 3.5)
        else:
            secs_left = clock_s + (4 - period) * 720
            if secs_left <= 120:
                time_factor = 5.0
            elif secs_left <= 300:
                time_factor = 3.5
            elif secs_left <= 720:
                time_factor = 2.5
            elif secs_left <= 1440:
                time_factor = 1.5
            else:
                time_factor = 1.0

        leverage = closeness * time_factor

        # ── Difficulty (made shots only) ──
        difficulty = 0.0
        if atype == 'Made Shot' and action.get('made'):
            dist = action.get('shot_distance') or 0
            if dist >= 25:
                difficulty += 1.0
            elif dist >= 20:
                difficulty += 0.7
            elif dist >= 15:
                difficulty += 0.5
            elif dist >= 10:
                difficulty += 0.3
            else:
                difficulty += 0.1

            sub = (action.get('sub_type') or '').lower()
            if any(w in sub for w in ('step back', 'fadeaway', 'turnaround')):
                difficulty += 1.0
            elif any(w in sub for w in ('pullup', 'driving', 'floating', 'running')):
                difficulty += 0.5
            elif 'dunk' in sub:
                difficulty += 0.3

        # ── Moment Bonus ──
        moment = 0.0
        for mt in moment_map.get(action['idx'], []):
            if mt == 'clutch':
                moment += 1.5
            elif mt == 'go_ahead':
                moment += 2.0
            elif mt == 'and_one':
                moment += 1.0
            elif mt == 'scoring_burst':
                moment += 0.5
            # three_pointer: no extra bonus (captured in base value)

        pis = round(max(base + leverage + difficulty + moment, 0), 1)
        action['pis'] = pis
        action['pis_components'] = {
            'base': round(base, 1),
            'leverage': round(leverage, 1),
            'difficulty': round(difficulty, 1),
            'moment': round(moment, 1),
        }


    # Compute scoring timeline by period
    by_period = {}
    for a in actions:
        p = a['period']
        if p not in by_period:
            by_period[p] = {'period': p, 'points': 0, 'fgm': 0, 'fga': 0, 'ftm': 0, 'fta': 0}
        if a['action_type'] == 'Made Shot':
            by_period[p]['fgm'] += 1
            by_period[p]['fga'] += 1
            by_period[p]['points'] += a['points']
        elif a['action_type'] == 'Missed Shot':
            by_period[p]['fga'] += 1
        elif a['action_type'] == 'Free Throw':
            by_period[p]['fta'] += 1
            if a['made']:
                by_period[p]['ftm'] += 1
                by_period[p]['points'] += 1

    scoring_timeline = []
    for p in sorted(by_period.keys()):
        entry = by_period[p]
        entry['label'] = f'Q{p}' if p <= 4 else f'OT{p - 4}'
        scoring_timeline.append(entry)

    # Build output
    components = game_meta.get('components', {})
    narrative = {
        'game_id': game_id,
        'player': {
            'name': player_name,
            'id': player_id,
            'slug': player_slug,
        },
        'game_info': {
            'date': game_meta.get('date', ''),
            'opponent': game_meta.get('opponent', ''),
            'is_home': is_home,
            'result': game_meta.get('result', ''),
            'final_score': {'home': final_home, 'away': final_away},
            'periods': max_period,
            'pts': game_meta.get('pts', 0),
            'reb': game_meta.get('reb', 0),
            'ast': game_meta.get('ast', 0),
            'minutes': game_meta.get('minutes', 0),
            'das': game_meta.get('das', 0),
            'das_components': components,
        },
        'actions': actions,
        'key_moments': key_moments,
        'scoring_timeline': {'by_period': scoring_timeline},
    }

    # Write file
    os.makedirs(GAMES_DIR, exist_ok=True)
    filename = f'{game_id}_{player_slug}.json'
    out_path = os.path.join(GAMES_DIR, filename)

    class SafeEncoder(json.JSONEncoder):
        def default(self, obj):
            import numpy as np
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                if np.isnan(obj) or np.isinf(obj):
                    return None
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, np.bool_):
                return bool(obj)
            return super().default(obj)

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(narrative, f, cls=SafeEncoder, ensure_ascii=False)

    file_size = os.path.getsize(out_path)
    action_count = len(actions)
    key_count = len(key_moments)
    print(f'    Written: {filename} ({file_size / 1024:.0f} KB, {action_count} actions, {key_count} key moments)')

    return {
        'game_id': game_id,
        'player_slug': player_slug,
        'player_name': player_name,
        'file': filename,
        'das': game_meta.get('das', 0),
    }


def update_game_index(entries):
    """Write data/game_index.json."""
    from datetime import datetime, timezone
    index = {
        'games': sorted(entries, key=lambda e: e['das'], reverse=True),
        'exported_at': datetime.now(timezone.utc).isoformat(),
    }
    with open(INDEX_PATH, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    print(f'\n  Game index updated: {len(entries)} games')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Export game narrative PBP data')
    parser.add_argument('--top', type=int, default=15, help='Number of top DAS games to export')
    parser.add_argument('--game', type=str, help='Specific game ID to export')
    parser.add_argument('--player', type=str, help='Player name (for --game)')
    args = parser.parse_args()

    print(f'\n{"=" * 60}')
    print(f'  NBA Factor Analysis — Game Narrative Export')
    print(f'{"=" * 60}')

    entries = []

    if args.game and args.player:
        # Export a specific game
        slug = slugify(args.player)
        player_path = os.path.join(PLAYERS_DIR, f'{slug}.json')
        if not os.path.isfile(player_path):
            print(f'  Player file not found: {slug}.json')
            sys.exit(1)
        with open(player_path, 'r') as f:
            data = json.load(f)
        player_info = data.get('player', {})
        player_id = player_info.get('id')
        player_name = player_info.get('full_name') or player_info.get('name')
        game_meta = None
        for g in data.get('das', {}).get('per_game', []):
            if g['game_id'] == args.game:
                game_meta = g
                break
        if not game_meta:
            print(f'  Game {args.game} not found for {args.player}')
            sys.exit(1)
        print(f'\n  Exporting: {player_name} — {game_meta.get("opponent")} ({game_meta.get("date")})')
        entry = export_game_narrative(args.game, player_id, slug, player_name, game_meta)
        if entry:
            entries.append(entry)
    else:
        # Export top N games by DAS
        games = get_top_das_games(args.top)
        print(f'\n  Exporting top {len(games)} games by DAS...\n')
        for i, g in enumerate(games):
            das = g['das']
            opp = g['game_meta'].get('opponent', '?')
            date = g['game_meta'].get('date', '?')
            pts = g['game_meta'].get('pts', '?')
            print(f'  [{i+1}/{len(games)}] {g["player_name"]} vs {opp} ({date}) — {pts} PTS, DAS: {das:.2f}')
            try:
                entry = export_game_narrative(
                    g['game_id'], g['player_id'], g['player_slug'],
                    g['player_name'], g['game_meta']
                )
                if entry:
                    entries.append(entry)
            except Exception as e:
                print(f'    FAILED: {e}')

    if entries:
        update_game_index(entries)

    print(f'\n{"=" * 60}')
    print(f'  Export complete! {len(entries)} game narratives exported.')
    print(f'  Files at: data/games/')
    print(f'{"=" * 60}\n')
