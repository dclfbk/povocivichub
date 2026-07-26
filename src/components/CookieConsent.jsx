import React from 'react';
import { Cookie, X } from 'lucide-react';

// Informativa cookie/local storage -- shown once on first visit, and
// reopenable any time via the footer button (2026-07-26 feedback). The app
// sets no third-party or tracking cookies: only browser localStorage, used
// exclusively to remember on-device UI state (this consent flag, the
// welcome-dialog "seen" flag), and the shareable-link URL query string.
// There's nothing optional to toggle, so this is a single-button
// acknowledgement rather than a multi-choice consent form.
export default function CookieConsent({ isOpen, onAccept }) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-x-0 bottom-0 z-[70] p-4 flex justify-center pointer-events-none">
      <div className="relative pointer-events-auto glass-panel w-full max-w-xl rounded-2xl border border-slate-700/60 shadow-2xl text-slate-100 p-5 flex flex-col sm:flex-row items-start sm:items-center gap-4">
        <div className="p-2 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl shadow-lg shadow-indigo-500/25 shrink-0">
          <Cookie className="w-5 h-5 text-white" />
        </div>
        <div className="flex-1 text-xs text-slate-300 leading-relaxed">
          <span className="font-semibold text-slate-100">Informativa cookie e dati locali. </span>
          Questo sito non usa cookie di tracciamento o di terze parti: salva solo, sul tuo browser
          (local storage), le preferenze di visualizzazione della mappa (livelli attivi, sfondo,
          esagono selezionato) e il fatto che tu abbia già visto questo messaggio. Nessun dato viene
          inviato a server esterni.
        </div>
        <button
          onClick={onAccept}
          className="w-full sm:w-auto shrink-0 flex items-center justify-center gap-2 text-xs font-semibold px-4 py-2 rounded-lg bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 hover:bg-indigo-500/30 transition"
        >
          Ho capito
        </button>
        <button
          onClick={onAccept}
          className="absolute top-2.5 right-2.5 sm:static p-1 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition shrink-0"
          aria-label="Chiudi"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
