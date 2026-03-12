const DATA_PATH = "./data/latest-lines.json";

const state = {
  games: [],
  selectedSport: "ALL",
  minConfidence: 85,
};

const elements = {
  sportFilter: document.querySelector("#sportFilter"),
  confidenceFilter: document.querySelector("#confidenceFilter"),
  confidenceValue: document.querySelector("#confidenceValue"),
  lastUpdated: document.querySelector("#lastUpdated"),
  feedSource: document.querySelector("#feedSource"),
  qualifiedCount: document.querySelector("#qualifiedCount"),
  summaryGrid: document.querySelector("#summaryGrid"),
  cards: document.querySelector("#cards"),
  emptyState: document.querySelector("#emptyState"),
  template: document.querySelector("#gameCardTemplate"),
};

const formatSignedNumber = (value) => {
  if (value > 0) {
    return `+${value}`;
  }
  return `${value}`;
};

const formatSpread = (team, spread) => `${team} ${formatSignedNumber(spread)}`;

const formatLocalDate = (isoString) => {
  const date = new Date(isoString);
  return new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
};

const renderSummary = (games) => {
  const summaries = [
    {
      label: "Avg confidence",
      value: `${Math.round(games.reduce((total, game) => total + game.confidence, 0) / Math.max(games.length, 1))}%`,
    },
    {
      label: "Top edge",
      value: `${Math.max(...games.map((game) => game.edge), 0).toFixed(1)} pts`,
    },
    {
      label: "Sports covered",
      value: `${new Set(games.map((game) => game.sport)).size}`,
    },
    {
      label: "Books tracked",
      value: `${Math.max(...games.map((game) => game.sportsbooks.length), 0)}`,
    },
  ];

  elements.summaryGrid.innerHTML = "";
  summaries.forEach((item) => {
    const card = document.createElement("article");
    card.className = "summary-card";
    card.innerHTML = `
      <p class="label">${item.label}</p>
      <p class="value">${item.value}</p>
    `;
    elements.summaryGrid.appendChild(card);
  });
};

const renderCards = () => {
  const filteredGames = state.games.filter((game) => {
    const matchesSport = state.selectedSport === "ALL" || game.sport === state.selectedSport;
    const matchesConfidence = game.confidence >= state.minConfidence;
    return matchesSport && matchesConfidence;
  });

  elements.qualifiedCount.textContent = filteredGames.length;
  elements.cards.innerHTML = "";
  elements.emptyState.classList.toggle("hidden", filteredGames.length !== 0);
  renderSummary(filteredGames);

  filteredGames
    .sort((left, right) => right.confidence - left.confidence)
    .forEach((game) => {
      const fragment = elements.template.content.cloneNode(true);
      fragment.querySelector(".sport-tag").textContent = game.sport;
      fragment.querySelector(".matchup").textContent = `${game.away_team} at ${game.home_team}`;
      fragment.querySelector(".confidence-pill").textContent = `${game.confidence}% confidence`;
      fragment.querySelector(".start-time").textContent = formatLocalDate(game.start_time);
      fragment.querySelector(".consensus-spread").textContent = formatSpread(game.consensus.favorite, game.consensus.spread);
      fragment.querySelector(".adjusted-spread").textContent = formatSpread(game.adjusted.favorite, game.adjusted.spread);
      fragment.querySelector(".recommended-side").textContent = `${game.recommended_side.team} ${formatSignedNumber(game.recommended_side.line)}`;
      fragment.querySelector(".edge-value").textContent = `${game.edge.toFixed(1)} pts`;
      fragment.querySelector(".notes").textContent = game.notes;

      const sportsbookList = fragment.querySelector(".sportsbook-list");
      game.sportsbooks.forEach((book) => {
        const item = document.createElement("li");
        item.textContent = book;
        sportsbookList.appendChild(item);
      });

      elements.cards.appendChild(fragment);
    });
};

const populateSportFilter = () => {
  const sports = [...new Set(state.games.map((game) => game.sport))].sort();
  sports.forEach((sport) => {
    const option = document.createElement("option");
    option.value = sport;
    option.textContent = sport;
    elements.sportFilter.appendChild(option);
  });
};

const bindEvents = () => {
  elements.sportFilter.addEventListener("change", (event) => {
    state.selectedSport = event.target.value;
    renderCards();
  });

  elements.confidenceFilter.addEventListener("input", (event) => {
    state.minConfidence = Number(event.target.value);
    elements.confidenceValue.textContent = `${state.minConfidence}%`;
    renderCards();
  });
};

const bootstrap = async () => {
  try {
    const response = await fetch(DATA_PATH);
    const payload = await response.json();
    state.games = payload.games;
    elements.lastUpdated.textContent = formatLocalDate(payload.generated_at);
    if (payload.source) {
      elements.feedSource.textContent = `${payload.source.provider} • ${payload.source.model}`;
    }
    populateSportFilter();
    bindEvents();
    renderCards();
  } catch (error) {
    elements.lastUpdated.textContent = "Data unavailable";
    elements.feedSource.textContent = "Live feed unavailable";
    elements.cards.innerHTML = `<p>Unable to load the daily line feed. ${error.message}</p>`;
  }
};

bootstrap();
