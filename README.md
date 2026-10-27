# 墨場 COURT NOIR

The GitHub Pages root is the integrated public NBA research platform, branded 墨場 COURT NOIR. The original research terminal remains at `research.html`; all original model, audit and team analysis tools remain available there.

- `index.html`, `platform.css`, `platform.js`: four consistent sections for games, prediction records, teams/players, and platform methodology.
- Public views load the existing published datasets without embedding credentials or private records. Single-game views show moneyline, spread and totals research only when generation predates tipoff. Finished games never receive newly calculated pregame forecasts.
- `data/integration-status.json`: manually checked aggregate snapshot of private integration, with explicit as-of time and 24-hour staleness notice. It is not an automatic private-to-public synchronization channel.
- Player averages use at most five observed regular-season appearances, omit DNP, preserve missing values and deduplicate event/player/team. They are descriptive, not player ratings or projected minutes.
- Results use the original historical Git-commit audit. Excluded games do not enter denominators. Unattested market provenance remains explicit; replay results are not prospective records.

This is an internal research beta. There is no checkout, subscriber authentication or cleared commercial redistribution license. APEX, mixture and online candidates have no authorized public prospective output. New player factors are collected privately as sidecar data and are not yet inputs to public forecast weights.

Validation: `node --check platform.js` and `python3 -m unittest discover -s tests -v` (requires BeautifulSoup4). GitHub Actions runs checks on PRs and deploys Pages on main.


2026-10-28 product update: warm paper/ink/copper brand, original court/lapel SVG mark, five suited figures with basketballs and books in an optional 3.4-second opening, next available game day by default, explicit tomorrow/today actions and shareable date URLs. Every available pregame Elo card and detail now includes its source-backed Chinese report (roughly 200 characters) and generation time. Intro is skippable, session-limited and bypassed for reduced motion.

The countable factor research, 40 candidate screening entries, 13 selected methods/results readings, limitations, correction checks and proposed validation protocol are in `docs/COUNTABLE_FACTORS_RESEARCH_20261028.md`. These are draft research rules, not trained weights or published new forecasts.
