import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { Info, X } from 'lucide-react';

// A small (i) button that opens a plain-language explanation on click --
// used next to technical index names (2026-07-25 feedback: "Mixité" and the
// hexagon indices aren't self-explanatory to a general Italian-speaking
// audience). Self-contained: safe to drop next to a <label> without the
// click also triggering the label's own radio/checkbox.
export default function InfoButton({ title, children }) {
  const [open, setOpen] = useState(false);

  const handleOpen = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setOpen(true);
  };

  return (
    <>
      <button
        type="button"
        onClick={handleOpen}
        className="text-slate-500 hover:text-indigo-400 transition shrink-0"
        aria-label={`Cos'è: ${title}`}
        title={`Cos'è: ${title}`}
      >
        <Info className="w-3.5 h-3.5" />
      </button>

      {open && createPortal(
        // Rendered into document.body via a portal, not inline where the
        // button sits: the sidebar's `.glass-panel` uses backdrop-filter,
        // which creates a CSS containing block for `position: fixed`
        // descendants and would otherwise trap this overlay inside the
        // narrow sidebar column instead of centering on the full viewport.
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm"
          onClick={() => setOpen(false)}
        >
          <div
            className="glass-panel w-full max-w-sm rounded-2xl border border-slate-700/60 shadow-2xl text-slate-100 p-5 space-y-3"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-bold text-indigo-300">{title}</h3>
              <button
                onClick={() => setOpen(false)}
                className="p-1 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition shrink-0"
                aria-label="Chiudi"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="text-xs text-slate-300 leading-relaxed">{children}</div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
