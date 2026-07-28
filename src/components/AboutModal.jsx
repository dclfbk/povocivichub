import React, { useEffect } from 'react';
import { X, BookOpen, Users, ShieldCheck, Eye, Mountain, Sigma, Leaf, GraduationCap, Bus, Trees } from 'lucide-react';

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

// Moved here from the sidebar (2026-07-26 feedback: as a standalone sidebar
// section it looked like an interactive legend/filter, but it's actually
// just background context on the neighbourhood -- it belongs with the rest
// of the "why this map, what am I looking at" explainer, not floating
// unconnected to any data layer.
const PLACES = [
  {
    icon: Leaf,
    color: 'emerald',
    title: 'Parchi & Giardini Pubblici',
    text: 'Aree verdi di quartiere (parchi e giardini) come spazi di incontro e beni comuni condivisi.'
  },
  {
    icon: BookOpen,
    color: 'amber',
    title: 'Punti di Bookcrossing (Public Bookcase)',
    text: 'Spazi ad accesso libero per lo scambio librario e la condivisione culturale nel quartiere.'
  },
  {
    icon: GraduationCap,
    color: 'blue',
    title: 'Poli Universitari & Ricerca (Povo 1 & 2, FBK, UniTrento, CNR, HIT)',
    // 2026-07-26 feedback: FBK e UniTrento non sono "luoghi pubblici" in
    // senso stretto -- contano soprattutto come attrattori di pendolari
    // (studenti, ricercatori) verso Povo, quindi il testo li lega
    // esplicitamente alla categoria Pendolari usata nell'analisi. CNR-IFN
    // Trento e HIT (Hub Innovazione Trentino) aggiunti 2026-07-28: stesso
    // office=research di FBK/UniTrento su OSM, stesso ruolo di attrattori.
    text: "Hub scientifico e universitario di eccellenza -- comprende anche il CNR-IFN e l'Hub Innovazione Trentino (HIT) -- che attira ogni giorno un forte flusso di studenti, ricercatori e lavoratori: sono tra i principali motori della categoria \"Pendolari\" nell'analisi, più che semplici luoghi pubblici."
  },
  {
    icon: Bus,
    color: 'purple',
    title: 'Nodo TPL (Fermate Urbane ed Extraurbane)',
    text: '71 fermate TTE integrate con 536 corse feriali di punta e 3.053 corse serali/festive.'
  },
  {
    icon: Trees,
    color: 'emerald',
    title: 'Rete Outdoor & Sentieristica',
    text: 'Accessibilità pedonale ai sentieri della collina orientale, punti panoramici e aree picnic.'
  }
];

const CREDITS = [
  { label: 'Dati geografici', value: 'OpenStreetMap · Provincia Autonoma di Trento (DTM 1m)' },
  { label: 'Trasporti', value: 'GTFS Trentino Trasporti' },
  { label: 'Mappa base', value: 'OpenFreeMap Liberty' }
];

// Tailwind needs full, static class strings to find them at build time --
// can't interpolate `bg-${color}-500/20` dynamically.
const PLACE_COLOR_CLASSES = {
  emerald: 'bg-emerald-500/20 text-emerald-300',
  amber: 'bg-amber-500/20 text-amber-300',
  blue: 'bg-blue-500/20 text-blue-300',
  purple: 'bg-purple-500/20 text-purple-300'
};

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

          <section className="space-y-3">
            <h3 className="text-xs font-bold text-indigo-400 uppercase tracking-widest">Il Contesto di Povo</h3>
            <p className="text-slate-400 text-xs leading-relaxed">
              Alcuni elementi del territorio che spiegano perché Povo mescola così tanti tipi diversi
              di presenza: residenti, pendolari e visitatori occasionali.
            </p>
            <div className="space-y-2.5">
              {PLACES.map(({ icon: Icon, color, title, text }) => (
                <div key={title} className="flex items-start gap-3 p-3 glass-card rounded-xl border border-slate-800">
                  <div className={`p-2 rounded-lg shrink-0 mt-0.5 ${PLACE_COLOR_CLASSES[color]}`}>
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
