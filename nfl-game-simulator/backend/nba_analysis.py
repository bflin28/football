"""
NBA Player Stat Z-Score Analysis Module

Fetches player game logs, calculates z-scores, runs distribution tests,
and identifies factors that drive stat variance (opponent, home/away, rest, etc.)
"""

import time
import numpy as np
import pandas as pd
from scipy import stats as scipy_stats
from nba_api.stats.endpoints import playergamelog, leaguedashteamstats
from nba_api.stats.static import players


# ── Helpers ──────────────────────────────────────────────────────────────────

def find_player(name):
    """Find an NBA player by name. Returns dict with id, full_name, etc."""
    results = players.find_players_by_full_name(name)
    if not results:
        # Try partial match
        all_players = players.get_active_players()
        results = [p for p in all_players if name.lower() in p['full_name'].lower()]
    if not results:
        raise ValueError(f"Player '{name}' not found")
    return results[0]


def get_player_game_logs(player_id, season='2024-25', season_type='Regular Season'):
    """Fetch game logs for a player/season from stats.nba.com."""
    time.sleep(0.6)  # respect rate limits
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
    time.sleep(0.6)
    defense = leaguedashteamstats.LeagueDashTeamStats(
        season=season,
        measure_type_detailed_defense='Base',
        timeout=30
    )
    df = defense.get_data_frames()[0]
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
    - home/away
    - opponent
    - rest days
    - back-to-back indicator
    - minutes played
    - game result (W/L)
    - point differential
    """
    df = game_logs_df.copy()

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


# ── Full Analysis Pipeline ───────────────────────────────────────────────────

def run_full_analysis(player_name, stat, season='2024-25'):
    """
    Run the complete z-score + factor analysis pipeline for a player/stat.

    Args:
        player_name: e.g. "Nikola Jokic"
        stat: column name e.g. "AST", "PTS", "REB"
        season: e.g. "2024-25"

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

    # 4. Extract stat values
    stat_upper = stat.upper()
    if stat_upper not in df.columns:
        available = [c for c in df.columns if c not in ['GAME_DATE', 'MATCHUP', 'game_date']]
        raise ValueError(f"Stat '{stat}' not found. Available: {available}")

    values = df[stat_upper].values.astype(float)

    # 5. Z-scores
    z_scores, mean, std = compute_z_scores(values)
    df['z_score'] = z_scores

    # 6. Distribution tests
    dist_tests = test_distribution(values)

    # 7. Factor analysis
    factors = analyze_factors(df, stat_upper)

    # 8. Build game-by-game data
    games = []
    for _, row in df.iterrows():
        games.append({
            'date': row['game_date'].strftime('%Y-%m-%d'),
            'matchup': row['MATCHUP'],
            'opponent': row['opponent'],
            'is_home': bool(row['is_home']),
            'stat_value': int(row[stat_upper]),
            'z_score': float(row['z_score']),
            'minutes': _parse_minutes(row.get('MIN', 0)),
            'result': row.get('WL', ''),
            'plus_minus': int(row.get('PLUS_MINUS', 0)),
            'rest_days': int(row['rest_days']),
            'is_back_to_back': bool(row['is_back_to_back']),
            'game_number': int(row['game_number'])
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
        'summary': {
            'mean': float(mean),
            'std': float(std),
            'median': float(np.median(values)),
            'min': int(np.min(values)),
            'max': int(np.max(values)),
            'games_played': int(len(values)),
            'cv': float(std / mean) if mean != 0 else 0,  # coefficient of variation
        },
        'distribution_tests': dist_tests,
        'factors': factors,
        'games': games,
        'histogram': {
            'counts': hist_counts.tolist(),
            'edges': [float(e) for e in hist_edges]
        }
    }
