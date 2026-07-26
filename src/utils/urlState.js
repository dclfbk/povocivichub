import { ALL_POI_CATEGORIES, DEFAULT_MAP_STYLE } from '../config/mapConfig';

// Compact single-letter/digit codes so a shared link stays short (2026-07-25
// feedback: "voglio evitare stringhe troppo lunghe" -- lat/lon/zoom keep
// their full values, everything else (view mode, grid metric, background,
// category set) is a single character).
const POI_VIEW_MODE_CODES = { none: 'n', icons: 'i', heatmap: 'h' };
const POI_VIEW_MODE_FROM_CODE = Object.fromEntries(
  Object.entries(POI_VIEW_MODE_CODES).map(([key, code]) => [code, key])
);

const GRID_METRIC_CODES = { dominant: 'd', mix_index: 'x', res_score: 'r', comm_score: 'c', occa_score: 'o' };
const GRID_METRIC_FROM_CODE = Object.fromEntries(
  Object.entries(GRID_METRIC_CODES).map(([key, code]) => [code, key])
);

const MAP_STYLE_CODES = {
  liberty: 'l', positron: 'p', bright: 'b', dark: 'k', fiord: 'f', aerial: 'a',
  'street-it': 's', 'hiking-it': 'h', 'cycling-it': 'y'
};
const MAP_STYLE_FROM_CODE = Object.fromEntries(
  Object.entries(MAP_STYLE_CODES).map(([key, code]) => [code, key])
);

export const DEFAULT_VIEW_STATE = {
  lat: 46.066,
  lon: 11.155,
  zoom: 14,
  bearing: 0,
  pitch: 0
};

const DEFAULTS = {
  ...DEFAULT_VIEW_STATE,
  showTerrain: false,
  poiViewMode: 'none',
  showGrid: false,
  gridMetric: 'dominant',
  activePoiCategories: ALL_POI_CATEGORIES,
  mapStyle: DEFAULT_MAP_STYLE,
  selectedHexId: null
};

// Category set -> one hex digit bitmask (bit order == ALL_POI_CATEGORIES).
function encodeCategories(categories) {
  let mask = 0;
  ALL_POI_CATEGORIES.forEach((cat, i) => {
    if (categories.includes(cat)) mask |= (1 << i);
  });
  return mask.toString(16);
}

function decodeCategories(code) {
  const mask = parseInt(code, 16);
  if (Number.isNaN(mask)) return DEFAULTS.activePoiCategories;
  return ALL_POI_CATEGORIES.filter((_, i) => (mask & (1 << i)) !== 0);
}

// Reads the current URL's query string into a full state object, falling
// back to defaults for anything missing/invalid.
export function parseUrlState() {
  const params = new URLSearchParams(window.location.search);

  const num = (key, fallback) => {
    const raw = params.get(key);
    if (raw === null) return fallback;
    const n = parseFloat(raw);
    return Number.isFinite(n) ? n : fallback;
  };

  const poiCode = params.get('s');
  const metricCode = params.get('m');
  const styleCode = params.get('bg');
  const catCode = params.get('c');

  return {
    lat: num('lat', DEFAULTS.lat),
    lon: num('lon', DEFAULTS.lon),
    zoom: num('z', DEFAULTS.zoom),
    bearing: num('b', DEFAULTS.bearing),
    pitch: num('p', DEFAULTS.pitch),
    showTerrain: params.get('t') === '1',
    poiViewMode: (poiCode && POI_VIEW_MODE_FROM_CODE[poiCode]) || DEFAULTS.poiViewMode,
    showGrid: params.get('g') === '1',
    gridMetric: (metricCode && GRID_METRIC_FROM_CODE[metricCode]) || DEFAULTS.gridMetric,
    activePoiCategories: catCode ? decodeCategories(catCode) : DEFAULTS.activePoiCategories,
    mapStyle: (styleCode && MAP_STYLE_FROM_CODE[styleCode]) || DEFAULTS.mapStyle,
    selectedHexId: params.get('h3') || null
  };
}

// Builds the query string for the current visible state. lat/lon/zoom are
// always present in full (per explicit request); everything else is
// omitted when at its default value, to keep the shared link as short as
// possible.
export function buildUrlSearch(state) {
  const params = new URLSearchParams();

  params.set('lat', state.lat.toFixed(5));
  params.set('lon', state.lon.toFixed(5));
  params.set('z', state.zoom.toFixed(2));

  if (Math.round(state.bearing) !== 0) params.set('b', Math.round(state.bearing));
  if (Math.round(state.pitch) !== 0) params.set('p', Math.round(state.pitch));
  if (state.showTerrain) params.set('t', '1');
  if (state.poiViewMode !== DEFAULTS.poiViewMode) params.set('s', POI_VIEW_MODE_CODES[state.poiViewMode]);

  if (state.showGrid) {
    params.set('g', '1');
    if (state.gridMetric !== DEFAULTS.gridMetric) params.set('m', GRID_METRIC_CODES[state.gridMetric]);
  }

  const catCode = encodeCategories(state.activePoiCategories);
  if (catCode !== encodeCategories(DEFAULTS.activePoiCategories)) params.set('c', catCode);
  if (state.mapStyle !== DEFAULTS.mapStyle) params.set('bg', MAP_STYLE_CODES[state.mapStyle]);
  if (state.selectedHexId) params.set('h3', state.selectedHexId);

  return params.toString();
}
