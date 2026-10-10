import type {
  Category, Facet, Job, JobCreate, MapPoints, Place, PlaceList, PlanPreview, Region, RegionDetail,
} from "./types";

export const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      const d = body?.detail;
      msg = typeof d === "string" ? d : Array.isArray(d) ? d.map((e) => e.msg).join("; ") : msg;
    } catch {
      /* body bukan JSON */
    }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  regions: (p: { level: number; parent?: string; q?: string; limit?: number }) => {
    const qs = new URLSearchParams({ level: String(p.level), limit: String(p.limit ?? 100) });
    if (p.parent) qs.set("parent", p.parent);
    if (p.q) qs.set("q", p.q);
    return request<Region[]>(`/regions?${qs}`);
  },
  region: (kode: string) => request<RegionDetail>(`/regions/${kode}`),
  categories: () => request<Category[]>("/categories"),
  previewJob: (body: JobCreate) =>
    request<PlanPreview>("/jobs/preview", { method: "POST", body: JSON.stringify(body) }),
  createJob: (body: JobCreate) =>
    request<Job>("/jobs", { method: "POST", body: JSON.stringify(body) }),
  places: (qs: URLSearchParams) => request<PlaceList>(`/places?${qs}`),
  placesMap: (qs: URLSearchParams) => request<MapPoints>(`/places/map?${qs}`),
  facets: (qs: URLSearchParams) => request<Facet[]>(`/places/facets?${qs}`),
  place: (id: number) => request<Place>(`/places/${id}`),
  exportUrl: (qs: URLSearchParams, format: "csv" | "xlsx") => {
    const p = new URLSearchParams(qs);
    p.set("format", format);
    return `${BASE}/places/export?${p}`;
  },
  jobs: () => request<Job[]>("/jobs?limit=30"),
  job: (id: string) => request<Job>(`/jobs/${id}`),
  cancelJob: (id: string) => request<Job>(`/jobs/${id}/cancel`, { method: "POST" }),
};
