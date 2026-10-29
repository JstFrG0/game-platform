export const defaults = () => ({
  year: "2025",
  scope: "default",
  q: "",
  search_scope: "global",
  game_type: "",
  platform_id: "",
  platform_ids: "",
  genre_id: "",
  genre_ids: "",
  mode_id: "",
  mode_ids: "",
  min_rating: "",
  min_rating_count: "",
  sort: "release_desc",
  page_size: "20",
});
const scopes = ["default", "all", "unknown"];
const sorts = [
  "release_desc",
  "release_asc",
  "name_asc",
  "rating_desc",
  "rating_asc",
];
const numeric = {
  year: [1950, 2100],
  platform_id: [0, 2147483647],
  genre_id: [0, 2147483647],
  mode_id: [0, 2147483647],
  min_rating: [0, 100],
  min_rating_count: [0, 2147483647],
  page_size: [1, 100],
};

export function platformIds(value) {
  if (typeof value !== "string" || !value.trim()) return [];
  const parts = value.split(',');
  if (value.length > 1100 || parts.length > 100 || parts.some(p => !/^\d+$/.test(p.trim()) || Number(p) > 2147483647)) return [];
  return [...new Set(parts.map(Number))].sort((a, b) => a - b);
}

export const genreIds = platformIds;
export const modeIds = platformIds;

export function readQuery(query) {
  const filters = defaults();
  for (const key of Object.keys(filters)) {
    const value = query[key];
    if (typeof value !== "string" || value === "") continue;
    if (key === "platform_ids" || key === "genre_ids" || key === "mode_ids") {
      filters[key] = platformIds(value).join(',');
      continue;
    }
    if (key === "scope" && !scopes.includes(value)) continue;
    if (key === "search_scope" && !["global", "filtered"].includes(value)) continue;
    if (key === "sort" && !sorts.includes(value)) continue;
    if (key === "q" && value.length > 100) continue;
    if (key === "game_type" && !/^[a-z_]+$/.test(value)) continue;
    if (key in numeric) {
      const n = Number(value),
        [min, max] = numeric[key];
      if (
        !Number.isFinite(n) ||
        n < min ||
        n > max ||
        (key !== "min_rating" && !Number.isInteger(n))
      )
        continue;
    }
    filters[key] = value;
  }
  filters.genre_ids = genreIds([filters.genre_ids, filters.genre_id].filter(Boolean).join(',')).join(',');
  filters.genre_id = '';
  filters.mode_ids = modeIds([filters.mode_ids, filters.mode_id].filter(Boolean).join(',')).join(',');
  filters.mode_id = '';
  const page = Number(query.page);
  return {
    filters,
    page: Number.isInteger(page) && page >= 1 && page <= 1000000 ? page : 1,
  };
}

export function buildQuery(filters, page = 1) {
  const result = {};
  for (const [key, value] of Object.entries(filters)) {
    if (value !== "" && value !== null && value !== undefined)
      result[key] = String(value).trim();
  }
  result.page = String(page);
  return result;
}

// Store the pre-search view in the route so it survives detail navigation,
// browser back/forward, and refreshing a search-results URL.
export function makeBrowseState(filters, page, position = {}) {
  const state = readQuery(buildQuery({ ...filters, q: "" }, page));
  const coordinate = (value) =>
    typeof value === "number" && Number.isFinite(value)
      ? Math.min(10000000, Math.max(0, value)) : 0;
  return {
    version: 1,
    filters: state.filters,
    page: state.page,
    position: { left: coordinate(position.left), top: coordinate(position.top) },
  };
}

export function readBrowseState(value) {
  if (typeof value !== "string" || value.length > 4096) return null;
  try {
    const state = JSON.parse(value);
    if (!state || state.version !== 1 || !state.filters ||
        typeof state.filters !== "object" || Array.isArray(state.filters) ||
        (typeof state.filters.q === "string" && state.filters.q.trim())) return null;
    return makeBrowseState(state.filters, state.page, state.position ?? {});
  } catch {
    return null;
  }
}

export function buildCatalogQuery(filters, page = 1, browseState = null) {
  const query = buildQuery(filters, page);
  if (query.q && browseState) query.browse = JSON.stringify(browseState);
  return query;
}

export function listParams(filters, page = 1) {
  // A route may contain a saved browsing view; it must never be sent to the API.
  const query = buildQuery(filters, page);
  if (!query.q || filters.search_scope !== "global") return query;
  return {
    q: query.q, search_scope: "global", page: query.page,
    page_size: query.page_size, sort: query.sort,
  };
}
