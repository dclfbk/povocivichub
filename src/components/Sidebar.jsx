import React, { useMemo, useState } from 'react';
import CategoryStackedBar from './CategoryStackedBar';
import InfoButton from './InfoButton';
import {
  MapPin,
  Layers,
  BookOpen,
  Sparkles,
  RotateCcw,
  Hexagon,
  MapPinned,
  EyeOff,
  Flame,
  PenTool,
  XCircle,
  Map as MapIcon,
  PanelLeftClose,
  Crosshair,
  Menu,
  ArrowLeft,
  Search,
  ChevronDown,
  ChevronRight,
  Table
} from 'lucide-react';
import {
  CATEGORY_STYLES,
  ALL_POI_CATEGORIES,
  GRUPPI_SERVIZIO,
  ALL_GRUPPI,
  GRID_METRICS,
  gridMetricGradientCss,
  MIXED_AREA_COLOR,
  buildHexSegments,
  MAP_STYLES,
  HEATMAP_RADIUS_RANGE,
  SEMANTIC_LEVELS_5,
  getSemanticLevel5
} from '../config/mapConfig';

// Default (empty) hex-score aggregate, used whenever no hexagon centroid
// falls inside the drawn area / current map extent -- renders as "no data"
// in the stacked bar rather than crashing on undefined fields.
const EMPTY_HEX_AGG = { res_score: 0, comm_score: 0, occa_score: 0, mix_index: 0 };

const POI_VIEW_MODES = [
  { key: 'none', label: 'Nessun PoI', icon: EyeOff },
  { key: 'icons', label: 'Icone e Cluster', icon: MapPinned },
  { key: 'heatmap', label: 'Mappa di Calore (Heatmap)', icon: Flame }
];

export default function Sidebar({
  selectedHex,
  onResetSelection,
  onCloseSidebar,
  showGrid,
  onToggleGrid,
  poiViewMode,
  onChangePoiViewMode,
  gridMetric,
  onChangeGridMetric,
  activePoiCategories,
  onTogglePoiCategory,
  activeGruppi,
  gruppiCounts,
  onToggleGruppo,
  onSetAllGruppi,
  onFocusGruppo,
  heatmapRadius,
  onChangeHeatmapRadius,
  hexValueRange,
  onChangeHexValueRange,
  onOpenAbout,
  onOpenTables,
  onOpenCookieInfo,
  drawMode,
  onStartDraw,
  onCancelDraw,
  drawnAreaStats,
  onClearDrawnArea,
  mapStyle,
  onChangeMapStyle,
  mapExtentHexStats,
  poisData,
  onSelectPoi,
  textScale,
  onChangeTextScale
}) {
  // Two views (2026-10-09 feedback: "spostare l'Elenco punti di interesse nel
  // menù principale e Livelli & filtri nell'icona menù hamburger"): 'esplora'
  // is the citizen-facing default (search + categories + their places),
  // 'analisi' holds every map-analysis tool behind the header's hamburger.
  const [view, setView] = useState('esplora');
  const [query, setQuery] = useState('');
  const [expandedGruppi, setExpandedGruppi] = useState([]);

  const poisByGruppo = useMemo(() => {
    const groups = {};
    ((poisData && poisData.features) || []).forEach((f) => {
      if (!f.geometry || f.geometry.type !== 'Point') return;
      const p = f.properties || {};
      const key = p.gruppo_servizio || 'altro';
      (groups[key] = groups[key] || []).push({ ...p, lng: f.geometry.coordinates[0], lat: f.geometry.coordinates[1] });
    });
    // The circoscrizione's own entries first, in their table order; then the rest alphabetically.
    Object.values(groups).forEach((list) => list.sort((a, b) => {
      const an = a.mappatura_n ?? Infinity;
      const bn = b.mappatura_n ?? Infinity;
      return an !== bn ? an - bn : (a.name || '').localeCompare(b.name || '', 'it');
    }));
    return groups;
  }, [poisData]);

  const searchResults = useMemo(() => {
    const q = normalizeText(query.trim());
    if (q.length < 2) return null;
    return Object.values(poisByGruppo).flat()
      .filter((p) => normalizeText(`${p.name || ''} ${p.amenity_type || ''} ${p.indirizzo || ''}`).includes(q))
      .slice(0, 50);
  }, [query, poisByGruppo]);

  const toggleExpanded = (key) => {
    setExpandedGruppi((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));
  };

  // The Polifunzionalità card reflects whichever context is active, in this
  // priority order (2026-07-26 feedback: "calcolato o sulla base dell'extent
  // della mappa (se non faccio nulla), o selezionando un esagono ... oppure
  // disegnando l'area"). All three read the SAME kind of value -- the
  // pipeline's own precomputed per-hexagon mix_index/res_score/comm_score/
  // occa_score -- either directly (one selected hexagon) or averaged across
  // every hexagon whose centroid falls in the drawn area / current viewport
  // (Map.jsx / App.jsx). An earlier version derived the drawn-area/map-extent
  // reading independently from raw PoI counts (Shannon entropy), which
  // nearly always saturated near 100% for any real area -- see
  // GRID_METRICS.mix_index.info and project memory
  // [[feature_solo_riferimento_osmid_percent_mixindex]] for why that was wrong.
  let contextLabel, mixIndex, segments;
  if (selectedHex) {
    contextLabel = 'Esagono Selezionato';
    mixIndex = parseFloat(selectedHex.mix_index || 0);
    segments = buildHexSegments(selectedHex);
  } else if (drawnAreaStats) {
    contextLabel = 'Area Disegnata';
    const agg = drawnAreaStats.hexAgg || EMPTY_HEX_AGG;
    mixIndex = agg.mix_index;
    segments = buildHexSegments(agg);
  } else {
    contextLabel = 'Vista Mappa Corrente';
    const agg = mapExtentHexStats || EMPTY_HEX_AGG;
    mixIndex = agg.mix_index;
    segments = buildHexSegments(agg);
  }

  // Determine Polifunzionalità Index badge color & label (plain Italian,
  // no "Mixité"/"Mixing" jargon -- 2026-07-25 feedback).
  const getMixLevel = (score) => {
    if (score > 0.75) return { label: 'Alta Polifunzionalità', color: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' };
    if (score > 0.45) return { label: 'Media Polifunzionalità', color: 'bg-amber-500/20 text-amber-300 border-amber-500/30' };
    return { label: 'Bassa Polifunzionalità (Monofunzionale)', color: 'bg-blue-500/20 text-blue-300 border-blue-500/30' };
  };

  const mixLevel = getMixLevel(mixIndex);

  return (
    <aside className="w-full md:w-[22rem] h-full glass-panel flex flex-col z-20 overflow-y-auto border-r border-slate-800 text-slate-100 shadow-2xl">
      {/* App Header */}
      <header className="p-5 border-b border-slate-800/80 bg-slate-900/60 flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            {/* TEMPORARY logo (2026-10-14): the Circoscrizione di Povo's coat of
                arms as published on their Facebook page, pending official files
                and permission from the circoscrizione. The Trento city brand
                is reserved to registered Visit Trento partners (login), so it
                can't be added until they supply it. */}
            <img
              src="./loghi/stemma_povo.jpg"
              alt="Stemma della Circoscrizione di Povo"
              className="w-11 h-11 rounded-xl bg-white object-contain p-0.5 shadow-lg shrink-0"
            />
            <div>
              <h1 className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-indigo-100 to-indigo-300">
                Povo Civic Hub
              </h1>
              <p className="text-xs text-indigo-300/80 font-medium">Mappe di Co-presenza & Polifunzionalità</p>
            </div>
          </div>
          <div className="flex items-center gap-0.5">
            <button
              onClick={() => setView(view === 'analisi' ? 'esplora' : 'analisi')}
              className={`p-2.5 rounded-lg transition ${view === 'analisi' ? 'bg-indigo-500/30 text-white' : 'text-slate-300 hover:bg-slate-800 hover:text-white'}`}
              title="Livelli e filtri"
              aria-label="Livelli e filtri"
              aria-pressed={view === 'analisi'}
            >
              <Menu className="w-5 h-5" />
            </button>
            <button
              onClick={onOpenAbout}
              className="p-2.5 hover:bg-slate-800 rounded-lg text-slate-300 hover:text-white transition"
              title="A cosa serve questa mappa?"
              aria-label="A cosa serve questa mappa?"
            >
              <BookOpen className="w-5 h-5" />
            </button>
            <button
              onClick={onCloseSidebar}
              className="p-2.5 hover:bg-slate-800 rounded-lg text-slate-300 hover:text-white transition"
              title="Nascondi il pannello"
              aria-label="Nascondi il pannello"
            >
              <PanelLeftClose className="w-5 h-5" />
            </button>
          </div>
        </div>
        {/* Text size (2026-10-09 feedback: accessibilità e alta leggibilità).
            Scales the root font size, so every rem-based size follows. */}
        <div className="flex items-center gap-2 text-sm text-slate-300" role="group" aria-label="Dimensione del testo">
          <span>Testo</span>
          {TEXT_SCALES.map((scale, i) => (
            <button
              key={scale.label}
              onClick={() => onChangeTextScale(i)}
              aria-pressed={textScale === i}
              aria-label={scale.aria}
              title={scale.aria}
              className={`min-w-[2.25rem] px-2 py-1 rounded-md border font-semibold transition ${textScale === i ? 'bg-indigo-500/30 border-indigo-400 text-white' : 'border-slate-700 text-slate-300 hover:bg-slate-800'}`}
              style={{ fontSize: scale.preview }}
            >
              A
            </button>
          ))}
        </div>
      </header>

      {/* Main Content Area */}
      <div className="p-5 space-y-5 flex-1">
        {view === 'esplora' && (
        <>
        <div className="relative">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Cerca un luogo o un servizio…"
            aria-label="Cerca un luogo o un servizio"
            className="w-full text-base bg-slate-900/70 border border-slate-600 rounded-xl pl-9 pr-3 py-2.5 text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />
        </div>

        {searchResults && (
          <section aria-label="Risultati della ricerca" className="space-y-1">
            <div className="text-sm text-slate-300">
              {searchResults.length === 0 ? 'Nessun risultato' : searchResults.length === 1 ? '1 risultato' : `${searchResults.length}${searchResults.length === 50 ? '+' : ''} risultati`}
            </div>
            <ul className="space-y-0.5">
              {searchResults.map((poi) => (
                <PoiListItem key={poi.id} poi={poi} onSelect={onSelectPoi} showGruppo />
              ))}
            </ul>
          </section>
        )}

        {/* Categorie di servizio -- the circoscrizione's own grouping
            (2026-10-09 feedback). Checkbox toggles a group on the map, the
            crosshair shows only that group and frames it, the chevron lists
            its places (the former "Elenco punti di interesse", now here). */}
        {!searchResults && (
        <section className="glass-card rounded-2xl p-4 border border-slate-700/60 space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-xs font-bold text-indigo-400 uppercase tracking-widest flex items-center gap-1.5">
              <MapPin className="w-3.5 h-3.5" /> Categorie
            </div>
            <div className="flex gap-2 text-xs">
              <button onClick={() => onSetAllGruppi(true)} className="text-slate-300 hover:text-white underline">Tutte</button>
              <button onClick={() => onSetAllGruppi(false)} className="text-slate-300 hover:text-white underline">Nessuna</button>
            </div>
          </div>
          <ul className="space-y-1">
            {ALL_GRUPPI.map((key) => {
              const { label, color, icon: Icon } = GRUPPI_SERVIZIO[key];
              const count = gruppiCounts[key] || 0;
              const active = activeGruppi.includes(key);
              const expanded = expandedGruppi.includes(key);
              return (
                <li key={key}>
                <div className="flex items-center gap-0.5">
                  <button
                    onClick={() => toggleExpanded(key)}
                    disabled={count === 0}
                    aria-expanded={expanded}
                    aria-label={`${expanded ? 'Nascondi' : 'Mostra'} l'elenco: ${label}`}
                    title={`${expanded ? 'Nascondi' : 'Mostra'} l'elenco`}
                    className="p-1.5 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800 disabled:opacity-30"
                  >
                    {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  </button>
                  <label className="flex-1 min-w-0 flex items-center gap-2 text-sm px-1.5 py-2 rounded-lg hover:bg-slate-800/60 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      className="w-4 h-4 rounded cursor-pointer shrink-0"
                      style={{ accentColor: color }}
                      checked={active}
                      onChange={(e) => onToggleGruppo(key, e.target.checked)}
                    />
                    <Icon className="w-4 h-4 shrink-0" style={{ color }} />
                    <span className="text-slate-200 leading-snug">{label}</span>
                    <span className="ml-auto text-sm text-slate-300 tabular-nums">{count}</span>
                  </label>
                  <button
                    onClick={() => onFocusGruppo(key)}
                    disabled={count === 0}
                    className="p-2 rounded-lg text-slate-300 hover:text-white hover:bg-slate-800 disabled:opacity-30 disabled:hover:bg-transparent"
                    title={`Mostra solo: ${label}`}
                    aria-label={`Mostra solo ${label} sulla mappa`}
                  >
                    <Crosshair className="w-5 h-5" />
                  </button>
                </div>
                {expanded && (
                  <ul className="ml-7 mt-1 mb-2 pl-2 space-y-0.5 border-l-2" style={{ borderColor: `${color}66` }}>
                    {(poisByGruppo[key] || []).map((poi) => (
                      <PoiListItem key={poi.id} poi={poi} onSelect={onSelectPoi} />
                    ))}
                  </ul>
                )}
                </li>
              );
            })}
          </ul>
        </section>
        )}

        <button
          onClick={onOpenTables}
          className="w-full flex items-center justify-center gap-2 text-sm font-semibold px-3 py-2.5 rounded-xl bg-slate-800/80 text-slate-200 border border-slate-600 hover:bg-slate-700 transition"
        >
          <Table className="w-4 h-4" /> Tabella completa e download CSV
        </button>

        <button
          onClick={() => setView('analisi')}
          className="w-full flex items-center justify-center gap-2 text-sm font-semibold px-3 py-2.5 rounded-xl bg-indigo-500/20 text-indigo-200 border border-indigo-500/40 hover:bg-indigo-500/30 transition"
        >
          <Layers className="w-4 h-4" /> Livelli, mappe di calore e analisi
        </button>
        </>
        )}

        {view === 'analisi' && (
        <>
        <button
          onClick={() => setView('esplora')}
          className="flex items-center gap-2 text-sm font-semibold text-slate-200 hover:text-white px-1 py-1"
        >
          <ArrowLeft className="w-4 h-4" /> Torna alle categorie
        </button>

        {selectedHex && (
          <button
            onClick={onResetSelection}
            className="w-full flex items-center justify-center gap-2 text-sm font-semibold px-3 py-2 rounded-xl bg-slate-800 text-slate-200 border border-slate-600 hover:bg-slate-700 transition"
          >
            <RotateCcw className="w-4 h-4" /> Deseleziona l&apos;esagono
          </button>
        )}

        {/* Background Map Style */}
        <section className="glass-card rounded-2xl p-5 border border-slate-700/60 space-y-2">
          <div className="text-xs font-bold text-indigo-400 uppercase tracking-widest flex items-center gap-1.5">
            <MapIcon className="w-3.5 h-3.5" /> Mappa di Sfondo
          </div>
          <select
            value={mapStyle}
            onChange={(e) => onChangeMapStyle(e.target.value)}
            className="w-full text-sm bg-slate-900/60 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {Object.entries(MAP_STYLES).map(([key, cfg]) => (
              <option key={key} value={key}>{cfg.label}</option>
            ))}
          </select>
        </section>

        {/* Layer Switcher / Control Panel */}
        <section className="glass-card rounded-2xl p-5 border border-slate-700/60 space-y-4">
          <div className="text-xs font-bold text-indigo-400 uppercase tracking-widest flex items-center gap-1.5">
            <Layers className="w-3.5 h-3.5" /> Livelli & Filtri
          </div>

          {/* Modalità Visualizzazione PoI */}
          <div className="space-y-2.5">
            <div className="text-sm font-semibold text-slate-200">Modalità Visualizzazione PoI</div>

            <div className="space-y-1.5">
              {POI_VIEW_MODES.map(({ key, label, icon: ModeIcon }) => (
                <label
                  key={key}
                  className="flex items-center gap-2 text-xs px-2.5 py-1.5 rounded-lg border border-slate-800 bg-slate-900/60 cursor-pointer select-none"
                >
                  <input
                    type="radio"
                    name="poiViewMode"
                    className="w-4 h-4 accent-indigo-500 cursor-pointer"
                    checked={poiViewMode === key}
                    onChange={() => onChangePoiViewMode(key)}
                  />
                  <ModeIcon className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  <span className="text-slate-300">{label}</span>
                </label>
              ))}
            </div>

            {poiViewMode === 'heatmap' && (
              <div className="space-y-1.5 pl-1">
                <div className="flex items-center justify-between text-sm text-slate-400">
                  <span>Raggio Mappa di Calore</span>
                  <span className="font-mono text-slate-300">{heatmapRadius}px</span>
                </div>
                <input
                  type="range"
                  min={HEATMAP_RADIUS_RANGE.min}
                  max={HEATMAP_RADIUS_RANGE.max}
                  step={1}
                  value={heatmapRadius}
                  onChange={(e) => onChangeHeatmapRadius(Number(e.target.value))}
                  className="w-full accent-indigo-500 cursor-pointer"
                />
              </div>
            )}

            {poiViewMode === 'icons' && (
              <div className="grid grid-cols-1 gap-1.5 pl-1">
                {ALL_POI_CATEGORIES.map((cat) => {
                  const style = CATEGORY_STYLES[cat];
                  const Icon = style.icon;
                  const active = activePoiCategories.includes(cat);
                  return (
                    <label
                      key={cat}
                      className="flex items-center gap-1.5 text-sm px-2 py-1.5 rounded-lg border border-slate-800 bg-slate-900/60 cursor-pointer select-none"
                    >
                      <input
                        type="checkbox"
                        className="w-4 h-4 rounded cursor-pointer"
                        style={{ accentColor: style.color }}
                        checked={active}
                        onChange={(e) => onTogglePoiCategory(cat, e.target.checked)}
                      />
                      <Icon className="w-3 h-3 shrink-0" style={{ color: style.color }} />
                      <span className="text-slate-300">{style.label}</span>
                    </label>
                  );
                })}
              </div>
            )}
          </div>

          {/* Toggle: Hex grid + metric */}
          <div className="space-y-2.5 border-t border-slate-800 pt-3">
            <label className="flex items-center justify-between cursor-pointer select-none">
              <span className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                <Hexagon className="w-4 h-4 text-slate-400" /> Mostra Griglia Esagonale
              </span>
              <input
                type="checkbox"
                className="w-4 h-4 accent-indigo-500 rounded cursor-pointer"
                checked={showGrid}
                onChange={(e) => onToggleGrid(e.target.checked)}
              />
            </label>

            {showGrid && (
              <div className="space-y-1.5 pl-1">
                {Object.entries(GRID_METRICS).map(([key, cfg]) => (
                  <div
                    key={key}
                    className="flex items-center gap-2 text-sm px-2 py-1.5 rounded-lg border border-slate-800 bg-slate-900/60"
                  >
                    <label className="flex items-center gap-2 flex-1 min-w-0 cursor-pointer select-none">
                      <input
                        type="radio"
                        name="gridMetric"
                        className="w-3 h-3 accent-indigo-500 cursor-pointer shrink-0"
                        checked={gridMetric === key}
                        onChange={() => onChangeGridMetric(key)}
                      />
                      <span className="text-slate-300 truncate">{cfg.label}</span>
                    </label>
                    <InfoButton title={cfg.label}>{cfg.info}</InfoButton>
                  </div>
                ))}

                {/* Legend for the currently-selected hex metric -- kept right
                    next to the metric picker (2026-07-25 feedback: it used to
                    sit at the very bottom of the sidebar, past several other
                    sections, so it went effectively unnoticed). */}
                <div className="glass-card rounded-xl p-3 space-y-2 border border-slate-800 mt-2">
                  <div className="text-sm font-semibold text-slate-300 flex items-center justify-between gap-2">
                    <span className="truncate">Legenda &bull; {GRID_METRICS[gridMetric].label}</span>
                    <InfoButton title={GRID_METRICS[gridMetric].label}>{GRID_METRICS[gridMetric].info}</InfoButton>
                  </div>
                  {gridMetric === 'dominant' ? (
                    <div className="grid grid-cols-2 gap-1.5 pt-1">
                      {ALL_POI_CATEGORIES.map((cat) => (
                        <div key={cat} className="flex items-center gap-1.5 text-xs text-slate-300">
                          <span className="w-3 h-3 rounded shrink-0" style={{ backgroundColor: CATEGORY_STYLES[cat].color }} />
                          <span className="truncate">{CATEGORY_STYLES[cat].label}</span>
                        </div>
                      ))}
                      <div className="flex items-center gap-1.5 text-xs text-slate-300 col-span-2">
                        <span className="w-3 h-3 rounded shrink-0" style={{ backgroundColor: MIXED_AREA_COLOR }} />
                        <span>Area Mista (2+ categorie in equilibrio)</span>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="h-3 w-full rounded-full" style={{ background: gridMetricGradientCss(gridMetric) }} />
                      <div className="flex justify-between text-xs text-slate-400 font-mono">
                        <span>0.0 Basso</span>
                        <span>0.5 Medio</span>
                        <span>1.0 Alto</span>
                      </div>

                      {/* Range slider filtering the hex grid down to the
                          selected value band on this metric (2026-07-26
                          feedback). Two overlapping native <input type=range>
                          thumbs sharing one track -- see .dual-range in
                          index.css for the pointer-events trick that lets
                          each thumb be dragged independently. */}
                      <div className="pt-2 space-y-1.5 border-t border-slate-800 mt-1">
                        <div className="flex items-center justify-between text-xs text-slate-400">
                          <span>Filtra esagoni per range di valore</span>
                          {(hexValueRange[0] > 0 || hexValueRange[1] < 1) && (
                            <button
                              type="button"
                              onClick={() => onChangeHexValueRange([0, 1])}
                              className="text-indigo-400 hover:text-indigo-300 transition font-semibold"
                            >
                              Reimposta
                            </button>
                          )}
                        </div>
                        <div className="relative h-4">
                          <div className="absolute top-1/2 -translate-y-1/2 h-1 w-full rounded-full bg-slate-700" />
                          <div
                            className="absolute top-1/2 -translate-y-1/2 h-1 rounded-full bg-indigo-500"
                            style={{ left: `${hexValueRange[0] * 100}%`, right: `${100 - hexValueRange[1] * 100}%` }}
                          />
                          <input
                            type="range"
                            min={0}
                            max={1}
                            step={0.01}
                            value={hexValueRange[0]}
                            onChange={(e) => onChangeHexValueRange([Math.min(Number(e.target.value), hexValueRange[1]), hexValueRange[1]])}
                            className="dual-range absolute inset-0 w-full h-4"
                            aria-label="Valore minimo"
                          />
                          <input
                            type="range"
                            min={0}
                            max={1}
                            step={0.01}
                            value={hexValueRange[1]}
                            onChange={(e) => onChangeHexValueRange([hexValueRange[0], Math.max(Number(e.target.value), hexValueRange[0])])}
                            className="dual-range absolute inset-0 w-full h-4"
                            aria-label="Valore massimo"
                          />
                        </div>
                        <div className="flex justify-between text-xs text-slate-400 font-mono">
                          <span>{hexValueRange[0].toFixed(2)}</span>
                          <span>{hexValueRange[1].toFixed(2)}</span>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Polifunzionalità Info Card -- context-aware: selected hexagon,
            drawn area, or (default) current map extent. */}
        <section className="glass-card rounded-2xl p-5 border border-slate-700/60 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-indigo-400 uppercase tracking-widest flex items-center gap-1.5">
              <MapPin className="w-3.5 h-3.5" /> {contextLabel}
            </span>
            {selectedHex && (
              <span className="text-xs font-mono bg-slate-800 px-2 py-0.5 rounded border border-slate-700 text-slate-300">
                {selectedHex.h3_id}
              </span>
            )}
          </div>

          {/* Polifunzionalità Index Metric */}
          <div className="flex items-baseline justify-between border-t border-slate-800 pt-3">
            <div>
              <div className="text-xs text-slate-400 flex items-center gap-1.5">
                <span>{GRID_METRICS.mix_index.label}</span>
                <InfoButton title={GRID_METRICS.mix_index.label}>{GRID_METRICS.mix_index.info}</InfoButton>
              </div>
              <div className="text-3xl font-extrabold tracking-tight text-white mt-0.5">
                {mixIndex.toFixed(4)}
              </div>
            </div>
            <span className={`text-xs px-3 py-1 rounded-full font-semibold border ${mixLevel.color}`}>
              {mixLevel.label}
            </span>
          </div>

          {/* Five-level semantic indicator, auto-computed from the 0-1 score
              (2026-07-26 feedback: "zero è schifo, uno è il massimo, fai
              cinque indicatori semantici") -- placed right below the number
              itself, distinct from the badge above (which reads the raw
              mix_index against the "mixed-use" threshold specifically). */}
          {(() => {
            const semLevel = getSemanticLevel5(mixIndex);
            return (
              <div className="pt-1">
                <div className="flex items-center gap-1">
                  {SEMANTIC_LEVELS_5.map((lvl, i) => (
                    <div
                      key={lvl.label}
                      className="h-1.5 flex-1 rounded-full transition-opacity"
                      style={{ backgroundColor: lvl.color, opacity: i === semLevel.index ? 1 : 0.25 }}
                    />
                  ))}
                </div>
                <div className="flex items-center gap-1.5 mt-1.5 text-xs font-semibold" style={{ color: semLevel.color }}>
                  <span>{semLevel.emoji}</span>
                  <span>{semLevel.label}</span>
                </div>
              </div>
            );
          })()}

          {/* Category Profile Stacked Bar */}
          <div className="pt-2 space-y-2">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
              <Sparkles className="w-4 h-4 text-indigo-400" /> Profilo Funzionale
            </div>
            <CategoryStackedBar
              title={contextLabel}
              segments={segments}
              valueLabel="Valore assoluto: punteggio normalizzato (0-1) di prossimità/densità PoI"
              note="I Luoghi Pubblici non hanno un asse proprio: alimentano Residenti/Pendolari/Occasionali nel calcolo della Polifunzionalità (sono gli oggetti che uniscono le categorie)."
            />
          </div>
        </section>

        {/* Draw-an-area tool */}
        <section className="glass-card rounded-2xl p-5 border border-slate-700/60 space-y-3">
          <div className="text-xs font-bold text-indigo-400 uppercase tracking-widest flex items-center gap-1.5">
            <PenTool className="w-3.5 h-3.5" /> Disegna un&apos;Area
          </div>

          {!drawMode ? (
            <button
              onClick={onStartDraw}
              className="w-full flex items-center justify-center gap-2 text-xs font-semibold px-3 py-2 rounded-lg bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 hover:bg-indigo-500/30 transition"
            >
              <PenTool className="w-3.5 h-3.5" /> Disegna Area sulla Mappa
            </button>
          ) : (
            <div className="space-y-2">
              <div className="text-sm text-slate-400 leading-relaxed">
                Clicca sulla mappa per aggiungere punti, doppio click per chiudere il poligono.
              </div>
              <button
                onClick={onCancelDraw}
                className="w-full flex items-center justify-center gap-2 text-xs font-semibold px-3 py-2 rounded-lg bg-slate-800 text-slate-300 border border-slate-700 hover:bg-slate-700 transition"
              >
                <XCircle className="w-3.5 h-3.5" /> Annulla Disegno
              </button>
            </div>
          )}

          {drawnAreaStats && (
            <div className="space-y-2 pt-1">
              {/* The Polifunzionalità % and category profile for this area are
                  shown in the card above (context-aware) -- this section keeps
                  just the raw count/ICC detail specific to the drawn shape. */}
              <div className="grid grid-cols-2 gap-2 text-center text-xs">
                <div className="bg-slate-900/60 p-2 rounded-lg border border-slate-800">
                  <div className="text-slate-400">PoI nell&apos;area</div>
                  <div className="font-bold text-white mt-0.5">{drawnAreaStats.total}</div>
                </div>
                <div className="bg-slate-900/60 p-2 rounded-lg border border-slate-800">
                  <div className="text-slate-400">ICC Medio</div>
                  <div className="font-bold text-white mt-0.5">
                    {drawnAreaStats.avgIcc !== null ? drawnAreaStats.avgIcc.toFixed(1) : '—'}
                  </div>
                </div>
              </div>

              <button
                onClick={onClearDrawnArea}
                className="w-full flex items-center justify-center gap-2 text-xs font-semibold px-3 py-2 rounded-lg bg-slate-800 text-slate-300 border border-slate-700 hover:bg-slate-700 transition"
              >
                <XCircle className="w-3.5 h-3.5" /> Cancella Area
              </button>
            </div>
          )}
        </section>
        </>
        )}
      </div>

      {/* Footer */}
      <footer className="p-4 border-t border-slate-800/80 bg-slate-950/80 text-sm text-slate-400 text-center">
        <div className="flex items-center justify-center gap-2 mb-2 text-slate-300">
          <img src="./loghi/stemma_povo.jpg" alt="" className="w-7 h-7 rounded bg-white object-contain" />
          In collaborazione con la Circoscrizione di Povo
        </div>
        Povo Civic Hub 2026 &bull; napo@fbk &bull;{' '}
        <a
          href="https://github.com/dclfbk/povocivichub"
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-slate-200 underline transition"
        >
          github.com/dclfbk/povocivichub
        </a>
        {' '}&bull;{' '}
        <button
          onClick={onOpenCookieInfo}
          className="hover:text-slate-200 underline transition"
        >
          Cookie
        </button>
        <div className="mt-1.5">
          Contenuti sotto licenza{' '}
          <a
            href="https://creativecommons.org/licenses/by/4.0/deed.it"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-slate-200 underline transition"
            title="Creative Commons Attribuzione 4.0 Internazionale"
          >
            CC BY 4.0
          </a>
        </div>
      </footer>
    </aside>
  );
}

export const TEXT_SCALES = [
  { label: 'normale', aria: 'Testo normale', preview: '0.8rem', rootSize: '100%' },
  { label: 'grande', aria: 'Testo grande', preview: '0.95rem', rootSize: '112.5%' },
  { label: 'molto grande', aria: 'Testo molto grande', preview: '1.1rem', rootSize: '125%' }
];

// Accent/case-insensitive matching for the search box ("salè" finds "Sale").
function normalizeText(text) {
  return text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}

function PoiListItem({ poi, onSelect, showGruppo = false }) {
  const gruppo = GRUPPI_SERVIZIO[poi.gruppo_servizio || 'altro'];
  return (
    <li>
      <button
        onClick={() => onSelect(poi)}
        className="w-full text-left px-2 py-1.5 rounded-lg hover:bg-slate-800/70 focus-visible:bg-slate-800/70 transition"
        title="Mostra sulla mappa"
      >
        <span className="block text-sm text-slate-100 leading-snug">{poi.name || 'Punto di interesse'}</span>
        <span className="block text-xs text-slate-400 leading-snug">
          {showGruppo && <span style={{ color: gruppo.color }}>{gruppo.label} · </span>}
          {poi.amenity_type}
        </span>
      </button>
    </li>
  );
}
