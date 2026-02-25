import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import nfl_data_py as nfl
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import LabelEncoder
from sklearn.cluster import KMeans
import warnings
warnings.filterwarnings('ignore')

# Page config
st.set_page_config(
    page_title="🏈 NFL 4th Down Decision Analysis",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        color: #1f4e79;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data
def load_nfl_data():
    """Load and preprocess NFL play-by-play data"""
    with st.spinner("🏈 Loading NFL data..."):
        try:
            # Use existing parquet file from the workspace
            pbp = pd.read_parquet('data/raw/pbp_2023.parquet')
            st.success("✅ Loaded 2023 season data from local file")
        except Exception as e:
            st.warning(f"Could not load local 2023 data: {e}")
            try:
                # Try 2022 data
                pbp = pd.read_parquet('data/raw/pbp_2022.parquet') 
                st.info("🔄 Loaded 2022 season data instead")
            except Exception as e2:
                st.error(f"Could not load any local data: {e2}")
                # Last resort - download 2022 data
                st.info("📥 Downloading 2022 data...")
                pbp = nfl.import_pbp_data([2022], cache=False)
        
        # Filter for relevant plays (4th down focus)
        pbp_filtered = pbp[
            (pbp['play_type'].isin(['pass', 'run'])) &
            (pbp['down'].notna()) &
            (pbp['ydstogo'].notna()) &
            (pbp['yardline_100'].notna()) &
            (pbp['score_differential'].notna())
        ].copy()
        
        # Add some derived features
        pbp_filtered['red_zone'] = pbp_filtered['yardline_100'] <= 20
        pbp_filtered['goal_line'] = pbp_filtered['yardline_100'] <= 5
        pbp_filtered['fourth_down'] = pbp_filtered['down'] == 4
        pbp_filtered['short_yardage'] = pbp_filtered['ydstogo'] <= 2
        
        return pbp_filtered

@st.cache_data
def train_model(data):
    """Train a simple model for demonstration"""
    # Select features and target
    features = ['down', 'ydstogo', 'yardline_100', 'score_differential', 'qtr']
    target = 'wpa'  # Win Probability Added
    
    # Filter data with required columns
    model_data = data[features + [target]].dropna()
    
    X = model_data[features]
    y = model_data[target]
    
    # Train-test split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Train model
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    
    # Get feature importance
    importance_df = pd.DataFrame({
        'feature': features,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)
    
    # Make predictions for analysis
    y_pred = model.predict(X_test)
    
    return model, importance_df, X_test, y_test, y_pred

def main():
    # Header
    st.markdown('<h1 class="main-header">🏈 NFL 4th Down Decision Analysis</h1>', unsafe_allow_html=True)
    
    # Sidebar
    st.sidebar.title("🎛️ Analysis Options")
    
    # Load data
    data = load_nfl_data()
    
    # Sidebar metrics
    st.sidebar.markdown("### 📊 Data Overview")
    st.sidebar.metric("Total Plays", f"{len(data):,}")
    st.sidebar.metric("4th Down Plays", f"{len(data[data['fourth_down']]):,}")
    st.sidebar.metric("Red Zone Plays", f"{len(data[data['red_zone']]):,}")
    
    # Analysis tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📈 Overview", "🤖 Model Analysis", "🎯 Clustering", "🔥 Correlations"])
    
    with tab1:
        st.header("📈 NFL Play Analysis Overview")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Down distribution
            fig_down = px.histogram(
                data, x='down', title='📊 Distribution by Down',
                color_discrete_sequence=['#1f77b4']
            )
            fig_down.update_layout(height=400)
            st.plotly_chart(fig_down, use_container_width=True)
            
            # Play type by down
            play_by_down = data.groupby(['down', 'play_type']).size().reset_index(name='count')
            fig_play = px.bar(
                play_by_down, x='down', y='count', color='play_type',
                title='🏃‍♂️ Play Types by Down'
            )
            fig_play.update_layout(height=400)
            st.plotly_chart(fig_play, use_container_width=True)
        
        with col2:
            # Field position analysis
            fig_field = px.histogram(
                data, x='yardline_100', title='📍 Field Position Distribution',
                nbins=20, color_discrete_sequence=['#ff7f0e']
            )
            fig_field.update_layout(height=400)
            st.plotly_chart(fig_field, use_container_width=True)
            
            # Win Probability Added distribution
            fig_wpa = px.histogram(
                data[data['wpa'].notna()], x='wpa', 
                title='📈 Win Probability Added Distribution',
                nbins=30, color_discrete_sequence=['#2ca02c']
            )
            fig_wpa.update_layout(height=400)
            st.plotly_chart(fig_wpa, use_container_width=True)
    
    with tab2:
        st.header("🤖 Machine Learning Model Analysis")
        
        # Train model
        model, importance_df, X_test, y_test, y_pred = train_model(data)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🎯 Feature Importance")
            
            # Feature importance plot
            fig_importance = px.bar(
                importance_df, x='importance', y='feature',
                title='🔥 Most Important Features',
                orientation='h'
            )
            fig_importance.update_layout(height=400)
            st.plotly_chart(fig_importance, use_container_width=True)
            
            # Model performance metrics
            from sklearn.metrics import mean_absolute_error, r2_score
            mae = mean_absolute_error(y_test, y_pred)
            r2 = r2_score(y_test, y_pred)
            
            st.markdown("### 📊 Model Performance")
            col_a, col_b = st.columns(2)
            col_a.metric("Mean Absolute Error", f"{mae:.3f}")
            col_b.metric("R² Score", f"{r2:.3f}")
        
        with col2:
            st.subheader("📈 Predictions vs Actual")
            
            # Scatter plot of predictions vs actual
            fig_pred = go.Figure()
            
            # Add scatter plot
            fig_pred.add_trace(go.Scatter(
                x=y_test, y=y_pred,
                mode='markers',
                name='Predictions',
                marker=dict(color='blue', opacity=0.6)
            ))
            
            # Add perfect prediction line
            min_val, max_val = min(y_test.min(), y_pred.min()), max(y_test.max(), y_pred.max())
            fig_pred.add_trace(go.Scatter(
                x=[min_val, max_val], y=[min_val, max_val],
                mode='lines',
                name='Perfect Predictions',
                line=dict(color='red', dash='dash')
            ))
            
            fig_pred.update_layout(
                title='🎯 Model Accuracy Analysis',
                xaxis_title='Actual WPA',
                yaxis_title='Predicted WPA',
                height=400
            )
            st.plotly_chart(fig_pred, use_container_width=True)
    
    with tab3:
        st.header("🎯 Game Situation Clustering")
        
        # Prepare clustering data
        cluster_data = data[['yardline_100', 'score_differential', 'down', 'ydstogo']].dropna()
        
        # Perform clustering
        kmeans = KMeans(n_clusters=4, random_state=42)
        cluster_data['cluster'] = kmeans.fit_predict(cluster_data[['yardline_100', 'score_differential']])
        
        # Create cluster labels
        cluster_labels = {
            0: "🔴 Red Zone Pressure",
            1: "🟡 Midfield Battle", 
            2: "🟢 Scoring Territory",
            3: "🔵 Deep Field"
        }
        cluster_data['cluster_label'] = cluster_data['cluster'].map(cluster_labels)
        
        # Clustering visualization
        fig_cluster = px.scatter(
            cluster_data, 
            x='yardline_100', y='score_differential',
            color='cluster_label',
            title='🎯 NFL Play Clustering by Game Situation',
            labels={
                'yardline_100': 'Yards from Goal',
                'score_differential': 'Score Differential'
            },
            hover_data=['down', 'ydstogo']
        )
        fig_cluster.update_layout(height=500)
        st.plotly_chart(fig_cluster, use_container_width=True)
        
        # Cluster analysis
        st.subheader("📊 Cluster Analysis")
        cluster_summary = cluster_data.groupby('cluster_label').agg({
            'yardline_100': 'mean',
            'score_differential': 'mean',
            'down': 'mean',
            'ydstogo': 'mean'
        }).round(2)
        
        st.dataframe(cluster_summary, use_container_width=True)
    
    with tab4:
        st.header("🔥 Feature Correlation Analysis")
        
        # Select numeric columns for correlation
        numeric_cols = ['down', 'ydstogo', 'yardline_100', 'score_differential', 'qtr', 'wpa']
        corr_data = data[numeric_cols].dropna()
        
        # Calculate correlation matrix
        corr_matrix = corr_data.corr()
        
        # Create correlation heatmap
        fig_corr = px.imshow(
            corr_matrix,
            title='🔥 Feature Correlation Heatmap',
            color_continuous_scale='RdBu',
            aspect='auto'
        )
        fig_corr.update_layout(height=500)
        st.plotly_chart(fig_corr, use_container_width=True)
        
        # Correlation insights
        st.subheader("🔍 Key Correlations")
        
        # Find strongest correlations
        corr_pairs = []
        for i in range(len(corr_matrix.columns)):
            for j in range(i+1, len(corr_matrix.columns)):
                corr_pairs.append({
                    'Feature 1': corr_matrix.columns[i],
                    'Feature 2': corr_matrix.columns[j],
                    'Correlation': corr_matrix.iloc[i, j]
                })
        
        corr_df = pd.DataFrame(corr_pairs)
        corr_df = corr_df.reindex(corr_df['Correlation'].abs().sort_values(ascending=False).index)
        
        st.dataframe(corr_df.head(10), use_container_width=True)
    
    # Footer
    st.markdown("---")
    st.markdown("🏈 **NFL 4th Down Analysis** | Built with Streamlit & NFL Data")

if __name__ == "__main__":
    main()