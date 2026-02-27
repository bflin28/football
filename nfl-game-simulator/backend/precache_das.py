"""
Pre-cache DAS results for top scoring players.
Runs directly against nba_analysis module — shares the same DiskCache.
Results are instantly available to the Flask app on next request.

Usage:
    python precache_das.py              # default: players 21-50 by PTS, 2025-26
    python precache_das.py --start 1 --count 50   # top 50
    python precache_das.py --stat REB   # top rebounders
"""

import sys
import io
import time
import argparse

# Fix Windows console encoding for Unicode player names
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from nba_analysis import (
    get_top_players_by_stat,
    run_das_analysis,
    DiskCache,
)

# The endpoint-level cache (same file the Flask app reads)
_nba_cache = DiskCache('nba_endpoints', write_every=1)


def precache(stat='PTS', season='2025-26', start=21, count=30, per_minute=False):
    total_needed = start + count - 1
    print(f"\n{'='*60}")
    print(f"  Pre-caching DAS for players {start}-{start+count-1}")
    print(f"  Stat: {stat}  Season: {season}  PerMin: {per_minute}")
    print(f"{'='*60}\n")

    # Fetch the full list of top players
    print(f"Fetching top {total_needed} {stat} leaders...")
    players = get_top_players_by_stat(stat, season, limit=total_needed)
    print(f"Got {len(players)} players\n")

    # Slice to the requested range (0-indexed)
    batch = players[start - 1 : start - 1 + count]

    cached = 0
    computed = 0
    failed = 0

    for i, p in enumerate(batch):
        name = p['player_name']
        rank = start + i
        cache_key = f'das|{name}|{stat}|{season}|pm={per_minute}'

        if cache_key in _nba_cache:
            print(f"  [{rank:2d}] {name:30s} — CACHED ✓")
            cached += 1
            continue

        print(f"  [{rank:2d}] {name:30s} — computing...", end='', flush=True)
        t0 = time.time()
        try:
            result = run_das_analysis(name, stat, season=season, per_minute=per_minute)
            _nba_cache[cache_key] = result
            elapsed = time.time() - t0
            games = result.get('das', {}).get('games_analyzed', '?')
            beta = result.get('das', {}).get('regression', {}).get('beta', '?')
            r2 = result.get('das', {}).get('regression', {}).get('r_squared', '?')
            print(f" done in {elapsed:.0f}s  (games={games}, β={beta}, R²={r2})")
            computed += 1
        except Exception as e:
            elapsed = time.time() - t0
            print(f" FAILED in {elapsed:.0f}s — {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"  Done! Cached: {cached}  Computed: {computed}  Failed: {failed}")
    print(f"  Total endpoint cache entries: {len(_nba_cache)}")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Pre-cache DAS for NBA players')
    parser.add_argument('--stat', default='PTS', help='Stat column (default: PTS)')
    parser.add_argument('--season', default='2025-26', help='NBA season (default: 2025-26)')
    parser.add_argument('--start', type=int, default=21, help='Starting rank (default: 21)')
    parser.add_argument('--count', type=int, default=30, help='Number of players (default: 30)')
    parser.add_argument('--per-minute', action='store_true', help='Use per-minute normalization')
    args = parser.parse_args()

    precache(
        stat=args.stat,
        season=args.season,
        start=args.start,
        count=args.count,
        per_minute=args.per_minute,
    )
