# NBA Factor Analysis

Defensive Attention Score (DAS) analysis platform for NBA players. Measures how much opposing defenses focus on stopping a specific player and how that attention correlates with statistical output.

## Quick Start

### Backend (Flask API)

```bash
cd backend
pip install -r requirements.txt
python app.py
```

### Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

## Deploy to Vercel

```bash
vercel
```

Pre-export player data with `backend/export_player.py` before deploying — the Vercel serverless function serves pre-computed JSON only.
