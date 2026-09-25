import { useEffect, useRef } from "react";
import maplibregl, { type GeoJSONSource, type StyleSpecification } from "maplibre-gl";
import type { Bus, Route } from "../api/types";
import { hhmm, loadColor, pct } from "../lib/format";

const STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";
const STYLE_TIMEOUT_MS = 8000;

// Fallback when OpenFreeMap is unreachable: plain background, only our route and bus layers (solution2 §6.10.1).
const BLANK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "background", type: "background", paint: { "background-color": "#eef0ee" } }],
};

const DELHI: [number, number] = [77.25, 28.6];

interface Props {
  routes: Route[];
  buses: Bus[];
  focusRouteId?: string | null;
}

function routesGeoJSON(routes: Route[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: routes.map((r) => ({
      type: "Feature",
      properties: { id: r.id, color: r.color, name: r.name },
      geometry: r.shape,
    })),
  };
}

function stopsGeoJSON(routes: Route[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: routes.flatMap((r) =>
      r.stops.map((s) => ({
        type: "Feature" as const,
        properties: { id: s.id, name: s.name, route_id: r.id },
        geometry: { type: "Point" as const, coordinates: [s.lon, s.lat] },
      })),
    ),
  };
}

function busesGeoJSON(buses: Bus[], routes: Route[]): GeoJSON.FeatureCollection {
  const names = new Map(routes.map((r) => [r.id, r.name]));
  return {
    type: "FeatureCollection",
    features: buses.map((b) => ({
      type: "Feature",
      properties: {
        id: b.id,
        route: names.get(b.route_id) ?? b.route_id,
        color: loadColor(b.load_factor, b.dark),
        dark: b.dark,
        load: pct(b.load_factor),
        delay: b.delay_min.toFixed(1),
        last_seen: hhmm(b.last_seen),
      },
      geometry: { type: "Point", coordinates: [b.lon, b.lat] },
    })),
  };
}

export function NetworkMap({ routes, buses, focusRouteId }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const data = useRef({ routes, buses });
  data.current = { routes, buses };

  useEffect(() => {
    if (!container.current) return;
    const map = new maplibregl.Map({ container: container.current, style: STYLE_URL, center: DELHI, zoom: 11 });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    let fellBack = false;
    const fallBack = () => {
      if (fellBack) return;
      fellBack = true;
      map.setStyle(BLANK_STYLE);
    };
    const timer = setTimeout(() => !map.isStyleLoaded() && fallBack(), STYLE_TIMEOUT_MS);
    map.on("error", () => {
      if (!map.isStyleLoaded()) fallBack();
    });

    // "style.load" fires for the initial style and again after a fallback setStyle, so layers are re-added.
    map.on("style.load", () => {
      const { routes, buses } = data.current;
      map.addSource("routes", { type: "geojson", data: routesGeoJSON(routes) });
      map.addSource("stops", { type: "geojson", data: stopsGeoJSON(routes) });
      map.addSource("buses", { type: "geojson", data: busesGeoJSON(buses, routes) });
      map.addLayer({
        id: "routes",
        type: "line",
        source: "routes",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": ["get", "color"], "line-width": 4, "line-opacity": 0.85 },
      });
      map.addLayer({
        id: "stops",
        type: "circle",
        source: "stops",
        minzoom: 13,
        paint: { "circle-radius": 3, "circle-color": "#ffffff", "circle-stroke-color": "#52514e", "circle-stroke-width": 1 },
      });
      // Dark buses (no report > 2 min): hollow grey ring. MapLibre circles cannot dash their stroke.
      map.addLayer({
        id: "buses",
        type: "circle",
        source: "buses",
        paint: {
          "circle-radius": 7,
          "circle-color": ["get", "color"],
          "circle-opacity": ["case", ["get", "dark"], 0.15, 1],
          "circle-stroke-color": ["case", ["get", "dark"], "#52514e", "#ffffff"],
          "circle-stroke-width": 2,
        },
      });
      if (routes.length) fitTo(map, routes);
    });

    map.on("click", "buses", (e) => {
      const f = e.features?.[0];
      if (!f) return;
      const p = f.properties as Record<string, string | boolean>;
      const status = p.dark === true || p.dark === "true" ? "<b>No signal</b> (dark)<br/>" : "";
      new maplibregl.Popup({ closeButton: true })
        .setLngLat((f.geometry as GeoJSON.Point).coordinates as [number, number])
        .setHTML(
          `<strong>${escapeHtml(String(p.route))}</strong><br/>${status}` +
            `Load ${p.load} · Delay ${p.delay} min<br/>Last seen ${p.last_seen}<br/><span class="muted">${escapeHtml(String(p.id))}</span>`,
        )
        .addTo(map);
    });
    map.on("mouseenter", "buses", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "buses", () => (map.getCanvas().style.cursor = ""));

    return () => {
      clearTimeout(timer);
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    (map?.getSource("routes") as GeoJSONSource | undefined)?.setData(routesGeoJSON(routes));
    (map?.getSource("stops") as GeoJSONSource | undefined)?.setData(stopsGeoJSON(routes));
    if (map && routes.length && map.getSource("routes")) fitTo(map, routes);
  }, [routes]);

  useEffect(() => {
    const src = mapRef.current?.getSource("buses") as GeoJSONSource | undefined;
    src?.setData(busesGeoJSON(buses, routes));
  }, [buses, routes]);

  useEffect(() => {
    const map = mapRef.current;
    const r = routes.find((x) => x.id === focusRouteId);
    if (map && r) fitTo(map, [r]);
  }, [focusRouteId, routes]);

  return (
    <div className="map-wrap">
      <div ref={container} className="map" />
      <div className="legend" aria-label="Bus load legend">
        <span><i style={{ background: loadColor(0.3) }} /> &lt;60%</span>
        <span><i style={{ background: loadColor(0.8) }} /> 60–100%</span>
        <span><i style={{ background: loadColor(1.2) }} /> &gt;100%</span>
        <span><i className="ring" /> no signal</span>
      </div>
    </div>
  );
}

function fitTo(map: maplibregl.Map, routes: Route[]) {
  const coords = routes.flatMap((r) => r.shape.coordinates);
  if (!coords.length) return;
  const b = new maplibregl.LngLatBounds(coords[0], coords[0]);
  coords.forEach((c) => b.extend(c));
  map.fitBounds(b, { padding: 40, duration: 600, maxZoom: 14 });
}

function escapeHtml(s: string) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}
