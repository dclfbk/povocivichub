import { Home, Bus, Trees, BookOpen } from 'lucide-react';

// Shared styling for POI categories, used by both the map (colors) and the
// sidebar layer switcher (legend icons/labels).
export const CATEGORY_STYLES = {
  residenti: { label: 'Residenti', color: '#60a5fa', icon: Home },
  pendolari: { label: 'Pendolari', color: '#fbbf24', icon: Bus },
  occasionali: { label: 'Occasionali', color: '#f472b6', icon: Trees },
  cross_civic: { label: 'Verde Urbano & Servizi Civici', color: '#34d399', icon: BookOpen }
};

export const ALL_POI_CATEGORIES = Object.keys(CATEGORY_STYLES);

// Color ramps per grid metric, shared between the MapLibre fill-color
// expression and the sidebar legend gradient.
export const GRID_METRICS = {
  mix_index: {
    label: 'Indice di Mixité (Entropia)',
    stops: [[0.0, '#312e81'], [0.2, '#3b82f6'], [0.45, '#10b981'], [0.75, '#f59e0b'], [1.0, '#ec4899']]
  },
  res_score: {
    label: 'Punteggio Residenti (R)',
    stops: [[0.0, '#0f172a'], [0.5, '#3b82f6'], [1.0, '#93c5fd']]
  },
  comm_score: {
    label: 'Punteggio Pendolari (P)',
    stops: [[0.0, '#1c1917'], [0.5, '#f59e0b'], [1.0, '#fde68a']]
  },
  occa_score: {
    label: 'Punteggio Occasionali (O)',
    stops: [[0.0, '#1e1b2e'], [0.5, '#ec4899'], [1.0, '#fbcfe8']]
  }
};

export function buildFillColorExpression(metric) {
  const cfg = GRID_METRICS[metric] || GRID_METRICS.mix_index;
  const expr = ['interpolate', ['linear'], ['coalesce', ['get', metric], 0]];
  cfg.stops.forEach(([stop, color]) => expr.push(stop, color));
  return expr;
}

export function gridMetricGradientCss(metric) {
  const cfg = GRID_METRICS[metric] || GRID_METRICS.mix_index;
  const colors = cfg.stops.map(([, color]) => color).join(', ');
  return `linear-gradient(to right, ${colors})`;
}

// Visual glyph + badge color per `icon_name`, as assigned by the Python pipeline's
// ICON_MAP (build_data.py). Colors echo the dominant CATEGORY_STYLES color so the
// unclustered POI icons stay legible against the category legend.
export const ICON_VISUALS = {
  castle: { emoji: '🏰', color: CATEGORY_STYLES.occasionali.color },
  monument: { emoji: '🗿', color: CATEGORY_STYLES.occasionali.color },
  ruins: { emoji: '🏚️', color: CATEGORY_STYLES.occasionali.color },
  theater: { emoji: '🎭', color: CATEGORY_STYLES.occasionali.color },
  museum: { emoji: '🏛️', color: CATEGORY_STYLES.occasionali.color },
  attraction: { emoji: '🎡', color: CATEGORY_STYLES.occasionali.color },
  viewpoint: { emoji: '🌄', color: CATEGORY_STYLES.occasionali.color },
  restaurant: { emoji: '🍽️', color: CATEGORY_STYLES.occasionali.color },
  cafe: { emoji: '☕', color: CATEGORY_STYLES.occasionali.color },
  hotel: { emoji: '🏨', color: CATEGORY_STYLES.occasionali.color },
  library: { emoji: '📚', color: CATEGORY_STYLES.pendolari.color },
  college: { emoji: '🎓', color: CATEGORY_STYLES.pendolari.color },
  bus: { emoji: '🚌', color: CATEGORY_STYLES.pendolari.color },
  park: { emoji: '🌳', color: CATEGORY_STYLES.cross_civic.color },
  drinking_water: { emoji: '🚰', color: CATEGORY_STYLES.cross_civic.color },
  bench: { emoji: '🪑', color: CATEGORY_STYLES.cross_civic.color },
  information: { emoji: 'ℹ️', color: '#94a3b8' },
  marker: { emoji: '📍', color: '#94a3b8' }
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
  guest_house: 'Agriturismo',
  hotel: 'Hotel',
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
  historic: 'Stoi Militari'
};

export function formatSubType(subType) {
  if (!subType) return '';
  if (SUB_TYPE_LABELS[subType]) return SUB_TYPE_LABELS[subType];
  return subType.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

// Rich badge shown in the POI detail popup — a purpose-built palette/copy for
// that single surface, distinct from CATEGORY_STYLES (used for map icon colors,
// the layer-switcher chips, and the legend) which stays unchanged elsewhere.
export const POPUP_CATEGORY_BADGES = {
  cross_civic: { label: 'Verde Urbano & Servizi Civici', color: '#10b981' }, // verde
  residenti: { label: 'Servizi per Residenti', color: '#3b82f6' }, // blu
  pendolari: { label: 'Flussi Pendolari & Uni', color: '#f97316' }, // arancione
  occasionali: { label: 'Outdoor, Memoria & Sport', color: '#8b5cf6' } // viola
};
