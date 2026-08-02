# Povo Civic Hub
> **Atlante interattivo della co-presenza, della vitalità territoriale e dell'infrastruttura sociale per la circoscrizione di Povo (Trento)**


[![Deploy to GitHub Pages](https://github.com/dclfbk/povocivichub/actions/workflows/deploy.yml/badge.svg)](https://github.com/dclfbk/povocivichub/actions/workflows/deploy.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Cos'è Povo Civic Hub?

**Povo Civic Hub** è una piattaforma WebGIS interattiva creata per analizzare, mappare e comprendere la complessità territoriale della circoscrizione di Povo (Trento). 

A differenza delle tradizionali mappe turistiche o di navigazione, il progetto applica i modelli della sociologia urbana e della geografia quantitativa per studiare la **co-presenza** nello spazio pubblico, ossia come tre popolazioni principali convivono e utilizzano il territorio:
1. **Residenti ($R$):** Residenti legati ai servizi di vicinato e alla vita quotidiana.
2. **Pendolari ($P$):** La comunità di chi si sposta ogni giorno a Povo (personale di FBK, UNITN, studenti ...)
3. **Occasionali ($O$):** Escursionisti, arrampicatori, sportivi o semplicemente famiglie in cerca di un luogo fresco o una breve gita attratti dall'ambiente naturale (Cimirlo, Celva, Marzola) e storico (es. *Stoi* del Chegul, Batteria Roncogno)

---

## Riferimenti Scientifici e Bibliografia Esatta

Il progettos si base su metriche e classificazione dei punti di interesse (PoI) su cinque pilastri teorici e metodologici:

### 1. Terzi Luoghi (*Third Places*)
Spazi neutri, inclusivi e ad accesso gratuito in cui le persone si incontrano spontaneamente, essenziali per la formazione del capitale sociale e del senso di appartenenza.
> Oldenburg, R. (1989). *The Great Good Place: Cafes, Coffee Shops, Community Centers, Beauty Parlors, General Stores, Bars, Hangouts, and How They Get You Through the Day*. Paragon House. ISBN: 978-1557781109.

### 2. Infrastruttura Sociale (*Social Infrastructure*)
I luoghi fisici e le organizzazioni che favoriscono le interazioni sociali, la fiducia reciproca e la resilienza comunitaria di fronte alle emergenze.
> Klinenberg, E. (2018). *Palaces for the People: How Social Infrastructure Can Help Fight Inequality, Polarization, and the Decline of Civic Life*. Crown Publishing Group. ISBN: 978-1524761370.

### 3. Vitalità Urbana e "Occhi sulla Strada"
L'importanza della varietà funzionale negli stessi orari e spazi per garantire una frequenza costante di persone, sicurezza informale e presidio della strada.
> Jacobs, J. (1961). *The Death and Life of Great American Cities*. Random House. ISBN: 978-0679644330.

### 4. Accessibilità Reale e Tempi di Percorrenza Pedonale
Calcolo dei tempi effettivi di camminata tenendo conto dell'inclinazione del terreno (DTM a 1m della PAT), superando il limite della semplice distanza in linea d'aria.
> Tobler, W. (1993). *Three presentations on geographical analysis and modeling: Non-isotropic geographic modeling, speculations on the geometry of geography, global spatial analysis*. Technical Report 93-1, National Center for Geographic Information and Analysis (NCGIA), University of California, Santa Barbara.

### 5. Quantificazione della Co-presenza e Varietà Spaziale
Applicazione dell'Entropia di Shannon su celle esagonali per calcolare l'indice sintetico di co-presenza tra le tre popolazioni ($R$, $P$, $O$).
> * Shannon, C. E. (1948). A Mathematical Theory of Communication. *Bell System Technical Journal*, 27(3), 379–423.  
> * Brodsky, A. (2018). *H3: Uber's Hexagonal Hierarchical Spatial Index*. Uber Engineering Blog.

#### Pesi per tipologia di PoI (`POI_WEIGHT`)

Fino al 2026-08-02 ogni PoI contribuiva al punteggio del proprio esagono (e quindi
a `res_score`/`comm_score`/`occa_score`/`mix_index`) con un peso fisso di 1, a
prescindere dal tipo: una fontanella contava quanto un'università. Da quella
data `compute_raw_poi_score` (`python_pipeline/build_data.py`) applica invece un
moltiplicatore per `sub_type`, definito nel dizionario `POI_WEIGHT`:

| Peso | Criterio | Esempi |
|---|---|---|
| 1.5 | Grande "ancora" del quartiere: presenza quotidiana e stabile, alto numero di persone coinvolte | università, istituto di ricerca, scuola, supermercato, centro/palestra sportiva |
| 1.3 | Servizio di quartiere con affluenza regolare ma più contenuta | asilo, biblioteca, centro civico, municipio, stazione, ambulatorio, mercato |
| 1.2 | Attrattore culturale, affluenza più occasionale | museo |
| 1.0 (default) | Tutto il resto: nessuna evidenza per scostarsi dal peso neutro | bar, ristoranti, negozi di vicinato, ecc. |
| 0.5–0.6 | Arredo/servizio minore: presenza reale ma richiamo individuale molto basso | fontanella, bookcrossing, area picnic/bbq, rifugio/pensilina |

**Come sono stati scelti questi valori.** Non da un dato di affluenza misurato
(il progetto non dispone di conteggi di presenze), ma da un criterio esplicito e
volutamente grezzo: quanto stabilmente e quanto spesso un PoI di quel tipo
richiama persone nel corso della giornata, per analogia con il ruolo di "terzo
luogo"/"infrastruttura sociale" descritto in Oldenburg (1989) e Klinenberg
(2018) sopra. È una prima approssimazione soggetta a revisione, non una stima
calibrata — se emergono controesempi concreti (un tipo di PoI pesato troppo
alto o troppo basso rispetto a quanto osservato sul campo), i valori vanno
aggiornati di conseguenza.

---

## Architettura Tecnica

Il progetto adotta un'architettura disaccoppiata e ad alte prestazioni:

* **Data Pipeline (Python / Offline Processing):**
  * `GeoPandas` & `Shapely`: Gestione delle geometrie e trasformazioni CRS proiettate in **EPSG:25832** (UTM 32N) per i calcoli metrici e riesportazione in **EPSG:4326** per la mappa web.
  * `OSMnx`: Estrazione massiva di PoI, beni comuni, sentieri e reti da OpenStreetMap.
  * `H3-Py`: Indicizzazione spaziale su griglia esagonale Uber H3.
  * `Rasterio`: Elaborazione del Modello Digitale del Terreno (DTM 1m) per le pendenze.
* **Frontend Web (React.js / Client-Side):**
  * **Vite**: Build tool ultra-veloce.
  * **MapLibre GL JS**: Rendering vettoriale 2D/3D con stile OpenFreeMap Liberty, clustering dinamico, heatmap e terrain 3D su richiesta.
  * **Recharts**: Grafici interattivi a radar per la composizione della co-presenza negli esagoni.
  * **Tailwind CSS**: Layout reattivo e moderno.
* **Deployment & Hosting:**
  * **GitHub Pages**: Distribuzione automatica via GitHub Actions ad ogni push sul ramo `main`.

---

## Mappe e Layer Disponibili

L'interfaccia permette all'utente di esplorare in modo granulare:
* **Mappa Base 2D di Default** (con toggle opzionale per l'orografia 3D).
* **Layer Poligonali (Griglia Esagonale H3):**
  * Indice sintetico di **Co-presenza e Vitalità**.
  * Dominanza **Residenti** ($R$).
  * Dominanza **Pendolari / Università** ($P$).
  * Dominanza **Outdoor / Memoria** ($O$).
* **Layer Puntuali (PoI e Beni Comuni):**
  * Filtro per categoria con icone dedicate.
  * Modalità di visualizzazione: **Icone singole**, **Cluster numerati** e **Mappa di Calore (Heatmap)**.
  * Schede popup con immagini, categoria e la **spiegazione della funzione sociale** per la comunità.

---

## Sviluppo Locale e Deployment

### 1. Clona il repository e installa le dipendenze
```bash
git clone [https://github.com/dclfbk/povocivichub.git](https://github.com/dclfbk/povocivichub.git)
cd povocivichub
npm install
