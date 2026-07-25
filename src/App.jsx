import React, { useState, useEffect } from 'react';
import Map from './components/Map';
import Sidebar from './components/Sidebar';
import AboutModal from './components/AboutModal';
import CategoryTablesModal from './components/CategoryTablesModal';
import { Menu, X, Layers } from 'lucide-react';
import { ALL_POI_CATEGORIES, DEFAULT_MAP_STYLE } from './config/mapConfig';

export default function App() {
  const [selectedHex, setSelectedHex] = useState(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isAboutOpen, setIsAboutOpen] = useState(false);
  const [isTablesOpen, setIsTablesOpen] = useState(false);

  // Layers are off by default; map starts in 2D.
  const [showGrid, setShowGrid] = useState(false);
  const [poiViewMode, setPoiViewMode] = useState('none'); // 'none' | 'icons' | 'heatmap'
  const [showTerrain, setShowTerrain] = useState(false);
  const [gridMetric, setGridMetric] = useState('dominant');
  const [activePoiCategories, setActivePoiCategories] = useState(ALL_POI_CATEGORIES);
  const [mapStyle, setMapStyle] = useState(DEFAULT_MAP_STYLE);

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

      <AboutModal isOpen={isAboutOpen} onClose={() => setIsAboutOpen(false)} />
      <CategoryTablesModal isOpen={isTablesOpen} onClose={() => setIsTablesOpen(false)} poisData={poisData} />
    </div>
  );
}
