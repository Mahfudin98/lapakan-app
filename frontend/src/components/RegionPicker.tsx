import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import type { Region } from "../api/types";
import { useDebounced } from "../hooks/useDebounced";
import { LEVEL_LABEL, pretty } from "../lib/format";
import { Combobox } from "./Combobox";

type Chain = (Region | null)[];

function LevelSelect({
  level, parent, value, onChange,
}: {
  level: number;
  parent: Region | null;
  value: Region | null;
  onChange: (r: Region | null) => void;
}) {
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const q = useDebounced(search.trim());

  const { data = [], isFetching, isError } = useQuery({
    queryKey: ["regions", level, parent?.kode ?? null, q],
    queryFn: () => api.regions({ level, parent: parent?.kode, q: q || undefined, limit: 100 }),
    enabled: open,
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
  });

  return (
    <div className="pop-in">
      <Combobox
        label={LEVEL_LABEL[level]}
        placeholder={`Cari ${LEVEL_LABEL[level].toLowerCase()}…`}
        value={value ? { value: value.kode, label: pretty(value.nama) } : null}
        options={data.map((r) => ({ value: r.kode, label: pretty(r.nama) }))}
        loading={isFetching}
        onSearch={setSearch}
        onOpenChange={setOpen}
        onChange={(o) => onChange(o ? (data.find((r) => r.kode === o.value) ?? null) : null)}
      />
      {isError && <p className="mt-1 text-xs text-red-600">Gagal memuat wilayah. Cek koneksi API.</p>}
    </div>
  );
}

export function deepest(chain: Chain): Region | null {
  for (let i = chain.length - 1; i >= 0; i--) if (chain[i]) return chain[i];
  return null;
}

const HINT: Record<number, string> = {
  1: "Provinsi terlalu luas; pilih kabupaten/kota atau lebih sempit.",
  2: "Akan dipecah otomatis per kecamatan agar hasil tidak terpotong.",
  3: "Satu pencarian per jenis toko untuk kecamatan ini.",
  4: "Pencarian paling spesifik, untuk satu desa/kelurahan.",
};

/** Pilih wilayah bertahap: level berikutnya baru muncul setelah level sebelumnya dipilih. */
export function RegionPicker({ onChange }: { onChange: (r: Region | null) => void }) {
  const [chain, setChain] = useState<Chain>([null, null, null, null]);

  const set = (i: number, r: Region | null) => {
    const next: Chain = chain.map((c, idx) => (idx < i ? c : idx === i ? r : null));
    setChain(next);
    onChange(deepest(next));
  };

  const sel = deepest(chain);
  const visible = Math.min(4, (sel ? sel.level : 0) + 1);

  return (
    <div>
      <div className="grid gap-3 sm:grid-cols-2">
        {[1, 2, 3, 4].slice(0, visible).map((level) => (
          <LevelSelect
            key={level}
            level={level}
            parent={level > 1 ? chain[level - 2] : null}
            value={chain[level - 1]}
            onChange={(r) => set(level - 1, r)}
          />
        ))}
      </div>
      <p className="mt-2 text-xs text-slate-500">
        {sel ? HINT[sel.level] : "Mulai dari provinsi. Anda boleh berhenti di level mana pun."}
      </p>
    </div>
  );
}
