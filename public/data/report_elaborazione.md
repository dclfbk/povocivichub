# Report di Elaborazione — Povo Civic Hub

_Generato automaticamente da `python_pipeline/build_data.py`._

## 1. Copertura dei PoI

- PoI grezzi nel file locale (Circoscrizione di Povo): **41**
- Duplicati esatti rimossi dal dataset locale: **0**
- PoI locali dopo la deduplica interna: **41**
- PoI estratti da OpenStreetMap: **335**
- Corrispondenze locale ↔ OSM fuse: **31** (di cui **30** per `osm_id` esatto, **1** per prossimità <= 25m + similarità nome > 80%)
- PoI solo locali (nessun corrispondente OSM): **10**
- PoI solo OSM (nessun corrispondente locale): **304**
- PoI iniettati manualmente (assenti da OSM e dal dataset locale): **1**
- Impianti sportivi ad accesso privato rimossi (non solo esclusi dagli indicatori, eliminati dal dataset): **0**
- **Totale PoI finali nel dataset unificato: 346**

## 2. Arricchimento Dati (Wikidata)

- PoI con tag `wikidata` verificati: **17**
- Foto recuperate automaticamente: **15**
- Siti web recuperati automaticamente: **0**
- _Nota: l'arricchimento è limitato ai PoI con tag `wikidata` OSM espliciti. Una ricerca per prossimità geografica su Wikidata/Commons per tutti i PoI non è stata implementata: sarebbe troppo lenta e poco affidabile (falsi positivi) per una pipeline eseguita ripetutamente._

## 2b. Verifica Immagini

- PoI con `image_url` verificati: **59**
- Link non raggiungibili (ripuliti, il frontend mostra un placeholder): **8**

## 3. Qualità del Dato

- `orari_apertura` compilato: **50 / 346**
- `contatti` compilato: **40 / 346**
- `image_url` compilato: **51 / 346**
- `accessibilita_disabili` compilato: **41 / 346**

## 4. Indice di Classe Civica (ICC) medio per categoria

| Categoria | W_cat | ICC medio | N. PoI |
|---|---|---|---|
| cross_civic | 1.0 | 72.8 | 63 |
| residenti | 0.8 | 63.7 | 102 |
| occasionali | 0.6 | 40.6 | 118 |
| pendolari | 0.4 | 48.5 | 63 |

## 5. Anomalie Rilevate

- Nessun PoI privo di coordinate valide.
- Il file locale conteneva 41 feature per sole 41 entità reali (ogni PoI era duplicato esattamente 2 volte nell'export sorgente, con proprietà identiche); tra i duplicati, alcuni presentavano coordinate leggermente diverse tra le due copie (fino a ~400m in un caso, 'Pizza Rio') — è stata mantenuta la prima occorrenza.
- Il PoI manuale "Mercato Zonale del Martedì" (iniettato a mano in una versione precedente della pipeline) è stato rimosso: il dataset locale fornisce ora un "Mercato Settimanale" più accurato e autorevole (martedì/mercoledì/sabato mattina).
