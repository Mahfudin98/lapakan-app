import { createColumnHelper, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import { useEffect, useMemo, useRef } from "react";
import type { Place, SortKey } from "../api/types";

interface Props {
  rows: Place[];
  sort: SortKey;
  onSort: (s: SortKey) => void;
  selectedId: number | null;
  onSelect: (id: number) => void;
  showDistance: boolean;
}

const col = createColumnHelper<Place>();
const NO_REVIEWS_HINT =
  "Jumlah ulasan tidak tersedia: Google Maps tanpa login tidak menampilkannya";

function Sortable({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1 font-semibold ${active ? "text-indigo-700" : "hover:text-indigo-700"}`}
    >
      {label}
      <span aria-hidden>{active ? "▼" : ""}</span>
    </button>
  );
}

export function PlacesTable({ rows, sort, onSort, selectedId, onSelect, showDistance }: Props) {
  const columns = useMemo(
    () => [
      col.display({
        id: "nama",
        header: () => <Sortable label="Nama" active={sort === "nama"} onClick={() => onSort("nama")} />,
        cell: ({ row }) => {
          const p = row.original;
          return (
            <div className="min-w-[10rem]">
              <div className="font-medium">
                {p.maps_url ? (
                  <a
                    href={p.maps_url}
                    target="_blank"
                    rel="noreferrer noopener"
                    onClick={(e) => e.stopPropagation()}
                    className="text-indigo-700 hover:underline"
                  >
                    {p.nama}
                  </a>
                ) : (
                  p.nama
                )}
              </div>
              <div className="mt-0.5 flex flex-wrap gap-1">
                {p.status_bisnis === "closed_permanently" && (
                  <span className="rounded bg-red-100 px-1.5 text-[11px] text-red-800">Tutup permanen</span>
                )}
                {p.status_bisnis === "closed_temporarily" && (
                  <span className="rounded bg-amber-100 px-1.5 text-[11px] text-amber-800">Tutup sementara</span>
                )}
                {p.in_region === false && (
                  <span className="rounded bg-slate-200 px-1.5 text-[11px] text-slate-700">Di luar wilayah</span>
                )}
              </div>
            </div>
          );
        },
      }),
      col.accessor("kategori_google", {
        header: "Kategori",
        cell: (c) => c.getValue() ?? "—",
      }),
      col.display({
        id: "rating",
        header: () => <Sortable label="Rating" active={sort === "rating"} onClick={() => onSort("rating")} />,
        cell: ({ row }) =>
          row.original.rating != null ? <span className="whitespace-nowrap">★ {row.original.rating.toFixed(1)}</span> : <span className="text-slate-400">—</span>,
      }),
      col.display({
        id: "ulasan",
        header: () => (
          <Sortable label="Ulasan" active={sort === "terpopuler"} onClick={() => onSort("terpopuler")} />
        ),
        cell: ({ row }) =>
          row.original.review_count != null ? (
            row.original.review_count.toLocaleString("id-ID")
          ) : (
            <span className="cursor-help text-slate-400" title={NO_REVIEWS_HINT}>
              n/a
            </span>
          ),
      }),
      col.display({
        id: "skor",
        header: () => <Sortable label="Skor" active={sort === "skor"} onClick={() => onSort("skor")} />,
        cell: ({ row }) =>
          row.original.score != null ? (
            row.original.score.toFixed(2)
          ) : (
            <span className="cursor-help text-slate-400" title={NO_REVIEWS_HINT}>
              —
            </span>
          ),
      }),
      ...(showDistance
        ? [
            col.display({
              id: "jarak",
              header: () => (
                <Sortable label="Jarak" active={sort === "terdekat"} onClick={() => onSort("terdekat")} />
              ),
              cell: ({ row }) =>
                row.original.distance_km != null ? (
                  <span className="whitespace-nowrap">{row.original.distance_km.toFixed(2)} km</span>
                ) : (
                  "—"
                ),
            }),
          ]
        : []),
      col.accessor("telepon", {
        header: "Telepon",
        cell: (c) => <span className="whitespace-nowrap">{c.getValue() ?? "—"}</span>,
      }),
      col.accessor("alamat", {
        header: "Alamat",
        cell: (c) => <span className="line-clamp-2 min-w-[12rem]">{c.getValue() ?? "—"}</span>,
      }),
    ],
    [sort, onSort, showDistance],
  );

  const body = useRef<HTMLTableSectionElement>(null);
  useEffect(() => {
    // pilihan dari marker peta: bawa barisnya ke dalam pandangan
    body.current?.querySelector('[data-selected="true"]')?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (r) => String(r.id),
    manualPagination: true,
    manualSorting: true,
  });

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="w-full text-left text-sm" data-testid="places-table">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => (
                <th key={h.id} scope="col" className="whitespace-nowrap px-3 py-2">
                  {flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody ref={body} className="divide-y divide-slate-100">
          {table.getRowModel().rows.map((row) => {
            const selected = row.original.id === selectedId;
            return (
              <tr
                key={row.id}
                data-testid="place-row"
                data-selected={selected}
                aria-selected={selected}
                onClick={() => onSelect(row.original.id)}
                className={`cursor-pointer align-top ${selected ? "bg-red-50 ring-1 ring-inset ring-red-300" : "hover:bg-slate-50"}`}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-3 py-2">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
