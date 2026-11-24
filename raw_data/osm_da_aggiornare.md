# OSM: cosa aggiornare per la mappatura di Povo

Lista di lavoro nata dall'incrocio tra la tabella PDF della Circoscrizione, la loro Google My Maps e OpenStreetMap (ottobre 2026).
Il raccordo voce per voce è in `raw_data/mappatura_povo.csv`. L'esito di ogni voce, con il suo `osm_id`, è nella sezione 1b di `public/data/report_elaborazione.md`.

Quando un oggetto viene aggiunto o corretto in OSM:

1. inserire il suo `osm_id` nella riga corrispondente del CSV;
2. scrivere `osm` nella colonna `coordinate` per prendere la posizione da OSM;
3. rieseguire `update_data.sh`.

## Oggetti esistenti con tag incompleti

- [ ] **Fontana dei Gai**, node/392387223: è `place=locality` + `name`, cioè il toponimo della località, non la fontana. Lasciarlo com'è e mappare la fontana come nodo a sé, nel punto esatto: `amenity=fountain` (o `amenity=drinking_water` se l'acqua è potabile, `natural=spring` se è una sorgente) + `name=Fontana dei Gai`. Poi aggiornare l'`osm_id` nel CSV. Per ora l'app usa la posizione del toponimo.
- [ ] **Casa Sociale**, way/78363071 (via Salè 1): aggiungere `name=Casa Sociale`.
- [ ] **Cappelle senza `name`.** Hanno già il tag `wikidata`, da cui l'app prende nome e foto. In OSM manca solo `name`; valutare anche `amenity=place_of_worship`.
  - [ ] way/189295439: `name=Cappella di San Francesco d'Assisi` (Wikidata Q100429600), via Villa Maria, accanto a Villa Graffer. Chiedere alla Circoscrizione se è la "Cappella ex Salvadori, Moggioli, Graffer – privata" del PDF; se privata, `access=private`.
  - [ ] way/1070388839: `name=Cappella della Beata Maria Vergine` (Wikidata Q111472699), Graffiano. Chiedere se è la "Cappella Manci – Graffiano" del PDF.
  - [ ] way/189295550: `name=Cappella della Madonna della Corona` (Wikidata Q100428515), via Villa Maria / via Madonna della Corona. Confermata.
- [ ] **Samont Drink & Food** al Passo del Cimirlo. way/1544654075 è oggi `amenity=shelter` + `building=yes`. Se è il chiosco, ritaggarlo `amenity=bar` (o `cafe`) e aggiungere `name=Samont Drink & Food`.
- [ ] **Giardino Borino**, way/548143655: oggi è solo `landuse=recreation_ground`. Valutare di aggiungere `leisure=park`.
- [ ] **Parchi senza nome:**
  - [ ] relation/6205272: Giardino Villa Cavagna.
  - [ ] relation/21068294: "Parco giochi e area verde via dei Rivi" (collinetta con cedri e betulle e anfiteatro, tra chiesa e cimitero): aggiungere `name`. Il parco giochi al suo interno, node/4970067463, è il "Parco giochi della Giraffa" (scultura ricavata da un faggio secolare, il Dolomiti 2017): aggiungere `name` anche lì.

- [ ] **Spiaz de le Patate, cartello SAT doppio.** node/424308123 (con `destination`) e node/10868054076 (con `operator=SAT`) sono lo stesso cartello a 8 m di distanza. Unirli in node/424308123, aggiungendo `operator=SAT`, e cancellare node/10868054076.
- [ ] **Fermata Povo / "Centro Civico" doppia.** Il GTFS di Trentino Trasporti ha due fermate (25010z, 25010x), che corrispondono a node/365500545 e node/365500546. La way/820475800 (`public_transport=platform`, 2020) è un terzo marciapiede senza riscontro nel GTFS: verificare sul posto ed eventualmente unirla a uno dei due nodi.

- [ ] **Fontana di Graffiano (antico lavatoio)**, node/676769466: oggi è solo `amenity=fountain`. Aggiungere `name=Fontana di Graffiano` e, se è il lavatoio, `historic=lavoir` (come il "Lavatoio pubblico" di Gabbiolo, node/430764605). Il nome in mappa oggi arriva dal foglio della Circoscrizione (riga 532).
- [ ] **Sentiero 100 scalini**, way/164887380 (gradini in galleria): ha `fixme=Non preciso, misurare punto di arrivo del tunnel`. Sul posto: rilevare l'uscita in alto della galleria e, se possibile, aggiungere `step_count=100`. L'app usa come partenza node/1764960513 (imbocco in basso).

## Oggetti da aggiungere

- [ ] **Centro Civico di Povo** (via Don T. Dallafior 5): edificio con `amenity=community_centre` e `name`. Oggi c'è solo il nodo della biblioteca (node/3292585477). Al suo interno, come nodi:
  - [ ] Sala video "Sergio Nichelatti"
  - [ ] Sala Multiuso 2
  - [ ] Sala del silenzio e della meditazione
  - [ ] Bookcrossing (`amenity=public_bookcase`)
  - [ ] sede del Patto di collaborazione "Memoria di Comunità"
- [ ] **Sale della Casa Sociale:** Sala Living + Cucina + Prato, Sala Musica, Salone Agorà.
- [ ] **Spazi APSP Margherita Grazioli**, dentro way/37393912 o nel Centro Polifunzionale way/161758820: vasca terapeutica, palestra, sale.
- [ ] **Palestra CTG Povo**: `leisure=sports_hall`, `name`.
- [ ] **Panificio Pittalis Loredana** (Salè): `shop=bakery`.
- [ ] **Api e Terre di Giuseppe Barbareschi** (Maso Bianca): `shop=greengrocer` oppure `shop=farm`.
- [ ] **Stoi del Chegul**: oggi in OSM c'è solo il pannello informativo node/392388064. Mappare gli Stoi stessi, per esempio con `historic=ruins` o `military=bunker`.
- [ ] **Aree picnic** (`tourism=picnic_site`), alle posizioni della My Maps:
  - [ ] Area picnic adiacente al Centro civico
  - [ ] Area picnic Dosso Sant'Agata
  - [ ] Area picnic Forte Roncogno
  - [ ] Parco e zona picnic area calisthenics
  - [ ] le due "Area picnic" generiche (vicino al parco tra chiesa e cimitero, e vicino al parco giochi di via Salè/Dallafior)
  - [ ] Grill park attrezzato Pra Marquart. A circa 60 m ci sono già `amenity=bbq` (node/13116979357) e `tourism=picnic_site` (node/6502872580): verificare se sono lo stesso posto.
- [ ] **Giardino delle Orsoline** (ex Villa Thun, piazza Manci 15): `leisure=garden`. La sequoia monumentale è già mappata (node/13018724186).
- [ ] **Campo comunale di Gabbiolo**: verificare se coincide con uno dei campi del Centro Sportivo Ceschi. Il più vicino è way/39120308, a 26 m.
- [ ] **Sedi delle associazioni** (`office=association`):
  - [ ] ACLI Povo: piazza Manci 5 (fonte: aclitrentine.it)
  - [ ] le altre, una volta che la Circoscrizione conferma l'indirizzo

## Da verificare sul posto

- [ ] "Punto grigliate" e "Area picnic strada per Maranza" puntano vicino alla stessa area picnic OSM (node/863821782): forse sono lo stesso posto.
- [ ] Il campo da calcio di Cimirlo è stato collegato a way/387218985, a 74 m dal segnaposto My Maps: confermare.

## Ancora senza posizione (da chiedere alla Circoscrizione)

- Associazioni senza sede trovata: AVIS, ARCI Paho, Comitato Gemellaggio Znojmo, GSA Povo, G.S. Marzola, Coro Voci in Accordo, Artici – Le Ali della Coccinella, Karamoja Group (le fonti lo legano ad Ala), Raise Hope ODV, Banca del Tempo Etico, Siamo il Salento, Povo Sonica.
- Palestra GSA, Piscina Moggioli.
- Car sharing: nessuna postazione entro la circoscrizione.
- Piste ciclabili: sono tracciati, non punti.
