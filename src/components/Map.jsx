import React, { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import {
  buildFillColorExpression,
  buildClusterCategoryColorExpression,
  buildHexRangeFilter,
  CLUSTER_CATEGORY_PROPERTIES,
  createPoiIconImage,
  computePoiStatsInPolygon,
  aggregateHexScoresInPolygon,
  buildMapStyleDefinition,
  computeBboxFromGeoJSON,
  buildPoiPopupHtml,
  buildHeatmapRadiusExpression
} from '../config/mapConfig';

const EMPTY_FC = { type: 'FeatureCollection', features: [] };
const ZOOM_OUT_LEVELS_BEYOND_BOUNDARY = 2;
// Fixed panning limit (2026-07-28 feedback: use these exact corners instead
// of a boundary-relative padded box) -- [southwest, northeast] as required by
// maplibregl.LngLatBoundsLike.
const MAX_BOUNDS = [[10.993710, 45.987540], [11.336002, 46.107755]];

const UNCLUSTERED_FILTER_BASE = ['!', ['has', 'point_count']];

function unclusteredCategoryFilter(categories) {
  const cats = categories && categories.length > 0 ? categories : ['__none__'];
  return ['all', UNCLUSTERED_FILTER_BASE, ['in', ['get', 'category'], ['literal', cats]]];
}

export default function Map({
  selectedHex,
  onSelectHex,
  showGrid,
  poiViewMode,
  showTerrain,
  gridMetric,
  activePoiCategories,
  heatmapRadius,
  hexValueRange,
  poisData,
  gridData,
  drawMode,
  onDrawComplete,
  clearDrawSignal,
  mapStyle,
  flyToTarget,
  initialViewState,
  initialSelectedHexId,
  onViewStateChange,
  onViewportBoundsChange
}) {
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);
  const [loaded, setLoaded] = useState(false);
  const drawModeRef = useRef(false);
  const drawPointsRef = useRef([]);
  const poisDataRef = useRef(poisData);
  const gridDataRef = useRef(gridData);
  // Tracks the mapStyle value already applied to the live map, so the
  // basemap-switch effect below can tell "prop actually changed" apart from
  // "React re-ran this effect without mapStyle changing" -- the latter
  // happens every mount under React.StrictMode (dev only), which
  // double-invokes effects to surface missing-cleanup bugs. A boolean
  // "did this run once already" ref (the previous approach) breaks under
  // that double-invoke: it flips true on the first (skipped) run and stays
  // true, so the second synthetic run no longer recognizes itself as "the
  // initial mount" and incorrectly calls map.setStyle()+addCustomLayers()
  // again on the SAME still-live map -- colliding with the sources the
  // mount effect's own 'load' handler already added ("Source aws-terrain
  // already exists", confirmed via a headless-browser repro) and, because
  // that exception aborts the mount's 'load' callback before it reaches
  // `setLoaded(true)`, permanently disables every layer-visibility toggle
  // in the sidebar (Sidebar effects below all bail out on `!loaded`).
  // Comparing against the actual last-applied value is idempotent no matter
  // how many times the effect body re-runs for the same mapStyle.
  const appliedMapStyleRef = useRef(mapStyle);
  const didInitTerrainRef = useRef(false);
  const onViewStateChangeRef = useRef(onViewStateChange);
  useEffect(() => {
    onViewStateChangeRef.current = onViewStateChange;
  }, [onViewStateChange]);
  const onViewportBoundsChangeRef = useRef(onViewportBoundsChange);
  useEffect(() => {
    onViewportBoundsChangeRef.current = onViewportBoundsChange;
  }, [onViewportBoundsChange]);

  // Latest prop values, kept in refs so the layer-(re)creation logic below
  // (shared between the initial mount and every basemap-style switch) always
  // reads current state instead of whatever was captured at mount time.
  const stateRef = useRef({ showGrid, poiViewMode, gridMetric, activePoiCategories, showTerrain, heatmapRadius, hexValueRange });
  useEffect(() => {
    stateRef.current = { showGrid, poiViewMode, gridMetric, activePoiCategories, showTerrain, heatmapRadius, hexValueRange };
  }, [showGrid, poiViewMode, gridMetric, activePoiCategories, showTerrain, heatmapRadius, hexValueRange]);

  useEffect(() => {
    poisDataRef.current = poisData;
  }, [poisData]);

  useEffect(() => {
    gridDataRef.current = gridData;
  }, [gridData]);

  // Adds every custom source/layer this app overlays on top of whichever
  // basemap style is currently active. Called once on mount, and again after
  // every map.setStyle() call (setStyle wipes all sources/layers -- runtime
  // symbol images added via addImage are cleared too, but self-heal via the
  // 'styleimagemissing' handler registered once below).
  const addCustomLayers = (map) => {
    // Idempotency guard: harmless if this is ever invoked twice on the same
    // still-set-up map (e.g. a stray double-invoke) -- addSource() throws on
    // a duplicate id otherwise, which would abort the rest of this function
    // (including the hex-grid layers) partway through.
    if (map.getSource('aws-terrain')) return;

    map.addSource('aws-terrain', {
      type: 'raster-dem',
      tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
      tileSize: 256,
      encoding: 'terrarium',
      maxzoom: 15
    });

    // 1. Povo boundary line — always visible.
    map.addSource('povo-boundary-src', { type: 'geojson', data: './data/povo_boundary.json' });
    map.addLayer({
      id: 'povo-boundary-line',
      type: 'line',
      source: 'povo-boundary-src',
      paint: { 'line-color': '#f43f5e', 'line-width': 2.5, 'line-dasharray': [3, 2], 'line-opacity': 0.85 }
    });

    // 2. H3 hexagon grid — hidden by default.
    map.addSource('povo-grid-src', { type: 'geojson', data: './data/povo_grid.json', generateId: true });

    const initialHexFilter = buildHexRangeFilter(stateRef.current.gridMetric, stateRef.current.hexValueRange);

    map.addLayer({
      id: 'povo-grid-fill',
      type: 'fill',
      source: 'povo-grid-src',
      layout: { visibility: 'none' },
      ...(initialHexFilter ? { filter: initialHexFilter } : {}),
      paint: {
        'fill-color': buildFillColorExpression(stateRef.current.gridMetric),
        'fill-opacity': [
          'case',
          ['boolean', ['feature-state', 'selected'], false], 0.88,
          ['boolean', ['feature-state', 'hover'], false], 0.75,
          0.55
        ]
      }
    });

    map.addLayer({
      id: 'povo-grid-outline',
      type: 'line',
      source: 'povo-grid-src',
      layout: { visibility: 'none' },
      ...(initialHexFilter ? { filter: initialHexFilter } : {}),
      paint: {
        'line-color': [
          'case',
          ['boolean', ['feature-state', 'selected'], false], '#ffffff',
          ['boolean', ['feature-state', 'hover'], false], '#6366f1',
          'rgba(255, 255, 255, 0.25)'
        ],
        'line-width': [
          'case',
          ['boolean', ['feature-state', 'selected'], false], 3.5,
          ['boolean', ['feature-state', 'hover'], false], 2.0,
          0.8
        ]
      }
    });

    // 3. POIs — clustered source, hidden by default. Four view layers
    // (heatmap, clusters, cluster count, unclustered icons) share it.
    map.addSource('povo-pois-source', {
      type: 'geojson',
      data: './data/povo_pois.json',
      cluster: true,
      clusterMaxZoom: 14,
      clusterRadius: 50,
      clusterProperties: CLUSTER_CATEGORY_PROPERTIES
    });

    map.addLayer({
      id: 'poi-heatmap',
      type: 'heatmap',
      source: 'povo-pois-source',
      layout: { visibility: 'none' },
      paint: {
        'heatmap-weight': 1,
        'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 11, 1, 15, 3],
        'heatmap-color': [
          'interpolate', ['linear'], ['heatmap-density'],
          0, 'rgba(0,0,0,0)', 0.2, '#312e81', 0.4, '#3b82f6', 0.6, '#10b981', 0.8, '#f59e0b', 1, '#ec4899'
        ],
        'heatmap-radius': buildHeatmapRadiusExpression(stateRef.current.heatmapRadius),
        'heatmap-opacity': 0.75
      }
    });

    map.addLayer({
      id: 'poi-clusters',
      type: 'circle',
      source: 'povo-pois-source',
      filter: ['has', 'point_count'],
      layout: { visibility: 'none' },
      paint: {
        'circle-color': buildClusterCategoryColorExpression(),
        'circle-radius': ['step', ['get', 'point_count'], 16, 10, 22, 30, 28],
        'circle-stroke-width': 2,
        'circle-stroke-color': '#0f172a'
      }
    });

    map.addLayer({
      id: 'poi-cluster-count',
      type: 'symbol',
      source: 'povo-pois-source',
      filter: ['has', 'point_count'],
      layout: {
        visibility: 'none',
        'text-field': ['get', 'point_count_abbreviated'],
        'text-font': ['Noto Sans Regular'],
        'text-size': 12
      },
      paint: { 'text-color': '#ffffff', 'text-halo-color': '#0f172a', 'text-halo-width': 1 }
    });

    map.addLayer({
      id: 'poi-unclustered-icon',
      type: 'symbol',
      source: 'povo-pois-source',
      filter: unclusteredCategoryFilter(stateRef.current.activePoiCategories),
      layout: {
        visibility: 'none',
        'icon-image': ['get', 'icon_name'],
        'icon-size': 1.2,
        'icon-allow-overlap': true,
        'text-field': ['get', 'name'],
        'text-font': ['Noto Sans Regular'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 14, 0, 16, 11],
        'text-anchor': 'top',
        'text-offset': [0, 0.6],
        'text-max-width': 8,
        'text-optional': true,
        'text-allow-overlap': false
      },
      paint: { 'text-color': '#0f172a', 'text-halo-color': '#ffffff', 'text-halo-width': 1.4 }
    });

    // 4. Draw-an-area tool: a live-updated source showing the in-progress
    // (line + vertex points) or finalized (polygon) shape the user draws.
    map.addSource('draw-area-src', { type: 'geojson', data: EMPTY_FC });

    map.addLayer({
      id: 'draw-area-fill',
      type: 'fill',
      source: 'draw-area-src',
      filter: ['==', ['geometry-type'], 'Polygon'],
      paint: { 'fill-color': '#6366f1', 'fill-opacity': 0.2 }
    });
    map.addLayer({
      id: 'draw-area-line',
      type: 'line',
      source: 'draw-area-src',
      filter: ['!=', ['geometry-type'], 'Point'],
      paint: { 'line-color': '#6366f1', 'line-width': 2.5, 'line-dasharray': [2, 1] }
    });
    map.addLayer({
      id: 'draw-area-vertices',
      type: 'circle',
      source: 'draw-area-src',
      filter: ['==', ['geometry-type'], 'Point'],
      paint: { 'circle-radius': 5, 'circle-color': '#ffffff', 'circle-stroke-width': 2, 'circle-stroke-color': '#6366f1' }
    });
  };

  // Re-applies every prop-driven visual state on top of freshly-(re)created
  // layers -- needed after a basemap switch, since setStyle() resets every
  // layer back to its just-created defaults regardless of current React state.
  const applyCurrentState = (map) => {
    const { showGrid: sg, poiViewMode: pvm, gridMetric: gm, activePoiCategories: apc, showTerrain: st, heatmapRadius: hr, hexValueRange: hvr } = stateRef.current;

    const gridVisibility = sg ? 'visible' : 'none';
    map.setLayoutProperty('povo-grid-fill', 'visibility', gridVisibility);
    map.setLayoutProperty('povo-grid-outline', 'visibility', gridVisibility);
    map.setPaintProperty('povo-grid-fill', 'fill-color', buildFillColorExpression(gm));
    const hexFilter = buildHexRangeFilter(gm, hvr);
    map.setFilter('povo-grid-fill', hexFilter);
    map.setFilter('povo-grid-outline', hexFilter);

    const iconsVisible = pvm === 'icons' ? 'visible' : 'none';
    const heatmapVisible = pvm === 'heatmap' ? 'visible' : 'none';
    map.setLayoutProperty('poi-clusters', 'visibility', iconsVisible);
    map.setLayoutProperty('poi-cluster-count', 'visibility', iconsVisible);
    map.setLayoutProperty('poi-unclustered-icon', 'visibility', iconsVisible);
    map.setLayoutProperty('poi-heatmap', 'visibility', heatmapVisible);
    map.setFilter('poi-unclustered-icon', unclusteredCategoryFilter(apc));
    map.setPaintProperty('poi-heatmap', 'heatmap-radius', buildHeatmapRadiusExpression(hr));

    if (st) {
      map.setTerrain({ source: 'aws-terrain', exaggeration: 1.3 });
    }
  };

  // Mount the map once. Camera starts from initialViewState (parsed from the
  // URL by App -- 2026-07-25 feedback: a shared link should reproduce the
  // same view) falling back to Povo/2D if not provided.
  useEffect(() => {
    if (!mapContainerRef.current) return;

    // Set by the cleanup below -- guards the async 'load' callback so it
    // becomes a no-op if this particular effect instance was already torn
    // down (e.g. React.StrictMode's dev-only mount/cleanup/remount replay)
    // before the map finished loading, rather than running full setup
    // (including setLoaded(true)) against a removed map.
    let cancelled = false;

    const ivs = initialViewState || {};
    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: buildMapStyleDefinition(mapStyle),
      center: [ivs.lon ?? 11.155, ivs.lat ?? 46.066], // Povo, Trento
      zoom: ivs.zoom ?? 14,
      pitch: ivs.pitch ?? 0,
      bearing: ivs.bearing ?? 0,
      maxPitch: 75,
      antialias: true
    });

    mapRef.current = map;

    // MapLibre sizes its canvas once from the container's dimensions at
    // construction time and never re-measures on its own. Without this, a
    // container that starts at zero size (e.g. squeezed out by a sibling
    // during a layout bug) or later gets resized (sidebar toggle, phone
    // rotation, mobile browser chrome show/hide) leaves the map blank or
    // mis-sized until a manual resize() call.
    const resizeObserver = new ResizeObserver(() => map.resize());
    resizeObserver.observe(mapContainerRef.current);

    // visualizePitch:false keeps the compass button scoped to bearing only --
    // clicking it calls resetNorth() (not resetNorthPitch()), so it can't
    // fight with the separate "Vista 3D" pitch toggle.
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right');

    // Lazily draw and register a symbol image the first time a given
    // icon_name is requested by the poi-unclustered-icon layer. Fires again
    // automatically after a basemap switch clears the previous images.
    map.on('styleimagemissing', (e) => {
      if (map.hasImage(e.id)) return;
      const imageData = createPoiIconImage(e.id);
      map.addImage(e.id, imageData, { pixelRatio: 2 });
    });

    map.on('load', () => {
      if (cancelled) return;
      addCustomLayers(map);

      // Panning limit: fixed to the given lat/lon corners rather than a
      // boundary-relative padded box (2026-07-28 feedback).
      map.setMaxBounds(MAX_BOUNDS);

      // Zoomed-out limit: 2 zoom levels beyond whatever level exactly fits
      // the full Povo boundary on screen.
      fetch('./data/povo_boundary.json')
        .then((res) => res.json())
        .then((boundaryGeoJSON) => {
          const [minLng, minLat, maxLng, maxLat] = computeBboxFromGeoJSON(boundaryGeoJSON);
          const bounds = new maplibregl.LngLatBounds([minLng, minLat], [maxLng, maxLat]);
          const cam = map.cameraForBounds(bounds, { padding: 0 });
          if (cam && typeof cam.zoom === 'number') {
            map.setMinZoom(Math.max(0, cam.zoom - ZOOM_OUT_LEVELS_BEYOND_BOUNDARY));
          }
        })
        .catch((err) => console.error('Failed to compute boundary min-zoom', err));

      // Hover interaction on hexagons.
      let hoveredFeatureId = null;
      map.on('mousemove', 'povo-grid-fill', (e) => {
        if (e.features.length > 0) {
          map.getCanvas().style.cursor = 'pointer';
          if (hoveredFeatureId !== null) {
            map.setFeatureState({ source: 'povo-grid-src', id: hoveredFeatureId }, { hover: false });
          }
          hoveredFeatureId = e.features[0].id;
          map.setFeatureState({ source: 'povo-grid-src', id: hoveredFeatureId }, { hover: true });
        }
      });

      map.on('mouseleave', 'povo-grid-fill', () => {
        map.getCanvas().style.cursor = '';
        if (hoveredFeatureId !== null) {
          map.setFeatureState({ source: 'povo-grid-src', id: hoveredFeatureId }, { hover: false });
        }
        hoveredFeatureId = null;
      });

      // Click on a hexagon updates the sidebar stacked-bar profile.
      let selectedFeatureId = null;
      map.on('click', 'povo-grid-fill', (e) => {
        if (drawModeRef.current) return;
        if (e.features.length > 0) {
          const feature = e.features[0];
          const props = feature.properties;

          if (selectedFeatureId !== null) {
            map.setFeatureState({ source: 'povo-grid-src', id: selectedFeatureId }, { selected: false });
          }
          selectedFeatureId = feature.id;
          map.setFeatureState({ source: 'povo-grid-src', id: selectedFeatureId }, { selected: true });

          if (onSelectHex) onSelectHex(props);
        }
      });

      // Restore the hexagon selected in a shared link (h3=... in the URL)
      // once the grid source has actually loaded its data, since it's a
      // remote GeoJSON source resolved asynchronously after 'load' fires.
      if (initialSelectedHexId) {
        const trySelectInitialHex = () => {
          if (!map.isSourceLoaded('povo-grid-src')) return;
          const matches = map.querySourceFeatures('povo-grid-src', {
            filter: ['==', ['get', 'h3_id'], initialSelectedHexId]
          });
          if (matches.length > 0) {
            const feature = matches[0];
            selectedFeatureId = feature.id;
            map.setFeatureState({ source: 'povo-grid-src', id: selectedFeatureId }, { selected: true });
            if (onSelectHex) onSelectHex(feature.properties);
          }
          map.off('sourcedata', trySelectInitialHex);
        };
        map.on('sourcedata', trySelectInitialHex);
      }

      // Report the settled camera back up to App on every pan/zoom/rotate/
      // pitch (MapLibre fires 'moveend' for all of these), so the URL can
      // stay in sync with whatever's actually on screen.
      const reportViewportBounds = () => {
        if (!onViewportBoundsChangeRef.current) return;
        const b = map.getBounds();
        onViewportBoundsChangeRef.current({
          minLng: b.getWest(), minLat: b.getSouth(), maxLng: b.getEast(), maxLat: b.getNorth()
        });
      };
      map.on('moveend', () => {
        if (onViewStateChangeRef.current) {
          const center = map.getCenter();
          onViewStateChangeRef.current({
            lat: center.lat,
            lon: center.lng,
            zoom: map.getZoom(),
            bearing: map.getBearing(),
            pitch: map.getPitch()
          });
        }
        reportViewportBounds();
      });
      // Fires once up front too, so the "map extent" Polifunzionalità reading
      // (2026-07-26 feedback) has a value before the user pans/zooms at all.
      reportViewportBounds();

      // Click on background map deselects the hexagon.
      map.on('click', (e) => {
        if (drawModeRef.current) return;
        const features = map.queryRenderedFeatures(e.point, { layers: ['povo-grid-fill'] });
        if (features.length === 0) {
          if (selectedFeatureId !== null) {
            map.setFeatureState({ source: 'povo-grid-src', id: selectedFeatureId }, { selected: false });
            selectedFeatureId = null;
          }
          if (onSelectHex) onSelectHex(null);
        }
      });

      // Click on a cluster zooms in to progressively expand it.
      map.on('click', 'poi-clusters', async (e) => {
        if (drawModeRef.current) return;
        const feature = e.features[0];
        const clusterId = feature.properties.cluster_id;
        const source = map.getSource('povo-pois-source');
        const zoom = await source.getClusterExpansionZoom(clusterId);
        map.easeTo({ center: feature.geometry.coordinates, zoom, duration: 500 });
      });
      map.on('mouseenter', 'poi-clusters', () => { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', 'poi-clusters', () => { map.getCanvas().style.cursor = ''; });

      // Click on an unclustered POI icon opens a popup with its details.
      map.on('mouseenter', 'poi-unclustered-icon', () => { map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', 'poi-unclustered-icon', () => { map.getCanvas().style.cursor = ''; });
      map.on('click', 'poi-unclustered-icon', (e) => {
        if (drawModeRef.current) return;
        if (!e.features.length) return;
        const feature = e.features[0];
        const props = feature.properties;
        const coords = feature.geometry.coordinates.slice();

        new maplibregl.Popup({ closeButton: true, offset: 12, maxWidth: '320px' })
          .setLngLat(coords)
          .setHTML(buildPoiPopupHtml(props))
          .addTo(map);
      });

      setLoaded(true);
    });

    return () => {
      cancelled = true;
      resizeObserver.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Basemap style switch: setStyle() wipes all custom sources/layers, so they
  // (and the current prop-driven visual state) are re-applied once the new
  // style finishes loading. Skips the very first run (mount already set the
  // initial style via the constructor above).
  //
  // { diff: false } is required here: MapLibre's default setStyle() diffs the
  // *current* style (which includes our injected hex/POI/heatmap/draw layers)
  // against the *new* style JSON (which never contains them, since they're
  // added programmatically, not part of any style.json). The diff then emits
  // removeLayer/removeSource ops for everything not in the new style -- i.e.
  // it silently deletes our custom layers -- and because that diff path
  // mutates the existing Style object rather than recreating it, 'style.load'
  // never fires, so the re-add below never runs either. This is what caused
  // hexagons/clusters/heatmap to disappear after switching basemaps (reported
  // 2026-07-26). diff:false forces a full style reload, which reliably fires
  // 'style.load' and gives us a clean slate to rebuild on, matching what the
  // comments below already assumed was happening.
  useEffect(() => {
    if (appliedMapStyleRef.current === mapStyle) return;
    appliedMapStyleRef.current = mapStyle;
    const map = mapRef.current;
    if (!map) return;

    map.setStyle(buildMapStyleDefinition(mapStyle), { diff: false });
    map.once('style.load', () => {
      addCustomLayers(map);
      applyCurrentState(map);
    });
  }, [mapStyle]);

  // React to layer-visibility / styling prop changes after the map has loaded.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded || !map.getLayer('povo-grid-fill')) return;
    const visibility = showGrid ? 'visible' : 'none';
    map.setLayoutProperty('povo-grid-fill', 'visibility', visibility);
    map.setLayoutProperty('povo-grid-outline', 'visibility', visibility);
  }, [showGrid, loaded]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded || !map.getLayer('poi-heatmap')) return;
    const iconsVisible = poiViewMode === 'icons' ? 'visible' : 'none';
    const heatmapVisible = poiViewMode === 'heatmap' ? 'visible' : 'none';
    map.setLayoutProperty('poi-clusters', 'visibility', iconsVisible);
    map.setLayoutProperty('poi-cluster-count', 'visibility', iconsVisible);
    map.setLayoutProperty('poi-unclustered-icon', 'visibility', iconsVisible);
    map.setLayoutProperty('poi-heatmap', 'visibility', heatmapVisible);
  }, [poiViewMode, loaded]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded || !map.getLayer('povo-grid-fill')) return;
    map.setPaintProperty('povo-grid-fill', 'fill-color', buildFillColorExpression(gridMetric));
  }, [gridMetric, loaded]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded || !map.getLayer('povo-grid-fill')) return;
    const hexFilter = buildHexRangeFilter(gridMetric, hexValueRange);
    map.setFilter('povo-grid-fill', hexFilter);
    map.setFilter('povo-grid-outline', hexFilter);
  }, [gridMetric, hexValueRange, loaded]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded || !map.getLayer('poi-unclustered-icon')) return;
    map.setFilter('poi-unclustered-icon', unclusteredCategoryFilter(activePoiCategories));
  }, [activePoiCategories, loaded]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded || !map.getLayer('poi-heatmap')) return;
    map.setPaintProperty('poi-heatmap', 'heatmap-radius', buildHeatmapRadiusExpression(heatmapRadius));
  }, [heatmapRadius, loaded]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;

    // Skip forcing the pitch/bearing preset the very first time this runs
    // after mount -- that first run just applies whatever showTerrain came
    // from the URL, and the camera's exact pitch/bearing was already set at
    // construction time (initialViewState). Only an explicit later toggle
    // (the sidebar checkbox) should ease to the fixed 3D/2D preset angles.
    const isInitial = !didInitTerrainRef.current;
    didInitTerrainRef.current = true;

    if (showTerrain) {
      map.setTerrain({ source: 'aws-terrain', exaggeration: 1.3 });
      if (!isInitial) map.easeTo({ pitch: 50, bearing: -10, duration: 800 });
    } else {
      map.setTerrain(null);
      if (!isInitial) map.easeTo({ pitch: 0, bearing: 0, duration: 800 });
    }
  }, [showTerrain, loaded]);

  // Draw-an-area tool: click adds vertices, double-click closes the polygon
  // and reports category-count stats for whatever PoIs fall inside it.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded || !map.getSource('draw-area-src')) return;

    drawModeRef.current = drawMode;
    if (!drawMode) return;

    drawPointsRef.current = [];
    map.doubleClickZoom.disable();
    map.getCanvas().style.cursor = 'crosshair';

    const renderDrawSource = () => {
      const pts = drawPointsRef.current;
      const features = [];
      if (pts.length > 1) {
        features.push({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: pts } });
      }
      pts.forEach((p) => features.push({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: p } }));
      const src = map.getSource('draw-area-src');
      if (src) src.setData({ type: 'FeatureCollection', features });
    };

    const handleClick = (e) => {
      drawPointsRef.current.push([e.lngLat.lng, e.lngLat.lat]);
      renderDrawSource();
    };

    const handleDblClick = (e) => {
      e.preventDefault();
      const pts = drawPointsRef.current;
      if (pts.length < 3) return;

      const ring = [...pts, pts[0]];
      const polygonGeom = { type: 'Polygon', coordinates: [ring] };
      const src = map.getSource('draw-area-src');
      if (src) {
        src.setData({ type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: polygonGeom }] });
      }

      const stats = computePoiStatsInPolygon(polygonGeom, poisDataRef.current);
      // Polifunzionalità for a drawn area is the average of the pipeline's
      // own precomputed hex scores, same as the "map extent" reading in
      // App.jsx -- not a separate formula (see hexAgg's null-safe use in
      // Sidebar.jsx when no hexagon centroid falls inside a small/oddly
      // placed shape).
      stats.hexAgg = aggregateHexScoresInPolygon(gridDataRef.current, polygonGeom);
      if (onDrawComplete) onDrawComplete(stats);
    };

    map.on('click', handleClick);
    map.on('dblclick', handleDblClick);

    return () => {
      map.off('click', handleClick);
      map.off('dblclick', handleDblClick);
      map.doubleClickZoom.enable();
      map.getCanvas().style.cursor = '';
    };
  }, [drawMode, loaded]);

  // External "clear drawn area" trigger (a counter bumped by the parent).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded || !clearDrawSignal) return;
    drawPointsRef.current = [];
    const src = map.getSource('draw-area-src');
    if (src) src.setData(EMPTY_FC);
  }, [clearDrawSignal, loaded]);

  // Row click in the PoI table: fly to that PoI and open its popup, the same
  // one shown when clicking its icon directly on the map.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded || !flyToTarget) return;
    const { lng, lat } = flyToTarget;
    if (typeof lng !== 'number' || typeof lat !== 'number') return;

    map.flyTo({ center: [lng, lat], zoom: Math.max(map.getZoom(), 17), duration: 1200 });

    const openPopup = () => {
      new maplibregl.Popup({ closeButton: true, offset: 12, maxWidth: '320px' })
        .setLngLat([lng, lat])
        .setHTML(buildPoiPopupHtml(flyToTarget))
        .addTo(map);
    };
    map.once('moveend', openPopup);
    return () => map.off('moveend', openPopup);
  }, [flyToTarget, loaded]);

  return (
    <div className="relative w-full h-full">
      <div ref={mapContainerRef} className="w-full h-full" />
    </div>
  );
}
