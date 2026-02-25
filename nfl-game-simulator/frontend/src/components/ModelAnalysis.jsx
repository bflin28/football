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
} from 'chart.js';
import { Bar, Scatter, Line } from 'react-chartjs-2';
import './ModelAnalysis.css';

ChartJS.register(
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    BarElement,
    Title,
    Tooltip,
    Legend
);

const ModelAnalysis = () => {
    const [modelData, setModelData] = useState(null);
    const [selectedFeature, setSelectedFeature] = useState(null);
    const [featureAnalysis, setFeatureAnalysis] = useState(null);
    const [predictionsData, setPredictionsData] = useState(null);
    const [clusteringData, setClusteringData] = useState(null);
    const [correlationData, setCorrelationData] = useState(null);
    const [activeTab, setActiveTab] = useState('overview');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadModelData();
        loadPredictionsData();
        loadClusteringData();
        loadCorrelationData();
    }, []);

    const loadModelData = async () => {
        try {
            const response = await fetch('/api/model/sample-data');
            const data = await response.json();
            setModelData(data);
            setLoading(false);
        } catch (error) {
            console.error('Error loading model data:', error);
            setLoading(false);
        }
    };

    const loadPredictionsData = async () => {
        try {
            const response = await fetch('/api/model/predictions-sample');
            const data = await response.json();
            setPredictionsData(data);
        } catch (error) {
            console.error('Error loading predictions data:', error);
        }
    };

    const loadClusteringData = async () => {
        try {
            const response = await fetch('/api/model/clustering-data');
            const data = await response.json();
            setClusteringData(data);
        } catch (error) {
            console.error('Error loading clustering data:', error);
        }
    };

    const loadCorrelationData = async () => {
        try {
            const response = await fetch('/api/model/feature-correlation');
            const data = await response.json();
            setCorrelationData(data);
        } catch (error) {
            console.error('Error loading correlation data:', error);
        }
    };

    const renderCorrelationHeatmap = () => {
        if (!correlationData?.correlation_matrix || !correlationData?.features) return null;

        const matrix = correlationData.correlation_matrix;
        const features = correlationData.features;
        
        // Convert correlation matrix to heatmap data
        const heatmapData = [];
        for (let i = 0; i < features.length; i++) {
            for (let j = 0; j < features.length; j++) {
                heatmapData.push({
                    x: features[j],
                    y: features[i],
                    v: matrix[i][j]
                });
            }
        }

        const chartData = {
            datasets: [{
                label: 'Correlation',
                data: heatmapData,
                backgroundColor: (ctx) => {
                    const value = ctx.parsed.v;
                    const alpha = Math.abs(value);
                    if (value > 0) {
                        return `rgba(231, 76, 60, ${alpha})`; // Red for positive correlation
                    } else {
                        return `rgba(52, 152, 219, ${alpha})`; // Blue for negative correlation
                    }
                },
                borderColor: 'rgba(255, 255, 255, 0.8)',
                borderWidth: 1,
                pointRadius: 15,
                pointHoverRadius: 17,
            }]
        };

        const options = {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: '🔥 Feature Correlation Heatmap',
                    font: { size: 18, weight: 'bold' }
                },
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        title: () => '',
                        label: (context) => {
                            const point = context.raw;
                            return [
                                `${point.y} ↔ ${point.x}`,
                                `Correlation: ${point.v.toFixed(3)}`,
                                point.v > 0.7 ? '🟢 Strong Positive' :
                                point.v > 0.3 ? '🟡 Moderate Positive' :
                                point.v < -0.7 ? '🔴 Strong Negative' :
                                point.v < -0.3 ? '🟠 Moderate Negative' : '⚪ Weak'
                            ];
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'category',
                    labels: features,
                    title: {
                        display: true,
                        text: 'Features'
                    },
                    ticks: {
                        maxRotation: 45,
                        minRotation: 45
                    }
                },
                y: {
                    type: 'category',
                    labels: features,
                    title: {
                        display: true,
                        text: 'Features'
                    }
                }
            }
        };

        return (
            <div className="chart-container">
                <Scatter data={chartData} options={options} height={150} />
                <div className="correlation-legend">
                    <h4>🎨 Color Guide:</h4>
                    <div className="correlation-guide">
                        <div className="correlation-item">
                            <div className="correlation-color positive"></div>
                            <span>Positive Correlation (Red)</span>
                        </div>
                        <div className="correlation-item">
                            <div className="correlation-color negative"></div>
                            <span>Negative Correlation (Blue)</span>
                        </div>
                        <div className="correlation-item">
                            <span>💡 Darker colors = stronger correlation</span>
                        </div>
                    </div>
                </div>
            </div>
        );
    };

    const loadFeatureAnalysis = async (featureName) => {
        try {
            setLoading(true);
            const response = await fetch(`/api/model/feature-analysis/${featureName}`);
            const data = await response.json();
            setFeatureAnalysis(data);
            setSelectedFeature(featureName);
            setLoading(false);
        } catch (error) {
            console.error('Error loading feature analysis:', error);
            setLoading(false);
        }
    };

    const renderFeatureImportanceChart = () => {
        if (!modelData?.feature_importance) return null;

        const chartData = {
            labels: modelData.feature_importance.map(f => f.feature),
            datasets: [{
                label: 'Feature Importance',
                data: modelData.feature_importance.map(f => f.importance * 100),
                backgroundColor: modelData.feature_importance.map((_, index) => 
                    index < 3 ? '#e74c3c' : index < 6 ? '#3498db' : '#95a5a6'
                ),
                borderColor: modelData.feature_importance.map((_, index) => 
                    index < 3 ? '#c0392b' : index < 6 ? '#2980b9' : '#7f8c8d'
                ),
                borderWidth: 2,
                borderRadius: 6,
                borderSkipped: false,
            }]
        };

        const options = {
            responsive: true,
            plugins: {
                legend: {
                    display: false
                },
                title: {
                    display: true,
                    text: '🎯 Feature Importance Rankings',
                    font: { size: 18, weight: 'bold' }
                },
                tooltip: {
                    callbacks: {
                        label: (context) => {
                            const feature = modelData.feature_importance[context.dataIndex];
                            return [
                                `Importance: ${context.parsed.y.toFixed(1)}%`,
                                `${feature.description}`
                            ];
                        }
                    }
                }
            },
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Features'
                    },
                    ticks: {
                        maxRotation: 45,
                        minRotation: 45
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'Importance (%)'
                    },
                    beginAtZero: true
                }
            },
            onClick: (event, elements) => {
                if (elements.length > 0) {
                    const index = elements[0].index;
                    const feature = modelData.feature_importance[index];
                    loadFeatureAnalysis(feature.feature);
                }
            }
        };

        return (
            <div className="chart-container">
                <Bar data={chartData} options={options} height={100} />
                <p className="chart-help">💡 Click on any bar to see detailed analysis for that feature</p>
            </div>
        );
    };

    const renderModelMetrics = () => {
        if (!modelData?.model_metrics) return null;

        const metrics = modelData.model_metrics;

        return (
            <div className="metrics-container">
                <h3>Model Performance</h3>
                <div className="metrics-grid">
                    <div className="metric-card">
                        <div className="metric-value">{(metrics.accuracy * 100).toFixed(1)}%</div>
                        <div className="metric-label">Accuracy</div>
                        <div className="metric-description">Overall prediction accuracy</div>
                    </div>
                    <div className="metric-card">
                        <div className="metric-value">{metrics.r2_score.toFixed(3)}</div>
                        <div className="metric-label">R² Score</div>
                        <div className="metric-description">How well model explains variance</div>
                    </div>
                    <div className="metric-card">
                        <div className="metric-value">{metrics.mean_absolute_error.toFixed(3)}</div>
                        <div className="metric-label">Mean Error</div>
                        <div className="metric-description">Average prediction error</div>
                    </div>
                    <div className="metric-card">
                        <div className="metric-value">{metrics.total_features}</div>
                        <div className="metric-label">Features</div>
                        <div className="metric-description">Total input features used</div>
                    </div>
                </div>
            </div>
        );
    };

    const renderPredictionsChart = () => {
        if (!predictionsData?.predictions) return null;

        const chartData = {
            datasets: [{
                label: 'Predictions vs Actual',
                data: predictionsData.predictions.map(pred => ({
                    x: pred.actual,
                    y: pred.predicted
                })),
                backgroundColor: 'rgba(52, 152, 219, 0.6)',
                borderColor: 'rgba(52, 152, 219, 1)',
                borderWidth: 2,
                pointRadius: 5,
                pointHoverRadius: 7,
            }, {
                label: 'Perfect Predictions',
                data: [
                    { x: -0.5, y: -0.5 },
                    { x: 0.5, y: 0.5 }
                ],
                type: 'line',
                borderColor: 'rgba(231, 76, 60, 0.8)',
                borderWidth: 3,
                borderDash: [5, 5],
                pointRadius: 0,
                fill: false
            }]
        };

        const options = {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: '📈 Model Predictions vs Actual Values',
                    font: { size: 18, weight: 'bold' }
                },
                tooltip: {
                    callbacks: {
                        label: (context) => {
                            if (context.datasetIndex === 0) {
                                return [
                                    `Actual: ${context.parsed.x.toFixed(3)}`,
                                    `Predicted: ${context.parsed.y.toFixed(3)}`,
                                    `Error: ${Math.abs(context.parsed.x - context.parsed.y).toFixed(3)}`
                                ];
                            }
                            return null;
                        }
                    }
                }
            },
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Actual Win Probability Added (WPA)'
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'Predicted Win Probability Added (WPA)'
                    }
                }
            }
        };

        return (
            <div className="chart-container">
                <Scatter data={chartData} options={options} height={100} />
                <p className="chart-help">💡 Points closer to the red line indicate better predictions</p>
            </div>
        );
    };

    const renderClusteringChart = () => {
        if (!clusteringData?.clusters) return null;

        // Group data by cluster for multiple datasets
        const clusterGroups = {};
        clusteringData.clusters.forEach(point => {
            if (!clusterGroups[point.cluster]) {
                clusterGroups[point.cluster] = [];
            }
            clusterGroups[point.cluster].push({
                x: point.x,
                y: point.y,
                wpa: point.wpa,
                down: point.down,
                ydstogo: point.ydstogo,
                play_type: point.play_type
            });
        });

        const datasets = Object.entries(clusterGroups).map(([cluster, points]) => ({
            label: cluster,
            data: points,
            backgroundColor: clusteringData.cluster_info[cluster].color + '80',
            borderColor: clusteringData.cluster_info[cluster].color,
            borderWidth: 2,
            pointRadius: 6,
            pointHoverRadius: 8,
        }));

        const options = {
            responsive: true,
            plugins: {
                title: {
                    display: true,
                    text: '🎯 NFL Play Clustering Analysis',
                    font: { size: 18, weight: 'bold' }
                },
                tooltip: {
                    callbacks: {
                        label: (context) => {
                            const point = context.raw;
                            return [
                                `Cluster: ${context.dataset.label}`,
                                `Field Position: ${context.parsed.x} yards`,
                                `Score Diff: ${context.parsed.y}`,
                                `Down: ${point.down}, To Go: ${point.ydstogo}`,
                                `WPA: ${point.wpa?.toFixed(3)}`,
                                `Play: ${point.play_type}`
                            ];
                        }
                    }
                }
            },
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Field Position (yards from opponent goal)'
                    },
                    reverse: true // Closer to goal = smaller number
                },
                y: {
                    title: {
                        display: true,
                        text: 'Score Differential'
                    }
                }
            }
        };

        return (
            <div className="chart-container">
                <Scatter data={{ datasets }} options={options} height={100} />
                <div className="cluster-legend">
                    <h4>🏷️ Cluster Meanings:</h4>
                    {Object.entries(clusteringData.cluster_info).map(([cluster, info]) => (
                        <div key={cluster} className="cluster-info">
                            <div 
                                className="cluster-color" 
                                style={{ backgroundColor: info.color }}
                            ></div>
                            <span><strong>{cluster}:</strong> {info.description}</span>
                        </div>
                    ))}
                </div>
            </div>
        );
    };

    const renderFeatureDetail = () => {
        if (!featureAnalysis) return null;

        const stats = featureAnalysis.statistics;
        const dist = featureAnalysis.distribution;

        return (
            <div className="feature-detail">
                <h3>Feature Analysis: {featureAnalysis.feature_name}</h3>
                
                <div className="feature-stats">
                    <div className="stat-card">
                        <div className="stat-value">{stats.count.toLocaleString()}</div>
                        <div className="stat-label">Total Records</div>
                    </div>
                    {stats.mean && (
                        <div className="stat-card">
                            <div className="stat-value">{stats.mean.toFixed(3)}</div>
                            <div className="stat-label">Mean Value</div>
                        </div>
                    )}
                    <div className="stat-card">
                        <div className="stat-value">{stats.unique_values}</div>
                        <div className="stat-label">Unique Values</div>
                    </div>
                    <div className="stat-card">
                        <div className="stat-value">{stats.min}</div>
                        <div className="stat-label">Min Value</div>
                    </div>
                    <div className="stat-card">
                        <div className="stat-value">{stats.max}</div>
                        <div className="stat-label">Max Value</div>
                    </div>
                </div>

                {dist && dist.type === 'histogram' && (
                    <div className="distribution-chart">
                        <h4>Value Distribution</h4>
                        <div className="histogram">
                            {dist.counts.map((count, index) => (
                                <div key={index} className="histogram-bar">
                                    <div 
                                        className="histogram-bar-fill"
                                        style={{ 
                                            height: `${(count / Math.max(...dist.counts)) * 100}px`,
                                            backgroundColor: '#4ecdc4'
                                        }}
                                        title={`Range: ${dist.bins[index].toFixed(2)} - ${dist.bins[index + 1].toFixed(2)}, Count: ${count}`}
                                    />
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {dist && dist.type === 'categorical' && (
                    <div className="distribution-chart">
                        <h4>Value Distribution</h4>
                        <div className="categorical-chart">
                            {dist.categories.slice(0, 10).map((category, index) => (
                                <div key={index} className="category-bar">
                                    <div className="category-label">{category}</div>
                                    <div className="category-bar-container">
                                        <div 
                                            className="category-bar-fill"
                                            style={{ 
                                                width: `${(dist.counts[index] / Math.max(...dist.counts)) * 100}%`,
                                                backgroundColor: '#ff6b6b'
                                            }}
                                        />
                                    </div>
                                    <div className="category-count">{dist.counts[index]}</div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        );
    };

    if (loading) {
        return (
            <div className="model-analysis loading">
                <div className="loading-spinner"></div>
                <p>Loading model analysis...</p>
            </div>
        );
    }

    return (
        <div className="model-analysis">
            <div className="analysis-header">
                <h1>🤖 NFL Model Analysis</h1>
                <p>Explore your machine learning model's behavior and predictions</p>
            </div>

            <div className="analysis-tabs">
                <button 
                    className={`tab-button ${activeTab === 'overview' ? 'active' : ''}`}
                    onClick={() => setActiveTab('overview')}
                >
                    📊 Overview
                </button>
                <button 
                    className={`tab-button ${activeTab === 'features' ? 'active' : ''}`}
                    onClick={() => setActiveTab('features')}
                >
                    🎯 Feature Importance
                </button>
                <button 
                    className={`tab-button ${activeTab === 'predictions' ? 'active' : ''}`}
                    onClick={() => setActiveTab('predictions')}
                >
                    📈 Predictions
                </button>
                <button 
                    className={`tab-button ${activeTab === 'clustering' ? 'active' : ''}`}
                    onClick={() => setActiveTab('clustering')}
                >
                    🎯 Clustering
                </button>
                <button 
                    className={`tab-button ${activeTab === 'correlation' ? 'active' : ''}`}
                    onClick={() => setActiveTab('correlation')}
                >
                    🔥 Correlations
                </button>
                {selectedFeature && (
                    <button 
                        className={`tab-button ${activeTab === 'detail' ? 'active' : ''}`}
                        onClick={() => setActiveTab('detail')}
                    >
                        🔍 {selectedFeature}
                    </button>
                )}
            </div>

            <div className="analysis-content">
                {activeTab === 'overview' && (
                    <div className="overview-tab">
                        {renderModelMetrics()}
                        <div className="overview-explanation">
                            <h3>Understanding Your Model</h3>
                            <div className="explanation-cards">
                                <div className="explanation-card">
                                    <h4>🎯 What This Model Does</h4>
                                    <p>Your model predicts Win Probability Added (WPA) for NFL plays based on game situation factors like field position, score, and time remaining.</p>
                                </div>
                                <div className="explanation-card">
                                    <h4>📊 How to Read the Metrics</h4>
                                    <ul>
                                        <li><strong>Accuracy:</strong> Higher is better (80%+ is good)</li>
                                        <li><strong>R² Score:</strong> How much variance the model explains (0.7+ is good)</li>
                                        <li><strong>Mean Error:</strong> Average prediction error (lower is better)</li>
                                    </ul>
                                </div>
                                <div className="explanation-card">
                                    <h4>🔍 Next Steps</h4>
                                    <p>Click on <strong>Feature Importance</strong> to see which factors matter most, or <strong>Predictions</strong> to see how well the model performs on actual data.</p>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === 'features' && (
                    <div className="features-tab">
                        {renderFeatureImportanceChart()}
                        <div className="features-explanation">
                            <h3>💡 Understanding Feature Importance</h3>
                            <p>Features are ranked by how much they influence the model's predictions. Click on any feature to see detailed analysis.</p>
                            <ul>
                                <li><strong>Red bars:</strong> Most important features (biggest impact)</li>
                                <li><strong>Teal bars:</strong> Moderately important features</li>
                                <li><strong>Gray bars:</strong> Less important features</li>
                            </ul>
                        </div>
                    </div>
                )}

                {activeTab === 'predictions' && (
                    <div className="predictions-tab">
                        {renderPredictionsChart()}
                        <div className="predictions-explanation">
                            <h3>📈 Model Accuracy Analysis</h3>
                            <p>This scatter plot shows how well your model predicts actual outcomes:</p>
                            <ul>
                                <li><strong>Perfect Line (red):</strong> Where predictions should ideally fall</li>
                                <li><strong>Close to line:</strong> Accurate predictions</li>
                                <li><strong>Far from line:</strong> Model struggles with these situations</li>
                            </ul>
                            {predictionsData?.metrics && (
                                <div className="prediction-metrics">
                                    <p><strong>MAE:</strong> {predictionsData.metrics.mae.toFixed(3)} (average error)</p>
                                    <p><strong>RMSE:</strong> {predictionsData.metrics.rmse.toFixed(3)} (error spread)</p>
                                    <p><strong>R²:</strong> {predictionsData.metrics.r2.toFixed(3)} (correlation)</p>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {activeTab === 'clustering' && (
                    <div className="clustering-tab">
                        {renderClusteringChart()}
                        <div className="clustering-explanation">
                            <h3>🎯 Game Situation Clustering</h3>
                            <p>This visualization groups similar NFL plays by game context:</p>
                            <ul>
                                <li><strong>X-axis:</strong> Field position (closer to goal = left side)</li>
                                <li><strong>Y-axis:</strong> Score differential (positive = winning)</li>
                                <li><strong>Colors:</strong> Different strategic situations</li>
                                <li><strong>Clusters help identify:</strong> When to be aggressive vs conservative</li>
                            </ul>
                        </div>
                    </div>
                )}

                {activeTab === 'correlation' && (
                    <div className="correlation-tab">
                        {renderCorrelationHeatmap()}
                        <div className="correlation-explanation">
                            <h3>🔥 Feature Relationships</h3>
                            <p>This heatmap shows how NFL statistics relate to each other:</p>
                            <ul>
                                <li><strong>Red points:</strong> Positive correlation (when one goes up, other goes up)</li>
                                <li><strong>Blue points:</strong> Negative correlation (when one goes up, other goes down)</li>
                                <li><strong>Darker colors:</strong> Stronger relationships</li>
                                <li><strong>Use this to find:</strong> Which stats predict each other</li>
                            </ul>
                        </div>
                    </div>
                )}

                {activeTab === 'detail' && renderFeatureDetail()}
            </div>
        </div>
    );
};

export default ModelAnalysis;