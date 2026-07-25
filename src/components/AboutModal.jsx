import React, { useEffect } from 'react';
import { X, BookOpen, Users, ShieldCheck, Eye, Mountain, Sigma } from 'lucide-react';

const MODELS = [
  {
    icon: Users,
    title: 'Terzi Luoghi (Ray Oldenburg)',
    text: 'Perché i bar, i mercati e le casette dei libri sono il collante della società: spazi informali, aperti a tutti, dove ci si incontra senza uno scopo preciso.'
  },
  {
    icon: ShieldCheck,
    title: 'Infrastruttura Sociale (Eric Klinenberg)',
    text: 'Come i luoghi fisici condivisi — biblioteche, parchi, centri civici — aumentano la sicurezza e la resilienza di un quartiere, soprattutto nei momenti di difficoltà.'
  },
  {
    icon: Eye,
    title: 'Mixité e Occhi sulla Strada (Jane Jacobs)',
    text: "L'importanza di far convivere studenti, residenti ed escursionisti negli stessi spazi: più sguardi vigili sulla strada, più vitalità e sicurezza percepita."
  },
  {
    icon: Mountain,
    title: 'Tempo di Percorrenza Reale (Funzione di Tobler)',
    text: "Come la pendenza del terreno (DTM) influenza la reale raggiungibilità a piedi, oltre la semplice distanza in linea d'aria."
  },
  {
    icon: Sigma,
    title: 'Indice di Mixité (Entropia di Shannon)',
    text: 'Il calcolo matematico usato per scoprire quali zone di Povo sono vive e polifunzionali, e quali invece monofunzionali.'
  }
];

const CREDITS = [
  { label: 'Dati geografici', value: 'OpenStreetMap · Provincia Autonoma di Trento (DTM 1m)' },
  { label: 'Trasporti', value: 'GTFS Trentino Trasporti' },
  { label: 'Mappa base', value: 'OpenFreeMap Liberty' }
];

export default function AboutModal({ isOpen, onClose }) {
  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="glass-panel w-full max-w-lg max-h-[85vh] overflow-y-auto rounded-2xl border border-slate-700/60 shadow-2xl text-slate-100"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between p-5 border-b border-slate-800/80 bg-slate-900/90 backdrop-blur-md">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl shadow-lg shadow-indigo-500/25">
              <BookOpen className="w-5 h-5 text-white" />
            </div>
            <h2 className="text-lg font-bold tracking-tight">Povo Civic HUB</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-slate-800 rounded-lg text-slate-400 hover:text-white transition"
            aria-label="Chiudi"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-6 text-sm">
          <section className="space-y-2">
            <h3 className="text-xs font-bold text-indigo-400 uppercase tracking-widest">Cos'è Povo Civic Hub</h3>
            <p className="text-slate-300 leading-relaxed">
              Una mappa di co-presenza che non si limita a mostrare dove sono le cose, ma misura
              come la comunità vive il territorio: dove le persone si incrociano, si fermano e
              condividono lo spazio pubblico.
            </p>
          </section>

          <section className="space-y-3">
            <h3 className="text-xs font-bold text-indigo-400 uppercase tracking-widest">I Modelli Scientifici Utilizzati</h3>
            <div className="space-y-2.5">
              {MODELS.map(({ icon: Icon, title, text }) => (
                <div key={title} className="flex items-start gap-3 p-3 glass-card rounded-xl border border-slate-800">
                  <div className="p-2 bg-indigo-500/20 text-indigo-300 rounded-lg shrink-0 mt-0.5">
                    <Icon className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="font-semibold text-slate-200">{title}</div>
                    <div className="text-slate-400 mt-0.5 text-xs leading-relaxed">{text}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="space-y-2">
            <h3 className="text-xs font-bold text-indigo-400 uppercase tracking-widest">Crediti e Dati Aperti</h3>
            <div className="space-y-1.5 text-xs">
              {CREDITS.map(({ label, value }) => (
                <div
                  key={label}
                  className="flex justify-between gap-3 p-2.5 bg-slate-900/60 rounded-lg border border-slate-800"
                >
                  <span className="text-slate-400 shrink-0">{label}</span>
                  <span className="text-slate-200 font-medium text-right">{value}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
