import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import type { Job, JobCreate, Region } from "../api/types";
import { useDebounced } from "../hooks/useDebounced";
import { CategoryPicker } from "./CategoryPicker";
import { RegionPicker } from "./RegionPicker";
import { Spinner } from "./ui";

const DEFAULT_MAX = 200;

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="flex items-center gap-2 text-base font-semibold">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-600 text-xs text-white">{n}</span>
        {title}
      </h2>
      {children}
    </section>
  );
}

function estimate(queries: number, detail: boolean): string {
  const lo = Math.max(1, Math.round((queries * (detail ? 40 : 15)) / 60));
  const hi = Math.max(lo + 1, Math.round((queries * (detail ? 120 : 45)) / 60));
  return `${lo}–${hi} menit`;
}

export function NewSearch({ onCreated }: { onCreated: (job: Job) => void }) {
  const [region, setRegion] = useState<Region | null>(null);
  const [categoryIds, setCategoryIds] = useState<number[]>([]);
  const [keywords, setKeywords] = useState<string[]>([]);
  const [maxResults, setMaxResults] = useState(String(DEFAULT_MAX));
  const [detail, setDetail] = useState(true);
  const [force, setForce] = useState(false);

  const max = Number.parseInt(maxResults, 10);
  const maxValid = Number.isInteger(max) && max >= 1 && max <= 5000;

  const body: JobCreate | null = useMemo(
    () =>
      region && (categoryIds.length || keywords.length) && maxValid
        ? { region_kode: region.kode, category_ids: categoryIds, keywords, max_results: max, detail, force_refresh: force }
        : null,
    [region, categoryIds, keywords, max, maxValid, detail, force],
  );
  const dBody = useDebounced(body, 300);

  const preview = useQuery({
    queryKey: ["preview", dBody],
    queryFn: () => api.previewJob(dBody!),
    enabled: !!dBody,
    retry: false,
    staleTime: 60_000,
  });

  const create = useMutation({ mutationFn: api.createJob, onSuccess: onCreated });

  const ready = !!body && body === dBody && preview.isSuccess && !create.isPending;

  let hint = "";
  if (!region) hint = "Pilih wilayah dulu";
  else if (!categoryIds.length && !keywords.length) hint = "Pilih minimal satu jenis toko";
  else if (!maxValid) hint = "Batas hasil harus 1–5000";

  return (
    <form
      className="space-y-7 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7"
      onSubmit={(e) => {
        e.preventDefault();
        if (body && ready) create.mutate(body);
      }}
    >
      <Step n={1} title="Di mana?">
        <RegionPicker onChange={setRegion} />
      </Step>

      <Step n={2} title="Toko apa?">
        <CategoryPicker categoryIds={categoryIds} keywords={keywords}
          onCategoryIds={setCategoryIds} onKeywords={setKeywords} />
      </Step>

      <details className="group rounded-lg bg-slate-50 px-4 py-3 text-sm">
        <summary className="cursor-pointer select-none font-medium text-slate-700">Opsi lanjutan</summary>
        <div className="mt-3 space-y-3">
          <label className="flex items-start gap-2.5">
            <input type="checkbox" checked={detail} onChange={(e) => setDetail(e.target.checked)} className="mt-1" />
            <span>
              <span className="font-medium">Lengkapi detail tiap toko</span>
              <span className="block text-xs text-slate-500">
                Alamat lengkap, website, jam buka, dan pengecekan wilayah yang lebih akurat. Lebih lambat.
              </span>
            </span>
          </label>
          <label className="flex items-start gap-2.5">
            <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} className="mt-1" />
            <span>
              <span className="font-medium">Abaikan cache</span>
              <span className="block text-xs text-slate-500">Pencarian yang sama dipakai ulang selama 7 hari. Centang untuk mengambil ulang.</span>
            </span>
          </label>
          <div>
            <label htmlFor="max" className="font-medium">Batas jumlah toko</label>
            <input id="max" type="number" min={1} max={5000} value={maxResults} onChange={(e) => setMaxResults(e.target.value)}
              className="ml-3 w-24 rounded-lg border border-slate-300 px-3 py-1.5" />
            <span className="ml-2 text-xs text-slate-500">total untuk seluruh pencarian</span>
          </div>
        </div>
      </details>

      <div aria-live="polite" className="space-y-3">
        {body && preview.isFetching && (
          <p className="flex items-center gap-2 text-sm text-slate-500"><Spinner /> Menyusun rencana…</p>
        )}
        {body && preview.isError && (
          <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{preview.error.message}</p>
        )}
        {body && preview.isSuccess && !preview.isFetching && (
          <p className="rounded-lg bg-indigo-50 p-3 text-sm text-indigo-900" data-testid="plan">
            <strong>{preview.data.total_queries}</strong> pencarian akan dijalankan · perkiraan{" "}
            {estimate(preview.data.total_queries, detail)}. Hasil muncul langsung selagi berjalan.
          </p>
        )}
        <button type="submit" disabled={!ready}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 py-3.5 text-base font-semibold text-white shadow-sm transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-300">
          {create.isPending ? <><Spinner className="h-5 w-5" /> Memulai…</> : hint || "Mulai cari toko"}
        </button>
        {create.isError && <p role="alert" className="text-sm text-red-700">{create.error.message}</p>}
      </div>
    </form>
  );
}
