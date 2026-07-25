import React from 'react';
import MixChart from './MixChart';
import {
  MapPin,
  Layers,
  BookOpen,
  Bus,
  GraduationCap,
  Trees,
  Leaf,
  Activity,
  Info,
  Sparkles,
  RotateCcw,
  Mountain,
  Hexagon,
  MapPinned,
  EyeOff,
  Flame
} from 'lucide-react';
import { CATEGORY_STYLES, ALL_POI_CATEGORIES, GRID_METRICS, gridMetricGradientCss } from '../config/mapConfig';

const POI_VIEW_MODES = [
  { key: 'none', label: 'Nessun PoI', icon: EyeOff },
  { key: 'icons', label: 'Icone e Cluster', icon: MapPinned },
  { key: 'heatmap', label: 'Mappa di Calore (Heatmap)', icon: Flame }
];

export default function Sidebar({
  selectedHex,
  onResetSelection,
  showGrid,
  onToggleGrid,
  poiViewMode,
  onChangePoiViewMode,
  showTerrain,
  onToggleTerrain,
  gridMetric,
  onChangeGridMetric,
  activePoiCategories,
  onTogglePoiCategory,
  onOpenAbout
}) {
  const mixIndex = selectedHex ? parseFloat(selectedHex.mix_index || 0) : null;

  // Determine Mixité Index Badge Color & Label
  const getMixLevel = (score) => {
    if (score === null) return { label: 'Media Generale', color: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30' };
    if (score > 0.75) return { label: 'Elevato Mixing (Alta Polifunzionalità)', color: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' };
    if (score > 0.45) return { label: 'Medio Mixing', color: 'bg-amber-500/20 text-amber-300 border-amber-500/30' };
    return { label: 'Basso Mixing (Monoculturale)', color: 'bg-blue-500/20 text-blue-300 border-blue-500/30' };
  };

  const mixLevel = getMixLevel(mixIndex);

  return (
    <aside className="w-full md:w-[420px] h-full glass-panel flex flex-col z-20 overflow-y-auto border-r border-slate-800 text-slate-100 shadow-2xl">
      {/* App Header */}
      <header className="p-6 border-b border-slate-800/80 bg-slate-900/60 flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl shadow-lg shadow-indigo-500/25">
              <Activity className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-indigo-100 to-indigo-300">
                Povo Civic Hub
              </h1>
              <p className="text-xs text-indigo-300/80 font-medium">Mappe di Co-presenza & Mixité</p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={onOpenAbout}
              className="p-2 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition"
              title="A cosa serve questa mappa?"
              aria-label="A cosa serve questa mappa?"
            >
              <BookOpen className="w-4 h-4" />
            </button>
            {selectedHex && (
              <button
                onClick={onResetSelection}
                className="p-2 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition"
                title="Reset Selezione"
              >
                <RotateCcw className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="p-6 space-y-6 flex-1">
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
                    className="w-3.5 h-3.5 accent-indigo-500 cursor-pointer"
                    checked={poiViewMode === key}
                    onChange={() => onChangePoiViewMode(key)}
                  />
                  <ModeIcon className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                  <span className="text-slate-300">{label}</span>
                </label>
              ))}
            </div>

            {poiViewMode === 'icons' && (
              <div className="grid grid-cols-2 gap-2 pl-1">
                {ALL_POI_CATEGORIES.map((cat) => {
                  const style = CATEGORY_STYLES[cat];
                  const Icon = style.icon;
                  const active = activePoiCategories.includes(cat);
                  return (
                    <label
                      key={cat}
                      className="flex items-center gap-1.5 text-[11px] px-2 py-1.5 rounded-lg border border-slate-800 bg-slate-900/60 cursor-pointer select-none"
                    >
                      <input
                        type="checkbox"
                        className="w-3 h-3 rounded cursor-pointer"
                        style={{ accentColor: style.color }}
                        checked={active}
                        onChange={(e) => onTogglePoiCategory(cat, e.target.checked)}
                      />
                      <Icon className="w-3 h-3 shrink-0" style={{ color: style.color }} />
                      <span className="text-slate-300 truncate">{style.label}</span>
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
                  <label
                    key={key}
                    className="flex items-center gap-2 text-[11px] px-2 py-1.5 rounded-lg border border-slate-800 bg-slate-900/60 cursor-pointer select-none"
                  >
                    <input
                      type="radio"
                      name="gridMetric"
                      className="w-3 h-3 accent-indigo-500 cursor-pointer"
                      checked={gridMetric === key}
                      onChange={() => onChangeGridMetric(key)}
                    />
                    <span className="text-slate-300">{cfg.label}</span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {/* Toggle: 3D terrain */}
          <div className="border-t border-slate-800 pt-3">
            <label className="flex items-center justify-between cursor-pointer select-none">
              <span className="flex items-center gap-2 text-sm font-semibold text-slate-200">
                <Mountain className="w-4 h-4 text-slate-400" /> Attiva Vista 3D Orografia
              </span>
              <input
                type="checkbox"
                className="w-4 h-4 accent-indigo-500 rounded cursor-pointer"
                checked={showTerrain}
                onChange={(e) => onToggleTerrain(e.target.checked)}
              />
            </label>
          </div>
        </section>

        {/* Selected Hexagon Info Card */}
        <section className="glass-card rounded-2xl p-5 border border-slate-700/60 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-indigo-400 uppercase tracking-widest flex items-center gap-1.5">
              <MapPin className="w-3.5 h-3.5" /> Esagone H3 (Res 9)
            </span>
            {selectedHex ? (
              <span className="text-xs font-mono bg-slate-800 px-2 py-0.5 rounded border border-slate-700 text-slate-300">
                {selectedHex.h3_id}
              </span>
            ) : (
              <span className="text-xs text-slate-400">Povo Centro</span>
            )}
          </div>

          {/* Mixité Index Metric */}
          <div className="flex items-baseline justify-between border-t border-slate-800 pt-3">
            <div>
              <div className="text-xs text-slate-400">Indice di Mixité (Shannon)</div>
              <div className="text-3xl font-extrabold tracking-tight text-white mt-0.5">
                {mixIndex !== null ? mixIndex.toFixed(4) : '0.6524'}
              </div>
            </div>
            <span className={`text-xs px-3 py-1 rounded-full font-semibold border ${mixLevel.color}`}>
              {mixLevel.label}
            </span>
          </div>

          {/* Score Breakdown Pills */}
          <div className="grid grid-cols-3 gap-2 pt-2 text-center text-xs">
            <div className="bg-slate-900/60 p-2 rounded-lg border border-slate-800">
              <div className="text-slate-400">Residenti</div>
              <div className="font-bold text-blue-400 mt-0.5">
                {selectedHex ? (selectedHex.res_score * 100).toFixed(1) + '%' : '42.0%'}
              </div>
            </div>
            <div className="bg-slate-900/60 p-2 rounded-lg border border-slate-800">
              <div className="text-slate-400">Pendolari</div>
              <div className="font-bold text-amber-400 mt-0.5">
                {selectedHex ? (selectedHex.comm_score * 100).toFixed(1) + '%' : '38.0%'}
              </div>
            </div>
            <div className="bg-slate-900/60 p-2 rounded-lg border border-slate-800">
              <div className="text-slate-400">Occasionali</div>
              <div className="font-bold text-pink-400 mt-0.5">
                {selectedHex ? (selectedHex.occa_score * 100).toFixed(1) + '%' : '56.0%'}
              </div>
            </div>
          </div>
        </section>

        {/* Co-presence Radar Chart */}
        <section className="space-y-2">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
            <Sparkles className="w-4 h-4 text-indigo-400" /> Profilo Funzionale
          </div>
          <MixChart selectedHex={selectedHex} />
        </section>

        {/* Verde Urbano & Servizi Civici */}
        <section className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-200">
            <Layers className="w-4 h-4 text-emerald-400" /> Verde Urbano & Servizi Civici
          </div>

          <div className="space-y-2.5 text-xs">
            <div className="flex items-start gap-3 p-3 glass-card rounded-xl border border-slate-800 hover:border-slate-700 transition">
              <div className="p-2 bg-emerald-500/20 text-emerald-300 rounded-lg shrink-0 mt-0.5">
                <Leaf className="w-4 h-4" />
              </div>
              <div>
                <div className="font-semibold text-slate-200">Parchi & Giardini Pubblici</div>
                <div className="text-slate-400 mt-0.5">
                  Aree verdi di quartiere (parchi e giardini) come spazi di incontro e beni comuni condivisi.
                </div>
              </div>
            </div>

            <div className="flex items-start gap-3 p-3 glass-card rounded-xl border border-slate-800 hover:border-slate-700 transition">
              <div className="p-2 bg-amber-500/20 text-amber-300 rounded-lg shrink-0 mt-0.5">
                <BookOpen className="w-4 h-4" />
              </div>
              <div>
                <div className="font-semibold text-slate-200">Punti di Bookcrossing (Public Bookcase)</div>
                <div className="text-slate-400 mt-0.5">
                  Spazi ad accesso libero per lo scambio librario e la condivisione culturale nel quartiere.
                </div>
              </div>
            </div>

            <div className="flex items-start gap-3 p-3 glass-card rounded-xl border border-slate-800 hover:border-slate-700 transition">
              <div className="p-2 bg-blue-500/20 text-blue-300 rounded-lg shrink-0 mt-0.5">
                <GraduationCap className="w-4 h-4" />
              </div>
              <div>
                <div className="font-semibold text-slate-200">Poli Universitari & Ricerca (Povo 1 & 2, FBK)</div>
                <div className="text-slate-400 mt-0.5">
                  Hub scientifico di eccellenza con forte afflusso giornaliero di studenti e ricercatori.
                </div>
              </div>
            </div>

            <div className="flex items-start gap-3 p-3 glass-card rounded-xl border border-slate-800 hover:border-slate-700 transition">
              <div className="p-2 bg-purple-500/20 text-purple-300 rounded-lg shrink-0 mt-0.5">
                <Bus className="w-4 h-4" />
              </div>
              <div>
                <div className="font-semibold text-slate-200">Nodo TPL (Fermate Urbane ed Extraurbane)</div>
                <div className="text-slate-400 mt-0.5">
                  71 fermate TTE integrate con 536 corse feriali di punta e 3.053 corse serali/festive.
                </div>
              </div>
            </div>

            <div className="flex items-start gap-3 p-3 glass-card rounded-xl border border-slate-800 hover:border-slate-700 transition">
              <div className="p-2 bg-emerald-500/20 text-emerald-300 rounded-lg shrink-0 mt-0.5">
                <Trees className="w-4 h-4" />
              </div>
              <div>
                <div className="font-semibold text-slate-200">Rete Outdoor & Sentieristica</div>
                <div className="text-slate-400 mt-0.5">
                  Accessibilità pedonale ai sentieri della collina orientale, punti panoramici e aree picnic.
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Legend */}
        <section className="glass-card rounded-xl p-4 space-y-2 border border-slate-800">
          <div className="text-xs font-semibold text-slate-300 flex items-center justify-between">
            <span>Legenda &bull; {GRID_METRICS[gridMetric].label}</span>
            <Info className="w-3.5 h-3.5 text-slate-400" />
          </div>
          <div className="h-3 w-full rounded-full" style={{ background: gridMetricGradientCss(gridMetric) }} />
          <div className="flex justify-between text-[10px] text-slate-400 font-mono">
            <span>0.0 Basso</span>
            <span>0.5 Medio</span>
            <span>1.0 Alto</span>
          </div>
        </section>
      </div>

      {/* Footer */}
      <footer className="p-4 border-t border-slate-800/80 bg-slate-950/80 text-[11px] text-slate-400 text-center">
        Povo Civic Hub &copy; 2026 &bull; Data Science Unitn &bull; OpenFreeMap & MapLibre GL
      </footer>
    </aside>
  );
}
