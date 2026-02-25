# Mobile Development Plan — Sports Analysis & Betting Lines Platform

## Vision

Transform the existing NFL Game Simulator into a **mobile-first sports analysis platform** where users can explore stats, identify value betting lines, and make informed decisions — all seamlessly from their phone, tablet, or desktop.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Mobile-First UI/UX Redesign](#2-mobile-first-uiux-redesign)
3. [Progressive Web App (PWA) Setup](#3-progressive-web-app-pwa-setup)
4. [Development Environment for Mobile Testing](#4-development-environment-for-mobile-testing)
5. [Testing Strategy](#5-testing-strategy)
6. [Backend Enhancements](#6-backend-enhancements)
7. [Sports Analysis & Line Value Features](#7-sports-analysis--line-value-features)
8. [Implementation Phases](#8-implementation-phases)
9. [File Structure](#9-file-structure)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                  CLIENT (Mobile/Desktop)         │
│                                                  │
│  React 19 + Vite (PWA)                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐│
│  │ Game     │ │ Model    │ │ Line Value       ││
│  │ Simulator│ │ Analysis │ │ Analyzer         ││
│  └──────────┘ └──────────┘ └──────────────────┘│
│  ┌──────────────────────────────────────────┐   │
│  │ Responsive Shell (bottom nav, swipe,     │   │
│  │ pull-to-refresh, touch-optimized charts) │   │
│  └──────────────────────────────────────────┘   │
└────────────────────┬────────────────────────────┘
                     │ REST API / WebSocket
┌────────────────────┴────────────────────────────┐
│                  SERVER                          │
│                                                  │
│  Flask API (existing + new endpoints)            │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐│
│  │ Play-by- │ │ ML Model │ │ Odds/Lines       ││
│  │ Play API │ │ Serve    │ │ Analysis API     ││
│  └──────────┘ └──────────┘ └──────────────────┘│
│  ┌──────────────────────────────────────────┐   │
│  │ Data Layer: nfl_data_py + cached parquet │   │
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### Tech Stack Additions

| Layer | Current | Adding |
|-------|---------|--------|
| Frontend | React 19, Vite, Chart.js, D3 | `vite-plugin-pwa`, `@testing-library/react`, Vitest, Playwright |
| Backend | Flask, Pandas, nfl_data_py | pytest, Flask-Caching, gunicorn |
| Mobile Testing | None | Playwright (mobile emulation), ngrok/localtunnel, BrowserStack (optional) |
| CI/CD | None | GitHub Actions |

---

## 2. Mobile-First UI/UX Redesign

### 2.1 Navigation Overhaul

**Current**: Tab bar at the top (Game Simulator | Model Analysis)
**New**: Bottom navigation bar for mobile, top nav for desktop

```
Mobile Layout (< 768px):
┌────────────────────────┐
│ ☰  Sports Analyzer     │  ← Compact header
├────────────────────────┤
│                        │
│   [Content Area]       │  ← Scrollable, touch-friendly
│   Cards, Charts,       │
│   Stats Tables         │
│                        │
├────────────────────────┤
│ 🏈  📊  💰  ⚙️        │  ← Bottom nav (Games, Analysis, Lines, Settings)
└────────────────────────┘

Desktop Layout (≥ 1024px):
┌──────────────────────────────────────────┐
│ 🏈 Sports Analyzer  | Games | Analysis | Lines | Settings │
├──────────────────────────────────────────┤
│ [Sidebar]  │        [Main Content]       │
│ Filters    │        Charts & Data        │
│ Quick Nav  │                              │
└──────────────────────────────────────────┘
```

### 2.2 Touch-Optimized Components

| Component | Current State | Mobile Enhancement |
|-----------|---------------|-------------------|
| Game Selector | Grid of cards | Swipeable card carousel + search/filter bar |
| Play Viewer | Prev/Next buttons | Swipe left/right to navigate plays, pinch-to-zoom field |
| Football Field | Static SVG | Touch-interactive SVG with tap-for-details on positions |
| Charts | Chart.js defaults | Touch-friendly tooltips, larger hit areas, horizontal scroll for wide charts |
| Model Analysis | 5 sub-tabs | Collapsible accordion sections for mobile |
| Data Tables | Full-width | Horizontally scrollable with sticky first column |

### 2.3 CSS Strategy

- Use CSS custom properties for theming (light/dark mode)
- Mobile breakpoints: `480px` (phone), `768px` (tablet), `1024px` (desktop)
- Replace fixed pixel layouts with `clamp()`, `min()`, `max()` for fluid typography
- Use CSS Grid + Flexbox (already partially in place)
- Minimum touch target: `44px × 44px` per Apple/Google guidelines

### 2.4 Key Mobile UX Patterns

- **Pull-to-refresh**: Refresh data/odds on the Lines page
- **Skeleton screens**: Show loading placeholders instead of spinners
- **Offline indicators**: Banner when connection is lost (PWA)
- **Haptic feedback**: Vibration API on key actions (bet placed, alert triggered)
- **Swipe gestures**: Navigate between plays, dismiss cards

---

## 3. Progressive Web App (PWA) Setup

### Why PWA

- Install to home screen — feels like a native app
- Works offline with cached data
- Push notifications for line movement alerts
- No app store required — instant updates
- Single codebase for all platforms

### 3.1 Implementation

**Install `vite-plugin-pwa`:**
```bash
cd nfl-game-simulator/frontend
npm install vite-plugin-pwa -D
```

**Update `vite.config.js`:**
```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.ico', 'apple-touch-icon.png'],
      manifest: {
        name: 'Sports Line Analyzer',
        short_name: 'LineCheck',
        description: 'NFL stats analysis and betting line value finder',
        theme_color: '#1a1a2e',
        background_color: '#1a1a2e',
        display: 'standalone',
        orientation: 'portrait-primary',
        start_url: '/',
        icons: [
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' }
        ]
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg}'],
        runtimeCaching: [
          {
            urlPattern: /^https:\/\/api\./i,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: { maxEntries: 100, maxAgeSeconds: 60 * 60 }
            }
          }
        ]
      }
    })
  ]
})
```

### 3.2 Offline Strategy

| Resource | Cache Strategy | Rationale |
|----------|---------------|-----------|
| App shell (HTML/CSS/JS) | Cache First | Rarely changes, load instantly |
| API: Game list | Stale While Revalidate | Show cached games, update in background |
| API: Play data | Network First | Needs freshness for live games |
| API: Model predictions | Cache First | Static model outputs |
| API: Odds/lines | Network Only | Must be real-time |
| Images/SVGs | Cache First | Static assets |

---

## 4. Development Environment for Mobile Testing

This is the core of seamless mobile testing — the ability to develop on your machine and instantly test on any phone on the same network or remotely.

### 4.1 Local Network Testing (Same Wi-Fi)

**Vite already supports this.** Bind to `0.0.0.0`:

```js
// vite.config.js
export default defineConfig({
  server: {
    host: '0.0.0.0',    // Expose to local network
    port: 5173,
    strictPort: true
  },
  // ...
})
```

**Flask backend — expose on network:**
```python
# app.py — already has this at the bottom:
app.run(debug=True, host='0.0.0.0', port=5000)
```

**Workflow:**
1. Run `npm run dev` — Vite prints your local IP (e.g., `http://192.168.1.42:5173`)
2. Open that URL on your phone's browser
3. Changes hot-reload on your phone in real-time

### 4.2 Remote Testing via Tunnel (Any Network)

For testing from anywhere (cellular, different network, share with others):

```bash
# Option A: ngrok (recommended for stability)
npm install -g ngrok
ngrok http 5173

# Option B: localtunnel (free, no account)
npm install -g localtunnel
lt --port 5173

# Option C: Cloudflare Tunnel (free, fast)
brew install cloudflared  # or apt install
cloudflared tunnel --url http://localhost:5173
```

Each gives you a public URL like `https://abc123.ngrok.io` — open on any device.

### 4.3 `dev:mobile` Script

Add a convenience script to `package.json`:

```json
{
  "scripts": {
    "dev": "vite",
    "dev:mobile": "vite --host 0.0.0.0",
    "dev:tunnel": "concurrently \"vite --host 0.0.0.0\" \"npx localtunnel --port 5173\"",
    "dev:full": "concurrently \"cd ../backend && python app.py\" \"vite --host 0.0.0.0\"",
    "build": "vite build",
    "preview": "vite preview",
    "lint": "eslint .",
    "test": "vitest",
    "test:ui": "vitest --ui",
    "test:mobile": "playwright test --project=mobile-chrome --project=mobile-safari",
    "test:all": "vitest run && playwright test"
  }
}
```

### 4.4 Browser DevTools for Mobile

- **Chrome DevTools** → Device Mode (Ctrl+Shift+M): Emulate any phone
- **Chrome Remote Debugging**: Connect physical Android via USB, inspect in `chrome://inspect`
- **Safari Web Inspector**: Connect physical iPhone via USB, inspect from macOS Safari
- **Responsive Design Mode**: Firefox (Ctrl+Shift+M) for quick viewport testing

### 4.5 Full-Stack Dev Server Script

Create a single entry point to start everything:

```bash
#!/bin/bash
# scripts/dev-mobile.sh
# Start both backend and frontend for mobile testing

echo "Starting Flask backend on 0.0.0.0:5000..."
cd "$(dirname "$0")/../nfl-game-simulator/backend"
python app.py &
BACKEND_PID=$!

echo "Starting Vite frontend on 0.0.0.0:5173..."
cd "$(dirname "$0")/../nfl-game-simulator/frontend"
npx vite --host 0.0.0.0 &
FRONTEND_PID=$!

# Get local IP
LOCAL_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "================================================"
echo "  Mobile Testing Ready!"
echo "  Frontend: http://${LOCAL_IP}:5173"
echo "  Backend:  http://${LOCAL_IP}:5000"
echo "  Open the frontend URL on your phone"
echo "================================================"
echo ""

# Cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
```

---

## 5. Testing Strategy

### 5.1 Testing Pyramid

```
        ╱  E2E (Playwright)  ╲          ← Mobile emulation, real browsers
       ╱   Integration Tests   ╲        ← API + component interaction
      ╱    Component Tests      ╲       ← React components (Vitest + RTL)
     ╱     Unit Tests            ╲      ← Pure logic, utils, helpers
    ╱      Backend Tests (pytest) ╲     ← Flask API endpoints
   ╱───────────────────────────────╲
```

### 5.2 Frontend Unit & Component Tests (Vitest + React Testing Library)

**Setup:**
```bash
cd nfl-game-simulator/frontend
npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

**`vitest.config.js`** (or inside `vite.config.js`):
```js
/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
    css: true
  }
})
```

**`src/test/setup.js`:**
```js
import '@testing-library/jest-dom'
```

**Example Tests:**

```jsx
// src/components/__tests__/GameSelector.test.jsx
import { render, screen, fireEvent } from '@testing-library/react'
import GameSelector from '../GameSelector'

const mockGames = [
  { game_id: '2023_01_KC_DET', week: 1, season: 2023, home_team: 'DET', away_team: 'KC' },
  { game_id: '2023_01_BAL_HOU', week: 1, season: 2023, home_team: 'HOU', away_team: 'BAL' }
]

describe('GameSelector', () => {
  it('renders all games', () => {
    render(<GameSelector games={mockGames} onSelectGame={() => {}} />)
    expect(screen.getByText(/KC/)).toBeInTheDocument()
    expect(screen.getByText(/BAL/)).toBeInTheDocument()
  })

  it('calls onSelectGame when a game is clicked', () => {
    const onSelect = vi.fn()
    render(<GameSelector games={mockGames} onSelectGame={onSelect} />)
    fireEvent.click(screen.getByText(/KC/))
    expect(onSelect).toHaveBeenCalledWith('2023_01_KC_DET')
  })
})
```

```jsx
// src/components/__tests__/FootballField.test.jsx
import { render, screen } from '@testing-library/react'
import FootballField from '../FootballField'

describe('FootballField', () => {
  it('renders with ball position', () => {
    const { container } = render(
      <FootballField yardLine={35} firstDownLine={25} possession="KC" down={3} distance={5} />
    )
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('shows down and distance', () => {
    render(
      <FootballField yardLine={35} firstDownLine={25} possession="KC" down={3} distance={5} />
    )
    expect(screen.getByText(/3rd & 5/i)).toBeInTheDocument()
  })
})
```

### 5.3 Backend Tests (pytest)

**Setup:**
```bash
cd nfl-game-simulator/backend
pip install pytest pytest-cov
```

**`tests/test_api.py`:**
```python
import pytest
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_games_endpoint(client):
    """GET /api/games returns a list of games."""
    response = client.get('/api/games')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)
    if len(data) > 0:
        assert 'game_id' in data[0]
        assert 'home_team' in data[0]

def test_game_plays(client):
    """GET /api/games/<id>/plays returns plays for a valid game."""
    games = client.get('/api/games').get_json()
    if games:
        game_id = games[0]['game_id']
        response = client.get(f'/api/games/{game_id}/plays')
        assert response.status_code == 200
        plays = response.get_json()
        assert isinstance(plays, list)

def test_model_sample_data(client):
    """GET /api/model/sample-data returns feature importance data."""
    response = client.get('/api/model/sample-data')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)

def test_invalid_game(client):
    """GET /api/games/invalid returns 404."""
    response = client.get('/api/games/FAKE_GAME/plays')
    assert response.status_code == 404
```

### 5.4 E2E Mobile Tests (Playwright)

This is the key to **seamless mobile testing** — automated tests that run in real mobile browser engines.

**Setup:**
```bash
cd nfl-game-simulator/frontend
npm install -D @playwright/test
npx playwright install  # Downloads Chromium, Firefox, WebKit
```

**`playwright.config.js`:**
```js
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? 'github' : 'html',

  webServer: [
    {
      command: 'cd ../backend && python app.py',
      port: 5000,
      reuseExistingServer: !process.env.CI,
      timeout: 30000
    },
    {
      command: 'npm run dev',
      port: 5173,
      reuseExistingServer: !process.env.CI,
      timeout: 15000
    }
  ],

  projects: [
    // Desktop browsers
    { name: 'desktop-chrome', use: { ...devices['Desktop Chrome'] } },
    { name: 'desktop-firefox', use: { ...devices['Desktop Firefox'] } },

    // Mobile browsers — the core of mobile testing
    { name: 'mobile-chrome', use: { ...devices['Pixel 7'] } },
    { name: 'mobile-safari', use: { ...devices['iPhone 14'] } },
    { name: 'mobile-safari-mini', use: { ...devices['iPhone SE'] } },
    { name: 'tablet-safari', use: { ...devices['iPad Pro 11'] } },
    { name: 'tablet-chrome', use: { ...devices['Galaxy Tab S4'] } },
  ]
})
```

**`e2e/mobile-navigation.spec.js`:**
```js
import { test, expect } from '@playwright/test'

test.describe('Mobile Navigation', () => {
  test('loads the app and shows game list', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('h1')).toContainText(/NFL|Game|Simulator/i)
  })

  test('can select a game and view plays', async ({ page }) => {
    await page.goto('/')
    // Wait for games to load
    const gameCard = page.locator('.game-card').first()
    await gameCard.waitFor({ state: 'visible', timeout: 15000 })
    await gameCard.tap()  // Use tap() for mobile

    // Verify play viewer loaded
    await expect(page.locator('.play-viewer')).toBeVisible()
  })

  test('can swipe between plays', async ({ page, isMobile }) => {
    test.skip(!isMobile, 'Swipe test only for mobile')
    await page.goto('/')
    const gameCard = page.locator('.game-card').first()
    await gameCard.waitFor({ state: 'visible', timeout: 15000 })
    await gameCard.tap()

    // Swipe left to go to next play
    const viewer = page.locator('.play-viewer')
    await viewer.swipe({ direction: 'left' })
  })

  test('football field renders at mobile viewport', async ({ page }) => {
    await page.goto('/')
    const gameCard = page.locator('.game-card').first()
    await gameCard.waitFor({ state: 'visible', timeout: 15000 })
    await gameCard.click()

    const field = page.locator('svg')
    await expect(field).toBeVisible()

    // Verify field fits within mobile viewport
    const box = await field.boundingBox()
    const viewport = page.viewportSize()
    expect(box.width).toBeLessThanOrEqual(viewport.width)
  })
})

test.describe('Mobile Responsive Layout', () => {
  test('bottom nav is visible on mobile', async ({ page, isMobile }) => {
    test.skip(!isMobile, 'Bottom nav only on mobile')
    await page.goto('/')
    await expect(page.locator('.bottom-nav')).toBeVisible()
  })

  test('tabs stack vertically on mobile', async ({ page, isMobile }) => {
    test.skip(!isMobile, 'Layout test only for mobile')
    await page.goto('/')
    // Verify vertical layout
    const tabs = page.locator('.tab-container')
    const box = await tabs.boundingBox()
    const viewport = page.viewportSize()
    expect(box.width).toBeLessThanOrEqual(viewport.width)
  })

  test('charts are touch-interactive', async ({ page, isMobile }) => {
    test.skip(!isMobile, 'Touch test only for mobile')
    await page.goto('/')
    // Navigate to Model Analysis
    await page.locator('text=Model Analysis').click()

    // Tap on a chart to see tooltip
    const chart = page.locator('canvas').first()
    await chart.waitFor({ state: 'visible' })
    await chart.tap()
  })
})

test.describe('Mobile Performance', () => {
  test('initial load under 3 seconds on 4G', async ({ page }) => {
    // Simulate 4G network
    const client = await page.context().newCDPSession(page)
    await client.send('Network.emulateNetworkConditions', {
      offline: false,
      downloadThroughput: 4 * 1024 * 1024 / 8,   // 4 Mbps
      uploadThroughput: 3 * 1024 * 1024 / 8,      // 3 Mbps
      latency: 20
    })

    const start = Date.now()
    await page.goto('/')
    await page.locator('.game-card').first().waitFor({ state: 'visible', timeout: 15000 })
    const loadTime = Date.now() - start

    expect(loadTime).toBeLessThan(5000) // 5s budget on 4G
  })
})
```

### 5.5 Visual Regression Testing

Catch unintended layout changes across devices:

```bash
npm install -D @playwright/test
```

```js
// e2e/visual-mobile.spec.js
import { test, expect } from '@playwright/test'

test('game selector matches snapshot on iPhone', async ({ page }) => {
  await page.goto('/')
  await page.locator('.game-card').first().waitFor({ state: 'visible', timeout: 15000 })
  await expect(page).toHaveScreenshot('game-selector-mobile.png', { maxDiffPixels: 100 })
})

test('play viewer matches snapshot on iPhone', async ({ page }) => {
  await page.goto('/')
  await page.locator('.game-card').first().click()
  await page.locator('.play-viewer').waitFor({ state: 'visible' })
  await expect(page).toHaveScreenshot('play-viewer-mobile.png', { maxDiffPixels: 100 })
})
```

### 5.6 Test Commands Summary

```bash
# Unit & Component Tests
npm run test              # Watch mode
npm run test -- --run     # Single run (CI)
npm run test -- --coverage # With coverage report

# E2E Tests
npx playwright test                                    # All browsers + mobile
npx playwright test --project=mobile-chrome            # Android only
npx playwright test --project=mobile-safari            # iPhone only
npx playwright test --project=tablet-safari            # iPad only
npx playwright test e2e/mobile-navigation.spec.js     # Specific test file
npx playwright test --ui                               # Interactive UI mode
npx playwright show-report                             # View HTML report

# Backend Tests
cd nfl-game-simulator/backend
pytest tests/ -v
pytest tests/ --cov=app --cov-report=html

# Full Suite
npm run test:all   # Vitest + Playwright
```

---

## 6. Backend Enhancements

### 6.1 API Proxy (Vite → Flask)

Avoid CORS issues and simplify mobile requests by proxying API calls through Vite:

```js
// vite.config.js
export default defineConfig({
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true
      }
    }
  }
})
```

Now the frontend just calls `/api/games` — no need for hardcoded `localhost:5000` URLs that break on mobile.

### 6.2 Response Compression

Mobile networks are slower — compress API responses:

```python
# app.py additions
from flask_compress import Compress

compress = Compress()
compress.init_app(app)
```

### 6.3 Pagination for Mobile

Large datasets kill mobile performance. Add pagination to existing endpoints:

```python
@app.route('/api/games')
def get_games():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    # ... paginate results
    return jsonify({
        'games': games[start:end],
        'total': len(all_games),
        'page': page,
        'per_page': per_page
    })
```

---

## 7. Sports Analysis & Line Value Features

### 7.1 Core Line Analysis Features

| Feature | Description | Data Source |
|---------|-------------|-------------|
| **EPA Analysis** | Expected Points Added per team/player/situation | nfl_data_py (existing) |
| **Win Probability Models** | Pre-game and live WP based on situation | nfl_data_py (existing) |
| **Matchup Analysis** | Head-to-head team/unit stats comparison | nfl_data_py + derived |
| **Trend Detection** | Rolling performance windows (3/5/10 games) | Derived from PBP data |
| **Line Value Score** | Compare model prediction to market line | Model output vs odds API |
| **Situational Splits** | Performance by down, distance, quarter, field zone | nfl_data_py (existing) |

### 7.2 New API Endpoints

```
GET /api/analysis/team/<team>/profile         → Team stats summary
GET /api/analysis/matchup/<team1>/<team2>     → Head-to-head comparison
GET /api/analysis/trends/<team>               → Rolling performance metrics
GET /api/analysis/situations/<team>           → Situational splits
GET /api/analysis/value-lines                 → Lines where model disagrees with market
POST /api/analysis/custom-query              → User-defined stat queries
```

### 7.3 Line Value Calculation Flow

```
1. Load historical play-by-play data
2. Calculate team-level aggregates (EPA/play, success rate, turnover rate, etc.)
3. Build predictive model for game outcomes (point spread, total)
4. Compare model output to current market lines
5. Flag lines where model differs by > threshold (e.g., 2+ points)
6. Display ranked list of "value" plays with confidence scores
```

### 7.4 Mobile-Specific Analysis Views

- **Quick Glance Cards**: Swipeable cards showing today's best value lines
- **Matchup Comparison**: Side-by-side stat bars (like ESPN matchup view)
- **Trend Sparklines**: Tiny inline charts showing team momentum
- **Alert System**: Push notifications when a tracked line moves into value territory

---

## 8. Implementation Phases

### Phase 1: Foundation (Week 1-2)
> Get the testing infrastructure and mobile dev environment running

- [ ] Set up Vitest + React Testing Library
- [ ] Write unit tests for existing components (GameSelector, PlayViewer, FootballField, ModelAnalysis)
- [ ] Set up pytest for Flask backend
- [ ] Write API endpoint tests
- [ ] Add `dev:mobile` and `dev:full` scripts to package.json
- [ ] Configure Vite proxy for `/api` routes
- [ ] Create `scripts/dev-mobile.sh` for one-command startup
- [ ] Verify hot-reload works on physical phone via local network

### Phase 2: Mobile UI (Week 3-4)
> Redesign the app as mobile-first

- [ ] Implement bottom navigation bar (mobile) / top nav (desktop)
- [ ] Redesign GameSelector as swipeable card carousel
- [ ] Add swipe navigation to PlayViewer
- [ ] Make FootballField touch-interactive (tap for play details)
- [ ] Make all charts touch-friendly with proper tooltip sizing
- [ ] Add pull-to-refresh functionality
- [ ] Implement skeleton loading screens
- [ ] Responsive data tables with horizontal scroll
- [ ] Dark mode support

### Phase 3: PWA & Offline (Week 5)
> Make the app installable and work offline

- [ ] Install and configure `vite-plugin-pwa`
- [ ] Create app icons (192px, 512px) and splash screens
- [ ] Configure service worker caching strategies
- [ ] Add offline fallback page
- [ ] Add "Install App" prompt banner
- [ ] Test offline mode on mobile devices

### Phase 4: E2E & Visual Testing (Week 6)
> Automated mobile testing across devices

- [ ] Set up Playwright with mobile device profiles
- [ ] Write E2E tests for core mobile flows
- [ ] Add visual regression snapshots for key screens
- [ ] Add mobile performance tests (load time budgets)
- [ ] Set up GitHub Actions CI pipeline running all tests
- [ ] Add test badge to README

### Phase 5: Line Value Features (Week 7-9)
> Build the sports analysis and betting line value engine

- [ ] Build team profile aggregation pipeline
- [ ] Create matchup comparison API endpoints
- [ ] Build trend detection (rolling averages)
- [ ] Create situational splits analysis
- [ ] Build point spread prediction model
- [ ] Implement line value scoring system
- [ ] Build mobile UI for line analysis (swipeable value cards)
- [ ] Build matchup comparison view
- [ ] Add sparkline trend charts

### Phase 6: Polish & Deploy (Week 10)
> Production-ready deployment

- [ ] Performance optimization (lazy loading, code splitting)
- [ ] Bundle size analysis and tree shaking
- [ ] Set up production deployment (Railway/Render/Fly.io)
- [ ] Configure production environment variables
- [ ] Final cross-device testing pass
- [ ] Documentation update

---

## 9. File Structure

After implementation, the project structure will look like:

```
football/
├── docs/
│   ├── project_plan.md
│   └── mobile_dev_plan.md          ← This document
│
├── scripts/
│   └── dev-mobile.sh               ← One-command mobile dev startup
│
├── nfl-game-simulator/
│   ├── backend/
│   │   ├── app.py                   ← Enhanced with new endpoints
│   │   ├── requirements.txt         ← + pytest, flask-compress
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── test_api.py          ← API endpoint tests
│   │       ├── test_analysis.py     ← Line analysis tests
│   │       └── conftest.py          ← Shared fixtures
│   │
│   └── frontend/
│       ├── vite.config.js           ← + PWA, proxy, test config
│       ├── playwright.config.js     ← E2E test configuration
│       ├── package.json             ← + test scripts, new deps
│       │
│       ├── public/
│       │   ├── pwa-192x192.png
│       │   ├── pwa-512x512.png
│       │   └── apple-touch-icon.png
│       │
│       ├── src/
│       │   ├── main.jsx
│       │   ├── App.jsx              ← Responsive shell + routing
│       │   ├── App.css              ← Mobile-first base styles
│       │   │
│       │   ├── components/
│       │   │   ├── GameSelector.jsx
│       │   │   ├── PlayViewer.jsx
│       │   │   ├── FootballField.jsx
│       │   │   ├── ModelAnalysis.jsx
│       │   │   ├── BottomNav.jsx        ← NEW: Mobile bottom navigation
│       │   │   ├── LineAnalyzer.jsx     ← NEW: Betting line value view
│       │   │   ├── MatchupCard.jsx      ← NEW: Team comparison cards
│       │   │   ├── TrendSparkline.jsx   ← NEW: Inline trend charts
│       │   │   ├── ValueLineCard.jsx    ← NEW: Swipeable value line cards
│       │   │   └── SkeletonLoader.jsx   ← NEW: Loading placeholder
│       │   │
│       │   ├── hooks/
│       │   │   ├── useIsMobile.js       ← NEW: Mobile detection hook
│       │   │   ├── useSwipe.js          ← NEW: Swipe gesture hook
│       │   │   └── usePullToRefresh.js  ← NEW: Pull-to-refresh hook
│       │   │
│       │   └── test/
│       │       └── setup.js             ← Test environment setup
│       │
│       ├── e2e/
│       │   ├── mobile-navigation.spec.js
│       │   ├── line-analyzer.spec.js
│       │   └── visual-mobile.spec.js
│       │
│       └── src/components/__tests__/
│           ├── GameSelector.test.jsx
│           ├── PlayViewer.test.jsx
│           ├── FootballField.test.jsx
│           └── ModelAnalysis.test.jsx
│
├── .github/
│   └── workflows/
│       └── test.yml                 ← CI: lint + unit + e2e tests
│
└── environment.yml
```

---

## Quick Start (After Implementation)

```bash
# 1. Start everything for mobile testing
./scripts/dev-mobile.sh

# 2. Open the printed URL on your phone
#    → http://192.168.x.x:5173

# 3. Run mobile tests
cd nfl-game-simulator/frontend
npm run test:mobile

# 4. Run all tests
npm run test:all
```

---

## GitHub Actions CI

```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  backend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.10' }
      - run: pip install -r nfl-game-simulator/backend/requirements.txt && pip install pytest
      - run: cd nfl-game-simulator/backend && pytest tests/ -v

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: cd nfl-game-simulator/frontend && npm ci
      - run: cd nfl-game-simulator/frontend && npm run lint
      - run: cd nfl-game-simulator/frontend && npm run test -- --run

  e2e-mobile:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - uses: actions/setup-python@v5
        with: { python-version: '3.10' }
      - run: pip install -r nfl-game-simulator/backend/requirements.txt
      - run: cd nfl-game-simulator/frontend && npm ci
      - run: cd nfl-game-simulator/frontend && npx playwright install --with-deps
      - run: cd nfl-game-simulator/frontend && npx playwright test
```
