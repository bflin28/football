# NFL 4th-Down Decision Agent

Build a data-driven assistant that recommends whether to punt, attempt a field goal, or go for it on 4th down based on historical NFL play-by-play data.

## Quickstart

```bash
conda env create -f environment.yml
conda activate football-4th-down
python -m ipykernel install --user --name football-4th-down --display-name "Python (football-4th-down)"
jupyter lab
```

Open `notebooks/4th_down_decision_agent.ipynb` and follow the step-by-step workflow. The notebook will download play-by-play data on demand (2018–2023 by default) using the `nfl_data_py` package and cache it under `data/raw/`.

## Repository Layout

- `environment.yml` — Conda environment specification with data/ML tooling.
- `docs/project_plan.md` — Detailed roadmap, data strategy, and modeling milestones.
- `notebooks/4th_down_decision_agent.ipynb` — Exploratory analysis and baseline modeling notebook.
- `data/` — Local cache for downloaded datasets (created automatically when you run the notebook).
- `reports/figures/` — Saved plots from the notebook (created on demand).

## Next Steps

- Enrich feature engineering with situational metrics (win probability deltas, weather, drive context).
- Add calibration and cost-sensitive evaluation based on expected points and win probability.
- Explore reinforcement learning or simulation to compare decision policies over entire drives/games.
- Package reusable utilities into a Python module for easier testing and experimentation.
