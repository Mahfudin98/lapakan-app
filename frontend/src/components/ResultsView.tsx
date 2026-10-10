import { keepPreviousData, useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { Place, SortKey } from "../api/types";
import { useDebounced } from "../hooks/useDebounced";
import { DEFAULT_FILTERS, type Filters, type RefPoint, filterParams, sortedParams } from "../lib/filters";
import { PlaceCard } from "./PlaceCard";
import { PlacesMap } from "./PlacesMap";
import { PlacesTable } from "./PlacesTable";
import { Chip, DropdownMenu, Segmented, Spinner } from "./ui";

type View = "daftar" | "peta" | "tabel";
const PAGE = 40;
const SORTS: { value: SortKey; label: string }[] = [
  { value: "skor", label: "Skor terbaik" },
  { value: "terdekat", label: "Terdekat dari saya" },
  { value: "rating", label: "Rating tertinggi" },
  { value: "terpopuler", label: "Ulasan terbanyak" },
  { value: "nama", label: "Nama A–Z" },
  { value: "terbaru", label: "Terbaru diambil" },
];

interface Props {
  jobId: string | null; // null = semua toko tersimpan
  active: boolean; // job masih berjalan: segarkan hasil secara berkala
}

export function ResultsView({ jobId, active }: Props) {
  const [q, setQ] = useState("");
  // default: tampilkan SEMUA hasil scraping (yang di luar wilayah hanya diberi lencana)
  const [insideOnly, setInsideOnly] = useState(false);
  const [hasPhone, setHasPhone] = useState(false);
  const [hasWebsite, setHasWebsite] = useState(false);
  const [topRated, setTopRated] = useState(false);
  const [kategori, setKategori] = useState("");
  const [sort, setSort] = useState<SortKey>("skor");
  const [refPoint, setRefPoint] = useState<RefPoint | null>(null);
  const [geoMsg, setGeoMsg] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const [view, setView] = useState<View>("daftar");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [hoveredId, setHoveredId] = useState<number | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();

  // Job baru selesai: segarkan sekali lagi. Polling berhenti saat job tidak aktif, dan pengambilan
  // terakhir bisa saja terjadi sebelum hasil terakhir tertaut ke job (job cepat / dari cache).
  const wasActive = useRef(active);
  useEffect(() => {
    if (wasActive.current && !active) {
      for (const key of ["places", "placesMap", "facets"]) qc.invalidateQueries({ queryKey: [key] });
    }
    wasActive.current = active;
  }, [active, qc]);

  const filters = useMemo<Filters>(
    () => ({
      ...DEFAULT_FILTERS,
      q,
      jobId: jobId ?? "",
      kategori: kategori ? [kategori] : [],
      hasPhone,
      hasWebsite,
      minRating: topRated ? "4" : "",
      regionFilter: insideOnly ? "hide_outside" : "all",
    }),
    [q, jobId, kategori, hasPhone, hasWebsite, topRated, insideOnly],
  );
  const dFilters = useDebounced(filters, 300);
  const needsRef = sort === "terdekat" && !refPoint;
  const refetchInterval = active ? 3000 : false;

  const baseParams = useMemo(() => sortedParams(dFilters, sort, refPoint, "20"), [dFilters, sort, refPoint]);
  const list = useInfiniteQuery({
    queryKey: ["places", baseParams.toString()],
    queryFn: ({ pageParam }) => {
      const p = new URLSearchParams(baseParams);
      p.set("page", String(pageParam));
      p.set("page_size", String(PAGE));
      return api.places(p);
    },
    initialPageParam: 1,
    getNextPageParam: (last) => (last.page < last.pages ? last.page + 1 : undefined),
    enabled: !needsRef,
    placeholderData: keepPreviousData,
    refetchInterval,
  });
  const mapParams = useMemo(() => filterParams(dFilters), [dFilters]);
  const mapQ = useQuery({
    queryKey: ["placesMap", mapParams.toString()],
    queryFn: () => api.placesMap(mapParams),
    placeholderData: keepPreviousData,
    refetchInterval,
  });
  const facetParams = useMemo(() => filterParams(dFilters, { skipKategori: true }), [dFilters]);
  const facets = useQuery({
    queryKey: ["facets", facetParams.toString()],
    queryFn: () => api.facets(facetParams),
    placeholderData: keepPreviousData,
    refetchInterval,
  });

  const items = useMemo(() => list.data?.pages.flatMap((p) => p.items) ?? [], [list.data]);
  const first = list.data?.pages[0];
  const total = first?.total ?? 0;
  const outside = first?.meta.outside_count ?? 0;
  const points = useMemo(() => mapQ.data?.points ?? [], [mapQ.data]);

  const inList = items.find((p) => p.id === selectedId);
  const extra = useQuery({
    queryKey: ["place", selectedId],
    queryFn: () => api.place(selectedId!),
    enabled: selectedId != null && !inList,
  });
  const pinned: Place | undefined = inList ? undefined : extra.data;

  // marker diklik -> bawa kartunya ke pandangan
  useEffect(() => {
    if (selectedId == null) return;
    listRef.current?.querySelector('[data-selected="true"]')?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedId, items.length]);

  // peta tersembunyi di tampilan Tabel, dan di ponsel juga di tampilan Daftar
  const showMapForPicking = () =>
    setView((v) => (v === "peta" ? v : v === "daftar" && window.matchMedia("(min-width: 1024px)").matches ? v : "peta"));

  const chooseSort = (s: SortKey) => {
    setSort(s);
    setGeoMsg(null);
    if (s === "terdekat" && !refPoint) locate();
  };

  const locate = () => {
    if (!navigator.geolocation) {
      setGeoMsg("Browser tidak mendukung geolokasi. Klik peta untuk menentukan titik acuan.");
      setPicking(true);
      showMapForPicking();
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setRefPoint({ lat: pos.coords.latitude, lng: pos.coords.longitude, source: "geolocation" });
        setGeoMsg(null);
      },
      () => {
        setGeoMsg("Lokasi tidak tersedia. Klik di peta untuk menentukan titik acuan.");
        setPicking(true);
        showMapForPicking();
      },
      { timeout: 10_000 },
    );
  };

  const onPick = useCallback((lat: number, lng: number) => {
    setRefPoint({ lat, lng, source: "map" });
    setPicking(false);
    setGeoMsg(null);
  }, []);

  const exportParams = baseParams;
  const select = useCallback((id: number) => setSelectedId((cur) => (cur === id ? null : id)), []);
  const filtersActive = q || hasPhone || hasWebsite || topRated || kategori || insideOnly;

  const showList = view === "daftar";
  const showMap = view !== "tabel";
  const mapClass = view === "daftar" ? "hidden lg:block" : "block";

  return (
    <div className="space-y-4">
      {/* ---- toolbar ---- */}
      <div className="relative z-30 -mx-4 space-y-3 border-b border-slate-200 bg-slate-50/95 px-4 py-3 backdrop-blur lg:sticky lg:top-0">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-[12rem] flex-1">
            <svg className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd" />
            </svg>
            <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari nama toko…" aria-label="Cari nama toko"
              className="w-full rounded-lg border border-slate-300 bg-white py-2.5 pl-9 pr-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500" />
          </div>
          <select value={sort} onChange={(e) => chooseSort(e.target.value as SortKey)} aria-label="Urutkan"
            className="rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm">
            {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
          <Segmented<View> label="Tampilan" value={view} onChange={setView}
            options={[{ value: "daftar", label: "Daftar" }, { value: "peta", label: "Peta" }, { value: "tabel", label: "Tabel" }]} />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {(outside > 0 || insideOnly) && (
            <Chip on={insideOnly} onClick={() => setInsideOnly((v) => !v)} title="Sembunyikan toko yang alamatnya jelas berada di wilayah lain">
              Sembunyikan di luar wilayah{outside > 0 ? ` (${outside})` : ""}
            </Chip>
          )}
          <Chip on={topRated} onClick={() => setTopRated((v) => !v)}>★ 4+</Chip>
          <Chip on={hasPhone} onClick={() => setHasPhone((v) => !v)}>Ada telepon</Chip>
          <Chip on={hasWebsite} onClick={() => setHasWebsite((v) => !v)}>Ada website</Chip>
          {(facets.data?.length ?? 0) > 1 && (
            <select value={kategori} onChange={(e) => setKategori(e.target.value)} aria-label="Kategori"
              className="max-w-[14rem] rounded-full border border-slate-300 bg-white px-3 py-1.5 text-sm">
              <option value="">Semua kategori</option>
              {facets.data!.map((f) => <option key={f.kategori} value={f.kategori}>{f.kategori} ({f.count})</option>)}
            </select>
          )}
          {filtersActive && (
            <button type="button" className="text-sm text-indigo-700 hover:underline"
              onClick={() => { setQ(""); setHasPhone(false); setHasWebsite(false); setTopRated(false); setKategori(""); setInsideOnly(false); }}>
              Reset
            </button>
          )}
          <div className="ml-auto">
            <DropdownMenu label="⬇ Unduh">
              {(close) =>
                (["csv", "xlsx"] as const).map((fmt) => (
                  <a key={fmt} role="menuitem" data-testid={`export-${fmt}`} download onClick={close}
                    href={needsRef ? undefined : api.exportUrl(exportParams, fmt)} aria-disabled={needsRef}
                    className={`block px-3 py-2 hover:bg-slate-50 ${needsRef ? "pointer-events-none opacity-50" : ""}`}>
                    {fmt === "csv" ? "CSV" : "Excel (.xlsx)"}
                  </a>
                ))
              }
            </DropdownMenu>
          </div>
        </div>

        {(refPoint || geoMsg || picking) && (
          <p className="flex flex-wrap items-center gap-2 text-sm" role="status" data-testid="ref-info">
            {picking && <span className="rounded-md bg-sky-100 px-2 py-1 text-sky-900">Klik di peta untuk menentukan titik acuan.</span>}
            {geoMsg && <span className="text-amber-800">{geoMsg}</span>}
            {refPoint && (
              <span className="text-slate-600" data-testid="ref-point">
                Jarak dihitung dari {refPoint.source === "geolocation" ? "lokasi Anda" : "titik di peta"} ({refPoint.lat.toFixed(4)}, {refPoint.lng.toFixed(4)})
                {" · "}
                <button type="button" className="text-indigo-700 hover:underline" onClick={() => { setRefPoint(null); if (sort === "terdekat") setSort("skor"); }}>hapus</button>
              </span>
            )}
          </p>
        )}
      </div>

      {/* ---- ringkasan ---- */}
      <p className="text-sm text-slate-600" aria-live="polite" data-testid="total">
        {needsRef ? "Menentukan titik acuan…" : (
          <>
            <strong className="text-slate-900">{total.toLocaleString("id-ID")}</strong> toko
            {insideOnly && outside > 0 && (
              <> · {outside} di luar wilayah disembunyikan{" "}
                <button type="button" className="text-indigo-700 hover:underline" onClick={() => setInsideOnly(false)}>tampilkan</button>
              </>
            )}
          </>
        )}
      </p>

      {list.isError && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{list.error.message}</p>}

      {/* ---- isi ---- */}
      <div className={view === "daftar" ? "grid gap-4 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)]" : "grid gap-4"}>
        <div ref={listRef} className={showList ? "space-y-3 lg:max-h-[calc(100vh-11rem)] lg:overflow-y-auto lg:pr-1" : "hidden"}>
          {pinned && <PlaceCard place={pinned} selected pinned onSelect={select} onHover={setHoveredId} />}
          {items.map((p) => (
            <PlaceCard key={p.id} place={p} selected={p.id === selectedId} onSelect={select} onHover={setHoveredId} />
          ))}

          {list.isLoading && !needsRef && (
            <div className="space-y-3" aria-label="Memuat">
              {[0, 1, 2].map((i) => <div key={i} className="h-28 animate-pulse rounded-xl bg-slate-200/70" />)}
            </div>
          )}
          {!list.isLoading && !needsRef && items.length === 0 && (
            <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500" data-testid="empty">
              {active ? (
                <p className="flex items-center justify-center gap-2"><Spinner /> Sedang mencari… hasil pertama akan muncul di sini.</p>
              ) : filtersActive || (insideOnly && outside > 0) ? (
                <p>Tidak ada toko yang cocok dengan filter.
                  {insideOnly && outside > 0 && <> <button type="button" className="text-indigo-700 hover:underline" onClick={() => setInsideOnly(false)}>Tampilkan {outside} yang di luar wilayah</button></>}
                </p>
              ) : <p>Tidak ada toko yang ditemukan.</p>}
            </div>
          )}
          {list.hasNextPage && (
            <button type="button" onClick={() => list.fetchNextPage()} disabled={list.isFetchingNextPage}
              className="w-full rounded-xl border border-slate-300 bg-white py-3 text-sm font-medium hover:bg-slate-50 disabled:opacity-60">
              {list.isFetchingNextPage ? "Memuat…" : `Tampilkan lebih banyak (${total - items.length} lagi)`}
            </button>
          )}
        </div>

        <div className={showMap ? mapClass : "hidden"}>
          <div className="relative">
            <PlacesMap points={points} selectedId={selectedId} hoveredId={hoveredId} onSelect={select}
              refPoint={refPoint} picking={picking} onPick={onPick} />
            {!mapQ.isLoading && points.length === 0 && (
              <p className="pointer-events-none absolute inset-x-6 top-1/2 z-10 -translate-y-1/2 rounded-lg bg-white/90 p-3 text-center text-sm text-slate-600 shadow">
                {active ? "Menunggu toko pertama…" : "Tidak ada toko dengan koordinat untuk ditampilkan di peta."}
              </p>
            )}
          </div>
          {mapQ.data?.truncated && <p className="mt-1 text-xs text-amber-700">Peta dibatasi 5.000 titik; persempit dengan filter.</p>}
          {view === "peta" && (pinned ?? inList) && (
            <div className="mt-3">
              <PlaceCard place={(pinned ?? inList)!} selected onSelect={select} onHover={setHoveredId} />
            </div>
          )}
        </div>

        {view === "tabel" && items.length > 0 && (
          <div className="space-y-3">
            <PlacesTable rows={items} sort={sort} onSort={chooseSort} selectedId={selectedId}
              onSelect={select} showDistance={!!refPoint} />
            {list.hasNextPage && (
              <button type="button" onClick={() => list.fetchNextPage()} disabled={list.isFetchingNextPage}
                className="w-full rounded-xl border border-slate-300 bg-white py-3 text-sm font-medium hover:bg-slate-50 disabled:opacity-60">
                {list.isFetchingNextPage ? "Memuat…" : `Tampilkan lebih banyak (${total - items.length} lagi)`}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
