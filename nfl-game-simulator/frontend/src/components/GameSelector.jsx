import React from 'react'
import './GameSelector.css'

const GameSelector = ({ games, onSelectGame }) => {
  return (
    <div className="game-selector">
      <h2>Select a Game</h2>
      <div className="games-grid">
        {games.map(game => (
          <div 
            key={game.game_id} 
            className="game-card"
            onClick={() => onSelectGame(game)}
          >
            <div className="game-teams">
              <span className="away-team">{game.away_team}</span>
              <span className="vs">@</span>
              <span className="home-team">{game.home_team}</span>
            </div>
            <div className="game-info">
              Week {game.week} • {game.season}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default GameSelector