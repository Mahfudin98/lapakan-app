import type { Place } from "../api/types";
import { BUSINESS_STATUS, formatTime } from "../lib/format";
import { hostname, safeHttpUrl, telHref } from "../lib/url";

interface Props {
  place: Place;
  selected: boolean;
  onSelect: (id: number) => void;
  onHover: (id: number | null) => void;
  pinned?: boolean;
}

function Rating({ p }: { p: Place }) {
  if (p.rating != null) {
    return (
      <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
        ★ {p.rating.toFixed(1)}
        {p.review_count != null && p.review_count > 0 && (
          <span className="font-normal"> ({p.review_count.toLocaleString("id-ID")})</span>
        )}
      </span>
    );
  }
  if (p.review_count === 0) {
    return <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">Belum ada ulasan</span>;
  }
  return null;
}

function Action({ href, children, external = false }: { href: string; children: React.ReactNode; external?: boolean }) {
  return (
    <a href={href} onClick={(e) => e.stopPropagation()} {...(external ? { target: "_blank", rel: "noreferrer noopener" } : {})}
      className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-800">
      {children}
    </a>
  );
}

function Hours({ jam }: { jam: Place["jam_buka"] }) {
  if (!jam) return null;
  const ringkasan = typeof jam.ringkasan === "string" ? jam.ringkasan : null;
  const jadwal = jam.jadwal && typeof jam.jadwal === "object" ? Object.entries(jam.jadwal as Record<string, unknown>) : [];
  if (!ringkasan && jadwal.length === 0) return null;
  return (
    <div className="text-xs text-slate-600">
      <span className="font-medium text-slate-700">Jam buka: </span>
      {ringkasan}
      {jadwal.map(([hari, jam2]) => (
        <span key={hari} className="ml-2">{hari} {String(jam2)}</span>
      ))}
    </div>
  );
}

export function PlaceCard({ place: p, selected, onSelect, onHover, pinned = false }: Props) {
  const tel = telHref(p.telepon);
  const web = safeHttpUrl(p.website);
  const maps = safeHttpUrl(p.maps_url);

  return (
    <article
      data-testid="place-card"
      data-selected={selected}
      data-id={p.id}
      tabIndex={0}
      aria-current={selected}
      onClick={() => onSelect(p.id)}
      onKeyDown={(e) => {
        if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onSelect(p.id);
        }
      }}
      onMouseEnter={() => onHover(p.id)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(p.id)}
      onBlur={() => onHover(null)}
      className={`pop-in cursor-pointer rounded-xl border bg-white p-3.5 shadow-sm transition ${
        selected ? "border-red-400 ring-2 ring-red-200" : "border-slate-200 hover:border-indigo-300 hover:shadow"
      } ${pinned ? "bg-red-50" : ""}`}
    >
      <div className="flex items-start justify-between gap-2">
        <h3 className="min-w-0 break-words font-semibold leading-snug">{p.nama}</h3>
        <Rating p={p} />
      </div>
      <p className="mt-0.5 text-sm text-slate-600">
        {p.kategori_google ?? "Tanpa kategori"}
        {p.distance_km != null && <span className="font-medium text-sky-700"> · {p.distance_km.toFixed(1)} km</span>}
      </p>
      {p.alamat && <p className={`mt-1 break-words text-sm text-slate-500 ${selected ? "" : "line-clamp-2"}`}>{p.alamat}</p>}

      {(p.in_region === false || p.status_bisnis !== "operational") && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {p.in_region === false && <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[11px] text-slate-700">Di luar wilayah</span>}
          {p.status_bisnis === "closed_permanently" && <span className="rounded bg-red-100 px-1.5 py-0.5 text-[11px] text-red-800">Tutup permanen</span>}
          {p.status_bisnis === "closed_temporarily" && <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[11px] text-amber-800">Tutup sementara</span>}
        </div>
      )}

      {(tel || web || maps) && (
        <div className="mt-3 flex flex-wrap gap-2">
          {tel && <Action href={tel}>📞 {p.telepon}</Action>}
          {web && <Action href={web} external>🌐 {hostname(web)}</Action>}
          {maps && <Action href={maps} external>📍 Google Maps</Action>}
        </div>
      )}

      {selected && (
        <div className="mt-3 space-y-1 border-t border-slate-100 pt-3">
          <Hours jam={p.jam_buka} />
          {p.lat != null && p.lng != null && (
            <p className="text-xs text-slate-500">Koordinat: {p.lat.toFixed(5)}, {p.lng.toFixed(5)}</p>
          )}
          <p className="text-xs text-slate-400">
            Diambil {formatTime(p.last_scraped_at)}
            {p.status_bisnis ? ` · ${BUSINESS_STATUS[p.status_bisnis] ?? p.status_bisnis}` : ""}
          </p>
        </div>
      )}
    </article>
  );
}
