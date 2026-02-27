"""
Export player DAS analysis + shot charts to JSON files for deployment.
Pre-computes everything so the hosted version needs zero NBA API calls.

Usage:
    python export_player.py "Nikola Jokic" "Shai Gilgeous-Alexander"
    python export_player.py "LeBron James" --stat REB
    python export_player.py --all              # re-export all cached DAS results
"""

import sys
import io
import os
import json
import time
import argparse
import unicodedata

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from nba_analysis import (
    run_das_analysis,
    fetch_game_shot_chart,
    DiskCache,
)

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'players')
MANIFEST_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'manifest.json')

# Shared caches
_nba_cache = DiskCache('nba_endpoints', write_every=1)


def slugify(name):
    """Convert player name to URL-safe slug: 'Nikola Jokić' → 'nikola-jokic'"""
    # Strip diacritics
    normalized = ''.join(
        c for c in unicodedata.normalize('NFD', name)
        if unicodedata.category(c) != 'Mn'
    )
    # Lowercase, replace non-alphanumeric with hyphens, collapse multiples
    slug = ''
    for c in normalized.lower():
        if c.isalnum():
            slug += c
        elif slug and slug[-1] != '-':
            slug += '-'
    return slug.strip('-')


def export_player(player_name, stat='PTS', season='2025-26', per_minute=False):
    """Export a single player's DAS + all shot charts to JSON."""
    slug = slugify(player_name)
    out_path = os.path.join(DATA_DIR, f'{slug}.json')

    print(f'\n  Exporting {player_name} → {slug}.json')

    # ── Step 1: Get DAS analysis ──
    cache_key = f'das|{player_name}|{stat}|{season}|pm={per_minute}'
    if cache_key in _nba_cache:
        print(f'    DAS: from cache')
        das_result = _nba_cache[cache_key]
    else:
        print(f'    DAS: computing fresh...')
        das_result = run_das_analysis(player_name, stat, season=season, per_minute=per_minute)
        _nba_cache[cache_key] = das_result

    player_info = das_result.get('player', {})
    player_id = player_info.get('id')
    das_data = das_result.get('das', {})
    per_game = das_data.get('per_game', [])
    print(f'    DAS: {len(per_game)} games, β={das_data.get("regression", {}).get("beta", "?"):.2f}')

    # ── Step 2: Fetch all shot charts ──
    shot_charts = {}
    cached_sc = 0
    fetched_sc = 0
    failed_sc = 0

    for i, game in enumerate(per_game):
        game_id = game.get('game_id', '')
        team_id = game.get('team_id', '')
        if not game_id or not player_id:
            continue

        sc_cache_key = f'shot_chart|{game_id}|{player_id}'

        # Check endpoint cache
        if sc_cache_key in _nba_cache:
            shot_charts[game_id] = _nba_cache[sc_cache_key]
            cached_sc += 1
            continue

        # Fetch fresh
        try:
            time.sleep(0.3)  # Rate limit
            result = fetch_game_shot_chart(game_id, int(player_id), int(team_id))
            shot_charts[game_id] = result
            _nba_cache[sc_cache_key] = result
            fetched_sc += 1
            if (fetched_sc % 5 == 0):
                print(f'    Shot charts: {cached_sc + fetched_sc}/{len(per_game)} ({fetched_sc} fetched)...')
        except Exception as e:
            print(f'    Shot chart FAILED for {game_id}: {e}')
            failed_sc += 1

    print(f'    Shot charts: {cached_sc} cached, {fetched_sc} fetched, {failed_sc} failed')

    # ── Step 3: Build export JSON ──
    export_data = {
        'player': player_info,
        'stat': stat,
        'season': season,
        'per_minute': per_minute,
        'das': das_data,
        'shot_charts': shot_charts,
    }

    # Ensure output directory exists
    os.makedirs(DATA_DIR, exist_ok=True)

    # Write JSON (handle NaN/Infinity which aren't valid JSON)
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
        json.dump(export_data, f, cls=SafeEncoder, ensure_ascii=False)

    file_size = os.path.getsize(out_path)
    print(f'    Written: {file_size / 1024:.0f} KB')

    return {
        'name': player_info.get('name', player_name),
        'slug': slug,
        'id': player_id,
        'stat': stat,
        'season': season,
        'games': len(per_game),
        'file_size_kb': round(file_size / 1024),
    }


def update_manifest(player_entries):
    """Update data/manifest.json with exported players."""
    from datetime import datetime, timezone

    # Load existing manifest
    existing = []
    if os.path.isfile(MANIFEST_PATH):
        with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            existing = data.get('players', [])

    # Merge: update existing entries, add new ones
    by_slug = {p['slug']: p for p in existing}
    for entry in player_entries:
        by_slug[entry['slug']] = entry

    manifest = {
        'players': sorted(by_slug.values(), key=lambda p: p['name']),
        'exported_at': datetime.now(timezone.utc).isoformat(),
    }

    with open(MANIFEST_PATH, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f'\n  Manifest updated: {len(manifest["players"])} players')


def export_all_cached(stat='PTS', season='2025-26'):
    """Re-export all players that have cached DAS results."""
    entries = []
    for key in _nba_cache._cache:
        if key.startswith(f'das|') and f'|{stat}|{season}|' in key:
            parts = key.split('|')
            player_name = parts[1]
            try:
                entry = export_player(player_name, stat=stat, season=season)
                entries.append(entry)
            except Exception as e:
                print(f'    FAILED: {player_name} — {e}')
    return entries


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Export player data to JSON for deployment')
    parser.add_argument('players', nargs='*', help='Player names to export')
    parser.add_argument('--stat', default='PTS', help='Stat column (default: PTS)')
    parser.add_argument('--season', default='2025-26', help='NBA season (default: 2025-26)')
    parser.add_argument('--all', action='store_true', help='Re-export all cached DAS results')
    parser.add_argument('--per-minute', action='store_true', help='Use per-minute normalization')
    args = parser.parse_args()

    print(f'\n{"=" * 60}')
    print(f'  NBA Factor Analysis — Data Export')
    print(f'  Stat: {args.stat}  Season: {args.season}')
    print(f'{"=" * 60}')

    entries = []

    if args.all:
        print(f'\n  Re-exporting all cached players...')
        entries = export_all_cached(stat=args.stat, season=args.season)
    elif args.players:
        for name in args.players:
            try:
                entry = export_player(name, stat=args.stat, season=args.season, per_minute=args.per_minute)
                entries.append(entry)
            except Exception as e:
                print(f'\n  FAILED: {name} — {e}')
    else:
        print('\n  No players specified. Use: python export_player.py "Player Name" [...]')
        print('  Or: python export_player.py --all')
        sys.exit(1)

    if entries:
        update_manifest(entries)

    print(f'\n{"=" * 60}')
    print(f'  Export complete! {len(entries)} players exported.')
    total_kb = sum(e.get('file_size_kb', 0) for e in entries)
    print(f'  Total data size: {total_kb} KB ({total_kb / 1024:.1f} MB)')
    print(f'  Files at: data/players/')
    print(f'{"=" * 60}\n')
