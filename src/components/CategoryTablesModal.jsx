import React, { useEffect, useMemo, useState } from 'react';
import { X, List, ChevronLeft, ChevronRight, ChevronUp, ChevronDown, ChevronsUpDown, MapPin, Globe, Lock } from 'lucide-react';
import { ALL_POI_CATEGORIES, CATEGORY_STYLES } from '../config/mapConfig';

const PAGE_SIZE = 20;

// Column-header filters (Excel-style: a small input/select right under each
// column name) replace the old single global search bar + one category
// dropdown (2026-07-25 feedback: filters should live in the column headers).
const COLUMNS = [
  { key: 'name', label: 'Nome', type: 'text', sortable: true },
  { key: 'category', label: 'Categoria', type: 'select', sortable: true },
  { key: 'amenity_type', label: 'Tipo di Servizio', type: 'select', sortable: true },
  { key: 'accesso_pubblico', label: 'Accesso', type: 'select', sortable: true },
  { key: 'indirizzo', label: 'Indirizzo', type: 'text', sortable: true },
  { key: 'icc_score', label: 'ICC', type: 'none', sortable: true, align: 'right' }
];

export default function CategoryTablesModal({ isOpen, onClose, poisData, onSelectPoi }) {
  const [columnFilters, setColumnFilters] = useState({ name: '', category: 'all', amenity_type: 'all', accesso_pubblico: 'all', indirizzo: '' });
  const [sort, setSort] = useState({ key: 'name', direction: 'asc' });
  const [page, setPage] = useState(1);

  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [isOpen, onClose]);

  // Reset to page 1 whenever the filters/sort change, so the user isn't stuck
  // on a now-out-of-range page.
  useEffect(() => {
    setPage(1);
  }, [columnFilters, sort]);

  const allRows = useMemo(() => {
    const features = (poisData && poisData.features) || [];
    return features.map((feature) => {
      const props = feature.properties || {};
      const coords = feature.geometry && feature.geometry.type === 'Point' ? feature.geometry.coordinates : null;
      return { ...props, lng: coords ? coords[0] : null, lat: coords ? coords[1] : null };
    });
  }, [poisData]);

  // Distinct "Tipo di Servizio" values actually present in the data, for the
  // column's dropdown filter -- built from the data rather than hardcoded so
  // it never drifts out of sync with what the pipeline actually produces.
  const amenityTypeOptions = useMemo(() => {
    const set = new Set(allRows.map((r) => r.amenity_type).filter(Boolean));
    return Array.from(set).sort((a, b) => a.localeCompare(b, 'it'));
  }, [allRows]);

  const filteredRows = useMemo(() => {
    const nameQ = columnFilters.name.trim().toLowerCase();
    const indirizzoQ = columnFilters.indirizzo.trim().toLowerCase();
    return allRows.filter((row) => {
      if (columnFilters.category !== 'all' && row.category !== columnFilters.category) return false;
      if (columnFilters.amenity_type !== 'all' && row.amenity_type !== columnFilters.amenity_type) return false;
      if (columnFilters.accesso_pubblico !== 'all') {
        const isPublic = row.accesso_pubblico !== false;
        if ((columnFilters.accesso_pubblico === 'true') !== isPublic) return false;
      }
      if (nameQ && !(row.name || '').toLowerCase().includes(nameQ)) return false;
      if (indirizzoQ && !(row.indirizzo || '').toLowerCase().includes(indirizzoQ)) return false;
      return true;
    });
  }, [allRows, columnFilters]);

  const sortedRows = useMemo(() => {
    const { key, direction } = sort;
    const dir = direction === 'asc' ? 1 : -1;
    return [...filteredRows].sort((a, b) => {
      if (key === 'icc_score') {
        const av = typeof a.icc_score === 'number' ? a.icc_score : -Infinity;
        const bv = typeof b.icc_score === 'number' ? b.icc_score : -Infinity;
        return (av - bv) * dir;
      }
      if (key === 'accesso_pubblico') {
        return ((a.accesso_pubblico !== false) - (b.accesso_pubblico !== false)) * dir;
      }
      return (a[key] || '').localeCompare(b[key] || '', 'it') * dir;
    });
  }, [filteredRows, sort]);

  const totalPages = Math.max(1, Math.ceil(sortedRows.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageRows = sortedRows.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const toggleSort = (key) => {
    setSort((prev) => (
      prev.key === key
        ? { key, direction: prev.direction === 'asc' ? 'desc' : 'asc' }
        : { key, direction: 'asc' }
    ));
  };

  const setColumnFilter = (key, value) => setColumnFilters((prev) => ({ ...prev, [key]: value }));

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="glass-panel w-full max-w-5xl max-h-[85vh] overflow-hidden rounded-2xl border border-slate-700/60 shadow-2xl text-slate-100 flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-5 border-b border-slate-800/80 bg-slate-900/90 backdrop-blur-md shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl shadow-lg shadow-indigo-500/25">
              <List className="w-5 h-5 text-white" />
            </div>
            <h2 className="text-lg font-bold tracking-tight">Elenco Punti di Interesse</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition"
            aria-label="Chiudi"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-5 py-2.5 text-[11px] text-slate-400 border-b border-slate-800/60 shrink-0 space-y-1">
          <div>
            I PoI di <span className="font-semibold" style={{ color: CATEGORY_STYLES.cross_civic.color }}>Verde Urbano &amp; Servizi Civici</span> sono
            i "terzi luoghi" che uniscono le altre categorie: nel calcolo del punteggio degli esagoni contribuiscono sia a Residenti sia a Occasionali,
            invece di formare un asse a s&eacute; stante. Clicca su una riga per vederlo sulla mappa.
          </div>
          <div>
            La colonna <span className="font-semibold text-slate-300">Accesso</span> indica se il luogo, a prescindere dalla sua categoria,
            &egrave; liberamente utilizzabile anche da altre comunit&agrave; (es. un campo da calcio ad accesso pubblico lo pu&ograve; usare chiunque).
          </div>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-slate-900/95 z-10">
              <tr>
                {COLUMNS.map((col) => {
                  const isSorted = sort.key === col.key;
                  const SortIcon = !isSorted ? ChevronsUpDown : (sort.direction === 'asc' ? ChevronUp : ChevronDown);
                  return (
                    <th
                      key={col.key}
                      className={`font-semibold text-slate-400 px-4 py-2 select-none ${col.align === 'right' ? 'text-right' : 'text-left'}`}
                    >
                      <button
                        type="button"
                        onClick={() => toggleSort(col.key)}
                        className={`flex items-center gap-1 hover:text-slate-200 transition ${col.align === 'right' ? 'ml-auto flex-row-reverse' : ''} ${isSorted ? 'text-indigo-300' : ''}`}
                      >
                        <span>{col.label}</span>
                        <SortIcon className="w-3 h-3 shrink-0" />
                      </button>
                    </th>
                  );
                })}
                <th className="w-8 px-2 py-2"></th>
              </tr>
              {/* Column filter row -- Excel-style, one control per column
                  instead of a single global search bar (2026-07-25 feedback). */}
              <tr className="bg-slate-900/95">
                <th className="px-4 pb-2">
                  <input
                    type="text"
                    value={columnFilters.name}
                    onChange={(e) => setColumnFilter('name', e.target.value)}
                    placeholder="Filtra..."
                    className="w-full text-[11px] font-normal bg-slate-800/70 border border-slate-700 rounded-md px-2 py-1 text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </th>
                <th className="px-4 pb-2">
                  <select
                    value={columnFilters.category}
                    onChange={(e) => setColumnFilter('category', e.target.value)}
                    className="w-full text-[11px] font-normal bg-slate-800/70 border border-slate-700 rounded-md px-2 py-1 text-slate-200 cursor-pointer focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="all">Tutte</option>
                    {ALL_POI_CATEGORIES.map((cat) => (
                      <option key={cat} value={cat}>{CATEGORY_STYLES[cat].label}</option>
                    ))}
                  </select>
                </th>
                <th className="px-4 pb-2">
                  <select
                    value={columnFilters.amenity_type}
                    onChange={(e) => setColumnFilter('amenity_type', e.target.value)}
                    className="w-full text-[11px] font-normal bg-slate-800/70 border border-slate-700 rounded-md px-2 py-1 text-slate-200 cursor-pointer focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="all">Tutti</option>
                    {amenityTypeOptions.map((type) => (
                      <option key={type} value={type}>{type}</option>
                    ))}
                  </select>
                </th>
                <th className="px-4 pb-2">
                  <select
                    value={columnFilters.accesso_pubblico}
                    onChange={(e) => setColumnFilter('accesso_pubblico', e.target.value)}
                    className="w-full text-[11px] font-normal bg-slate-800/70 border border-slate-700 rounded-md px-2 py-1 text-slate-200 cursor-pointer focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="all">Tutti</option>
                    <option value="true">Pubblico</option>
                    <option value="false">Riservato</option>
                  </select>
                </th>
                <th className="px-4 pb-2">
                  <input
                    type="text"
                    value={columnFilters.indirizzo}
                    onChange={(e) => setColumnFilter('indirizzo', e.target.value)}
                    placeholder="Filtra..."
                    className="w-full text-[11px] font-normal bg-slate-800/70 border border-slate-700 rounded-md px-2 py-1 text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </th>
                <th className="px-4 pb-2"></th>
                <th className="px-2 pb-2"></th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((row, i) => {
                const style = CATEGORY_STYLES[row.category] || { label: row.category, color: '#94a3b8' };
                const canFly = typeof row.lng === 'number' && typeof row.lat === 'number';
                return (
                  <tr
                    key={row.id || i}
                    onClick={() => canFly && onSelectPoi && onSelectPoi(row)}
                    className={`border-t border-slate-800/60 ${canFly ? 'hover:bg-slate-800/40 cursor-pointer' : 'opacity-60'}`}
                    title={canFly ? 'Clicca per vedere sulla mappa' : 'Coordinate non disponibili'}
                  >
                    <td className="px-4 py-2 text-slate-200 font-medium">
                      {row.name || <span className="text-slate-500 italic">senza nome</span>}
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-semibold whitespace-nowrap"
                        style={{ backgroundColor: `${style.color}33`, color: style.color }}
                      >
                        {style.label}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-slate-400">{row.amenity_type || '—'}</td>
                    <td className="px-4 py-2">
                      {row.accesso_pubblico !== false ? (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold whitespace-nowrap bg-emerald-500/20 text-emerald-300">
                          <Globe className="w-3 h-3" /> Pubblico
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold whitespace-nowrap bg-slate-700/60 text-slate-400">
                          <Lock className="w-3 h-3" /> Riservato
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-slate-400">{row.indirizzo || '—'}</td>
                    <td className="px-4 py-2 text-right text-slate-300 font-mono">
                      {typeof row.icc_score === 'number' ? row.icc_score.toFixed(0) : '—'}
                    </td>
                    <td className="px-2 py-2 text-slate-500">
                      {canFly && <MapPin className="w-3.5 h-3.5" />}
                    </td>
                  </tr>
                );
              })}
              {pageRows.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-500 italic">
                    Nessun PoI corrisponde ai filtri.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between gap-3 p-4 border-t border-slate-800/60 shrink-0 bg-slate-900/40 text-xs">
          <span className="text-slate-400">
            {sortedRows.length} PoI &bull; pagina {currentPage} di {totalPages}
          </span>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={currentPage <= 1}
              className="p-1.5 rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed transition"
              aria-label="Pagina precedente"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage >= totalPages}
              className="p-1.5 rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed transition"
              aria-label="Pagina successiva"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
