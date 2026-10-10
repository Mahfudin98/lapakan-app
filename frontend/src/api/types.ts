export interface Region {
  kode: string;
  nama: string;
  level: number;
  parent_kode: string | null;
}

export interface RegionDetail extends Region {
  path: Region[];
}

export interface Category {
  id: number;
  nama: string;
  keyword: string;
}

export type JobStatus = "queued" | "running" | "done" | "failed" | "blocked" | "cancelled";

export interface JobProgress {
  total_queries?: number;
  done_queries?: number;
  cached_queries?: number;
  failed_queries?: number;
  current_query?: string | null;
  phase?: string;
  found?: number;
  query_found?: number;
  new?: number;
  updated?: number;
  truncated?: boolean;
  errors?: { query: string; error: string }[];
}

export interface JobParams {
  region_kode: string;
  category_ids: number[];
  keywords: string[];
  resolved_keywords?: string[];
  max_results: number;
  detail: boolean;
  force_refresh: boolean;
}

export interface Job {
  id: string;
  status: JobStatus;
  params: JobParams;
  progress: JobProgress;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface JobCreate {
  region_kode: string;
  category_ids: number[];
  keywords: string[];
  max_results?: number;
  detail: boolean;
  force_refresh: boolean;
}

export interface PlanPreview {
  total_queries: number;
  keywords: string[];
  queries: { keyword: string; region_kode: string; query: string }[];
}

export type SortKey = "skor" | "terdekat" | "terpopuler" | "rating" | "nama" | "terbaru";
export type RegionFilter = "all" | "hide_outside" | "inside_only";

export interface Place {
  id: number;
  nama: string;
  kategori_google: string | null;
  rating: number | null;
  review_count: number | null;
  alamat: string | null;
  telepon: string | null;
  website: string | null;
  maps_url: string | null;
  lat: number | null;
  lng: number | null;
  jam_buka: Record<string, unknown> | null;
  status_bisnis: string | null;
  region_kode: string | null;
  in_region: boolean | null;
  first_seen_at: string;
  last_scraped_at: string;
  distance_km: number | null;
  score: number | null;
}

export interface PlaceList {
  items: Place[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
  meta: { avg_rating: number; m: number; with_reviews: number; outside_count: number };
}

export interface MapPoint {
  id: number;
  nama: string;
  lat: number;
  lng: number;
  rating: number | null;
  review_count: number | null;
  in_region: boolean | null;
}

export interface MapPoints {
  points: MapPoint[];
  total: number;
  truncated: boolean;
}

export interface Facet {
  kategori: string;
  count: number;
}
