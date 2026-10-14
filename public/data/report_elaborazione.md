# Report di Elaborazione — Povo Civic Hub

_Generato automaticamente da `python_pipeline/build_data.py`._

## 1. Copertura dei PoI

- PoI grezzi nel file locale (Circoscrizione di Povo): **41**
- Duplicati esatti rimossi dal dataset locale: **0**
- PoI locali dopo la deduplica interna: **41**
- PoI estratti da OpenStreetMap: **465**
- Corrispondenze locale ↔ OSM fuse: **31** (di cui **30** per `osm_id` esatto, **1** per prossimità <= 25m + similarità nome > 80%)
- PoI solo locali (nessun corrispondente OSM): **10**
- PoI solo OSM (nessun corrispondente locale): **434**
- PoI iniettati manualmente (assenti da OSM e dal dataset locale): **0**
- Impianti sportivi ad accesso privato rimossi (non solo esclusi dagli indicatori, eliminati dal dataset): **0**
- **Totale PoI finali nel dataset unificato: 530**

## 1b. Mappatura servizi della Circoscrizione (PDF + Google My Maps)

- Voci in `raw_data/mappatura_povo.csv`: **158** -> **86** unite a PoI esistenti, **55** nuovi PoI, **17** senza posizione
- Foto importate dalla My Maps: **61**
- Allineamento OSM: le voci con `osm_id` vuoto non hanno (ancora) un corrispondente in OpenStreetMap.

| Gruppo | N. | Nome | Posizione | osm_id | Esito | Note |
|---|---|---|---|---|---|---|
| Cultura e tempo libero | 1 | Sala Living + Cucina + Prato - Casa Sociale | My Maps |  | nuovo PoI (assente in OSM) |  |
| Cultura e tempo libero | 2 | Sala Musica - Casa Sociale | My Maps |  | nuovo PoI (assente in OSM) |  |
| Cultura e tempo libero | 3 | Salone Agorà - Casa Sociale | My Maps |  | nuovo PoI (assente in OSM) |  |
| Cultura e tempo libero | 4 | Sala Video Nichelatti presso Centro Civico | My Maps |  | unito a PoI esistente (nome 86%) |  |
| Cultura e tempo libero | 5 | Sala Multiuso 2 presso Centro Civico | My Maps |  | unito a PoI esistente (nome 100%) |  |
| Cultura e tempo libero | 6 | Biblioteca Comunale di Trento - Sede di Povo | My Maps | node/3292585477 | unito a PoI esistente (nome 100%) |  |
| Cultura e tempo libero | 7 | Bookcrossing c/o Centro Civico | My Maps |  | unito a PoI esistente (nome 100%) |  |
| Cultura e tempo libero | 8 | Bookcrossing al Parco del Salè | My Maps |  | unito a PoI esistente (nome 100%) |  |
| Cultura e tempo libero | 9 | Anfiteatro all'aperto / Arena | My Maps | way/1535651765 | unito a PoI esistente (nome 100%) |  |
| Cultura e tempo libero | 10 | Teatro Concordia | My Maps | node/1999372436 | unito a PoI esistente (osm_id) |  |
| Cultura e tempo libero | 11 | Patto di collaborazione "Memoria di Comunità" | My Maps |  | nuovo PoI (assente in OSM) |  |
| Cultura e tempo libero | 12 | Casa Sociale - sede patto di coesione territoriale "Povo Educa" | OSM | way/78363071 | unito a PoI esistente (osm_id) | da My Maps (non nel PDF); posizione: edificio Casa Sociale in OSM |
| Cultura e tempo libero | 13 | Sala del silenzio e della meditazione presso il Centro Civico | My Maps |  | nuovo PoI (assente in OSM) | da My Maps (non nel PDF); assente in OSM: posizione My Maps |
| Aree sportive | 1 | Palestra Povo - Marzola | My Maps | way/78363353 | unito a PoI esistente (nome 100%) |  |
| Aree sportive | 2 | Centro Sportivo Oscar Ceschi - Gabbiolo | My Maps | way/24876852 | unito a PoI esistente (nome 75%) |  |
| Aree sportive | 3 | Parco con attrezzature da calisthenics | My Maps | node/13192595456 | unito a PoI esistente (stesso tipo, 3m) |  |
| Aree sportive | 4 | Campo da basket di Oltrecastello | My Maps | way/393277793 | unito a PoI esistente (nome 100%) |  |
| Aree sportive | 5 | Campo da calcio - Oltrecastello | My Maps | way/393277791 | unito a PoI esistente (nome 100%) |  |
| Aree sportive | 6 | Tavolo da ping pong - Oltrecastello | My Maps | node/5535628392 | unito a PoI esistente (nome 75%) |  |
| Aree sportive | 7 | Campo da volley - Oltrecastello | My Maps | way/393277792 | unito a PoI esistente (stesso tipo, 2m) |  |
| Aree sportive | 8 | Campo comunale di Gabbiolo | My Maps |  | nuovo PoI (assente in OSM) |  |
| Aree sportive | 9 | Campo da calcio - Oratorio di Povo | My Maps | way/78363186 | unito a PoI esistente (nome 93%) |  |
| Aree sportive | 10 | Palestra GSA |  |  | non localizzato | posizione sconosciuta: assente in My Maps e OSM |
| Aree sportive | 11 | Campo da calcio - Cimirlo | My Maps | way/387218985 | unito a PoI esistente (osm_id) | allineato a OSM leisure=pitch sport=soccer (74 m dal segnaposto My Maps) - da confermare |
| Aree sportive | 12 | Falesie di Celva - Palestra di roccia | My Maps | way/421826836 | unito a PoI esistente (nome 100%) |  |
| Aree sportive | 13 | Tavolo da ping pong - Giardini Villa Cavagna | My Maps | node/9162334469 | unito a PoI esistente (nome 75%) |  |
| Aree sportive | 14 | Piscina Moggioli |  |  | non localizzato | posizione sconosciuta: assente in My Maps e OSM |
| Aree sportive | 15 | Palestra CTG Povo | My Maps |  | nuovo PoI (assente in OSM) | da My Maps (non nel PDF); assente in OSM: posizione My Maps |
| Aree sportive | 16 | Campo da bocce Stoi del Chegul | OSM | node/5984876678 | unito a PoI esistente (osm_id) | da My Maps (non nel PDF); posizione: OSM leisure=pitch sport=boules (il segnaposto My Maps era a ~140 m) |
| Ristorazione e agriturismi | 1 | Pizza Rio | My Maps | node/289227941 | unito a PoI esistente (nome 100%) |  |
| Ristorazione e agriturismi | 2 | Orostube | My Maps | node/288938675 | unito a PoI esistente (nome 100%) |  |
| Ristorazione e agriturismi | 3 | Gelateria Dolomeis Povo | My Maps | way/823542138 | unito a PoI esistente (nome 100%) |  |
| Ristorazione e agriturismi | 4 | Pane... e non solo! | My Maps | node/4725510687 | unito a PoI esistente (nome 100%) |  |
| Ristorazione e agriturismi | 5 | Bar Caffè Osteria Canton | My Maps | node/1620451932 | unito a PoI esistente (nome 84%) |  |
| Ristorazione e agriturismi | 6 | Bar in Centro | My Maps | way/78363327 | unito a PoI esistente (nome 100%) |  |
| Ristorazione e agriturismi | 7 | Ristorante La Botte | My Maps | node/289225782 | unito a PoI esistente (nome 100%) |  |
| Ristorazione e agriturismi | 8 | Ristorante La Cantina | My Maps | node/13320027801 | unito a PoI esistente (nome 100%) |  |
| Ristorazione e agriturismi | 9 | Oltrebar | My Maps | node/274232823 | unito a PoI esistente (nome 100%) |  |
| Ristorazione e agriturismi | 10 | Bar al Salè - Panificio Tabacchi | My Maps | way/1240467725 | unito a PoI esistente (nome 100%) |  |
| Ristorazione e agriturismi | 11 | Sapori di Gastronomia | My Maps | node/1620451940 | unito a PoI esistente (nome 100%) |  |
| Ristorazione e agriturismi | 12 | Samont Drink & Food | My Maps |  | nuovo PoI (assente in OSM) |  |
| Ristorazione e agriturismi | 13 | Agritur 8 Grappoli | My Maps | way/770869614 | unito a PoI esistente (nome 100%) |  |
| Ristorazione e agriturismi | 14 | Agritur Verderame | My Maps | way/562069894 | unito a PoI esistente (nome 100%) |  |
| Ristorazione e agriturismi | 15 | Agritur La Tenuta | OSM | way/783856494 | unito a PoI esistente (osm_id) | assente in My Maps: posizione da OSM |
| Ristorazione e agriturismi | 16 | Agritur Ponte Alto | My Maps | way/1162543897 | unito a PoI esistente (nome 100%) |  |
| Ristorazione e agriturismi | 17 | Panificio Pittalis Loredana | My Maps |  | nuovo PoI (assente in OSM) | da My Maps (non nel PDF); assente in OSM: posizione My Maps |
| Luoghi di interesse storico/artistico/naturalistico e fontane | 1 | Orrido di Ponte Alto | OSM | node/5680205931 | unito a PoI esistente (osm_id) | posizione OSM natural=gorge, tra il ponte romano e il Ristorante La Gnoccata |
| Luoghi di interesse storico/artistico/naturalistico e fontane | 2 | Gallerie della guerra | My Maps | node/5405518900 | nuovo PoI | allineato a OSM military=bunker "gallerie militari" |
| Luoghi di interesse storico/artistico/naturalistico e fontane | 3 | Monumento "Ai Caduti di tutte le Guerre" | My Maps | node/13990384642 | unito a PoI esistente (nome 100%) |  |
| Luoghi di interesse storico/artistico/naturalistico e fontane | 4 | Fonte storica | My Maps | node/678035999 | unito a PoI esistente (stesso tipo, 12m) |  |
| Luoghi di interesse storico/artistico/naturalistico e fontane | 5 | Fontana - Gabbiolo | My Maps | node/430764605 | nuovo PoI | allineato a OSM "Lavatoio pubblico" (amenity=fountain, historic=lavoir) |
| Luoghi di interesse storico/artistico/naturalistico e fontane | 6 | Forte Sella di Roncogno | My Maps | way/79387122 | unito a PoI esistente (nome 100%) |  |
| Luoghi di interesse storico/artistico/naturalistico e fontane | 7 | Fontana di Piazza Manci | My Maps | node/556932263 | unito a PoI esistente (nome 100%) |  |
| Luoghi di interesse storico/artistico/naturalistico e fontane | 8 | Lapide commemorativa di Giannantonio Manci | My Maps | node/13990737741 | unito a PoI esistente (nome 100%) |  |
| Luoghi di interesse storico/artistico/naturalistico e fontane | 9 | Fontana di via Madonnina | My Maps | node/279462074 | unito a PoI esistente (nome 100%) |  |
| Luoghi di interesse storico/artistico/naturalistico e fontane | 10 | Giardino Orsoline | manuale |  | nuovo PoI (assente in OSM) | parco dell'ex Villa Thun (Istituto delle Orsoline), piazza Manci 15 - posizione della sequoia, approssimata per il giardino |
| Luoghi di interesse storico/artistico/naturalistico e fontane | 11 | Albero monumentale Giardino Orsoline - Sequoia gigante | OSM | node/13018724186 | nuovo PoI | OSM natural=tree, denotation=natural_monument, Sequoiadendron giganteum; albero monumentale del Comune di Trento |
| Luoghi di interesse storico/artistico/naturalistico e fontane | 12 | Villa Gherta | My Maps | way/78363234 | nuovo PoI | allineato a OSM historic=manor, access=private |
| Luoghi di interesse storico/artistico/naturalistico e fontane | 13 | "Sason" - Masso erratico | OSM | way/692657294 | nuovo PoI | assente in My Maps: posizione da OSM (natural=stone "El Sason") |
| Luoghi di interesse storico/artistico/naturalistico e fontane | 14 | Stoi de Chegul | OSM | node/392388064 | unito a PoI esistente (osm_id) | da My Maps (non nel PDF); posizione: pannello OSM "Stoi del Chegul" (gli Stoi non sono mappati in OSM); sostituisce il vecchio PoI manuale |
| Luoghi di interesse storico/artistico/naturalistico e fontane | 15 | Fontana dei Gai | OSM | node/392387223 | nuovo PoI | da My Maps (non nel PDF); nella My Maps sta in "Cultura": spostata tra le fontane; il nodo OSM ha solo il nome |
| Luoghi di interesse storico/artistico/naturalistico e fontane | 16 | Ponte Alto - ponte romano | OSM | way/1202532377 | nuovo PoI | da My Maps (non nel PDF, era in "Ristorazione"): è il ponte romano al confine, vicino al Ristorante La Gnoccata; posizione OSM man_made=bridge |
| Servizi e attività economiche | 1 | Vigili del Fuoco Volontari | OSM | way/1266800064 | unito a PoI esistente (osm_id) | assente in My Maps: posizione da OSM |
| Servizi e attività economiche | 2 | A.P.S.P. Margherita Grazioli - Casa Melograno - Centro Servizi | My Maps | way/161758820 | unito a PoI esistente (nome 93%) |  |
| Servizi e attività economiche | 3 | Punto prelievi | My Maps | node/5621650716 | unito a PoI esistente (nome 100%) |  |
| Servizi e attività economiche | 4 | Ufficio postale | My Maps | node/258015066 | unito a PoI esistente (nome 100%) |  |
| Servizi e attività economiche | 5 | Farmacia comunale di Povo | My Maps | node/288917447 | unito a PoI esistente (nome 100%) |  |
| Servizi e attività economiche | 6 | Famiglia Cooperativa - Supermercato Piazza Manci | My Maps | node/288911508 | unito a PoI esistente (nome 83%) |  |
| Servizi e attività economiche | 7 | Famiglia Cooperativa - Supermercato Sprè | My Maps | node/556978697 | unito a PoI esistente (nome 89%) |  |
| Servizi e attività economiche | 8 | Mercatino del riuso | My Maps |  | unito a PoI esistente (nome 100%) |  |
| Servizi e attività economiche | 9 | Tabaccheria | My Maps | node/289227507 | nuovo PoI | allineato a OSM shop=newsagent "Giornali Tabacchi" |
| Servizi e attività economiche | 10 | Banca per il Trentino Alto Adige | My Maps | node/288910331 | unito a PoI esistente (nome 100%) |  |
| Servizi e attività economiche | 11 | CRM Povo | My Maps | way/36868904 | unito a PoI esistente (nome 100%) |  |
| Servizi e attività economiche | 12 | Api e Terre di Giuseppe Barbareschi - Frutta e verdura | My Maps |  | nuovo PoI (assente in OSM) |  |
| Servizi e attività economiche | 13 | Mercato di Piazza Manci del mercoledì e del sabato | My Maps |  | unito a PoI esistente (nome 54% a 7m) |  |
| Servizi e attività economiche | 14 | AB Cartocopisteria S.a.s. | My Maps | node/4179376123 | unito a PoI esistente (nome 100%) |  |
| Servizi e attività economiche | 15 | Autodelta di Zordan Romeo | My Maps | node/556932210 | unito a PoI esistente (nome 85%) |  |
| Servizi e attività economiche | 16 | Estetica Mia | My Maps | node/13990921963 | unito a PoI esistente (nome 100%) |  |
| Servizi e attività economiche | 17 | Cabina per fototessere | My Maps | node/13990998128 | unito a PoI esistente (nome 100%) |  |
| Servizi e attività economiche | 18 | Scuola dell'infanzia M. Conotter | OSM | way/189295614 | unito a PoI esistente (osm_id) | assente in My Maps: posizione da OSM |
| Servizi e attività economiche | 19 | Scuola dell'infanzia A. Lorenzini | OSM | way/78362954 | unito a PoI esistente (osm_id) | assente in My Maps: posizione da OSM |
| Servizi e attività economiche | 20 | Scuola primaria U. Moggioli di Povo | OSM | way/180406222 | unito a PoI esistente (osm_id) | assente in My Maps: posizione da OSM |
| Servizi e attività economiche | 21 | DAE - Defibrillatore | My Maps | node/11855466596 | nuovo PoI |  |
| Servizi e attività economiche | 22 | Vasca terapeutica presso APSP M. Grazioli | My Maps |  | nuovo PoI (assente in OSM) | da My Maps (non nel PDF); spazio interno alla struttura APSP: PoI separato; assente in OSM: posizione My Maps |
| Servizi e attività economiche | 23 | Palestra presso APSP M. Grazioli | My Maps |  | nuovo PoI (assente in OSM) | da My Maps (non nel PDF); spazio interno alla struttura APSP: PoI separato; assente in OSM: posizione My Maps |
| Servizi e attività economiche | 24 | Sale presso APSP M. Grazioli | My Maps |  | nuovo PoI (assente in OSM) | da My Maps (non nel PDF); spazio interno alla struttura APSP: PoI separato; assente in OSM: posizione My Maps |
| Luoghi di culto | 1 | Chiesa parrocchiale dei Santi Pietro e Andrea - Povo Pantè | My Maps | way/78363100 | unito a PoI esistente (nome 100%) |  |
| Luoghi di culto | 2 | Chiesetta di Sant'Agata e Santa Lucia - Doss Sant'Agata (in ristrutturazione) | My Maps | way/592790203 | unito a PoI esistente (osm_id) |  |
| Luoghi di culto | 3 | Chiesetta di San Francesco d'Assisi - Gabbiolo | My Maps | way/295079478 | unito a PoI esistente (nome 100%) |  |
| Luoghi di culto | 4 | Chiesetta dei Santi Rocco e Sebastiano - Gabbiolo | OSM | way/818875812 | unito a PoI esistente (osm_id) | assente in My Maps: posizione da OSM |
| Luoghi di culto | 5 | Chiesetta di San Pantaleone - Oltrecastello | My Maps | way/421817095 | unito a PoI esistente (nome 100%) |  |
| Luoghi di culto | 6 | Chiesa del Cuore Immacolato di Maria - Oltrecastello | My Maps | way/79384257 | unito a PoI esistente (nome 100%) |  |
| Luoghi di culto | 7 | Chiesetta di Sant'Antonio da Padova - Celva | My Maps | way/79386950 | unito a PoI esistente (nome 100%) |  |
| Luoghi di culto | 8 | Chiesa di San Bernardo - Cimirlo | OSM | way/79387094 | unito a PoI esistente (osm_id) | assente in My Maps: posizione da OSM |
| Luoghi di culto | 9 | Chiesetta di San Carlo Borromeo - Oltrecastello | My Maps | way/421817093 | unito a PoI esistente (nome 100%) |  |
| Luoghi di culto | 10 | Cappella di San Francesco d'Assisi - via Villa Maria | OSM | way/189295439 | nuovo PoI | nome da Wikidata Q100429600 (tag wikidata dell'elemento OSM), foto Commons; accanto a Villa Graffer: probabilmente la "Cappella ex Salvadori, Moggioli, Graffer - privata" del PDF (n. 10), da confermare |
| Luoghi di culto | 11 | Cappella Manci - Mesiano | OSM | way/64714418 | nuovo PoI | Wikidata Q96631795 "cappella del Crocefisso", foto Commons; in OSM disused=yes |
| Luoghi di culto | 12 | Cappella della Beata Maria Vergine - Graffiano | OSM | way/1070388839 | nuovo PoI | nome da Wikidata Q111472699 (tag wikidata dell'elemento OSM), nessuna foto; probabilmente la "Cappella Manci - Graffiano" del PDF (n. 12), da confermare |
| Luoghi di culto | 13 | Cappella della Madonna della Corona - Via Villa Maria | OSM | way/189295550 | nuovo PoI | confermata da Wikidata Q100428515 (tag wikidata dell'elemento OSM), foto Commons |
| Luoghi di culto | 14 | Cimitero di Povo | My Maps | way/38960039 | nuovo PoI | allineato a OSM landuse=cemetery "Cimitero Comunale di Povo" |
| Luoghi di culto | 15 | Crocifisso di via Gabbiolo | OSM | node/1999373684 | nuovo PoI | da My Maps (non nel PDF); posizione: OSM historic=wayside_cross |
| Associazioni e gruppi | 1 | ACLI Povo | manuale |  | nuovo PoI (assente in OSM) | sede: piazza Manci 5 (aclitrentine.it) |
| Associazioni e gruppi | 2 | ANA Povo-Villazzano | manuale |  | nuovo PoI (assente in OSM) | luogo di attività: Baita ANA in località Moronar (l'Adige 2018) - posizione della località, approssimata |
| Associazioni e gruppi | 3 | AVIS Povo |  |  | non localizzato | senza sede sulla mappa |
| Associazioni e gruppi | 4 | Circolo ARCI Paho |  |  | non localizzato | senza sede sulla mappa |
| Associazioni e gruppi | 5 | Circolo Oratorio Concordia | manuale |  | nuovo PoI (assente in OSM) | luogo di attività: Oratorio di Povo (eventi TuttaPovo) |
| Associazioni e gruppi | 6 | Circolo Culturale Pensionati ed Anziani | manuale |  | nuovo PoI (assente in OSM) | sede: "Circolo Pensionati di Povo, piazza Manci" (eventi TuttaPovo) - civico non noto, posizione approssimata |
| Associazioni e gruppi | 7 | Pro Loco Oltrecastello | manuale |  | nuovo PoI (assente in OSM) | luogo di attività: parco e piazza di Oltrecastello (eventi TuttaPovo) |
| Associazioni e gruppi | 8 | Comitato Gemellaggio Znojmo |  |  | non localizzato | senza sede sulla mappa |
| Associazioni e gruppi | 9 | CTG Povo | My Maps |  | nuovo PoI (assente in OSM) | luogo di attività: Palestra CTG (My Maps) |
| Associazioni e gruppi | 10 | Filodrammatica Concordia 74 | manuale |  | nuovo PoI (assente in OSM) | luogo di attività: Teatro Concordia (eventi TuttaPovo) |
| Associazioni e gruppi | 11 | GLOW | manuale |  | nuovo PoI (assente in OSM) | luogo di attività: Casa Sociale, via Salè 1 (eventi TuttaPovo) |
| Associazioni e gruppi | 12 | GSA Povo |  |  | non localizzato | senza sede sulla mappa |
| Associazioni e gruppi | 13 | G.S. Marzola |  |  | non localizzato | senza sede sulla mappa |
| Associazioni e gruppi | 14 | SAT Sezione di Povo | OSM | node/11676194235 | unito a PoI esistente (osm_id) | sede: piazzale Carlo Merler 2 (OSM) |
| Associazioni e gruppi | 15 | U.S.D. ViPo Trento | manuale |  | nuovo PoI (assente in OSM) | luogo di attività: campo ViPo al Centro Sportivo Ceschi (My Maps) |
| Associazioni e gruppi | 16 | Coro Voci in Accordo |  |  | non localizzato | senza sede sulla mappa |
| Associazioni e gruppi | 17 | Club Interassociativo TuttaPovo | OSM | node/14049910025 | unito a PoI esistente (osm_id) | sede (OSM) |
| Associazioni e gruppi | 18 | Artici - Le Ali della Coccinella |  |  | non localizzato | senza sede sulla mappa |
| Associazioni e gruppi | 19 | Karamoja Group |  |  | non localizzato | senza sede sulla mappa |
| Associazioni e gruppi | 20 | Kazoo (Circolo Open) | OSM | node/279462366 | unito a PoI esistente (osm_id) | sede: via Madonnina 1, Circolo Open (OSM) |
| Associazioni e gruppi | 21 | Raise Hope ODV |  |  | non localizzato | senza sede sulla mappa |
| Associazioni e gruppi | 22 | Vigili del Fuoco Volontari |  |  | non localizzato | stessa sede di Servizi n.1 (caserma VVF): non duplicata sulla mappa |
| Associazioni e gruppi | 23 | Kaleidoscopio s.c.s. | OSM | node/13990899418 | unito a PoI esistente (osm_id) | sede (OSM); eventi TuttaPovo: Spazio Aperto via Dallafior 2 |
| Associazioni e gruppi | 24 | Banca del Tempo Etico |  |  | non localizzato | senza sede sulla mappa |
| Associazioni e gruppi | 25 | Siamo il Salento |  |  | non localizzato | senza sede sulla mappa |
| Associazioni e gruppi | 26 | Povo Sonica |  |  | non localizzato | senza sede sulla mappa |
| Parchi e aree picnic | 1 | Parco giochi Villa Cavagna | My Maps | node/4179375532 | unito a PoI esistente (nome 100%) |  |
| Parchi e aree picnic | 2 | Parco giochi e area verde tra via Salè e via Dallafior | My Maps | way/119405069 | unito a PoI esistente (nome 100%) |  |
| Parchi e aree picnic | 3 | Area giochi nuovo parco al Salè | My Maps | node/9160222544 | unito a PoI esistente (nome 100%) |  |
| Parchi e aree picnic | 4 | Parco giochi di Graffiano | My Maps | node/361378960 | unito a PoI esistente (nome 100%) |  |
| Parchi e aree picnic | 5 | Parco giochi e area verde via dei Rivi | OSM | relation/21068294 | unito a PoI esistente (osm_id) | area verde con collinetta e anfiteatro (descrizione My Maps) = OSM leisure=park relation/21068294; il parco giochi al suo interno è la "Giraffa" (n. 8) |
| Parchi e aree picnic | 6 | Parco giochi - Giardino Oltrecastello | My Maps | node/678066076 | unito a PoI esistente (nome 100%) |  |
| Parchi e aree picnic | 7 | Altalene e giochi vecchio parco al Salè | My Maps | node/12707150392 | unito a PoI esistente (nome 100%) |  |
| Parchi e aree picnic | 8 | Parco giochi "della Giraffa" - Piazza Manci | OSM | node/4970067463 | unito a PoI esistente (osm_id) | parco giochi OSM node/4970067463 (conferma utente): tra la chiesa e il cimitero, scultura "giraffaggia" (il Dolomiti 2017), gestito dalla Cooperativa Il Gabbiano |
| Parchi e aree picnic | 9 | Parco via Brenz - Borino | OSM | way/548143655 | nuovo PoI | "Giardino Borino" in OSM (landuse=recreation_ground) |
| Parchi e aree picnic | 10 | Area picnic adiacente al Centro civico | My Maps |  | nuovo PoI (assente in OSM) | da My Maps (non nel PDF) |
| Parchi e aree picnic | 11 | Area picnic | My Maps |  | nuovo PoI (assente in OSM) | da My Maps (non nel PDF) |
| Parchi e aree picnic | 12 | Area picnic strada per Maranza - punto grigliate | My Maps | node/863821782 | unito a PoI esistente (nome 100%) | da My Maps (non nel PDF); stesso posto del segnaposto My Maps "Punto grigliate" (conferma utente) |
| Parchi e aree picnic | 13 | Area picnic Dosso Sant'Agata | My Maps |  | nuovo PoI (assente in OSM) | da My Maps (non nel PDF) |
| Parchi e aree picnic | 14 | Grill park attrezzato Pra Marquart | My Maps |  | nuovo PoI (assente in OSM) | da My Maps (non nel PDF) |
| Parchi e aree picnic | 15 | Parco di Cimirlo | My Maps | way/65728799 | unito a PoI esistente (nome 100%) | da My Maps (non nel PDF) |
| Parchi e aree picnic | 16 | Panchine - Giardino Villa Cavagna | My Maps |  | nuovo PoI (assente in OSM) | da My Maps (non nel PDF) |
| Parchi e aree picnic | 17 | Area picnic e sosta al Parco al Salè | My Maps | way/820475798 | unito a PoI esistente (nome 73%) | da My Maps (non nel PDF) |
| Parchi e aree picnic | 18 | Area picnic | My Maps |  | nuovo PoI (assente in OSM) | da My Maps (non nel PDF) |
| Parchi e aree picnic | 19 | Area picnic Forte Roncogno | My Maps |  | nuovo PoI (assente in OSM) | da My Maps (non nel PDF) |
| Parchi e aree picnic | 20 | Parco e zona picnic area calisthenics | My Maps |  | nuovo PoI (assente in OSM) | da My Maps (non nel PDF) |
| Percorsi escursionistici | 1 | Passeggiata sul Dos Sant'Agata - Salita Sant'Agata | My Maps | node/10081546979 | nuovo PoI | allineato a OSM: cartello escursionistico alla partenza |
| Percorsi escursionistici | 2 | Passeggiata sul Dos Sant'Agata - Salita Santa Lucia | My Maps |  | nuovo PoI (assente in OSM) |  |
| Percorsi escursionistici | 3 | Passeggiata sul Dos Sant'Agata - Salita da Oltrecastello | OSM | node/8977889118 | nuovo PoI | estremità lato Oltrecastello del Sentiero Sant'Agata (OSM relation/14666008) |
| Percorsi escursionistici | 4 | Passo Cimirlo ed escursioni sulle pendici della Marzola | My Maps | node/274232982 | nuovo PoI | allineato a OSM natural=saddle "Passo del Cimirlo" |
| Percorsi escursionistici | 5 | Monte Celva ed il sentiero dei cento scalini | My Maps |  | nuovo PoI (assente in OSM) |  |
| Percorsi escursionistici | 6 | Sentiero attrezzato G. Bertotti | OSM | node/10868054072 | nuovo PoI | da My Maps (non nel PDF); partenza località Piani = cartello OSM "Piani" (il segnaposto My Maps era a 544 m) |
| Percorsi escursionistici | 7 | Sentieri n. 455 e 456 (Sentiero del 50°) | OSM | node/274232982 | nuovo PoI | da My Maps (non nel PDF); partenza Passo del Cimirlo (OSM natural=saddle); tracciati SAT 455 = relation/7186805, 456 = relation/7184935 |
| Mobilità | 1 | Piste ciclabili |  |  | non localizzato | tracciati lineari: non rappresentabili come punto |
| Mobilità | 2 | Stazione Trento - Povo Mesiano | OSM | node/4922948640 | unito a PoI esistente (osm_id) | assente in My Maps: posizione da OSM |
| Mobilità | 3 | Colonnina di ricarica elettrica - Piazza Manci | OSM | node/13989631523 | nuovo PoI | assente in My Maps: posizione da OSM |
| Mobilità | 4 | Car sharing |  |  | non localizzato | nessuna postazione in OSM entro la circoscrizione |

## 2. Arricchimento Dati (Wikidata)

- PoI con tag `wikidata` verificati: **25**
- Foto recuperate automaticamente: **19**
- Siti web recuperati automaticamente: **0**
- _Nota: l'arricchimento è limitato ai PoI con tag `wikidata` OSM espliciti. Una ricerca per prossimità geografica su Wikidata/Commons per tutti i PoI non è stata implementata: sarebbe troppo lenta e poco affidabile (falsi positivi) per una pipeline eseguita ripetutamente._

## 2b. Verifica Immagini

- PoI con `image_url` verificati: **96**
- Link non raggiungibili (ripuliti, il frontend mostra un placeholder): **0**

## 3. Qualità del Dato

- `orari_apertura` compilato: **50 / 530**
- `contatti` compilato: **40 / 530**
- `image_url` compilato: **96 / 530**
- `accessibilita_disabili` compilato: **41 / 530**

## 4. Indice di Classe Civica (ICC) medio per categoria

| Categoria | W_cat | ICC medio | N. PoI |
|---|---|---|---|
| cross_civic | 1.0 | 73.3 | 75 |
| residenti | 0.8 | 63.4 | 209 |
| occasionali | 0.6 | 42.2 | 182 |
| pendolari | 0.4 | 48.5 | 64 |

## 5. Anomalie Rilevate

- Nessun PoI privo di coordinate valide.
- Il file locale conteneva 41 feature per sole 41 entità reali (ogni PoI era duplicato esattamente 2 volte nell'export sorgente, con proprietà identiche); tra i duplicati, alcuni presentavano coordinate leggermente diverse tra le due copie (fino a ~400m in un caso, 'Pizza Rio') — è stata mantenuta la prima occorrenza.
- Il PoI manuale "Mercato Zonale del Martedì" (iniettato a mano in una versione precedente della pipeline) è stato rimosso: il dataset locale fornisce ora un "Mercato Settimanale" più accurato e autorevole (martedì/mercoledì/sabato mattina).
