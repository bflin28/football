import React, { useState, useEffect } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Bar, Scatter, Line } from 'react-chartjs-2';
import './NbaPlayerAnalysis.css';

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement, BarElement,
  Title, Tooltip, Legend, Filler
);

const FACTORS = [
  { key: 'das', label: 'Defensive Attention Score (DAS)' },
  // Future factors go here
];

const FACTOR_INFO = {
  das: {
    name: 'Defensive Attention Score (DAS)',
    oneLiner: 'Measures how much a defense focused on stopping a specific player in a given game.',
    formula: 'DAS = 0.30 × Usage Spike + 0.25 × Shot Openness + 0.25 × Teammate Suppression + 0.20 × Touch Increase',
    signals: [
      {
        name: 'Usage Spike',
        weight: '30%',
        desc: 'How much higher was the player\'s usage rate than their season average? Defenses that focus on a star often can\'t prevent them from getting the ball — they just try to make shots harder.',
        example: 'Jokic\'s season-avg usage is 29.8%. In the LAC game he posted 39.0% (+1.37 z-score).',
      },
      {
        name: 'Shot Openness',
        weight: '25%',
        desc: 'What fraction of the player\'s field goal attempts were uncontested? When defenses collapse on a player, ironically some shots open up (kick-outs back, offensive boards, etc.).',
        example: '52.2% of his FGA were uncontested vs 46.0% average (+0.43 z-score).',
      },
      {
        name: 'Teammate Suppression',
        weight: '25%',
        desc: 'Did teammates who shared court time see their usage drop? If a defense is funneling everything through one player, teammates get fewer touches. Weighted by minutes shared (rotation data).',
        example: 'Teammate avg usage dropped to 14.6% vs 17.4% norm (+1.81 z-score — heavy suppression).',
      },
      {
        name: 'Touch Increase',
        weight: '20%',
        desc: 'Did the player handle the ball more than usual? Measured by player-tracking touch count relative to their season average.',
        example: '98.0 touches vs 96.6 average (+0.07 z-score — roughly average).',
      },
    ],
    interpretation: [
      'Each signal is z-scored against the player\'s own season, then combined with the weights above.',
      'DAS > 0 means the defense paid above-average attention to this player. DAS < 0 means below-average.',
      'A DAS of +1.0 is roughly one standard deviation of extra defensive attention.',
      'The regression beta (e.g. +10.06 for Jokic PTS) tells you: "each +1.0 DAS associates with +10 extra points."',
      'R-squared tells you what fraction of game-to-game stat variance DAS explains (39.6% for Jokic PTS).',
    ],
    example: {
      player: 'Nikola Jokic',
      game: 'vs LAC (Nov 12)',
      line: '55 PTS on 18/23 FG',
      das: '+0.98',
      story: 'The Clippers committed heavy attention to Jokic — his usage spiked to 39%, teammates were suppressed, and despite the focus he got open looks (52% uncontested). DAS of +0.98 means ~1 standard deviation above his normal level of defensive attention. The model predicts this level of attention associates with roughly +10 extra points.',
    },
  },
};

const GLOSSARY = {
  categories: [
    {
      name: 'Core DAS Metrics',
      terms: [
        { term: 'DAS (Defensive Attention Score)', definition: 'Composite z-score measuring how much a defense focused on stopping a specific player in a given game. Positive = above-average attention.', formula: 'DAS = 0.30 \u00d7 Usage Spike + 0.25 \u00d7 Shot Openness + 0.25 \u00d7 Teammate Suppression + 0.20 \u00d7 Touch Increase', range: 'Typically -2.0 to +2.0; >1.0 = heavy attention, <-1.0 = light' },
        { term: 'Usage Spike', definition: 'How much the player\'s usage rate exceeded their season average, z-scored. Usage rate = % of team possessions used by the player while on court.', source: 'BoxScoreAdvancedV3' },
        { term: 'Shot Openness', definition: 'Fraction of the player\'s FGA that were uncontested, z-scored against their season. Higher = more open looks.', source: 'BoxScorePlayerTrackV3' },
        { term: 'Teammate Suppression', definition: 'Whether teammates who shared court time saw their usage drop. Weighted by rotation overlap minutes. Higher z = more suppression. Sign is inverted: lower teammate usage = higher DAS component.', source: 'BoxScoreAdvancedV3 + GameRotation' },
        { term: 'Touch Increase', definition: 'Player\'s touch count relative to their season average, z-scored. More touches = more ball-handling responsibility.', source: 'BoxScorePlayerTrackV3' },
      ],
    },
    {
      name: 'Regression & Statistics',
      terms: [
        { term: 'Beta (\u03b2)', definition: 'Regression slope \u2014 stat units per 1.0 DAS. E.g., \u03b2=+10 means each +1.0 DAS associates with ~10 extra stat units.' },
        { term: 'R-squared (R\u00b2)', definition: 'Fraction of game-to-game stat variance explained by DAS. 0\u2013100%. Higher = DAS is more predictive for this player.' },
        { term: 'p-value', definition: 'Probability the DAS\u2013stat relationship is due to chance. <0.05 = statistically significant, <0.001 = highly significant.' },
        { term: 'Adjusted Z-Score', definition: 'The player\'s stat z-score after removing the DAS-explained component. Isolates "true" over/under-performance from defensive scheme effects.' },
        { term: 'Z-Score', definition: 'Number of standard deviations from the mean. +1.0 = one std dev above average, -1.0 = one below.' },
      ],
    },
    {
      name: 'Defensive Scheme Metrics',
      terms: [
        { term: 'D_FG_PCT', definition: 'Field goal percentage opponents shoot when a team/player is the closest defender. Lower = better defense.', source: 'LeagueDashPtTeamDefend' },
        { term: 'Normal FG%', definition: 'Expected FG% for those same shots based on league averages. Used as baseline for comparison.', source: 'LeagueDashPtTeamDefend' },
        { term: 'PCT +/-', definition: 'D_FG_PCT minus Normal FG%. Negative = defense makes opponents shoot worse than expected. Positive = worse defense.', source: 'LeagueDashPtTeamDefend' },
        { term: 'Contested Shots', definition: 'Number of opponent shot attempts where the player/team was within close proximity as the closest defender.', source: 'BoxScoreHustleV2' },
        { term: 'Deflections', definition: 'Number of times a player tipped or deflected the ball on defense (disrupted passes, reaches).', source: 'BoxScoreHustleV2' },
        { term: 'Charges Drawn', definition: 'Offensive fouls drawn by the defender by establishing legal guarding position.', source: 'BoxScoreHustleV2' },
        { term: 'Screen Assists', definition: 'Screens set that directly led to a teammate scoring or an assist.', source: 'BoxScoreHustleV2' },
        { term: 'Defensive Box Outs', definition: 'Number of times a player boxed out an opponent on the defensive glass to secure a rebound.', source: 'BoxScoreHustleV2' },
        { term: 'Loose Balls Recovered', definition: 'Loose balls picked up on the defensive end.', source: 'BoxScoreHustleV2' },
      ],
    },
    {
      name: 'Matchup Metrics',
      terms: [
        { term: 'Matchup Minutes', definition: 'Time (minutes) a specific defender was assigned to guard the player in a game.', source: 'BoxScoreMatchupsV3' },
        { term: 'Matchup FG / FG%', definition: 'Field goals made/attempted and shooting percentage while guarded by a specific defender.' },
        { term: 'Switches On', definition: 'Number of times the defense switched this defender onto the player. High count indicates a switch-heavy defensive scheme.', source: 'BoxScoreMatchupsV3' },
        { term: 'Help Blocks', definition: 'Blocks by a help defender (not the primary matchup assignment).', source: 'BoxScoreMatchupsV3' },
        { term: 'Help FGM/FGA', definition: 'Field goals when a help defender was involved rather than the primary assignment. Shows help defense activity.', source: 'BoxScoreMatchupsV3' },
        { term: 'Partial Possessions', definition: 'Possessions where a defender was only partially involved (switched on/off partway through).', source: 'BoxScoreMatchupsV3' },
        { term: '% Defender Time', definition: 'What percentage of the defender\'s total defensive minutes were spent guarding this player.', source: 'BoxScoreMatchupsV3' },
        { term: '% Offensive Time', definition: 'What percentage of the offensive player\'s time this defender was guarding them.', source: 'BoxScoreMatchupsV3' },
        { term: 'Player Points', definition: 'Points scored by the offensive player while matched up with this specific defender.', source: 'BoxScoreMatchupsV3' },
        { term: 'Matchup Assists', definition: 'Assists recorded by the offensive player while guarded by this defender.', source: 'BoxScoreMatchupsV3' },
        { term: 'Matchup Turnovers', definition: 'Turnovers committed while being guarded by this defender.', source: 'BoxScoreMatchupsV3' },
        { term: 'Shooting Fouls', definition: 'Shooting fouls drawn against this defender.', source: 'BoxScoreMatchupsV3' },
      ],
    },
    {
      name: 'Synergy Play Types',
      terms: [
        { term: 'PPP (Points Per Possession)', definition: 'Average points scored per possession on a given play type. Higher = more efficient offense.' },
        { term: 'Percentile', definition: 'Rank among all teams (0\u2013100). 95th percentile = top 5% in the league at defending that play type.' },
        { term: 'Isolation', definition: 'One-on-one play where the ball handler creates their own shot without a screen.' },
        { term: 'Pick & Roll (Ball Handler)', definition: 'Ball handler uses a screen and attacks off the pick-and-roll action.' },
        { term: 'Pick & Roll (Roll Man)', definition: 'The screener rolls to the basket or pops out after setting the screen.' },
        { term: 'Post Up', definition: 'Player receives the ball with their back to the basket and operates from the low/mid post.' },
        { term: 'Spot Up', definition: 'Catch-and-shoot or one-dribble pull-up from a stationary position, typically off a pass.' },
        { term: 'Transition', definition: 'Fast break or semi-transition possession before the defense sets up.' },
        { term: 'Handoff', definition: 'Dribble handoff action between two players, often involving a screen.' },
        { term: 'Cut', definition: 'Off-ball movement toward the basket to receive a pass for a layup or dunk.' },
        { term: 'Off Screen', definition: 'Player uses an off-ball screen to get open for a catch-and-shoot opportunity.' },
        { term: 'Putbacks', definition: 'Offensive rebounds converted immediately into shot attempts.' },
      ],
    },
    {
      name: 'General Basketball',
      terms: [
        { term: 'FGA / FGM / FG%', definition: 'Field Goals Attempted / Made / Percentage.' },
        { term: '3PA / 3PM / 3P%', definition: 'Three-Point Attempts / Made / Percentage.' },
        { term: 'Usage Rate', definition: 'Estimated % of team possessions used by a player while on court. Formula: 100 \u00d7 ((FGA + 0.44 \u00d7 FTA + TOV) \u00d7 (Tm MP / 5)) / (MP \u00d7 (Tm FGA + 0.44 \u00d7 Tm FTA + Tm TOV))' },
        { term: 'Pace', definition: 'Estimated number of possessions per 48 minutes. Higher pace = faster tempo game.' },
        { term: 'Defensive Rating', definition: 'Points allowed per 100 possessions. Lower = better defense.' },
        { term: 'Offensive Rating', definition: 'Points scored per 100 possessions. Higher = better offense.' },
        { term: 'Net Rating', definition: 'Offensive Rating minus Defensive Rating. Positive = outscoring opponents.' },
        { term: 'Per Minute Rate', definition: 'Stat divided by minutes played. Normalizes for playing time differences across games.' },
      ],
    },
  ],
};

const NbaPlayerAnalysis = () => {
  // ── Controls ──
  const [playerName, setPlayerName] = useState('Nikola Jokic');
  const [stat, setStat] = useState('PTS');
  const [season, setSeason] = useState('2025-26');
  const [statsList, setStatsList] = useState([]);
  const [searchResults, setSearchResults] = useState([]);
  const [showSearch, setShowSearch] = useState(false);
  const [perMinute, setPerMinute] = useState(false);
  const [activeFactor, setActiveFactor] = useState('das');
  const [viewMode, setViewMode] = useState('player');
  const [showFactorInfo, setShowFactorInfo] = useState(false);
  const [error, setError] = useState(null);

  // ── Player Deep Dive ──
  const [dasData, setDasData] = useState(null);
  const [dasLoading, setDasLoading] = useState(false);
  const [dasProgress, setDasProgress] = useState(0);
  const [expandedGame, setExpandedGame] = useState(null);
  const [shotChartData, setShotChartData] = useState({});
  const [shotChartLoading, setShotChartLoading] = useState(null);
  const [highlightedShot, setHighlightedShot] = useState(null);
  const [showGlossary, setShowGlossary] = useState(false);
  const [glossarySearch, setGlossarySearch] = useState('');
  const [availablePlayers, setAvailablePlayers] = useState([]);

  // ── Leaderboard ──
  const [leaderboardData, setLeaderboardData] = useState(null);
  const [leaderboardLoading, setLeaderboardLoading] = useState(false);
  const [leaderboardProgress, setLeaderboardProgress] = useState({ current: 0, total: 0, playerName: '' });

  const statLabel = perMinute ? `${stat}/min` : stat;

  useEffect(() => {
    fetch('/api/nba/stats-list')
      .then(r => r.json())
      .then(setStatsList)
      .catch(() => {});
    fetch('/api/nba/available-players')
      .then(r => r.json())
      .then(data => setAvailablePlayers(data.players || []))
      .catch(() => {});
  }, []);

  // ── Player search ──
  const searchPlayers = async (query) => {
    if (query.length < 2) { setSearchResults([]); return; }
    try {
      const res = await fetch(`/api/nba/players/search?q=${encodeURIComponent(query)}`);
      const json = await res.json();
      setSearchResults(json);
      setShowSearch(true);
    } catch { setSearchResults([]); }
  };

  const selectPlayer = (name) => {
    setPlayerName(name);
    setShowSearch(false);
    setSearchResults([]);
    setDasData(null);
  };

  const quickPickPlayer = (name) => {
    setPlayerName(name);
    setShowSearch(false);
    setSearchResults([]);
    setDasData(null);
    // Auto-trigger analyze after state update
    setTimeout(() => {
      document.querySelector('.analyze-btn')?.click();
    }, 50);
  };

  // ── DAS fetch (Player Deep Dive) ──
  const fetchDefensiveAttention = async () => {
    setDasLoading(true);
    setDasProgress(0);
    setError(null);
    const estSeconds = 80;
    const progressInterval = setInterval(() => {
      setDasProgress(prev => Math.min(prev + (100 / estSeconds), 95));
    }, 1000);
    try {
      const params = new URLSearchParams({
        player: playerName, stat, season, per_minute: perMinute,
      });
      const res = await fetch(`/api/nba/defensive-attention?${params}`);
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'DAS analysis failed');
      setDasData(json);
    } catch (e) {
      setError(e.message);
    } finally {
      clearInterval(progressInterval);
      setDasProgress(100);
      setDasLoading(false);
    }
  };

  // ── Shot chart fetch ──
  const fetchShotChart = async (gameId, teamId) => {
    if (!gameId || !dasData?.player?.id || shotChartData[gameId]) return;
    setShotChartLoading(gameId);
    try {
      const params = new URLSearchParams({
        game_id: gameId,
        player_id: dasData.player.id.toString(),
        team_id: teamId,
      });
      const res = await fetch(`/api/nba/game/shot-chart?${params}`);
      const json = await res.json();
      if (res.ok) {
        setShotChartData(prev => ({ ...prev, [gameId]: json }));
      }
    } catch { /* non-critical */ }
    finally { setShotChartLoading(null); }
  };

  // ── Game row expand/collapse ──
  const toggleGameExpand = (gameId, teamId) => {
    if (expandedGame === gameId) {
      setExpandedGame(null);
    } else {
      setExpandedGame(gameId);
      if (teamId) fetchShotChart(gameId, teamId);
    }
  };

  // ── Leaderboard ──
  const loadLeaderboard = async () => {
    setLeaderboardLoading(true);
    setLeaderboardData(null);
    setError(null);

    try {
      const topRes = await fetch(
        `/api/nba/top-players?${new URLSearchParams({ stat, season, limit: '20' })}`
      );
      const players = await topRes.json();
      if (!topRes.ok) throw new Error(players.error || 'Failed to fetch top players');

      const allGames = [];
      const playerSummaries = [];

      for (let i = 0; i < players.length; i++) {
        const p = players[i];
        setLeaderboardProgress({ current: i + 1, total: players.length, playerName: p.player_name });

        try {
          const dasRes = await fetch(
            `/api/nba/defensive-attention?${new URLSearchParams({
              player: p.player_name, stat, season, per_minute: perMinute,
            })}`
          );
          const dasJson = await dasRes.json();

          if (dasRes.ok && dasJson.das?.per_game) {
            for (const game of dasJson.das.per_game) {
              if (game.das != null && game.stat_value != null) {
                allGames.push({
                  ...game,
                  player_name: p.player_name,
                  player_team: p.team,
                });
              }
            }

            const validGames = dasJson.das.per_game.filter(g => g.das != null);
            playerSummaries.push({
              player_name: p.player_name,
              team: p.team,
              avg_stat: p.stat_value,
              avg_das: validGames.length > 0
                ? validGames.reduce((sum, g) => sum + g.das, 0) / validGames.length
                : 0,
              beta: dasJson.das.regression?.beta,
              r_squared: dasJson.das.regression?.r_squared,
              p_value: dasJson.das.regression?.p_value,
              games_fetched: dasJson.das.games_fetched,
            });

            // Incremental update
            setLeaderboardData({
              allGames: [...allGames].sort((a, b) => b.das - a.das),
              playerSummaries: [...playerSummaries].sort((a, b) => b.avg_das - a.avg_das),
              byTeam: computeTeamAggregation([...allGames]),
            });
          }
        } catch (e) {
          console.error(`DAS failed for ${p.player_name}:`, e);
        }
      }

      // Final sort
      setLeaderboardData({
        allGames: allGames.sort((a, b) => b.das - a.das),
        playerSummaries: playerSummaries.sort((a, b) => b.avg_das - a.avg_das),
        byTeam: computeTeamAggregation(allGames),
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setLeaderboardLoading(false);
    }
  };

  const computeTeamAggregation = (allGames) => {
    const byOpp = {};
    for (const g of allGames) {
      const opp = g.opponent;
      if (!opp) continue;
      if (!byOpp[opp]) byOpp[opp] = { games: 0, totalDas: 0, totalStat: 0 };
      byOpp[opp].games += 1;
      byOpp[opp].totalDas += g.das || 0;
      byOpp[opp].totalStat += g.stat_value || 0;
    }
    return Object.entries(byOpp)
      .map(([team, d]) => ({
        team,
        avgDas: d.totalDas / d.games,
        avgStat: d.totalStat / d.games,
        games: d.games,
      }))
      .sort((a, b) => b.avgDas - a.avgDas);
  };

  // ── DAS lookup for game detail ──
  const dasLookup = {};
  if (dasData?.das?.per_game) {
    for (const g of dasData.das.per_game) {
      dasLookup[g.game_id] = g;
    }
  }

  // ── Render: Shot Chart ──
  const renderShotChart = (gameId) => {
    const chartData = shotChartData[gameId];
    const isLoading = shotChartLoading === gameId;

    if (isLoading) return <div className="shot-chart-loading"><div className="loading-spinner small" /><span>Loading shot chart...</span></div>;
    if (!chartData || !chartData.shots?.length) return null;

    const toSvgX = (locX) => locX + 250;
    const toSvgY = (locY) => locY + 50;

    return (
      <div className="shot-chart-container">
        <h4>Shot Chart ({chartData.summary.total_fgm}/{chartData.summary.total_fga} FG, {(chartData.summary.fg_pct * 100).toFixed(0)}%)</h4>
        <svg viewBox="0 0 500 470" className="shot-chart-svg">
          <rect x="0" y="0" width="500" height="470" fill="#f5e6c8" rx="4" />
          <rect x="170" y="0" width="160" height="190" fill="none" stroke="#8b6914" strokeWidth="1.5" />
          <circle cx="250" cy="190" r="60" fill="none" stroke="#8b6914" strokeWidth="1" strokeDasharray="5,5" />
          <circle cx="250" cy="52" r="7.5" fill="none" stroke="#e74c3c" strokeWidth="2" />
          <line x1="220" y1="40" x2="280" y2="40" stroke="#333" strokeWidth="3" />
          <path d="M 30 0 L 30 140 A 238 238 0 0 0 470 140 L 470 0" fill="none" stroke="#8b6914" strokeWidth="1.5" />
          <path d="M 210 52 A 40 40 0 0 0 290 52" fill="none" stroke="#8b6914" strokeWidth="1" />
          {chartData.shots.map((shot, i) => (
            <circle
              key={i}
              cx={toSvgX(shot.loc_x)}
              cy={toSvgY(shot.loc_y)}
              r={highlightedShot === i ? 9 : (shot.shot_type?.includes('3PT') ? 6 : 5)}
              fill={shot.made ? 'rgba(39,174,96,0.8)' : 'rgba(231,76,60,0.8)'}
              stroke={highlightedShot === i ? '#fff' : (shot.made ? '#1e8449' : '#c0392b')}
              strokeWidth={highlightedShot === i ? 2.5 : 1}
              className={highlightedShot === i ? 'shot-dot-highlight' : ''}
              style={{ transition: 'r 0.15s, stroke-width 0.15s' }}
            >
              <title>{`${shot.sub_type || shot.action_type}\n${shot.distance}ft — ${shot.made ? 'Made' : 'Missed'}\nQ${shot.quarter} ${shot.time_remaining}${shot.assist ? `\nAST: ${shot.assist}` : ''}`}</title>
            </circle>
          ))}
        </svg>
        {chartData.summary.by_zone && (
          <div className="shot-chart-zones">
            {Object.entries(chartData.summary.by_zone)
              .sort((a, b) => b[1].fga - a[1].fga)
              .map(([zone, stats]) => (
                <div key={zone} className="shot-zone-tag">
                  <span className="zone-name">{zone}</span>
                  <span className="zone-stat">{stats.fgm}/{stats.fga}</span>
                  <span className={`zone-pct ${stats.pct > 0.5 ? 'good' : stats.pct < 0.33 ? 'bad' : ''}`}>
                    {(stats.pct * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
          </div>
        )}
      </div>
    );
  };

  // ── Render: Matchup Summary (who guarded them) ──
  const renderMatchupSummary = (gameId) => {
    const chartData = shotChartData[gameId];
    if (!chartData?.matchups?.length) return null;

    return (
      <div className="matchup-summary">
        <h4>Who Guarded Them</h4>
        <div className="matchup-cards">
          {chartData.matchups.map((m, i) => (
            <div key={m.defender_id || i} className={`matchup-card ${i === 0 ? 'matchup-primary' : ''}`}>
              {i === 0 && <span className="matchup-badge">Primary</span>}
              <div className="matchup-name">{m.defender_name}</div>
              <div className="matchup-stats">
                <span>{m.matchup_min.toFixed(1)} min</span>
                <span className="matchup-divider">&middot;</span>
                <span>{m.matchup_fgm}/{m.matchup_fga} FG ({(m.matchup_fg_pct * 100).toFixed(0)}%)</span>
                {m.matchup_3pa > 0 && (
                  <>
                    <span className="matchup-divider">&middot;</span>
                    <span>{m.matchup_3pm}/{m.matchup_3pa} 3PT</span>
                  </>
                )}
              </div>
              {(m.switches_on > 0 || m.help_fga > 0 || m.pct_def_time > 0) && (
                <div className="matchup-detail">
                  {m.switches_on > 0 && <span>{m.switches_on} sw</span>}
                  {m.help_fga > 0 && <span>{m.switches_on > 0 ? ' · ' : ''}{m.help_fgm}/{m.help_fga} help</span>}
                  {m.pct_def_time > 0 && <span>{(m.switches_on > 0 || m.help_fga > 0) ? ' · ' : ''}{(m.pct_def_time * 100).toFixed(0)}% def time</span>}
                  {m.shooting_fouls > 0 && <span> · {m.shooting_fouls} fouls</span>}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  };

  // ── Render: Shot-by-Shot Log ──
  const renderShotLog = (gameId) => {
    const chartData = shotChartData[gameId];
    if (!chartData?.shots?.length) return null;

    // Sort by quarter asc, then time desc (higher time = earlier in quarter)
    const sortedShots = [...chartData.shots].sort((a, b) => {
      if (a.quarter !== b.quarter) return a.quarter - b.quarter;
      // Parse time_remaining "M:SS" for comparison
      const parseTime = (t) => {
        const [m, s] = (t || '0:00').split(':').map(Number);
        return (m || 0) * 60 + (s || 0);
      };
      return parseTime(b.time_remaining) - parseTime(a.time_remaining);
    });

    return (
      <div className="shot-log-section">
        <h4>Shot-by-Shot Log ({chartData.summary.total_fga} FGA)</h4>
        <div className="shot-log-table-wrap">
          <table className="shot-log-table">
            <thead>
              <tr>
                <th>Q</th>
                <th>Time</th>
                <th>Shot Type</th>
                <th>Dist</th>
                <th>Zone</th>
                <th>Result</th>
                <th>Play Detail</th>
              </tr>
            </thead>
            <tbody>
              {sortedShots.map((shot, i) => {
                // Find original index in chartData.shots for highlight sync
                const origIdx = chartData.shots.indexOf(shot);
                return (
                  <tr
                    key={i}
                    className={`shot-log-row ${highlightedShot === origIdx ? 'shot-log-highlighted' : ''}`}
                    onMouseEnter={() => setHighlightedShot(origIdx)}
                    onMouseLeave={() => setHighlightedShot(null)}
                  >
                    <td>{shot.quarter}</td>
                    <td className="shot-time">{shot.time_remaining}</td>
                    <td className="shot-type-cell">{shot.sub_type || shot.action_type}</td>
                    <td>{shot.distance}ft</td>
                    <td className="shot-zone-cell">{shot.zone}</td>
                    <td>
                      <span className={shot.made ? 'shot-result-made' : 'shot-result-missed'}>
                        {shot.made ? 'Made' : 'Miss'}
                      </span>
                    </td>
                    <td className="shot-detail-cell">
                      {shot.description || '—'}
                      {shot.assist && (
                        <span className="shot-assist-badge">AST: {shot.assist}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  // ── Render: Opponent Defensive Scheme Profile ──
  const renderDefenseSchemeProfile = (game) => {
    const dg = dasLookup[game.game_id];
    const chartData = shotChartData[game.game_id];
    const oppScheme = dg?.opp_scheme;
    const oppDefProfile = dg?.opp_defense_profile;
    const hustle = chartData?.hustle;
    const matchups = chartData?.matchups;

    if (!oppScheme && !oppDefProfile && !hustle) return null;

    // Compute aggregate matchup scheme indicators
    const totalSwitches = matchups?.reduce((s, m) => s + (m.switches_on || 0), 0) || 0;
    const totalHelpFGA = matchups?.reduce((s, m) => s + (m.help_fga || 0), 0) || 0;
    const totalHelpFGM = matchups?.reduce((s, m) => s + (m.help_fgm || 0), 0) || 0;
    const totalPartial = matchups?.reduce((s, m) => s + (m.partial_poss || 0), 0) || 0;

    const zoneLabels = {
      overall: 'Overall',
      '3_pointers': '3-Pointers',
      less_than_6ft: 'At Rim (<6ft)',
      greater_than_15ft: 'Mid-Range (15ft+)',
    };

    return (
      <div className="defense-scheme-section">
        <h4>Opponent Defensive Scheme {dg?.opponent ? `\u2014 ${dg.opponent}` : ''}</h4>

        {oppDefProfile?.contest_profile && (
          <div className="contest-profile">
            <h5>Shot Contest Profile (Season)</h5>
            {Object.entries(zoneLabels).map(([key, label]) => {
              const zone = oppDefProfile.contest_profile[key];
              if (!zone) return null;
              const diff = zone.pct_plusminus || 0;
              const barWidth = Math.min(Math.abs(diff) * 500, 100);
              return (
                <div key={key} className="contest-bar-row">
                  <div className="contest-bar-label">{label}</div>
                  <div className="contest-bar-track">
                    <div
                      className={`contest-bar-fill ${diff < 0 ? 'better' : 'worse'}`}
                      style={{ width: `${barWidth}%`, marginLeft: diff >= 0 ? '50%' : `${50 - barWidth}%` }}
                    />
                    <div className="contest-bar-center" />
                  </div>
                  <div className={`contest-bar-value ${diff < 0 ? 'good' : 'bad'}`}>
                    {diff > 0 ? '+' : ''}{(diff * 100).toFixed(1)}%
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {oppScheme?.weaknesses?.length > 0 && (
          <div className="scheme-weaknesses">
            <h5>Defensive Weaknesses (Synergy)</h5>
            <div className="weakness-cards">
              {oppScheme.weaknesses.map((w, i) => (
                <div key={i} className="weakness-card">
                  <span className="weakness-type">{w.play_type}</span>
                  <span className="weakness-stat">{w.ppp_allowed?.toFixed(2)} PPP</span>
                  <span className="weakness-pctile">{w.percentile != null ? `${(w.percentile * 100).toFixed(0)}th` : ''}</span>
                </div>
              ))}
            </div>
            {oppScheme.strengths?.length > 0 && (
              <>
                <h5>Defensive Strengths</h5>
                <div className="weakness-cards">
                  {oppScheme.strengths.map((s, i) => (
                    <div key={i} className="strength-card">
                      <span className="weakness-type">{s.play_type}</span>
                      <span className="weakness-stat">{s.ppp_allowed?.toFixed(2)} PPP</span>
                      <span className="weakness-pctile">{s.percentile != null ? `${(s.percentile * 100).toFixed(0)}th` : ''}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {oppDefProfile?.hustle && (
          <div className="hustle-profile">
            <h5>Team Hustle Profile (Season)</h5>
            <div className="hustle-grid">
              {[
                { key: 'contested_shots', label: 'Contested Shots' },
                { key: 'deflections', label: 'Deflections' },
                { key: 'charges_drawn', label: 'Charges Drawn' },
                { key: 'screen_assists', label: 'Screen Assists' },
                { key: 'loose_balls_def', label: 'Loose Balls (Def)' },
                { key: 'def_box_outs', label: 'Def Box Outs' },
              ].map(({ key, label }) => {
                const val = oppDefProfile.hustle[key];
                return val != null ? (
                  <div key={key} className="hustle-stat">
                    <span className="hustle-val">{typeof val === 'number' ? val.toFixed(1) : val}</span>
                    <span className="hustle-label">{label}</span>
                  </div>
                ) : null;
              })}
            </div>
          </div>
        )}

        {(totalSwitches > 0 || totalHelpFGA > 0) && (
          <div className="scheme-indicators">
            <h5>Game Scheme Indicators</h5>
            <div className="hustle-grid">
              {totalSwitches > 0 && (
                <div className="hustle-stat">
                  <span className="hustle-val">{totalSwitches}</span>
                  <span className="hustle-label">Total Switches</span>
                </div>
              )}
              {totalHelpFGA > 0 && (
                <div className="hustle-stat">
                  <span className="hustle-val">{totalHelpFGM}/{totalHelpFGA}</span>
                  <span className="hustle-label">Help Defense FG</span>
                </div>
              )}
              {totalPartial > 0 && (
                <div className="hustle-stat">
                  <span className="hustle-val">{totalPartial.toFixed(1)}</span>
                  <span className="hustle-label">Partial Poss</span>
                </div>
              )}
            </div>
          </div>
        )}

        {hustle && (
          <div className="game-hustle-stats">
            <h5>Player Hustle (This Game)</h5>
            <div className="hustle-grid">
              {[
                { key: 'contested_shots', label: 'Contested Shots' },
                { key: 'deflections', label: 'Deflections' },
                { key: 'charges_drawn', label: 'Charges Drawn' },
                { key: 'screen_assists', label: 'Screen Assists' },
                { key: 'loose_balls_recovered_def', label: 'Loose Balls (Def)' },
                { key: 'defensive_box_outs', label: 'Def Box Outs' },
              ].map(({ key, label }) => {
                const val = hustle[key];
                return val != null && val > 0 ? (
                  <div key={key} className="hustle-stat">
                    <span className="hustle-val">{val}</span>
                    <span className="hustle-label">{label}</span>
                  </div>
                ) : null;
              })}
            </div>
          </div>
        )}
      </div>
    );
  };

  // ── Render: Glossary Panel ──
  const renderGlossary = () => {
    if (!showGlossary) return null;

    const searchLower = glossarySearch.toLowerCase();
    const filtered = GLOSSARY.categories.map(cat => ({
      ...cat,
      terms: cat.terms.filter(t =>
        t.term.toLowerCase().includes(searchLower) ||
        t.definition.toLowerCase().includes(searchLower)
      ),
    })).filter(cat => cat.terms.length > 0);

    return (
      <div className="glossary-overlay" onClick={() => setShowGlossary(false)}>
        <div className="glossary-panel" onClick={e => e.stopPropagation()}>
          <div className="glossary-header">
            <h3>Glossary</h3>
            <input
              className="glossary-search"
              placeholder="Search terms..."
              value={glossarySearch}
              onChange={e => setGlossarySearch(e.target.value)}
            />
            <button className="glossary-close" onClick={() => setShowGlossary(false)}>&times;</button>
          </div>
          <div className="glossary-body">
            {filtered.map((cat, ci) => (
              <div key={ci} className="glossary-category">
                <h4>{cat.name}</h4>
                <dl>
                  {cat.terms.map((t, ti) => (
                    <div key={ti} className="glossary-term">
                      <dt>{t.term}</dt>
                      <dd>
                        {t.definition}
                        {t.formula && <div className="glossary-formula"><code>{t.formula}</code></div>}
                        {t.range && <div className="glossary-range">Range: {t.range}</div>}
                        {t.source && <div className="glossary-source">Source: {t.source}</div>}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  };

  // ── Render: Expanded game detail (DAS breakdown + shot chart) ──
  const renderGameDetail = (game) => {
    const dg = dasLookup[game.game_id];
    if (!dg) return null;

    const avgs = dasData?.das?.season_avgs;
    const reg = dasData?.das?.regression;
    const signalInfo = [
      { key: 'usage_spike', label: 'Usage Spike', raw: dg.raw?.usage_spike, avg: avgs?.usage_pct, unit: '%', mult: 100 },
      { key: 'shot_openness', label: 'Shot Openness', raw: dg.raw?.shot_openness, avg: avgs?.openness_pct, unit: '%', mult: 100 },
      { key: 'teammate_suppression', label: 'Teammate Suppression', raw: dg.raw?.teammate_suppression, avg: avgs?.teammate_usage_avg, unit: '%', mult: 100 },
      { key: 'touch_increase', label: 'Touch Increase', raw: dg.raw?.touch_increase, avg: avgs?.touches, unit: '', mult: 1 },
    ];

    return (
      <div className="game-detail-panel">
        <div className="das-game-breakdown">
          <h4>Defensive Attention — DAS {dg.das?.toFixed(2) ?? '—'}</h4>
          <div className="das-component-bars">
            {signalInfo.map(s => {
              const z = dg.components[s.key];
              const rawVal = s.raw != null ? (s.raw * s.mult).toFixed(1) : '—';
              const avgVal = s.avg != null ? (s.avg * s.mult).toFixed(1) : '—';
              return (
                <div key={s.key} className="das-bar-row">
                  <div className="das-bar-label">{s.label}</div>
                  <div className="das-bar-values">
                    <span>{rawVal}{s.unit} vs {avgVal}{s.unit} avg</span>
                  </div>
                  <div className="das-bar-track">
                    <div className={`das-bar-fill ${z > 0.5 ? 'high' : z < -0.5 ? 'low' : 'neutral'}`}
                      style={{
                        width: `${Math.min(Math.abs(z || 0) * 25, 100)}%`,
                        marginLeft: z < 0 ? 'auto' : undefined,
                      }}
                    />
                  </div>
                  <div className={`das-bar-z ${z > 0.5 ? 'das-pos' : z < -0.5 ? 'das-neg' : ''}`}>
                    {z?.toFixed(2) ?? '—'}
                  </div>
                </div>
              );
            })}
          </div>
          {dg.adjusted_z != null && reg?.beta != null && (
            <div className="das-adj-note">
              Implied stat boost: {(reg.beta * dg.das).toFixed(1)} {statLabel}
            </div>
          )}
        </div>
        {renderDefenseSchemeProfile(game)}
        {renderMatchupSummary(game.game_id)}
        {renderShotChart(game.game_id)}
        {renderShotLog(game.game_id)}
      </div>
    );
  };

  // ── Render: Mini stats bar ──
  const renderMiniStatsBar = () => {
    const perGame = dasData.das.per_game.filter(g => g.stat_value != null);
    const vals = perGame.map(g => g.stat_value);
    const mean = vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
    const reg = dasData.das.regression;

    return (
      <div className="mini-stats-bar">
        <div className="mini-stat">
          <span className="mini-val">{mean.toFixed(1)}</span>
          <span className="mini-lbl">Avg {statLabel}</span>
        </div>
        <div className="mini-stat">
          <span className="mini-val">{dasData.das.games_fetched}/{dasData.das.games_total}</span>
          <span className="mini-lbl">Games</span>
        </div>
        {reg && <>
          <div className="mini-stat">
            <span className="mini-val">{reg.beta > 0 ? '+' : ''}{reg.beta.toFixed(2)}</span>
            <span className="mini-lbl">Beta</span>
          </div>
          <div className="mini-stat">
            <span className="mini-val">{(reg.r_squared * 100).toFixed(1)}%</span>
            <span className="mini-lbl">R-squared</span>
          </div>
          <div className="mini-stat">
            <span className="mini-val">{reg.p_value < 0.001 ? '<.001' : reg.p_value.toFixed(3)}</span>
            <span className="mini-lbl">p-value</span>
          </div>
        </>}
      </div>
    );
  };

  // ── Render: Player Deep Dive charts ──
  const renderPlayerCharts = () => {
    const das = dasData.das;
    const reg = das.regression;
    const perGame = das.per_game.filter(g => g.das !== null);
    const sorted = [...perGame].sort((a, b) => (a.date || '').localeCompare(b.date || ''));

    // Pre-compute stat z-scores for point coloring
    const vals = perGame.map(x => x.stat_value).filter(v => v != null);
    const statMean = vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
    const statStd = vals.length > 1
      ? Math.sqrt(vals.reduce((a, b) => a + Math.pow(b - statMean, 2), 0) / (vals.length - 1))
      : 1;

    return (
      <>
        {/* Interpretation */}
        {reg?.interpretation && (
          <p className="das-interpretation">{reg.interpretation}</p>
        )}

        {/* Dual-axis timeline: Stat + DAS */}
        <div className="chart-box">
          <Line
            data={{
              labels: sorted.map(g => `${g.opponent || '?'} ${(g.date || '').slice(5)}`),
              datasets: [
                {
                  label: statLabel,
                  data: sorted.map(g => g.stat_value),
                  borderColor: '#2c3e50',
                  backgroundColor: 'rgba(44, 62, 80, 0.06)',
                  fill: true,
                  tension: 0.3,
                  pointRadius: 5,
                  pointBackgroundColor: sorted.map(g => {
                    const z = statStd > 0 ? (g.stat_value - statMean) / statStd : 0;
                    return z > 1.5 ? '#27ae60' : z < -1.5 ? '#e74c3c' : '#2c3e50';
                  }),
                  yAxisID: 'y',
                  order: 2,
                },
                {
                  label: 'DAS',
                  data: sorted.map(g => g.das),
                  borderColor: '#e67e22',
                  backgroundColor: 'rgba(230, 126, 34, 0.08)',
                  fill: true,
                  tension: 0.3,
                  pointRadius: 4,
                  borderWidth: 2,
                  borderDash: [6, 3],
                  pointBackgroundColor: sorted.map(g =>
                    g.das > 1.0 ? '#e74c3c' : g.das > 0.5 ? '#e67e22' : g.das < -0.5 ? '#3498db' : '#95a5a6'
                  ),
                  yAxisID: 'y1',
                  order: 1,
                },
              ],
            }}
            options={{
              responsive: true,
              interaction: { mode: 'index', intersect: false },
              plugins: {
                title: { display: true, text: `${statLabel} vs Defensive Attention — Full Season` },
                tooltip: {
                  callbacks: {
                    afterBody: (ctxArr) => {
                      const idx = ctxArr[0]?.dataIndex;
                      if (idx == null) return '';
                      const g = sorted[idx];
                      return [
                        '',
                        `Usage: ${g.components?.usage_spike?.toFixed(2) ?? '—'}`,
                        `Openness: ${g.components?.shot_openness?.toFixed(2) ?? '—'}`,
                        `Suppression: ${g.components?.teammate_suppression?.toFixed(2) ?? '—'}`,
                        `Touches: ${g.components?.touch_increase?.toFixed(2) ?? '—'}`,
                        g.minutes ? `Min: ${g.minutes}` : '',
                      ];
                    }
                  }
                },
                legend: { labels: { usePointStyle: true, padding: 16 } },
              },
              scales: {
                y: {
                  type: 'linear', position: 'left',
                  title: { display: true, text: statLabel, color: '#2c3e50' },
                  ticks: { color: '#2c3e50' },
                  grid: { drawOnChartArea: true },
                },
                y1: {
                  type: 'linear', position: 'right',
                  title: { display: true, text: 'DAS', color: '#e67e22' },
                  ticks: { color: '#e67e22' },
                  grid: { drawOnChartArea: false },
                },
                x: { ticks: { maxRotation: 70, font: { size: 9 } } },
              }
            }}
          />
        </div>

        {/* Regression Scatter */}
        <div className="charts-grid">
          <div className="chart-box">
            <Scatter
              data={{
                datasets: [{
                  label: `DAS vs ${statLabel}`,
                  data: perGame.filter(g => g.stat_value != null).map(g => ({
                    x: g.das,
                    y: g.stat_value,
                  })),
                  backgroundColor: perGame.filter(g => g.stat_value != null).map(g =>
                    g.das > 1.0 ? 'rgba(231,76,60,0.7)' :
                    g.das > 0.5 ? 'rgba(230,126,34,0.7)' :
                    g.das < -0.5 ? 'rgba(52,152,219,0.7)' :
                    'rgba(149,165,166,0.7)'
                  ),
                  pointRadius: 6,
                },
                ...(reg && reg.beta !== null ? [{
                  label: `Trendline (\u03B2=${reg.beta.toFixed(2)})`,
                  data: (() => {
                    const minDas = Math.min(...perGame.map(g => g.das));
                    const maxDas = Math.max(...perGame.map(g => g.das));
                    return [
                      { x: minDas, y: reg.alpha + reg.beta * minDas },
                      { x: maxDas, y: reg.alpha + reg.beta * maxDas },
                    ];
                  })(),
                  type: 'line',
                  borderColor: '#e74c3c',
                  borderDash: [6, 3],
                  borderWidth: 2,
                  pointRadius: 0,
                  fill: false,
                }] : []),
              ]}}
              options={{
                responsive: true,
                plugins: {
                  title: { display: true, text: `DAS vs ${statLabel} — Regression` },
                  tooltip: {
                    callbacks: {
                      label: (ctx) => {
                        const g = perGame.filter(g => g.stat_value != null)[ctx.dataIndex];
                        if (!g) return '';
                        return `${g.opponent || ''} ${g.date || ''}: DAS ${g.das.toFixed(2)}, ${statLabel} ${g.stat_value}`;
                      }
                    }
                  }
                },
                scales: {
                  x: { title: { display: true, text: 'Defensive Attention Score' } },
                  y: { title: { display: true, text: statLabel } },
                }
              }}
            />
          </div>

          {/* Adjusted vs Raw Z-Score */}
          {reg?.per_game_adj_z?.length > 0 && (
            <div className="chart-box">
              <Bar
                data={{
                  labels: reg.per_game_adj_z
                    .sort((a, b) => {
                      const ga = perGame.find(g => g.game_id === a.game_id);
                      const gb = perGame.find(g => g.game_id === b.game_id);
                      return (ga?.date || '').localeCompare(gb?.date || '');
                    })
                    .map(g => {
                      const gm = perGame.find(x => x.game_id === g.game_id);
                      return gm ? `${gm.opponent || '?'} ${(gm.date || '').slice(5)}` : g.game_id.slice(-4);
                    }),
                  datasets: [
                    {
                      label: 'Raw Z-Score',
                      data: reg.per_game_adj_z.map(g => g.raw_z),
                      backgroundColor: 'rgba(52, 152, 219, 0.5)',
                      borderColor: '#3498db',
                      borderWidth: 1,
                    },
                    {
                      label: 'Adjusted Z-Score',
                      data: reg.per_game_adj_z.map(g => g.adjusted_z),
                      backgroundColor: 'rgba(230, 126, 34, 0.5)',
                      borderColor: '#e67e22',
                      borderWidth: 1,
                    },
                  ],
                }}
                options={{
                  responsive: true,
                  plugins: {
                    title: { display: true, text: 'Raw vs DAS-Adjusted Z-Scores' },
                    tooltip: {
                      callbacks: {
                        afterLabel: (ctx) => {
                          const g = reg.per_game_adj_z[ctx.dataIndex];
                          if (!g) return '';
                          return `Boost: ${g.das_boost?.toFixed(1) ?? '?'} ${statLabel}`;
                        }
                      }
                    }
                  },
                  scales: {
                    y: { title: { display: true, text: 'Z-Score' } },
                    x: { ticks: { maxRotation: 70, font: { size: 9 } } },
                  }
                }}
              />
            </div>
          )}
        </div>

        {/* Per-Game Table */}
        <div className="game-table-wrap">
          <h3>Per-Game Breakdown</h3>
          <table className="game-log-table">
            <thead>
              <tr>
                <th></th>
                <th>Date</th>
                <th>Opp</th>
                <th>H/A</th>
                <th>{statLabel}</th>
                <th>DAS</th>
                <th>Adj Z</th>
                <th>Usage</th>
                <th>Open</th>
                <th>Suppress</th>
                <th>Touches</th>
                <th>Min</th>
                <th>W/L</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((g, i) => (
                <React.Fragment key={g.game_id || i}>
                  <tr
                    className={`
                      ${(g.das || 0) > 1.0 ? 'das-high' : (g.das || 0) < -1.0 ? 'das-low' : ''}
                      ${expandedGame === g.game_id ? 'expanded-row' : ''}
                    `}
                    onClick={() => g.game_id && toggleGameExpand(g.game_id, g.team_id)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td className="expand-toggle">
                      {expandedGame === g.game_id ? '\u25BC' : '\u25B6'}
                    </td>
                    <td>{(g.date || '').slice(5)}</td>
                    <td>{g.opponent || '—'}</td>
                    <td>{g.is_home ? 'H' : 'A'}</td>
                    <td className="stat-val">{g.stat_value != null ? (perMinute ? g.stat_value.toFixed(2) : g.stat_value) : '—'}</td>
                    <td className={`das-val ${(g.das || 0) > 1 ? 'das-pos' : (g.das || 0) < -1 ? 'das-neg' : ''}`}>
                      {g.das?.toFixed(2) ?? '—'}
                    </td>
                    <td className={`z-val ${(g.adjusted_z || 0) > 1 ? 'pos' : (g.adjusted_z || 0) < -1 ? 'neg' : ''}`}>
                      {g.adjusted_z?.toFixed(2) ?? '—'}
                    </td>
                    <td>{g.components?.usage_spike?.toFixed(2) ?? '—'}</td>
                    <td>{g.components?.shot_openness?.toFixed(2) ?? '—'}</td>
                    <td>{g.components?.teammate_suppression?.toFixed(2) ?? '—'}</td>
                    <td>{g.components?.touch_increase?.toFixed(2) ?? '—'}</td>
                    <td>{g.minutes ?? '—'}</td>
                    <td className={g.result === 'W' ? 'win' : 'loss'}>{g.result || '—'}</td>
                  </tr>
                  {expandedGame === g.game_id && (
                    <tr className="detail-row">
                      <td colSpan={13}>
                        {renderGameDetail(g)}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </>
    );
  };

  // ── RENDER ──
  return (
    <div className="nba-analysis">
      {/* Header */}
      <div className="nba-header">
        <h1>NBA Factor Analysis</h1>
        <p>Quantify the hidden signals that drive player stat lines</p>
        <button className="glossary-btn" onClick={() => setShowGlossary(true)}>
          Glossary
        </button>
      </div>

      {renderGlossary()}

      {/* Factor Info Panel */}
      {(() => {
        const info = FACTOR_INFO[activeFactor];
        if (!info) return null;
        return (
          <div className="factor-info-panel">
            <button
              className="factor-info-toggle"
              onClick={() => setShowFactorInfo(!showFactorInfo)}
            >
              {showFactorInfo ? 'Hide' : 'What is'} {info.name}? {showFactorInfo ? '\u25B2' : '\u25BC'}
            </button>
            {showFactorInfo && (
              <div className="factor-info-body">
                <p className="factor-oneliner">{info.oneLiner}</p>

                <div className="factor-formula-box">
                  <span className="factor-formula-label">Formula</span>
                  <code>{info.formula}</code>
                </div>

                <div className="factor-signals">
                  <h4>The 4 Signals</h4>
                  {info.signals.map((s, i) => (
                    <div key={i} className="factor-signal">
                      <div className="signal-header">
                        <span className="signal-name">{s.name}</span>
                        <span className="signal-weight">{s.weight}</span>
                      </div>
                      <p className="signal-desc">{s.desc}</p>
                      <p className="signal-example"><em>Example:</em> {s.example}</p>
                    </div>
                  ))}
                </div>

                <div className="factor-interpretation">
                  <h4>How to Read DAS</h4>
                  <ul>
                    {info.interpretation.map((line, i) => (
                      <li key={i}>{line}</li>
                    ))}
                  </ul>
                </div>

                <div className="factor-example-box">
                  <h4>Worked Example: {info.example.player} {info.example.game}</h4>
                  <div className="example-headline">
                    <span className="example-line">{info.example.line}</span>
                    <span className="example-das">DAS {info.example.das}</span>
                  </div>
                  <p>{info.example.story}</p>
                </div>
              </div>
            )}
          </div>
        );
      })()}

      {/* Controls Bar */}
      <div className="nba-controls">
        <div className="control-group">
          <label>Factor</label>
          <select value={activeFactor} onChange={e => setActiveFactor(e.target.value)}>
            {FACTORS.map(f => (
              <option key={f.key} value={f.key}>{f.label}</option>
            ))}
          </select>
        </div>

        <div className="control-group">
          <label>Stat</label>
          <select value={stat} onChange={e => setStat(e.target.value)}>
            {statsList.map(s => <option key={s.key || s} value={s.key || s}>{s.label || s.key || s}</option>)}
          </select>
        </div>

        <div className="control-group">
          <label>Season</label>
          <select value={season} onChange={e => setSeason(e.target.value)}>
            <option value="2025-26">2025-26</option>
            <option value="2024-25">2024-25</option>
            <option value="2023-24">2023-24</option>
          </select>
        </div>

        <div className="control-group">
          <label>Mode</label>
          <div className="rate-toggle">
            <button className={`rate-btn ${!perMinute ? 'active' : ''}`} onClick={() => setPerMinute(false)}>Raw</button>
            <button className={`rate-btn ${perMinute ? 'active' : ''}`} onClick={() => setPerMinute(true)}>Per Min</button>
          </div>
        </div>

        <div className="view-toggle">
          <button className={`view-btn ${viewMode === 'player' ? 'active' : ''}`} onClick={() => setViewMode('player')}>
            Player Deep Dive
          </button>
          <button className={`view-btn ${viewMode === 'leaderboard' ? 'active' : ''}`} onClick={() => setViewMode('leaderboard')}>
            League Leaderboard
          </button>
        </div>
      </div>

      {error && <div className="nba-error">{error}</div>}

      {/* ─── PLAYER DEEP DIVE ─── */}
      {viewMode === 'player' && (
        <div className="player-view">
          <div className="player-search-row">
            <div className="control-group player-search">
              <label>Player</label>
              <div className="search-wrapper">
                <input
                  value={playerName}
                  onChange={e => { setPlayerName(e.target.value); searchPlayers(e.target.value); }}
                  onFocus={() => searchResults.length > 0 && setShowSearch(true)}
                  placeholder="Search player..."
                />
                {showSearch && searchResults.length > 0 && (
                  <div className="search-dropdown">
                    {searchResults.map(p => (
                      <div key={p.id} className="search-item" onClick={() => selectPlayer(p.full_name)}>
                        {p.full_name}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <button className="analyze-btn" onClick={fetchDefensiveAttention} disabled={dasLoading}>
              {dasLoading ? 'Analyzing...' : 'Analyze'}
            </button>
          </div>

          {availablePlayers.length > 0 && !dasData && !dasLoading && (
            <div className="available-players">
              <span className="available-label">Quick pick:</span>
              {availablePlayers.map(p => (
                <button key={p.slug} className="player-chip" onClick={() => quickPickPlayer(p.name)}>
                  {p.name}
                </button>
              ))}
            </div>
          )}

          {/* Loading */}
          {dasLoading && (
            <div className="das-loading">
              <div className="loading-spinner" />
              <p>Computing {FACTORS.find(f => f.key === activeFactor)?.label}...</p>
              <div className="das-progress-bar-wrap">
                <div className="das-progress-bar" style={{ width: `${dasProgress}%` }} />
              </div>
              <p className="loading-sub">Fetching per-game tracking data from NBA API (3 calls per game)</p>
            </div>
          )}

          {/* Results */}
          {dasData && !dasLoading && (
            <>
              {renderMiniStatsBar()}
              {renderPlayerCharts()}
            </>
          )}
        </div>
      )}

      {/* ─── LEAGUE LEADERBOARD ─── */}
      {viewMode === 'leaderboard' && (
        <div className="leaderboard-view">
          {!leaderboardLoading && !leaderboardData && (
            <div className="leaderboard-start">
              <p>Compute {FACTORS.find(f => f.key === activeFactor)?.label} for the top 20 {stat} leaders this season.</p>
              <button className="analyze-btn" onClick={loadLeaderboard}>Load Leaderboard</button>
              <p className="loading-sub">First run takes 15-30 min (cached after). Results appear as each player completes.</p>
            </div>
          )}

          {leaderboardLoading && (
            <div className="leaderboard-progress">
              <div className="loading-spinner" />
              <p>Analyzing player {leaderboardProgress.current}/{leaderboardProgress.total}: <strong>{leaderboardProgress.playerName}</strong></p>
              <div className="das-progress-bar-wrap">
                <div className="das-progress-bar" style={{ width: `${(leaderboardProgress.current / Math.max(leaderboardProgress.total, 1)) * 100}%` }} />
              </div>
              <p className="loading-sub">Each player takes 30-90s. Results appear as they finish.</p>
            </div>
          )}

          {leaderboardData && (
            <>
              {/* Top Games Table */}
              <div className="leaderboard-table-wrap">
                <h3>Top Games by {FACTORS.find(f => f.key === activeFactor)?.label}</h3>
                <table className="game-log-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Player</th>
                      <th>Date</th>
                      <th>Opp</th>
                      <th>{statLabel}</th>
                      <th>DAS</th>
                      <th>Usage</th>
                      <th>Open</th>
                      <th>Suppress</th>
                      <th>Touches</th>
                    </tr>
                  </thead>
                  <tbody>
                    {leaderboardData.allGames.slice(0, 100).map((g, i) => (
                      <tr key={`${g.game_id}-${g.player_name}-${i}`}
                        className={g.das > 1.5 ? 'das-high' : g.das < -1.0 ? 'das-low' : ''}
                      >
                        <td>{i + 1}</td>
                        <td><strong>{g.player_name}</strong> <span className="team-tag">{g.player_team}</span></td>
                        <td>{(g.date || '').slice(5)}</td>
                        <td>{g.opponent || '—'}</td>
                        <td className="stat-val">{g.stat_value != null ? (perMinute ? g.stat_value.toFixed(2) : g.stat_value) : '—'}</td>
                        <td className={`das-val ${g.das > 1 ? 'das-pos' : g.das < -1 ? 'das-neg' : ''}`}>
                          {g.das?.toFixed(2)}
                        </td>
                        <td>{g.components?.usage_spike?.toFixed(2) ?? '—'}</td>
                        <td>{g.components?.shot_openness?.toFixed(2) ?? '—'}</td>
                        <td>{g.components?.teammate_suppression?.toFixed(2) ?? '—'}</td>
                        <td>{g.components?.touch_increase?.toFixed(2) ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Aggregation: by player + by team */}
              <div className="aggregation-grid">
                {/* By Player */}
                <div className="agg-section">
                  <h3>By Player — Who Gets Funneled To</h3>
                  <table className="game-log-table compact">
                    <thead>
                      <tr>
                        <th>Player</th>
                        <th>Team</th>
                        <th>Avg {statLabel}</th>
                        <th>Avg DAS</th>
                        <th>Beta</th>
                        <th>R\u00B2</th>
                      </tr>
                    </thead>
                    <tbody>
                      {leaderboardData.playerSummaries.map(p => (
                        <tr key={p.player_name}
                          className={p.avg_das > 0.3 ? 'das-high' : p.avg_das < -0.3 ? 'das-low' : ''}
                        >
                          <td><strong>{p.player_name}</strong></td>
                          <td>{p.team}</td>
                          <td>{p.avg_stat?.toFixed(1)}</td>
                          <td className={`das-val ${p.avg_das > 0.3 ? 'das-pos' : p.avg_das < -0.3 ? 'das-neg' : ''}`}>
                            {p.avg_das?.toFixed(3)}
                          </td>
                          <td>{p.beta != null ? `${p.beta > 0 ? '+' : ''}${p.beta.toFixed(2)}` : '—'}</td>
                          <td>{p.r_squared != null ? `${(p.r_squared * 100).toFixed(1)}%` : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* By Opponent Team */}
                <div className="agg-section">
                  <h3>By Opponent — Which Defenses Funnel</h3>
                  <table className="game-log-table compact">
                    <thead>
                      <tr>
                        <th>Opponent</th>
                        <th>Games</th>
                        <th>Avg {statLabel}</th>
                        <th>Avg DAS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {leaderboardData.byTeam?.map(t => (
                        <tr key={t.team}
                          className={t.avgDas > 0.3 ? 'das-high' : t.avgDas < -0.3 ? 'das-low' : ''}
                        >
                          <td><strong>{t.team}</strong></td>
                          <td>{t.games}</td>
                          <td>{t.avgStat?.toFixed(1)}</td>
                          <td className={`das-val ${t.avgDas > 0.3 ? 'das-pos' : t.avgDas < -0.3 ? 'das-neg' : ''}`}>
                            {t.avgDas?.toFixed(3)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default NbaPlayerAnalysis;
