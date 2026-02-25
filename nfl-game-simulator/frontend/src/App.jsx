import { useState, useEffect } from 'react'
import './App.css'
import GameSelector from './components/GameSelector'
import PlayViewer from './components/PlayViewer'
import ModelAnalysis from './components/ModelAnalysis'

function App() {
  const [selectedGame, setSelectedGame] = useState(null)
  const [games, setGames] = useState([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('simulator') // 'simulator' or 'analysis'

  useEffect(() => {
    // Fetch available games  
    fetch('http://localhost:5000/api/games')
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

  if (loading) {
    return (
      <div className="app">
        <h1>NFL Analysis Platform</h1>
        <p>Loading... (Make sure the Flask backend is running on port 5000)</p>
      </div>
    )
  }

  return (
    <div className="app">
      <div className="app-header">
        <h1>🏈 NFL Analysis Platform</h1>
        <div className="app-tabs">
          <button 
            className={`app-tab ${activeTab === 'simulator' ? 'active' : ''}`}
            onClick={() => {
              setActiveTab('simulator')
              setSelectedGame(null) // Reset game selection when switching tabs
            }}
          >
            🎮 Game Simulator
          </button>
          <button 
            className={`app-tab ${activeTab === 'analysis' ? 'active' : ''}`}
            onClick={() => setActiveTab('analysis')}
          >
            🤖 Model Analysis
          </button>
        </div>
      </div>

      <div className="app-content">
        {activeTab === 'simulator' && (
          <div className="simulator-section">
            {!selectedGame ? (
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
