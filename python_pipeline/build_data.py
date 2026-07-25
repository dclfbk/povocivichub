"""
Povo Civic Hub - Geographic Data Analysis Pipeline (ICC Edition, outdoor-sport focus)

1. ESTRAZIONE OSM AMPLIATA:
   - Downloads Nodes and Polygons (converted to centroids) via OSMnx/Overpass:
     amenity, shop, tourism, leisure, sport=* (any value, not just climbing --
     used to label sports pitches), highway=bus_stop, railway=station/halt,
     place=square, historic, office, public_transport=platform.
   - Benches, viewpoints and recycling points (isole ecologiche) are
     intentionally NOT extracted (2026-07-25 feedback: street-furniture
     noise, not signal for this project's goal). `amenity=parking` IS fetched,
     but only to compute a distance-to-parking
     accessibility indicator (d_parking_m) -- it's never classified/displayed
     as a PoI and never feeds W_cat/ICC/mix_index (see
     classify_and_transform_pois and calculate_accessibility_distances).
   - `tourism=information` trail signage is kept ONLY if it falls within 30m of
     a named trail/track way (fetch_named_hiking_routes) -- otherwise it's
     dropped as clutter.

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
BOUNDARY_INPUT = "raw_data/povo_boundary.geojson"
DTM_INPUT = "raw_data/dtm_povo.tif"
GTFS_URBANO_INPUT = "raw_data/google_transit_urbano_tte.zip"
GTFS_EXTRAURBANO_INPUT = "raw_data/google_transit_extraurbano_tte.zip"
LOCAL_DATASET_INPUT = "raw_data/dati_circoscrizione.geojson"

GRID_OUTPUT = "public/data/povo_grid.json"
BOUNDARY_OUTPUT = "public/data/povo_boundary.json"
POIS_OUTPUT = "public/data/povo_pois.json"
REPORT_OUTPUT = "public/data/report_elaborazione.md"

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

    # 2. Comprehensive POI tags. NOTE: benches, viewpoints and recycling
    # points (isole ecologiche, amenity=recycling) are intentionally excluded
    # (2026-07-25 feedback): they're street-furniture noise for this project's
    # goal, not signal. `sport` is kept as its own column even for
    # `leisure=pitch` features (not just climbing) so pitches can be labelled
    # "Campo da <sport>" instead of the raw OSM word "pitch". `parking` IS
    # fetched (2026-07-25 feedback) but only to compute a distance-to-parking
    # accessibility indicator (see calculate_accessibility_distances) --
    # classify_and_transform_pois explicitly skips it so it never becomes a
    # displayed/scored PoI (no category, no icon, doesn't feed any social
    # indicator).
    tags = {
        'amenity': [
            'university', 'research_institute', 'library', 'school', 'kindergarten',
            'pharmacy', 'post_office', 'townhall', 'community_centre', 'social_facility',
            'cafe', 'restaurant', 'pub', 'bar', 'canteen', 'fast_food', 'bank',
            'public_bookcase', 'drinking_water', 'shelter', 'place_of_worship',
            'theatre', 'arts_centre', 'parking'
        ],
        'shop': [
            'supermarket', 'bakery', 'convenience', 'butcher', 'greengrocer', 'chemist', 'books',
            'copyshop', 'beauty', 'hairdresser', 'deli'
        ],
        'tourism': [
            'information', 'picnic_site', 'alpine_hut', 'wilderness_hut',
            'guest_house', 'hotel', 'attraction', 'museum', 'artwork', 'chalet', 'camp_site'
        ],
        'leisure': ['park', 'playground', 'sports_centre', 'pitch', 'garden', 'nature_reserve', 'amphitheatre'],
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
    ('amenity', 'theatre'): 'theater',
    ('amenity', 'arts_centre'): 'theater',
    ('amenity', 'restaurant'): 'restaurant',
    ('amenity', 'cafe'): 'cafe',
    ('amenity', 'pub'): 'cafe',
    ('amenity', 'bar'): 'cafe',
    ('amenity', 'fast_food'): 'cafe',
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
    ('shop', 'copyshop'): 'copyshop',
    ('office', 'association'): 'association',
    ('office', 'ngo'): 'association',
    ('office', 'research'): 'college',
    ('office', 'educational_institution'): 'college',
    ('office', 'it'): 'office_it',
}


def assign_icon_name(historic, amenity, tourism, leisure, highway, railway,
                      sport='nan', office='nan', shop='nan', public_transport='nan'):
    """Pick a MapLibre icon name for a POI from its OSM tags, with a 'marker' fallback."""
    for key, value in [
        ('historic', historic), ('amenity', amenity), ('tourism', tourism),
        ('sport', sport), ('office', office), ('shop', shop),
        ('leisure', leisure), ('highway', highway), ('railway', railway),
        ('public_transport', public_transport)
    ]:
        if value != 'nan' and (key, value) in ICON_MAP:
            return ICON_MAP[(key, value)]
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
    'deli': 'Rosticceria',
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
    EPSG:25832 and EPSG:4326. `tourism=information` signage is dropped unless it
    falls within `named_routes_buffer` (2026-07-25: too many generic trail signs
    otherwise -- only keep the ones that actually mark a named route).
    """
    print("--> Classifying POIs and converting polygon geometries to centroids...")
    empty_cols = [
        'id', 'name', 'category', 'sub_type', 'osm_tag', 'icon_name', 'amenity_type',
        'social_function', 'image_url', 'indirizzo', 'orari_apertura', 'contatti',
        'sito_web', 'accessibilita_disabili', 'source', 'wikidata_id', 'wikipedia_title',
        'accesso_pubblico', 'offre_asporto', 'geometry'
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

    n_signage_dropped = 0
    n_parking_skipped = 0
    for idx, row in gdf_pts_utm.iterrows():
        pt_utm = row.geometry
        pt_wgs84 = gdf_pts_wgs84.loc[idx].geometry
        if pt_utm is None or pt_utm.is_empty:
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
        accesso_pubblico = compute_accesso_pubblico(row.get('access', ''))

        name = str(row.get('name', ''))
        if name == 'nan':
            name = ''

        is_bus_shelter = False
        if amenity == 'shelter':
            shelter_type = str(row.get('shelter_type', ''))
            if shelter_type == 'public_transport':
                is_bus_shelter = True
            elif len(bus_stop_geoms) > 0 and bus_stop_geoms.distance(pt_utm).min() <= BUS_SHELTER_RADIUS_M:
                is_bus_shelter = True

        # Parking is fetched only to feed the distance-to-parking accessibility
        # indicator (calculate_accessibility_distances reads it straight from
        # raw_pois_utm) -- it must never become a displayed/scored PoI (2026-07-25
        # feedback: no social-indicator category, no map icon, no table row).
        if amenity == 'parking':
            n_parking_skipped += 1
            continue

        # Generic trail signage is noise unless it marks a named hiking/running
        # route (2026-07-25 feedback: too many points on mountain trails).
        if tourism == 'information':
            on_named_route = named_routes_buffer is not None and named_routes_buffer.contains(pt_utm)
            if not on_named_route:
                n_signage_dropped += 1
                continue

        # Classification Logic
        # 1. Cross / Civic (Luoghi Pubblici) -- an unnamed amenity=shelter that's
        # actually a bus-stop shelter is NOT third-place civic infrastructure,
        # it's transit infra, so it's carved out here and picked up by the
        # pendolari branch below instead (2026-07-25 feedback).
        is_cross_civic_amenity = (
            amenity in ['public_bookcase', 'community_centre', 'drinking_water', 'shelter', 'townhall', 'social_facility', 'place_of_worship']
            and not (amenity == 'shelter' and is_bus_shelter)
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
        #    attrazioni, falesie, bivacchi, sentieri, punti panoramici, picnic, ristorazione)
        elif (historic != 'nan' or
              amenity in ['cafe', 'restaurant', 'pub', 'bar', 'fast_food', 'theatre', 'arts_centre'] or
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

        # 4. Residenti (Servizi vicinato, scuole, farmacie, alimentari, estetica, parco giochi)
        else:
            category = 'residenti'
            sub_type = amenity if amenity != 'nan' else (shop if shop != 'nan' else leisure)
            osm_tag = f'amenity={amenity}' if amenity != 'nan' else (f'shop={shop}' if shop != 'nan' else f'leisure={leisure}')

        icon_name = assign_icon_name(historic, amenity, tourism, leisure, highway, railway,
                                      sport, office, shop, public_transport)

        # "Campo da <sport>" instead of the raw OSM word "pitch" (2026-07-25 feedback).
        amenity_type = (format_pitch_label(sport) if sub_type == 'pitch' else
                         (ACCOMMODATION_LABEL_IT if sub_type in ACCOMMODATION_SUB_TYPES else
                          format_amenity_type(sub_type)))

        # Does this PoI hand out ready-to-eat/takeaway food? Used only to gate
        # picnic areas' relevance to pendolari lunch breaks (2026-07-25
        # feedback) -- see calculate_scores_and_mixite.
        offre_asporto = (
            sub_type in TAKEAWAY_FOOD_SUB_TYPES or
            shop == 'supermarket' or
            takeaway_tag == 'yes'
        )

        rec_meta = {
            'id': str(idx[1]) if isinstance(idx, tuple) else str(idx),
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
            'sito_web': '',
            'accessibilita_disabili': '',
            'source': 'osm',
            'wikidata_id': wikidata if wikidata != 'nan' else '',
            'wikipedia_title': wikipedia if wikipedia != 'nan' else '',
            'accesso_pubblico': accesso_pubblico,
            'offre_asporto': offre_asporto
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
    print(f"    Trail signage (tourism=information) dropped, not on a named route: {n_signage_dropped}")
    print(f"    Parking features skipped (fetched only for distance-to-parking indicator, not a scored PoI): {n_parking_skipped}")
    print("    OSM POIs categorized:", counts)
    return gdf_pois_utm, gdf_pois_wgs84


# --- Local dataset (Circoscrizione di Povo) ---------------------------------

DAY_COLUMNS = ['lunedi', 'martedi', 'mercoledi', 'giovedi', 'venerdi', 'sabato', 'domenica']
DAY_LABELS = {
    'lunedi': 'Lun', 'martedi': 'Mar', 'mercoledi': 'Mer', 'giovedi': 'Gio',
    'venerdi': 'Ven', 'sabato': 'Sab', 'domenica': 'Dom'
}

# (substring found in the POI name, lowercased) -> sociological category.
# Checked before the per-`servizio`-bucket default below.
LOCAL_CATEGORY_KEYWORDS = [
    ('fontana', 'cross_civic'),
    ('bookcrossing', 'cross_civic'),
    ('mercat', 'cross_civic'),  # mercato, mercatino
    ('associazion', 'cross_civic'),
    ('centro civico', 'cross_civic'),
    ('casa sociale', 'cross_civic'),
    ('sala multiuso', 'cross_civic'),
    ('copisteria', 'pendolari'),
    ('cartocopisteria', 'pendolari'),
    ('biblioteca', 'pendolari'),
    ('scuola', 'residenti'),
    ('farmacia', 'residenti'),
    ('ufficio postale', 'residenti'),
    ('banca', 'residenti'),
    ('cooperativa', 'residenti'),
    ('officina', 'residenti'),
    ('estetic', 'residenti'),
    ('prelievi', 'residenti'),
    ('fototessere', 'residenti'),
    ('vigili del fuoco', 'residenti'),
    ('pane', 'residenti'),
    ('agritur', 'occasionali'),
    ('bar ', 'occasionali'),
    ('pizzeria', 'occasionali'),
    ('pizza ', 'occasionali'),
    ('gelateria', 'occasionali'),
    ('anfiteatro', 'occasionali'),
    ('sala video', 'occasionali'),
    ('monumento', 'occasionali'),
    ('lapide', 'occasionali'),
    ('forte ', 'occasionali'),
]

# Fallback when no keyword above matches the POI name, keyed by the source's
# own `servizio` bucket.
SERVIZIO_DEFAULT_CATEGORY = {
    'Servizi e attività economiche': 'residenti',
    'Ristorazione e agriturismi': 'occasionali',
    'Cultura e tempo libero': 'cross_civic',
    'Luoghi/monumenti di interesse storico/artistico e fontane': 'occasionali',
    'Associazioni e gruppi': 'cross_civic',
}


def classify_local_poi(servizio, nome):
    nome_low = (nome or '').lower()
    for keyword, category in LOCAL_CATEGORY_KEYWORDS:
        if keyword in nome_low:
            return category
    return SERVIZIO_DEFAULT_CATEGORY.get(servizio, 'residenti')


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
        category = classify_local_poi(servizio, nome)

        referente = _clean(row.get('referente', ''))
        contatti_raw = _clean(row.get('contatti', ''))
        contatti = ' · '.join(p for p in (referente, contatti_raw) if p)

        attore = _clean(row.get('attore', ''))
        if attore in LOCAL_ATTORE_AMENITY_OVERRIDES:
            nome = f'{nome} - {attore}'
            amenity_type = LOCAL_ATTORE_AMENITY_OVERRIDES[attore]
        else:
            amenity_type = normalize_attore(attore)

        records_wgs84.append({
            'id': f'locale_{idx}',
            'name': nome,
            'category': category,
            'sub_type': servizio,
            'osm_tag': f'locale={servizio}',
            'icon_name': 'marker',  # refined if fused with a matching OSM feature
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
    Match local circoscrizione POIs against OSM-derived POIs within 25m using
    RapidFuzz name similarity (>80%). Matched pairs are fused (local hyper-local
    fields win, OSM geometry/tags/icon are adopted); unmatched records on either
    side are kept standalone.
    """
    print("--> Deduplicating and merging local dataset with OSM POIs...")

    osm_used = set()
    merged_utm, merged_wgs84 = [], []
    n_matched = 0

    osm_sindex = gdf_osm_utm.sindex if len(gdf_osm_utm) > 0 else None

    for i in range(len(gdf_local_utm)):
        local_row_utm = gdf_local_utm.iloc[i]
        local_row_wgs84 = gdf_local_wgs84.iloc[i]
        local_geom = local_row_utm.geometry

        best_idx, best_score = None, 0
        if osm_sindex is not None and local_geom is not None and not local_geom.is_empty:
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
        'n_local_standalone': len(gdf_local_utm) - n_matched,
        'n_osm_standalone': n_osm_standalone,
        'n_final': len(gdf_merged_utm)
    }
    print(f"    Matched {n_matched} local POIs to OSM features "
          f"(<= {DEDUP_RADIUS_M}m, name similarity > {DEDUP_NAME_THRESHOLD}%).")
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


def integrate_dtm_and_tobler(G_utm, dtm_path):
    """Integrate DTM raster and compute Tobler travel times on pedestrian edges."""
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
            speed_kmh = 6.0 * math.exp(-3.5 * abs(grade + 0.05))
            travel_time = length / max(speed_kmh / 3.6, 0.001)

            data['grade'] = grade
            data['travel_time'] = travel_time

    print("    DTM integration and Tobler travel time calculations complete.")
    return G_utm


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

    poi_xs = [g.x for g in gdf_pois_utm.geometry]
    poi_ys = [g.y for g in gdf_pois_utm.geometry]
    poi_nodes = ox.distance.nearest_nodes(G_utm, poi_xs, poi_ys)

    FAR = 5000.0  # metres: fallback when unreachable within the extracted graph
    gdf_pois_utm['d_bus_m'] = np.round([dist_to_bus.get(n, FAR) for n in poi_nodes], 1)
    gdf_pois_utm['d_parking_m'] = np.round([dist_to_parking.get(n, FAR) for n in poi_nodes], 1)
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
    excluded_mask = (
        (gdf_pois_utm['sub_type'] == 'place_of_worship') |
        (gdf_pois_utm['accesso_pubblico'] == False) |  # noqa: E712
        ((gdf_pois_utm['sub_type'] == 'shelter') & (gdf_pois_utm['category'] == 'cross_civic') & (gdf_pois_utm['name'] == ''))
    )
    gdf_indic = gdf_pois_utm[~excluded_mask]
    print(f"    PoI esclusi dal calcolo indicatori (luoghi di culto, accesso non pubblico, "
          f"o rifugi/pensiline senza nome): {excluded_mask.sum()}")

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
    total_final = dedup_stats['n_final'] + manual_count

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
        f"- Corrispondenze locale ↔ OSM fuse (raggio {DEDUP_RADIUS_M}m, "
        f"similarità nome > {DEDUP_NAME_THRESHOLD}%): **{dedup_stats['n_matched']}**"
    )
    lines.append(f"- PoI solo locali (nessun corrispondente OSM): **{dedup_stats['n_local_standalone']}**")
    lines.append(f"- PoI solo OSM (nessun corrispondente locale): **{dedup_stats['n_osm_standalone']}**")
    lines.append(f"- PoI iniettati manualmente (assenti da OSM e dal dataset locale): **{manual_count}**")
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


def main():
    print("=== POVO CIVIC HUB - GEOGRAPHIC DATA ANALYSIS PIPELINE (ICC EDITION) ===")
    gdf_wgs84, gdf_utm = load_boundary()
    G_utm, raw_pois_utm = fetch_osm_graph_and_pois(gdf_wgs84)
    named_routes_buffer = fetch_named_hiking_routes(gdf_wgs84)
    gdf_osm_utm, gdf_osm_wgs84 = classify_and_transform_pois(raw_pois_utm, named_routes_buffer)

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

    gdf_pois_utm, gdf_pois_wgs84, enrich_stats = enrich_missing_data(gdf_pois_utm, gdf_pois_wgs84)
    gdf_pois_utm, gdf_pois_wgs84, image_check_stats = verify_image_urls(gdf_pois_utm, gdf_pois_wgs84)

    G_utm = integrate_dtm_and_tobler(G_utm, DTM_INPUT)
    gtfs_stops = process_gtfs_feeds(gdf_utm)

    gdf_pois_utm = calculate_accessibility_distances(gdf_pois_utm, G_utm, raw_pois_utm)
    gdf_pois_wgs84['d_bus_m'] = gdf_pois_utm['d_bus_m'].values
    gdf_pois_wgs84['d_parking_m'] = gdf_pois_utm['d_parking_m'].values

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
        'manual_count': len(manual_utm)
    }, gdf_pois_wgs84)

    print("=== PIPELINE EXECUTED SUCCESSFULLY ===")


if __name__ == "__main__":
    main()
