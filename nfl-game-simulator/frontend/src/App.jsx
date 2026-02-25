import { useState, useEffect } from 'react'
import './App.css'
import GameSelector from './components/GameSelector'
import PlayViewer from './components/PlayViewer'
import ModelAnalysis from './components/ModelAnalysis'
import NbaPlayerAnalysis from './components/NbaPlayerAnalysis'

function App() {
  const [selectedGame, setSelectedGame] = useState(null)
  const [games, setGames] = useState([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('nba')

  useEffect(() => {
    // Fetch available games (uses Vite proxy → Flask)
    fetch('/api/games')
      .then(res => res.json())
      .then(data => {
        setGames(data)
        setLoading(false)
      })
      .catch(err => {
        console.error('Failed to fetch games:', err)
        setLoading(false)
      })
  }, [])

  return (
    <div className="app">
      <div className="app-header">
        <h1>Sports Analysis Platform</h1>
        <div className="app-tabs">
          <button
            className={`app-tab ${activeTab === 'nba' ? 'active' : ''}`}
            onClick={() => setActiveTab('nba')}
          >
            NBA Z-Scores
          </button>
          <button
            className={`app-tab ${activeTab === 'simulator' ? 'active' : ''}`}
            onClick={() => {
              setActiveTab('simulator')
              setSelectedGame(null)
            }}
          >
            NFL Simulator
          </button>
          <button
            className={`app-tab ${activeTab === 'analysis' ? 'active' : ''}`}
            onClick={() => setActiveTab('analysis')}
          >
            NFL Model
          </button>
        </div>
      </div>

      <div className="app-content">
        {activeTab === 'nba' && (
          <div className="analysis-section">
            <NbaPlayerAnalysis />
          </div>
        )}

        {activeTab === 'simulator' && (
          <div className="simulator-section">
            {loading ? (
              <p style={{ textAlign: 'center', padding: '40px', color: '#7f8c8d' }}>
                Loading NFL data...
              </p>
            ) : !selectedGame ? (
              <GameSelector
                games={games}
                onSelectGame={setSelectedGame}
              />
            ) : (
              <PlayViewer
                game={selectedGame}
                onBackToGames={() => setSelectedGame(null)}
              />
            )}
          </div>
        )}

        {activeTab === 'analysis' && (
          <div className="analysis-section">
            <ModelAnalysis />
          </div>
        )}
      </div>
    </div>
  )
}

export default App
