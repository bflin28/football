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

const NbaPlayerAnalysis = () => {
  const [playerName, setPlayerName] = useState('Nikola Jokic');
  const [stat, setStat] = useState('AST');
  const [season, setSeason] = useState('2024-25');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [statsList, setStatsList] = useState([]);
  const [searchResults, setSearchResults] = useState([]);
  const [showSearch, setShowSearch] = useState(false);
  const [activeSection, setActiveSection] = useState('overview');
  const [playTypeData, setPlayTypeData] = useState(null);
  const [matchupData, setMatchupData] = useState(null);
  const [playTypeLoading, setPlayTypeLoading] = useState(false);

  useEffect(() => {
    fetch('/api/nba/stats-list')
      .then(r => r.json())
      .then(setStatsList)
      .catch(() => {});
  }, []);

  const runAnalysis = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ player: playerName, stat, season });
      const res = await fetch(`/api/nba/analyze?${params}`);
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || 'Analysis failed');
      setData(json);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchPlayTypes = async () => {
    setPlayTypeLoading(true);
    try {
      const params = new URLSearchParams({ player: playerName, season });
      const [ptRes, matchRes] = await Promise.all([
        fetch(`/api/nba/play-types/player?${params}`),
        fetch(`/api/nba/play-types/matchup?${new URLSearchParams({ player: playerName, stat, season })}`),
      ]);
      if (ptRes.ok) setPlayTypeData(await ptRes.json());
      if (matchRes.ok) setMatchupData(await matchRes.json());
    } catch { /* non-critical */ }
    finally { setPlayTypeLoading(false); }
  };

  const searchPlayers = async (q) => {
    setPlayerName(q);
    if (q.length < 2) { setSearchResults([]); return; }
    try {
      const res = await fetch(`/api/nba/players/search?q=${encodeURIComponent(q)}`);
      const results = await res.json();
      setSearchResults(results);
      setShowSearch(true);
    } catch { setSearchResults([]); }
  };

  const selectPlayer = (name) => {
    setPlayerName(name);
    setShowSearch(false);
    setSearchResults([]);
  };

  // ── Charts ──────────────────────────────────────────────────────────────

  const renderZScoreTimeline = () => {
    if (!data?.games) return null;
    const games = data.games;

    const chartData = {
      labels: games.map(g => g.date.slice(5)), // MM-DD
      datasets: [
        {
          label: `${data.stat} Z-Score`,
          data: games.map(g => g.z_score),
          borderColor: games.map(g =>
            g.z_score > 1.5 ? '#27ae60' : g.z_score < -1.5 ? '#e74c3c' : '#3498db'
          ),
          backgroundColor: games.map(g =>
            g.z_score > 1.5 ? 'rgba(39,174,96,0.3)' : g.z_score < -1.5 ? 'rgba(231,76,60,0.3)' : 'rgba(52,152,219,0.3)'
          ),
          borderWidth: 2,
          pointRadius: 6,
          pointHoverRadius: 9,
          fill: false,
          tension: 0.1,
        },
        {
          label: '+1.5 SD',
          data: games.map(() => 1.5),
          borderColor: 'rgba(39,174,96,0.4)',
          borderDash: [5, 5],
          pointRadius: 0,
          borderWidth: 1,
          fill: false,
        },
        {
          label: '-1.5 SD',
          data: games.map(() => -1.5),
          borderColor: 'rgba(231,76,60,0.4)',
          borderDash: [5, 5],
          pointRadius: 0,
          borderWidth: 1,
          fill: false,
        },
        {
          label: 'Mean (0)',
          data: games.map(() => 0),
          borderColor: 'rgba(0,0,0,0.2)',
          borderDash: [3, 3],
          pointRadius: 0,
          borderWidth: 1,
          fill: false,
        }
      ]
    };

    const options = {
      responsive: true,
      plugins: {
        title: { display: true, text: `${data.player.name} — ${data.stat} Z-Scores by Game`, font: { size: 16, weight: 'bold' } },
        tooltip: {
          callbacks: {
            afterLabel: (ctx) => {
              if (ctx.datasetIndex !== 0) return '';
              const g = games[ctx.dataIndex];
              return [
                `${data.stat}: ${g.stat_value}`,
                `vs ${g.opponent} (${g.is_home ? 'Home' : 'Away'})`,
                `Result: ${g.result} (${g.plus_minus > 0 ? '+' : ''}${g.plus_minus})`,
                `Rest: ${g.rest_days}d${g.is_back_to_back ? ' (B2B)' : ''}`,
                `Minutes: ${g.minutes?.toFixed(0) || '?'}`,
              ];
            }
          }
        }
      },
      scales: {
        y: { title: { display: true, text: 'Z-Score (standard deviations from mean)' } },
        x: { title: { display: true, text: 'Game Date' }, ticks: { maxRotation: 45 } }
      }
    };

    return <Line data={chartData} options={options} />;
  };

  const renderHistogram = () => {
    if (!data?.histogram) return null;
    const { counts, edges } = data.histogram;
    const labels = counts.map((_, i) => {
      const lo = edges[i];
      const hi = edges[i + 1];
      return `${lo.toFixed(0)}-${hi.toFixed(0)}`;
    });

    const chartData = {
      labels,
      datasets: [{
        label: `${data.stat} Distribution`,
        data: counts,
        backgroundColor: 'rgba(52,152,219,0.6)',
        borderColor: 'rgba(52,152,219,1)',
        borderWidth: 1,
        borderRadius: 4,
      }]
    };

    const options = {
      responsive: true,
      plugins: {
        title: { display: true, text: `${data.stat} Distribution (n=${data.summary.games_played})`, font: { size: 16, weight: 'bold' } },
        legend: { display: false }
      },
      scales: {
        y: { title: { display: true, text: 'Frequency' }, beginAtZero: true },
        x: { title: { display: true, text: data.stat } }
      }
    };

    return <Bar data={chartData} options={options} />;
  };

  const renderOpponentChart = () => {
    if (!data?.factors?.opponent_effect?.breakdown) return null;
    const breakdown = data.factors.opponent_effect.breakdown;

    const chartData = {
      labels: breakdown.map(o => o.opponent),
      datasets: [{
        label: `Avg ${data.stat}`,
        data: breakdown.map(o => o.mean),
        backgroundColor: breakdown.map(o =>
          o.mean > data.summary.mean + data.summary.std ? 'rgba(39,174,96,0.7)' :
          o.mean < data.summary.mean - data.summary.std ? 'rgba(231,76,60,0.7)' :
          'rgba(52,152,219,0.7)'
        ),
        borderWidth: 1,
        borderRadius: 4,
      }]
    };

    const options = {
      responsive: true,
      indexAxis: 'y',
      plugins: {
        title: { display: true, text: `${data.stat} by Opponent`, font: { size: 16, weight: 'bold' } },
        legend: { display: false },
        tooltip: {
          callbacks: {
            afterLabel: (ctx) => {
              const o = breakdown[ctx.dataIndex];
              return [`Games: ${o.games}`, `Std: ${o.std.toFixed(1)}`];
            }
          }
        }
      },
      scales: {
        x: {
          title: { display: true, text: `Avg ${data.stat}` },
          beginAtZero: true,
        }
      }
    };

    return <Bar data={chartData} options={options} />;
  };

  const renderGameValueChart = () => {
    if (!data?.games) return null;
    const games = data.games;

    const chartData = {
      labels: games.map(g => g.date.slice(5)),
      datasets: [{
        label: data.stat,
        data: games.map(g => g.stat_value),
        borderColor: '#8e44ad',
        backgroundColor: 'rgba(142,68,173,0.15)',
        borderWidth: 2,
        pointRadius: 5,
        pointHoverRadius: 8,
        fill: true,
        tension: 0.2,
      }, {
        label: 'Season Mean',
        data: games.map(() => data.summary.mean),
        borderColor: 'rgba(0,0,0,0.3)',
        borderDash: [5, 5],
        pointRadius: 0,
        borderWidth: 2,
        fill: false,
      }]
    };

    const options = {
      responsive: true,
      plugins: {
        title: { display: true, text: `${data.stat} Raw Values Over Season`, font: { size: 16, weight: 'bold' } },
        tooltip: {
          callbacks: {
            afterLabel: (ctx) => {
              if (ctx.datasetIndex !== 0) return '';
              const g = games[ctx.dataIndex];
              return `vs ${g.opponent} (${g.is_home ? 'H' : 'A'}) — ${g.result}`;
            }
          }
        }
      },
      scales: {
        y: { title: { display: true, text: data.stat }, beginAtZero: true },
        x: { title: { display: true, text: 'Game Date' }, ticks: { maxRotation: 45 } }
      }
    };

    return <Line data={chartData} options={options} />;
  };

  // ── Play Type Charts ────────────────────────────────────────────────────

  const renderOffensivePlayTypes = () => {
    if (!playTypeData?.offensive?.length) return null;
    const items = playTypeData.offensive.filter(p => p.possessions > 0);

    const chartData = {
      labels: items.map(p => p.label),
      datasets: [
        {
          label: 'PPP (Points Per Possession)',
          data: items.map(p => p.ppp),
          backgroundColor: items.map(p =>
            p.percentile >= 75 ? 'rgba(39,174,96,0.7)' :
            p.percentile <= 25 ? 'rgba(231,76,60,0.7)' :
            'rgba(52,152,219,0.7)'
          ),
          borderWidth: 1,
          borderRadius: 4,
        }
      ]
    };

    const options = {
      responsive: true,
      indexAxis: 'y',
      plugins: {
        title: { display: true, text: `${playTypeData.team} Offensive Play Types — PPP`, font: { size: 16, weight: 'bold' } },
        legend: { display: false },
        tooltip: {
          callbacks: {
            afterLabel: (ctx) => {
              const p = items[ctx.dataIndex];
              return [
                `Percentile: ${(p.percentile * 100).toFixed(0)}th`,
                `Freq: ${(p.poss_pct * 100).toFixed(1)}%`,
                `FG%: ${(p.fg_pct * 100).toFixed(1)}%`,
                `Possessions: ${p.possessions}`,
              ];
            }
          }
        }
      },
      scales: {
        x: { title: { display: true, text: 'Points Per Possession' }, beginAtZero: true },
      }
    };

    return <Bar data={chartData} options={options} />;
  };

  const renderDefensivePlayTypes = () => {
    if (!playTypeData?.defensive?.length) return null;
    const items = playTypeData.defensive.filter(p => p.possessions > 0);

    const chartData = {
      labels: items.map(p => p.label),
      datasets: [
        {
          label: 'PPP Allowed',
          data: items.map(p => p.ppp),
          backgroundColor: items.map(p =>
            p.percentile >= 75 ? 'rgba(39,174,96,0.7)' :   // good defense
            p.percentile <= 25 ? 'rgba(231,76,60,0.7)' :   // bad defense
            'rgba(241,196,15,0.7)'
          ),
          borderWidth: 1,
          borderRadius: 4,
        }
      ]
    };

    const options = {
      responsive: true,
      indexAxis: 'y',
      plugins: {
        title: { display: true, text: `${playTypeData.team} Defensive Play Types — PPP Allowed`, font: { size: 16, weight: 'bold' } },
        legend: { display: false },
        tooltip: {
          callbacks: {
            afterLabel: (ctx) => {
              const p = items[ctx.dataIndex];
              return [
                `Percentile: ${(p.percentile * 100).toFixed(0)}th`,
                `Freq: ${(p.poss_pct * 100).toFixed(1)}%`,
                `Opp FG%: ${(p.fg_pct * 100).toFixed(1)}%`,
              ];
            }
          }
        }
      },
      scales: {
        x: { title: { display: true, text: 'PPP Allowed (lower = better defense)' }, beginAtZero: true },
      }
    };

    return <Bar data={chartData} options={options} />;
  };

  const renderSchemeMatchupTable = () => {
    if (!matchupData?.matchups?.length) return null;
    const mean = data?.summary?.mean || 0;
    const std = data?.summary?.std || 1;

    return (
      <div className="scheme-matchup-section">
        <h3>Opponent Scheme Matchups — {matchupData.stat} vs Defensive Weaknesses</h3>
        <p className="scheme-subtitle">
          Each opponent's top defensive weaknesses (lowest Synergy percentile = worst defense in that play type).
          Green rows = player performed above average vs that team.
        </p>
        <div className="opp-table-wrap">
          <table className="opp-table scheme-table">
            <thead>
              <tr>
                <th>Opponent</th>
                <th>Avg {matchupData.stat}</th>
                <th>Games</th>
                <th>Worst Defensive Play Type</th>
                <th>PPP Allowed</th>
                <th>Def Percentile</th>
              </tr>
            </thead>
            <tbody>
              {matchupData.matchups.map(m => {
                const diff = m.stat_avg - mean;
                const weakness = m.defensive_weaknesses[0];
                return (
                  <tr key={m.opponent} className={diff > std ? 'above' : diff < -std ? 'below' : ''}>
                    <td>{m.opponent}</td>
                    <td className={diff > 0 ? 'positive' : 'negative'}>
                      {m.stat_avg.toFixed(1)}
                    </td>
                    <td>{m.games}</td>
                    <td>{weakness?.label || '—'}</td>
                    <td>{weakness?.ppp_allowed?.toFixed(3) || '—'}</td>
                    <td>
                      {weakness?.percentile != null ? (
                        <span className={`pctile-badge ${weakness.percentile <= 0.25 ? 'bad' : weakness.percentile >= 0.75 ? 'good' : 'mid'}`}>
                          {(weakness.percentile * 100).toFixed(0)}th
                        </span>
                      ) : '—'}
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

  // ── Factor Cards ──────────────────────────────────────────────────────────

  const renderFactorCard = (title, factor, description) => {
    if (!factor) return null;
    const sig = factor.significant;

    return (
      <div className={`factor-card ${sig ? 'significant' : 'not-significant'}`}>
        <div className="factor-header">
          <h4>{title}</h4>
          <span className={`factor-badge ${sig ? 'sig' : 'not-sig'}`}>
            {sig ? 'SIGNIFICANT' : 'Not significant'}
          </span>
        </div>
        <p className="factor-desc">{description}</p>
        <div className="factor-details">
          {factor.p_value !== undefined && (
            <div className="factor-stat">
              <span className="factor-stat-label">p-value</span>
              <span className="factor-stat-value">{factor.p_value.toFixed(4)}</span>
            </div>
          )}
          {factor.correlation !== undefined && (
            <div className="factor-stat">
              <span className="factor-stat-label">Correlation</span>
              <span className="factor-stat-value">{factor.correlation.toFixed(3)}</span>
            </div>
          )}
          {factor.interpretation && (
            <p className="factor-interpretation">{factor.interpretation}</p>
          )}
          {factor.home_mean !== undefined && (
            <div className="factor-comparison">
              <div className="comp-item">
                <span className="comp-label">Home</span>
                <span className="comp-value">{factor.home_mean.toFixed(1)}</span>
                <span className="comp-n">({factor.home_n} games)</span>
              </div>
              <div className="comp-item">
                <span className="comp-label">Away</span>
                <span className="comp-value">{factor.away_mean.toFixed(1)}</span>
                <span className="comp-n">({factor.away_n} games)</span>
              </div>
            </div>
          )}
          {factor.win_mean !== undefined && (
            <div className="factor-comparison">
              <div className="comp-item">
                <span className="comp-label">Wins</span>
                <span className="comp-value">{factor.win_mean.toFixed(1)}</span>
                <span className="comp-n">({factor.win_n} games)</span>
              </div>
              <div className="comp-item">
                <span className="comp-label">Losses</span>
                <span className="comp-value">{factor.loss_mean.toFixed(1)}</span>
                <span className="comp-n">({factor.loss_n} games)</span>
              </div>
            </div>
          )}
          {factor.b2b_mean !== undefined && (
            <div className="factor-comparison">
              <div className="comp-item">
                <span className="comp-label">Back-to-back</span>
                <span className="comp-value">{factor.b2b_mean.toFixed(1)}</span>
                <span className="comp-n">({factor.b2b_n} games)</span>
              </div>
              <div className="comp-item">
                <span className="comp-label">Rested</span>
                <span className="comp-value">{factor.rested_mean.toFixed(1)}</span>
                <span className="comp-n">({factor.rested_n} games)</span>
              </div>
            </div>
          )}
          {factor.cohens_d !== undefined && (
            <div className="factor-stat">
              <span className="factor-stat-label">Effect size</span>
              <span className="factor-stat-value">{factor.effect_size} (d={factor.cohens_d.toFixed(2)})</span>
            </div>
          )}
        </div>
      </div>
    );
  };

  // ── Normality Test Cards ──────────────────────────────────────────────────

  const renderDistributionTests = () => {
    if (!data?.distribution_tests) return null;
    const tests = data.distribution_tests;

    return (
      <div className="dist-tests">
        <h3>Is this distribution random (normal)?</h3>
        <p className="dist-subtitle">
          If the stat is just random noise, it should follow a normal (bell curve) distribution.
          Deviations suggest hidden factors are influencing the outcomes.
        </p>

        <div className="test-cards">
          {tests.shapiro_wilk && (
            <div className={`test-card ${tests.shapiro_wilk.normal ? 'normal' : 'not-normal'}`}>
              <h4>Shapiro-Wilk Test</h4>
              <p className="test-verdict">{tests.shapiro_wilk.interpretation}</p>
              <div className="test-stats">
                <span>W = {tests.shapiro_wilk.statistic.toFixed(4)}</span>
                <span>p = {tests.shapiro_wilk.p_value.toFixed(4)}</span>
              </div>
              <p className="test-explain">Gold standard normality test. p &lt; 0.05 means NOT normal.</p>
            </div>
          )}

          {tests.dagostino && (
            <div className={`test-card ${tests.dagostino.normal ? 'normal' : 'not-normal'}`}>
              <h4>D'Agostino-Pearson Test</h4>
              <p className="test-verdict">{tests.dagostino.interpretation}</p>
              <div className="test-stats">
                <span>K2 = {tests.dagostino.statistic.toFixed(4)}</span>
                <span>p = {tests.dagostino.p_value.toFixed(4)}</span>
              </div>
              <p className="test-explain">Tests both skewness and kurtosis together.</p>
            </div>
          )}

          {tests.anderson_darling && (
            <div className={`test-card ${tests.anderson_darling.normal ? 'normal' : 'not-normal'}`}>
              <h4>Anderson-Darling Test</h4>
              <p className="test-verdict">{tests.anderson_darling.interpretation}</p>
              <div className="test-stats">
                <span>A2 = {tests.anderson_darling.statistic.toFixed(4)}</span>
                <span>Critical (5%) = {tests.anderson_darling.critical_value_5pct.toFixed(4)}</span>
              </div>
              <p className="test-explain">Sensitive to distribution tails. Statistic must be below critical value for normality.</p>
            </div>
          )}

          {tests.shape && (
            <div className="test-card shape">
              <h4>Distribution Shape</h4>
              <div className="shape-stats">
                <div className="shape-item">
                  <span className="shape-label">Skewness</span>
                  <span className="shape-value">{tests.shape.skewness.toFixed(3)}</span>
                  <span className="shape-interp">{tests.shape.skew_interpretation}</span>
                </div>
                <div className="shape-item">
                  <span className="shape-label">Kurtosis</span>
                  <span className="shape-value">{tests.shape.kurtosis.toFixed(3)}</span>
                  <span className="shape-interp">{tests.shape.kurtosis_interpretation}</span>
                </div>
              </div>
              <p className="test-explain">Normal distribution has skewness ~ 0 and kurtosis ~ 0.</p>
            </div>
          )}
        </div>
      </div>
    );
  };

  // ── Main Render ───────────────────────────────────────────────────────────

  return (
    <div className="nba-analysis">
      <div className="nba-header">
        <h1>NBA Player Z-Score Analysis</h1>
        <p>Analyze if a player's stats are randomly distributed or driven by hidden factors</p>
      </div>

      {/* Controls */}
      <div className="nba-controls">
        <div className="control-group player-search">
          <label>Player</label>
          <div className="search-wrapper">
            <input
              type="text"
              value={playerName}
              onChange={e => searchPlayers(e.target.value)}
              onFocus={() => searchResults.length > 0 && setShowSearch(true)}
              onBlur={() => setTimeout(() => setShowSearch(false), 200)}
              placeholder="Search player..."
            />
            {showSearch && searchResults.length > 0 && (
              <div className="search-dropdown">
                {searchResults.map(p => (
                  <button key={p.id} onMouseDown={() => selectPlayer(p.name)}>
                    {p.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="control-group">
          <label>Stat</label>
          <select value={stat} onChange={e => setStat(e.target.value)}>
            {statsList.map(s => (
              <option key={s.key} value={s.key}>{s.label}</option>
            ))}
          </select>
        </div>

        <div className="control-group">
          <label>Season</label>
          <select value={season} onChange={e => setSeason(e.target.value)}>
            <option value="2024-25">2024-25</option>
            <option value="2023-24">2023-24</option>
            <option value="2022-23">2022-23</option>
          </select>
        </div>

        <button className="analyze-btn" onClick={runAnalysis} disabled={loading}>
          {loading ? 'Analyzing...' : 'Analyze'}
        </button>
      </div>

      {error && <div className="nba-error">{error}</div>}

      {loading && (
        <div className="nba-loading">
          <div className="loading-spinner"></div>
          <p>Fetching data from NBA.com and running analysis...</p>
          <p className="loading-sub">First load may take 10-15 seconds</p>
        </div>
      )}

      {data && !loading && (
        <>
          {/* Summary Cards */}
          <div className="summary-grid">
            <div className="summary-card primary">
              <div className="summary-value">{data.summary.mean.toFixed(1)}</div>
              <div className="summary-label">Season Avg</div>
            </div>
            <div className="summary-card">
              <div className="summary-value">{data.summary.std.toFixed(2)}</div>
              <div className="summary-label">Std Dev</div>
            </div>
            <div className="summary-card">
              <div className="summary-value">{data.summary.median}</div>
              <div className="summary-label">Median</div>
            </div>
            <div className="summary-card">
              <div className="summary-value">{data.summary.min}-{data.summary.max}</div>
              <div className="summary-label">Range</div>
            </div>
            <div className="summary-card">
              <div className="summary-value">{data.summary.games_played}</div>
              <div className="summary-label">Games</div>
            </div>
            <div className="summary-card">
              <div className="summary-value">{(data.summary.cv * 100).toFixed(0)}%</div>
              <div className="summary-label">CV (variability)</div>
            </div>
          </div>

          {/* Section Nav */}
          <div className="section-nav">
            {['overview', 'distribution', 'factors', 'opponents', 'playtypes'].map(s => (
              <button
                key={s}
                className={`section-btn ${activeSection === s ? 'active' : ''}`}
                onClick={() => {
                  setActiveSection(s);
                  if (s === 'playtypes' && !playTypeData && !playTypeLoading) fetchPlayTypes();
                }}
              >
                {s === 'overview' && 'Z-Score Timeline'}
                {s === 'distribution' && 'Distribution Tests'}
                {s === 'factors' && 'Factor Analysis'}
                {s === 'opponents' && 'By Opponent'}
                {s === 'playtypes' && 'Play Types'}
              </button>
            ))}
          </div>

          {/* Sections */}
          <div className="section-content">
            {activeSection === 'overview' && (
              <div className="charts-grid">
                <div className="chart-box">{renderZScoreTimeline()}</div>
                <div className="chart-box">{renderGameValueChart()}</div>
              </div>
            )}

            {activeSection === 'distribution' && (
              <div>
                <div className="chart-box">{renderHistogram()}</div>
                {renderDistributionTests()}
              </div>
            )}

            {activeSection === 'factors' && (
              <div className="factors-grid">
                {renderFactorCard(
                  'Home vs Away',
                  data.factors.home_away,
                  `Does playing at home affect ${data.stat}?`
                )}
                {renderFactorCard(
                  'Win vs Loss',
                  data.factors.win_loss,
                  `Does the game outcome correlate with ${data.stat}?`
                )}
                {renderFactorCard(
                  'Back-to-Back',
                  data.factors.back_to_back,
                  `Does playing on consecutive days affect ${data.stat}?`
                )}
                {renderFactorCard(
                  'Rest Days',
                  data.factors.rest_days,
                  `Does more rest lead to higher/lower ${data.stat}?`
                )}
                {renderFactorCard(
                  'Minutes Played',
                  data.factors.minutes,
                  `How strongly do minutes predict ${data.stat}?`
                )}
                {renderFactorCard(
                  'Point Differential',
                  data.factors.point_differential,
                  `Do blowouts affect ${data.stat} output?`
                )}
                {renderFactorCard(
                  'Season Trend',
                  data.factors.season_trend,
                  `Is ${data.stat} trending up or down as the season progresses?`
                )}
                {renderFactorCard(
                  'Opponent Effect',
                  data.factors.opponent_effect,
                  `Does the opponent significantly affect ${data.stat}? (ANOVA test across teams)`
                )}
              </div>
            )}

            {activeSection === 'opponents' && (
              <div>
                <div className="chart-box">{renderOpponentChart()}</div>
                {data.factors.opponent_effect && (
                  <div className="opp-table-wrap">
                    <table className="opp-table">
                      <thead>
                        <tr>
                          <th>Opponent</th>
                          <th>Avg {data.stat}</th>
                          <th>Std</th>
                          <th>Games</th>
                          <th>vs Mean</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.factors.opponent_effect.breakdown.map(o => {
                          const diff = o.mean - data.summary.mean;
                          return (
                            <tr key={o.opponent} className={diff > data.summary.std ? 'above' : diff < -data.summary.std ? 'below' : ''}>
                              <td>{o.opponent}</td>
                              <td>{o.mean.toFixed(1)}</td>
                              <td>{o.std.toFixed(1)}</td>
                              <td>{o.games}</td>
                              <td className={diff > 0 ? 'positive' : 'negative'}>
                                {diff > 0 ? '+' : ''}{diff.toFixed(1)}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {activeSection === 'playtypes' && (
              <div className="play-types-section">
                {playTypeLoading && (
                  <div className="nba-loading">
                    <div className="loading-spinner"></div>
                    <p>Fetching Synergy play type data...</p>
                    <p className="loading-sub">This pulls scheme data from NBA.com</p>
                  </div>
                )}

                {!playTypeLoading && playTypeData && (
                  <>
                    <div className="pt-intro">
                      <h3>Offensive & Defensive Scheme Breakdown</h3>
                      <p>Synergy Sports play type data for {playTypeData.team}. Shows how the team generates offense
                        and defends each play type. Percentile rank: green = top quartile, red = bottom quartile.</p>
                    </div>

                    {/* Offensive play type frequency breakdown */}
                    {playTypeData.offensive?.length > 0 && (
                      <div className="pt-freq-grid">
                        {playTypeData.offensive.filter(p => p.possessions > 0).map(p => (
                          <div key={p.play_type} className={`pt-freq-card ${
                            p.percentile >= 0.75 ? 'elite' : p.percentile <= 0.25 ? 'weak' : ''
                          }`}>
                            <div className="pt-freq-name">{p.label}</div>
                            <div className="pt-freq-ppp">{p.ppp?.toFixed(3) || '—'} PPP</div>
                            <div className="pt-freq-bar-wrap">
                              <div className="pt-freq-bar" style={{ width: `${(p.poss_pct || 0) * 100}%` }} />
                            </div>
                            <div className="pt-freq-meta">
                              <span>{((p.poss_pct || 0) * 100).toFixed(1)}% freq</span>
                              <span className={`pctile-badge ${p.percentile >= 0.75 ? 'good' : p.percentile <= 0.25 ? 'bad' : 'mid'}`}>
                                {((p.percentile || 0) * 100).toFixed(0)}th pctile
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="charts-grid" style={{ marginTop: 20 }}>
                      <div className="chart-box">{renderOffensivePlayTypes()}</div>
                      <div className="chart-box">{renderDefensivePlayTypes()}</div>
                    </div>
                  </>
                )}

                {!playTypeLoading && matchupData && renderSchemeMatchupTable()}

                {!playTypeLoading && !playTypeData && !playTypeLoading && (
                  <div className="pt-empty">
                    <p>Click the "Play Types" tab to load Synergy scheme data for the selected player's team.</p>
                    <button className="analyze-btn" onClick={fetchPlayTypes}>Load Play Types</button>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Game Log Table */}
          <details className="game-log-details">
            <summary>Full Game Log with Z-Scores ({data.games.length} games)</summary>
            <div className="game-log-wrap">
              <table className="game-log-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Opp</th>
                    <th>H/A</th>
                    <th>{data.stat}</th>
                    <th>Z-Score</th>
                    <th>Min</th>
                    <th>W/L</th>
                    <th>+/-</th>
                    <th>Rest</th>
                  </tr>
                </thead>
                <tbody>
                  {[...data.games].reverse().map((g, i) => (
                    <tr key={i} className={
                      g.z_score > 1.5 ? 'z-high' : g.z_score < -1.5 ? 'z-low' : ''
                    }>
                      <td>{g.date}</td>
                      <td>{g.opponent}</td>
                      <td>{g.is_home ? 'H' : 'A'}</td>
                      <td className="stat-val">{g.stat_value}</td>
                      <td className={`z-val ${g.z_score > 1 ? 'pos' : g.z_score < -1 ? 'neg' : ''}`}>
                        {g.z_score.toFixed(2)}
                      </td>
                      <td>{g.minutes?.toFixed(0) || '-'}</td>
                      <td className={g.result === 'W' ? 'win' : 'loss'}>{g.result}</td>
                      <td>{g.plus_minus > 0 ? '+' : ''}{g.plus_minus}</td>
                      <td>{g.rest_days}d{g.is_back_to_back ? '*' : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </div>
  );
};

export default NbaPlayerAnalysis;
