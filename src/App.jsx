import React, { useState, useEffect, useMemo } from 'react';
import Map from './components/Map';
import Sidebar, { TEXT_SCALES } from './components/Sidebar';
import AboutModal from './components/AboutModal';
import CategoryTablesModal from './components/CategoryTablesModal';
import CookieConsent from './components/CookieConsent';
import { PanelLeftOpen } from 'lucide-react';
import { parseUrlState, buildUrlSearch } from './utils/urlState';
import { DEFAULT_HEATMAP_RADIUS, ALL_GRUPPI, aggregateHexScoresInBounds } from './config/mapConfig';

const INTRO_SEEN_KEY = 'povoCivicHub_introSeen';
const COOKIE_CONSENT_KEY = 'povoCivicHub_cookieConsent';
const TEXT_SCALE_KEY = 'povoCivicHub_textScale';

const isMobileViewport = () => window.matchMedia && !window.matchMedia('(min-width: 768px)').matches;

export default function App() {
  // Parsed once on first render -- everything visible on screen (camera,
  // layers, background, selected hexagon) is seeded from the URL so a
  // shared link reproduces the exact same view (2026-07-25 feedback).
  const [initialUrlState] = useState(() => parseUrlState());

  const [selectedHex, setSelectedHex] = useState(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  // Auto-opens the intro/methodology dialog on a visitor's first-ever visit
  // (2026-07-25 feedback: the project needs an initial explainer dialog).
  const [isAboutOpen, setIsAboutOpen] = useState(() => {
    try {
      return !localStorage.getItem(INTRO_SEEN_KEY);
    } catch {
      return true;
    }
  });
  const [isTablesOpen, setIsTablesOpen] = useState(false);
  // Informativa cookie/local storage -- same first-visit-only pattern as
  // isAboutOpen above, but reopenable any time via a dedicated footer button
  // rather than the header's book icon (2026-07-26 feedback).
  const [isCookieBannerOpen, setIsCookieBannerOpen] = useState(() => {
    try {
      return !localStorage.getItem(COOKIE_CONSENT_KEY);
    } catch {
      return true;
    }
  });
  const [flyToTarget, setFlyToTarget] = useState(null);

  // Text size (2026-10-09 feedback: alta leggibilità) -- index into
  // TEXT_SCALES, applied as the root font size so every rem-based size
  // scales with it; remembered per browser.
  const [textScale, setTextScale] = useState(() => {
    try {
      const saved = Number(localStorage.getItem(TEXT_SCALE_KEY));
      return TEXT_SCALES[saved] ? saved : 0;
    } catch {
      return 0;
    }
  });
  useEffect(() => {
    document.documentElement.style.fontSize = TEXT_SCALES[textScale].rootSize;
    try {
      localStorage.setItem(TEXT_SCALE_KEY, String(textScale));
    } catch {
      // localStorage unavailable -- the size just won't be remembered.
    }
  }, [textScale]);

  // Layers default to whatever the URL says, falling back to off/2D.
  const [showGrid, setShowGrid] = useState(initialUrlState.showGrid);
  const [poiViewMode, setPoiViewMode] = useState(initialUrlState.poiViewMode); // 'none' | 'icons' | 'heatmap'
  const [showTerrain, setShowTerrain] = useState(initialUrlState.showTerrain);
  const [gridMetric, setGridMetric] = useState(initialUrlState.gridMetric);
  const [activePoiCategories, setActivePoiCategories] = useState(initialUrlState.activePoiCategories);
  const [activeGruppi, setActiveGruppi] = useState(initialUrlState.activeGruppi);
  // { key, _t } -- bumped by "mostra solo" so the map re-frames that group
  // even when it's picked twice in a row.
  const [focusGruppo, setFocusGruppo] = useState(null);
  const [mapStyle, setMapStyle] = useState(initialUrlState.mapStyle);
  const [heatmapRadius, setHeatmapRadius] = useState(DEFAULT_HEATMAP_RADIUS);
  // Range filter over the current hex legend metric's [0,1] domain
  // (2026-07-26 feedback: dragging the legend should filter which hexagons
  // show). Reset to the full domain whenever the metric itself changes --
  // a range chosen for e.g. mix_index has no meaningful carry-over to res_score.
  const [hexValueRange, setHexValueRange] = useState([0, 1]);
  useEffect(() => {
    setHexValueRange([0, 1]);
  }, [gridMetric]);

  // Current camera -- initialized from the URL, kept in sync afterwards via
  // Map's onViewStateChange (fired on every 'moveend', which in MapLibre
  // covers pan/zoom/rotate/pitch alike).
  const [viewState, setViewState] = useState(() => ({
    lat: initialUrlState.lat,
    lon: initialUrlState.lon,
    zoom: initialUrlState.zoom,
    bearing: initialUrlState.bearing,
    pitch: initialUrlState.pitch
  }));

  // Loaded once for JS-side use (draw-tool point-in-polygon stats, the PoI
  // tables modal) -- separate from the copy MapLibre loads for rendering.
  const [poisData, setPoisData] = useState(null);
  // Loaded once so the "map extent" Polifunzionalità reading below can
  // aggregate the pipeline's own precomputed per-hexagon scores -- separate
  // from the copy MapLibre loads for rendering the grid layer.
  const [gridData, setGridData] = useState(null);

  // Draw-an-area tool state.
  const [drawMode, setDrawMode] = useState(false);
  const [drawnAreaStats, setDrawnAreaStats] = useState(null);
  const [clearDrawSignal, setClearDrawSignal] = useState(0);

  // Current map viewport (reported by Map on load + every moveend), used to
  // compute a live "map extent" Polifunzionalità reading when nothing else is
  // selected/drawn (2026-07-26 feedback: "l'indice ... sulla base dell'extent
  // della mappa ... se non faccio nulla"). This averages the mix_index/
  // res_score/comm_score/occa_score the pipeline already computed for every
  // hexagon whose centroid falls in view -- NOT an independently recomputed
  // formula (an earlier attempt using Shannon entropy over raw PoI counts in
  // view was scrapped: it saturates near 100% for almost any real area,
  // see [[feature_solo_riferimento_osmid_percent_mixindex]] project memory).
  const [viewportBounds, setViewportBounds] = useState(null);
  const mapExtentHexStats = useMemo(
    () => aggregateHexScoresInBounds(gridData, viewportBounds),
    [viewportBounds, gridData]
  );

  useEffect(() => {
    fetch('./data/povo_pois.json')
      .then((res) => res.json())
      .then(setPoisData)
      .catch((err) => console.error('Failed to load povo_pois.json', err));
    fetch('./data/povo_grid.json')
      .then((res) => res.json())
      .then(setGridData)
      .catch((err) => console.error('Failed to load povo_grid.json', err));
  }, []);

  // Keep the URL in sync with everything visible on screen, so copying the
  // address bar reproduces the same view. replaceState (not pushState) so
  // panning/toggling layers doesn't spam the browser's back-button history.
  useEffect(() => {
    const qs = buildUrlSearch({
      ...viewState,
      showTerrain,
      poiViewMode,
      showGrid,
      gridMetric,
      activePoiCategories,
      activeGruppi,
      mapStyle,
      selectedHexId: (selectedHex && selectedHex.h3_id) || null
    });
    window.history.replaceState(null, '', `${window.location.pathname}?${qs}`);
  }, [viewState, showTerrain, poiViewMode, showGrid, gridMetric, activePoiCategories, activeGruppi, mapStyle, selectedHex]);

  const gruppiCounts = useMemo(() => {
    const counts = {};
    ((poisData && poisData.features) || []).forEach((f) => {
      const key = f.properties.gruppo_servizio || 'altro';
      counts[key] = (counts[key] || 0) + 1;
    });
    return counts;
  }, [poisData]);

  // Picking a group only makes sense if pins are on screen -- the default
  // view mode is 'none' (2026-10-09 feedback: the group filter must show
  // where things are), so switch to icons whenever the selection changes.
  const handleToggleGruppo = (key, isActive) => {
    setActiveGruppi((prev) => (isActive ? [...prev, key] : prev.filter((g) => g !== key)));
    if (isActive) setPoiViewMode('icons');
  };

  const handleSetAllGruppi = (isActive) => {
    setActiveGruppi(isActive ? ALL_GRUPPI : []);
    if (isActive) setPoiViewMode('icons');
  };

  const handleFocusGruppo = (key) => {
    setActiveGruppi([key]);
    setPoiViewMode('icons');
    setFocusGruppo({ key, _t: Date.now() });
    // On phones the sidebar covers the whole map -- close it so the result is visible.
    if (isMobileViewport()) setIsSidebarOpen(false);
  };

  const handleTogglePoiCategory = (category, isActive) => {
    setActivePoiCategories((prev) =>
      isActive ? [...prev, category] : prev.filter((c) => c !== category)
    );
  };

  const handleStartDraw = () => {
    // Deselect any hexagon so the Polifunzionalità card's context switches
    // to the area being drawn instead of staying stuck on the old hex
    // selection (hex > drawn-area > map-extent priority, see Sidebar).
    setSelectedHex(null);
    setDrawnAreaStats(null);
    setDrawMode(true);
  };

  const handleCancelDraw = () => {
    setDrawMode(false);
    setClearDrawSignal((n) => n + 1);
  };

  const handleDrawComplete = (stats) => {
    setDrawMode(false);
    setDrawnAreaStats(stats);
  };

  const handleClearDrawnArea = () => {
    setDrawnAreaStats(null);
    setClearDrawSignal((n) => n + 1);
  };

  const handleAcceptCookies = () => {
    setIsCookieBannerOpen(false);
    try {
      localStorage.setItem(COOKIE_CONSENT_KEY, '1');
    } catch {
      // localStorage unavailable (e.g. private browsing) -- the banner will
      // just reopen next visit, same fallback as the intro dialog below.
    }
  };

  const handleCloseAbout = () => {
    setIsAboutOpen(false);
    try {
      localStorage.setItem(INTRO_SEEN_KEY, '1');
    } catch {
      // localStorage unavailable (e.g. private browsing) -- the dialog will
      // just auto-open again next visit, which is an acceptable fallback.
    }
  };

  // Row click in the PoI table: close the table, switch to icon view so the
  // point is actually visible, and fly the map to it (Map.jsx also opens its
  // popup once centered).
  // Also used by the sidebar's category lists / search results. On phones the
  // panel would hide the result, so it's closed there.
  const handleSelectPoiFromTable = (poi) => {
    setIsTablesOpen(false);
    setPoiViewMode('icons');
    setFlyToTarget({ ...poi, _t: Date.now() });
    if (isMobileViewport()) setIsSidebarOpen(false);
  };

  return (
    <div className="relative w-screen h-screen overflow-hidden flex flex-col md:flex-row bg-slate-950">
      {/* Sidebar Toggle Button -- only floats over the map once the sidebar
          is closed (2026-07-28 feedback: sidebar should be collapsible on
          every screen size, not just mobile). Closing itself happens via the
          dedicated button in Sidebar's own header instead, so this one never
          has to overlap the open panel. */}
      {!isSidebarOpen && (
        <button
          onClick={() => setIsSidebarOpen(true)}
          className="absolute z-30 bottom-6 left-1/2 -translate-x-1/2 md:bottom-auto md:translate-x-0 md:top-4 md:left-4 flex items-center gap-2 px-4 py-3 bg-slate-900/95 text-white text-base font-semibold rounded-xl border border-slate-600 shadow-xl backdrop-blur-md"
          aria-label="Apri il pannello con categorie ed elenco dei luoghi"
        >
          <PanelLeftOpen className="w-5 h-5" /> Categorie e luoghi
        </button>
      )}

      {/* Sidebar Panel -- on phones a bottom sheet over the lower part of
          the map (2026-10-09 feedback: ottimizzazione per dispositivi mobili;
          previously a full-screen overlay that hid the map entirely). Fixed,
          not a flex child, so it never squeezes the map to zero height
          (2026-07-29 bug). On md+ it's a normal flex item next to the map. */}
      <div className={`${isSidebarOpen ? 'flex' : 'hidden'} fixed md:static inset-x-0 bottom-0 h-[60vh] md:h-full w-full md:w-auto shrink-0 z-30 md:z-20 rounded-t-2xl md:rounded-none overflow-hidden shadow-[0_-8px_30px_rgba(0,0,0,0.5)] md:shadow-none`}>
        <Sidebar
          selectedHex={selectedHex}
          onResetSelection={() => setSelectedHex(null)}
          onCloseSidebar={() => setIsSidebarOpen(false)}
          showGrid={showGrid}
          onToggleGrid={setShowGrid}
          poiViewMode={poiViewMode}
          onChangePoiViewMode={setPoiViewMode}
          gridMetric={gridMetric}
          onChangeGridMetric={setGridMetric}
          activePoiCategories={activePoiCategories}
          onTogglePoiCategory={handleTogglePoiCategory}
          activeGruppi={activeGruppi}
          gruppiCounts={gruppiCounts}
          onToggleGruppo={handleToggleGruppo}
          onSetAllGruppi={handleSetAllGruppi}
          onFocusGruppo={handleFocusGruppo}
          heatmapRadius={heatmapRadius}
          onChangeHeatmapRadius={setHeatmapRadius}
          hexValueRange={hexValueRange}
          onChangeHexValueRange={setHexValueRange}
          onOpenAbout={() => setIsAboutOpen(true)}
          onOpenTables={() => setIsTablesOpen(true)}
          onOpenCookieInfo={() => setIsCookieBannerOpen(true)}
          drawMode={drawMode}
          onStartDraw={handleStartDraw}
          onCancelDraw={handleCancelDraw}
          drawnAreaStats={drawnAreaStats}
          onClearDrawnArea={handleClearDrawnArea}
          mapStyle={mapStyle}
          onChangeMapStyle={setMapStyle}
          mapExtentHexStats={mapExtentHexStats}
          poisData={poisData}
          onSelectPoi={handleSelectPoiFromTable}
          textScale={textScale}
          onChangeTextScale={setTextScale}
        />
      </div>

      {/* Main Vector Map */}
      <main className="flex-1 relative h-full w-full">
        <Map
          selectedHex={selectedHex}
          onSelectHex={(props) => setSelectedHex(props)}
          showGrid={showGrid}
          poiViewMode={poiViewMode}
          showTerrain={showTerrain}
          onToggleTerrain={setShowTerrain}
          gridMetric={gridMetric}
          activePoiCategories={activePoiCategories}
          activeGruppi={activeGruppi}
          focusGruppo={focusGruppo}
          heatmapRadius={heatmapRadius}
          hexValueRange={hexValueRange}
          poisData={poisData}
          gridData={gridData}
          drawMode={drawMode}
          onDrawComplete={handleDrawComplete}
          clearDrawSignal={clearDrawSignal}
          mapStyle={mapStyle}
          flyToTarget={flyToTarget}
          initialViewState={viewState}
          initialSelectedHexId={initialUrlState.selectedHexId}
          onViewStateChange={setViewState}
          onViewportBoundsChange={setViewportBounds}
        />

        {/* Draw-mode hint overlay */}
        {drawMode && (
          <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 glass-card px-4 py-2 rounded-xl border border-indigo-500/40 shadow-lg text-xs font-semibold text-slate-100">
            Clicca per aggiungere punti &bull; doppio click per chiudere il poligono
          </div>
        )}
      </main>

      <AboutModal isOpen={isAboutOpen} onClose={handleCloseAbout} />
      <CookieConsent isOpen={isCookieBannerOpen} onAccept={handleAcceptCookies} />
      <CategoryTablesModal
        isOpen={isTablesOpen}
        onClose={() => setIsTablesOpen(false)}
        poisData={poisData}
        onSelectPoi={handleSelectPoiFromTable}
      />
    </div>
  );
}
