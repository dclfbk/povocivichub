import React, { useState } from 'react';

// Horizontal stacked bar showing category segments (color-matched to
// CATEGORY_STYLES), with a hover tooltip showing both the absolute value and
// the percentage share -- replaces the old radar chart, which didn't make it
// obvious at a glance what a hexagon (or drawn area) was actually for.
export default function CategoryStackedBar({ title, segments, valueLabel = 'Valore', valueFormatter, note }) {
  const [hoveredKey, setHoveredKey] = useState(null);
  const hovered = segments.find((s) => s.key === hoveredKey);
  const formatValue = valueFormatter || ((v) => v.toFixed(2));
  const hasData = segments.some((s) => s.value > 0);

  return (
    <div className="w-full bg-slate-900/40 rounded-xl p-3 border border-slate-700/50 space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-xs font-semibold text-slate-300 uppercase tracking-wider">{title}</div>
        <div className="text-[11px] text-slate-400 h-4">
          {hovered ? (
            <span>
              <span className="font-semibold" style={{ color: hovered.color }}>{hovered.label}</span>
              {': '}
              {formatValue(hovered.value)} ({hovered.percentage.toFixed(1)}%)
            </span>
          ) : (
            <span className="text-slate-500">passa il mouse per i dettagli</span>
          )}
        </div>
      </div>

      {hasData ? (
        <div className="flex w-full h-6 rounded-lg overflow-hidden border border-slate-800">
          {segments.filter((s) => s.value > 0).map((s) => (
            <div
              key={s.key}
              className="h-full transition-opacity cursor-default flex items-center justify-center"
              style={{
                width: `${s.percentage}%`,
                backgroundColor: s.color,
                opacity: hoveredKey && hoveredKey !== s.key ? 0.45 : 1
              }}
              onMouseEnter={() => setHoveredKey(s.key)}
              onMouseLeave={() => setHoveredKey(null)}
              title={`${s.label}: ${formatValue(s.value)} (${s.percentage.toFixed(1)}%)`}
            >
              {s.percentage >= 12 && (
                <span className="text-[10px] font-bold text-slate-950/80 select-none">
                  {s.percentage.toFixed(0)}%
                </span>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="h-6 rounded-lg border border-dashed border-slate-700 flex items-center justify-center text-[11px] text-slate-500">
          Nessun dato disponibile
        </div>
      )}

      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {segments.map((s) => (
          <div
            key={s.key}
            className="flex items-center gap-1.5 text-[10px] text-slate-400 cursor-default"
            onMouseEnter={() => setHoveredKey(s.key)}
            onMouseLeave={() => setHoveredKey(null)}
          >
            <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: s.color }} />
            <span>{s.label}</span>
          </div>
        ))}
      </div>

      {note && <div className="text-[10px] text-slate-500 leading-relaxed pt-1 border-t border-slate-800">{note}</div>}
      <div className="text-[10px] text-slate-600">{valueLabel}</div>
    </div>
  );
}
