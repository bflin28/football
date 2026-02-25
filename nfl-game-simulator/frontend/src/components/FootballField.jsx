import React from 'react'
import './FootballField.css'

const FootballField = ({ yardLine, down, ydstogo, posteam }) => {
  // Convert yardline_100 to field position (0-100 from left to right)
  const fieldPosition = yardLine || 50
  
  // Calculate ball position as percentage of field width
  const ballPositionPercent = ((100 - fieldPosition) / 100) * 100
  
  return (
    <div className="football-field">
      <svg viewBox="0 0 1200 300" className="field-svg">
        {/* Field background */}
        <rect x="0" y="0" width="1200" height="300" fill="#2d5016" />
        
        {/* End zones */}
        <rect x="0" y="0" width="120" height="300" fill="#1a3009" />
        <rect x="1080" y="0" width="120" height="300" fill="#1a3009" />
        
        {/* Yard lines */}
        {Array.from({ length: 11 }, (_, i) => (
          <line
            key={i}
            x1={120 + i * 96}
            y1="0"
            x2={120 + i * 96}
            y2="300"
            stroke="white"
            strokeWidth="2"
          />
        ))}
        
        {/* 50 yard line */}
        <line x1="600" y1="0" x2="600" y2="300" stroke="white" strokeWidth="4" />
        
        {/* Hash marks */}
        {Array.from({ length: 21 }, (_, i) => (
          <g key={i}>
            <line
              x1={120 + i * 48}
              y1="75"
              x2={120 + i * 48}
              y2="90"
              stroke="white"
              strokeWidth="1"
            />
            <line
              x1={120 + i * 48}
              y1="210"
              x2={120 + i * 48}
              y2="225"
              stroke="white"
              strokeWidth="1"
            />
          </g>
        ))}
        
        {/* Yard numbers */}
        {[10, 20, 30, 40, 50, 40, 30, 20, 10].map((num, i) => (
          <text
            key={i}
            x={216 + i * 96}
            y="50"
            fill="white"
            fontSize="24"
            textAnchor="middle"
            fontWeight="bold"
          >
            {num}
          </text>
        ))}
        
        {/* Ball position */}
        <circle
          cx={120 + (ballPositionPercent / 100) * 960}
          cy="150"
          r="8"
          fill="#8B4513"
          stroke="white"
          strokeWidth="2"
        />
        
        {/* First down marker */}
        {down && ydstogo && (
          <line
            x1={120 + ((ballPositionPercent + (ydstogo * 0.96)) / 100) * 960}
            y1="50"
            x2={120 + ((ballPositionPercent + (ydstogo * 0.96)) / 100) * 960}
            y2="250"
            stroke="yellow"
            strokeWidth="3"
            strokeDasharray="5,5"
          />
        )}
      </svg>
      
      <div className="field-info">
        <div className="possession">
          {posteam && <span>Possession: {posteam}</span>}
        </div>
        <div className="down-distance">
          {down && ydstogo && (
            <span>{down}{getOrdinalSuffix(down)} & {ydstogo}</span>
          )}
        </div>
        <div className="yard-line">
          {fieldPosition && <span>Ball at {fieldPosition} yard line</span>}
        </div>
      </div>
    </div>
  )
}

const getOrdinalSuffix = (num) => {
  const suffixes = ['st', 'nd', 'rd', 'th']
  const value = num % 100
  return suffixes[(value - 20) % 10] || suffixes[value] || suffixes[0]
}

export default FootballField