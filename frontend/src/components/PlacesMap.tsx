import L from "leaflet";
import "leaflet.markercluster";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";
import { useEffect, useRef } from "react";
import type { MapPoint } from "../api/types";
import type { RefPoint } from "../lib/filters";

interface Props {
  points: MapPoint[];
  selectedId: number | null;
  hoveredId?: number | null;
  onSelect: (id: number) => void;
  refPoint: RefPoint | null;
  picking: boolean;
  onPick: (lat: number, lng: number) => void;
}

const BASE_STYLE: L.CircleMarkerOptions = {
  radius: 7, color: "#3730a3", weight: 1.5, fillColor: "#6366f1", fillOpacity: 0.85,
};
const OUTSIDE_STYLE: L.CircleMarkerOptions = { ...BASE_STYLE, color: "#475569", fillColor: "#94a3b8" };
const HOVER_STYLE: L.CircleMarkerOptions = {
  radius: 10, color: "#9a3412", weight: 3, fillColor: "#fb923c", fillOpacity: 1,
};
const SELECTED_STYLE: L.CircleMarkerOptions = {
  radius: 11, color: "#991b1b", weight: 3, fillColor: "#ef4444", fillOpacity: 1,
};

function styleFor(p: MapPoint | undefined, selected: boolean): L.CircleMarkerOptions {
  if (selected) return SELECTED_STYLE;
  return p?.in_region === false ? OUTSIDE_STYLE : BASE_STYLE;
}

function tooltipEl(p: MapPoint): HTMLElement {
  // DOM + textContent (bukan innerHTML): nama toko berasal dari web, jangan dipercaya
  const el = document.createElement("div");
  const b = document.createElement("strong");
  b.textContent = p.nama;
  el.append(b);
  if (p.rating != null) el.append(document.createElement("br"), `★ ${p.rating.toFixed(1)}`);
  if (p.in_region === false) el.append(document.createElement("br"), "di luar wilayah");
  return el;
}

export function PlacesMap({ points, selectedId, hoveredId = null, onSelect, refPoint, picking, onPick }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<L.Map | null>(null);
  const cluster = useRef<L.MarkerClusterGroup | null>(null);
  const markers = useRef(new Map<number, L.CircleMarker>());
  const byId = useRef(new Map<number, MapPoint>());
  const refMarker = useRef<L.CircleMarker | null>(null);
  const prevSelected = useRef<number | null>(null);
  const prevHovered = useRef<number | null>(null);
  // callback terbaru tanpa memicu pembuatan ulang peta
  const cb = useRef({ onSelect, onPick, picking });
  cb.current = { onSelect, onPick, picking };

  // inisialisasi peta sekali
  useEffect(() => {
    if (!box.current) return;
    const m = L.map(box.current, { zoomControl: true }).setView([-2.5, 118], 5);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(m);
    const cg = L.markerClusterGroup({ chunkedLoading: true, maxClusterRadius: 50 });
    m.addLayer(cg);
    m.on("click", (e: L.LeafletMouseEvent) => {
      if (cb.current.picking) cb.current.onPick(e.latlng.lat, e.latlng.lng);
    });
    map.current = m;
    cluster.current = cg;
    const ro = new ResizeObserver(() => m.invalidateSize());
    ro.observe(box.current);
    return () => {
      ro.disconnect();
      m.remove();
      map.current = null;
      cluster.current = null;
      markers.current.clear();
    };
  }, []);

  // ganti marker saat data berubah
  useEffect(() => {
    const cg = cluster.current;
    const m = map.current;
    if (!cg || !m) return;
    cg.clearLayers();
    markers.current.clear();
    byId.current.clear();
    const layers: L.CircleMarker[] = [];
    for (const p of points) {
      byId.current.set(p.id, p);
      const mk = L.circleMarker([p.lat, p.lng], styleFor(p, p.id === selectedId));
      mk.bindTooltip(tooltipEl(p));
      mk.on("click", () => cb.current.onSelect(p.id));
      markers.current.set(p.id, mk);
      layers.push(mk);
    }
    cg.addLayers(layers);
    if (points.length) {
      m.fitBounds(L.latLngBounds(points.map((p) => [p.lat, p.lng] as [number, number])), {
        padding: [30, 30], maxZoom: 15,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points]);

  // sorot marker terpilih (dari klik baris atau klik marker)
  useEffect(() => {
    const prev = prevSelected.current;
    if (prev != null) markers.current.get(prev)?.setStyle(styleFor(byId.current.get(prev), false));
    prevSelected.current = selectedId;
    if (selectedId == null) return;
    const mk = markers.current.get(selectedId);
    if (!mk || !cluster.current) return;
    mk.setStyle(SELECTED_STYLE);
    mk.bringToFront();
    cluster.current.zoomToShowLayer(mk, () => {
      mk.openTooltip();
    });
  }, [selectedId, points]);

  // sorot sementara saat kartu di-hover (tanpa menggeser peta)
  useEffect(() => {
    const prev = prevHovered.current;
    if (prev != null && prev !== selectedId) markers.current.get(prev)?.setStyle(styleFor(byId.current.get(prev), false));
    prevHovered.current = hoveredId;
    if (hoveredId == null || hoveredId === selectedId) return;
    const mk = markers.current.get(hoveredId);
    if (mk) {
      mk.setStyle(HOVER_STYLE);
      mk.bringToFront();
    }
  }, [hoveredId, selectedId, points]);

  // titik acuan jarak
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    refMarker.current?.remove();
    refMarker.current = null;
    if (refPoint) {
      refMarker.current = L.circleMarker([refPoint.lat, refPoint.lng], {
        radius: 9, color: "#0369a1", weight: 3, fillColor: "#38bdf8", fillOpacity: 0.9,
      })
        .bindTooltip("Titik acuan", { permanent: false })
        .addTo(m);
    }
  }, [refPoint]);

  useEffect(() => {
    if (box.current) box.current.style.cursor = picking ? "crosshair" : "";
  }, [picking]);

  return (
    <div
      ref={box}
      data-testid="map"
      className="h-[60vh] min-h-[320px] w-full rounded-xl border border-slate-200 lg:h-[calc(100vh-11rem)]"
      role="application"
      aria-label="Peta hasil"
    />
  );
}
