import React, { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import {
  POPUP_CATEGORY_BADGES,
  buildFillColorExpression,
  createPoiIconImage,
  formatSubType
} from '../config/mapConfig';

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
  activePoiCategories
}) {
  const mapContainerRef = useRef(null);
  const mapRef = useRef(null);
  const [loaded, setLoaded] = useState(false);

  // Mount the map once, 2D by default (pitch/bearing 0, no 3D terrain).
  useEffect(() => {
    if (!mapContainerRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: 'https://tiles.openfreemap.org/styles/liberty',
      center: [11.155, 46.066], // Povo, Trento
      zoom: 14,
      pitch: 0,
      bearing: 0,
      maxPitch: 75,
      antialias: true
    });

    mapRef.current = map;

    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right');

    // Lazily draw and register a symbol image the first time a given
    // icon_name is requested by the poi-unclustered-icon layer.
    map.on('styleimagemissing', (e) => {
      if (map.hasImage(e.id)) return;
      const imageData = createPoiIconImage(e.id);
      map.addImage(e.id, imageData, { pixelRatio: 2 });
    });

    map.on('load', () => {
      // 3D terrain source is registered but not activated by default.
      map.addSource('aws-terrain', {
        type: 'raster-dem',
        tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
        tileSize: 256,
        encoding: 'terrarium',
        maxzoom: 15
      });

      // 1. Povo boundary line — always visible.
      map.addSource('povo-boundary-src', {
        type: 'geojson',
        data: './data/povo_boundary.json'
      });

      map.addLayer({
        id: 'povo-boundary-line',
        type: 'line',
        source: 'povo-boundary-src',
        paint: {
          'line-color': '#f43f5e',
          'line-width': 2.5,
          'line-dasharray': [3, 2],
          'line-opacity': 0.85
        }
      });

      // 2. H3 hexagon grid — hidden by default.
      map.addSource('povo-grid-src', {
        type: 'geojson',
        data: './data/povo_grid.json',
        generateId: true
      });

      map.addLayer({
        id: 'povo-grid-fill',
        type: 'fill',
        source: 'povo-grid-src',
        layout: { visibility: 'none' },
        paint: {
          'fill-color': buildFillColorExpression(gridMetric),
          'fill-opacity': [
            'case',
            ['boolean', ['feature-state', 'selected'], false],
            0.88,
            ['boolean', ['feature-state', 'hover'], false],
            0.75,
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
            ['boolean', ['feature-state', 'selected'], false],
            '#ffffff',
            ['boolean', ['feature-state', 'hover'], false],
            '#6366f1',
            'rgba(255, 255, 255, 0.25)'
          ],
          'line-width': [
            'case',
            ['boolean', ['feature-state', 'selected'], false],
            3.5,
            ['boolean', ['feature-state', 'hover'], false],
            2.0,
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
        clusterRadius: 50
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
            0, 'rgba(0,0,0,0)',
            0.2, '#312e81',
            0.4, '#3b82f6',
            0.6, '#10b981',
            0.8, '#f59e0b',
            1, '#ec4899'
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
          'circle-color': ['step', ['get', 'point_count'], '#60a5fa', 10, '#fbbf24', 30, '#f472b6'],
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
        paint: {
          'text-color': '#0f172a'
        }
      });

      map.addLayer({
        id: 'poi-unclustered-icon',
        type: 'symbol',
        source: 'povo-pois-source',
        filter: unclusteredCategoryFilter(activePoiCategories),
        layout: {
          visibility: 'none',
          'icon-image': ['get', 'icon_name'],
          'icon-size': 1.2,
          'icon-allow-overlap': true
        }
      });

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

      // Click on a hexagon updates the sidebar radar chart.
      let selectedFeatureId = null;
      map.on('click', 'povo-grid-fill', (e) => {
        if (e.features.length > 0) {
          const feature = e.features[0];
          const props = feature.properties;

          if (selectedFeatureId !== null) {
            map.setFeatureState({ source: 'povo-grid-src', id: selectedFeatureId }, { selected: false });
          }
          selectedFeatureId = feature.id;
          map.setFeatureState({ source: 'povo-grid-src', id: selectedFeatureId }, { selected: true });

          if (onSelectHex) {
            onSelectHex(props);
          }
        }
      });

      // Click on background map deselects the hexagon.
      map.on('click', (e) => {
        const features = map.queryRenderedFeatures(e.point, { layers: ['povo-grid-fill'] });
        if (features.length === 0) {
          if (selectedFeatureId !== null) {
            map.setFeatureState({ source: 'povo-grid-src', id: selectedFeatureId }, { selected: false });
            selectedFeatureId = null;
          }
          if (onSelectHex) {
            onSelectHex(null);
          }
        }
      });

      // Click on a cluster zooms in to progressively expand it.
      map.on('click', 'poi-clusters', async (e) => {
        const feature = e.features[0];
        const clusterId = feature.properties.cluster_id;
        const source = map.getSource('povo-pois-source');
        const zoom = await source.getClusterExpansionZoom(clusterId);
        map.easeTo({ center: feature.geometry.coordinates, zoom, duration: 500 });
      });
      map.on('mouseenter', 'poi-clusters', () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', 'poi-clusters', () => {
        map.getCanvas().style.cursor = '';
      });

      // Click on an unclustered POI icon opens a popup with its details.
      map.on('mouseenter', 'poi-unclustered-icon', () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', 'poi-unclustered-icon', () => {
        map.getCanvas().style.cursor = '';
      });
      map.on('click', 'poi-unclustered-icon', (e) => {
        if (!e.features.length) return;
        const feature = e.features[0];
        const props = feature.properties;
        const coords = feature.geometry.coordinates.slice();
        const badge = POPUP_CATEGORY_BADGES[props.category] || { label: props.category, color: '#94a3b8' };
        const serviceType = formatSubType(props.sub_type);
        const hasImage = props.image_url && props.image_url.length > 0;
        const hasSocialFunction = props.social_function && props.social_function.length > 0;

        new maplibregl.Popup({ closeButton: true, offset: 12, maxWidth: '260px' })
          .setLngLat(coords)
          .setHTML(`
            <div style="font-family: Inter, sans-serif; width: 240px;">
              ${hasImage ? `
                <img src="${props.image_url}" alt=""
                     style="width: 100%; height: 120px; object-fit: cover; display: block;" />
              ` : ''}
              <div style="padding: 12px;">
                <div style="font-weight: 700; font-size: 14px; color: #0f172a; line-height: 1.3;">
                  ${props.name && props.name.length > 0 ? props.name : 'Punto di interesse'}
                </div>
                <span style="display: inline-block; margin-top: 6px; padding: 3px 9px; border-radius: 999px; font-size: 10px; font-weight: 700; color: #ffffff; background: ${badge.color};">
                  ${badge.label}
                </span>
                ${serviceType ? `
                  <div style="font-size: 11px; color: #64748b; margin-top: 6px; font-weight: 600;">
                    ${serviceType}
                  </div>
                ` : ''}
                ${hasSocialFunction ? `
                  <div style="margin-top: 10px; padding-top: 8px; border-top: 1px solid #e2e8f0;">
                    <div style="font-size: 10px; font-weight: 700; color: #6366f1; text-transform: uppercase; letter-spacing: 0.05em;">
                      Funzione Civica e Sociale
                    </div>
                    <div style="font-size: 11px; color: #334155; margin-top: 4px; line-height: 1.4;">
                      ${props.social_function}
                    </div>
                  </div>
                ` : ''}
              </div>
            </div>
          `)
          .addTo(map);
      });

      setLoaded(true);
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

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

  return (
    <div className="relative w-full h-full">
      <div ref={mapContainerRef} className="w-full h-full" />
    </div>
  );
}
