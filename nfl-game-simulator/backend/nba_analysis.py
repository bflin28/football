"""
NBA Player Stat Z-Score Analysis Module

Fetches player game logs, calculates z-scores, runs distribution tests,
and identifies factors that drive stat variance (opponent, home/away, rest, etc.)
"""

import time
import os
import pickle
import threading
import numpy as np
import pandas as pd
from math import floor
from scipy import stats as scipy_stats
from scipy.stats import poisson
import re
from nba_api.stats.endpoints import (
    playergamelog, leaguedashteamstats, synergyplaytypes, playbyplayv3,
    boxscoreadvancedv3, boxscoreplayertrackv3, gamerotation, shotchartdetail,
    leaguedashplayerstats, boxscorematchupsv3,
    leaguedashptteamdefend, leaguehustlestatsteam, boxscorehustlev2
)
from nba_api.stats.static import players, teams as nba_teams


# ── Persistent Disk Cache ────────────────────────────────────────────────
_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.cache')
os.makedirs(_CACHE_DIR, exist_ok=True)


class DiskCache:
    """Dict-like cache that persists to a pickle file on disk.

    - Loads from disk on init
    - Auto-reloads when another process updates the file (mtime check)
    - Merges disk data on reload so no entries are lost
    - Thread-safe writes via lock
    - Survives server restarts
    """

    def __init__(self, name, write_every=3):
        self._path = os.path.join(_CACHE_DIR, f'{name}.pkl')
        self._lock = threading.Lock()
        self._data = {}
        self._dirty_count = 0
        self._write_every = write_every
        self._last_mtime = 0
        self._load()

    def _load(self):
        if os.path.exists(self._path):
            try:
                self._last_mtime = os.path.getmtime(self._path)
                with open(self._path, 'rb') as f:
                    self._data = pickle.load(f)
                print(f"[Cache] Loaded {len(self._data)} entries from {self._path}")
            except Exception as e:
                print(f"[Cache] Failed to load {self._path}: {e}")
                self._data = {}

    def _check_disk(self):
        """Reload from disk if another process has updated the file."""
        try:
            if not os.path.exists(self._path):
                return
            mtime = os.path.getmtime(self._path)
            if mtime > self._last_mtime:
                with open(self._path, 'rb') as f:
                    disk_data = pickle.load(f)
                # Merge: disk entries fill gaps, our in-memory entries take priority
                merged = {**disk_data, **self._data}
                new_keys = len(merged) - len(self._data)
                if new_keys > 0:
                    print(f"[Cache] Hot-reload: +{new_keys} entries from disk ({self._path})")
                self._data = merged
                self._last_mtime = mtime
        except Exception:
            pass  # Non-critical — worst case we recompute

    def _save(self):
        with self._lock:
            try:
                # Merge with disk before saving to avoid clobbering another process's writes
                if os.path.exists(self._path):
                    try:
                        with open(self._path, 'rb') as f:
                            disk_data = pickle.load(f)
                        self._data = {**disk_data, **self._data}
                    except Exception:
                        pass
                tmp = self._path + '.tmp'
                with open(tmp, 'wb') as f:
                    pickle.dump(self._data, f)
                os.replace(tmp, self._path)
                self._last_mtime = os.path.getmtime(self._path)
            except Exception as e:
                print(f"[Cache] Save failed: {e}")

    def __contains__(self, key):
        if key in self._data:
            return True
        # Key not in memory — check if disk has newer data
        self._check_disk()
        return key in self._data

    def __getitem__(self, key):
        if key not in self._data:
            self._check_disk()
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value
        self._dirty_count += 1
        if self._dirty_count >= self._write_every:
            self._save()
            self._dirty_count = 0

    def get(self, key, default=None):
        if key not in self._data:
            self._check_disk()
        return self._data.get(key, default)

    def flush(self):
        """Force save to disk."""
        if self._dirty_count > 0:
            self._save()
            self._dirty_count = 0

    def clear(self):
        self._data = {}
        self._dirty_count = 0
        self._save()

    def __len__(self):
        return len(self._data)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _strip_diacritics(s):
    """Remove diacritical marks (accents) for search matching."""
    import unicodedata
    return ''.join(
        c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn'
    ).lower()


def find_player(name):
    """Find an NBA player by name (diacritics-insensitive)."""
    results = players.find_players_by_full_name(name)
    if not results:
        # Try partial match with diacritics stripping
        name_norm = _strip_diacritics(name)
        all_players = players.get_active_players()
        results = [p for p in all_players if name_norm in _strip_diacritics(p['full_name'])]
    if not results:
        raise ValueError(f"Player '{name}' not found")
    return results[0]


def get_player_game_logs(player_id, season='2024-25', season_type='Regular Season'):
    """Fetch game logs for a player/season from stats.nba.com."""
    time.sleep(0.4)  # respect rate limits
    log = playergamelog.PlayerGameLog(
        player_id=player_id,
        season=season,
        season_type_all_star=season_type,
        timeout=30
    )
    df = log.get_data_frames()[0]
    return df


def get_team_defensive_ratings(season='2024-25'):
    """Fetch team defensive stats for opponent analysis."""
    time.sleep(0.4)
    defense = leaguedashteamstats.LeagueDashTeamStats(
        season=season,
        measure_type_detailed_defense='Base',
        timeout=30
    )
    df = defense.get_data_frames()[0]
    return df


def get_team_context(season='2024-25'):
    """
    Fetch all teams' pace, offensive/defensive ratings in a single API call.
    Returns dict keyed by team abbreviation.
    """
    time.sleep(0.4)
    stats = leaguedashteamstats.LeagueDashTeamStats(
        season=season,
        measure_type_detailed_defense='Advanced',
        timeout=30,
    )
    df = stats.get_data_frames()[0]
    context = {}
    for _, row in df.iterrows():
        abbr = row.get('TEAM_ABBREVIATION', row.get('TEAM_NAME', ''))
        context[abbr] = {
            'pace': _safe_float(row.get('PACE')),
            'off_rating': _safe_float(row.get('OFF_RATING')),
            'def_rating': _safe_float(row.get('DEF_RATING')),
            'net_rating': _safe_float(row.get('NET_RATING')),
        }
    return context


def enrich_with_opponent_context(df, team_context):
    """
    Add opponent pace and defensive rating to each game row.
    team_context is the dict returned by get_team_context().
    """
    df = df.copy()
    df['opp_pace'] = df['opponent'].map(
        lambda opp: team_context.get(opp, {}).get('pace')
    ).astype(float)
    df['opp_def_rating'] = df['opponent'].map(
        lambda opp: team_context.get(opp, {}).get('def_rating')
    ).astype(float)
    df['opp_off_rating'] = df['opponent'].map(
        lambda opp: team_context.get(opp, {}).get('off_rating')
    ).astype(float)
    df['opp_net_rating'] = df['opponent'].map(
        lambda opp: team_context.get(opp, {}).get('net_rating')
    ).astype(float)
    return df


# ── Core Analysis ────────────────────────────────────────────────────────────

def compute_z_scores(values):
    """Calculate z-scores for an array of values."""
    arr = np.array(values, dtype=float)
    mean = np.nanmean(arr)
    std = np.nanstd(arr, ddof=1)
    if std == 0:
        return np.zeros_like(arr), mean, std
    z = (arr - mean) / std
    return z, mean, std


def test_distribution(values):
    """
    Run multiple normality tests on a stat distribution.
    Returns dict with test results and interpretation.
    """
    arr = np.array(values, dtype=float)
    arr = arr[~np.isnan(arr)]

    results = {}

    # Shapiro-Wilk (best for n < 5000)
    if len(arr) >= 3:
        stat, p = scipy_stats.shapiro(arr)
        results['shapiro_wilk'] = {
            'statistic': float(stat),
            'p_value': float(p),
            'normal': bool(p > 0.05),
            'interpretation': 'Normally distributed' if p > 0.05 else 'NOT normally distributed'
        }

    # D'Agostino-Pearson (tests skewness + kurtosis)
    if len(arr) >= 20:
        stat, p = scipy_stats.normaltest(arr)
        results['dagostino'] = {
            'statistic': float(stat),
            'p_value': float(p),
            'normal': bool(p > 0.05),
            'interpretation': 'Normally distributed' if p > 0.05 else 'NOT normally distributed'
        }

    # Anderson-Darling
    if len(arr) >= 8:
        try:
            ad_result = scipy_stats.anderson(arr, dist='norm', method='interpolate')
            p_val = float(ad_result.pvalue) if hasattr(ad_result, 'pvalue') else None
            is_normal = p_val > 0.05 if p_val is not None else True
            results['anderson_darling'] = {
                'statistic': float(ad_result.statistic),
                'critical_value_5pct': 0.0,
                'p_value': p_val,
                'normal': bool(is_normal),
                'interpretation': 'Normally distributed' if is_normal
                                  else 'NOT normally distributed'
            }
        except TypeError:
            # Older scipy without method parameter
            ad_result = scipy_stats.anderson(arr, dist='norm')
            sig_level = ad_result.significance_level[2] if len(ad_result.significance_level) > 2 else 5.0
            critical = ad_result.critical_values[2] if len(ad_result.critical_values) > 2 else 0
            results['anderson_darling'] = {
                'statistic': float(ad_result.statistic),
                'critical_value_5pct': float(critical),
                'normal': bool(ad_result.statistic < critical),
                'interpretation': 'Normally distributed' if ad_result.statistic < critical
                                  else 'NOT normally distributed'
            }

    # Skewness and Kurtosis
    skew = float(scipy_stats.skew(arr))
    kurt = float(scipy_stats.kurtosis(arr))
    results['shape'] = {
        'skewness': skew,
        'kurtosis': kurt,
        'skew_interpretation': (
            'Roughly symmetric' if abs(skew) < 0.5
            else 'Moderately skewed' if abs(skew) < 1
            else 'Highly skewed'
        ),
        'kurtosis_interpretation': (
            'Normal tails (mesokurtic)' if abs(kurt) < 1
            else 'Heavy tails (leptokurtic)' if kurt > 1
            else 'Light tails (platykurtic)'
        )
    }

    return results


def build_game_features(game_logs_df):
    """
    Enrich game log DataFrame with features for factor analysis:
    - home/away, opponent
    - rest days, back-to-back
    - game result, point differential
    - blowout category, usage proxy, shooting efficiency
    - rolling averages (momentum)
    """
    df = game_logs_df.copy()

    # Preserve Game_ID for PBP linking
    if 'Game_ID' in df.columns:
        df['game_id'] = df['Game_ID']

    # Parse matchup for home/away and opponent
    df['is_home'] = ~df['MATCHUP'].str.contains('@')
    df['opponent'] = df['MATCHUP'].apply(
        lambda x: x.split('vs.')[-1].strip() if 'vs.' in x else x.split('@')[-1].strip()
    )

    # Parse game date
    df['game_date'] = pd.to_datetime(df['GAME_DATE'])
    df = df.sort_values('game_date').reset_index(drop=True)

    # Rest days (days since last game)
    df['rest_days'] = df['game_date'].diff().dt.days.fillna(3)
    df['is_back_to_back'] = (df['rest_days'] <= 1)

    # Game result and point differential
    df['win'] = df['WL'] == 'W'
    df['point_diff'] = df['PLUS_MINUS']

    # Season game number
    df['game_number'] = range(1, len(df) + 1)

    # ── New derived features ──────────────────────────────────────────────

    # Blowout category based on final margin
    abs_margin = df['PLUS_MINUS'].abs()
    df['blowout_category'] = pd.cut(
        abs_margin, bins=[-1, 5, 15, 200],
        labels=['close', 'moderate', 'blowout']
    )

    # Minutes as float for calculations
    df['minutes_float'] = df['MIN'].apply(_parse_minutes)

    # Usage proxy: FGA per minute (how involved is the player offensively)
    if 'FGA' in df.columns:
        df['fga_per_min'] = df['FGA'] / df['minutes_float'].replace(0, np.nan)

    # Per-game shooting efficiency
    if 'FG_PCT' in df.columns:
        df['fg_pct_game'] = df['FG_PCT']

    return df


def analyze_factors(df, stat_col):
    """
    Analyze what factors correlate with a given stat.
    Returns dict of factor analyses with effect sizes.
    """
    factors = {}
    stat_values = df[stat_col].values

    # 1. Home vs Away
    home_vals = df[df['is_home']][stat_col].values
    away_vals = df[~df['is_home']][stat_col].values
    if len(home_vals) >= 2 and len(away_vals) >= 2:
        t_stat, p_val = scipy_stats.ttest_ind(home_vals, away_vals)
        cohens_d = (np.mean(home_vals) - np.mean(away_vals)) / np.sqrt(
            ((len(home_vals) - 1) * np.var(home_vals, ddof=1) +
             (len(away_vals) - 1) * np.var(away_vals, ddof=1)) /
            (len(home_vals) + len(away_vals) - 2)
        ) if np.var(home_vals, ddof=1) + np.var(away_vals, ddof=1) > 0 else 0
        factors['home_away'] = {
            'home_mean': float(np.mean(home_vals)),
            'away_mean': float(np.mean(away_vals)),
            'home_std': float(np.std(home_vals, ddof=1)),
            'away_std': float(np.std(away_vals, ddof=1)),
            'home_n': int(len(home_vals)),
            'away_n': int(len(away_vals)),
            't_statistic': float(t_stat),
            'p_value': float(p_val),
            'significant': bool(p_val < 0.05),
            'cohens_d': float(cohens_d),
            'effect_size': (
                'Negligible' if abs(cohens_d) < 0.2
                else 'Small' if abs(cohens_d) < 0.5
                else 'Medium' if abs(cohens_d) < 0.8
                else 'Large'
            )
        }

    # 2. Rest days correlation
    if 'rest_days' in df.columns:
        rest = df['rest_days'].values
        mask = ~np.isnan(rest) & ~np.isnan(stat_values)
        if mask.sum() >= 3:
            r, p = scipy_stats.pearsonr(rest[mask], stat_values[mask])
            factors['rest_days'] = {
                'correlation': float(r),
                'p_value': float(p),
                'significant': bool(p < 0.05),
                'interpretation': (
                    f"{'Positive' if r > 0 else 'Negative'} correlation "
                    f"({'strong' if abs(r) > 0.5 else 'moderate' if abs(r) > 0.3 else 'weak'})"
                )
            }

    # 3. Back-to-back effect
    if 'is_back_to_back' in df.columns:
        b2b_vals = df[df['is_back_to_back']][stat_col].values
        rest_vals = df[~df['is_back_to_back']][stat_col].values
        if len(b2b_vals) >= 2 and len(rest_vals) >= 2:
            t_stat, p_val = scipy_stats.ttest_ind(b2b_vals, rest_vals)
            factors['back_to_back'] = {
                'b2b_mean': float(np.mean(b2b_vals)),
                'rested_mean': float(np.mean(rest_vals)),
                'b2b_n': int(len(b2b_vals)),
                'rested_n': int(len(rest_vals)),
                't_statistic': float(t_stat),
                'p_value': float(p_val),
                'significant': bool(p_val < 0.05)
            }

    # 4. Minutes played correlation
    if 'MIN' in df.columns:
        # MIN might be a string like "34:20", convert to float minutes
        min_vals = df['MIN'].apply(_parse_minutes).values
        mask = ~np.isnan(min_vals) & ~np.isnan(stat_values)
        if mask.sum() >= 3:
            r, p = scipy_stats.pearsonr(min_vals[mask], stat_values[mask])
            factors['minutes'] = {
                'correlation': float(r),
                'p_value': float(p),
                'significant': bool(p < 0.05),
                'interpretation': (
                    f"{'Positive' if r > 0 else 'Negative'} correlation "
                    f"({'strong' if abs(r) > 0.5 else 'moderate' if abs(r) > 0.3 else 'weak'})"
                )
            }

    # 5. Win/Loss effect
    if 'win' in df.columns:
        win_vals = df[df['win']][stat_col].values
        loss_vals = df[~df['win']][stat_col].values
        if len(win_vals) >= 2 and len(loss_vals) >= 2:
            t_stat, p_val = scipy_stats.ttest_ind(win_vals, loss_vals)
            factors['win_loss'] = {
                'win_mean': float(np.mean(win_vals)),
                'loss_mean': float(np.mean(loss_vals)),
                'win_n': int(len(win_vals)),
                'loss_n': int(len(loss_vals)),
                't_statistic': float(t_stat),
                'p_value': float(p_val),
                'significant': bool(p_val < 0.05)
            }

    # 6. Point differential correlation
    if 'point_diff' in df.columns:
        pd_vals = df['point_diff'].values.astype(float)
        mask = ~np.isnan(pd_vals) & ~np.isnan(stat_values)
        if mask.sum() >= 3:
            r, p = scipy_stats.pearsonr(pd_vals[mask], stat_values[mask])
            factors['point_differential'] = {
                'correlation': float(r),
                'p_value': float(p),
                'significant': bool(p < 0.05),
                'interpretation': (
                    f"{'Positive' if r > 0 else 'Negative'} correlation "
                    f"({'strong' if abs(r) > 0.5 else 'moderate' if abs(r) > 0.3 else 'weak'})"
                )
            }

    # 7. Game number (fatigue/trend over season)
    if 'game_number' in df.columns:
        gn = df['game_number'].values.astype(float)
        mask = ~np.isnan(gn) & ~np.isnan(stat_values)
        if mask.sum() >= 3:
            r, p = scipy_stats.pearsonr(gn[mask], stat_values[mask])
            factors['season_trend'] = {
                'correlation': float(r),
                'p_value': float(p),
                'significant': bool(p < 0.05),
                'interpretation': (
                    f"{'Increasing' if r > 0 else 'Decreasing'} trend over season "
                    f"({'strong' if abs(r) > 0.5 else 'moderate' if abs(r) > 0.3 else 'weak'})"
                )
            }

    # 8. Per-opponent breakdown
    opp_groups = df.groupby('opponent')[stat_col]
    opp_stats = opp_groups.agg(['mean', 'std', 'count']).reset_index()
    opp_stats.columns = ['opponent', 'mean', 'std', 'games']
    opp_stats = opp_stats[opp_stats['games'] >= 1].sort_values('mean', ascending=False)

    # ANOVA across opponents (if enough groups)
    opp_groups_list = [g[stat_col].values for _, g in df.groupby('opponent') if len(g) >= 2]
    if len(opp_groups_list) >= 2:
        f_stat, p_val = scipy_stats.f_oneway(*opp_groups_list)
        factors['opponent_effect'] = {
            'f_statistic': float(f_stat),
            'p_value': float(p_val),
            'significant': bool(p_val < 0.05),
            'interpretation': (
                'Significant difference across opponents'
                if p_val < 0.05 else 'No significant difference across opponents'
            ),
            'breakdown': [
                {
                    'opponent': row['opponent'],
                    'mean': float(row['mean']),
                    'std': float(row['std']) if not np.isnan(row['std']) else 0,
                    'games': int(row['games'])
                }
                for _, row in opp_stats.iterrows()
            ]
        }

    # 9. Blowout effect (close vs moderate vs blowout)
    if 'blowout_category' in df.columns:
        groups = {}
        for cat in ['close', 'moderate', 'blowout']:
            vals = df[df['blowout_category'] == cat][stat_col].values
            if len(vals) >= 1:
                groups[cat] = vals
        if len(groups) >= 2:
            group_lists = list(groups.values())
            if all(len(g) >= 2 for g in group_lists):
                f_stat, p_val = scipy_stats.f_oneway(*group_lists)
            else:
                f_stat, p_val = 0.0, 1.0
            factors['blowout_effect'] = {
                'close_mean': float(np.mean(groups['close'])) if 'close' in groups else None,
                'close_n': int(len(groups.get('close', []))),
                'moderate_mean': float(np.mean(groups['moderate'])) if 'moderate' in groups else None,
                'moderate_n': int(len(groups.get('moderate', []))),
                'blowout_mean': float(np.mean(groups['blowout'])) if 'blowout' in groups else None,
                'blowout_n': int(len(groups.get('blowout', []))),
                'f_statistic': float(f_stat),
                'p_value': float(p_val),
                'significant': bool(p_val < 0.05),
                'interpretation': (
                    'Significant difference by game margin'
                    if p_val < 0.05 else 'No significant effect of game margin'
                ),
            }

    # 10. Usage rate correlation (FGA per minute)
    if 'fga_per_min' in df.columns:
        usage = df['fga_per_min'].values
        mask = ~np.isnan(usage) & ~np.isnan(stat_values)
        if mask.sum() >= 3:
            r, p = scipy_stats.pearsonr(usage[mask], stat_values[mask])
            factors['usage_rate'] = {
                'correlation': float(r),
                'p_value': float(p),
                'significant': bool(p < 0.05),
                'mean_fga_per_min': float(np.nanmean(usage)),
                'interpretation': (
                    f"{'Positive' if r > 0 else 'Negative'} correlation with usage "
                    f"({'strong' if abs(r) > 0.5 else 'moderate' if abs(r) > 0.3 else 'weak'})"
                )
            }

    # 11. Opponent pace correlation
    if 'opp_pace' in df.columns:
        pace = df['opp_pace'].values
        mask = ~np.isnan(pace) & ~np.isnan(stat_values)
        if mask.sum() >= 3:
            r, p = scipy_stats.pearsonr(pace[mask], stat_values[mask])
            factors['opponent_pace'] = {
                'correlation': float(r),
                'p_value': float(p),
                'significant': bool(p < 0.05),
                'interpretation': (
                    f"{'Higher' if r > 0 else 'Lower'} {stat_col} vs faster-paced opponents "
                    f"({'strong' if abs(r) > 0.5 else 'moderate' if abs(r) > 0.3 else 'weak'})"
                )
            }

    # 12. Opponent defensive rating correlation
    if 'opp_def_rating' in df.columns:
        def_rtg = df['opp_def_rating'].values
        mask = ~np.isnan(def_rtg) & ~np.isnan(stat_values)
        if mask.sum() >= 3:
            r, p = scipy_stats.pearsonr(def_rtg[mask], stat_values[mask])
            factors['opponent_defense'] = {
                'correlation': float(r),
                'p_value': float(p),
                'significant': bool(p < 0.05),
                'interpretation': (
                    f"{'Higher' if r > 0 else 'Lower'} {stat_col} vs weaker defenses "
                    f"({'strong' if abs(r) > 0.5 else 'moderate' if abs(r) > 0.3 else 'weak'}). "
                    f"Higher DEF_RATING = worse defense."
                )
            }

    # 13. Hot/cold streaks (5-game rolling average trend)
    if len(stat_values) >= 10:
        rolling_5 = pd.Series(stat_values).rolling(5, min_periods=5).mean().values
        # Correlate rolling avg with raw value to see if momentum matters
        mask = ~np.isnan(rolling_5) & ~np.isnan(stat_values)
        if mask.sum() >= 5:
            # Compare: do games after hot streaks stay hot?
            # Use shifted rolling avg (previous 5 games) vs current game
            prev_rolling = pd.Series(stat_values).rolling(5, min_periods=5).mean().shift(1).values
            mask = ~np.isnan(prev_rolling) & ~np.isnan(stat_values)
            if mask.sum() >= 5:
                r, p = scipy_stats.pearsonr(prev_rolling[mask], stat_values[mask])
                factors['momentum'] = {
                    'correlation': float(r),
                    'p_value': float(p),
                    'significant': bool(p < 0.05),
                    'interpretation': (
                        f"{'Hot streaks carry over' if r > 0.3 else 'Cold streaks carry over' if r < -0.3 else 'No momentum effect'} "
                        f"(r={r:.3f}). Previous 5-game avg {'predicts' if p < 0.05 else 'does NOT predict'} next game."
                    )
                }

    # 14. Shooting efficiency effect (FG% correlation with the stat)
    if 'fg_pct_game' in df.columns and stat_col not in ('FG_PCT', 'FG3_PCT', 'FT_PCT'):
        fg_pct = df['fg_pct_game'].values.astype(float)
        mask = ~np.isnan(fg_pct) & ~np.isnan(stat_values)
        if mask.sum() >= 3:
            r, p = scipy_stats.pearsonr(fg_pct[mask], stat_values[mask])
            factors['shooting_efficiency'] = {
                'correlation': float(r),
                'p_value': float(p),
                'significant': bool(p < 0.05),
                'interpretation': (
                    f"{'Positive' if r > 0 else 'Negative'} relationship with FG% "
                    f"({'strong' if abs(r) > 0.5 else 'moderate' if abs(r) > 0.3 else 'weak'})"
                )
            }

    return factors


def _parse_minutes(val):
    """Parse minutes string like '34:20' or int to float minutes."""
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float)):
        return float(val)
    try:
        parts = str(val).split(':')
        return float(parts[0]) + float(parts[1]) / 60 if len(parts) == 2 else float(parts[0])
    except (ValueError, IndexError):
        return np.nan


# ── Synergy Play Type Analysis ───────────────────────────────────────────────

PLAY_TYPES = [
    'Transition', 'Isolation', 'PRBallHandler', 'PRRollman',
    'Postup', 'Spotup', 'Handoff', 'Cut', 'OffScreen', 'OffRebound', 'Misc',
]

PLAY_TYPE_LABELS = {
    'Transition': 'Transition',
    'Isolation': 'Isolation',
    'PRBallHandler': 'Pick & Roll (Ball Handler)',
    'PRRollman': 'Pick & Roll (Roll Man)',
    'PRRollMan': 'Pick & Roll (Roll Man)',
    'Postup': 'Post Up',
    'Spotup': 'Spot Up',
    'Handoff': 'Handoff',
    'Cut': 'Cut',
    'OffScreen': 'Off Screen',
    'OffRebound': 'Putbacks',
    'Misc': 'Misc',
}


_synergy_cache = {}  # In-memory cache for synergy bulk fetches (keyed per session)


def _fetch_all_synergy(scope, season, grouping, play_type):
    """Fetch one play type for all players/teams. Uses cache to avoid re-fetching."""
    cache_key = f'synergy_bulk|{scope}|{season}|{grouping}|{play_type}'
    if cache_key in _synergy_cache:
        return _synergy_cache[cache_key]

    time.sleep(0.4)
    data = synergyplaytypes.SynergyPlayTypes(
        player_or_team_abbreviation=scope,  # 'P' or 'T'
        season=season,
        season_type_all_star='Regular Season',
        type_grouping_nullable=grouping,
        play_type_nullable=play_type,
        timeout=30,
    )
    df = data.get_data_frames()[0]
    _synergy_cache[cache_key] = df
    return df


def get_player_synergy_data(player_name, season='2024-25'):
    """
    Fetch Synergy play type data for a specific player.
    Returns offensive and defensive play type breakdowns.
    Fetches each play type individually (API requires it) but caches
    the league-wide response so subsequent players are instant.
    """
    player = find_player(player_name)

    # Get the player's team from their most recent game log
    time.sleep(0.4)
    log = playergamelog.PlayerGameLog(
        player_id=player['id'], season=season,
        season_type_all_star='Regular Season', timeout=30,
    )
    df = log.get_data_frames()[0]
    if df.empty:
        raise ValueError(f"No game data for {player_name} in {season}")

    matchup = df.iloc[0]['MATCHUP']
    team_abbr = matchup.split(' ')[0].strip()

    results = {'player': player['full_name'], 'team': team_abbr, 'season': season}

    play_types = list(PLAY_TYPE_LABELS.keys())
    off_records = []
    def_records = []

    for pt in play_types:
        for grouping, records in [('offensive', off_records), ('defensive', def_records)]:
            try:
                pt_df = _fetch_all_synergy('P', season, grouping, pt)
                if not pt_df.empty:
                    player_rows = pt_df[pt_df['PLAYER_ID'] == player['id']]
                    if not player_rows.empty:
                        records.extend(_format_play_type_df(player_rows))
            except Exception:
                pass

    off_records.sort(key=lambda r: r['possessions'] or 0, reverse=True)
    def_records.sort(key=lambda r: r['possessions'] or 0, reverse=True)
    results['offensive'] = off_records
    results['defensive'] = def_records

    return results


def get_team_synergy_data(team_abbr, season='2024-25'):
    """
    Fetch Synergy play type data for a team (offensive + defensive).
    """
    all_teams = nba_teams.get_teams()
    team_info = next((t for t in all_teams if t['abbreviation'] == team_abbr), None)
    if not team_info:
        raise ValueError(f"Team '{team_abbr}' not found")

    results = {'team': team_abbr, 'team_name': team_info['full_name'], 'season': season}

    play_types = list(PLAY_TYPE_LABELS.keys())
    off_records = []
    def_records = []

    for pt in play_types:
        for grouping, records in [('offensive', off_records), ('defensive', def_records)]:
            try:
                pt_df = _fetch_all_synergy('T', season, grouping, pt)
                if not pt_df.empty:
                    team_rows = pt_df[pt_df['TEAM_ABBREVIATION'] == team_abbr]
                    if not team_rows.empty:
                        records.extend(_format_play_type_df(team_rows))
            except Exception:
                pass

    off_records.sort(key=lambda r: r['possessions'] or 0, reverse=True)
    def_records.sort(key=lambda r: r['possessions'] or 0, reverse=True)
    results['offensive'] = off_records
    results['defensive'] = def_records

    return results


def get_opponent_scheme_matchup(player_name, stat, season='2024-25'):
    """
    Cross-reference a player's game logs with opponent defensive scheme weaknesses.
    For each game, look at the opponent's defensive play type data to find
    exploitable tendencies.
    """
    player = find_player(player_name)
    game_logs = get_player_game_logs(player['id'], season=season)
    if game_logs.empty:
        raise ValueError(f"No game data for {player_name} in {season}")

    df = build_game_features(game_logs)
    stat_upper = stat.upper()
    if stat_upper not in df.columns:
        raise ValueError(f"Stat '{stat}' not found")

    # Fetch all team defensive play type data (one call covers all teams)
    time.sleep(0.4)
    def_data = synergyplaytypes.SynergyPlayTypes(
        player_or_team_abbreviation='T',
        season=season,
        season_type_all_star='Regular Season',
        type_grouping_nullable='defensive',
        timeout=30,
    )
    def_df = def_data.get_data_frames()[0]

    # Build per-opponent defensive profile
    opp_profiles = {}
    for team_abbr in df['opponent'].unique():
        team_rows = def_df[def_df['TEAM_ABBREVIATION'] == team_abbr]
        if team_rows.empty:
            continue
        profile = {}
        for _, row in team_rows.iterrows():
            pt = row['PLAY_TYPE']
            profile[pt] = {
                'ppp_allowed': float(row['PPP']) if not pd.isna(row['PPP']) else None,
                'fg_pct_allowed': float(row['FG_PCT']) if not pd.isna(row['FG_PCT']) else None,
                'percentile': float(row['PERCENTILE']) if not pd.isna(row['PERCENTILE']) else None,
                'freq': float(row['POSS_PCT']) if not pd.isna(row['POSS_PCT']) else None,
            }
        opp_profiles[team_abbr] = profile

    # For each opponent, compute: stat avg vs. their worst-defended play types
    matchups = []
    for opp, group in df.groupby('opponent'):
        stat_avg = float(group[stat_upper].mean())
        stat_games = int(len(group))
        profile = opp_profiles.get(opp, {})

        # Find weakest play types (highest PPP allowed, lowest percentile = bad defense)
        weaknesses = []
        for pt, vals in profile.items():
            if vals['percentile'] is not None and vals['ppp_allowed'] is not None:
                weaknesses.append({
                    'play_type': pt,
                    'label': PLAY_TYPE_LABELS.get(pt, pt),
                    **vals,
                })
        weaknesses.sort(key=lambda x: x['percentile'])  # lowest percentile = worst defense

        matchups.append({
            'opponent': opp,
            'stat_avg': stat_avg,
            'games': stat_games,
            'defensive_weaknesses': weaknesses[:3],  # top 3 weakest play types
            'full_profile': weaknesses,
        })

    matchups.sort(key=lambda x: x['stat_avg'], reverse=True)

    return {
        'player': player['full_name'],
        'stat': stat_upper,
        'season': season,
        'matchups': matchups,
    }


def _format_play_type_df(df):
    """Convert a Synergy play type DataFrame to a list of dicts."""
    if df.empty:
        return []
    records = []
    for _, row in df.iterrows():
        pt = row.get('PLAY_TYPE', '')
        records.append({
            'play_type': pt,
            'label': PLAY_TYPE_LABELS.get(pt, pt),
            'percentile': _safe_float(row.get('PERCENTILE')),
            'poss_pct': _safe_float(row.get('POSS_PCT')),
            'ppp': _safe_float(row.get('PPP')),
            'fg_pct': _safe_float(row.get('FG_PCT')),
            'efg_pct': _safe_float(row.get('EFG_PCT')),
            'tov_pct': _safe_float(row.get('TOV_POSS_PCT')),
            'score_pct': _safe_float(row.get('SCORE_POSS_PCT')),
            'foul_pct': _safe_float(row.get('SF_POSS_PCT')),
            'possessions': _safe_int(row.get('POSS')),
            'points': _safe_int(row.get('PTS')),
            'gp': _safe_int(row.get('GP')),
        })
    records.sort(key=lambda r: r['possessions'] or 0, reverse=True)
    return records


def _safe_float(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# ── Full Analysis Pipeline ───────────────────────────────────────────────────

def run_full_analysis(player_name, stat, season='2024-25', per_minute=False):
    """
    Run the complete z-score + factor analysis pipeline for a player/stat.

    Args:
        player_name: e.g. "Nikola Jokic"
        stat: column name e.g. "AST", "PTS", "REB"
        season: e.g. "2024-25"
        per_minute: if True, normalize stat values to per-minute rates

    Returns:
        dict with all analysis results
    """
    # 1. Find player
    player = find_player(player_name)

    # 2. Fetch game logs
    game_logs = get_player_game_logs(player['id'], season=season)
    if game_logs.empty:
        raise ValueError(f"No game logs found for {player_name} in {season}")

    # 3. Build features
    df = build_game_features(game_logs)

    # 3b. Enrich with opponent context (pace, def rating) — 1 extra API call
    try:
        team_ctx = get_team_context(season)
        df = enrich_with_opponent_context(df, team_ctx)
    except Exception:
        pass  # non-critical, analysis works without it

    # 4. Extract stat values
    stat_upper = stat.upper()
    if stat_upper not in df.columns:
        available = [c for c in df.columns if c not in ['GAME_DATE', 'MATCHUP', 'game_date']]
        raise ValueError(f"Stat '{stat}' not found. Available: {available}")

    # 4b. Per-minute normalization
    if per_minute:
        valid_minutes = df['minutes_float'].replace(0, np.nan)
        df[stat_upper] = df[stat_upper].astype(float) / valid_minutes
        df = df.dropna(subset=[stat_upper]).reset_index(drop=True)

    values = df[stat_upper].values.astype(float)

    # 5. Z-scores
    z_scores, mean, std = compute_z_scores(values)
    df['z_score'] = z_scores

    # 6. Distribution tests
    dist_tests = test_distribution(values)

    # 7. Factor analysis
    factors = analyze_factors(df, stat_upper)

    # 8. Build game-by-game data
    _fmt = (lambda v: round(float(v), 2)) if per_minute else (lambda v: int(v))

    # Resolve player's team_id from MATCHUP abbreviation
    _team_id_cache = {}
    def _resolve_team_id(matchup):
        """Extract player's team abbreviation from MATCHUP and look up team_id."""
        abbr = matchup.split(' ')[0].strip() if matchup else ''
        if abbr in _team_id_cache:
            return _team_id_cache[abbr]
        matches = [t for t in nba_teams.get_teams() if t['abbreviation'] == abbr]
        tid = str(matches[0]['id']) if matches else ''
        _team_id_cache[abbr] = tid
        return tid

    games = []
    for _, row in df.iterrows():
        games.append({
            'game_id': str(row.get('game_id', '')),
            'date': row['game_date'].strftime('%Y-%m-%d'),
            'matchup': row['MATCHUP'],
            'opponent': row['opponent'],
            'is_home': bool(row['is_home']),
            'stat_value': _fmt(row[stat_upper]),
            'z_score': float(row['z_score']),
            'minutes': _parse_minutes(row.get('MIN', 0)),
            'result': row.get('WL', ''),
            'plus_minus': int(row.get('PLUS_MINUS', 0)),
            'rest_days': int(row['rest_days']),
            'is_back_to_back': bool(row['is_back_to_back']),
            'game_number': int(row['game_number']),
            'team_id': _resolve_team_id(row['MATCHUP']),
        })

    # 9. Histogram bins for the distribution chart
    hist_counts, hist_edges = np.histogram(values, bins='auto')

    return {
        'player': {
            'id': player['id'],
            'name': player['full_name'],
        },
        'stat': stat_upper,
        'season': season,
        'per_minute': per_minute,
        'summary': {
            'mean': round(float(mean), 2),
            'std': round(float(std), 2),
            'median': round(float(np.median(values)), 2),
            'min': round(float(np.min(values)), 2),
            'max': round(float(np.max(values)), 2),
            'games_played': int(len(values)),
            'cv': float(std / mean) if mean != 0 else 0,
        },
        'distribution_tests': dist_tests,
        'factors': factors,
        'games': games,
        'histogram': {
            'counts': hist_counts.tolist(),
            'edges': [float(e) for e in hist_edges]
        }
    }


# ── Betting Analytics ─────────────────────────────────────────────────────────

COUNT_STATS = {'PTS', 'AST', 'REB', 'STL', 'BLK', 'TOV', 'FG3M', 'FGM',
               'FGA', 'FTM', 'FTA', 'OREB', 'DREB', 'PF'}


def american_odds_to_prob(odds):
    """Convert American odds to implied probability."""
    odds = int(odds)
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    else:
        return 100 / (odds + 100)


def compute_ev(true_prob, american_odds):
    """Compute expected value per $1 wagered. Positive = profitable."""
    american_odds = int(american_odds)
    if american_odds < 0:
        payout = 100 / abs(american_odds)
    else:
        payout = american_odds / 100
    return float((true_prob * payout) - ((1 - true_prob) * 1))


def analyze_prop_line(df, stat_col, line):
    """
    Analyze a player prop betting line against game log data.

    Returns dict with overall hit rate, contextual breakdowns, streaks,
    recent form windows, probability estimates, and EV calculations.
    """
    values = df[stat_col].values.astype(float)
    line = float(line)

    over_mask = values > line
    under_mask = values < line
    push_mask = values == line

    over_count = int(over_mask.sum())
    under_count = int(under_mask.sum())
    push_count = int(push_mask.sum())
    total = len(values)
    overall_hit_rate = over_count / total if total > 0 else 0.0

    # ── Contextual hit rates ─────────────────────────────────────────────
    contextual = {}

    def _ctx(label, mask):
        sub = values[mask]
        if len(sub) < 1:
            return
        hits = (sub > line).sum()
        contextual[label] = {
            'over_pct': float(hits / len(sub)),
            'n': int(len(sub)),
            'mean': float(np.nanmean(sub)),
            'std': float(np.nanstd(sub, ddof=1)) if len(sub) > 1 else 0.0,
        }

    if 'is_home' in df.columns:
        _ctx('Home', df['is_home'].values.astype(bool))
        _ctx('Away', ~df['is_home'].values.astype(bool))

    if 'win' in df.columns:
        _ctx('Wins', df['win'].values.astype(bool))
        _ctx('Losses', ~df['win'].values.astype(bool))

    if 'is_back_to_back' in df.columns:
        _ctx('Back-to-Back', df['is_back_to_back'].values.astype(bool))
        rested = df['rest_days'].values >= 2 if 'rest_days' in df.columns else ~df['is_back_to_back'].values.astype(bool)
        _ctx('Rested (2+ days)', rested)

    # Last N games (df should already be sorted by game_date ascending)
    for n in [5, 10, 15]:
        if len(values) >= n:
            _ctx(f'Last {n}', np.array([False] * (len(values) - n) + [True] * n))

    # Per-opponent
    if 'opponent' in df.columns:
        for opp, group in df.groupby('opponent'):
            if len(group) >= 2:
                opp_vals = group[stat_col].values.astype(float)
                hits = (opp_vals > line).sum()
                contextual[f'vs {opp}'] = {
                    'over_pct': float(hits / len(opp_vals)),
                    'n': int(len(opp_vals)),
                    'mean': float(np.nanmean(opp_vals)),
                    'std': float(np.nanstd(opp_vals, ddof=1)) if len(opp_vals) > 1 else 0.0,
                }

    # ── Streak analysis ──────────────────────────────────────────────────
    streaks = _compute_streaks(values, line)

    # ── Recent form windows ──────────────────────────────────────────────
    recent_windows = {}
    for n_label, n_val in [('last_5', 5), ('last_10', 10), ('last_15', 15)]:
        if len(values) >= n_val:
            window = values[-n_val:]
            recent_windows[n_label] = {
                'mean': float(np.nanmean(window)),
                'median': float(np.median(window)),
                'hit_rate': float((window > line).sum() / len(window)),
                'n': int(len(window)),
            }
    recent_windows['season'] = {
        'mean': float(np.nanmean(values)),
        'median': float(np.median(values)),
        'hit_rate': float(overall_hit_rate),
        'n': int(total),
    }

    # T-test: last 10 vs full season
    recent_form_ttest = None
    if len(values) >= 15:
        last_10 = values[-10:]
        t_stat, p_val = scipy_stats.ttest_ind(last_10, values, equal_var=False)
        direction = 'higher' if np.mean(last_10) > np.mean(values) else 'lower'
        recent_form_ttest = {
            'last_10_vs_season_t': float(t_stat),
            'last_10_vs_season_p': float(p_val),
            'significant': bool(p_val < 0.05),
            'direction': direction,
        }

    # ── Probability estimates ────────────────────────────────────────────
    probabilities = {
        'empirical_over': float(overall_hit_rate),
        'percentile_of_line': float(scipy_stats.percentileofscore(values, line)),
    }

    mean_val = float(np.nanmean(values))
    if stat_col in COUNT_STATS and mean_val > 0:
        poisson_over = float(1 - poisson.cdf(floor(line), mu=mean_val))
        probabilities['poisson_over'] = poisson_over
        probabilities['poisson_under'] = float(1 - poisson_over)

    return {
        'overall_hit_rate': float(overall_hit_rate),
        'over_count': over_count,
        'under_count': under_count,
        'push_count': push_count,
        'contextual_hit_rates': contextual,
        'streaks': streaks,
        'recent_windows': recent_windows,
        'recent_form_ttest': recent_form_ttest,
        'probabilities': probabilities,
    }


def _compute_streaks(values, line):
    """Compute current streak and longest over/under streaks."""
    current_type = None
    current_len = 0
    longest_over = 0
    longest_under = 0
    run_over = 0
    run_under = 0

    for v in values:
        if v > line:
            run_over += 1
            run_under = 0
            longest_over = max(longest_over, run_over)
        elif v < line:
            run_under += 1
            run_over = 0
            longest_under = max(longest_under, run_under)
        else:
            run_over = 0
            run_under = 0

    # Current streak is the last run
    if run_over > 0:
        current_type = 'over'
        current_len = run_over
    elif run_under > 0:
        current_type = 'under'
        current_len = run_under
    else:
        current_type = 'push'
        current_len = 0

    return {
        'current_streak_type': current_type,
        'current_streak_len': current_len,
        'longest_over': longest_over,
        'longest_under': longest_under,
    }


def analyze_stat_correlation(df, stat_col_a, stat_col_b, line_a=None, line_b=None):
    """
    Analyze correlation between two stats for the same player.
    Useful for parlay risk assessment.
    """
    a = df[stat_col_a].values.astype(float)
    b = df[stat_col_b].values.astype(float)
    mask = ~np.isnan(a) & ~np.isnan(b)
    a_clean, b_clean = a[mask], b[mask]

    if len(a_clean) < 3:
        return {'error': 'Not enough data'}

    pearson_r, pearson_p = scipy_stats.pearsonr(a_clean, b_clean)
    spearman_r, spearman_p = scipy_stats.spearmanr(a_clean, b_clean)

    result = {
        'stat_a': stat_col_a,
        'stat_b': stat_col_b,
        'n': int(len(a_clean)),
        'pearson_r': float(pearson_r),
        'pearson_p': float(pearson_p),
        'spearman_r': float(spearman_r),
        'spearman_p': float(spearman_p),
        'interpretation': (
            f"{'Positive' if pearson_r > 0 else 'Negative'} correlation "
            f"({'strong' if abs(pearson_r) > 0.5 else 'moderate' if abs(pearson_r) > 0.3 else 'weak'})"
        ),
    }

    if line_a is not None and line_b is not None:
        line_a, line_b = float(line_a), float(line_b)
        both_over = ((a_clean > line_a) & (b_clean > line_b)).sum()
        joint_rate = both_over / len(a_clean) if len(a_clean) > 0 else 0
        indep_rate = ((a_clean > line_a).sum() / len(a_clean)) * ((b_clean > line_b).sum() / len(b_clean))
        result['joint_hit_rate'] = float(joint_rate)
        result['independent_probability'] = float(indep_rate)
        result['correlation_impact'] = float(joint_rate - indep_rate)
        result['parlay_assessment'] = (
            'Positively correlated — parlay is LESS valuable than individual lines'
            if pearson_r > 0.2 else
            'Negatively correlated — parlay is MORE valuable than individual lines'
            if pearson_r < -0.2 else
            'Weakly correlated — parlay value close to independent probability'
        )

    return result


def run_betting_analysis(player_name, stat, line, season='2024-25',
                         odds_over=-110, odds_under=-110, per_minute=False):
    """
    Full betting analysis pipeline for a player prop.
    Mirrors the run_full_analysis() pattern.
    """
    player = find_player(player_name)

    game_logs = get_player_game_logs(player['id'], season=season)
    if game_logs.empty:
        raise ValueError(f"No game logs found for {player_name} in {season}")

    df = build_game_features(game_logs)

    try:
        team_ctx = get_team_context(season)
        df = enrich_with_opponent_context(df, team_ctx)
    except Exception:
        pass

    stat_upper = stat.upper()
    if stat_upper not in df.columns:
        available = [c for c in df.columns if c.isupper() and len(c) <= 10]
        raise ValueError(f"Stat '{stat}' not found. Available: {available}")

    # Per-minute normalization
    if per_minute:
        valid_minutes = df['minutes_float'].replace(0, np.nan)
        df[stat_upper] = df[stat_upper].astype(float) / valid_minutes
        df = df.dropna(subset=[stat_upper]).reset_index(drop=True)

    line = float(line)
    values = df[stat_upper].values.astype(float)

    z_scores, mean, std = compute_z_scores(values)
    df['z_score'] = z_scores

    prop_analysis = analyze_prop_line(df, stat_upper, line)

    # EV calculations
    implied_over = american_odds_to_prob(odds_over)
    implied_under = american_odds_to_prob(odds_under)
    true_over = prop_analysis['overall_hit_rate']
    true_under = 1 - true_over

    ev = {
        'over_ev_custom': compute_ev(true_over, odds_over),
        'under_ev_custom': compute_ev(true_under, odds_under),
        'implied_prob_over': float(implied_over),
        'implied_prob_under': float(implied_under),
        'edge_over': float(true_over - implied_over),
        'edge_under': float(true_under - implied_under),
    }

    # Outlier games (|z| > 2)
    _fmt = (lambda v: round(float(v), 2)) if per_minute else (lambda v: int(v))
    outliers = []
    for _, row in df.iterrows():
        if abs(row['z_score']) > 2.0:
            outliers.append({
                'date': row['game_date'].strftime('%Y-%m-%d'),
                'opponent': row['opponent'],
                'is_home': bool(row['is_home']),
                'stat_value': _fmt(row[stat_upper]),
                'z_score': float(row['z_score']),
                'result': row.get('WL', ''),
                'plus_minus': int(row.get('PLUS_MINUS', 0)),
                'rest_days': int(row['rest_days']),
            })
    outliers.sort(key=lambda x: abs(x['z_score']), reverse=True)
    outliers = outliers[:8]

    # Game-by-game data with hit flag
    games = []
    for _, row in df.iterrows():
        games.append({
            'game_id': str(row.get('game_id', '')),
            'date': row['game_date'].strftime('%Y-%m-%d'),
            'matchup': row['MATCHUP'],
            'opponent': row['opponent'],
            'is_home': bool(row['is_home']),
            'stat_value': _fmt(row[stat_upper]),
            'z_score': float(row['z_score']),
            'minutes': _parse_minutes(row.get('MIN', 0)),
            'result': row.get('WL', ''),
            'plus_minus': int(row.get('PLUS_MINUS', 0)),
            'rest_days': int(row['rest_days']),
            'hit': bool(row[stat_upper] > line),
        })

    hist_counts, hist_edges = np.histogram(values, bins='auto')

    return {
        'player': {'id': player['id'], 'name': player['full_name']},
        'stat': stat_upper,
        'line': line,
        'season': season,
        'per_minute': per_minute,
        'summary': {
            'mean': round(float(mean), 2),
            'std': round(float(std), 2),
            'median': round(float(np.median(values)), 2),
            'min': round(float(np.min(values)), 2),
            'max': round(float(np.max(values)), 2),
            'games_played': int(len(values)),
            'cv': float(std / mean) if mean != 0 else 0,
        },
        'prop_analysis': prop_analysis,
        'ev': ev,
        'outliers': outliers,
        'games': games,
        'histogram': {
            'counts': hist_counts.tolist(),
            'edges': [float(e) for e in hist_edges],
        },
    }


# ── Per-Game Scheme Analysis ────────────────────────────────────────────────

_analysis_cache = DiskCache('analysis')


def classify_shot_action(sub_type, shot_value, shot_distance):
    """Classify a PBP shot action into a category based on subType string."""
    st = (sub_type or '').strip().lower()
    is_three = (shot_value == 3)

    if st.startswith('driving'):
        return {'category': 'drive', 'label': 'Drive', 'is_three': is_three}
    if st.startswith('cutting'):
        return {'category': 'cutting', 'label': 'Cut', 'is_three': is_three}
    if st.startswith('running'):
        if 'pull' in st:
            return {'category': 'transition_pullup', 'label': 'Transition Pull-Up', 'is_three': is_three}
        return {'category': 'transition', 'label': 'Transition', 'is_three': is_three}
    if any(kw in st for kw in ['pullup', 'pull-up', 'step back']):
        return {'category': 'pullup_stepback', 'label': 'Pull-Up/Stepback', 'is_three': is_three}
    if any(kw in st for kw in ['hook', 'turnaround', 'fadeaway']):
        return {'category': 'post_up', 'label': 'Post Up', 'is_three': is_three}
    if 'floating' in st:
        return {'category': 'floater', 'label': 'Floater', 'is_three': is_three}
    if any(kw in st for kw in ['layup', 'dunk', 'finger roll', 'tip', 'putback', 'alley oop']):
        return {'category': 'at_rim', 'label': 'At Rim', 'is_three': is_three}

    # Fallback: plain jump shot — classify by value/distance
    if is_three:
        return {'category': 'catch_shoot_3', 'label': 'Catch & Shoot 3', 'is_three': True}
    if shot_distance and shot_distance >= 15:
        return {'category': 'midrange', 'label': 'Midrange', 'is_three': False}
    return {'category': 'midrange_short', 'label': 'Short Midrange', 'is_three': False}


def parse_game_pbp(game_id, player_id):
    """
    Fetch PlayByPlayV3 for one game, classify all actions for the target player.
    Returns shot summary, assists, FT, turnovers.
    """
    time.sleep(0.4)
    pbp = playbyplayv3.PlayByPlayV3(game_id=game_id, timeout=30)
    df = pbp.play_by_play.get_data_frame()

    player_id = int(player_id)
    player_plays = df[df['personId'] == player_id]

    # ── Shots (made + missed) ──
    shots = player_plays[player_plays['actionType'].isin(['Made Shot', 'Missed Shot'])]
    classified_shots = []
    category_summary = {}

    for _, row in shots.iterrows():
        sv = int(row.get('shotValue', 0)) if pd.notna(row.get('shotValue')) else 0
        sd = int(row.get('shotDistance', 0)) if pd.notna(row.get('shotDistance')) else 0
        classification = classify_shot_action(row.get('subType', ''), sv, sd)
        made = row['actionType'] == 'Made Shot'
        classified_shots.append({
            'period': int(row['period']),
            'clock': str(row.get('clock', '')),
            'sub_type': str(row.get('subType', '')),
            'description': str(row.get('description', '')),
            'made': made,
            'shot_value': sv,
            'shot_distance': sd,
            **classification,
        })
        cat = classification['category']
        if cat not in category_summary:
            category_summary[cat] = {
                'label': classification['label'], 'attempts': 0,
                'makes': 0, 'points': 0,
            }
        category_summary[cat]['attempts'] += 1
        if made:
            category_summary[cat]['makes'] += 1
            category_summary[cat]['points'] += sv

    for cat in category_summary.values():
        cat['fg_pct'] = round(cat['makes'] / cat['attempts'], 3) if cat['attempts'] > 0 else 0.0

    # ── Assists (player as passer) ──
    # In PBPv3, assists show up as separate rows with actionType "Made Shot"
    # and the assister is referenced in the description like "(Jokic 10 AST)"
    assist_pattern = re.compile(r'\(([^)]+?)\s+\d+\s+AST\)')
    # Get player last name from their own plays
    player_name_parts = None
    player_rows = player_plays[player_plays['playerNameI'].notna()]
    if len(player_rows) > 0:
        pni = str(player_rows.iloc[0]['playerNameI'])  # e.g. "N. Jokic"
        player_name_parts = pni.split('.')[-1].strip()  # "Jokic"

    assisted_shots = []
    if player_name_parts:
        all_made = df[df['actionType'] == 'Made Shot']
        for _, row in all_made.iterrows():
            desc = str(row.get('description', ''))
            m = assist_pattern.search(desc)
            if m and player_name_parts.lower() in m.group(1).lower():
                sv = int(row.get('shotValue', 0)) if pd.notna(row.get('shotValue')) else 0
                sd = int(row.get('shotDistance', 0)) if pd.notna(row.get('shotDistance')) else 0
                shot_class = classify_shot_action(row.get('subType', ''), sv, sd)
                assisted_shots.append({
                    'to_player': str(row.get('playerNameI', '')),
                    'shot_type': shot_class['label'],
                    'shot_value': sv,
                    'period': int(row['period']),
                })

    # ── Free throws ──
    fts = player_plays[player_plays['actionType'] == 'Free Throw']
    ft_made = len(fts[fts['shotResult'] == 'Made']) if 'shotResult' in fts.columns else 0
    ft_attempted = len(fts)

    # ── Turnovers ──
    tovs = player_plays[player_plays['actionType'] == 'Turnover']
    turnover_types = {}
    for _, row in tovs.iterrows():
        st = str(row.get('subType', 'Unknown'))
        turnover_types[st] = turnover_types.get(st, 0) + 1

    # ── Rebounds ──
    rebs = player_plays[player_plays['actionType'] == 'Rebound']

    return {
        'game_id': game_id,
        'player_id': player_id,
        'shot_summary': category_summary,
        'total_fga': len(shots),
        'total_fgm': len([s for s in classified_shots if s['made']]),
        'assists': assisted_shots,
        'assist_count': len(assisted_shots),
        'free_throws': {'made': ft_made, 'attempted': ft_attempted},
        'turnovers': turnover_types,
        'turnover_count': len(tovs),
        'rebounds': len(rebs),
    }


def get_team_defense_profiles(season='2024-25'):
    """
    Fetch comprehensive defensive scheme profiles for all 30 teams.
    Combines:
      - LeagueDashPtTeamDefend (closest-defender FG% by zone) — 4 zone calls
      - LeagueHustleStatsTeam (season hustle stats) — 1 call
    All season-level. Returns dict keyed by TEAM_ABBREVIATION.
    """
    cache_key = f"team_def_profiles|{season}"
    if cache_key in _analysis_cache:
        return _analysis_cache[cache_key]

    profiles = {}

    # ── Shot contest by zone ──
    # Each zone returns DIFFERENT column names for FG%, normal FG%, +/-, FGM, FGA
    zone_categories = [
        ('overall', 'Overall', 'D_FG_PCT', 'NORMAL_FG_PCT', 'PCT_PLUSMINUS', 'D_FGM', 'D_FGA'),
        ('3_pointers', '3 Pointers', 'FG3_PCT', 'NS_FG3_PCT', 'PLUSMINUS', 'FG3M', 'FG3A'),
        ('less_than_6ft', 'Less Than 6Ft', 'LT_06_PCT', 'NS_LT_06_PCT', 'PLUSMINUS', 'FGM_LT_06', 'FGA_LT_06'),
        ('greater_than_15ft', 'Greater Than 15Ft', 'GT_15_PCT', 'NS_GT_15_PCT', 'PLUSMINUS', 'FGM_GT_15', 'FGA_GT_15'),
    ]
    for zone_key, cat_value, col_fg, col_normal, col_pm, col_fgm, col_fga in zone_categories:
        try:
            time.sleep(0.4)
            data = leaguedashptteamdefend.LeagueDashPtTeamDefend(
                defense_category=cat_value,
                season=season,
                season_type_all_star='Regular Season',
                timeout=30,
            )
            df = data.get_data_frames()[0]
            for _, row in df.iterrows():
                abbr = row.get('TEAM_ABBREVIATION', '')
                if not abbr:
                    continue
                if abbr not in profiles:
                    profiles[abbr] = {'contest_profile': {}, 'hustle': {}}
                profiles[abbr]['contest_profile'][zone_key] = {
                    'd_fg_pct': _safe_float(row.get(col_fg)),
                    'normal_fg_pct': _safe_float(row.get(col_normal)),
                    'pct_plusminus': _safe_float(row.get(col_pm)),
                    'd_fgm': int(row.get(col_fgm, 0) or 0),
                    'd_fga': int(row.get(col_fga, 0) or 0),
                    'freq': _safe_float(row.get('FREQ')),
                    'gp': int(row.get('GP', 0) or 0),
                }
            print(f"[DefProfiles] Loaded {zone_key} contest data ({len(df)} teams)")
        except Exception as e:
            print(f"[DefProfiles] Failed to fetch {cat_value}: {e}")

    # ── Hustle stats ──
    try:
        time.sleep(0.4)
        hustle = leaguehustlestatsteam.LeagueHustleStatsTeam(
            season=season,
            season_type_all_star='Regular Season',
            timeout=30,
        )
        hdf = hustle.get_data_frames()[0]
        for _, row in hdf.iterrows():
            # Team abbreviation not always in hustle; match by TEAM_ID
            team_id = row.get('TEAM_ID')
            team_name = row.get('TEAM_NAME', '')
            # Find abbreviation from nba_teams
            matches = [t for t in nba_teams.get_teams() if t['id'] == team_id]
            abbr = matches[0]['abbreviation'] if matches else ''
            if not abbr:
                continue
            if abbr not in profiles:
                profiles[abbr] = {'contest_profile': {}, 'hustle': {}}
            # No GP column in hustle — get it from the contest profile 'overall' zone
            overall_zone = profiles.get(abbr, {}).get('contest_profile', {}).get('overall', {})
            gp = overall_zone.get('gp', 1) or 1
            profiles[abbr]['hustle'] = {
                'contested_shots': round((_safe_float(row.get('CONTESTED_SHOTS')) or 0) / gp, 1),
                'contested_shots_2pt': round((_safe_float(row.get('CONTESTED_SHOTS_2PT')) or 0) / gp, 1),
                'contested_shots_3pt': round((_safe_float(row.get('CONTESTED_SHOTS_3PT')) or 0) / gp, 1),
                'deflections': round((_safe_float(row.get('DEFLECTIONS')) or 0) / gp, 1),
                'charges_drawn': round((_safe_float(row.get('CHARGES_DRAWN')) or 0) / gp, 1),
                'screen_assists': round((_safe_float(row.get('SCREEN_ASSISTS')) or 0) / gp, 1),
                'loose_balls_def': round((_safe_float(row.get('DEF_LOOSE_BALLS_RECOVERED')) or 0) / gp, 1),
                'def_box_outs': round((_safe_float(row.get('DEF_BOXOUTS')) or 0) / gp, 1),
                'gp': gp,
            }
        print(f"[DefProfiles] Loaded hustle data ({len(hdf)} teams)")
    except Exception as e:
        print(f"[DefProfiles] Failed to fetch hustle stats: {e}")

    _analysis_cache[cache_key] = profiles
    print(f"[DefProfiles] Cached {len(profiles)} team defensive profiles for {season}")
    return profiles


def fetch_game_hustle_data(game_id, player_id):
    """
    Fetch BoxScoreHustleV2 for a single game, extract target player's hustle stats.
    Called on-demand when user expands a game detail row.
    """
    cache_key = f"hustle_game|{game_id}|{player_id}"
    if cache_key in _analysis_cache:
        return _analysis_cache[cache_key]

    time.sleep(0.4)
    data = boxscorehustlev2.BoxScoreHustleV2(game_id=game_id, timeout=30)
    pdf = data.get_data_frames()[0]  # PlayerStats

    player_id_int = int(player_id)
    player_row = pdf[pdf['personId'] == player_id_int]
    if player_row.empty:
        # Try string match
        player_row = pdf[pdf['personId'].astype(str) == str(player_id)]

    if player_row.empty:
        result = None
    else:
        row = player_row.iloc[0]
        result = {
            'contested_shots': int(row.get('contestedShots', 0) or 0),
            'contested_shots_2pt': int(row.get('contestedShots2pt', 0) or 0),
            'contested_shots_3pt': int(row.get('contestedShots3pt', 0) or 0),
            'deflections': int(row.get('deflections', 0) or 0),
            'charges_drawn': int(row.get('chargesDrawn', 0) or 0),
            'screen_assists': int(row.get('screenAssists', 0) or 0),
            'loose_balls_recovered_def': int(row.get('looseBallsRecoveredDefensive', 0) or 0),
            'defensive_box_outs': int(row.get('defensiveBoxOuts', 0) or 0),
        }

    _analysis_cache[cache_key] = result
    return result


def enrich_games_with_scheme_context(games, season='2024-25'):
    """
    Attach opponent defensive Synergy profile to each game dict.
    Fetches defensive Synergy data per play type (API requires per-type calls).
    """
    cache_key = f"synergy_all_def|{season}"
    if cache_key in _analysis_cache:
        def_df = _analysis_cache[cache_key]
    else:
        # Synergy API requires per-play-type queries
        all_rows = []
        for pt in PLAY_TYPES:
            try:
                time.sleep(0.4)
                def_data = synergyplaytypes.SynergyPlayTypes(
                    player_or_team_abbreviation='T',
                    season=season,
                    season_type_all_star='Regular Season',
                    type_grouping_nullable='defensive',
                    play_type_nullable=pt,
                    timeout=30,
                )
                df = def_data.get_data_frames()[0]
                if not df.empty:
                    all_rows.append(df)
            except Exception:
                continue
        if not all_rows:
            return games
        def_df = pd.concat(all_rows, ignore_index=True)
        _analysis_cache[cache_key] = def_df

    # Build per-team defensive profiles
    opp_profiles = {}
    unique_opps = set(g['opponent'] for g in games)
    for team_abbr in unique_opps:
        team_rows = def_df[def_df['TEAM_ABBREVIATION'] == team_abbr]
        if team_rows.empty:
            continue
        play_types = []
        for _, row in team_rows.iterrows():
            pctile = _safe_float(row.get('PERCENTILE'))
            ppp = _safe_float(row.get('PPP'))
            poss = row.get('POSS', 0) or 0
            if pctile is None or poss <= 0:
                continue
            play_types.append({
                'play_type': PLAY_TYPE_LABELS.get(row['PLAY_TYPE'], row['PLAY_TYPE']),
                'ppp_allowed': ppp,
                'percentile': pctile,
                'freq': _safe_float(row.get('POSS_PCT')),
            })
        play_types.sort(key=lambda x: x['percentile'] if x['percentile'] is not None else 999)
        opp_profiles[team_abbr] = {
            'weaknesses': play_types[:3],
            'strengths': play_types[-3:][::-1] if len(play_types) >= 3 else [],
        }

    for game in games:
        game['opp_scheme'] = opp_profiles.get(game['opponent'])

    # ── Attach team defense profiles (contest + hustle) ──
    try:
        def_profiles = get_team_defense_profiles(season)
    except Exception as e:
        print(f"[SchemeContext] Team defense profiles failed: {e}")
        def_profiles = {}

    for game in games:
        opp = game.get('opponent', '')
        profile = def_profiles.get(opp)
        if profile:
            game['opp_defense_profile'] = profile

    return games


# ── Defensive Attention Score (DAS) ──────────────────────────────────────────

def fetch_game_tracking_data(game_id):
    """
    Fetch BoxScoreAdvancedV3 + BoxScorePlayerTrackV3 + GameRotation for one game.
    Returns (adv_df, track_df, rotation_df) for ALL players in that game.
    Cached in _analysis_cache by 'tracking_v2|{game_id}'.
    """
    cache_key = f'tracking_v2|{game_id}'
    if cache_key in _analysis_cache:
        return _analysis_cache[cache_key]

    adv_df, track_df, rotation_df = None, None, None

    # Fetch advanced box score
    try:
        time.sleep(0.4)
        adv = boxscoreadvancedv3.BoxScoreAdvancedV3(game_id=game_id, timeout=30)
        frames = adv.get_data_frames()
        adv_df = frames[0] if len(frames) > 0 else None
    except Exception as e:
        print(f"[DAS] Advanced box score failed for {game_id}: {e}")

    # Fetch player tracking box score
    try:
        time.sleep(0.4)
        track = boxscoreplayertrackv3.BoxScorePlayerTrackV3(game_id=game_id, timeout=30)
        frames = track.get_data_frames()
        track_df = frames[0] if len(frames) > 0 else None
    except Exception as e:
        print(f"[DAS] Tracking box score failed for {game_id}: {e}")

    # Fetch game rotation (substitution stints)
    try:
        time.sleep(0.4)
        rot = gamerotation.GameRotation(game_id=game_id, timeout=30)
        frames = rot.get_data_frames()
        # GameRotation returns [AwayTeam, HomeTeam] — concatenate both
        if len(frames) >= 2:
            rotation_df = pd.concat([frames[0], frames[1]], ignore_index=True)
        elif len(frames) == 1:
            rotation_df = frames[0]
    except Exception as e:
        print(f"[DAS] GameRotation failed for {game_id}: {e}")

    result = (adv_df, track_df, rotation_df)
    _analysis_cache[cache_key] = result
    return result


def compute_defensive_attention_scores(games_df, player_id, game_ids, stat_col):
    """
    Compute Defensive Attention Score for each game.

    4 signals (each z-scored vs player's own season):
      - Usage Spike (0.30): usagePercentage vs season avg
      - Shot Openness (0.25): uncontested FGA / total tracked FGA
      - Teammate Suppression (0.25): avg teammates' usage drop
      - Touch Increase (0.20): touches vs season avg

    Returns dict with:
      - per_game: list of per-game DAS data
      - season_avgs: dict of season averages for each signal
      - regression: regression results (beta, r2, p_value, etc.)
      - games_missing: list of game_ids that failed to fetch
      - warnings: list of warning strings
    """
    WEIGHTS = {
        'usage_spike': 0.30,
        'shot_openness': 0.25,
        'teammate_suppression': 0.25,
        'touch_increase': 0.20,
    }

    per_game_raw = []
    games_missing = []
    warnings = []
    player_id_str = str(player_id)

    for gid in game_ids:
        adv_df, track_df, rotation_df = fetch_game_tracking_data(gid)

        if adv_df is None or track_df is None:
            games_missing.append(gid)
            continue

        # Normalize column names — API sometimes returns camelCase or UPPER
        def _norm_cols(df):
            df.columns = [c.lower() for c in df.columns]
            return df

        adv_df = _norm_cols(adv_df.copy())
        track_df = _norm_cols(track_df.copy())

        # Find player row — match by personid (numeric)
        pid_col_adv = 'personid' if 'personid' in adv_df.columns else None
        pid_col_trk = 'personid' if 'personid' in track_df.columns else None

        if pid_col_adv is None or pid_col_trk is None:
            games_missing.append(gid)
            continue

        adv_df[pid_col_adv] = adv_df[pid_col_adv].astype(str)
        track_df[pid_col_trk] = track_df[pid_col_trk].astype(str)

        player_adv = adv_df[adv_df[pid_col_adv] == player_id_str]
        player_trk = track_df[track_df[pid_col_trk] == player_id_str]

        if player_adv.empty or player_trk.empty:
            games_missing.append(gid)
            continue

        player_adv_row = player_adv.iloc[0]
        player_trk_row = player_trk.iloc[0]

        # Get team ID for teammate filtering
        team_col = 'teamid' if 'teamid' in adv_df.columns else None
        if team_col is None:
            games_missing.append(gid)
            continue
        player_team_id = str(player_adv_row[team_col])

        # ── Signal 1: Usage Percentage ──
        usage_col = 'usagepercentage' if 'usagepercentage' in adv_df.columns else None
        usage_pct = None
        if usage_col:
            usage_pct = _safe_float(player_adv_row.get(usage_col))

        # ── Signal 2: Shot Openness (uncontested FGA / total tracked FGA) ──
        uncontested_fga_col = 'uncontestedfieldgoalsattempted'
        contested_fga_col = 'contestedfieldgoalsattempted'
        uc_fga = _safe_float(player_trk_row.get(uncontested_fga_col, 0)) or 0
        c_fga = _safe_float(player_trk_row.get(contested_fga_col, 0)) or 0
        total_tracked_fga = uc_fga + c_fga
        openness_pct = (uc_fga / total_tracked_fga) if total_tracked_fga > 0 else None

        # ── Signal 3: Teammate Suppression (rotation-weighted usage) ──
        teammates_adv = adv_df[
            (adv_df[team_col].astype(str) == player_team_id) &
            (adv_df[pid_col_adv] != player_id_str)
        ]
        teammate_usage_avg = None

        # Try rotation-weighted approach (only teammates who shared court time)
        if rotation_df is not None and not rotation_df.empty and usage_col:
            rot = rotation_df.copy()
            rot.columns = [c.lower() for c in rot.columns]
            rot_pid_col = 'person_id' if 'person_id' in rot.columns else None
            rot_team_col = 'team_id' if 'team_id' in rot.columns else None
            rot_in_col = 'in_time_real' if 'in_time_real' in rot.columns else None
            rot_out_col = 'out_time_real' if 'out_time_real' in rot.columns else None

            if all(c is not None for c in [rot_pid_col, rot_team_col, rot_in_col, rot_out_col]):
                rot[rot_pid_col] = rot[rot_pid_col].astype(str)
                rot[rot_team_col] = rot[rot_team_col].astype(str)

                # Build player's stint intervals
                player_stints = rot[rot[rot_pid_col] == player_id_str]
                player_intervals = []
                for _, stint in player_stints.iterrows():
                    in_t = _safe_float(stint[rot_in_col])
                    out_t = _safe_float(stint[rot_out_col])
                    if in_t is not None and out_t is not None:
                        player_intervals.append((min(in_t, out_t), max(in_t, out_t)))

                if player_intervals:
                    # For each teammate, compute overlap minutes with target player
                    team_rot = rot[
                        (rot[rot_team_col] == player_team_id) &
                        (rot[rot_pid_col] != player_id_str)
                    ]
                    weighted_usages = []
                    for tm_pid in team_rot[rot_pid_col].unique():
                        tm_stints = team_rot[team_rot[rot_pid_col] == tm_pid]
                        overlap_total = 0.0
                        for _, ts in tm_stints.iterrows():
                            tm_in = _safe_float(ts[rot_in_col])
                            tm_out = _safe_float(ts[rot_out_col])
                            if tm_in is None or tm_out is None:
                                continue
                            tm_start, tm_end = min(tm_in, tm_out), max(tm_in, tm_out)
                            for p_start, p_end in player_intervals:
                                overlap_total += max(0, min(p_end, tm_end) - max(p_start, tm_start))

                        # Convert tenths-of-seconds to minutes
                        overlap_min = overlap_total / 600.0
                        if overlap_min > 1.0:
                            # Look up this teammate's usage from adv_df
                            tm_adv_row = teammates_adv[teammates_adv[pid_col_adv] == tm_pid]
                            if not tm_adv_row.empty:
                                tm_usg = _safe_float(tm_adv_row.iloc[0].get(usage_col))
                                if tm_usg is not None:
                                    weighted_usages.append((tm_usg, overlap_min))

                    if weighted_usages:
                        total_weight = sum(w for _, w in weighted_usages)
                        teammate_usage_avg = sum(u * w for u, w in weighted_usages) / total_weight

        # Fallback: if rotation data unavailable, use old unweighted method
        if teammate_usage_avg is None and not teammates_adv.empty and usage_col:
            tm_usages = teammates_adv[usage_col].apply(_safe_float).dropna()
            if len(tm_usages) > 0:
                teammate_usage_avg = float(tm_usages.mean())

        # ── Signal 4: Touches ──
        touch_col = 'touches' if 'touches' in track_df.columns else None
        touches = None
        if touch_col:
            touches = _safe_float(player_trk_row.get(touch_col))

        per_game_raw.append({
            'game_id': gid,
            'usage_pct': usage_pct,
            'openness_pct': openness_pct,
            'teammate_usage_avg': teammate_usage_avg,
            'touches': touches,
        })

    if len(per_game_raw) < 5:
        warnings.append(f"Only {len(per_game_raw)} games with tracking data (need ≥5 for meaningful DAS)")

    if len(games_missing) > 0:
        pct_missing = len(games_missing) / len(game_ids) * 100
        if pct_missing > 30:
            warnings.append(f"{pct_missing:.0f}% of games missing tracking data")

    # ── Compute season averages + z-scores for each signal ──
    signals = ['usage_pct', 'openness_pct', 'teammate_usage_avg', 'touches']
    signal_names = ['usage_spike', 'shot_openness', 'teammate_suppression', 'touch_increase']
    season_avgs = {}
    season_stds = {}

    for sig in signals:
        vals = [g[sig] for g in per_game_raw if g[sig] is not None]
        if len(vals) >= 2:
            season_avgs[sig] = float(np.mean(vals))
            season_stds[sig] = float(np.std(vals, ddof=1))
        else:
            season_avgs[sig] = None
            season_stds[sig] = None

    # ── Z-score each game + compute composite DAS ──
    per_game_results = []

    # Build lookup of stat values from games_df
    # NOTE: if per_minute=True, games_df[stat_col] is already per-minute normalized
    # by run_das_analysis, so we just read the values directly.
    stat_by_game = {}
    for _, row in games_df.iterrows():
        gid = str(row.get('game_id', ''))
        val = row.get(stat_col)
        stat_by_game[gid] = float(val) if val is not None else None

    for g in per_game_raw:
        gid = g['game_id']
        z_components = {}
        raw_values = {}

        for sig, sig_name in zip(signals, signal_names):
            val = g[sig]
            avg = season_avgs.get(sig)
            std = season_stds.get(sig)

            raw_values[sig_name] = val

            if val is not None and avg is not None and std is not None and std > 0:
                # For teammate suppression, LOWER avg = more suppression = higher DAS
                if sig == 'teammate_usage_avg':
                    z_components[sig_name] = -(val - avg) / std  # negate: lower = better
                else:
                    z_components[sig_name] = (val - avg) / std
            else:
                z_components[sig_name] = None

        # Compute composite DAS — reweight if some signals missing
        valid_signals = {k: v for k, v in z_components.items() if v is not None}
        if valid_signals:
            total_weight = sum(WEIGHTS[k] for k in valid_signals)
            das = sum(WEIGHTS[k] * v / total_weight for k, v in valid_signals.items())
        else:
            das = None

        per_game_results.append({
            'game_id': gid,
            'das': round(das, 3) if das is not None else None,
            'components': {k: round(v, 3) if v is not None else None
                          for k, v in z_components.items()},
            'raw': {k: round(v, 4) if v is not None else None
                    for k, v in raw_values.items()},
            'stat_value': stat_by_game.get(gid),
        })

    # ── Regression: stat_value = alpha + beta * DAS + epsilon ──
    regression = compute_adjusted_z_scores(per_game_results)

    # Merge adjusted z-scores back into per_game_results
    adj_z_map = {}
    if regression and regression.get('per_game_adj_z'):
        for item in regression['per_game_adj_z']:
            adj_z_map[item['game_id']] = item['adjusted_z']

    for g in per_game_results:
        g['adjusted_z'] = adj_z_map.get(g['game_id'])

    # Flush tracking cache to disk so progress persists
    _analysis_cache.flush()

    return {
        'per_game': per_game_results,
        'season_avgs': {
            'usage_pct': season_avgs.get('usage_pct'),
            'openness_pct': season_avgs.get('openness_pct'),
            'teammate_usage_avg': season_avgs.get('teammate_usage_avg'),
            'touches': season_avgs.get('touches'),
        },
        'season_stds': {
            'usage_pct': season_stds.get('usage_pct'),
            'openness_pct': season_stds.get('openness_pct'),
            'teammate_usage_avg': season_stds.get('teammate_usage_avg'),
            'touches': season_stds.get('touches'),
        },
        'regression': regression,
        'games_missing': games_missing,
        'games_fetched': len(per_game_raw),
        'games_total': len(game_ids),
        'warnings': warnings,
    }


def compute_adjusted_z_scores(per_game_results):
    """
    OLS regression: stat_value = alpha + beta * DAS + epsilon.

    Returns:
      - beta: points per unit of DAS
      - r_squared: how much variance DAS explains
      - p_value: significance of relationship
      - residual_std: std of residuals
      - interpretation: human-readable string
      - per_game_adj_z: list of {game_id, raw_z, adjusted_z}
    """
    # Filter to games with both DAS and stat_value
    valid = [(g['das'], g['stat_value']) for g in per_game_results
             if g['das'] is not None and g['stat_value'] is not None]

    if len(valid) < 5:
        return {
            'beta': None, 'r_squared': None, 'p_value': None,
            'residual_std': None, 'interpretation': 'Insufficient data for regression',
            'per_game_adj_z': [],
        }

    das_vals = np.array([v[0] for v in valid])
    stat_vals = np.array([v[1] for v in valid])

    # OLS regression
    slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(das_vals, stat_vals)

    # Residuals
    predicted = intercept + slope * das_vals
    residuals = stat_vals - predicted
    residual_std = float(np.std(residuals, ddof=2)) if len(residuals) > 2 else float(np.std(residuals))

    # Overall stat mean and std
    stat_mean = float(np.mean(stat_vals))
    stat_std = float(np.std(stat_vals, ddof=1))

    # Per-game adjusted z-scores
    per_game_adj_z = []
    das_lookup = {g['game_id']: g['das'] for g in per_game_results if g['das'] is not None}

    for g in per_game_results:
        if g['stat_value'] is None or g['das'] is None:
            continue

        # Raw z-score
        raw_z = (g['stat_value'] - stat_mean) / stat_std if stat_std > 0 else 0.0

        # Adjusted: remove the DAS-explained component, re-z-score against original std
        # This answers: "what would the z-score be if we removed the defensive attention boost?"
        das_boost = slope * g['das']
        adjusted_value = g['stat_value'] - das_boost
        adjusted_z = (adjusted_value - stat_mean) / stat_std if stat_std > 0 else 0.0

        per_game_adj_z.append({
            'game_id': g['game_id'],
            'raw_z': round(float(raw_z), 3),
            'adjusted_z': round(float(adjusted_z), 3),
            'das_boost': round(float(das_boost), 2),
        })

    r_squared = r_value ** 2
    interp = (f"Each 1.0 DAS ≈ {slope:+.1f} stat units. "
              f"DAS explains {r_squared * 100:.0f}% of game-to-game variance.")

    if p_value > 0.10:
        interp += " (Not statistically significant — DAS may not be predictive for this player/stat.)"
    elif p_value > 0.05:
        interp += " (Marginally significant, p < 0.10)"

    return {
        'beta': round(float(slope), 3),
        'alpha': round(float(intercept), 3),
        'r_squared': round(float(r_squared), 4),
        'p_value': round(float(p_value), 5),
        'std_err': round(float(std_err), 4),
        'residual_std': round(float(residual_std), 3),
        'stat_mean': round(stat_mean, 3),
        'stat_std': round(stat_std, 3),
        'interpretation': interp,
        'per_game_adj_z': per_game_adj_z,
    }


def get_top_players_by_stat(stat, season='2024-25', limit=20):
    """
    Fetch top N players by per-game average of the given stat.
    Uses LeagueDashPlayerStats.

    Returns list of dicts:
      [{player_id, player_name, team, stat_value, games_played}, ...]
    """
    time.sleep(0.4)
    league = leaguedashplayerstats.LeagueDashPlayerStats(
        season=season,
        per_mode_detailed='PerGame',
        timeout=30,
    )
    ldf = league.get_data_frames()[0]

    stat_upper = stat.upper()
    if stat_upper not in ldf.columns:
        raise ValueError(f"Stat '{stat_upper}' not found in league stats")

    # Filter to players with meaningful sample (>= 10 games)
    ldf = ldf[ldf['GP'] >= 10].copy()
    ldf = ldf.nlargest(limit, stat_upper)

    result = []
    for _, row in ldf.iterrows():
        result.append({
            'player_id': int(row['PLAYER_ID']),
            'player_name': row['PLAYER_NAME'],
            'team': row.get('TEAM_ABBREVIATION', ''),
            'stat_value': round(float(row[stat_upper]), 1),
            'games_played': int(row['GP']),
        })
    return result


def run_das_analysis(player_name, stat, season='2024-25', per_minute=False):
    """
    Top-level orchestrator: runs the existing pipeline, then computes DAS.

    Returns dict with:
      - player: basic info
      - stat, season, per_minute
      - das: full DAS results from compute_defensive_attention_scores
    """
    # 1. Find player
    player = find_player(player_name)

    # 2. Fetch game logs
    game_logs = get_player_game_logs(player['id'], season=season)
    if game_logs.empty:
        raise ValueError(f"No game logs found for {player_name} in {season}")

    # 3. Build features
    df = build_game_features(game_logs)

    # 4. Extract stat + optional per-minute
    stat_upper = stat.upper()
    if stat_upper not in df.columns:
        raise ValueError(f"Stat '{stat}' not found")

    if per_minute:
        valid_minutes = df['minutes_float'].replace(0, np.nan)
        df[stat_upper] = df[stat_upper].astype(float) / valid_minutes
        df = df.dropna(subset=[stat_upper]).reset_index(drop=True)

    # 5. Collect game IDs
    game_ids = [str(row.get('game_id', '')) for _, row in df.iterrows()]
    game_ids = [gid for gid in game_ids if gid]

    # 6. Compute DAS
    das_results = compute_defensive_attention_scores(
        df, player['id'], game_ids, stat_upper
    )

    # 7. Enrich per_game entries with game metadata from df
    _team_id_cache = {}
    def _resolve_tid(matchup):
        abbr = matchup.split(' ')[0].strip() if matchup else ''
        if abbr in _team_id_cache:
            return _team_id_cache[abbr]
        matches = [t for t in nba_teams.get_teams() if t['abbreviation'] == abbr]
        tid = str(matches[0]['id']) if matches else ''
        _team_id_cache[abbr] = tid
        return tid

    game_meta = {}
    for _, row in df.iterrows():
        gid = str(row.get('game_id', ''))
        if gid:
            game_meta[gid] = {
                'opponent': row.get('opponent', ''),
                'date': row['game_date'].strftime('%Y-%m-%d') if pd.notna(row.get('game_date')) else '',
                'is_home': bool(row.get('is_home', False)),
                'team_id': _resolve_tid(row.get('MATCHUP', '')),
                'minutes': round(float(row.get('minutes_float', 0)), 1) if row.get('minutes_float') else None,
                'result': 'W' if row.get('win') else 'L',
                'plus_minus': int(row.get('PLUS_MINUS', 0)) if pd.notna(row.get('PLUS_MINUS')) else None,
                # Always include core box-score stats for the per-game table
                'pts': int(row['PTS']) if pd.notna(row.get('PTS')) else None,
                'reb': int(row['REB']) if pd.notna(row.get('REB')) else None,
                'ast': int(row['AST']) if pd.notna(row.get('AST')) else None,
            }

    for g in das_results['per_game']:
        meta = game_meta.get(g['game_id'], {})
        g.update(meta)

    # 8. Enrich with opponent scheme context (season-level, cheap)
    try:
        enriched = enrich_games_with_scheme_context(das_results['per_game'], season)
        das_results['per_game'] = enriched
    except Exception as e:
        print(f"[DAS] Scheme enrichment failed (non-critical): {e}")

    return {
        'player': {
            'name': player['full_name'],
            'id': player['id'],
        },
        'stat': stat_upper,
        'season': season,
        'per_minute': per_minute,
        'das': das_results,
    }


def fetch_game_shot_chart(game_id, player_id, team_id):
    """
    Fetch enriched shot chart data for a player in a specific game.

    Returns dict with:
      - shots: list of {loc_x, loc_y, made, distance, zone, action_type,
               game_event_id, description, sub_type, assist, ...}
      - summary: {total_fga, total_fgm, fg_pct, by_zone}
      - matchups: [{defender_name, defender_id, matchup_min, matchup_fgm,
                    matchup_fga, matchup_fg_pct, matchup_3pm, matchup_3pa}, ...]
    """
    cache_key = f'shotchart|{game_id}|{player_id}'
    if cache_key in _analysis_cache:
        return _analysis_cache[cache_key]

    # ── Step 1: ShotChartDetail ──
    time.sleep(0.4)
    try:
        chart = shotchartdetail.ShotChartDetail(
            team_id=team_id,
            player_id=player_id,
            game_id_nullable=game_id,
            season_nullable='',
            context_measure_simple='FGA',
            timeout=30,
        )
        df = chart.get_data_frames()[0]
    except Exception as e:
        print(f"[ShotChart] Failed for {game_id}/{player_id}: {e}")
        return {'shots': [], 'summary': {}, 'matchups': [], 'error': str(e)}

    if df.empty:
        result = {'shots': [], 'summary': {}, 'matchups': []}
        _analysis_cache[cache_key] = result
        return result

    shots = []
    for _, row in df.iterrows():
        shots.append({
            'loc_x': int(row.get('LOC_X', 0)),
            'loc_y': int(row.get('LOC_Y', 0)),
            'made': bool(row.get('SHOT_MADE_FLAG', 0)),
            'distance': int(row.get('SHOT_DISTANCE', 0)),
            'zone': row.get('SHOT_ZONE_BASIC', ''),
            'zone_area': row.get('SHOT_ZONE_AREA', ''),
            'zone_range': row.get('SHOT_ZONE_RANGE', ''),
            'action_type': row.get('ACTION_TYPE', ''),
            'shot_type': row.get('SHOT_TYPE', ''),
            'quarter': int(row.get('PERIOD', 0)),
            'time_remaining': f"{row.get('MINUTES_REMAINING', '')}:{str(row.get('SECONDS_REMAINING', '')).zfill(2)}",
            'game_event_id': int(row.get('GAME_EVENT_ID', 0)),
        })

    # ── Step 2: PlayByPlayV3 → match to shots via GAME_EVENT_ID ──
    assist_pattern = re.compile(r'\(([^)]+?)\s+\d+\s+AST\)')
    try:
        time.sleep(0.4)
        pbp = playbyplayv3.PlayByPlayV3(game_id=game_id, timeout=30)
        pbp_df = pbp.play_by_play.get_data_frame()
        # Build lookup: actionNumber → row data
        pbp_lookup = {}
        for _, prow in pbp_df.iterrows():
            action_num = int(prow.get('actionNumber', 0))
            pbp_lookup[action_num] = prow

        for shot in shots:
            eid = shot['game_event_id']
            if eid in pbp_lookup:
                prow = pbp_lookup[eid]
                desc = str(prow.get('description', ''))
                sub_type = str(prow.get('subType', ''))
                shot['description'] = desc
                shot['sub_type'] = sub_type
                # Parse assist from description
                m = assist_pattern.search(desc)
                if m:
                    shot['assist'] = m.group(1).strip()
            else:
                shot['description'] = ''
                shot['sub_type'] = ''
    except Exception as e:
        print(f"[ShotChart] PBP enrichment failed for {game_id}: {e}")
        for shot in shots:
            shot.setdefault('description', '')
            shot.setdefault('sub_type', '')

    # ── Step 3: BoxScoreMatchupsV3 → defender breakdown ──
    matchups = []
    try:
        time.sleep(0.4)
        mu = boxscorematchupsv3.BoxScoreMatchupsV3(game_id=game_id, timeout=30)
        mu_df = mu.get_data_frames()[0]
        player_mu = mu_df[mu_df['personIdOff'] == int(player_id)]
        for _, mrow in player_mu.iterrows():
            def _safe_float(v, default=0.0):
                try:
                    return round(float(v), 3) if pd.notna(v) else default
                except (ValueError, TypeError):
                    return default
            def _safe_int(v, default=0):
                try:
                    return int(v) if pd.notna(v) else default
                except (ValueError, TypeError):
                    return default

            # matchupMinutesSort is in seconds; convert to minutes
            min_secs = _safe_float(mrow.get('matchupMinutesSort'))
            matchups.append({
                'defender_name': f"{mrow.get('firstNameDef', '')} {mrow.get('familyNameDef', '')}".strip(),
                'defender_id': _safe_int(mrow.get('personIdDef')),
                'matchup_min': round(min_secs / 60, 1),
                'matchup_min_str': str(mrow.get('matchupMinutes', '0:00')),
                'matchup_fgm': _safe_int(mrow.get('matchupFieldGoalsMade')),
                'matchup_fga': _safe_int(mrow.get('matchupFieldGoalsAttempted')),
                'matchup_fg_pct': _safe_float(mrow.get('matchupFieldGoalsPercentage')),
                'matchup_3pm': _safe_int(mrow.get('matchupThreePointersMade')),
                'matchup_3pa': _safe_int(mrow.get('matchupThreePointersAttempted')),
                # Extended scheme fields
                'switches_on': _safe_int(mrow.get('switchesOn')),
                'help_blk': _safe_int(mrow.get('helpBlocks')),
                'help_fgm': _safe_int(mrow.get('helpFieldGoalsMade')),
                'help_fga': _safe_int(mrow.get('helpFieldGoalsAttempted')),
                'help_fg_pct': _safe_float(mrow.get('helpFieldGoalsPercentage')),
                'partial_poss': _safe_float(mrow.get('partialPossessions')),
                'pct_def_time': _safe_float(mrow.get('percentageDefenderTotalTime')),
                'pct_off_time': _safe_float(mrow.get('percentageOffensiveTotalTime')),
                'player_points': _safe_int(mrow.get('playerPoints')),
                'matchup_ast': _safe_int(mrow.get('matchupAssists')),
                'matchup_tov': _safe_int(mrow.get('matchupTurnovers')),
                'matchup_blk': _safe_int(mrow.get('matchupBlocks')),
                'shooting_fouls': _safe_int(mrow.get('shootingFouls')),
            })
        matchups.sort(key=lambda x: x['matchup_min'], reverse=True)
    except Exception as e:
        print(f"[ShotChart] Matchup enrichment failed for {game_id}: {e}")

    # ── Summary ──
    total = len(shots)
    made_count = sum(1 for s in shots if s['made'])

    zone_stats = {}
    for s in shots:
        z = s['zone']
        if z not in zone_stats:
            zone_stats[z] = {'fga': 0, 'fgm': 0}
        zone_stats[z]['fga'] += 1
        if s['made']:
            zone_stats[z]['fgm'] += 1
    for z in zone_stats:
        zone_stats[z]['pct'] = round(zone_stats[z]['fgm'] / zone_stats[z]['fga'], 3) \
            if zone_stats[z]['fga'] > 0 else 0

    summary = {
        'total_fga': total,
        'total_fgm': made_count,
        'fg_pct': round(made_count / total, 3) if total > 0 else 0,
        'by_zone': zone_stats,
    }

    # ── Step 4: BoxScoreHustleV2 → game-level hustle stats ──
    hustle = None
    try:
        hustle = fetch_game_hustle_data(game_id, player_id)
    except Exception as e:
        print(f"[ShotChart] Hustle fetch failed for {game_id}: {e}")

    result = {'shots': shots, 'summary': summary, 'matchups': matchups, 'hustle': hustle}
    _analysis_cache[cache_key] = result
    return result
