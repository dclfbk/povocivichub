"""
Povo Civic Hub - Geographic Data Analysis Pipeline (ICC Edition, outdoor-sport focus)

1. ESTRAZIONE OSM AMPLIATA:
   - Downloads Nodes and Polygons (converted to centroids) via OSMnx/Overpass:
     amenity, shop, tourism, leisure, sport=* (any value, not just climbing --
     used to label sports pitches), highway=bus_stop, railway=station/halt,
     place=square, historic, office, public_transport=platform.
   - Benches and viewpoints are intentionally NOT extracted (2026-07-25
     feedback: street-furniture noise, not signal for this project's goal).
     `amenity=recycling` IS fetched, but only `recycling_type=centre` (a real
     staffed/drop-off "isola ecologica") is kept -- individual street
     recycling bins/containers are dropped as clutter (2026-07-26 feedback).
   - `amenity=parking` and off-route `tourism=information` trail signage are
     both fetched and shown on the map/table with a normal icon + popup, but
     flagged `solo_riferimento=True` (2026-07-26 feedback: "punti di cui fai
     uso e che non fanno parte del calcolo" should still be queryable) --
     they're excluded from W_cat/ICC/mix_index scoring the same way
     place_of_worship/private PoIs are (see calculate_scores_and_mixite).
     Parking is additionally used to compute a distance-to-parking
     accessibility indicator (d_parking_m, see calculate_accessibility_distances).
     `tourism=information` is flagged `solo_riferimento=False` only when it
     falls within 30m of a named trail/track way (fetch_named_hiking_routes) --
     those genuinely mark a route and count normally toward occa_score.

2. DATASET LOCALE (Circoscrizione di Povo):
   - Loads raw_data/dati_circoscrizione.geojson, drops the exact duplicate
     features present in the source export (each POI appears twice), and maps
     its Italian schema onto the pipeline's snake_case fields (indirizzo,
     orari_apertura, contatti, sito_web, accessibilita_disabili, ...).

3. DEDUPLICAZIONE E FUSIONE LOCALE <-> OSM:
   - Matches local POIs to OSM features within 25m using RapidFuzz name
     similarity (> 80%). Matches are fused (local hyper-local fields + OSM
     geometry/tags); unmatched records on either side are kept standalone.

4. ARRICCHIMENTO (Wikidata):
   - For POIs carrying an OSM `wikidata` tag with missing photo/website,
     queries the Wikidata API for P18 (image) and P856 (official website).
     Scoped to tagged features only (no geographic-proximity search: too slow
     and unreliable to run as part of a repeatable build).
   - Normalizes the OSM `opening_hours` tag into a human-readable string.
   - Sports pitches (`leisure=pitch`) get an `amenity_type` of "Campo da
     <sport>" (e.g. "Campo da pallavolo") built from the OSM `sport` tag,
     instead of the raw English word "pitch".

5. CLASSIFICAZIONE SOCIOLOGICA E INDICE DI CLASSE CIVICA (ICC):
   - 'cross_civic' (W=1.0, Oldenburg Third Places), 'residenti' (W=0.8,
     Klinenberg neighborhood infrastructure), 'occasionali' (W=0.6, outdoor/
     historic/leisure), 'pendolari' (W=0.4, academic/commuter flow hubs).
   - ICC = (0.4706*W_cat + 0.2941*A_bus + 0.2353*Q_data) * 100 -- A_bus is a
     network-distance decay factor to the nearest bus/rail stop (pedestrian
     graph, no redundant second download) and Q_data is the share of key
     fields populated. The original formula's P_park term was dropped and the
     remaining weights renormalized (parking distance is still computed as
     its own d_parking_m indicator, just no longer scored into ICC/mix_index).

6. RICALCOLO GRIGLIA H3 E MIXITE:
   - H3 resolution 10 (finer than the previous res 9, 2026-07-25 feedback).
   - Same Shannon-entropy mix_index/res_score/comm_score/occa_score as before,
     now computed over the unified, deduplicated, enriched POI set.

7. EXPORT:
   - public/data/povo_boundary.json, povo_grid.json, povo_pois.json
   - public/data/report_elaborazione.md (coverage, enrichment, ICC, anomalies)
"""

import os
import re
import math
import zipfile
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from shapely.geometry import Polygon, MultiPolygon, shape, Point
import rasterio
import h3
import networkx as nx
import osmnx as ox
import requests
from rapidfuzz import fuzz

# Paths
BOUNDARY_INPUT = "../raw_data/povo_boundary.geojson"
DTM_INPUT = "../raw_data/dtm_povo.tif"
GTFS_URBANO_INPUT = "../raw_data/google_transit_urbano_tte.zip"
GTFS_EXTRAURBANO_INPUT = "../raw_data/google_transit_extraurbano_tte.zip"
LOCAL_DATASET_INPUT = "../raw_data/dati_circoscrizione.geojson"

GRID_OUTPUT = "../public/data/povo_grid.json"
BOUNDARY_OUTPUT = "../public/data/povo_boundary.json"
POIS_OUTPUT = "../public/data/povo_pois.json"
REPORT_OUTPUT = "../public/data/report_elaborazione.md"

TARGET_CRS = "EPSG:25832"  # UTM 32N (meters)
WGS84_CRS = "EPSG:4326"

DEDUP_RADIUS_M = 25
DEDUP_NAME_THRESHOLD = 80

# Ray Oldenburg (1989), Eric Klinenberg (2018), Jane Jacobs (1961) category weights.
W_CAT = {'cross_civic': 1.0, 'residenti': 0.8, 'occasionali': 0.6, 'pendolari': 0.4}

# Sub-types that function as shared/third-place infrastructure regardless of
# which sociological category they happen to be bucketed into -- a "campo da
# calcio ad accesso pubblico lo possono usare tutti" (2026-07-25 feedback).
# This generalizes the old cross_civic-only cross-feed (park/garden/square/
# community_centre/public_bookcase/drinking_water/social_facility/
# association/ngo -- cross_civic's own sub-types) to also cover sport and
# leisure facilities that live under residenti/pendolari/occasionali but are
# just as usable by every other community: pitches, sports halls/centres,
# fitness stations, climbing crags, playgrounds, picnic sites, nature
# reserves, amphitheatres, museums, libraries.
PUBLIC_INTEREST_SUB_TYPES = {
    'park', 'garden', 'square', 'community_centre', 'public_bookcase', 'drinking_water',
    'social_facility', 'association', 'ngo',
    'pitch', 'sports_centre', 'sports_hall', 'fitness_station', 'climbing', 'playground',
    'picnic_site', 'nature_reserve', 'amphitheatre', 'museum', 'library'
}

# Icon names that represent a constructed sport facility (pitches, courts,
# sports centres) rather than an open-air natural feature like a climbing
# crag. Used to fully drop private-access ones from the dataset (2026-07-26
# feedback: "sarei per eliminarli" -- a private=access facility is even more
# restricted than a residenti-only one, since only the owner's guests can use
# it, so unlike other private PoIs (which stay on the map/table but are
# excluded from indicators, see calculate_scores_and_mixite) these shouldn't
# be shown at all). Deliberately excludes 'climbing': an outdoor crag isn't a
# constructed "impianto" in the sense the feedback meant.
SPORT_FACILITY_ICONS = {'sport', 'basketball_court', 'volleyball_court', 'tennis_court'}

# Places that hand out ready-to-eat/takeaway food: pizza al taglio, pizzerie,
# fast-food, ristoranti, bar, supermercati (2026-07-25 feedback). Used to
# gate whether a picnic area is realistically useful to pendolari on a lunch
# break -- see calculate_scores_and_mixite, where this determines
# `offre_asporto` per PoI. `shop == 'supermarket'` and the OSM `takeaway=yes`
# tag are checked separately (a supermarket sells takeaway-able food without
# being one of these amenity sub-types, and `takeaway=yes` can appear on
# other shop/amenity types this list doesn't otherwise cover).
TAKEAWAY_FOOD_SUB_TYPES = {'fast_food', 'restaurant', 'pub', 'bar', 'cafe'}

# Fields whose fill-rate makes up the ICC's Q_data (data quality) component.
KEY_QUALITY_FIELDS = ['orari_apertura', 'contatti', 'image_url', 'accessibilita_disabili']


def load_boundary():
    """Load boundary GeoJSON and return both WGS84 and projected EPSG:25832 GeoDataFrames."""
    print("--> Loading boundary from", BOUNDARY_INPUT)
    gdf_boundary = gpd.read_file(BOUNDARY_INPUT)
    if gdf_boundary.crs is None:
        gdf_boundary.set_crs(WGS84_CRS, inplace=True)

    gdf_wgs84 = gdf_boundary.to_crs(WGS84_CRS)
    gdf_utm = gdf_boundary.to_crs(TARGET_CRS)
    return gdf_wgs84, gdf_utm


def fetch_osm_graph_and_pois(gdf_wgs84):
    """Download pedestrian graph and exhaustive POIs/features from OSM."""
    print("--> Downloading pedestrian graph and massive POIs from OpenStreetMap...")
    poly_wgs84 = gdf_wgs84.geometry.union_all()

    # 1. Download pedestrian network
    G = ox.graph_from_polygon(poly_wgs84, network_type='walk')
    G_utm = ox.project_graph(G, to_crs=TARGET_CRS)
    print(f"    Pedestrian network retrieved: {len(G_utm.nodes)} nodes, {len(G_utm.edges)} edges.")

    # 2. Comprehensive POI tags. NOTE: benches and viewpoints are
    # intentionally excluded (2026-07-25 feedback): they're street-furniture
    # noise for this project's goal, not signal. `sport` is kept as its own
    # column even for `leisure=pitch` features (not just climbing) so
    # pitches can be labelled "Campo da <sport>" instead of the raw OSM word
    # "pitch". `parking` and `recycling` ARE fetched, but
    # classify_and_transform_pois flags them `solo_riferimento=True` (or, for
    # recycling, drops non-`recycling_type=centre` ones entirely) so they
    # never feed W_cat/ICC/mix_index -- see the module docstring and
    # calculate_accessibility_distances (d_parking_m).
    tags = {
        'amenity': [
            'university', 'research_institute', 'library', 'school', 'kindergarten',
            'pharmacy', 'post_office', 'townhall', 'community_centre', 'social_facility',
            'cafe', 'restaurant', 'pub', 'bar', 'canteen', 'fast_food', 'bank', 'atm',
            'public_bookcase', 'drinking_water', 'shelter', 'place_of_worship',
            'theatre', 'arts_centre', 'parking', 'recycling', 'marketplace',
            'fire_station', 'clinic', 'doctors'
        ],
        'shop': [
            'supermarket', 'bakery', 'convenience', 'butcher', 'greengrocer', 'chemist', 'books',
            'copyshop', 'beauty', 'hairdresser', 'deli'
        ],
        'tourism': [
            'information', 'picnic_site', 'alpine_hut', 'wilderness_hut',
            'guest_house', 'hotel', 'attraction', 'museum', 'artwork', 'chalet', 'camp_site'
        ],
        'leisure': ['park', 'playground', 'sports_centre', 'pitch', 'garden', 'nature_reserve', 'amphitheatre', 'sports_hall', 'fitness_station'],
        'sport': True,
        'highway': ['bus_stop'],
        'railway': ['station', 'halt'],
        'place': ['square'],
        'historic': ['fort', 'castle', 'monument', 'memorial', 'archaeological_site', 'ruins', 'trench'],
        'office': ['research', 'educational_institution', 'association', 'ngo', 'it'],
        # 'stop_position' nodes duplicate the bus_stop/platform representation of
        # the same physical stop and are routing-only infra, not shown on the map.
        'public_transport': ['platform']
    }

    try:
        raw_pois = ox.features_from_polygon(poly_wgs84, tags=tags)
        if raw_pois.crs is None:
            raw_pois.set_crs(WGS84_CRS, inplace=True)
        raw_pois_utm = raw_pois.to_crs(TARGET_CRS)
        print(f"    Raw POIs/features fetched: {len(raw_pois_utm)}")
    except Exception as e:
        print("    Warning querying POIs:", e)
        raw_pois_utm = gpd.GeoDataFrame(geometry=[], crs=TARGET_CRS)

    return G_utm, raw_pois_utm


def fetch_named_hiking_routes(gdf_wgs84):
    """
    Download named trail/track ways (highway=path/track/footway/bridleway with
    a name) and return a single buffered UTM polygon (30m) used to keep only
    the `tourism=information` signage that actually sits on a named route --
    everywhere else those points are noise (2026-07-25 feedback).

    NOTE: OSM route=hiking/running *relations* would be the more "correct"
    source, but osmnx's features_from_polygon can't resolve route relations
    into geometries in this area (returns "no matching features" even for any
    route=* at all) -- named trail/track ways are used instead, which osmnx
    fetches natively as LineStrings.
    """
    print("--> Downloading named trail/track ways (to filter trail signage)...")
    poly_wgs84 = gdf_wgs84.geometry.union_all()
    try:
        trails = ox.features_from_polygon(poly_wgs84, tags={'highway': ['path', 'track', 'footway', 'bridleway']})
    except Exception as e:
        print("    Warning querying trails:", e)
        return None

    if len(trails) == 0 or 'name' not in trails.columns:
        print("    No named trail/track ways found.")
        return None

    named = trails[trails['name'].notna()]
    if len(named) == 0:
        print("    Trail ways found but none carry a name.")
        return None

    if named.crs is None:
        named.set_crs(WGS84_CRS, inplace=True)
    named_utm = named.to_crs(TARGET_CRS)
    buffer_poly = named_utm.geometry.buffer(30).union_all()
    print(f"    Found {len(named_utm)} named trail/track ways; built a 30m trail-signage buffer.")
    return buffer_poly


# Stock photo fallback for sub_types that are real, physical, photographable
# places but are anonymous OSM nodes with no name/Wikidata entry of their own
# to enrich a photo from (2026-07-25 feedback: "per le immagini di area
# fitness vorrei una foto, pesca dalla rete"). Sourced from Wikimedia Commons
# (Category:Outdoor gyms), reachable and CC-licensed like the other Commons
# photos this pipeline already links to.
DEFAULT_IMAGE_BY_SUB_TYPE = {
    'fitness_station': 'https://commons.wikimedia.org/wiki/Special:FilePath/Bench%20press%20at%20an%20outdoor%20fitness%20station.jpg',
}

# Maps (osm_key, osm_value) pairs to a MapLibre-renderable icon name. Checked in
# priority order (historic > amenity > tourism > leisure > highway > railway) since
# a POI can carry tags from more than one of these keys at once.
ICON_MAP = {
    ('historic', 'fort'): 'castle',
    ('historic', 'castle'): 'castle',
    ('historic', 'monument'): 'monument',
    ('historic', 'memorial'): 'monument',
    ('historic', 'archaeological_site'): 'ruins',
    ('historic', 'ruins'): 'ruins',
    ('historic', 'trench'): 'ruins',
    ('amenity', 'theatre'): 'theater',
    ('amenity', 'arts_centre'): 'theater',
    ('amenity', 'restaurant'): 'restaurant',
    ('amenity', 'cafe'): 'cafe',
    ('amenity', 'pub'): 'cafe',
    ('amenity', 'bar'): 'cafe',
    ('amenity', 'fast_food'): 'cafe',
    ('amenity', 'canteen'): 'canteen',
    ('amenity', 'public_bookcase'): 'library',
    ('amenity', 'library'): 'library',
    ('amenity', 'university'): 'college',
    ('amenity', 'research_institute'): 'college',
    ('amenity', 'drinking_water'): 'drinking_water',
    ('tourism', 'museum'): 'museum',
    ('tourism', 'attraction'): 'attraction',
    ('tourism', 'artwork'): 'attraction',
    ('tourism', 'information'): 'information',
    ('tourism', 'picnic_site'): 'park',
    ('tourism', 'hotel'): 'hotel',
    ('tourism', 'guest_house'): 'hotel',
    ('tourism', 'chalet'): 'hotel',
    ('tourism', 'camp_site'): 'hotel',
    ('tourism', 'alpine_hut'): 'hotel',
    ('tourism', 'wilderness_hut'): 'hotel',
    ('leisure', 'amphitheatre'): 'theater',
    ('leisure', 'park'): 'park',
    ('leisure', 'garden'): 'park',
    ('leisure', 'pitch'): 'sport',
    ('leisure', 'sports_centre'): 'sport',
    ('leisure', 'sports_hall'): 'sports_hall',
    ('leisure', 'playground'): 'playground',
    ('leisure', 'nature_reserve'): 'nature_reserve',
    ('leisure', 'fitness_station'): 'fitness_station',
    ('highway', 'bus_stop'): 'bus',
    ('railway', 'station'): 'bus',
    ('railway', 'halt'): 'bus',
    ('public_transport', 'platform'): 'bus',
    ('sport', 'climbing'): 'climbing',
    # Sport-specific pitch icons (2026-07-25 feedback) -- checked before
    # `sport` falls through to the generic ('leisure', 'pitch'): 'sport'
    # mapping below, since `assign_icon_name` tries the `sport` key ahead of
    # `leisure` in its priority order.
    ('sport', 'basketball'): 'basketball_court',
    ('sport', 'volleyball'): 'volleyball_court',
    ('sport', 'tennis'): 'tennis_court',
    # Every other common `sport=*` value gets its own recognizable icon too
    # (2026-07-28 feedback: "dammi l'icona corretta di ogni sport: chess =
    # scacchi, tennis table = ping pong ecc.") instead of collapsing onto the
    # generic ball-icon fallback in assign_icon_name. padel/beachvolleyball/
    # futsal/fitness reuse the closest existing court/icon rather than adding
    # a near-duplicate glyph.
    ('sport', 'table_tennis'): 'table_tennis',
    ('sport', 'chess'): 'chess',
    ('sport', 'athletics'): 'athletics',
    ('sport', 'skateboard'): 'skateboard',
    ('sport', 'rugby'): 'rugby',
    ('sport', 'baseball'): 'baseball',
    ('sport', 'cricket'): 'cricket',
    ('sport', 'hockey'): 'hockey',
    ('sport', 'gymnastics'): 'gymnastics',
    ('sport', 'american_football'): 'american_football',
    ('sport', 'bocce'): 'bocce',
    ('sport', 'boules'): 'bocce',
    ('sport', 'padel'): 'tennis_court',
    ('sport', 'beachvolleyball'): 'volleyball_court',
    ('sport', 'fitness'): 'fitness_station',
    ('shop', 'copyshop'): 'copyshop',
    ('shop', 'supermarket'): 'supermarket',
    ('shop', 'bakery'): 'bakery',
    ('shop', 'convenience'): 'convenience',
    ('shop', 'butcher'): 'butcher',
    ('shop', 'greengrocer'): 'greengrocer',
    ('shop', 'chemist'): 'pharmacy',
    ('shop', 'books'): 'books',
    ('shop', 'beauty'): 'beauty',
    ('shop', 'hairdresser'): 'hairdresser',
    ('shop', 'deli'): 'deli',
    ('office', 'association'): 'association',
    ('office', 'ngo'): 'association',
    ('office', 'research'): 'college',
    ('office', 'educational_institution'): 'college',
    ('office', 'it'): 'office_it',
    # Civic/"Luoghi Pubblici" building types that used to all collapse onto the
    # generic gray marker/info pin, making a church indistinguishable from a
    # town hall on the map (2026-07-26 feedback: keep the gray background --
    # these aren't tied to one social-function color the way e.g. sport is --
    # but give each its own glyph so the icon itself says what the place is).
    ('amenity', 'place_of_worship'): 'place_of_worship',
    ('amenity', 'community_centre'): 'community_centre',
    ('amenity', 'townhall'): 'townhall',
    ('amenity', 'social_facility'): 'social_facility',
    ('amenity', 'shelter'): 'shelter',
    ('place', 'square'): 'square',
    # Reference-only PoIs (2026-07-26 feedback): shown with their own icon +
    # popup even though they're excluded from indicator scoring (see
    # `solo_riferimento` in classify_and_transform_pois).
    ('amenity', 'parking'): 'parking',
    ('amenity', 'recycling'): 'recycling',
    # Neighbourhood-service icons that were fetched from OSM but still fell
    # back to the generic 'marker' pin, indistinguishable from an unclassified
    # feature (2026-07-26 feedback: "mancano ancora icone" -- audited every
    # tag this pipeline fetches against ICON_MAP and filled every gap, not
    # just the examples given).
    ('amenity', 'school'): 'school',
    ('amenity', 'kindergarten'): 'kindergarten',
    ('amenity', 'pharmacy'): 'pharmacy',
    ('amenity', 'post_office'): 'post_office',
    ('amenity', 'bank'): 'bank',
    ('amenity', 'atm'): 'atm',
    ('amenity', 'marketplace'): 'market',
    ('amenity', 'fire_station'): 'fire_station',
    ('amenity', 'clinic'): 'clinic',
    ('amenity', 'doctors'): 'clinic',
}


def assign_icon_name(historic, amenity, tourism, leisure, highway, railway,
                      sport='nan', office='nan', shop='nan', public_transport='nan', place='nan'):
    """Pick a MapLibre icon name for a POI from its OSM tags, with a 'marker' fallback."""
    for key, value in [
        ('historic', historic), ('amenity', amenity), ('tourism', tourism),
        ('sport', sport), ('office', office), ('shop', shop),
        ('leisure', leisure), ('highway', highway), ('railway', railway),
        ('public_transport', public_transport), ('place', place)
    ]:
        if value != 'nan' and (key, value) in ICON_MAP:
            return ICON_MAP[(key, value)]
    # Any other sport=* value (e.g. table_tennis, athletics, multi) not
    # specifically mapped above still deserves the generic sport icon rather
    # than the plain marker pin (2026-07-26 feedback: audited every PoI that
    # still fell back to 'marker' on a real pipeline run).
    if sport != 'nan':
        return 'sport'
    return 'marker'


# Sociological rationale attached to every POI, keyed by its assigned category.
SOCIAL_FUNCTION_BY_CATEGORY = {
    'cross_civic': (
        "Terzo Luogo (Oldenburg). Spazio aperto e inclusivo per la nascita di "
        "relazioni informali e capitale sociale."
    ),
    'residenti': (
        "Infrastruttura di Vicinato (Klinenberg / Jacobs). Garantisce i servizi "
        "primari e il presidio vigile della strada."
    ),
    'pendolari': (
        "Hub di Flusso Accademico. Spazio funzionale allo studio e alla mobilità "
        "quotidiana di studenti e lavoratori."
    ),
    'occasionali': (
        "Attrattore Eco-Ricreativo. Promuove il benessere attivo, lo sport all'aperto "
        "e la valorizzazione del paesaggio."
    ),
}


# Italian translation for a POI's raw OSM sub_type value, used to build
# `amenity_type`. Mirrors src/config/mapConfig.js's SUB_TYPE_LABELS -- kept in
# sync by hand since Python and the frontend don't share a single source of
# truth; update both when adding a new OSM tag value (2026-07-25 feedback:
# raw English tag names like "drinking_water" shouldn't reach the UI).
AMENITY_TYPE_LABELS_IT = {
    'fort': 'Forte / Sito Storico',
    'castle': 'Castello',
    'monument': 'Monumento',
    'memorial': 'Monumento Commemorativo',
    'archaeological_site': 'Sito Archeologico',
    'ruins': 'Rovine',
    'museum': 'Museo',
    'attraction': 'Attrazione Turistica',
    'artwork': "Opera d'Arte Pubblica",
    'viewpoint': 'Punto Panoramico',
    'picnic_site': 'Area Picnic',
    'guest_house': 'Agriturismo',
    'hotel': 'Hotel',
    'chalet': 'Chalet',
    'camp_site': 'Campeggio',
    'alpine_hut': 'Rifugio Alpino',
    'theatre': 'Teatro',
    'arts_centre': 'Centro Culturale',
    'cafe': 'Caffè',
    'restaurant': 'Ristorante',
    'pub': 'Pub',
    'bar': 'Bar',
    'fast_food': 'Fast Food',
    'public_bookcase': 'Bookcrossing',
    'community_centre': 'Centro Civico',
    'drinking_water': 'Fontanella',
    'bench': 'Panchina',
    'shelter': 'Rifugio / Pensilina',
    'townhall': 'Municipio',
    'social_facility': 'Servizio Sociale',
    'place_of_worship': 'Luogo di Culto',
    'square': 'Piazza',
    'university': 'Università',
    'research_institute': 'Istituto di Ricerca',
    'library': 'Biblioteca',
    'canteen': 'Mensa',
    'parking': 'Parcheggio',
    'bus_stop': 'Fermata Bus',
    'station': 'Stazione',
    'halt': 'Fermata Ferroviaria',
    'park': 'Parco Pubblico',
    'garden': 'Giardino Pubblico',
    'copyshop': 'Copisteria',
    'beauty': 'Centro Estetico',
    'hairdresser': 'Parrucchiere',
    'deli': 'Gastronomia',
    'association': 'Associazione / Circolo',
    'ngo': 'Associazione / ONG',
    'wilderness_hut': 'Bivacco',
    'trench': 'Trincea Storica',
    'market': 'Mercato Settimanale',
    'historic': 'Stoi Militari',
    'sports_centre': 'Centro Sportivo',
    'bank': 'Banca',
    'climbing': "Falesia d'Arrampicata",
    'fitness_station': 'Area Fitness',
    'footway': 'Percorso Pedonale',
    'kindergarten': "Asilo Nido / Scuola dell'Infanzia",
    'platform': 'Fermata Bus',
    'post_office': 'Ufficio Postale',
    'school': 'Scuola',
    'sports_hall': 'Palestra',
    'recycling': 'Isola Ecologica',
    'playground': 'Parco Giochi',
    'information': 'Punto Informativo',
    'it': 'Azienda ICT',
    'research': 'Ufficio di Ricerca',
    'educational_institution': 'Istituto Formativo',
    # Added 2026-07-26 -- these OSM tags were already fetched (or newly added
    # to the fetch list, see fetch_osm_graph_and_pois) but had no Italian
    # label, so they fell back to a raw/title-cased English word in the UI.
    'pharmacy': 'Farmacia',
    'supermarket': 'Supermercato',
    'convenience': 'Minimarket',
    'butcher': 'Macelleria',
    'greengrocer': 'Fruttivendolo',
    'chemist': 'Drogheria',
    'books': 'Libreria',
    'atm': 'Bancomat',
    'marketplace': 'Mercato Rionale',
    'fire_station': 'Vigili del Fuoco',
    'clinic': 'Ambulatorio Medico',
    'doctors': 'Studio Medico',
    'nature_reserve': 'Riserva Naturale',
}


def format_amenity_type(sub_type):
    """Italian label for a raw OSM sub_type value, e.g. 'drinking_water' -> 'Fontanella'."""
    if not sub_type or sub_type == 'nan':
        return ''
    if sub_type in AMENITY_TYPE_LABELS_IT:
        return AMENITY_TYPE_LABELS_IT[sub_type]
    return sub_type.replace('_', ' ').title()


# OSM `sport` tag value -> Italian sport name, used to turn the raw word
# "pitch" into "Campo da <sport>" (2026-07-25 feedback).
SPORT_NAME_IT = {
    'soccer': 'calcio', 'multi': 'sport misti', 'basketball': 'basket',
    'volleyball': 'pallavolo', 'tennis': 'tennis', 'table_tennis': 'ping pong',
    'athletics': 'atletica', 'skateboard': 'skateboard', 'climbing': 'arrampicata',
    'beachvolleyball': 'beach volley', 'bocce': 'bocce', 'boules': 'bocce',
    'padel': 'padel', 'futsal': 'calcetto', 'american_football': 'football americano',
    'rugby': 'rugby', 'baseball': 'baseball', 'cricket': 'cricket', 'hockey': 'hockey',
    'fitness': 'fitness', 'gymnastics': 'ginnastica', 'chess': 'scacchi'
}


def format_pitch_label(sport):
    """Build a 'Campo da <sport>' label from an OSM `sport` tag value."""
    if not sport or sport == 'nan':
        return 'Campo Sportivo'
    it_name = SPORT_NAME_IT.get(sport, sport.replace('_', ' '))
    return f'Campo da {it_name}'


# Affittacamere, guest house, hotel and agriturismi are all the same kind of
# thing to a visitor -- a place to sleep -- so they're unified under one
# "Tipo di Servizio" label rather than split by OSM's `tourism=guest_house`
# vs `tourism=hotel` vs the `guest_house=agritourism/bed_and_breakfast/...`
# sub-tag (2026-07-25 feedback: "vanno sotto la stessa categoria"). Covers
# every sub_type in ACCOMMODATION_SUB_TYPES; sub_type/osm_tag still keep the
# precise underlying OSM value if that distinction is ever needed again.
ACCOMMODATION_LABEL_IT = 'Struttura Ricettiva'
ACCOMMODATION_SUB_TYPES = {'guest_house', 'hotel'}


OPENING_HOURS_DAY_MAP = {'Mo': 'Lun', 'Tu': 'Mar', 'We': 'Mer', 'Th': 'Gio', 'Fr': 'Ven', 'Sa': 'Sab', 'Su': 'Dom'}


def normalize_opening_hours(raw):
    """Lightly normalize an OSM `opening_hours` tag into an Italian-readable string."""
    if not raw or raw == 'nan':
        return ''
    text = raw
    for en, it in OPENING_HOURS_DAY_MAP.items():
        text = re.sub(rf'\b{en}\b', it, text)
    return text.replace(';', ' · ').strip()


# OSM `access=*` values that mean "not open to the general public" (2026-07-25
# feedback: a PoI's sociological category shouldn't be the only signal --
# e.g. a publicly-accessible football pitch is useful to every community, not
# just the one its category happens to bucket it into). Anything else,
# including no `access` tag at all, is treated as public per the same
# feedback ("se non c'è assumi public").
RESTRICTED_ACCESS_VALUES = {'private', 'no', 'customers', 'customers_only'}


def compute_accesso_pubblico(access_raw):
    """True unless OSM's `access` tag explicitly restricts entry (see RESTRICTED_ACCESS_VALUES)."""
    value = str(access_raw).strip().lower()
    if value in ('', 'nan', 'none'):
        return True
    return value not in RESTRICTED_ACCESS_VALUES


def classify_and_transform_pois(raw_pois_utm, named_routes_buffer=None):
    """
    Transform polygon POIs to centroids in EPSG:25832, assign category, name, sub_type,
    osm_tag, icon_name, sociological/ICC metadata, and return GeoDataFrames in
    EPSG:25832 and EPSG:4326. Individual recycling bins (recycling_type != 'centre')
    are dropped entirely. Parking and off-route `tourism=information` signage (outside
    `named_routes_buffer`) are kept but flagged `solo_riferimento=True` -- shown on the
    map/table with their own icon and popup, excluded from indicator scoring
    (see calculate_scores_and_mixite).
    """
    print("--> Classifying POIs and converting polygon geometries to centroids...")
    empty_cols = [
        'id', 'osm_id', 'name', 'category', 'sub_type', 'osm_tag', 'icon_name', 'amenity_type',
        'social_function', 'image_url', 'indirizzo', 'orari_apertura', 'contatti',
        'sito_web', 'accessibilita_disabili', 'source', 'wikidata_id', 'wikipedia_title',
        'accesso_pubblico', 'offre_asporto', 'solo_riferimento', 'geometry'
    ]
    if len(raw_pois_utm) == 0:
        empty_gdf_utm = gpd.GeoDataFrame(columns=empty_cols, crs=TARGET_CRS)
        empty_gdf_wgs84 = gpd.GeoDataFrame(columns=empty_cols, crs=WGS84_CRS)
        return empty_gdf_utm, empty_gdf_wgs84

    # Convert polygon/multipolygon geometries to centroids in metric UTM 32N
    centroids_utm = raw_pois_utm.geometry.centroid
    gdf_pts_utm = gpd.GeoDataFrame(raw_pois_utm.drop(columns=['geometry']), geometry=centroids_utm, crs=TARGET_CRS)
    gdf_pts_wgs84 = gdf_pts_utm.to_crs(WGS84_CRS)

    # Bus stop locations, used below to recognize an amenity=shelter as a bus
    # stop's pensilina rather than generic civic infrastructure (2026-07-25
    # feedback) when it doesn't carry the (rarer) shelter_type=public_transport
    # tag itself.
    BUS_SHELTER_RADIUS_M = 15.0
    if 'highway' in gdf_pts_utm.columns:
        bus_stop_geoms = gdf_pts_utm.loc[gdf_pts_utm['highway'] == 'bus_stop', 'geometry']
    else:
        bus_stop_geoms = gpd.GeoSeries([], crs=TARGET_CRS)

    poi_records_utm = []
    poi_records_wgs84 = []

    n_signage_reference_only = 0
    n_parking_reference_only = 0
    n_recycling_dropped = 0
    n_private_access_dropped = 0
    for idx, row in gdf_pts_utm.iterrows():
        pt_utm = row.geometry
        pt_wgs84 = gdf_pts_wgs84.loc[idx].geometry
        if pt_utm is None or pt_utm.is_empty:
            continue

        # Anything explicitly tagged access=private is dropped entirely --
        # not shown, not calculated (2026-07-28 feedback: "dove un oggetto ha
        # il tag access=private non devi considerarlo"). This is stricter than
        # `accesso_pubblico`/RESTRICTED_ACCESS_VALUES below (which also treats
        # access=no/customers as non-public but still keeps those PoIs visible
        # on the map/table, just excluded from indicator scoring) and applies
        # to every fetched tag/category alike -- including amenity=parking,
        # which used to always stay in the dataset regardless of access.
        if str(row.get('access', '')).strip().lower() == 'private':
            n_private_access_dropped += 1
            continue

        amenity = str(row.get('amenity', ''))
        shop = str(row.get('shop', ''))
        leisure = str(row.get('leisure', ''))
        office = str(row.get('office', ''))
        highway = str(row.get('highway', ''))
        tourism = str(row.get('tourism', ''))
        railway = str(row.get('railway', ''))
        place = str(row.get('place', ''))
        historic = str(row.get('historic', ''))
        sport = str(row.get('sport', ''))
        public_transport = str(row.get('public_transport', ''))
        wikidata = str(row.get('wikidata', ''))
        wikipedia = str(row.get('wikipedia', ''))
        opening_hours = str(row.get('opening_hours', ''))
        takeaway_tag = str(row.get('takeaway', '')).lower()
        recycling_type = str(row.get('recycling_type', '')).lower()
        cuisine = str(row.get('cuisine', '')).lower()
        accesso_pubblico = compute_accesso_pubblico(row.get('access', ''))
        # OSM's own `website` (falling back to `contact:website`) straight into
        # the info-card field -- previously left blank for every OSM-sourced
        # PoI and only ever filled later by the Wikidata enrichment step
        # (2026-07-28 feedback: "sei nei tag trovi website aggiungilo nella
        # scheda informativa" -- e.g. CNR-IFN Trento / HIT carry it directly).
        website = str(row.get('website', ''))
        if website == 'nan' or not website:
            website = str(row.get('contact:website', ''))
        if website == 'nan':
            website = ''

        name = str(row.get('name', ''))
        if name == 'nan':
            name = ''

        # An amenity=shelter can mean three very different things -- a bus
        # stop's pensilina, an open-air civic third-place shelter, or a
        # mountain/trail rifugio-style hut -- and OSM's own `shelter_type`
        # sub-tag is what actually distinguishes the last case (2026-07-26
        # feedback: "devi capire quando sei davanti ad una pensilina
        # dell'autobus ... o davanti ad un rifugio"). Checked in this order:
        # explicit shelter_type=public_transport, then proximity to a mapped
        # bus stop (shelter_type is often left blank even on real bus
        # shelters), then outdoor/hiking shelter_type values.
        OUTDOOR_SHELTER_TYPES = {'basic_hut', 'lean_to', 'rock_shelter', 'weather_shelter', 'field_shelter'}
        is_bus_shelter = False
        is_outdoor_shelter = False
        if amenity == 'shelter':
            shelter_type = str(row.get('shelter_type', '')).lower()
            if shelter_type == 'public_transport':
                is_bus_shelter = True
            elif len(bus_stop_geoms) > 0 and bus_stop_geoms.distance(pt_utm).min() <= BUS_SHELTER_RADIUS_M:
                is_bus_shelter = True
            elif shelter_type in OUTDOOR_SHELTER_TYPES:
                is_outdoor_shelter = True

        # Individual street recycling bins/containers are noise; only a real
        # staffed/drop-off "isola ecologica" (recycling_type=centre) is kept
        # (2026-07-26 feedback).
        if amenity == 'recycling' and recycling_type != 'centre':
            n_recycling_dropped += 1
            continue

        # Parking feeds the distance-to-parking accessibility indicator
        # (calculate_accessibility_distances reads it straight from
        # raw_pois_utm) and generic off-route trail signage is otherwise just
        # clutter (2026-07-25 feedback: too many points on mountain trails) --
        # neither represents a neighbourhood service in its own right, so both
        # are marked `solo_riferimento` below and excluded from indicator
        # scoring (see calculate_scores_and_mixite), but they're still shown
        # on the map/table with their own icon and a query popup (2026-07-26
        # feedback: "punti di cui fai uso e che non fanno parte del calcolo"
        # should still be identifiable).
        is_reference_only_parking = amenity == 'parking'
        on_named_route = tourism == 'information' and named_routes_buffer is not None and named_routes_buffer.contains(pt_utm)
        is_reference_only_signage = tourism == 'information' and not on_named_route
        solo_riferimento = is_reference_only_parking or is_reference_only_signage
        if is_reference_only_parking:
            n_parking_reference_only += 1
        if is_reference_only_signage:
            n_signage_reference_only += 1

        # Classification Logic
        # 1. Cross / Civic (Luoghi Pubblici) -- an unnamed amenity=shelter that's
        # actually a bus-stop shelter is NOT third-place civic infrastructure,
        # it's transit infra, so it's carved out here and picked up by the
        # pendolari branch below instead (2026-07-25 feedback); an outdoor/
        # hiking-hut shelter is carved out too, picked up by the occasionali
        # branch instead (2026-07-26 feedback).
        is_cross_civic_amenity = (
            amenity in ['public_bookcase', 'community_centre', 'drinking_water', 'shelter', 'townhall', 'social_facility', 'place_of_worship', 'marketplace']
            and not (amenity == 'shelter' and (is_bus_shelter or is_outdoor_shelter))
        )
        if (is_cross_civic_amenity or
            leisure in ['park', 'garden'] or
            place == 'square' or
            office in ['association', 'ngo']):
            category = 'cross_civic'
            sub_type = (amenity if amenity != 'nan' else
                        (leisure if leisure != 'nan' else
                         (place if place != 'nan' else office)))
            osm_tag = (f'amenity={amenity}' if amenity != 'nan' else
                       (f'leisure={leisure}' if leisure != 'nan' else
                        (f'place={place}' if place != 'nan' else f'office={office}')))

        # 2. Pendolari (Campus UniTN/FBK, biblioteche, mense, TPL, copisterie,
        #    uffici/aziende ICT -- office=it, come le altre sedi di ricerca,
        #    pensiline delle fermate -- amenity=shelter riconosciuto come
        #    tale, 2026-07-25 feedback)
        elif (amenity in ['university', 'research_institute', 'library', 'canteen'] or
              (amenity == 'shelter' and is_bus_shelter) or
              shop == 'copyshop' or
              highway == 'bus_stop' or
              railway in ['station', 'halt'] or
              public_transport == 'platform' or
              office in ['research', 'educational_institution', 'it']):
            category = 'pendolari'
            # NOTE: `office` was previously missing from this fallback chain,
            # so an office-only POI (no amenity/shop/highway/railway/
            # public_transport) would end up with sub_type/osm_tag == 'nan'.
            # `public_transport` is checked *before* `highway` here (2026-07-25
            # feedback: "i percorsi pedonali sono fermate dell'autobus") --
            # a bus platform mapped as a way often carries an incidental
            # highway=footway tag alongside public_transport=platform, and
            # without this ordering it showed up mislabeled as "Percorso
            # Pedonale" instead of the bus platform it actually is.
            sub_type = (amenity if amenity != 'nan' else
                        (shop if shop != 'nan' else
                         (public_transport if public_transport != 'nan' else
                          (highway if highway != 'nan' else
                           (railway if railway != 'nan' else office)))))
            osm_tag = (f'amenity={amenity}' if amenity != 'nan' else
                       (f'shop={shop}' if shop != 'nan' else
                        (f'public_transport={public_transport}' if public_transport != 'nan' else
                         (f'highway={highway}' if highway != 'nan' else
                          (f'railway={railway}' if railway != 'nan' else f'office={office}')))))

        # 3. Occasionali (forti/castelli, monumenti/trincee, teatri/anfiteatri, musei/
        #    attrazioni, falesie, bivacchi, sentieri, punti panoramici, picnic, ristorazione,
        #    rifugi/ripari escursionistici -- amenity=shelter con shelter_type di tipo
        #    outdoor, 2026-07-26 feedback)
        elif (historic != 'nan' or
              amenity in ['cafe', 'restaurant', 'pub', 'bar', 'fast_food', 'theatre', 'arts_centre'] or
              (amenity == 'shelter' and is_outdoor_shelter) or
              tourism != 'nan' or
              leisure in ['nature_reserve', 'amphitheatre'] or
              sport == 'climbing'):
            category = 'occasionali'
            sub_type = (historic if historic != 'nan' else
                        (tourism if tourism != 'nan' else
                         (amenity if amenity != 'nan' else
                          (sport if sport != 'nan' else leisure))))
            osm_tag = (f'historic={historic}' if historic != 'nan' else
                       (f'tourism={tourism}' if tourism != 'nan' else
                        (f'amenity={amenity}' if amenity != 'nan' else
                         (f'sport={sport}' if sport != 'nan' else f'leisure={leisure}'))))

        # 4. Residenti (Servizi vicinato, scuole, farmacie, alimentari, estetica, parco giochi).
        # `sport` is the last resort in the chain -- catches a bare sport=*
        # node/way with no amenity/shop/leisure tag of its own (2026-07-26
        # feedback: found via a real pipeline run producing a nonsensical
        # "leisure=nan" name/osm_tag for exactly this case).
        else:
            category = 'residenti'
            sub_type = (amenity if amenity != 'nan' else
                        (shop if shop != 'nan' else
                         (leisure if leisure != 'nan' else sport)))
            osm_tag = (f'amenity={amenity}' if amenity != 'nan' else
                       (f'shop={shop}' if shop != 'nan' else
                        (f'leisure={leisure}' if leisure != 'nan' else f'sport={sport}')))

        # "Campo da <sport>" instead of the raw OSM word "pitch" (2026-07-25
        # feedback). An indoor climbing wall (leisure=sports_centre +
        # sport=climbing) reads as "Parete d'Arrampicata" rather than the
        # generic AMENITY_TYPE_LABELS_IT['climbing'] "Falesia d'Arrampicata"
        # (a falesia is specifically an outdoor natural crag, 2026-07-28
        # feedback: "per il discorso di amenity=climb traduci come parete
        # d'arrampicata"). Computed here (before the name fallback below) so
        # it can also serve as the fallback display name for an unnamed PoI.
        amenity_type = (
            "Parete d'Arrampicata" if sub_type == 'climbing' and leisure == 'sports_centre' else
            (format_pitch_label(sport) if sub_type == 'pitch' else
             (ACCOMMODATION_LABEL_IT if sub_type in ACCOMMODATION_SUB_TYPES else
              format_amenity_type(sub_type)))
        )

        # Always surface a name -- an anonymous OSM node/way shouldn't reach
        # the UI as a nameless "Punto di interesse": fall back to its translated
        # service type (2026-07-28 feedback: "non usare il tag come nome, ma
        # prendi la chiave principale e traduci il valore in italiano" --
        # supersedes the previous raw "amenity=shelter"-style fallback). An
        # unnamed amenity=shelter is ambiguous on its own (AMENITY_TYPE_LABELS_IT
        # just says "Rifugio / Pensilina"), so it's disambiguated using the same
        # bus-stop-proximity check already used for its category/icon above
        # (2026-07-28 feedback: "attenzione fra pensiline dell'autobus e
        # bivacchi -- basta che controlli se e' una fermata dell'autobus").
        if not name:
            if amenity == 'shelter' and is_bus_shelter:
                name = 'Pensilina Autobus'
            elif amenity == 'shelter' and is_outdoor_shelter:
                name = 'Bivacco'
            else:
                name = amenity_type or osm_tag

        icon_name = assign_icon_name(historic, amenity, tourism, leisure, highway, railway,
                                      sport, office, shop, public_transport, place)
        # A bus-stop shelter is transit infra (already routed to category=
        # 'pendolari' above), not the generic civic "shelter" glyph added for
        # amenity=shelter -- keep it visually grouped with the other transit
        # icons instead. An outdoor/hiking-hut shelter (already routed to
        # category='occasionali' above) gets its own distinct glyph too, so
        # it doesn't read as the same "civic shelter" as an urban one
        # (2026-07-26 feedback).
        if amenity == 'shelter' and is_bus_shelter:
            icon_name = 'bus'
        elif amenity == 'shelter' and is_outdoor_shelter:
            icon_name = 'mountain_shelter'

        # A pizzeria/pizza-al-taglio place is usually just tagged
        # amenity=restaurant or amenity=fast_food with cuisine=pizza -- give
        # it its own icon instead of the generic restaurant/fast_food one
        # (2026-07-26 feedback: "pizza al taglio" / "pizzeria" in the list of
        # PoI types that need a distinguishable icon).
        if amenity in ('restaurant', 'fast_food') and 'pizza' in cuisine:
            icon_name = 'pizza'

        # Does this PoI hand out ready-to-eat/takeaway food? Used only to gate
        # picnic areas' relevance to pendolari lunch breaks (2026-07-25
        # feedback) -- see calculate_scores_and_mixite.
        offre_asporto = (
            sub_type in TAKEAWAY_FOOD_SUB_TYPES or
            shop == 'supermarket' or
            takeaway_tag == 'yes'
        )

        # OSM's own "element/id" reference (idx is an (element_type, osmid)
        # MultiIndex tuple from osmnx's features_from_polygon, e.g.
        # ('node', 13990384642) -> 'node/13990384642'). This is the same
        # format the circoscrizione dataset's own new `osm_id` column now
        # uses (2026-07-26 feedback), so deduplicate_and_merge below can
        # match local <-> OSM records by exact element identity instead of
        # (or ahead of) fuzzy name/distance matching.
        osm_id = f'{idx[0]}/{idx[1]}' if isinstance(idx, tuple) else ''

        rec_meta = {
            'id': str(idx[1]) if isinstance(idx, tuple) else str(idx),
            'osm_id': osm_id,
            'name': name,
            'category': category,
            'sub_type': sub_type,
            'osm_tag': osm_tag,
            'icon_name': icon_name,
            'amenity_type': amenity_type,
            'social_function': SOCIAL_FUNCTION_BY_CATEGORY[category],
            'image_url': DEFAULT_IMAGE_BY_SUB_TYPE.get(sub_type, ''),
            'indirizzo': '',
            'orari_apertura': normalize_opening_hours(opening_hours),
            'contatti': '',
            'sito_web': website,
            'accessibilita_disabili': '',
            'source': 'osm',
            'wikidata_id': wikidata if wikidata != 'nan' else '',
            'wikipedia_title': wikipedia if wikipedia != 'nan' else '',
            'accesso_pubblico': accesso_pubblico,
            'offre_asporto': offre_asporto,
            'solo_riferimento': solo_riferimento
        }

        rec_utm = rec_meta.copy()
        rec_utm['geometry'] = pt_utm
        poi_records_utm.append(rec_utm)

        rec_wgs84 = rec_meta.copy()
        rec_wgs84['geometry'] = pt_wgs84
        poi_records_wgs84.append(rec_wgs84)

    gdf_pois_utm = gpd.GeoDataFrame(poi_records_utm, crs=TARGET_CRS)
    gdf_pois_wgs84 = gpd.GeoDataFrame(poi_records_wgs84, crs=WGS84_CRS)

    counts = gdf_pois_utm['category'].value_counts().to_dict()
    print(f"    Features dropped entirely for access=private: {n_private_access_dropped}")
    print(f"    Individual recycling bins/containers dropped (kept only recycling_type=centre): {n_recycling_dropped}")
    print(f"    Trail signage (tourism=information) kept as reference-only, not on a named route: {n_signage_reference_only}")
    print(f"    Parking features kept as reference-only (also feed the distance-to-parking indicator): {n_parking_reference_only}")
    print("    OSM POIs categorized:", counts)
    return gdf_pois_utm, gdf_pois_wgs84


# --- Local dataset (Circoscrizione di Povo) ---------------------------------

DAY_COLUMNS = ['lunedi', 'martedi', 'mercoledi', 'giovedi', 'venerdi', 'sabato', 'domenica']
DAY_LABELS = {
    'lunedi': 'Lun', 'martedi': 'Mar', 'mercoledi': 'Mer', 'giovedi': 'Gio',
    'venerdi': 'Ven', 'sabato': 'Sab', 'domenica': 'Dom'
}

# (substring found in the POI name, lowercased) -> (sociological category,
# icon_name). Checked before the per-`servizio`-bucket default below. The
# icon is needed because a local-only entry (no matching OSM feature to
# adopt icon_name from -- see deduplicate_and_merge) would otherwise stay on
# the generic 'marker' pin forever (2026-07-26 feedback: "mancano ancora
# icone sui PoI" -- bookcrossing/casa sociale/cabina fototessere/mercato
# settimanale etc. are exactly the local-only entries this fixes).
LOCAL_CATEGORY_KEYWORDS = [
    ('fontana', 'cross_civic', 'drinking_water'),
    ('bookcrossing', 'cross_civic', 'library'),
    ('mercat', 'cross_civic', 'market'),  # mercato, mercatino
    ('associazion', 'cross_civic', 'association'),
    ('centro civico', 'cross_civic', 'community_centre'),
    ('casa sociale', 'cross_civic', 'community_centre'),
    ('sala multiuso', 'cross_civic', 'community_centre'),
    ('copisteria', 'pendolari', 'copyshop'),
    ('cartocopisteria', 'pendolari', 'copyshop'),
    ('biblioteca', 'pendolari', 'library'),
    ('scuola', 'residenti', 'school'),
    ('farmacia', 'residenti', 'pharmacy'),
    ('ufficio postale', 'residenti', 'post_office'),
    ('banca', 'residenti', 'bank'),
    ('cooperativa', 'residenti', 'supermarket'),
    ('officina', 'residenti', 'workshop'),
    ('estetic', 'residenti', 'beauty'),
    ('prelievi', 'residenti', 'clinic'),
    ('fototessere', 'residenti', 'photo_booth'),
    ('vigili del fuoco', 'residenti', 'fire_station'),
    ('pane', 'residenti', 'bakery'),
    ('agritur', 'occasionali', 'hotel'),
    ('bar ', 'occasionali', 'cafe'),
    ('pizzeria', 'occasionali', 'pizza'),
    ('pizza ', 'occasionali', 'pizza'),
    ('gelateria', 'occasionali', 'gelateria'),
    ('anfiteatro', 'occasionali', 'theater'),
    ('sala video', 'occasionali', 'theater'),
    ('monumento', 'occasionali', 'monument'),
    ('lapide', 'occasionali', 'monument'),
    ('forte ', 'occasionali', 'castle'),
]

# Fallback when no keyword above matches the POI name, keyed by the source's
# own `servizio` bucket -- (category, icon_name). 'Servizi e attività
# economiche' is left on 'marker': it's a catch-all bucket (banks, workshops,
# hairdressers, ...) too heterogeneous for one representative icon, and most
# of its real entries already match a more specific keyword above.
SERVIZIO_DEFAULT_CATEGORY = {
    'Servizi e attività economiche': ('residenti', 'marker'),
    'Ristorazione e agriturismi': ('occasionali', 'restaurant'),
    'Cultura e tempo libero': ('cross_civic', 'community_centre'),
    'Luoghi/monumenti di interesse storico/artistico e fontane': ('occasionali', 'monument'),
    'Associazioni e gruppi': ('cross_civic', 'association'),
}


def classify_local_poi(servizio, nome):
    """Returns (category, icon_name) for a local circoscrizione POI, by keyword first, then servizio bucket."""
    nome_low = (nome or '').lower()
    for keyword, category, icon in LOCAL_CATEGORY_KEYWORDS:
        if keyword in nome_low:
            return category, icon
    return SERVIZIO_DEFAULT_CATEGORY.get(servizio, ('residenti', 'marker'))


# Manual corrections applied to specific local-dataset entries before
# classification/dedup (2026-07-25 feedback). "Bar Al Canton" (local) and
# OSM's "Bar Osteria Can Ton" are the same physical bar (identical
# coordinates) but only 62.5% name-similar -- below DEDUP_NAME_THRESHOLD, so
# they showed up as two separate PoIs. Renaming the local side to match OSM's
# name exactly (100% similarity) lets the normal dedup path fuse them.
LOCAL_NOME_OVERRIDES = {
    'Bar Al Canton': 'Bar Osteria Can Ton',
}

# APSP Margherita Grazioli runs three distinct local-dataset entries (Centro
# Servizi, Casa Melograno, Punto Prelievi) that all shared the same generic
# `attore` value as their displayed "Tipo di Servizio" -- renamed to a proper
# Italian category, with the operator's name folded into the PoI's own name
# instead (2026-07-25 feedback).
LOCAL_ATTORE_AMENITY_OVERRIDES = {
    'APSP Margherita Grazioli': 'Servizi alla Persona',
}

# Icon fallback for the same APSP-run entries, applied only when name-keyword
# matching (LOCAL_CATEGORY_KEYWORDS) didn't already find something more
# specific -- "Punto Prelievi" already matches the 'prelievi' keyword (its own
# dedicated 'clinic' icon), but "Centro Servizi"/"Casa Melograno" are generic
# names an APSP (a nursing-home institution -- "casa per anziani", 2026-07-26
# feedback) uses that no keyword can catch on their own.
LOCAL_ATTORE_ICON_OVERRIDES = {
    'APSP Margherita Grazioli': 'nursing_home',
}


def normalize_attore(attore):
    """
    Case/synonym-fold the local dataset's `attore` field: 'privato',
    'Privato' and 'Soggetto privato' all mean the same thing (an unnamed
    private individual/operator) but showed up as distinct values in the
    "Tipo di Servizio" filter (2026-07-25 feedback) -- everything else in
    this field (org names, institution names, etc.) is left untouched.
    """
    key = (attore or '').strip().lower()
    if key in ('privato', 'soggetto privato'):
        return 'Privato'
    return attore


def _clean(value):
    """Normalize a raw local-dataset cell: strip, treat '-' / None / NaN as empty."""
    text = '' if value is None else str(value).strip()
    return '' if text in ('-', 'nan', 'None') else text


def build_orari_apertura(row):
    """Build a human-readable weekly schedule string from the day-of-week columns."""
    periodo = _clean(row.get('periodo_apertura', ''))
    day_parts = []
    for day in DAY_COLUMNS:
        val = _clean(row.get(day, ''))
        if val:
            day_parts.append(f"{DAY_LABELS[day]}: {val}")

    if day_parts:
        return ' · '.join(day_parts)
    if periodo:
        return periodo
    return _clean(row.get('accesso_temporale', ''))


def load_local_dataset(path):
    """
    Load the Circoscrizione di Povo's hyper-local POI dataset, drop the exact
    duplicate features present in the source export, and map its Italian schema
    onto snake_case fields uniform with the rest of the pipeline.
    """
    print("--> Loading local circoscrizione dataset from", path)
    empty_stats = {'n_raw': 0, 'n_deduped_internal': 0, 'n_final': 0}
    if not os.path.exists(path):
        print("    Local dataset not found, skipping.")
        empty = gpd.GeoDataFrame(columns=['id', 'name', 'category', 'geometry'], crs=WGS84_CRS)
        return empty.to_crs(TARGET_CRS), empty, empty_stats

    gdf_raw = gpd.read_file(path)
    if gdf_raw.crs is None:
        gdf_raw.set_crs(WGS84_CRS, inplace=True)
    n_raw = len(gdf_raw)

    # The source export contains exact duplicate features (same nome+indirizzo,
    # identical properties) -- keep only the first occurrence of each.
    dedup_key = gdf_raw['nome'].astype(str) + '||' + gdf_raw['indirizzo'].astype(str)
    gdf_dedup = gdf_raw.loc[~dedup_key.duplicated(keep='first')].reset_index(drop=True)
    n_deduped_internal = n_raw - len(gdf_dedup)

    records_wgs84 = []
    n_missing_geom = 0
    for idx, row in gdf_dedup.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            n_missing_geom += 1
            continue

        nome = _clean(row.get('nome', ''))
        nome = LOCAL_NOME_OVERRIDES.get(nome, nome)
        servizio = _clean(row.get('servizio', ''))
        category, local_icon_name = classify_local_poi(servizio, nome)

        referente = _clean(row.get('referente', ''))
        contatti_raw = _clean(row.get('contatti', ''))
        contatti = ' · '.join(p for p in (referente, contatti_raw) if p)

        attore = _clean(row.get('attore', ''))
        if attore in LOCAL_ATTORE_AMENITY_OVERRIDES:
            nome = f'{nome} - {attore}'
            amenity_type = LOCAL_ATTORE_AMENITY_OVERRIDES[attore]
            if local_icon_name == 'marker':
                local_icon_name = LOCAL_ATTORE_ICON_OVERRIDES.get(attore, local_icon_name)
        else:
            amenity_type = normalize_attore(attore)

        # Authoritative link to the matching OSM feature, e.g. 'node/13990384642'
        # or 'way/79387122' (2026-07-26 feedback: the circoscrizione dataset now
        # carries this itself) -- lets deduplicate_and_merge fuse local <-> OSM
        # records by exact element identity instead of relying only on
        # fuzzy name/distance matching, which can miss or misfire.
        osm_id = _clean(row.get('osm_id', ''))

        records_wgs84.append({
            'id': f'locale_{idx}',
            'osm_id': osm_id,
            'name': nome,
            'category': category,
            'sub_type': servizio,
            'osm_tag': f'locale={servizio}',
            'icon_name': local_icon_name,  # overridden by the OSM feature's own icon if fused (deduplicate_and_merge)
            'amenity_type': amenity_type,
            'social_function': SOCIAL_FUNCTION_BY_CATEGORY[category],
            'image_url': _clean(row.get('foto', '')),
            'indirizzo': _clean(row.get('indirizzo', '')),
            'orari_apertura': build_orari_apertura(row),
            'contatti': contatti,
            'sito_web': _clean(row.get('url', '')),
            'accessibilita_disabili': _clean(row.get('disabili', '')),
            'source': 'locale',
            'wikidata_id': '',
            'wikipedia_title': '',
            # The circoscrizione dataset carries no access-restriction field --
            # default to public, same rule as an OSM POI with no `access` tag.
            'accesso_pubblico': True,
            # Best-effort inference from the source's own "servizio" bucket --
            # its "Ristorazione e agriturismi" entries are exactly the kind of
            # place that hands out ready-to-eat food (2026-07-25 feedback).
            'offre_asporto': servizio == 'Ristorazione e agriturismi',
            # The circoscrizione dataset never carries a reference-only PoI
            # (parking / off-route trail signage) -- those are OSM-only.
            'solo_riferimento': False,
            'geometry': geom
        })

    gdf_wgs84 = gpd.GeoDataFrame(records_wgs84, crs=WGS84_CRS)
    gdf_utm = gdf_wgs84.to_crs(TARGET_CRS)

    counts = gdf_wgs84['category'].value_counts().to_dict() if len(gdf_wgs84) else {}
    print(f"    Local dataset: {n_raw} raw features -> {len(gdf_dedup)} after removing "
          f"{n_deduped_internal} exact duplicates ({n_missing_geom} dropped for missing geometry).")
    print("    Local POIs categorized:", counts)

    stats = {
        'n_raw': n_raw,
        'n_deduped_internal': n_deduped_internal,
        'n_missing_geom': n_missing_geom,
        'n_final': len(gdf_wgs84)
    }
    return gdf_utm, gdf_wgs84, stats


def deduplicate_and_merge(gdf_local_utm, gdf_local_wgs84, gdf_osm_utm, gdf_osm_wgs84):
    """
    Match local circoscrizione POIs against OSM-derived POIs, preferring an
    exact `osm_id` match ('<element>/<id>', e.g. 'node/13990384642' or
    'way/79387122' -- present on both sides, see load_local_dataset and
    classify_and_transform_pois) whenever the local dataset supplies one
    (2026-07-26 feedback: this is the authoritative identity link, avoids
    fuzzy-match misses/false-positives). Falls back to RapidFuzz name
    similarity (>80%) within 25m otherwise. Matched pairs are fused (local
    hyper-local fields win, OSM geometry/tags/icon are adopted); unmatched
    records on either side are kept standalone.
    """
    print("--> Deduplicating and merging local dataset with OSM POIs...")

    osm_used = set()
    merged_utm, merged_wgs84 = [], []
    n_matched = 0
    n_matched_by_osm_id = 0

    osm_sindex = gdf_osm_utm.sindex if len(gdf_osm_utm) > 0 else None

    # osm_id -> positional index in gdf_osm_utm, for the exact-match path.
    osm_id_to_pos = {}
    if 'osm_id' in gdf_osm_utm.columns:
        for pos, val in enumerate(gdf_osm_utm['osm_id']):
            if val:
                osm_id_to_pos[val] = pos

    for i in range(len(gdf_local_utm)):
        local_row_utm = gdf_local_utm.iloc[i]
        local_row_wgs84 = gdf_local_wgs84.iloc[i]
        local_geom = local_row_utm.geometry
        local_osm_id = local_row_utm.get('osm_id', '')

        best_idx, best_score, matched_by_osm_id = None, 0, False
        if local_osm_id and osm_id_to_pos.get(local_osm_id) is not None and osm_id_to_pos[local_osm_id] not in osm_used:
            best_idx = osm_id_to_pos[local_osm_id]
            matched_by_osm_id = True
        elif osm_sindex is not None and local_geom is not None and not local_geom.is_empty:
            candidate_idx = list(osm_sindex.intersection(local_geom.buffer(DEDUP_RADIUS_M).bounds))
            for j in candidate_idx:
                if j in osm_used:
                    continue
                osm_geom = gdf_osm_utm.iloc[j].geometry
                if local_geom.distance(osm_geom) > DEDUP_RADIUS_M:
                    continue
                score = fuzz.token_sort_ratio(str(local_row_utm['name']).lower(), str(gdf_osm_utm.iloc[j]['name']).lower())
                if score > DEDUP_NAME_THRESHOLD and score > best_score:
                    best_score, best_idx = score, j

        if best_idx is not None:
            osm_used.add(best_idx)
            n_matched += 1
            if matched_by_osm_id:
                n_matched_by_osm_id += 1
            osm_utm_row = gdf_osm_utm.iloc[best_idx]
            osm_wgs84_row = gdf_osm_wgs84.iloc[best_idx]

            fused_utm = local_row_utm.to_dict()
            fused_wgs84 = local_row_wgs84.to_dict()
            for fused, osm_row in ((fused_utm, osm_utm_row), (fused_wgs84, osm_wgs84_row)):
                fused['geometry'] = osm_row.geometry
                fused['osm_tag'] = osm_row['osm_tag']
                fused['icon_name'] = osm_row['icon_name']
                fused['source'] = 'locale+osm'
                # OSM carries the real `access` tag; the local dataset only ever
                # defaults to True, so OSM's value is the more informative one.
                fused['accesso_pubblico'] = osm_row.get('accesso_pubblico', True)
                # OR-combine: either side inferring "yes" is enough to count.
                fused['offre_asporto'] = bool(osm_row.get('offre_asporto', False)) or bool(fused.get('offre_asporto', False))
                fused['solo_riferimento'] = bool(osm_row.get('solo_riferimento', False)) or bool(fused.get('solo_riferimento', False))
                for field in ('image_url', 'orari_apertura', 'wikidata_id', 'wikipedia_title'):
                    if not fused.get(field):
                        fused[field] = osm_row.get(field, '')

            merged_utm.append(fused_utm)
            merged_wgs84.append(fused_wgs84)
        else:
            merged_utm.append(local_row_utm.to_dict())
            merged_wgs84.append(local_row_wgs84.to_dict())

    n_osm_standalone = 0
    for j in range(len(gdf_osm_utm)):
        if j not in osm_used:
            merged_utm.append(gdf_osm_utm.iloc[j].to_dict())
            merged_wgs84.append(gdf_osm_wgs84.iloc[j].to_dict())
            n_osm_standalone += 1

    gdf_merged_utm = gpd.GeoDataFrame(merged_utm, crs=TARGET_CRS)
    gdf_merged_wgs84 = gpd.GeoDataFrame(merged_wgs84, crs=WGS84_CRS)

    stats = {
        'n_local': len(gdf_local_utm),
        'n_osm': len(gdf_osm_utm),
        'n_matched': n_matched,
        'n_matched_by_osm_id': n_matched_by_osm_id,
        'n_local_standalone': len(gdf_local_utm) - n_matched,
        'n_osm_standalone': n_osm_standalone,
        'n_final': len(gdf_merged_utm)
    }
    print(f"    Matched {n_matched} local POIs to OSM features "
          f"({n_matched_by_osm_id} by exact osm_id, "
          f"{n_matched - n_matched_by_osm_id} by <= {DEDUP_RADIUS_M}m + name similarity > {DEDUP_NAME_THRESHOLD}%).")
    print(f"    Merged dataset (pre-manual): {stats['n_final']} POIs "
          f"({stats['n_local_standalone']} local-only, {n_osm_standalone} OSM-only, {n_matched} fused).")
    return gdf_merged_utm, gdf_merged_wgs84, stats


# --- Manually curated territorial POIs --------------------------------------

# Key territorial POIs with no OSM presence AND no equivalent in the local
# circoscrizione dataset. NOTE: the market in Piazza Manci previously injected
# here by hand ("Mercato Zonale del Martedì") has been dropped -- the
# circoscrizione dataset now supplies a more accurate, authoritative
# "Mercato Settimanale" entry (correct Tue/Wed/Sat schedule) that supersedes it.
MANUAL_POIS = [
    {
        'id': 'manual_stoi_chegul',
        'osm_id': '',
        'name': 'Stoi del Chegul (Ricoveri Militari)',
        'category': 'occasionali',
        'sub_type': 'historic',
        'osm_tag': 'manual=historic',
        'icon_name': 'historic',
        'amenity_type': 'Patrimonio Storico & Outdoor',
        'social_function': (
            "Luogo della memoria e tappa chiave dell'escursionismo locale. Connette "
            "la storia del fronte con il turismo sostenibile."
        ),
        'image_url': 'https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Trento_-_Monte_Celva_-_Trottole_02.jpg/640px-Trento_-_Monte_Celva_-_Trottole_02.jpg',
        'indirizzo': 'Monte Celva',
        'orari_apertura': '',
        'contatti': '',
        'sito_web': '',
        'accessibilita_disabili': '',
        'source': 'manuale',
        'wikidata_id': '',
        'wikipedia_title': '',
        'accesso_pubblico': True,
        'offre_asporto': False,
        'solo_riferimento': False,
        'lon': 11.1782,
        'lat': 46.0625
    }
]


def build_manual_pois():
    """Build UTM/WGS84 GeoDataFrames for the hand-curated MANUAL_POIS entries."""
    print("--> Injecting manually curated territorial POIs...")
    records_wgs84 = []
    for poi in MANUAL_POIS:
        meta = {k: v for k, v in poi.items() if k not in ('lon', 'lat')}
        meta['geometry'] = Point(poi['lon'], poi['lat'])
        records_wgs84.append(meta)

    gdf_wgs84 = gpd.GeoDataFrame(records_wgs84, crs=WGS84_CRS)
    gdf_utm = gdf_wgs84.to_crs(TARGET_CRS)
    print(f"    Manual POIs injected: {len(gdf_wgs84)}")
    return gdf_utm, gdf_wgs84


# Field patches for specific, already-existing OSM features that are missing
# one piece of data OSM itself doesn't carry (2026-07-28 feedback: "trovi
# anche la foto" for Teatro Concordia) -- keyed by `osm_id` ('<element>/<id>',
# same identity format `classify_and_transform_pois` assigns), unlike
# MANUAL_POIS (used for territory with NO OSM presence at all, which would
# duplicate this node on the map if used here instead).
OSM_FIELD_OVERRIDES = {
    # Teatro Concordia / "Teatro parrocchiale Concordia" (amenity=theatre,
    # already carries its own `website` tag, picked up automatically -- see
    # the `website` extraction in classify_and_transform_pois). OSM has no
    # image tag for it; this is the photo from the same comune.trento.it page
    # the website links to.
    'node/1999372436': {
        'image_url': (
            'https://spazicomuni.comune.trento.it/var/comunetn/storage/images/comune/'
            'organi-politici/circoscrizioni/circoscrizione-n.-07-povo/sale-della-circoscrizione/'
            'teatro-parrocchiale-concordia/5902639-9-ita-IT/Teatro-parrocchiale-Concordia_imagefull.jpg'
        )
    }
}


def apply_osm_field_overrides(gdf_utm, gdf_wgs84):
    """Patch specific fields (see OSM_FIELD_OVERRIDES) onto matching osm_id rows."""
    n_patched = 0
    for osm_id, fields in OSM_FIELD_OVERRIDES.items():
        mask = gdf_utm['osm_id'] == osm_id
        if not mask.any():
            continue
        for col, value in fields.items():
            gdf_utm.loc[mask, col] = value
            gdf_wgs84.loc[mask, col] = value
        n_patched += 1
    print(f"--> Applied hand-curated field overrides to {n_patched}/{len(OSM_FIELD_OVERRIDES)} known OSM features.")
    return gdf_utm, gdf_wgs84


# --- Wikidata enrichment -----------------------------------------------------

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
# Wikimedia's API etiquette rejects requests without a descriptive User-Agent
# (returns 403) -- see https://meta.wikimedia.org/wiki/User-Agent_policy.
WIKIDATA_HEADERS = {
    'User-Agent': 'PovoCivicHub/1.0 (https://github.com/povocivichub; data pipeline for build_data.py)'
}


def fetch_wikidata_enrichment(qid):
    """Fetch P18 (image) and P856 (official website) claims for a Wikidata QID."""
    try:
        resp = requests.get(WIKIDATA_API, params={
            'action': 'wbgetentities', 'ids': qid, 'props': 'claims', 'format': 'json'
        }, headers=WIKIDATA_HEADERS, timeout=6)
        resp.raise_for_status()
        claims = resp.json()['entities'].get(qid, {}).get('claims', {})

        image_url = ''
        if 'P18' in claims:
            filename = claims['P18'][0]['mainsnak']['datavalue']['value']
            image_url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{filename.replace(' ', '_')}"

        website = ''
        if 'P856' in claims:
            website = claims['P856'][0]['mainsnak']['datavalue']['value']

        return image_url, website
    except Exception:
        return '', ''


def enrich_missing_data(gdf_utm, gdf_wgs84):
    """
    For POIs carrying an OSM `wikidata` tag with still-missing photo/website,
    query Wikidata. Scoped to tagged features only -- a full geographic-
    proximity Commons/Wikidata search across every POI would be slow and
    unreliable to run as part of a repeatable build.
    """
    print("--> Enriching missing photo/website data via Wikidata (wikidata-tagged POIs only)...")
    n_candidates, n_photo, n_website = 0, 0, 0
    cache = {}

    for idx in gdf_utm.index:
        qid = gdf_utm.at[idx, 'wikidata_id']
        if not qid:
            continue
        needs_photo = not gdf_utm.at[idx, 'image_url']
        needs_website = not gdf_utm.at[idx, 'sito_web']
        if not (needs_photo or needs_website):
            continue

        n_candidates += 1
        if qid not in cache:
            cache[qid] = fetch_wikidata_enrichment(qid)
        image_url, website = cache[qid]

        if needs_photo and image_url:
            gdf_utm.at[idx, 'image_url'] = image_url
            gdf_wgs84.at[idx, 'image_url'] = image_url
            n_photo += 1
        if needs_website and website:
            gdf_utm.at[idx, 'sito_web'] = website
            gdf_wgs84.at[idx, 'sito_web'] = website
            n_website += 1

    print(f"    Wikidata candidates checked: {n_candidates} -> {n_photo} photos, {n_website} websites enriched.")
    return gdf_utm, gdf_wgs84, {'n_candidates': n_candidates, 'n_photo': n_photo, 'n_website': n_website}


IMAGE_CHECK_HEADERS = {'User-Agent': WIKIDATA_HEADERS['User-Agent']}


def _image_url_is_reachable(url):
    """HEAD-check an image URL (falling back to a ranged GET if HEAD isn't allowed)."""
    try:
        resp = requests.head(url, headers=IMAGE_CHECK_HEADERS, timeout=6, allow_redirects=True)
        if resp.status_code == 200:
            return True
        if resp.status_code in (403, 405):
            # Some hosts (e.g. Wikimedia Commons' Special:FilePath redirects)
            # reject HEAD; a small ranged GET avoids downloading the full image.
            resp = requests.get(url, headers=IMAGE_CHECK_HEADERS, timeout=6,
                                 stream=True, allow_redirects=True)
            return resp.status_code == 200
        return False
    except Exception:
        return False


def verify_image_urls(gdf_utm, gdf_wgs84):
    """
    Verify every PoI's `image_url` actually resolves (2026-07-25 feedback).
    Broken links are cleared to '' -- the frontend then falls back to a drawn
    placeholder (colored badge + icon emoji) instead of a dead <img>.
    """
    print("--> Verifying PoI image URLs are reachable...")
    n_checked, n_broken = 0, 0
    cache = {}

    for idx in gdf_utm.index:
        url = gdf_utm.at[idx, 'image_url']
        if not url:
            continue

        n_checked += 1
        if url not in cache:
            cache[url] = _image_url_is_reachable(url)
        if not cache[url]:
            gdf_utm.at[idx, 'image_url'] = ''
            gdf_wgs84.at[idx, 'image_url'] = ''
            n_broken += 1

    print(f"    Image URLs checked: {n_checked} -> {n_broken} broken (cleared, frontend uses a placeholder).")
    return gdf_utm, gdf_wgs84, {'n_checked': n_checked, 'n_broken': n_broken}


# Tobler's hiking function (1993), offset by +0.05 the same way the edge-weight
# loop below applies it -- factored out so the "flat ground" baseline used for
# the per-PoI fatica index (see calculate_accessibility_distances) is provably
# the same formula, evaluated at grade=0, rather than a separately-hardcoded
# number that could drift out of sync.
def tobler_speed_kmh(grade):
    return 6.0 * math.exp(-3.5 * abs(grade + 0.05))


FLAT_WALK_SPEED_MS = tobler_speed_kmh(0.0) / 3.6


def _sample_raster_at_points(src, dtm_arr, nodata, xs, ys):
    """Nearest-pixel DTM lookup for a batch of UTM (x, y) points, 0.0 if out of bounds/nodata."""
    values = []
    for x, y in zip(xs, ys):
        try:
            row, col = src.index(x, y)
            if 0 <= row < src.height and 0 <= col < src.width:
                val = dtm_arr[row, col]
                if nodata is not None and val == nodata:
                    val = 0.0
            else:
                val = 0.0
        except Exception:
            val = 0.0
        values.append(float(val))
    return values


def integrate_dtm_and_tobler(G_utm, dtm_path, gdf_pois_utm=None):
    """
    Integrate DTM raster, compute Tobler travel times on pedestrian edges, and
    (if gdf_pois_utm is given) sample each PoI's own altitude directly from the
    raster -- reuses the single rasterio.open() rather than opening the file
    twice.
    """
    print(f"--> Integrating DTM raster ({dtm_path}) and computing Tobler travel times...")
    with rasterio.open(dtm_path) as src:
        dtm_arr = src.read(1)
        nodata = src.nodata

        node_elevations = {}
        for node, data in G_utm.nodes(data=True):
            x, y = data['x'], data['y']
            try:
                row, col = src.index(x, y)
                if 0 <= row < src.height and 0 <= col < src.width:
                    val = dtm_arr[row, col]
                    if nodata is not None and val == nodata:
                        val = 0.0
                else:
                    val = 0.0
            except Exception:
                val = 0.0
            node_elevations[node] = float(val)

        nx.set_node_attributes(G_utm, node_elevations, 'elevation')

        for u, v, k, data in G_utm.edges(keys=True, data=True):
            length = max(float(data.get('length', 1.0)), 0.1)
            z_u = node_elevations.get(u, 0.0)
            z_v = node_elevations.get(v, 0.0)
            grade = (z_v - z_u) / length
            speed_kmh = tobler_speed_kmh(grade)
            travel_time = length / max(speed_kmh / 3.6, 0.001)

            data['grade'] = grade
            data['travel_time'] = travel_time

        if gdf_pois_utm is not None and len(gdf_pois_utm) > 0:
            poi_xs = [g.x for g in gdf_pois_utm.geometry]
            poi_ys = [g.y for g in gdf_pois_utm.geometry]
            gdf_pois_utm['altitudine_m'] = np.round(
                _sample_raster_at_points(src, dtm_arr, nodata, poi_xs, poi_ys), 1
            )

    print("    DTM integration and Tobler travel time calculations complete.")
    return G_utm, gdf_pois_utm


def parse_gtfs_time(time_str):
    try:
        parts = str(time_str).strip().split(':')
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except Exception:
        return -1


def process_gtfs_feeds(gdf_utm):
    """Process GTFS feeds for peak and off-peak transit passages within Povo + 300m."""
    print("--> Processing GTFS feeds (Urban & Extraurban)...")
    buffer_poly = gdf_utm.geometry.union_all().buffer(300)

    gtfs_feeds = [
        ('urbano', GTFS_URBANO_INPUT),
        ('extraurbano', GTFS_EXTRAURBANO_INPUT)
    ]

    combined_stops_list = []

    for prefix, feed_path in gtfs_feeds:
        if not os.path.exists(feed_path):
            continue

        with zipfile.ZipFile(feed_path) as z:
            stops = pd.read_csv(z.open('stops.txt'))
            trips = pd.read_csv(z.open('trips.txt'))
            stop_times = pd.read_csv(z.open('stop_times.txt'))
            cal = pd.read_csv(z.open('calendar.txt')) if 'calendar.txt' in z.namelist() else pd.DataFrame()

            stops['unique_stop_id'] = prefix + '_' + stops['stop_id'].astype(str)
            stop_times['unique_stop_id'] = prefix + '_' + stop_times['stop_id'].astype(str)
            trips['unique_trip_id'] = prefix + '_' + trips['trip_id'].astype(str)
            stop_times['unique_trip_id'] = prefix + '_' + stop_times['trip_id'].astype(str)

            gdf_stops = gpd.GeoDataFrame(
                stops,
                geometry=gpd.points_from_xy(stops.stop_lon, stops.stop_lat),
                crs=WGS84_CRS
            ).to_crs(TARGET_CRS)

            filtered_stops = gdf_stops[gdf_stops.geometry.within(buffer_poly)].copy()
            if len(filtered_stops) == 0:
                continue

            target_stop_ids = set(filtered_stops['unique_stop_id'])
            st = stop_times[stop_times['unique_stop_id'].isin(target_stop_ids)].copy()
            st = st.merge(trips[['unique_trip_id', 'service_id']], on='unique_trip_id', how='left')

            if not cal.empty:
                st = st.merge(cal, on='service_id', how='left')

            st['sec'] = st['departure_time'].apply(parse_gtfs_time)

            is_weekday = (st.get('monday', 1) == 1) | (st.get('tuesday', 1) == 1) | (st.get('wednesday', 1) == 1) | (st.get('thursday', 1) == 1) | (st.get('friday', 1) == 1)
            is_peak_time = (st['sec'] >= 7 * 3600) & (st['sec'] <= 9 * 3600)
            is_evening_time = (st['sec'] >= 18 * 3600) & (st['sec'] <= 23 * 3600)
            is_weekend = (st.get('saturday', 0) == 1) | (st.get('sunday', 0) == 1)

            is_peak = is_weekday & is_peak_time
            is_offpeak = is_evening_time | is_weekend

            peak_counts = st[is_peak].groupby('unique_stop_id').size().to_dict()
            offpeak_counts = st[is_offpeak].groupby('unique_stop_id').size().to_dict()

            filtered_stops['peak_passages'] = filtered_stops['unique_stop_id'].map(lambda x: peak_counts.get(x, 0))
            filtered_stops['offpeak_passages'] = filtered_stops['unique_stop_id'].map(lambda x: offpeak_counts.get(x, 0))
            filtered_stops['feed'] = prefix

            combined_stops_list.append(filtered_stops)

    if combined_stops_list:
        combined_gtfs_stops = pd.concat(combined_stops_list, ignore_index=True)
    else:
        combined_gtfs_stops = gpd.GeoDataFrame(columns=['stop_id', 'stop_name', 'peak_passages', 'offpeak_passages', 'geometry'], crs=TARGET_CRS)

    print(f"    GTFS Processing complete: {len(combined_gtfs_stops)} stops in Povo+300m buffer.")
    return combined_gtfs_stops


def generate_h3_grid(gdf_wgs84, gdf_utm, res=9):
    """Generate Uber H3 resolution 9 hexagon grid clipped to Povo boundary."""
    print(f"--> Generating Uber H3 grid (resolution {res})...")
    poly_wgs84 = gdf_wgs84.geometry.union_all()

    geom_json = shapely.geometry.mapping(poly_wgs84)
    h3_shape = h3.geo_to_h3shape(geom_json)
    cells = h3.h3shape_to_cells(h3_shape, res=res)

    features = []
    for cell in cells:
        boundary = h3.cell_to_boundary(cell)
        poly = Polygon([(lng, lat) for lat, lng in boundary])
        features.append({'h3_id': cell, 'geometry': poly})

    gdf_hex = gpd.GeoDataFrame(features, crs=WGS84_CRS)
    gdf_hex_utm = gdf_hex.to_crs(TARGET_CRS)

    povo_poly_utm = gdf_utm.geometry.union_all()
    gdf_clipped = gpd.clip(gdf_hex_utm, povo_poly_utm).copy()
    gdf_clipped = gdf_clipped[~gdf_clipped.is_empty].reset_index(drop=True)

    print(f"    Generated {len(gdf_clipped)} H3 resolution {res} hexagons inside Povo boundary.")
    return gdf_clipped


def calculate_gtfs_accessibility(gdf_hex_utm, G_utm, gtfs_stops):
    """Connect GTFS stops to pedestrian network and compute Tobler walking travel time access."""
    if len(gtfs_stops) == 0:
        zeros = np.zeros(len(gdf_hex_utm))
        return zeros, zeros

    stop_xs = [pt.x for pt in gtfs_stops.geometry]
    stop_ys = [pt.y for pt in gtfs_stops.geometry]
    stop_nodes = ox.distance.nearest_nodes(G_utm, stop_xs, stop_ys)

    node_peak_supply = {node: 0.0 for node in G_utm.nodes()}
    node_offpeak_supply = {node: 0.0 for node in G_utm.nodes()}

    for stop_node, (_, stop_row) in zip(stop_nodes, gtfs_stops.iterrows()):
        peak_passages = float(stop_row['peak_passages'])
        offpeak_passages = float(stop_row['offpeak_passages'])

        if peak_passages <= 0 and offpeak_passages <= 0:
            continue

        lengths = nx.single_source_dijkstra_path_length(G_utm, stop_node, weight='travel_time')

        for target_node, walk_time_sec in lengths.items():
            decay = math.exp(-walk_time_sec / 300.0)
            if peak_passages > 0:
                node_peak_supply[target_node] += peak_passages * decay
            if offpeak_passages > 0:
                node_offpeak_supply[target_node] += offpeak_passages * decay

    hex_centroids_x = [row.geometry.centroid.x for _, row in gdf_hex_utm.iterrows()]
    hex_centroids_y = [row.geometry.centroid.y for _, row in gdf_hex_utm.iterrows()]
    hex_nodes = ox.distance.nearest_nodes(G_utm, hex_centroids_x, hex_centroids_y)

    peak_access = np.array([node_peak_supply.get(n, 0.0) for n in hex_nodes])
    offpeak_access = np.array([node_offpeak_supply.get(n, 0.0) for n in hex_nodes])

    return peak_access, offpeak_access


def calculate_accessibility_distances(gdf_pois_utm, G_utm, raw_pois_utm):
    """
    Compute, for every POI, the shortest pedestrian-network distance (metres) to
    the nearest bus/rail stop (d_bus_m) and to the nearest parking lot
    (d_parking_m). Reuses the pedestrian graph already fetched for the boundary
    area (no redundant second ox.graph_from_place download) and treats it as
    undirected, since one-way tagging on footways doesn't meaningfully restrict
    where a pedestrian can walk.
    NOTE: d_parking_m is a distance indicator only (2026-07-25 feedback: fetch
    parking for accessibility-distance purposes, but never score/display it as
    a PoI) -- it does not feed W_cat/ICC or any social/mix indicator, exactly
    like the old P_park term that was dropped entirely from those formulas.
    """
    print("--> Calculating network accessibility distances to bus stops and parking...")
    G_undirected = G_utm.to_undirected()

    def nodes_for(mask):
        if not isinstance(mask, pd.Series) or not mask.any():
            return []
        subset = raw_pois_utm[mask]
        xs = [g.centroid.x for g in subset.geometry]
        ys = [g.centroid.y for g in subset.geometry]
        return list(ox.distance.nearest_nodes(G_utm, xs, ys))

    highway_col = raw_pois_utm['highway'] if 'highway' in raw_pois_utm.columns else None
    railway_col = raw_pois_utm['railway'] if 'railway' in raw_pois_utm.columns else None
    pt_col = raw_pois_utm['public_transport'] if 'public_transport' in raw_pois_utm.columns else None
    amenity_col = raw_pois_utm['amenity'] if 'amenity' in raw_pois_utm.columns else None

    bus_mask = pd.Series(False, index=raw_pois_utm.index)
    if highway_col is not None:
        bus_mask |= (highway_col == 'bus_stop')
    if railway_col is not None:
        bus_mask |= railway_col.isin(['station', 'halt'])
    if pt_col is not None:
        bus_mask |= (pt_col == 'platform')

    parking_mask = pd.Series(False, index=raw_pois_utm.index)
    if amenity_col is not None:
        parking_mask |= (amenity_col == 'parking')

    bus_nodes = set(nodes_for(bus_mask))
    parking_nodes = set(nodes_for(parking_mask))
    print(f"    Accessibility sources: {len(bus_nodes)} bus/rail stop nodes, {len(parking_nodes)} parking-lot nodes.")

    dist_to_bus = nx.multi_source_dijkstra_path_length(G_undirected, bus_nodes, weight='length') if bus_nodes else {}
    dist_to_parking = nx.multi_source_dijkstra_path_length(G_undirected, parking_nodes, weight='length') if parking_nodes else {}

    # Tobler-weighted (slope-aware) walking TIME to the same sources, reusing
    # the 'travel_time' edge attribute computed in integrate_dtm_and_tobler --
    # this is what the per-PoI "fatica" (effort) index below is derived from,
    # alongside the flat-distance d_bus_m/d_parking_m above.
    time_to_bus = (nx.multi_source_dijkstra_path_length(G_undirected, bus_nodes, weight='travel_time')
                   if bus_nodes else {})
    time_to_parking = (nx.multi_source_dijkstra_path_length(G_undirected, parking_nodes, weight='travel_time')
                        if parking_nodes else {})

    poi_xs = [g.x for g in gdf_pois_utm.geometry]
    poi_ys = [g.y for g in gdf_pois_utm.geometry]
    poi_nodes = ox.distance.nearest_nodes(G_utm, poi_xs, poi_ys)

    FAR = 5000.0  # metres: fallback when unreachable within the extracted graph
    FAR_TIME = FAR / FLAT_WALK_SPEED_MS  # matching time fallback, same FAR distance at flat pace
    d_bus = np.array([dist_to_bus.get(n, FAR) for n in poi_nodes])
    d_parking = np.array([dist_to_parking.get(n, FAR) for n in poi_nodes])
    t_bus = np.array([time_to_bus.get(n, FAR_TIME) for n in poi_nodes])
    t_parking = np.array([time_to_parking.get(n, FAR_TIME) for n in poi_nodes])

    gdf_pois_utm['d_bus_m'] = np.round(d_bus, 1)
    gdf_pois_utm['d_parking_m'] = np.round(d_parking, 1)
    gdf_pois_utm['t_bus_min'] = np.round(t_bus / 60.0, 1)
    gdf_pois_utm['t_parking_min'] = np.round(t_parking / 60.0, 1)

    # "Fatica" (effort) index: how much longer the real, slope-aware walk
    # takes versus a flat-ground walk covering the same network distance, as a
    # percentage. 0% means effectively flat; clipped at 0 on the (occasional,
    # short-downhill) side where Tobler's function briefly outpaces the flat
    # baseline, since a negative "effort" percentage would read as a confusing
    # double-negative to a lay user rather than "easier than flat".
    flat_time_bus = np.maximum(d_bus / FLAT_WALK_SPEED_MS, 0.001)
    flat_time_parking = np.maximum(d_parking / FLAT_WALK_SPEED_MS, 0.001)
    gdf_pois_utm['fatica_bus_pct'] = np.round(np.clip((t_bus / flat_time_bus - 1.0) * 100, 0, None), 0)
    gdf_pois_utm['fatica_parking_pct'] = np.round(np.clip((t_parking / flat_time_parking - 1.0) * 100, 0, None), 0)
    return gdf_pois_utm


def calculate_icc(gdf_pois_utm):
    """
    Compute the Indice di Classe Civica (ICC) per POI on a 0-100 scale.
    Original formula was 0.40*W_cat + 0.25*A_bus + 0.15*P_park + 0.20*Q_data;
    the P_park term was dropped entirely (2026-07-25: parking isn't mapped or
    scored anymore), and the remaining weights renormalized to sum to 1:
    ICC = (0.4706*W_cat + 0.2941*A_bus + 0.2353*Q_data) * 100
    """
    print("--> Calculating Indice di Classe Civica (ICC)...")

    remaining = 0.40 + 0.25 + 0.20  # = 0.85, the original weights minus P_park's 0.15
    w_cat_weight = 0.40 / remaining
    a_bus_weight = 0.25 / remaining
    q_data_weight = 0.20 / remaining

    w_cat = gdf_pois_utm['category'].map(W_CAT).fillna(0.5)
    a_bus = (1 - gdf_pois_utm['d_bus_m'] / 800.0).clip(lower=0, upper=1)

    def field_filled(val):
        s = str(val).strip()
        return s not in ('', 'nan', '-', 'None')

    q_data = gdf_pois_utm.apply(
        lambda row: sum(field_filled(row.get(f, '')) for f in KEY_QUALITY_FIELDS) / len(KEY_QUALITY_FIELDS),
        axis=1
    )

    icc = (w_cat_weight * w_cat + a_bus_weight * a_bus + q_data_weight * q_data) * 100

    gdf_pois_utm['w_cat'] = np.round(w_cat, 3)
    gdf_pois_utm['a_bus'] = np.round(a_bus, 3)
    gdf_pois_utm['q_data'] = np.round(q_data, 3)
    gdf_pois_utm['icc_score'] = np.round(icc, 1)

    print("    ICC medio per categoria:")
    print(gdf_pois_utm.groupby('category')['icc_score'].mean().round(1).to_string())
    return gdf_pois_utm


def calculate_scores_and_mixite(gdf_hex_utm, G_utm, gdf_pois_utm, gtfs_stops):
    """
    Compute res_score, comm_score, occa_score weighted with massive POIs & GTFS frequency,
    and compute Shannon Entropy mix_index per hexagon.
    """
    print("--> Calculating weighted hexagon scores and Mixité Index with massive POIs...")

    # Places of worship, anything not openly accessible (access=private/no/
    # customers), and unnamed generic shelters don't represent a neighbourhood
    # service available to the general population, so they're excluded from
    # the indicator calculation entirely (2026-07-25 feedback) -- they still
    # show up on the map/table, just don't count toward
    # res_score/comm_score/occa_score/mix_index. An unnamed "Rifugio /
    # Pensilina" (amenity=shelter) is ambiguous clutter unless it's actually a
    # bus-stop shelter -- but those were already reclassified to
    # category='pendolari' in classify_and_transform_pois, so checking
    # category=='cross_civic' here only catches the non-bus-shelter ones.
    # `solo_riferimento` (parking, off-route trail signage -- see
    # classify_and_transform_pois) is the same kind of "shown but not
    # counted" PoI as the other three conditions here: real, queryable map
    # markers that don't represent a neighbourhood service in their own right.
    excluded_mask = (
        (gdf_pois_utm['sub_type'] == 'place_of_worship') |
        (gdf_pois_utm['accesso_pubblico'] == False) |  # noqa: E712
        ((gdf_pois_utm['sub_type'] == 'shelter') & (gdf_pois_utm['category'] == 'cross_civic') & (gdf_pois_utm['name'] == '')) |
        (gdf_pois_utm['solo_riferimento'] == True)  # noqa: E712
    )
    gdf_indic = gdf_pois_utm[~excluded_mask]
    print(f"    PoI esclusi dal calcolo indicatori (luoghi di culto, accesso non pubblico, "
          f"rifugi/pensiline senza nome, o PoI di solo riferimento): {excluded_mask.sum()}")

    # Filter POIs by category
    gdf_res = gdf_indic[gdf_indic['category'] == 'residenti']
    gdf_comm = gdf_indic[gdf_indic['category'] == 'pendolari']
    gdf_occa = gdf_indic[gdf_indic['category'] == 'occasionali']

    # Shared/third-place PoIs (see PUBLIC_INTEREST_SUB_TYPES) cross-feed every
    # axis they don't already belong to at a reduced weight -- a category
    # alone doesn't capture that e.g. a public football pitch (residenti)
    # also interests pendolari/occasionali, so this dimension is layered on
    # top of, not instead of, the category split above.
    gdf_shared = gdf_indic[gdf_indic['sub_type'].isin(PUBLIC_INTEREST_SUB_TYPES)]
    gdf_shared_for_res = gdf_shared[gdf_shared['category'] != 'residenti']
    gdf_shared_for_occa = gdf_shared[gdf_shared['category'] != 'occasionali']

    # Picnic areas only make sense as a pendolari lunch-break draw if there's
    # actually takeaway food nearby, within a ~5-minute walk (2026-07-25
    # feedback) -- unlike every other PUBLIC_INTEREST_SUB_TYPES entry, a
    # picnic site's contribution to comm_score specifically is gated on this
    # proximity check (it still freely cross-feeds res_score, and occa_score
    # is its own home axis, unaffected).
    WALK_5MIN_M = 400.0  # ~5 minutes at a standard ~80 m/min walking pace
    takeaway_pois = gdf_indic[gdf_indic['offre_asporto'] == True]  # noqa: E712
    picnic_mask = gdf_shared['sub_type'] == 'picnic_site'
    picnic_near_takeaway_ids = set()
    if picnic_mask.any() and len(takeaway_pois) > 0:
        G_undirected_food = G_utm.to_undirected()
        takeaway_nodes = set(ox.distance.nearest_nodes(
            G_utm, [g.x for g in takeaway_pois.geometry], [g.y for g in takeaway_pois.geometry]
        ))
        dist_to_takeaway = nx.multi_source_dijkstra_path_length(G_undirected_food, takeaway_nodes, weight='length')

        picnic_pois = gdf_shared[picnic_mask]
        picnic_nodes = ox.distance.nearest_nodes(
            G_utm, [g.x for g in picnic_pois.geometry], [g.y for g in picnic_pois.geometry]
        )
        for poi_id, node in zip(picnic_pois.index, picnic_nodes):
            if dist_to_takeaway.get(node, math.inf) <= WALK_5MIN_M:
                picnic_near_takeaway_ids.add(poi_id)
    print(f"    Aree picnic vicine (<= {WALK_5MIN_M:.0f}m) a cibo d'asporto, rilevanti anche per pendolari: "
          f"{len(picnic_near_takeaway_ids)} / {picnic_mask.sum()}")

    picnic_eligible_for_comm = ~picnic_mask | gdf_shared.index.isin(picnic_near_takeaway_ids)
    gdf_shared_for_comm = gdf_shared[(gdf_shared['category'] != 'pendolari') & picnic_eligible_for_comm]

    def compute_raw_poi_score(hex_geom, pois_gdf):
        if len(pois_gdf) == 0:
            return 0.0
        centroid = hex_geom.centroid
        spatial_index = pois_gdf.sindex
        possible_matches_index = list(spatial_index.intersection(hex_geom.bounds))
        possible_matches = pois_gdf.iloc[possible_matches_index]
        exact_matches = possible_matches[possible_matches.intersects(hex_geom)]
        count_inside = len(exact_matches)

        distances = pois_gdf.distance(centroid)
        min_dist = distances.min() if len(distances) > 0 else 1000.0
        proximity = math.exp(-min_dist / 250.0)

        return (count_inside * 2.0) + proximity

    raw_res_poi = np.array([compute_raw_poi_score(r.geometry, gdf_res) for _, r in gdf_hex_utm.iterrows()])
    raw_comm_poi = np.array([compute_raw_poi_score(r.geometry, gdf_comm) for _, r in gdf_hex_utm.iterrows()])
    raw_occa_poi = np.array([compute_raw_poi_score(r.geometry, gdf_occa) for _, r in gdf_hex_utm.iterrows()])
    raw_shared_res = np.array([compute_raw_poi_score(r.geometry, gdf_shared_for_res) for _, r in gdf_hex_utm.iterrows()])
    raw_shared_comm = np.array([compute_raw_poi_score(r.geometry, gdf_shared_for_comm) for _, r in gdf_hex_utm.iterrows()])
    raw_shared_occa = np.array([compute_raw_poi_score(r.geometry, gdf_shared_for_occa) for _, r in gdf_hex_utm.iterrows()])

    # GTFS walking accessibility
    peak_transit, offpeak_transit = calculate_gtfs_accessibility(gdf_hex_utm, G_utm, gtfs_stops)

    # Combine scores: each axis's own-category PoIs count fully, plus a
    # reduced (0.5x) contribution from every shared/third-place PoI that
    # belongs to a *different* category -- see PUBLIC_INTEREST_SUB_TYPES.
    res_combined = raw_res_poi + (0.5 * raw_shared_res) + offpeak_transit
    comm_combined = raw_comm_poi + (0.5 * raw_shared_comm) + peak_transit
    occa_combined = raw_occa_poi + (0.5 * raw_shared_occa) + offpeak_transit

    def normalize(arr):
        min_val, max_val = arr.min(), arr.max()
        if max_val > min_val:
            return (arr - min_val) / (max_val - min_val)
        return np.zeros_like(arr)

    norm_res = normalize(res_combined)
    norm_comm = normalize(comm_combined)
    norm_occa = normalize(occa_combined)

    mix_index = []
    max_entropy = math.log(3.0)
    # Below this combined-score floor there isn't enough real signal (POIs
    # inside/near the hex) to call the area "mixed" -- with res/comm/occa all
    # near-zero, their *relative* proportions can look artificially balanced
    # (Shannon entropy maxes out on near-empty countryside just as readily as
    # on a genuinely lively square), which would otherwise flag most of a fine
    # H3 res-10 grid as "mixed" (2026-07-25: this happened in practice, ~76%
    # of hexagons). Below the floor, treat the hex as having no clear
    # vocation yet rather than a false-positive mixed one.
    SIGNAL_FLOOR = 0.15

    for r, c, o in zip(norm_res, norm_comm, norm_occa):
        total = r + c + o
        if total <= SIGNAL_FLOOR:
            mix_index.append(0.0)
        else:
            p_r = r / total
            p_c = c / total
            p_o = o / total

            h_val = 0.0
            for p in [p_r, p_c, p_o]:
                if p > 0:
                    h_val -= p * math.log(p)

            mix_index.append(max(0.0, min(1.0, h_val / max_entropy)))

    gdf_hex_utm['res_score'] = np.round(norm_res, 4)
    gdf_hex_utm['comm_score'] = np.round(norm_comm, 4)
    gdf_hex_utm['occa_score'] = np.round(norm_occa, 4)
    gdf_hex_utm['mix_index'] = np.round(mix_index, 4)

    # Make the cross-feed above an explicit, queryable per-PoI attribute
    # instead of just an internal scoring detail (2026-07-25 feedback:
    # "dobbiamo mettere categoria principale ed una secondaria che indica per
    # quale altra categoria [conta]"). A PoI's `categoria_secondaria` lists
    # every OTHER category its own axis-membership above actually feeds into
    # -- empty for anything not in PUBLIC_INTEREST_SUB_TYPES (or a picnic
    # site too far from takeaway food to count for pendolari), and excluded
    # PoIs (place_of_worship/private) also end up empty since they were never
    # part of gdf_shared in the first place.
    secondary_res_ids = set(gdf_shared_for_res.index)
    secondary_comm_ids = set(gdf_shared_for_comm.index)
    secondary_occa_ids = set(gdf_shared_for_occa.index)

    def compute_secondary_categories(idx):
        cats = []
        if idx in secondary_res_ids:
            cats.append('residenti')
        if idx in secondary_comm_ids:
            cats.append('pendolari')
        if idx in secondary_occa_ids:
            cats.append('occasionali')
        # Comma-joined string, not a list -- GeoJSON/OGR property serialization
        # doesn't handle list-typed columns cleanly, and a plain string is
        # just as easy for the frontend to split on ',' when non-empty.
        return ','.join(cats)

    gdf_pois_utm['categoria_secondaria'] = gdf_pois_utm.index.map(compute_secondary_categories)

    print("    Score calculations and Mixité Index complete.")
    return gdf_hex_utm, gdf_pois_utm


def export_results(gdf_hex_utm, gdf_boundary_utm, gdf_pois_wgs84):
    """Reproject to EPSG:4326 and export GeoJSON files to public/data/."""
    print("--> Exporting results to public/data/ (EPSG:4326)...")
    gdf_hex_wgs84 = gdf_hex_utm.to_crs(WGS84_CRS)
    gdf_boundary_wgs84 = gdf_boundary_utm.to_crs(WGS84_CRS)

    os.makedirs("public/data", exist_ok=True)

    print("--> Exporting", GRID_OUTPUT)
    gdf_hex_wgs84.to_file(GRID_OUTPUT, driver="GeoJSON")

    print("--> Exporting", BOUNDARY_OUTPUT)
    gdf_boundary_wgs84.to_file(BOUNDARY_OUTPUT, driver="GeoJSON")

    print("--> Exporting", POIS_OUTPUT)
    gdf_pois_wgs84.to_file(POIS_OUTPUT, driver="GeoJSON")

    print("--> All exports completed successfully!")


def write_report(path, stats, gdf_pois_wgs84):
    """Write a Markdown processing report: coverage, enrichment, ICC, anomalies."""
    print("--> Writing processing report to", path)
    local_stats = stats['local']
    dedup_stats = stats['dedup']
    enrich_stats = stats['enrich']
    image_check_stats = stats['image_check']
    manual_count = stats['manual_count']
    n_private_sport_removed = stats['n_private_sport_removed']
    total_final = dedup_stats['n_final'] + manual_count - n_private_sport_removed

    lines = []
    lines.append("# Report di Elaborazione — Povo Civic Hub")
    lines.append("")
    lines.append("_Generato automaticamente da `python_pipeline/build_data.py`._")
    lines.append("")

    lines.append("## 1. Copertura dei PoI")
    lines.append("")
    lines.append(f"- PoI grezzi nel file locale (Circoscrizione di Povo): **{local_stats['n_raw']}**")
    lines.append(f"- Duplicati esatti rimossi dal dataset locale: **{local_stats['n_deduped_internal']}**")
    lines.append(f"- PoI locali dopo la deduplica interna: **{local_stats['n_final']}**")
    lines.append(f"- PoI estratti da OpenStreetMap: **{dedup_stats['n_osm']}**")
    lines.append(
        f"- Corrispondenze locale ↔ OSM fuse: **{dedup_stats['n_matched']}** "
        f"(di cui **{dedup_stats['n_matched_by_osm_id']}** per `osm_id` esatto, "
        f"**{dedup_stats['n_matched'] - dedup_stats['n_matched_by_osm_id']}** per prossimità "
        f"<= {DEDUP_RADIUS_M}m + similarità nome > {DEDUP_NAME_THRESHOLD}%)"
    )
    lines.append(f"- PoI solo locali (nessun corrispondente OSM): **{dedup_stats['n_local_standalone']}**")
    lines.append(f"- PoI solo OSM (nessun corrispondente locale): **{dedup_stats['n_osm_standalone']}**")
    lines.append(f"- PoI iniettati manualmente (assenti da OSM e dal dataset locale): **{manual_count}**")
    lines.append(
        f"- Impianti sportivi ad accesso privato rimossi (non solo esclusi dagli indicatori, "
        f"eliminati dal dataset): **{n_private_sport_removed}**"
    )
    lines.append(f"- **Totale PoI finali nel dataset unificato: {total_final}**")
    lines.append("")

    lines.append("## 2. Arricchimento Dati (Wikidata)")
    lines.append("")
    lines.append(f"- PoI con tag `wikidata` verificati: **{enrich_stats['n_candidates']}**")
    lines.append(f"- Foto recuperate automaticamente: **{enrich_stats['n_photo']}**")
    lines.append(f"- Siti web recuperati automaticamente: **{enrich_stats['n_website']}**")
    lines.append(
        "- _Nota: l'arricchimento è limitato ai PoI con tag `wikidata` OSM espliciti. "
        "Una ricerca per prossimità geografica su Wikidata/Commons per tutti i PoI non è "
        "stata implementata: sarebbe troppo lenta e poco affidabile (falsi positivi) per "
        "una pipeline eseguita ripetutamente._"
    )
    lines.append("")

    lines.append("## 2b. Verifica Immagini")
    lines.append("")
    lines.append(f"- PoI con `image_url` verificati: **{image_check_stats['n_checked']}**")
    lines.append(f"- Link non raggiungibili (ripuliti, il frontend mostra un placeholder): **{image_check_stats['n_broken']}**")
    lines.append("")

    lines.append("## 3. Qualità del Dato")
    lines.append("")
    for field in KEY_QUALITY_FIELDS:
        filled = gdf_pois_wgs84[field].apply(lambda v: str(v).strip() not in ('', 'nan', '-', 'None')).sum()
        lines.append(f"- `{field}` compilato: **{filled} / {len(gdf_pois_wgs84)}**")
    lines.append("")

    lines.append("## 4. Indice di Classe Civica (ICC) medio per categoria")
    lines.append("")
    lines.append("| Categoria | W_cat | ICC medio | N. PoI |")
    lines.append("|---|---|---|---|")
    for cat, w in W_CAT.items():
        subset = gdf_pois_wgs84[gdf_pois_wgs84['category'] == cat]
        mean_icc = subset['icc_score'].mean() if len(subset) else 0.0
        lines.append(f"| {cat} | {w:.1f} | {mean_icc:.1f} | {len(subset)} |")
    lines.append("")

    lines.append("## 5. Anomalie Rilevate")
    lines.append("")
    no_geom = gdf_pois_wgs84[gdf_pois_wgs84.geometry.isna() | gdf_pois_wgs84.geometry.is_empty]
    if len(no_geom) > 0:
        lines.append(f"- **{len(no_geom)} PoI privi di coordinate valide** (esclusi dal dataset finale).")
    else:
        lines.append("- Nessun PoI privo di coordinate valide.")
    lines.append(
        f"- Il file locale conteneva {local_stats['n_raw']} feature per sole "
        f"{local_stats['n_final']} entità reali (ogni PoI era duplicato esattamente 2 volte "
        "nell'export sorgente, con proprietà identiche); tra i duplicati, alcuni presentavano "
        "coordinate leggermente diverse tra le due copie (fino a ~400m in un caso, 'Pizza Rio') "
        "— è stata mantenuta la prima occorrenza."
    )
    lines.append(
        "- Il PoI manuale \"Mercato Zonale del Martedì\" (iniettato a mano in una versione "
        "precedente della pipeline) è stato rimosso: il dataset locale fornisce ora un "
        "\"Mercato Settimanale\" più accurato e autorevole (martedì/mercoledì/sabato mattina)."
    )
    lines.append("")

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print("    Report written.")


def drop_private_sport_facilities(gdf_pois_utm, gdf_pois_wgs84):
    """
    Fully remove sport facilities (pitches, courts, sports centres -- see
    SPORT_FACILITY_ICONS) whose OSM `access` tag marks them non-public. Unlike
    the broader accesso_pubblico exclusion in calculate_scores_and_mixite
    (which keeps private PoIs visible on the map/table but drops them from the
    indicator calculation), these are dropped from the dataset entirely
    (2026-07-26 feedback): a private sport facility isn't just "not a
    neighbourhood service," it's stricter than even a residenti-only one --
    only the owner's own guests can use it, so it has no place being shown as
    a usable community amenity at all.
    """
    mask = gdf_pois_utm['icon_name'].isin(SPORT_FACILITY_ICONS) & (gdf_pois_utm['accesso_pubblico'] == False)  # noqa: E712
    n_removed = int(mask.sum())
    print(f"--> Removing private-access sport facilities entirely (not just from indicators): {n_removed}")
    gdf_pois_utm = gdf_pois_utm.loc[~mask].reset_index(drop=True)
    gdf_pois_wgs84 = gdf_pois_wgs84.loc[~mask.values].reset_index(drop=True)
    return gdf_pois_utm, gdf_pois_wgs84, n_removed


def main():
    print("=== POVO CIVIC HUB - GEOGRAPHIC DATA ANALYSIS PIPELINE (ICC EDITION) ===")
    gdf_wgs84, gdf_utm = load_boundary()
    G_utm, raw_pois_utm = fetch_osm_graph_and_pois(gdf_wgs84)
    named_routes_buffer = fetch_named_hiking_routes(gdf_wgs84)
    gdf_osm_utm, gdf_osm_wgs84 = classify_and_transform_pois(raw_pois_utm, named_routes_buffer)
    gdf_osm_utm, gdf_osm_wgs84 = apply_osm_field_overrides(gdf_osm_utm, gdf_osm_wgs84)

    gdf_local_utm, gdf_local_wgs84, local_stats = load_local_dataset(LOCAL_DATASET_INPUT)

    gdf_pois_utm, gdf_pois_wgs84, dedup_stats = deduplicate_and_merge(
        gdf_local_utm, gdf_local_wgs84, gdf_osm_utm, gdf_osm_wgs84
    )

    manual_utm, manual_wgs84 = build_manual_pois()
    gdf_pois_utm = gpd.GeoDataFrame(
        pd.concat([gdf_pois_utm, manual_utm], ignore_index=True), geometry='geometry', crs=TARGET_CRS
    )
    gdf_pois_wgs84 = gpd.GeoDataFrame(
        pd.concat([gdf_pois_wgs84, manual_wgs84], ignore_index=True), geometry='geometry', crs=WGS84_CRS
    )

    gdf_pois_utm, gdf_pois_wgs84, n_private_sport_removed = drop_private_sport_facilities(gdf_pois_utm, gdf_pois_wgs84)

    gdf_pois_utm, gdf_pois_wgs84, enrich_stats = enrich_missing_data(gdf_pois_utm, gdf_pois_wgs84)
    gdf_pois_utm, gdf_pois_wgs84, image_check_stats = verify_image_urls(gdf_pois_utm, gdf_pois_wgs84)

    G_utm, gdf_pois_utm = integrate_dtm_and_tobler(G_utm, DTM_INPUT, gdf_pois_utm)
    gdf_pois_wgs84['altitudine_m'] = gdf_pois_utm['altitudine_m'].values
    gtfs_stops = process_gtfs_feeds(gdf_utm)

    gdf_pois_utm = calculate_accessibility_distances(gdf_pois_utm, G_utm, raw_pois_utm)
    for col in ['d_bus_m', 'd_parking_m', 't_bus_min', 't_parking_min', 'fatica_bus_pct', 'fatica_parking_pct']:
        gdf_pois_wgs84[col] = gdf_pois_utm[col].values

    gdf_pois_utm = calculate_icc(gdf_pois_utm)
    for col in ['w_cat', 'a_bus', 'q_data', 'icc_score']:
        gdf_pois_wgs84[col] = gdf_pois_utm[col].values

    gdf_hex_utm = generate_h3_grid(gdf_wgs84, gdf_utm, res=10)
    gdf_hex_scored, gdf_pois_utm = calculate_scores_and_mixite(gdf_hex_utm, G_utm, gdf_pois_utm, gtfs_stops)
    gdf_pois_wgs84['categoria_secondaria'] = gdf_pois_utm['categoria_secondaria'].values

    export_results(gdf_hex_scored, gdf_utm, gdf_pois_wgs84)

    write_report(REPORT_OUTPUT, {
        'local': local_stats,
        'dedup': dedup_stats,
        'enrich': enrich_stats,
        'image_check': image_check_stats,
        'manual_count': len(manual_utm),
        'n_private_sport_removed': n_private_sport_removed
    }, gdf_pois_wgs84)

    print("=== PIPELINE EXECUTED SUCCESSFULLY ===")


if __name__ == "__main__":
    main()
