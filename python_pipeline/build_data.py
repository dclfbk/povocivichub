"""
Povo Civic Hub - Geographic Data Analysis Pipeline (Exhaustive POI & GTFS Edition)

1. ESTRAZIONE MASSIVA POI DA OSM:
   - Downloads both Nodes and Polygons from OSM using exhaustive tag dictionary:
     amenity (incl. parking, theatre, arts_centre, bar), shop (incl. copyshop, beauty,
     hairdresser, deli), tourism (incl. museum, artwork, chalet, camp_site,
     wilderness_hut), leisure (incl. amphitheatre), sport=climbing, highway=bus_stop,
     railway=station/halt, place=square, historic (fort, castle, monument, memorial,
     archaeological_site, ruins, trench), office (research, educational_institution,
     association, ngo).
   - Calculates centroids in EPSG:25832 for all polygon POIs.

2. INIEZIONE MANUALE POI SPECIALI:
   - Aggiunge al DataFrame due elementi del territorio assenti/incompleti su OSM
     (Mercato Zonale del Martedì in Piazza Manci, Stoi del Chegul sul Monte Celva)
     con coordinate, categoria, icona e metadati curati a mano (vedi MANUAL_POIS).

3. CLASSIFICAZIONE SOCIOLOGICA DEI POI:
   - 'residenti': neighborhood services, schools, pharmacies, groceries, playgrounds,
     estetica/parrucchieri, rosticcerie.
   - 'pendolari': UniTN/FBK campus, libraries, canteens, parking, copisterie, TPL
     stops/station.
   - 'occasionali': forts, castles, monuments/ruins/trenches, theatres/amphitheatres,
     museums, attractions, falesie (sport=climbing), bivacchi (wilderness_hut), trail
     access, viewpoints, picnic areas, hotels/guest houses, pubs/bars/restaurants.
   - 'cross_civic': VERDE URBANO & SERVIZI CIVICI (public parks/gardens, public_bookcase,
     squares, civic centres, drinking_water, benches, associazioni/ONG, mercati).
   Each POI also gets:
   - `icon_name` for MapLibre rendering (castle, theater, museum, attraction, restaurant,
     cafe, viewpoint, library, college, bus, park, drinking_water, bench, hotel,
     monument, ruins, information, climbing, association, copyshop, market, historic,
     marker fallback).
   - `amenity_type`: human-readable OSM sub-type label.
   - `social_function`: sociological rationale for the category (Oldenburg's Third
     Place, Klinenberg/Jacobs neighborhood infrastructure, academic flow hub, or
     eco-recreational attractor).
   - `image_url`: reference photo (populated for the manually curated POIs; empty
     for bulk OSM extractions, left for the caller to backfill with real photography).

4. RICALCOLO GRIGLIA H3 CON POI MASSIVI E GTFS:
   - Calculates density and proximity (weighted with DTM slope and Tobler hiking travel times)
     for each POI category and GTFS passages, including the manually injected POIs.
   - Computes res_score, comm_score, occa_score (normalized 0-1) and Shannon Entropy mix_index.

5. EXPORT FILE IN public/data/ (TUTTI IN EPSG:4326):
   - public/data/povo_boundary.json
   - public/data/povo_grid.json
   - public/data/povo_pois.json
"""

import os
import json
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

# Paths
BOUNDARY_INPUT = "raw_data/povo_boundary.geojson"
DTM_INPUT = "raw_data/dtm_povo.tif"
GTFS_URBANO_INPUT = "raw_data/google_transit_urbano_tte.zip"
GTFS_EXTRAURBANO_INPUT = "raw_data/google_transit_extraurbano_tte.zip"

GRID_OUTPUT = "public/data/povo_grid.json"
BOUNDARY_OUTPUT = "public/data/povo_boundary.json"
POIS_OUTPUT = "public/data/povo_pois.json"

TARGET_CRS = "EPSG:25832"  # UTM 32N (meters)
WGS84_CRS = "EPSG:4326"


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

    # 2. Comprehensive POI tags
    tags = {
        'amenity': [
            'university', 'research_institute', 'library', 'school', 'kindergarten',
            'pharmacy', 'post_office', 'townhall', 'community_centre', 'social_facility',
            'cafe', 'restaurant', 'pub', 'bar', 'canteen', 'fast_food', 'bank', 'recycling',
            'public_bookcase', 'bench', 'drinking_water', 'shelter', 'place_of_worship',
            'parking', 'theatre', 'arts_centre'
        ],
        'shop': [
            'supermarket', 'bakery', 'convenience', 'butcher', 'greengrocer', 'chemist', 'books',
            'copyshop', 'beauty', 'hairdresser', 'deli'
        ],
        'tourism': [
            'viewpoint', 'information', 'picnic_site', 'alpine_hut', 'wilderness_hut',
            'guest_house', 'hotel', 'attraction', 'museum', 'artwork', 'chalet', 'camp_site'
        ],
        'leisure': ['park', 'playground', 'sports_centre', 'pitch', 'garden', 'nature_reserve', 'amphitheatre'],
        'sport': ['climbing'],
        'highway': ['bus_stop'],
        'railway': ['station', 'halt'],
        'place': ['square'],
        'historic': ['fort', 'castle', 'monument', 'memorial', 'archaeological_site', 'ruins', 'trench'],
        'office': ['research', 'educational_institution', 'association', 'ngo']
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
    ('amenity', 'bench'): 'bench',
    ('tourism', 'museum'): 'museum',
    ('tourism', 'attraction'): 'attraction',
    ('tourism', 'artwork'): 'attraction',
    ('tourism', 'viewpoint'): 'viewpoint',
    ('tourism', 'information'): 'information',
    ('tourism', 'picnic_site'): 'park',
    ('tourism', 'hotel'): 'hotel',
    ('tourism', 'guest_house'): 'hotel',
    ('tourism', 'chalet'): 'hotel',
    ('tourism', 'camp_site'): 'hotel',
    ('tourism', 'alpine_hut'): 'hotel',
    ('leisure', 'amphitheatre'): 'theater',
    ('leisure', 'park'): 'park',
    ('leisure', 'garden'): 'park',
    ('highway', 'bus_stop'): 'bus',
    ('railway', 'station'): 'bus',
    ('railway', 'halt'): 'bus',
    ('tourism', 'wilderness_hut'): 'hotel',
    ('historic', 'trench'): 'ruins',
    ('sport', 'climbing'): 'climbing',
    ('shop', 'copyshop'): 'copyshop',
    ('office', 'association'): 'association',
    ('office', 'ngo'): 'association',
}


def assign_icon_name(historic, amenity, tourism, leisure, highway, railway, sport='nan', office='nan', shop='nan'):
    """Pick a MapLibre icon name for a POI from its OSM tags, with a 'marker' fallback."""
    for key, value in [
        ('historic', historic), ('amenity', amenity), ('tourism', tourism),
        ('sport', sport), ('office', office), ('shop', shop),
        ('leisure', leisure), ('highway', highway), ('railway', railway)
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


def format_amenity_type(sub_type):
    """Human-readable label derived from a raw OSM sub_type value, e.g. 'picnic_site' -> 'Picnic Site'."""
    if not sub_type or sub_type == 'nan':
        return ''
    return sub_type.replace('_', ' ').title()


def classify_and_transform_pois(raw_pois_utm):
    """
    Transform polygon POIs to centroids in EPSG:25832, assign category, name, sub_type,
    osm_tag, icon_name, and return GeoDataFrames in EPSG:25832 and EPSG:4326.
    """
    print("--> Classifying POIs and converting polygon geometries to centroids...")
    if len(raw_pois_utm) == 0:
        cols = [
            'id', 'name', 'category', 'sub_type', 'osm_tag', 'icon_name',
            'amenity_type', 'social_function', 'image_url', 'geometry'
        ]
        empty_gdf_utm = gpd.GeoDataFrame(columns=cols, crs=TARGET_CRS)
        empty_gdf_wgs84 = gpd.GeoDataFrame(columns=cols, crs=WGS84_CRS)
        return empty_gdf_utm, empty_gdf_wgs84

    # Convert polygon/multipolygon geometries to centroids in metric UTM 32N
    centroids_utm = raw_pois_utm.geometry.centroid
    gdf_pts_utm = gpd.GeoDataFrame(raw_pois_utm.drop(columns=['geometry']), geometry=centroids_utm, crs=TARGET_CRS)
    gdf_pts_wgs84 = gdf_pts_utm.to_crs(WGS84_CRS)

    poi_records_utm = []
    poi_records_wgs84 = []

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

        name = str(row.get('name', ''))
        if name == 'nan':
            name = ''

        # Classification Logic
        # 1. Cross / Civic (Verde Urbano & Servizi Civici)
        if (amenity in ['public_bookcase', 'community_centre', 'drinking_water', 'bench', 'shelter', 'townhall', 'social_facility', 'place_of_worship'] or
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

        # 2. Pendolari (Campus UniTN/FBK, biblioteche, mense, TPL, parcheggi, copisterie)
        elif (amenity in ['university', 'research_institute', 'library', 'canteen', 'parking'] or
              shop == 'copyshop' or
              highway == 'bus_stop' or
              railway in ['station', 'halt'] or
              office in ['research', 'educational_institution']):
            category = 'pendolari'
            sub_type = (amenity if amenity != 'nan' else
                        (shop if shop != 'nan' else
                         (highway if highway != 'nan' else railway)))
            osm_tag = (f'amenity={amenity}' if amenity != 'nan' else
                       (f'shop={shop}' if shop != 'nan' else
                        (f'highway={highway}' if highway != 'nan' else f'railway={railway}')))

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

        icon_name = assign_icon_name(historic, amenity, tourism, leisure, highway, railway, sport, office, shop)

        rec_meta = {
            'id': str(idx[1]) if isinstance(idx, tuple) else str(idx),
            'name': name,
            'category': category,
            'sub_type': sub_type,
            'osm_tag': osm_tag,
            'icon_name': icon_name,
            'amenity_type': format_amenity_type(sub_type),
            'social_function': SOCIAL_FUNCTION_BY_CATEGORY[category],
            'image_url': ''
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
    print("    POIs categorized:", counts)
    return gdf_pois_utm, gdf_pois_wgs84


# Key territorial POIs with no (or incomplete) OSM presence, curated by hand so they
# still appear in the map, PoI list, and H3 scoring alongside the OSM-derived ones.
MANUAL_POIS = [
    {
        'id': 'manual_mercato_povo',
        'name': 'Mercato Zonale del Martedì',
        'category': 'cross_civic',
        'sub_type': 'market',
        'osm_tag': 'manual=market',
        'icon_name': 'market',
        'amenity_type': 'Mercato Civico',
        'social_function': (
            "Infrastruttura sociale temporanea. Favorisce l'incontro intergenerazionale "
            "tra residenti ed economia a km zero."
        ),
        'image_url': 'https://upload.wikimedia.org/wikipedia/commons/thumb/c/c8/Povo_piazza_Manci.jpg/640px-Povo_piazza_Manci.jpg',
        'lon': 11.1565,
        'lat': 46.0662
    },
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


def calculate_scores_and_mixite(gdf_hex_utm, G_utm, gdf_pois_utm, gtfs_stops):
    """
    Compute res_score, comm_score, occa_score weighted with massive POIs & GTFS frequency,
    and compute Shannon Entropy mix_index per hexagon.
    """
    print("--> Calculating weighted hexagon scores and Mixité Index with massive POIs...")

    # Filter POIs by category
    gdf_res = gdf_pois_utm[gdf_pois_utm['category'] == 'residenti']
    gdf_comm = gdf_pois_utm[gdf_pois_utm['category'] == 'pendolari']
    gdf_occa = gdf_pois_utm[gdf_pois_utm['category'] == 'occasionali']
    gdf_civic = gdf_pois_utm[gdf_pois_utm['category'] == 'cross_civic']

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
    raw_civic_poi = np.array([compute_raw_poi_score(r.geometry, gdf_civic) for _, r in gdf_hex_utm.iterrows()])

    # GTFS walking accessibility
    peak_transit, offpeak_transit = calculate_gtfs_accessibility(gdf_hex_utm, G_utm, gtfs_stops)

    # Combine scores
    # cross_civic adds to res and occa to enhance civic third place mixing
    res_combined = raw_res_poi + (0.5 * raw_civic_poi) + offpeak_transit
    comm_combined = raw_comm_poi + peak_transit
    occa_combined = raw_occa_poi + (0.5 * raw_civic_poi) + offpeak_transit

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

    for r, c, o in zip(norm_res, norm_comm, norm_occa):
        total = r + c + o
        if total <= 0.0:
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

    print("    Score calculations and Mixité Index complete.")
    return gdf_hex_utm


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


def main():
    print("=== POVO CIVIC HUB - GEOGRAPHIC DATA ANALYSIS PIPELINE (EXHAUSTIVE EDITION) ===")
    gdf_wgs84, gdf_utm = load_boundary()
    G_utm, raw_pois_utm = fetch_osm_graph_and_pois(gdf_wgs84)
    gdf_pois_utm, gdf_pois_wgs84 = classify_and_transform_pois(raw_pois_utm)

    manual_utm, manual_wgs84 = build_manual_pois()
    gdf_pois_utm = gpd.GeoDataFrame(
        pd.concat([gdf_pois_utm, manual_utm], ignore_index=True), geometry='geometry', crs=TARGET_CRS
    )
    gdf_pois_wgs84 = gpd.GeoDataFrame(
        pd.concat([gdf_pois_wgs84, manual_wgs84], ignore_index=True), geometry='geometry', crs=WGS84_CRS
    )
    counts = gdf_pois_utm['category'].value_counts().to_dict()
    print("    POIs after manual injection:", counts)

    G_utm = integrate_dtm_and_tobler(G_utm, DTM_INPUT)
    gtfs_stops = process_gtfs_feeds(gdf_utm)
    gdf_hex_utm = generate_h3_grid(gdf_wgs84, gdf_utm, res=9)
    gdf_hex_scored = calculate_scores_and_mixite(gdf_hex_utm, G_utm, gdf_pois_utm, gtfs_stops)
    export_results(gdf_hex_scored, gdf_utm, gdf_pois_wgs84)
    print("=== PIPELINE EXECUTED SUCCESSFULLY ===")


if __name__ == "__main__":
    main()
