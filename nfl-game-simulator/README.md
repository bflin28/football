# NFL Game Simulator

An interactive React app that lets you explore NFL play-by-play data with a visual football field and detailed analytics for each play. Built with a Python Flask backend and React frontend.

## Features

- 🏈 Select from all 2023 NFL games
- ⬅️➡️ Navigate through plays with forward/backward controls
- 🏟️ Visual football field showing ball position and first down markers
- 📊 Detailed play statistics including Win Probability Added (WPA) and Expected Points Added (EPA)
- 📱 Responsive design that works on desktop and mobile

## Quick Start

### Prerequisites

- Python 3.8+ with pip
- Node.js 16+ with npm
- About 5 minutes for initial data download

### 1. Start the Backend (Flask API)

```bash
cd backend
pip install -r requirements.txt
python app.py
```

The backend will start on `http://localhost:5000` and automatically download 2023 NFL play-by-play data (this may take a few minutes the first time).

### 2. Start the Frontend (React)

In a new terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend will start on `http://localhost:5173`.

## How to Use

1. **Select a Game**: Choose from the grid of 2023 NFL games
2. **Navigate Plays**: Use the Previous/Next buttons to move through plays
3. **Analyze**: Watch how Win Probability and Expected Points change with each play
4. **Visual Field**: See ball position and first down markers on the football field

## Project Structure

```
nfl-game-simulator/
├── backend/
│   ├── app.py              # Flask API server
│   └── requirements.txt    # Python dependencies
└── frontend/
    ├── src/
    │   ├── components/
    │   │   ├── GameSelector.jsx    # Game selection grid
    │   │   ├── PlayViewer.jsx      # Main play interface
    │   │   └── FootballField.jsx   # SVG football field
    │   └── App.jsx
    ├── package.json
    └── vite.config.js
```

## Key Stats Explained

- **WP (Win Probability)**: Chance of winning before this play
- **WPA (Win Probability Added)**: How much this play changed win probability
- **EP (Expected Points)**: Expected points from this field position before the play
- **EPA (Expected Points Added)**: Points value added by this play

## API Endpoints

- `GET /api/games` - List all available games
- `GET /api/games/{game_id}/plays` - Get all plays for a specific game
- `GET /api/games/{game_id}/plays/{play_index}` - Get a specific play by index

## Development

### Backend Development

The Flask app fetches data using your provided NFL code:

```python
# Your original code is integrated into the Flask endpoints
pbp = import_pbp_data([2023], downcast=False, cache=False)
# ... rest of your data processing
```

### Frontend Development

Built with Vite for fast development:

```bash
cd frontend
npm run dev    # Start development server
npm run build  # Build for production
```

## Troubleshooting

**Backend Issues:**
- Make sure Flask is running on port 5000
- First run may take 3-5 minutes to download NFL data
- Check console for any Python package installation errors

**Frontend Issues:**  
- Ensure the backend is running before starting the frontend
- Check browser console for API connection errors
- Try refreshing if game/play data doesn't load

## Next Steps

- Add more seasons beyond 2023
- Include player-level statistics
- Add play outcome predictions
- Export play sequences for analysis
- Add team-specific filtering

Enjoy exploring NFL analytics! 🏈