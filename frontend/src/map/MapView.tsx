/** MapLibre command-centre map: ICGC basemap, contours (arrived vs forecast), assets by tier. */

import maplibregl, { Map as MLMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";

import type { FeatureCollection, Scenario, ScoredResult, SpreadForecast, Tier } from "../api/types";
import { TIER_COLORS } from "../lib/ranks";
import { basemapStyle } from "./basemap";

interface Props {
  scenario: Scenario | undefined;
  spread: SpreadForecast | undefined;
  scored: ScoredResult | undefined;
  t: number; // scrubber minutes
  selectedId: string | null;
  onSelect: (assetId: string | null) => void;
}

const EMPTY_FC: FeatureCollection = { type: "FeatureCollection", features: [] };

export default function MapView({
  scenario,
  spread,
  scored,
  t,
  selectedId,
  onSelect,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const [ready, setReady] = useState(false);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  // Init once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: basemapStyle(),
      center: [1.25, 41.8],
      zoom: 10,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    (window as unknown as { __map?: MLMap }).__map = map; // e2e/debug handle
    map.on("load", () => {
      map.addSource("spread", { type: "geojson", data: EMPTY_FC });
      map.addSource("assets", { type: "geojson", data: EMPTY_FC });

      map.addLayer({
        id: "contours-fill",
        type: "fill",
        source: "spread",
        paint: {
          "fill-color": ["case", ["<=", ["get", "eta_minutes"], -1], "#EF4444", "#F97316"] as never,
          "fill-opacity": ["case", ["<=", ["get", "eta_minutes"], -1], 0.3, 0.12] as never,
        },
      });
      map.addLayer({
        id: "contours-line",
        type: "line",
        source: "spread",
        paint: {
          "line-color": ["case", ["<=", ["get", "eta_minutes"], -1], "#EF4444", "#FB923C"] as never,
          "line-width": ["case", ["<=", ["get", "eta_minutes"], -1], 2.5, 1.2] as never,
          "line-opacity": 0.85,
        },
      });
      map.addLayer({
        id: "assets",
        type: "circle",
        source: "assets",
        paint: {
          "circle-radius": ["case", ["==", ["get", "tier"], "critical"], 9, 6] as never,
          "circle-color": [
            "match",
            ["get", "tier"],
            "critical",
            TIER_COLORS.critical,
            "high",
            TIER_COLORS.high,
            "medium",
            TIER_COLORS.medium,
            "low",
            TIER_COLORS.low,
            TIER_COLORS.not_threatened,
          ] as never,
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#0B1220",
        },
      });
      map.addLayer({
        id: "assets-selected",
        type: "circle",
        source: "assets",
        filter: ["==", ["get", "asset_id"], ""],
        paint: {
          "circle-radius": 11,
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-width": 2.5,
          "circle-stroke-color": "#38BDF8",
        },
      });
      map.addLayer({
        id: "ignition",
        type: "circle",
        source: { type: "geojson", data: EMPTY_FC },
        paint: {
          "circle-radius": 7,
          "circle-color": "#EF4444",
          "circle-stroke-width": 2,
          "circle-stroke-color": "#FCA5A5",
        },
      });

      map.on("click", "assets", (e) => {
        const id = e.features?.[0]?.properties?.asset_id as string | undefined;
        onSelectRef.current(id ?? null);
      });
      map.on("mouseenter", "assets", () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", "assets", () => (map.getCanvas().style.cursor = ""));
      setReady(true);
    });
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Spread contours + fit bounds.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !spread) return;
    (map.getSource("spread") as maplibregl.GeoJSONSource)?.setData(spread as never);
    const coords: number[][] = [];
    for (const f of spread.features) collectCoords(f.geometry.coordinates, coords);
    if (coords.length) {
      const bounds = coords.reduce(
        (b, [x, y]) => b.extend([x, y]),
        new maplibregl.LngLatBounds(coords[0] as [number, number], coords[0] as [number, number]),
      );
      map.fitBounds(bounds, { padding: 80, duration: 600 });
    }
  }, [ready, spread]);

  // Assets (scored features carry tier/risk props).
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !scored) return;
    (map.getSource("assets") as maplibregl.GeoJSONSource)?.setData(scored as never);
  }, [ready, scored]);

  // Ignition point.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !scenario) return;
    (map.getSource("ignition") as maplibregl.GeoJSONSource)?.setData({
      type: "FeatureCollection",
      features: [{ type: "Feature", geometry: scenario.ignition_point, properties: {} }],
    } as never);
  }, [ready, scenario]);

  // Scrubber: restyle contours by arrival time vs t.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.setPaintProperty("contours-fill", "fill-color", [
      "case",
      ["<=", ["get", "eta_minutes"], t],
      "#EF4444",
      "#F97316",
    ]);
    map.setPaintProperty("contours-fill", "fill-opacity", [
      "case",
      ["<=", ["get", "eta_minutes"], t],
      0.32,
      0.12,
    ]);
    map.setPaintProperty("contours-line", "line-color", [
      "case",
      ["<=", ["get", "eta_minutes"], t],
      "#EF4444",
      "#FB923C",
    ]);
    map.setPaintProperty("contours-line", "line-width", [
      "case",
      ["<=", ["get", "eta_minutes"], t],
      2.5,
      1.2,
    ]);
  }, [ready, t]);

  // Selection ring.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.setFilter("assets-selected", ["==", ["get", "asset_id"], selectedId ?? ""]);
  }, [ready, selectedId]);

  return <div ref={containerRef} className="h-full w-full" data-testid="map" />;
}

function collectCoords(coords: unknown, out: number[][]): void {
  if (!Array.isArray(coords)) return;
  if (typeof coords[0] === "number" && typeof coords[1] === "number") {
    out.push(coords as number[]);
    return;
  }
  for (const c of coords) collectCoords(c, out);
}

export type { Tier };
