#!/usr/bin/env python3
"""Pull live sportsbook spreads and normalize them for the site.

Live market odds come from The Odds API v4 odds endpoint.
The "adjusted line" is produced by a transparent local model layer so we can
swap in your own handicapping logic later without changing the frontend.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_FILE = DATA_DIR / "latest-lines.json"
MODEL_CONFIG_FILE = DATA_DIR / "model_config.json"

ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"
DEFAULT_SPORTS = (
  "basketball_ncaab",
  "basketball_nba",
  "baseball_mlb",
)
SPORT_LABELS = {
  "americanfootball_ncaaf": "NCAA Football",
  "americanfootball_nfl": "NFL",
  "baseball_mlb": "MLB",
  "basketball_nba": "NBA",
  "basketball_ncaab": "NCAA Basketball",
  "icehockey_nhl": "NHL",
}
DEFAULT_MODEL_CONFIG = {
  "global": {
    "home_advantage": 0.35,
    "dispersion_weight": 0.4,
    "edge_to_confidence": 7.5,
    "agreement_weight": 12.0,
    "min_books": 2,
  },
  "sports": {
    "NCAA Basketball": {"home_advantage": 0.9, "dispersion_weight": 0.45},
    "NBA": {"home_advantage": 0.75, "dispersion_weight": 0.35},
    "MLB": {"home_advantage": 0.2, "dispersion_weight": 0.3},
  },
}


class OddsApiError(RuntimeError):
  """Raised when the live odds provider cannot be queried successfully."""


@dataclass
class SportsbookLine:
  sportsbook: str
  home_spread: float


@dataclass
class SourceGame:
  sport: str
  start_time: str
  home_team: str
  away_team: str
  model_home_spread: float
  model_confidence: int
  notes: str
  lines: List[SportsbookLine]


def load_dotenv() -> None:
  dotenv_file = ROOT / ".env"
  if not dotenv_file.exists():
    return

  for line in dotenv_file.read_text(encoding="utf-8").splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
      continue
    key, value = stripped.split("=", 1)
    os.environ.setdefault(key.strip(), value.strip())


def load_model_config() -> dict:
  if not MODEL_CONFIG_FILE.exists():
    return DEFAULT_MODEL_CONFIG

  with MODEL_CONFIG_FILE.open("r", encoding="utf-8") as handle:
    return json.load(handle)


def env_list(name: str, default: Iterable[str]) -> List[str]:
  raw_value = os.environ.get(name, "")
  if not raw_value.strip():
    return list(default)
  return [item.strip() for item in raw_value.split(",") if item.strip()]


def get_required_api_key() -> str:
  api_key = os.environ.get("ODDS_API_KEY", "").strip()
  if not api_key:
    raise OddsApiError(
      "Missing ODDS_API_KEY. Add your The Odds API key to the environment before running the updater."
    )
  return api_key


def fetch_json(url: str) -> list:
  try:
    with urlopen(url, timeout=30) as response:
      return json.loads(response.read().decode("utf-8"))
  except HTTPError as error:
    body = error.read().decode("utf-8", errors="replace")
    raise OddsApiError(f"The Odds API request failed with HTTP {error.code}: {body}") from error
  except URLError as error:
    raise OddsApiError(f"Could not reach The Odds API: {error.reason}") from error


def build_odds_url(api_key: str, sport_key: str) -> str:
  params = {
    "apiKey": api_key,
    "regions": os.environ.get("ODDS_API_REGIONS", "us"),
    "markets": os.environ.get("ODDS_API_MARKETS", "spreads"),
    "oddsFormat": os.environ.get("ODDS_API_ODDS_FORMAT", "american"),
    "dateFormat": os.environ.get("ODDS_API_DATE_FORMAT", "iso"),
  }
  bookmakers = os.environ.get("ODDS_API_BOOKMAKERS", "").strip()
  if bookmakers:
    params["bookmakers"] = bookmakers

  query = urlencode(params)
  return f"{ODDS_API_BASE_URL}/sports/{sport_key}/odds/?{query}"


def extract_spread_from_market(bookmaker: dict, home_team: str) -> Optional[SportsbookLine]:
  markets = bookmaker.get("markets", [])
  spread_market = next((market for market in markets if market.get("key") == "spreads"), None)
  if not spread_market:
    return None

  outcomes = spread_market.get("outcomes", [])
  home_outcome = next((outcome for outcome in outcomes if outcome.get("name") == home_team), None)
  if not home_outcome or home_outcome.get("point") is None:
    return None

  return SportsbookLine(
    sportsbook=bookmaker.get("title", bookmaker.get("key", "Unknown")),
    home_spread=float(home_outcome["point"]),
  )


def clamp_confidence(value: float) -> int:
  return max(50, min(99, round(value)))


def compute_model_outputs(
  sport: str,
  home_team: str,
  away_team: str,
  lines: List[SportsbookLine],
  config: dict,
) -> tuple[float, int, str]:
  global_config = config.get("global", {})
  sport_config = config.get("sports", {}).get(sport, {})

  home_advantage = float(sport_config.get("home_advantage", global_config.get("home_advantage", 0.35)))
  dispersion_weight = float(sport_config.get("dispersion_weight", global_config.get("dispersion_weight", 0.4)))
  edge_to_confidence = float(global_config.get("edge_to_confidence", 7.5))
  agreement_weight = float(global_config.get("agreement_weight", 12.0))

  home_spreads = [line.home_spread for line in lines]
  consensus_home_spread = round(mean(home_spreads), 1)
  dispersion = pstdev(home_spreads) if len(home_spreads) > 1 else 0.0

  direction = -1 if consensus_home_spread <= 0 else 1
  adjustment = (home_advantage * direction) + (dispersion * dispersion_weight * direction)
  model_home_spread = round(consensus_home_spread + adjustment, 1)

  edge = abs(model_home_spread - consensus_home_spread)
  agreement_score = max(0.0, 1.5 - dispersion)
  confidence = clamp_confidence(62 + (edge * edge_to_confidence) + (agreement_score * agreement_weight))

  favored_team = home_team if consensus_home_spread <= 0 else away_team
  notes = (
    f"Live consensus from {len(lines)} books. Adjusted line applies a transparent "
    f"{sport.lower()} home-edge and bookmaker-agreement weighting, leaning {favored_team}."
  )
  return model_home_spread, confidence, notes


def load_source_games() -> Iterable[SourceGame]:
  api_key = get_required_api_key()
  sport_keys = env_list("ODDS_API_SPORTS", DEFAULT_SPORTS)
  config = load_model_config()
  minimum_books = int(config.get("global", {}).get("min_books", 2))

  for sport_key in sport_keys:
    raw_games = fetch_json(build_odds_url(api_key, sport_key))
    sport_label = SPORT_LABELS.get(sport_key, sport_key)

    for game in raw_games:
      lines = []
      for bookmaker in game.get("bookmakers", []):
        line = extract_spread_from_market(bookmaker, game["home_team"])
        if line:
          lines.append(line)

      if len(lines) < minimum_books:
        continue

      model_home_spread, model_confidence, notes = compute_model_outputs(
        sport=sport_label,
        home_team=game["home_team"],
        away_team=game["away_team"],
        lines=lines,
        config=config,
      )

      yield SourceGame(
        sport=sport_label,
        start_time=game["commence_time"],
        home_team=game["home_team"],
        away_team=game["away_team"],
        model_home_spread=model_home_spread,
        model_confidence=model_confidence,
        notes=notes,
        lines=lines,
      )


def build_output_game(game: SourceGame) -> dict:
  consensus_home_spread = round(mean(line.home_spread for line in game.lines), 1)
  consensus_is_home_favorite = consensus_home_spread < 0
  adjusted_is_home_favorite = game.model_home_spread < 0

  consensus_favorite = game.home_team if consensus_is_home_favorite else game.away_team
  adjusted_favorite = game.home_team if adjusted_is_home_favorite else game.away_team

  if game.model_home_spread < consensus_home_spread:
    recommended_team = game.home_team
    recommended_line = consensus_home_spread
  else:
    recommended_team = game.away_team
    recommended_line = round(consensus_home_spread * -1, 1)

  return {
    "sport": game.sport,
    "start_time": game.start_time,
    "home_team": game.home_team,
    "away_team": game.away_team,
    "consensus": {
      "favorite": consensus_favorite,
      "spread": -abs(consensus_home_spread),
    },
    "adjusted": {
      "favorite": adjusted_favorite,
      "spread": -abs(game.model_home_spread),
    },
    "recommended_side": {
      "team": recommended_team,
      "line": recommended_line,
    },
    "edge": round(abs(game.model_home_spread - consensus_home_spread), 1),
    "confidence": game.model_confidence,
    "sportsbooks": [line.sportsbook for line in game.lines],
    "notes": game.notes,
  }


def write_latest_file(games: Iterable[SourceGame]) -> None:
  materialized_games = [build_output_game(game) for game in games]
  payload = {
    "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    "source": {
      "provider": "The Odds API",
      "markets": os.environ.get("ODDS_API_MARKETS", "spreads"),
      "sports": env_list("ODDS_API_SPORTS", DEFAULT_SPORTS),
      "model": "Local transparent heuristic",
    },
    "games": materialized_games,
  }
  with OUTPUT_FILE.open("w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)
    handle.write("\n")


if __name__ == "__main__":
  load_dotenv()
  try:
    write_latest_file(load_source_games())
    print(f"Wrote {OUTPUT_FILE}")
  except OddsApiError as error:
    print(f"Error: {error}")
    raise SystemExit(1)
