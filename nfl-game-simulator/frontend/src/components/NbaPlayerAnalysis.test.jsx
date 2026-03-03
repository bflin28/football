import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import NbaPlayerAnalysis from './NbaPlayerAnalysis'

// Mock Chart.js components — they don't render in jsdom
vi.mock('react-chartjs-2', () => ({
  Bar: () => <div data-testid="mock-bar-chart" />,
  Scatter: () => <div data-testid="mock-scatter-chart" />,
  Line: () => <div data-testid="mock-line-chart" />,
}))

vi.mock('chart.js', () => ({
  Chart: { register: vi.fn() },
  CategoryScale: {},
  LinearScale: {},
  PointElement: {},
  LineElement: {},
  BarElement: {},
  Title: {},
  Tooltip: {},
  Legend: {},
  Filler: {},
}))

const MOCK_STATS = [
  { key: 'PTS', label: 'Points' },
  { key: 'REB', label: 'Rebounds' },
  { key: 'AST', label: 'Assists' },
  { key: 'STL', label: 'Steals' },
]

const MOCK_PLAYERS = [
  { id: 1, full_name: 'LeBron James' },
  { id: 2, full_name: 'LeBron Raymond James' },
]

const MOCK_AVAILABLE = {
  players: [
    { slug: 'nikola-jokic', name: 'Nikola Jokic' },
    { slug: 'shai-gilgeous-alexander', name: 'Shai Gilgeous-Alexander' },
  ],
}

/** Build a mock Response with .text() returning JSON string (matches safeJson usage). */
function mockResponse(data, ok = true) {
  return Promise.resolve({
    ok,
    text: () => Promise.resolve(JSON.stringify(data)),
  })
}

function mockFetch(overrides = {}) {
  return vi.fn((url) => {
    if (url === '/api/nba/available-players') {
      return mockResponse(overrides.available ?? MOCK_AVAILABLE)
    }
    if (url.startsWith('/api/nba/players/search')) {
      return mockResponse(overrides.search ?? MOCK_PLAYERS)
    }
    if (url.startsWith('/api/nba/defensive-attention')) {
      return mockResponse(overrides.das ?? { player: { id: 1, name: 'Test' }, das: { games_total: 0, games_fetched: 0, per_game: [], regression: null } })
    }
    return mockResponse({})
  })
}

describe('NbaPlayerAnalysis', () => {
  beforeEach(() => {
    global.fetch = mockFetch()
  })

  // ── Rendering ──

  it('renders the DAS-focused header', async () => {
    render(<NbaPlayerAnalysis />)
    expect(screen.getByText('Defensive Attention Score')).toBeInTheDocument()
  })

  it('does not render Factor or Stat dropdowns', async () => {
    render(<NbaPlayerAnalysis />)
    expect(screen.queryByLabelText('Factor')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Stat')).not.toBeInTheDocument()
  })

  it('renders season select', async () => {
    render(<NbaPlayerAnalysis />)
    expect(screen.getByLabelText('Season')).toBeInTheDocument()
  })

  it('auto-analyzes on mount', async () => {
    render(<NbaPlayerAnalysis />)
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/nba/defensive-attention')
      )
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('player=Nikola+Jokic')
      )
    })
  })

  it('renders mode toggle buttons', () => {
    render(<NbaPlayerAnalysis />)
    expect(screen.getByRole('radio', { name: 'Raw' })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: 'Per Min' })).toBeInTheDocument()
  })

  it('renders view toggle tabs', () => {
    render(<NbaPlayerAnalysis />)
    expect(screen.getByRole('tab', { name: 'Player Deep Dive' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'League Leaderboard' })).toBeInTheDocument()
  })

  // ── Season Select ──

  it('has three season options', () => {
    render(<NbaPlayerAnalysis />)
    const seasonSelect = screen.getByLabelText('Season')
    const options = within(seasonSelect).getAllByRole('option')
    expect(options).toHaveLength(3)
    expect(options[0]).toHaveValue('2025-26')
    expect(options[1]).toHaveValue('2024-25')
    expect(options[2]).toHaveValue('2023-24')
  })

  it('changes season when selected', async () => {
    const user = userEvent.setup()
    render(<NbaPlayerAnalysis />)

    await user.selectOptions(screen.getByLabelText('Season'), '2023-24')
    expect(screen.getByLabelText('Season')).toHaveValue('2023-24')
  })

  // ── Mode Toggle ──

  it('toggles between Raw and Per Min mode', async () => {
    const user = userEvent.setup()
    render(<NbaPlayerAnalysis />)

    const rawBtn = screen.getByRole('radio', { name: 'Raw' })
    const perMinBtn = screen.getByRole('radio', { name: 'Per Min' })

    expect(rawBtn).toHaveAttribute('aria-checked', 'true')
    expect(perMinBtn).toHaveAttribute('aria-checked', 'false')

    await user.click(perMinBtn)
    expect(rawBtn).toHaveAttribute('aria-checked', 'false')
    expect(perMinBtn).toHaveAttribute('aria-checked', 'true')
  })

  // ── View Toggle ──

  it('switches between Player Deep Dive and Leaderboard views', async () => {
    const user = userEvent.setup()
    render(<NbaPlayerAnalysis />)

    // Player view is default
    expect(screen.getByRole('tab', { name: 'Player Deep Dive' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByPlaceholderText('Search player...')).toBeInTheDocument()

    // Switch to leaderboard
    await user.click(screen.getByRole('tab', { name: 'League Leaderboard' }))
    expect(screen.getByRole('tab', { name: 'League Leaderboard' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.queryByPlaceholderText('Search player...')).not.toBeInTheDocument()
  })

  // ── Player Search Dropdown ──

  describe('Player Search', () => {
    it('shows dropdown when typing 2+ characters', async () => {
      const user = userEvent.setup()
      render(<NbaPlayerAnalysis />)

      const input = screen.getByPlaceholderText('Search player...')
      await user.clear(input)
      await user.type(input, 'Le')

      await waitFor(() => {
        const listbox = screen.getByRole('listbox')
        expect(listbox).toBeInTheDocument()
        expect(within(listbox).getAllByRole('option')).toHaveLength(2)
      })
    })

    it('does not show dropdown for 1 character', async () => {
      const user = userEvent.setup()
      render(<NbaPlayerAnalysis />)

      const input = screen.getByPlaceholderText('Search player...')
      await user.clear(input)
      await user.type(input, 'L')

      expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    })

    it('selects a player on click', async () => {
      const user = userEvent.setup()
      render(<NbaPlayerAnalysis />)

      const input = screen.getByPlaceholderText('Search player...')
      await user.clear(input)
      await user.type(input, 'Le')

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument()
      })

      await user.click(screen.getByText('LeBron James'))
      expect(input).toHaveValue('LeBron James')
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    })

    it('navigates dropdown with arrow keys and selects with Enter', async () => {
      const user = userEvent.setup()
      render(<NbaPlayerAnalysis />)

      const input = screen.getByPlaceholderText('Search player...')
      await user.clear(input)
      await user.type(input, 'Le')

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument()
      })

      const getOptions = () => within(screen.getByRole('listbox')).getAllByRole('option')

      // Arrow down to first item
      await user.keyboard('{ArrowDown}')
      await waitFor(() => {
        expect(getOptions()[0]).toHaveAttribute('aria-selected', 'true')
      })

      // Arrow down to second item
      await user.keyboard('{ArrowDown}')
      await waitFor(() => {
        expect(getOptions()[1]).toHaveAttribute('aria-selected', 'true')
        expect(getOptions()[0]).toHaveAttribute('aria-selected', 'false')
      })

      // Arrow up back to first item
      await user.keyboard('{ArrowUp}')
      await waitFor(() => {
        expect(getOptions()[0]).toHaveAttribute('aria-selected', 'true')
      })

      // Enter to select
      await user.keyboard('{Enter}')
      await waitFor(() => {
        expect(input).toHaveValue('LeBron James')
        expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
      })
    })

    it('closes dropdown on Escape', async () => {
      const user = userEvent.setup()
      render(<NbaPlayerAnalysis />)

      const input = screen.getByPlaceholderText('Search player...')
      await user.clear(input)
      await user.type(input, 'Le')

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument()
      })

      await user.keyboard('{Escape}')
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    })

    it('closes dropdown on click outside', async () => {
      const user = userEvent.setup()
      render(<NbaPlayerAnalysis />)

      const input = screen.getByPlaceholderText('Search player...')
      await user.clear(input)
      await user.type(input, 'Le')

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument()
      })

      // Click outside — use the header
      await user.click(screen.getByText('Defensive Attention Score'))
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    })

    it('highlights item on mouse hover', async () => {
      const user = userEvent.setup()
      render(<NbaPlayerAnalysis />)

      const input = screen.getByPlaceholderText('Search player...')
      await user.clear(input)
      await user.type(input, 'Le')

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument()
      })

      const getOptions = () => within(screen.getByRole('listbox')).getAllByRole('option')
      await user.hover(getOptions()[1])
      await waitFor(() => {
        expect(getOptions()[1]).toHaveAttribute('aria-selected', 'true')
      })
    })
  })

  // ── Analyze Button ──

  it('disables analyze button when player name is empty', async () => {
    const user = userEvent.setup()
    render(<NbaPlayerAnalysis />)

    // Wait for auto-analyze to finish first
    await waitFor(() => {
      expect(screen.getByText('Analyze')).toBeEnabled()
    })

    const input = screen.getByPlaceholderText('Search player...')
    await user.clear(input)
    expect(screen.getByText('Analyze')).toBeDisabled()
  })

  it('enables analyze button after auto-analyze completes', async () => {
    render(<NbaPlayerAnalysis />)
    // Auto-analyze fires on mount, button should re-enable after
    await waitFor(() => {
      expect(screen.getByText('Analyze')).toBeEnabled()
    })
  })

  it('re-analyzes when analyze button is clicked', async () => {
    const user = userEvent.setup()
    render(<NbaPlayerAnalysis />)

    // Wait for auto-analyze to finish
    await waitFor(() => {
      expect(screen.getByText('Analyze')).toBeEnabled()
    })

    const callsBefore = global.fetch.mock.calls.filter(c =>
      c[0].includes('/api/nba/defensive-attention')
    ).length

    await user.click(screen.getByText('Analyze'))

    await waitFor(() => {
      const callsAfter = global.fetch.mock.calls.filter(c =>
        c[0].includes('/api/nba/defensive-attention')
      ).length
      expect(callsAfter).toBeGreaterThan(callsBefore)
    })
  })

  // ── Factor Info Panel ──

  it('toggles factor info panel', async () => {
    const user = userEvent.setup()
    render(<NbaPlayerAnalysis />)

    const toggleBtn = screen.getByText(/What is.*Defensive Attention Score/i)
    await user.click(toggleBtn)
    expect(screen.getByText(/Measures how much a defense focused/)).toBeInTheDocument()

    await user.click(screen.getByText(/Hide.*Defensive Attention Score/i))
    expect(screen.queryByText(/Measures how much a defense focused/)).not.toBeInTheDocument()
  })

  // ── Glossary ──

  it('opens and closes the glossary', async () => {
    const user = userEvent.setup()
    render(<NbaPlayerAnalysis />)

    await user.click(screen.getByText('Glossary'))
    expect(screen.getByText('Core DAS Metrics')).toBeInTheDocument()

    // Close via X button
    await user.click(screen.getByText('\u00d7'))
    expect(screen.queryByText('Core DAS Metrics')).not.toBeInTheDocument()
  })
})
