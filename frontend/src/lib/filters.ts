import type { Region, RegionFilter, SortKey } from "../api/types";

export interface Filters {
  q: string;
  jobId: string;
  region: Region | null;
  kategori: string[];
  minRating: string;
  minReviews: string;
  hasPhone: boolean;
  hasWebsite: boolean;
  hideClosed: boolean;
  regionFilter: RegionFilter;
}

export const DEFAULT_FILTERS: Filters = {
  q: "",
  jobId: "",
  region: null,
  kategori: [],
  minRating: "",
  minReviews: "",
  hasPhone: false,
  hasWebsite: false,
  hideClosed: false,
  regionFilter: "hide_outside",
};

export interface RefPoint {
  lat: number;
  lng: number;
  source: "geolocation" | "map";
}

export const SORT_LABEL: Record<SortKey, string> = {
  skor: "Skor terbaik (Bayesian)",
  terdekat: "Terdekat",
  terpopuler: "Terpopuler (ulasan terbanyak)",
  rating: "Rating tertinggi",
  nama: "Nama A–Z",
  terbaru: "Terbaru di-scrape",
};

/** Parameter filter (dipakai /places, /places/map, /places/facets). */
export function filterParams(f: Filters, opts: { skipKategori?: boolean } = {}): URLSearchParams {
  const p = new URLSearchParams();
  if (f.q.trim()) p.set("q", f.q.trim());
  if (f.jobId) p.set("job_id", f.jobId);
  if (f.region) p.set("region_kode", f.region.kode);
  if (!opts.skipKategori) f.kategori.forEach((k) => p.append("kategori", k));
  const rating = Number.parseFloat(f.minRating.replace(",", "."));
  if (Number.isFinite(rating) && rating > 0) p.set("min_rating", String(Math.min(rating, 5)));
  const reviews = Number.parseInt(f.minReviews, 10);
  if (Number.isFinite(reviews) && reviews > 0) p.set("min_reviews", String(reviews));
  if (f.hasPhone) p.set("has_phone", "true");
  if (f.hasWebsite) p.set("has_website", "true");
  if (f.hideClosed) p.set("hide_closed", "true");
  if (f.regionFilter !== "all") p.set("region_filter", f.regionFilter);
  return p;
}

/** Filter + pengurutan + titik acuan (dipakai /places dan ekspor). */
export function sortedParams(
  f: Filters, sort: SortKey, ref: RefPoint | null, m: string,
): URLSearchParams {
  const p = filterParams(f);
  p.set("sort", sort);
  if (ref) {
    p.set("lat", ref.lat.toFixed(6));
    p.set("lng", ref.lng.toFixed(6));
  }
  const mv = Number.parseInt(m, 10);
  if (sort === "skor" && Number.isInteger(mv) && mv >= 0) p.set("m", String(mv));
  return p;
}
