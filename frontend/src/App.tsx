import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { api } from "./api/client";
import { ACTIVE, History } from "./components/History";
import { JobPanel } from "./components/JobPanel";
import { NewSearch } from "./components/NewSearch";
import { ResultsView } from "./components/ResultsView";
import { Spinner } from "./components/ui";
import { go, useRoute } from "./lib/route";

function JobPage({ id }: { id: string }) {
  const { data: job, isError, error } = useQuery({
    queryKey: ["job", id],
    queryFn: () => api.job(id),
    refetchInterval: (q) => (q.state.data && ACTIVE.includes(q.state.data.status) ? 2500 : false),
  });

  if (isError) {
    return (
      <p role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700">
        {error.message === "job tidak ditemukan"
          ? "Pencarian ini tidak ditemukan atau sudah dihapus."
          : `Gagal memuat pencarian: ${error.message}`}{" "}
        <button type="button" className="underline" onClick={go.home}>Kembali</button>
      </p>
    );
  }
  if (!job) return <p className="flex items-center gap-2 text-sm text-slate-500"><Spinner /> Memuat…</p>;

  return (
    <div className="space-y-4">
      <JobPanel job={job} />
      {/* key: hasil di-reset saat pindah job */}
      <ResultsView key={job.id} jobId={job.id} active={ACTIVE.includes(job.status)} />
    </div>
  );
}

export default function App() {
  const route = useRoute();

  useEffect(() => {
    document.title =
      route.name === "home" ? "Peta Toko" : route.name === "all" ? "Semua toko · Peta Toko" : "Hasil pencarian · Peta Toko";
  }, [route.name]);

  return (
    <div className="mx-auto min-h-screen max-w-7xl px-4 pb-10">
      <header className="flex items-center justify-between py-4">
        <button type="button" onClick={go.home} className="flex items-center gap-2 text-lg font-bold" aria-label="Peta Toko, ke beranda">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white">📍</span>
          Peta Toko
        </button>
        {route.name !== "home" && (
          <button type="button" onClick={go.home}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700">
            + Pencarian baru
          </button>
        )}
      </header>

      {route.name === "home" && (
        <div className="mx-auto max-w-2xl space-y-8">
          <div>
            <h1 className="text-2xl font-bold">Cari toko di Google Maps</h1>
            <p className="mt-1 text-slate-600">Pilih wilayah dan jenis toko. Hasil muncul langsung selagi pencarian berjalan.</p>
          </div>
          <NewSearch onCreated={(job) => go.job(job.id)} />
          <History onOpen={go.job} onOpenAll={go.all} />
        </div>
      )}

      {route.name === "job" && <JobPage id={route.id} />}

      {route.name === "all" && (
        <div className="space-y-4">
          <h1 className="text-lg font-bold">Semua toko tersimpan</h1>
          <ResultsView jobId={null} active={false} />
        </div>
      )}
    </div>
  );
}
