import React, { useState, useEffect } from 'react'
import FootballField from './FootballField'
import './PlayViewer.css'

const PlayViewer = ({ game, onBackToGames }) => {
  const [plays, setPlays] = useState([])
  const [currentPlayIndex, setCurrentPlayIndex] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Fetch plays for the selected game
    fetch(`http://localhost:5000/api/games/${game.game_id}/plays`)
      .then(res => res.json())
      .then(data => {
        setPlays(data)
        setLoading(false)
      })
      .catch(err => {
        console.error('Failed to fetch plays:', err)
        setLoading(false)
      })
  }, [game.game_id])

  const currentPlay = plays[currentPlayIndex]

  const nextPlay = () => {
    if (currentPlayIndex < plays.length - 1) {
      setCurrentPlayIndex(currentPlayIndex + 1)
    }
  }

  const prevPlay = () => {
    if (currentPlayIndex > 0) {
      setCurrentPlayIndex(currentPlayIndex - 1)
    }
  }

  const formatValue = (value) => {
    if (value === null || value === undefined) return 'N/A'
    if (typeof value === 'number') return value.toFixed(3)
    return value
  }

  const formatTime = (play) => {
    // Try different time fields that might be available
    let seconds = play.game_seconds_remaining || play.half_seconds_remaining || 0
    
    // If we have half_seconds_remaining but not game_seconds_remaining, 
    // we need to add time based on which half we're in
    if (!play.game_seconds_remaining && play.half_seconds_remaining && play.qtr) {
      if (play.qtr <= 2) {
        // First half: add 30 minutes (1800 seconds) for second half
        seconds = play.half_seconds_remaining + 1800
      } else {
        // Second half: use half_seconds_remaining as is
        seconds = play.half_seconds_remaining
      }
    }
    
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${String(secs).padStart(2, '0')}`
  }

  if (loading) {
    return (
      <div className="play-viewer">
        <h2>Loading plays...</h2>
      </div>
    )
  }

  if (!currentPlay) {
    return (
      <div className="play-viewer">
        <h2>No plays found for this game</h2>
        <button onClick={onBackToGames}>Back to Games</button>
      </div>
    )
  }

  return (
    <div className="play-viewer">
      <div className="game-header">
        <button onClick={onBackToGames} className="back-button">
          ← Back to Games
        </button>
        <h2>{game.display_name}</h2>
      </div>

      <div className="play-controls">
        <button 
          onClick={prevPlay} 
          disabled={currentPlayIndex === 0}
          className="nav-button"
        >
          ← Previous
        </button>
        
        <div className="play-info">
          <span className="play-counter">
            Play {currentPlayIndex + 1} of {plays.length}
          </span>
          {currentPlay && (
            <span className="time-info">
              Q{currentPlay.qtr} • {formatTime(currentPlay)} remaining
            </span>
          )}
        </div>
        
        <button 
          onClick={nextPlay} 
          disabled={currentPlayIndex === plays.length - 1}
          className="nav-button"
        >
          Next →
        </button>
      </div>

      <FootballField
        yardLine={currentPlay.yardline_100}
        down={currentPlay.down}
        ydstogo={currentPlay.ydstogo}
        posteam={currentPlay.posteam}
      />

      {/* Play Description */}
      {(currentPlay.desc || currentPlay.play_description) && (
        <div className="play-description">
          <h3>📝 Play Description</h3>
          <p>{currentPlay.desc || currentPlay.play_description}</p>
        </div>
      )}

      <div className="analytics-explainer">
        <details className="explainer-toggle">
          <summary>
            <h3>🤔 Understanding the Analytics</h3>
          </summary>
          <div className="explainer-content">
            <div className="explainer-section">
              <h4>Expected Points (EP)</h4>
              <p><strong>EP Before:</strong> Expected points from the current field position and down/distance before the play</p>
              <p><strong>EPA (Expected Points Added):</strong> How many points this play added/subtracted compared to the average play in this situation</p>
              <p><strong>EP After:</strong> Expected points from the new field position after the play</p>
              <p><em>Note: EP can go down even on successful plays! A 5-yard gain on 3rd & 10 moves you closer but gives the opponent better field position after you punt.</em></p>
            </div>
            <div className="explainer-section">
              <h4>Win Probability (WP)</h4>
              <p><strong>WP Before:</strong> Chance of winning the game before this play</p>
              <p><strong>WPA (Win Prob Added):</strong> How much this play changed your win probability</p>
              <p><strong>WP After:</strong> New chance of winning after the play</p>
              <p><em>WP considers the entire game situation: score, time, field position, timeouts, etc.</em></p>
            </div>
            <div className="explainer-section">
              <h4>Why WP and EP Can Move Differently</h4>
              <p>• <strong>Field position matters:</strong> A play might help short-term (EP) but hurt long-term positioning</p>
              <p>• <strong>Down & distance:</strong> Converting 3rd down is huge for WP, even if EP drops due to field position</p>
              <p>• <strong>Game context:</strong> Late-game situations where any progress helps WP regardless of EP</p>
              <p>• <strong>Time remaining:</strong> Clock management affects WP more than EP</p>
            </div>
          </div>
        </details>
      </div>

      <div className="play-stats">
        <div className="stat-grid">
          <div className="stat-group">
            <h3>Game Situation</h3>
            <div className="stat-item">
              <span className="stat-label">Quarter:</span>
              <span className="stat-value">{formatValue(currentPlay.qtr)}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Time Remaining:</span>
              <span className="stat-value">{formatValue(currentPlay.half_seconds_remaining)}s</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Score Diff:</span>
              <span className="stat-value">{formatValue(currentPlay.score_differential)}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Play Type:</span>
              <span className="stat-value">{formatValue(currentPlay.play_type)}</span>
            </div>
          </div>

          <div className="stat-group">
            <h3>Play Outcome</h3>
            <div className="stat-item">
              <span className="stat-label">Yards Gained:</span>
              <span className="stat-value">{formatValue(currentPlay.yards_gained)}</span>
            </div>
            {currentPlay.passer && (
              <div className="stat-item">
                <span className="stat-label">Passer:</span>
                <span className="stat-value">{currentPlay.passer}</span>
              </div>
            )}
            {currentPlay.rusher && (
              <div className="stat-item">
                <span className="stat-label">Rusher:</span>
                <span className="stat-value">{currentPlay.rusher}</span>
              </div>
            )}
            {currentPlay.receiver && (
              <div className="stat-item">
                <span className="stat-label">Receiver:</span>
                <span className="stat-value">{currentPlay.receiver}</span>
              </div>
            )}
            {currentPlay.first_down && (
              <div className="stat-item highlight">
                <span className="stat-label">First Down:</span>
                <span className="stat-value">✅ Yes</span>
              </div>
            )}
            {currentPlay.touchdown && (
              <div className="stat-item highlight">
                <span className="stat-label">Touchdown:</span>
                <span className="stat-value">🏈 Yes</span>
              </div>
            )}
          </div>

          <div className="stat-group">
            <h3>Win Probability</h3>
            <div className="stat-item highlight">
              <span className="stat-label">WP Before:</span>
              <span className="stat-value">{formatValue(currentPlay.wp)}</span>
            </div>
            <div className="stat-item highlight">
              <span className="stat-label">WPA:</span>
              <span className="stat-value">{formatValue(currentPlay.wpa)}</span>
            </div>
            <div className="stat-item highlight">
              <span className="stat-label">WP After:</span>
              <span className="stat-value">{formatValue(currentPlay.wp_post)}</span>
            </div>
          </div>

          <div className="stat-group">
            <h3>Expected Points</h3>
            <div className="stat-item">
              <span className="stat-label">EP Before:</span>
              <span className="stat-value">{formatValue(currentPlay.ep)}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">EPA:</span>
              <span className="stat-value">{formatValue(currentPlay.epa)}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">EP After:</span>
              <span className="stat-value">{currentPlay.ep ? formatValue((currentPlay.ep || 0) + (currentPlay.epa || 0)) : 'N/A'}</span>
            </div>
          </div>

          <div className="stat-group">
            <h3>Timeouts</h3>
            <div className="stat-item">
              <span className="stat-label">{currentPlay.posteam} TO:</span>
              <span className="stat-value">{formatValue(currentPlay.posteam_timeouts_remaining)}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">{currentPlay.defteam} TO:</span>
              <span className="stat-value">{formatValue(currentPlay.defteam_timeouts_remaining)}</span>
            </div>
          </div>

          <div className="stat-group">
            <h3>Field Conditions</h3>
            <div className="stat-item">
              <span className="stat-label">Surface:</span>
              <span className="stat-value">{formatValue(currentPlay.surface)}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Roof:</span>
              <span className="stat-value">{formatValue(currentPlay.roof)}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Temperature:</span>
              <span className="stat-value">{currentPlay.temp ? `${currentPlay.temp}°F` : 'N/A'}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Wind:</span>
              <span className="stat-value">{currentPlay.wind ? `${currentPlay.wind} mph` : 'N/A'}</span>
            </div>
          </div>

          <div className="stat-group">
            <h3>Play Details</h3>
            <div className="stat-item">
              <span className="stat-label">Play ID:</span>
              <span className="stat-value">{formatValue(currentPlay.play_id)}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Game ID:</span>
              <span className="stat-value">{formatValue(currentPlay.game_id)}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Season:</span>
              <span className="stat-value">{formatValue(currentPlay.season)}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">Week:</span>
              <span className="stat-value">{formatValue(currentPlay.week)}</span>
            </div>
          </div>
        </div>

        <div className="raw-data-section">
          <details className="raw-data-toggle">
            <summary>
              <h3>📋 Complete Play Data</h3>
            </summary>
            <div className="raw-data-grid">
              {Object.entries(currentPlay)
                .filter(([key, value]) => value !== null && value !== undefined)
                .sort(([a], [b]) => a.localeCompare(b))
                .map(([key, value]) => (
                  <div key={key} className="raw-data-item">
                    <span className="raw-data-key">{key}:</span>
                    <span className="raw-data-value">
                      {typeof value === 'number' ? value.toFixed(6) : String(value)}
                    </span>
                  </div>
                ))}
            </div>
          </details>
        </div>
      </div>
    </div>
  )
}

export default PlayViewer