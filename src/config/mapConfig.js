import booleanPointInPolygon from '@turf/boolean-point-in-polygon';
import { Home, Bus, Trees, BookOpen } from 'lucide-react';

// Shared styling for POI categories, used by both the map (colors) and the
// sidebar layer switcher (legend icons/labels).
export const CATEGORY_STYLES = {
  residenti: { label: 'Residenti', color: '#60a5fa', icon: Home },
  pendolari: { label: 'Pendolari', color: '#fbbf24', icon: Bus },
  occasionali: { label: 'Occasionali', color: '#f472b6', icon: Trees },
  cross_civic: { label: 'Luoghi Pubblici', color: '#34d399', icon: BookOpen }
};

export const ALL_POI_CATEGORIES = Object.keys(CATEGORY_STYLES);

// Selectable background maps. The first 5 are complete OpenFreeMap vector
// styles (fetched as a style.json URL); 'aerial' is a single raster XYZ
// layer (2019 Trento orthophoto), not a full style, so Map.jsx builds a
// minimal raster-only style object for it instead of passing the tile URL
// straight to setStyle.
export const MAP_STYLES = {
  liberty: { label: 'Liberty', url: 'https://tiles.openfreemap.org/styles/liberty' },
  positron: { label: 'Positron', url: 'https://tiles.openfreemap.org/styles/positron' },
  bright: { label: 'Bright', url: 'https://tiles.openfreemap.org/styles/bright' },
  dark: { label: 'Dark', url: 'https://tiles.openfreemap.org/styles/dark' },
  fiord: { label: 'Fiord', url: 'https://tiles.openfreemap.org/styles/fiord' },
  aerial: {
    label: 'Ortofotocarta Trento 2019',
    // The given tiles.openaerialmap.org URL 302-redirects to this exact
    // titiler.hotosm.org endpoint (same COG file, verified stable across
    // z/x/y). Using it directly avoids a real browser limitation: the
    // openaerialmap.org redirect hop carries no Access-Control-Allow-Origin
    // header, which fails MapLibre's fetch()-based raster tile loading with
    // a CORS error even though the final destination allows it (confirmed
    // in-browser: fetching the redirecting URL fails, fetching this one
    // succeeds with `access-control-allow-origin: *`).
    tiles: [
      'https://titiler.hotosm.org/cog/tiles/WebMercatorQuad/{z}/{x}/{y}@1x' +
      '?url=https://oin-hotosm-temp.s3.us-east-1.amazonaws.com/60770b0fb85cd80007a01414/0/60770b0fb85cd80007a01415.tif'
    ]
  }
};
export const DEFAULT_MAP_STYLE = 'liberty';

// Heatmap radius: user-adjustable via the sidebar slider (2026-07-26
// feedback). The slider value is the radius (px) at zoom 15; zoom 11 scales
// down proportionally (0.75x) so the map still zooms into visibly tighter
// blobs the same way the previous fixed 15->30 stops did. DEFAULT_HEATMAP_RADIUS
// (30) reproduces that exact original fixed radius when untouched.
export const DEFAULT_HEATMAP_RADIUS = 30;
export const HEATMAP_RADIUS_RANGE = { min: 10, max: 60 };

export function buildHeatmapRadiusExpression(radius) {
  const r = typeof radius === 'number' && Number.isFinite(radius) ? radius : DEFAULT_HEATMAP_RADIUS;
  return ['interpolate', ['linear'], ['zoom'], 11, r * 0.5, 15, r];
}

export function buildMapStyleDefinition(styleKey) {
  const cfg = MAP_STYLES[styleKey] || MAP_STYLES[DEFAULT_MAP_STYLE];
  if (cfg.url) return cfg.url;
  return {
    version: 8,
    sources: {
      'aerial-raster-src': {
        type: 'raster',
        tiles: cfg.tiles,
        tileSize: 256,
        attribution: 'OpenAerialMap &bull; Provincia Autonoma di Trento (Ortofotocarta 2019)'
      }
    },
    layers: [{ id: 'aerial-raster-layer', type: 'raster', source: 'aerial-raster-src' }]
  };
}

// Flattens every coordinate out of a GeoJSON geometry/feature/FeatureCollection
// into a [minLng, minLat, maxLng, maxLat] bbox. Used to compute the "fit the
// whole Povo boundary" zoom level so the map's zoomed-out limit can be set
// relative to it, without pulling in a full turf bbox module for one call.
export function computeBboxFromGeoJSON(geojson) {
  let minLng = Infinity, minLat = Infinity, maxLng = -Infinity, maxLat = -Infinity;

  const visit = (coords) => {
    if (typeof coords[0] === 'number') {
      const [lng, lat] = coords;
      if (lng < minLng) minLng = lng;
      if (lat < minLat) minLat = lat;
      if (lng > maxLng) maxLng = lng;
      if (lat > maxLat) maxLat = lat;
    } else {
      coords.forEach(visit);
    }
  };

  const features = geojson.type === 'FeatureCollection' ? geojson.features : [geojson];
  features.forEach((f) => {
    const geom = f.geometry || f;
    if (geom && geom.coordinates) visit(geom.coordinates);
  });

  return [minLng, minLat, maxLng, maxLat];
}

// Counts PoIs (by category) whose point geometry falls inside a drawn
// polygon, plus the average ICC score of whatever falls inside. Used by the
// map's "draw an area" tool to compute live indicators for any shape the
// user draws, the same way a selected H3 hexagon shows its own profile.
export function computePoiStatsInPolygon(polygonGeom, poisGeoJSON) {
  const counts = Object.fromEntries(ALL_POI_CATEGORIES.map((cat) => [cat, 0]));
  let total = 0;
  let iccSum = 0;
  let iccCount = 0;

  const features = (poisGeoJSON && poisGeoJSON.features) || [];
  for (const feature of features) {
    const geom = feature.geometry;
    if (!geom || geom.type !== 'Point') continue;
    if (!booleanPointInPolygon(geom.coordinates, polygonGeom)) continue;

    const category = feature.properties && feature.properties.category;
    if (category in counts) counts[category] += 1;
    total += 1;

    const icc = feature.properties && feature.properties.icc_score;
    if (typeof icc === 'number') {
      iccSum += icc;
      iccCount += 1;
    }
  }

  return { counts, total, avgIcc: iccCount > 0 ? iccSum / iccCount : null };
}

// Builds the {key, label, color, value, percentage} segments consumed by
// CategoryStackedBar from a plain {category: count} map.
export function buildCategorySegments(counts) {
  const total = ALL_POI_CATEGORIES.reduce((sum, cat) => sum + (counts[cat] || 0), 0);
  return ALL_POI_CATEGORIES.map((cat) => {
    const value = counts[cat] || 0;
    return {
      key: cat,
      label: CATEGORY_STYLES[cat].label,
      color: CATEGORY_STYLES[cat].color,
      value,
      percentage: total > 0 ? (value / total) * 100 : 0
    };
  });
}

// Builds stacked-bar segments from a selected H3 hexagon's res_score/
// comm_score/occa_score. Only 3 categories: the pipeline doesn't track a
// separate per-hexagon civic score -- cross_civic PoIs feed into both the
// residenti and occasionali hex scores instead (see calculate_scores_and_mixite
// in build_data.py), so there's nothing meaningful to show as a 4th segment
// here the way there is for a drawn area's raw PoI counts.
const HEX_SEGMENT_CATEGORIES = ['residenti', 'pendolari', 'occasionali'];
const HEX_SCORE_FIELD = { residenti: 'res_score', pendolari: 'comm_score', occasionali: 'occa_score' };

export function buildHexSegments(selectedHex) {
  const scores = HEX_SEGMENT_CATEGORIES.map((cat) => parseFloat(selectedHex?.[HEX_SCORE_FIELD[cat]] ?? 0) || 0);
  const total = scores.reduce((a, b) => a + b, 0);
  return HEX_SEGMENT_CATEGORIES.map((cat, i) => ({
    key: cat,
    label: CATEGORY_STYLES[cat].label,
    color: CATEGORY_STYLES[cat].color,
    value: scores[i],
    percentage: total > 0 ? (scores[i] / total) * 100 : 0
  }));
}

// Color ramps per grid metric, shared between the MapLibre fill-color
// expression and the sidebar legend gradient. `dominant` has no gradient
// `stops` -- it's rendered as a categorical case expression (see
// buildDominantCategoryExpression) with its own swatch-style legend.
// Labels avoid jargon ("Mixité", "Mixing", "(R)/(P)/(O)") in favor of plain
// Italian; `info` is the plain-language explanation shown by InfoButton
// (2026-07-25 feedback: these terms aren't self-explanatory to a general
// Italian-speaking audience).
export const GRID_METRICS = {
  dominant: {
    label: 'Vocazione Prevalente dell’Area',
    info: 'Ogni esagono viene colorato in base alla categoria di servizi che prevale al suo interno (Residenti, Pendolari, Occasionali). Quando invece nessuna categoria prevale nettamente e l’area offre un buon equilibrio tra più funzioni, viene evidenziata con un colore distinto come "area mista".'
  },
  mix_index: {
    label: 'Indice di Polifunzionalità',
    stops: [[0.0, '#312e81'], [0.2, '#3b82f6'], [0.45, '#10b981'], [0.75, '#f59e0b'], [1.0, '#ec4899']],
    info: 'Misura quanto un’area riesce a mescolare bene funzioni diverse — abitare, studiare/lavorare, tempo libero — invece di essere dedicata a una sola cosa. Va da 0 (l’area serve praticamente a una sola funzione) a 1 (le funzioni sono ben bilanciate tra loro). Un valore alto indica un quartiere vivo e polifunzionale.'
  },
  res_score: {
    label: 'Presenza Servizi Residenziali',
    stops: [[0.0, '#0f172a'], [0.5, '#3b82f6'], [1.0, '#93c5fd']],
    info: 'Misura quanto quest’area è ricca di servizi di vicinato utili a chi ci abita (scuole, farmacie, negozi alimentari, ecc.), pesato anche in base a quanto sono vicini. Valore da 0 (pochi o lontani) a 1 (molti e vicini).'
  },
  comm_score: {
    label: 'Presenza Flussi Pendolari',
    stops: [[0.0, '#1c1917'], [0.5, '#f59e0b'], [1.0, '#fde68a']],
    info: 'Misura la presenza di poli universitari, biblioteche, mense e fermate del trasporto pubblico — i luoghi frequentati da studenti e pendolari — combinata con la frequenza reale dei mezzi pubblici in quest’area.'
  },
  occa_score: {
    label: 'Presenza Attività Occasionali',
    stops: [[0.0, '#1e1b2e'], [0.5, '#ec4899'], [1.0, '#fbcfe8']],
    info: 'Misura la presenza di luoghi legati al tempo libero occasionale: sentieri, punti panoramici, aree picnic, ristoranti, agriturismi e siti storici.'
  }
};

// Threshold above which a hexagon's mix_index counts as genuinely "mixed"
// (2+ categories in real balance) rather than dominated by one category.
export const MIX_THRESHOLD = 0.65;
// Distinct hue for mixed areas -- deliberately not blue/amber/pink/emerald
// (already used by residenti/pendolari/occasionali/cross_civic) so it reads
// as its own, fifth thing at a glance.
export const MIXED_AREA_COLOR = '#22d3ee';

export function buildFillColorExpression(metric) {
  if (metric === 'dominant') return buildDominantCategoryExpression();
  const cfg = GRID_METRICS[metric] || GRID_METRICS.mix_index;
  const expr = ['interpolate', ['linear'], ['coalesce', ['get', metric], 0]];
  cfg.stops.forEach(([stop, color]) => expr.push(stop, color));
  return expr;
}

// Colors a hexagon by whichever of res_score/comm_score/occa_score dominates,
// or by MIXED_AREA_COLOR when mix_index shows a genuine 2+-category balance --
// so an area's main "vocation" (or its mixed-use status) reads at a glance,
// without clicking (2026-07-25 feedback).
export function buildDominantCategoryExpression() {
  const r = ['coalesce', ['get', 'res_score'], 0];
  const c = ['coalesce', ['get', 'comm_score'], 0];
  const o = ['coalesce', ['get', 'occa_score'], 0];
  return [
    'case',
    ['>=', ['coalesce', ['get', 'mix_index'], 0], MIX_THRESHOLD], MIXED_AREA_COLOR,
    ['all', ['>=', r, c], ['>=', r, o]], CATEGORY_STYLES.residenti.color,
    ['>=', c, o], CATEGORY_STYLES.pendolari.color,
    CATEGORY_STYLES.occasionali.color
  ];
}

// MapLibre filter expression restricting the hex grid to features whose
// current metric value falls in [min, max] -- backs the legend's range
// slider (2026-07-26 feedback). No-op (`null`, meaning "no filter") for the
// categorical `dominant` metric, which has no single numeric value to range
// over, and for a full [0, 1] range (the metrics' whole domain), so the
// common case of "slider untouched" costs nothing extra.
export function buildHexRangeFilter(metric, range) {
  if (metric === 'dominant' || !range) return null;
  const [min, max] = range;
  if (min <= 0 && max >= 1) return null;
  return ['all', ['>=', ['coalesce', ['get', metric], 0], min], ['<=', ['coalesce', ['get', metric], 0], max]];
}

// Five-level semantic reading of a 0-1 score (2026-07-26 feedback: "sappiamo
// che zero è schifo, e che 1 è il massimo. Fai cinque indicatori semantici e
// calcola in automatica dando il valore") -- currently used for the
// Polifunzionalità Index card, but kept generic (any 0-1 score in, a level
// out) rather than hardcoded to mix_index specifically.
export const SEMANTIC_LEVELS_5 = [
  { max: 0.2, label: 'Scarso', emoji: '😞', color: '#ef4444' },
  { max: 0.4, label: 'Basso', emoji: '🙁', color: '#f97316' },
  { max: 0.6, label: 'Medio', emoji: '😐', color: '#eab308' },
  { max: 0.8, label: 'Buono', emoji: '🙂', color: '#84cc16' },
  { max: Infinity, label: 'Ottimo', emoji: '😄', color: '#22c55e' }
];

export function getSemanticLevel5(score) {
  const s = typeof score === 'number' && Number.isFinite(score) ? score : 0;
  const index = SEMANTIC_LEVELS_5.findIndex((lvl) => s <= lvl.max);
  return { ...SEMANTIC_LEVELS_5[index === -1 ? SEMANTIC_LEVELS_5.length - 1 : index], index: index === -1 ? SEMANTIC_LEVELS_5.length - 1 : index };
}

export function gridMetricGradientCss(metric) {
  const cfg = GRID_METRICS[metric] || GRID_METRICS.mix_index;
  if (!cfg || !cfg.stops) return null;
  const colors = cfg.stops.map(([, color]) => color).join(', ');
  return `linear-gradient(to right, ${colors})`;
}

// Cluster circle color, by whichever category has the most points inside that
// cluster (aggregated via the source's clusterProperties: cnt_<category>).
// Ties break in cross_civic > residenti > pendolari > occasionali order.
export function buildClusterCategoryColorExpression() {
  const cc = ['coalesce', ['get', 'cnt_cross_civic'], 0];
  const rs = ['coalesce', ['get', 'cnt_residenti'], 0];
  const pd = ['coalesce', ['get', 'cnt_pendolari'], 0];
  const oc = ['coalesce', ['get', 'cnt_occasionali'], 0];
  return [
    'case',
    ['all', ['>=', cc, rs], ['>=', cc, pd], ['>=', cc, oc]], CATEGORY_STYLES.cross_civic.color,
    ['all', ['>=', rs, pd], ['>=', rs, oc]], CATEGORY_STYLES.residenti.color,
    ['>=', pd, oc], CATEGORY_STYLES.pendolari.color,
    CATEGORY_STYLES.occasionali.color
  ];
}

export const CLUSTER_CATEGORY_PROPERTIES = {
  cnt_cross_civic: ['+', ['case', ['==', ['get', 'category'], 'cross_civic'], 1, 0]],
  cnt_residenti: ['+', ['case', ['==', ['get', 'category'], 'residenti'], 1, 0]],
  cnt_pendolari: ['+', ['case', ['==', ['get', 'category'], 'pendolari'], 1, 0]],
  cnt_occasionali: ['+', ['case', ['==', ['get', 'category'], 'occasionali'], 1, 0]]
};

// Visual glyph + badge color per `icon_name`, as assigned by the Python pipeline's
// ICON_MAP (build_data.py). Colors echo the dominant CATEGORY_STYLES color so the
// unclustered POI icons stay legible against the category legend.
// NOTE: 'bench' and 'viewpoint' are no longer produced by the pipeline (dropped
// as street-furniture noise, 2026-07-25) but are harmless to leave mapped here.
export const ICON_VISUALS = {
  castle: { emoji: '🏰', color: CATEGORY_STYLES.occasionali.color },
  monument: { emoji: '🗿', color: CATEGORY_STYLES.occasionali.color },
  ruins: { emoji: '🏚️', color: CATEGORY_STYLES.occasionali.color },
  historic: { emoji: '🎖️', color: CATEGORY_STYLES.occasionali.color },
  theater: { emoji: '🎭', color: CATEGORY_STYLES.occasionali.color },
  museum: { emoji: '🏛️', color: CATEGORY_STYLES.occasionali.color },
  attraction: { emoji: '🎡', color: CATEGORY_STYLES.occasionali.color },
  viewpoint: { emoji: '🌄', color: CATEGORY_STYLES.occasionali.color },
  restaurant: { emoji: '🍽️', color: CATEGORY_STYLES.occasionali.color },
  cafe: { emoji: '☕', color: CATEGORY_STYLES.occasionali.color },
  hotel: { emoji: '🏨', color: CATEGORY_STYLES.occasionali.color },
  climbing: { emoji: '🧗', color: CATEGORY_STYLES.occasionali.color },
  library: { emoji: '📚', color: CATEGORY_STYLES.pendolari.color },
  college: { emoji: '🎓', color: CATEGORY_STYLES.pendolari.color },
  bus: { emoji: '🚌', color: CATEGORY_STYLES.pendolari.color },
  copyshop: { emoji: '🖨️', color: CATEGORY_STYLES.pendolari.color },
  office_it: { emoji: '💻', color: CATEGORY_STYLES.pendolari.color },
  sport: { emoji: '⚽', color: CATEGORY_STYLES.residenti.color },
  basketball_court: { emoji: '🏀', color: CATEGORY_STYLES.residenti.color },
  volleyball_court: { emoji: '🏐', color: CATEGORY_STYLES.residenti.color },
  tennis_court: { emoji: '🎾', color: CATEGORY_STYLES.residenti.color },
  park: { emoji: '🌳', color: CATEGORY_STYLES.cross_civic.color },
  drinking_water: { emoji: '🚰', color: CATEGORY_STYLES.cross_civic.color },
  bench: { emoji: '🪑', color: CATEGORY_STYLES.cross_civic.color },
  market: { emoji: '🛒', color: CATEGORY_STYLES.cross_civic.color },
  association: { emoji: '🤝', color: CATEGORY_STYLES.cross_civic.color },
  information: { emoji: 'ℹ️', color: '#94a3b8' },
  marker: { emoji: '📍', color: '#94a3b8' },
  // Civic/public-building types that used to all fall back to the plain
  // 'marker' pin (2026-07-26 feedback: keep them gray -- they aren't tied to
  // one social-function color -- but give each its own glyph so a church
  // reads differently from a town hall at a glance).
  place_of_worship: { emoji: '⛪', color: '#94a3b8' },
  community_centre: { emoji: '🏘️', color: '#94a3b8' },
  townhall: { emoji: '🏢', color: '#94a3b8' },
  social_facility: { emoji: '🫂', color: '#94a3b8' },
  shelter: { emoji: '🛖', color: '#94a3b8' },
  square: { emoji: '🏙️', color: '#94a3b8' }
};

// Renders a colored circular badge with an emoji glyph onto an offscreen canvas,
// used to register MapLibre symbol images on demand (see 'styleimagemissing' in
// Map.jsx). Keeping icons self-drawn avoids bundling/licensing an external sprite.
export function createPoiIconImage(iconName) {
  const { emoji, color } = ICON_VISUALS[iconName] || ICON_VISUALS.marker;
  const size = 48;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');

  ctx.beginPath();
  ctx.arc(size / 2, size / 2, size / 2 - 2, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();
  ctx.lineWidth = 3;
  ctx.strokeStyle = '#0f172a';
  ctx.stroke();

  ctx.font = `${Math.round(size * 0.5)}px sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(emoji, size / 2, size / 2 + 2);

  return ctx.getImageData(0, 0, size, size);
}

// Human-friendly Italian label for a POI's raw OSM sub_type value.
const SUB_TYPE_LABELS = {
  fort: 'Forte / Sito Storico',
  castle: 'Castello',
  monument: 'Monumento',
  memorial: 'Monumento Commemorativo',
  archaeological_site: 'Sito Archeologico',
  ruins: 'Rovine',
  museum: 'Museo',
  attraction: 'Attrazione Turistica',
  artwork: "Opera d'Arte Pubblica",
  viewpoint: 'Punto Panoramico',
  picnic_site: 'Area Picnic',
  // Affittacamere/guest house/hotel/agriturismo all read as the same kind of
  // thing to a visitor, so they share one label (2026-07-25 feedback).
  guest_house: 'Struttura Ricettiva',
  hotel: 'Struttura Ricettiva',
  chalet: 'Chalet',
  camp_site: 'Campeggio',
  alpine_hut: 'Rifugio Alpino',
  theatre: 'Teatro',
  arts_centre: 'Centro Culturale',
  cafe: 'Caffè',
  restaurant: 'Ristorante',
  pub: 'Pub',
  bar: 'Bar',
  fast_food: 'Fast Food',
  public_bookcase: 'Bookcrossing',
  community_centre: 'Centro Civico',
  drinking_water: 'Fontanella',
  bench: 'Panchina',
  shelter: 'Rifugio / Pensilina',
  townhall: 'Municipio',
  social_facility: 'Servizio Sociale',
  place_of_worship: 'Luogo di Culto',
  square: 'Piazza',
  university: 'Università',
  research_institute: 'Istituto di Ricerca',
  library: 'Biblioteca',
  canteen: 'Mensa',
  parking: 'Parcheggio',
  bus_stop: 'Fermata Bus',
  station: 'Stazione',
  halt: 'Fermata Ferroviaria',
  park: 'Parco Pubblico',
  garden: 'Giardino Pubblico',
  copyshop: 'Copisteria',
  beauty: 'Centro Estetico',
  hairdresser: 'Parrucchiere',
  deli: 'Rosticceria',
  association: 'Associazione / Circolo',
  ngo: 'Associazione / ONG',
  wilderness_hut: 'Bivacco',
  trench: 'Trincea Storica',
  market: 'Mercato Settimanale',
  historic: 'Stoi Militari',
  sports_centre: 'Centro Sportivo',
  bank: 'Banca',
  climbing: "Falesia d'Arrampicata",
  fitness_station: 'Area Fitness',
  footway: 'Percorso Pedonale',
  kindergarten: "Asilo Nido / Scuola dell'Infanzia",
  platform: 'Fermata Bus',
  post_office: 'Ufficio Postale',
  school: 'Scuola',
  sports_hall: 'Palestra',
  recycling: 'Isola Ecologica',
  playground: 'Parco Giochi',
  information: 'Punto Informativo',
  it: 'Azienda ICT',
  research: 'Ufficio di Ricerca',
  educational_institution: 'Istituto Formativo'
};

// Placeholder banner (data: URI, no network request) shown in the PoI popup
// when `image_url` is missing or was found broken by the pipeline's image
// check -- a colored card with the icon's emoji, instead of hotlinking a
// stock photo we can't vouch for. Reuses ICON_VISUALS so it matches the same
// color/emoji already used for that PoI's map marker.
export function buildPlaceholderImageDataUri(iconName) {
  const { emoji, color } = ICON_VISUALS[iconName] || ICON_VISUALS.marker;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="240" height="120">
    <rect width="240" height="120" fill="${color}"/>
    <text x="120" y="64" font-size="46" text-anchor="middle" dominant-baseline="middle">${emoji}</text>
  </svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

// Only shown once the slope-aware walk is a genuinely noticeable step up from
// a flat-ground walk covering the same distance -- below this, terrain is
// negligible and calling it out just adds noise (2026-07-26 feedback: "la
// fatica che si fa a piedi").
const FATICA_DISPLAY_THRESHOLD_PCT = 10;

function fatigueSuffix(pct) {
  if (typeof pct !== 'number' || pct <= FATICA_DISPLAY_THRESHOLD_PCT) return '';
  const glyph = pct > 40 ? '🥾' : '⛰️';
  return ` <span style="color: #b45309;">${glyph} +${Math.round(pct)}% fatica</span>`;
}

// One row for a walking-reachability target (bus/parking): distance in
// metres, Tobler-weighted walking time, and the fatica suffix above. Omitted
// entirely if the pipeline hasn't computed it for this PoI (t_*_min missing
// -- e.g. data generated before this field existed).
function reachabilityRow(icon, label, distanceM, timeMin, fatiguePct) {
  if (typeof distanceM !== 'number' || typeof timeMin !== 'number') return '';
  return `
    <div style="font-size: 11px; color: #334155; margin-top: 3px;">
      ${icon} ${label}: <strong>${Math.round(distanceM)} m</strong> · ~${timeMin.toFixed(0)} min a piedi${fatigueSuffix(fatiguePct)}
    </div>
  `;
}

function detailRow(icon, label, value) {
  if (!value || String(value).trim().length === 0) return '';
  return `
    <div style="font-size: 11px; color: #334155; margin-top: 3px;">
      ${icon} ${label}: ${value}
    </div>
  `;
}

// Builds the PoI detail popup's inner HTML from a feature's properties.
// Shared between the map's direct-click handler and the PoI table's
// "row click -> fly to it" flow, so both produce the identical rich popup.
// Surfaces every field the pipeline was able to derive for this PoI (OSM +
// the circoscrizione geojson + computed accessibility/altitude/fatica),
//2026-07-26 feedback -- previously only name/category/service-type/social
// function showed, even though address/hours/contacts/website/disabled
// access were already being collected and sitting unused in the data.
export function buildPoiPopupHtml(props) {
  const badge = POPUP_CATEGORY_BADGES[props.category] || { label: props.category, color: '#94a3b8' };
  const serviceType = props.amenity_type || formatSubType(props.sub_type);
  const hasSocialFunction = props.social_function && props.social_function.length > 0;
  const imageSrc = props.image_url && props.image_url.length > 0
    ? props.image_url
    : buildPlaceholderImageDataUri(props.icon_name);
  const secondaryCategories = (props.categoria_secondaria || '').split(',').filter(Boolean);

  const detailsHtml = [
    detailRow('📍', 'Indirizzo', props.indirizzo),
    detailRow('🕐', 'Orari', props.orari_apertura),
    // altitudine_m === 0 means "outside the DTM raster's coverage" (the
    // pipeline's sampling fallback -- see _sample_raster_at_points in
    // build_data.py), not a real sea-level reading in landlocked Trentino,
    // so it's treated as missing data here rather than shown as 0.
    typeof props.altitudine_m === 'number' && props.altitudine_m > 0
      ? detailRow('⛰️', 'Altitudine', `${Math.round(props.altitudine_m)} m s.l.m.`) : '',
    reachabilityRow('🚌', 'Fermata bus/treno più vicina', props.d_bus_m, props.t_bus_min, props.fatica_bus_pct),
    reachabilityRow('🅿️', 'Parcheggio più vicino', props.d_parking_m, props.t_parking_min, props.fatica_parking_pct),
    detailRow('♿', 'Accessibilità disabili', props.accessibilita_disabili),
    detailRow('☎️', 'Contatti', props.contatti),
    props.sito_web ? `
      <div style="font-size: 11px; margin-top: 3px;">
        🌐 <a href="${props.sito_web}" target="_blank" rel="noopener noreferrer" style="color: #4f46e5; text-decoration: underline;">Sito web</a>
      </div>
    ` : ''
  ].filter(Boolean).join('');

  return `
    <div style="font-family: Inter, sans-serif; width: 280px;">
      <img src="${imageSrc}" alt=""
           style="width: 100%; height: 120px; object-fit: cover; display: block;" />
      <div style="padding: 12px;">
        <div style="font-weight: 700; font-size: 14px; color: #0f172a; line-height: 1.3;">
          ${props.name && props.name.length > 0 ? props.name : 'Punto di interesse'}
        </div>
        <span style="display: inline-block; margin-top: 6px; padding: 3px 9px; border-radius: 999px; font-size: 10px; font-weight: 700; color: #ffffff; background: ${badge.color};">
          ${badge.label}
        </span>
        ${props.accesso_pubblico !== false ? `
          <span style="display: inline-block; margin-top: 6px; margin-left: 4px; padding: 3px 9px; border-radius: 999px; font-size: 10px; font-weight: 700; color: #065f46; background: #6ee7b7;">
            🌐 Accesso Pubblico
          </span>
        ` : ''}
        ${secondaryCategories.length > 0 ? `
          <div style="margin-top: 6px;">
            ${secondaryCategories.map((cat) => {
              const secBadge = POPUP_CATEGORY_BADGES[cat] || { label: cat, color: '#94a3b8' };
              return `<span style="display: inline-block; margin-top: 2px; margin-right: 4px; padding: 2px 8px; border-radius: 999px; font-size: 9px; font-weight: 700; color: ${secBadge.color}; background: #ffffff; border: 1.5px solid ${secBadge.color};">
                + ${secBadge.label}
              </span>`;
            }).join('')}
          </div>
        ` : ''}
        ${serviceType ? `
          <div style="font-size: 11px; color: #64748b; margin-top: 6px; font-weight: 600;">
            ${serviceType}
          </div>
        ` : ''}
        ${detailsHtml ? `
          <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid #e2e8f0;">
            ${detailsHtml}
          </div>
        ` : ''}
        ${hasSocialFunction ? `
          <div style="margin-top: 10px; padding-top: 8px; border-top: 1px solid #e2e8f0;">
            <div style="font-size: 10px; font-weight: 700; color: #6366f1; text-transform: uppercase; letter-spacing: 0.05em;">
              Funzione Civica e Sociale
            </div>
            <div style="font-size: 11px; color: #334155; margin-top: 4px; line-height: 1.4;">
              ${props.social_function}
            </div>
          </div>
        ` : ''}
      </div>
    </div>
  `;
}

export function formatSubType(subType) {
  if (!subType) return '';
  if (SUB_TYPE_LABELS[subType]) return SUB_TYPE_LABELS[subType];
  return subType.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

// Rich badge shown in the POI detail popup — a purpose-built palette/copy for
// that single surface, distinct from CATEGORY_STYLES (used for map icon colors,
// the layer-switcher chips, and the legend) which stays unchanged elsewhere.
export const POPUP_CATEGORY_BADGES = {
  cross_civic: { label: 'Luoghi Pubblici', color: '#10b981' }, // verde
  residenti: { label: 'Servizi per Residenti', color: '#3b82f6' }, // blu
  pendolari: { label: 'Flussi Pendolari & Uni', color: '#f97316' }, // arancione
  occasionali: { label: 'Outdoor, Memoria & Sport', color: '#8b5cf6' } // viola
};
