import React, { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import {
  buildFillColorExpression,
  buildClusterCategoryColorExpression,
  CLUSTER_CATEGORY_PROPERTIES,
  createPoiIconImage,
  computePoiStatsInPolygon,
  buildMapStyleDefinition,
  computeBboxFromGeoJSON,
  buildPoiPopupHtml
} from '../config/mapConfig';

const EMPTY_FC = { type: 'FeatureCollection', features: [] };
const ZOOM_OUT_LEVELS_BEYOND_BOUNDARY = 2;

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
  poisData,
  drawMode,
  onDrawComplete,
  clearDrawSignal,
  mapStyle,
  flyToTarget
}) {
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);
  const [loaded, setLoaded] = useState(false);
  const drawModeRef = useRef(false);
  const drawPointsRef = useRef([]);
  const poisDataRef = useRef(poisData);
  const didMountStyleRef = useRef(false);

  // Latest prop values, kept in refs so the layer-(re)creation logic below
  // (shared between the initial mount and every basemap-style switch) always
  // reads current state instead of whatever was captured at mount time.
  const stateRef = useRef({ showGrid, poiViewMode, gridMetric, activePoiCategories, showTerrain });
  useEffect(() => {
    stateRef.current = { showGrid, poiViewMode, gridMetric, activePoiCategories, showTerrain };
  }, [showGrid, poiViewMode, gridMetric, activePoiCategories, showTerrain]);

  useEffect(() => {
    poisDataRef.current = poisData;
  }, [poisData]);

  // Adds every custom source/layer this app overlays on top of whichever
  // basemap style is currently active. Called once on mount, and again after
  // every map.setStyle() call (setStyle wipes all sources/layers -- runtime
  // symbol images added via addImage are cleared too, but self-heal via the
  // 'styleimagemissing' handler registered once below).
  const addCustomLayers = (map) => {
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

    map.addLayer({
      id: 'povo-grid-fill',
      type: 'fill',
      source: 'povo-grid-src',
      layout: { visibility: 'none' },
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
        'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 11, 15, 15, 30],
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
    const { showGrid: sg, poiViewMode: pvm, gridMetric: gm, activePoiCategories: apc, showTerrain: st } = stateRef.current;

    const gridVisibility = sg ? 'visible' : 'none';
    map.setLayoutProperty('povo-grid-fill', 'visibility', gridVisibility);
    map.setLayoutProperty('povo-grid-outline', 'visibility', gridVisibility);
    map.setPaintProperty('povo-grid-fill', 'fill-color', buildFillColorExpression(gm));

    const iconsVisible = pvm === 'icons' ? 'visible' : 'none';
    const heatmapVisible = pvm === 'heatmap' ? 'visible' : 'none';
    map.setLayoutProperty('poi-clusters', 'visibility', iconsVisible);
    map.setLayoutProperty('poi-cluster-count', 'visibility', iconsVisible);
    map.setLayoutProperty('poi-unclustered-icon', 'visibility', iconsVisible);
    map.setLayoutProperty('poi-heatmap', 'visibility', heatmapVisible);
    map.setFilter('poi-unclustered-icon', unclusteredCategoryFilter(apc));

    if (st) {
      map.setTerrain({ source: 'aws-terrain', exaggeration: 1.3 });
    }
  };

  // Mount the map once, 2D by default (pitch/bearing 0, no 3D terrain).
  useEffect(() => {
    if (!mapContainerRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: buildMapStyleDefinition(mapStyle),
      center: [11.155, 46.066], // Povo, Trento
      zoom: 14,
      pitch: 0,
      bearing: 0,
      maxPitch: 75,
      antialias: true
    });

    mapRef.current = map;

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
      addCustomLayers(map);

      // Zoomed-out limit: 2 zoom levels beyond whatever level exactly fits
      // the full Povo boundary on screen. Also caps panning (maxBounds) to a
      // generously padded version of the same boundary, so the boundary can
      // never be scrolled/panned entirely out of view (2026-07-25 feedback).
      fetch('./data/povo_boundary.json')
        .then((res) => res.json())
        .then((boundaryGeoJSON) => {
          const [minLng, minLat, maxLng, maxLat] = computeBboxFromGeoJSON(boundaryGeoJSON);
          const bounds = new maplibregl.LngLatBounds([minLng, minLat], [maxLng, maxLat]);
          const cam = map.cameraForBounds(bounds, { padding: 0 });
          if (cam && typeof cam.zoom === 'number') {
            map.setMinZoom(Math.max(0, cam.zoom - ZOOM_OUT_LEVELS_BEYOND_BOUNDARY));
          }

          // Pad the boundary bbox by its own width/height on every side (a
          // generous 3x-area buffer) so panning stays smooth even at the
          // zoomed-out limit above, while never allowing the boundary itself
          // to leave the viewport entirely.
          const lngPad = (maxLng - minLng) || 0.01;
          const latPad = (maxLat - minLat) || 0.01;
          map.setMaxBounds([
            [minLng - lngPad, minLat - latPad],
            [maxLng + lngPad, maxLat + latPad]
          ]);
        })
        .catch((err) => console.error('Failed to compute boundary min-zoom/max-bounds', err));

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

        new maplibregl.Popup({ closeButton: true, offset: 12, maxWidth: '260px' })
          .setLngLat(coords)
          .setHTML(buildPoiPopupHtml(props))
          .addTo(map);
      });

      setLoaded(true);
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Basemap style switch: setStyle() wipes all custom sources/layers, so they
  // (and the current prop-driven visual state) are re-applied once the new
  // style finishes loading. Skips the very first run (mount already set the
  // initial style via the constructor above).
  useEffect(() => {
    if (!didMountStyleRef.current) {
      didMountStyleRef.current = true;
      return;
    }
    const map = mapRef.current;
    if (!map) return;

    map.setStyle(buildMapStyleDefinition(mapStyle));
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
    if (!map || !loaded || !map.getLayer('poi-unclustered-icon')) return;
    map.setFilter('poi-unclustered-icon', unclusteredCategoryFilter(activePoiCategories));
  }, [activePoiCategories, loaded]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;
    if (showTerrain) {
      map.setTerrain({ source: 'aws-terrain', exaggeration: 1.3 });
      map.easeTo({ pitch: 50, bearing: -10, duration: 800 });
    } else {
      map.setTerrain(null);
      map.easeTo({ pitch: 0, bearing: 0, duration: 800 });
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
      new maplibregl.Popup({ closeButton: true, offset: 12, maxWidth: '260px' })
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
