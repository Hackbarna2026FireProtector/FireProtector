/** ICGC topographic raster basemap (EPSG:3857 tiles), darkened for the command-centre theme. */

import type { StyleSpecification } from "maplibre-gl";

export const ICGC_TILES =
  "https://geoserveis.icgc.cat/servei/catalunya/mapa-base/wmts/topografic/MON3857NW/{z}/{x}/{y}.png";

export function basemapStyle(): StyleSpecification {
  return {
    version: 8,
    sources: {
      icgc: {
        type: "raster",
        tiles: [ICGC_TILES],
        tileSize: 256,
        attribution: "© Institut Cartogràfic i Geològic de Catalunya",
        maxzoom: 19,
      },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": "#0B1220" } },
      {
        id: "icgc",
        type: "raster",
        source: "icgc",
        paint: {
          "raster-saturation": -0.75,
          "raster-brightness-max": 0.55,
          "raster-contrast": 0.15,
          "raster-opacity": 0.85,
        },
      },
    ],
  };
}
