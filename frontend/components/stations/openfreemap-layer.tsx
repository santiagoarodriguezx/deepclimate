"use client";

import "maplibre-gl/dist/maplibre-gl.css";
import { maplibreGL } from "@maplibre/maplibre-gl-leaflet";
import { useEffect } from "react";
import { useMap } from "react-leaflet";

const DEFAULT_STYLE = "https://tiles.openfreemap.org/styles/positron";

export function OpenFreeMapLayer() {
  const map = useMap();
  useEffect(() => {
    const layer = maplibreGL({
      style: process.env.NEXT_PUBLIC_OPENFREEMAP_STYLE_URL || DEFAULT_STYLE,
      interactive: false,
    });
    layer.addTo(map);
    return () => { layer.remove(); };
  }, [map]);
  return null;
}
