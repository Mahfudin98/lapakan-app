import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import type { Job } from "../api/types";
import { relativeTime } from "../lib/format";
import { RegionName } from "./RegionName";
import { ProgressBar, StatusPill } from "./ui";

export const ACTIVE = ["queued", "running"];

export function useJobs() {
  return useQuery({
    queryKey: ["jobs"],
    queryFn: api.jobs,
    refetchInterval: (q) => (q.state.data?.some((j) => ACTIVE.includes(j.status)) ? 2500 : 15_000),
  });
}

export function progressPct(job: Job): number {
  if (job.status === "done") return 100;
  const t = job.progress.total_queries ?? 0;
  return t ? ((job.progress.done_queries ?? 0) / t) * 100 : 0;
}

function Item({ job, onOpen }: { job: Job; onOpen: (id: string) => void }) {
  const kws = job.params.resolved_keywords ?? job.params.keywords;
  const found = job.progress.found ?? 0;
  return (
    <li>
      <button type="button" onClick={() => onOpen(job.id)} data-testid="history-item"
        className="w-full rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition hover:border-indigo-300 hover:shadow">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate font-semibold"><RegionName kode={job.params.region_kode} /></p>
            <p className="truncate text-sm text-slate-500">{kws.join(" · ")}</p>
          </div>
          <StatusPill status={job.status} />
        </div>
        {ACTIVE.includes(job.status) && (
          <div className="mt-3"><ProgressBar pct={progressPct(job)} status={job.status} /></div>
        )}
        <p className="mt-2 text-xs text-slate-500">
          <span className="font-medium text-slate-700">{found.toLocaleString("id-ID")} toko</span> ·{" "}
          {relativeTime(job.created_at)}
        </p>
      </button>
    </li>
  );
}

export function History({ onOpen, onOpenAll }: { onOpen: (id: string) => void; onOpenAll: () => void }) {
  const { data = [], isLoading, isError, error } = useJobs();
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? data : data.slice(0, 5);
  const all = useQuery({ queryKey: ["places-total"], queryFn: () => api.places(new URLSearchParams({ page_size: "1", region_filter: "all" })) });
  const total = all.data?.total ?? 0;

  return (
    <section aria-label="Pencarian sebelumnya" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">Pencarian sebelumnya</h2>
        {total > 0 && (
          <button type="button" onClick={onOpenAll} className="text-sm font-medium text-indigo-700 hover:underline">
            Lihat semua {total.toLocaleString("id-ID")} toko tersimpan →
          </button>
        )}
      </div>
      {isLoading && <p className="text-sm text-slate-500">Memuat…</p>}
      {isError && <p role="alert" className="text-sm text-red-700">Gagal memuat riwayat: {error.message}</p>}
      {!isLoading && !isError && data.length === 0 && (
        <p className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
          Belum ada pencarian. Mulai dengan memilih wilayah dan jenis toko.
        </p>
      )}
      <ul className="space-y-3">
        {shown.map((j) => <Item key={j.id} job={j} onOpen={onOpen} />)}
      </ul>
      {data.length > 5 && (
        <button type="button" onClick={() => setExpanded((e) => !e)} className="w-full rounded-xl py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-50">
          {expanded ? "Tampilkan lebih sedikit" : `Tampilkan ${data.length - 5} pencarian lainnya`}
        </button>
      )}
    </section>
  );
}
