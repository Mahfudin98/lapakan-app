import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Job } from "../api/types";
import { PHASE_LABEL } from "../lib/format";
import { go } from "../lib/route";
import { ACTIVE, progressPct } from "./History";
import { RegionName } from "./RegionName";
import { ProgressBar, Spinner, StatusPill } from "./ui";

/** Ringkasan + progres langsung untuk satu job scraping, di atas daftar hasil. */
export function JobPanel({ job }: { job: Job }) {
  const qc = useQueryClient();
  const cancel = useMutation({
    mutationFn: () => api.cancelJob(job.id),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: ["job", job.id] });
    },
  });
  const rerun = useMutation({
    mutationFn: () =>
      api.createJob({
        region_kode: job.params.region_kode,
        category_ids: job.params.category_ids,
        keywords: job.params.keywords,
        max_results: job.params.max_results,
        detail: job.params.detail,
        force_refresh: true,
      }),
    onSuccess: (j) => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      go.job(j.id);
    },
  });

  const p = job.progress;
  const active = ACTIVE.includes(job.status);
  const total = p.total_queries ?? 0;
  const done = p.done_queries ?? 0;
  const kws = job.params.resolved_keywords ?? job.params.keywords;

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5" aria-label="Status pencarian" data-testid="job-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-lg font-bold"><RegionName kode={job.params.region_kode} /></h1>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-slate-600">
            {kws.map((k) => (
              <span key={k} className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs">{k}</span>
            ))}
            {job.params.detail && <span className="text-xs text-slate-500">· mode detail</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill status={job.status} />
          {active && (
            <button type="button" onClick={() => cancel.mutate()} disabled={cancel.isPending}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50 disabled:opacity-50">
              {cancel.isPending ? "Membatalkan…" : "Batalkan"}
            </button>
          )}
          {!active && (
            <button type="button" onClick={() => rerun.mutate()} disabled={rerun.isPending}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-50 disabled:opacity-50"
              title="Ambil ulang dari Google Maps (mengabaikan cache)">
              {rerun.isPending ? "Memulai…" : "Perbarui data"}
            </button>
          )}
        </div>
      </div>

      {(active || (total > 0 && job.status !== "done")) && (
        <div className="mt-4 space-y-1.5">
          <ProgressBar pct={progressPct(job)} status={job.status} />
          <p className="flex flex-wrap items-center justify-between gap-2 text-sm text-slate-600">
            <span>
              Pencarian <strong>{done}</strong> dari {total} · <strong data-testid="found-count">{(p.found ?? 0).toLocaleString("id-ID")}</strong> toko ditemukan
              {(p.cached_queries ?? 0) > 0 && <> · {p.cached_queries} dari cache</>}
            </span>
            {job.status === "running" && p.phase && (
              <span className="flex min-w-0 items-center gap-1.5 text-xs text-slate-500">
                <Spinner className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{PHASE_LABEL[p.phase] ?? p.phase}{p.current_query ? ` · ${p.current_query}` : ""}</span>
              </span>
            )}
            {job.status === "queued" && <span className="text-xs text-slate-500">Menunggu giliran…</span>}
          </p>
        </div>
      )}

      {job.status === "done" && (
        <p className="mt-3 text-sm text-slate-600">
          Selesai: <strong>{(p.found ?? 0).toLocaleString("id-ID")}</strong> toko dari {total} pencarian
          {(p.cached_queries ?? 0) > 0 && <> ({p.cached_queries} dari cache)</>}.
          {p.truncated && <span className="text-amber-700"> Berhenti di batas {job.params.max_results} toko; naikkan batas untuk cakupan penuh.</span>}
        </p>
      )}

      {job.status === "blocked" && (
        <div role="alert" className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <p className="font-semibold">Google Maps memblokir permintaan (captcha / lalu lintas tidak biasa).</p>
          <p className="mt-1 text-xs">Pencarian dihentikan dan tidak mencoba melewati captcha. Hasil yang sudah terkumpul tetap tersimpan di bawah. Tunggu beberapa jam, lalu coba lagi dengan pencarian lebih sedikit.</p>
        </div>
      )}
      {job.status === "failed" && job.error && (
        <p role="alert" className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-800">{job.error}</p>
      )}
      {job.status === "cancelled" && <p className="mt-3 text-sm text-slate-600">Dibatalkan. Hasil yang sudah terkumpul tetap tersimpan.</p>}

      {(p.errors?.length ?? 0) > 0 && (
        <details className="mt-3 text-xs text-slate-600">
          <summary className="cursor-pointer">{p.errors!.length} pencarian bermasalah</summary>
          <ul className="mt-1 space-y-1">
            {p.errors!.map((e) => <li key={e.query}><span className="font-medium">{e.query}</span>: {e.error}</li>)}
          </ul>
        </details>
      )}
      {(cancel.isError || rerun.isError) && (
        <p role="alert" className="mt-2 text-xs text-red-700">{(cancel.error ?? rerun.error)?.message}</p>
      )}
    </section>
  );
}
