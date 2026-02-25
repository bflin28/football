# NFL 4th-Down Decision Agent — Project Plan

## Goals
- Build a reproducible workflow to study 4th-down decision making using historical NFL data.
- Train an initial supervised model that recommends **punt**, **field goal attempt**, or **go for it** decisions based on contextual features.
- Lay groundwork for future reinforcement-learning style agents that optimize long-term expected value.

## Data Strategy
- **Source**: [`nflfastR` play-by-play data](https://github.com/nflverse/nflfastR-data) via the [`nfl_data_py`](https://github.com/nflverse/nfl-data-py) Python package.
- **Seasons**: Start with the 2018–2023 regular seasons for modern rule consistency. Extend to playoffs or earlier seasons as needed.
- **Acquisition**: Download parquet files on demand into `data/raw/` using the notebook; cache locally to avoid repeated downloads.
- **Filtering**:
  - Keep plays with `down == 4`.
  - Valid decision outcomes: `play_type` in `{"punt", "field_goal", "run", "pass"}` with `go_for_it` inferred from non-special-teams offensive plays.
  - Exclude plays affected by penalties, fake punts, delays, or missing data when appropriate.

## Feature Engineering
- Core numeric features: yards to go, yard line (yardline_100), score differential, time remaining (game and half), win probability, expected points, distance to FG range.
- Categorical features: offense team, defense team, roof/surface, game situation (home/away), season.
- Derived signals:
  - Field goal make probability from `kick_distance` if available (or custom logistic model using historical FG data).
  - Expected points swing between options using built-in `nflfastR` EPA fields.
  - Indicator for trailing vs. leading, and two-minute warning scenarios.

## Modeling Approach
1. **Baseline classifier** (Notebook Step 1)
   - Train tree-based gradient boosting (e.g., LightGBM or XGBoost) with class weights for imbalance.
   - Compare with simpler logistic regression.
   - Evaluate using accuracy, macro F1, and calibration (Brier score).

2. **Decision policy interpretation** (Notebook Step 2)
   - Translate class probabilities into go/punt/FG recommendations.
   - Use SHAP values or feature importances to explain decisions.

3. **Optional extension**
   - Frame as cost-sensitive classification using expected points per option.
   - Build a small MDP using drive-level transitions for reinforcement learning.

## Notebook Structure
1. Introduction & setup.
2. Environment checks and data download utilities.
3. Data filtering for 4th-down situations.
4. Exploratory analysis (rate of each decision, success metrics, EPA by option).
5. Feature engineering pipeline (train/validation split, encoders, imputers).
6. Baseline model training and evaluation.
7. Visualization of model recommendations vs. historical choices.
8. Next steps & RL considerations.

## Environment Requirements
- Python 3.10 (managed through Conda).
- Key libraries: `pandas`, `numpy`, `scikit-learn`, `lightgbm`, `matplotlib`, `seaborn`, `plotly`, `nfl_data_py`, `pyarrow`.
- Jupyter kernel registered for the environment (`ipykernel`).

## Deliverables & Milestones
- ✅ Project plan (this document).
- ⏳ Conda environment file (`environment.yml`).
- ⏳ Exploratory notebook (`notebooks/4th_down_decision_agent.ipynb`).
- 🔜 README with setup instructions and roadmap.

## Risks & Mitigations
- **Large data volume**: Use season subsets and caching; consider down-sampling for rapid iteration.
- **Class imbalance**: Employ stratified splits and class weights; monitor confusion matrices.
- **Data anomalies**: Keep validation checks for missing kick distances or weird penalty plays.

## Future Enhancements
- Integrate expected-win-probability models for decision cost functions.
- Add simulation to estimate expected win share of alternative decisions.
- Deploy as an interactive dashboard or API once model performance is validated.
