# SharpLine Daily

A lightweight betting dashboard that updates daily with live sportsbook spreads, a model-adjusted line, and a confidence filter that only shows plays at 85% or higher.

## What is included

- A responsive static site in `index.html`, `styles.css`, and `app.js`
- Daily feed data in `data/latest-lines.json`
- A live odds normalization script in `scripts/update_lines.py`
- Model tuning config in `data/model_config.json`
- A simple local server in `scripts/serve.py`

## Run locally

1. Add your API key:

   ```bash
   cp .env.example .env
   ```

   Then set `ODDS_API_KEY` in `.env`.

2. Refresh the output feed:

   ```bash
   python3 scripts/update_lines.py
   ```

3. Start the site:

   ```bash
   python3 scripts/serve.py
   ```

4. Open `http://127.0.0.1:8000`

## How the daily update flow works

`scripts/update_lines.py` calls The Odds API and computes:

- Consensus spread from the average of tracked sportsbook lines
- Adjusted spread from a transparent local model layer
- Recommended side based on the market versus adjusted line gap
- Edge as the absolute difference between consensus and adjusted spread
- Confidence from edge size plus bookmaker agreement

The site then filters the board client-side so only plays with confidence `>= 85` are shown by default.

## Live odds configuration

Environment variables supported by the updater:

- `ODDS_API_KEY`: required
- `ODDS_API_SPORTS`: comma-separated The Odds API sport keys
- `ODDS_API_REGIONS`: defaults to `us`
- `ODDS_API_MARKETS`: defaults to `spreads`
- `ODDS_API_BOOKMAKERS`: optional comma-separated bookmaker keys

The frontend output format stays the same, so the site doesn’t need to change when you change books or sports.

## Adjusted-line model

Right now the live feed is real and the adjusted line is intentionally transparent. The model uses:

- A per-sport home advantage value
- Market agreement or disagreement across books
- A confidence curve tied to edge size and line dispersion

You can tune those values in `data/model_config.json`. If you later want to plug in your own ratings, injury inputs, or a proprietary spread model, the cleanest place is `compute_model_outputs()` in `scripts/update_lines.py`.

## Scheduling a daily refresh

You can schedule this command with `cron`, `launchd`, GitHub Actions, or any hosted scheduler:

```bash
cd /Users/craigcarver/Documents/Codex\ Trial && python3 scripts/update_lines.py
```

If you later want this deployed, the easiest next step is to host the static site on Netlify, Vercel, GitHub Pages, or Cloudflare Pages and run the updater on a daily schedule that commits the refreshed JSON.

## Deploy with GitHub Pages

This repo now includes:

- `.github/workflows/deploy-pages.yml` to publish the static site
- `.github/workflows/refresh-lines.yml` to regenerate `data/latest-lines.json` every day at `11:15 UTC`

To put it live:

1. Create a GitHub repository and push this project to the `main` branch.
2. In GitHub, add a repository secret named `ODDS_API_KEY` with your The Odds API key.
3. In the repo settings, enable GitHub Pages and choose `GitHub Actions` as the source.
4. Run the `Refresh Betting Lines` workflow once manually to confirm the secret is working.
5. Run the `Deploy Pages` workflow or push a new commit to `main`.

After that:

- The site will be hosted on GitHub Pages.
- The daily workflow will refresh the JSON feed and commit it back to the repo.
- Each refresh commit will automatically trigger a new Pages deploy.

If you want a different refresh time, edit the cron entry in `.github/workflows/refresh-lines.yml`. The current schedule is `11:15 UTC`, which is `7:15 AM EDT` or `6:15 AM EST` in the U.S. Eastern time zone.
