import React, { useState, useEffect } from 'react';
import Map from './components/Map';
import Sidebar from './components/Sidebar';
import AboutModal from './components/AboutModal';
import CategoryTablesModal from './components/CategoryTablesModal';
import { Menu, X, Layers } from 'lucide-react';
import { parseUrlState, buildUrlSearch } from './utils/urlState';

const INTRO_SEEN_KEY = 'povoCivicHub_introSeen';

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
  const [flyToTarget, setFlyToTarget] = useState(null);

  // Layers default to whatever the URL says, falling back to off/2D.
  const [showGrid, setShowGrid] = useState(initialUrlState.showGrid);
  const [poiViewMode, setPoiViewMode] = useState(initialUrlState.poiViewMode); // 'none' | 'icons' | 'heatmap'
  const [showTerrain, setShowTerrain] = useState(initialUrlState.showTerrain);
  const [gridMetric, setGridMetric] = useState(initialUrlState.gridMetric);
  const [activePoiCategories, setActivePoiCategories] = useState(initialUrlState.activePoiCategories);
  const [mapStyle, setMapStyle] = useState(initialUrlState.mapStyle);

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

  // Draw-an-area tool state.
  const [drawMode, setDrawMode] = useState(false);
  const [drawnAreaStats, setDrawnAreaStats] = useState(null);
  const [clearDrawSignal, setClearDrawSignal] = useState(0);

  useEffect(() => {
    fetch('./data/povo_pois.json')
      .then((res) => res.json())
      .then(setPoisData)
      .catch((err) => console.error('Failed to load povo_pois.json', err));
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
      mapStyle,
      selectedHexId: (selectedHex && selectedHex.h3_id) || null
    });
    window.history.replaceState(null, '', `${window.location.pathname}?${qs}`);
  }, [viewState, showTerrain, poiViewMode, showGrid, gridMetric, activePoiCategories, mapStyle, selectedHex]);

  const handleTogglePoiCategory = (category, isActive) => {
    setActivePoiCategories((prev) =>
      isActive ? [...prev, category] : prev.filter((c) => c !== category)
    );
  };

  const handleStartDraw = () => {
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
  const handleSelectPoiFromTable = (poi) => {
    setIsTablesOpen(false);
    setPoiViewMode('icons');
    setFlyToTarget({ ...poi, _t: Date.now() });
  };

  return (
    <div className="relative w-screen h-screen overflow-hidden flex flex-col md:flex-row bg-slate-950">
      {/* Mobile Toggle Button */}
      <button
        onClick={() => setIsSidebarOpen(!isSidebarOpen)}
        className="md:hidden absolute top-4 left-4 z-30 p-3 bg-slate-900/90 text-white rounded-xl border border-slate-700 shadow-xl backdrop-blur-md"
        aria-label="Toggle Sidebar"
      >
        {isSidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
      </button>

      {/* Sidebar Panel */}
      <div className={`${isSidebarOpen ? 'flex' : 'hidden'} md:flex h-full shrink-0 z-20`}>
        <Sidebar
          selectedHex={selectedHex}
          onResetSelection={() => setSelectedHex(null)}
          showGrid={showGrid}
          onToggleGrid={setShowGrid}
          poiViewMode={poiViewMode}
          onChangePoiViewMode={setPoiViewMode}
          showTerrain={showTerrain}
          onToggleTerrain={setShowTerrain}
          gridMetric={gridMetric}
          onChangeGridMetric={setGridMetric}
          activePoiCategories={activePoiCategories}
          onTogglePoiCategory={handleTogglePoiCategory}
          onOpenAbout={() => setIsAboutOpen(true)}
          onOpenTables={() => setIsTablesOpen(true)}
          drawMode={drawMode}
          onStartDraw={handleStartDraw}
          onCancelDraw={handleCancelDraw}
          drawnAreaStats={drawnAreaStats}
          onClearDrawnArea={handleClearDrawnArea}
          mapStyle={mapStyle}
          onChangeMapStyle={setMapStyle}
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
          gridMetric={gridMetric}
          activePoiCategories={activePoiCategories}
          poisData={poisData}
          drawMode={drawMode}
          onDrawComplete={handleDrawComplete}
          clearDrawSignal={clearDrawSignal}
          mapStyle={mapStyle}
          flyToTarget={flyToTarget}
          initialViewState={viewState}
          initialSelectedHexId={initialUrlState.selectedHexId}
          onViewStateChange={setViewState}
        />

        {/* Floating Top Badge Info */}
        <div className="hidden lg:flex absolute top-4 right-16 z-10 glass-card px-4 py-2 rounded-xl border border-slate-700/60 shadow-lg text-xs font-semibold items-center gap-2 text-slate-200 pointer-events-none">
          <Layers className="w-4 h-4 text-indigo-400" />
          <span>
            {showTerrain ? 'MapLibre 3D Terrain' : 'MapLibre 2D'} &bull; Uber H3 Res 10 &bull; Tobler Hiking Model
          </span>
        </div>

        {/* Draw-mode hint overlay */}
        {drawMode && (
          <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 glass-card px-4 py-2 rounded-xl border border-indigo-500/40 shadow-lg text-xs font-semibold text-slate-100">
            Clicca per aggiungere punti &bull; doppio click per chiudere il poligono
          </div>
        )}
      </main>

      <AboutModal isOpen={isAboutOpen} onClose={handleCloseAbout} />
      <CategoryTablesModal
        isOpen={isTablesOpen}
        onClose={() => setIsTablesOpen(false)}
        poisData={poisData}
        onSelectPoi={handleSelectPoiFromTable}
      />
    </div>
  );
}
