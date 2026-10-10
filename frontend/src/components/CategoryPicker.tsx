import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { Chip } from "./ui";

interface Props {
  categoryIds: number[];
  keywords: string[];
  onCategoryIds: (ids: number[]) => void;
  onKeywords: (kw: string[]) => void;
}

// kategori yang paling sering dicari tampil di depan; sisanya di balik "Lihat semua"
const POPULAR = [
  "toko kosmetik", "salon", "klinik kecantikan", "toko skincare", "apotek", "kafe", "minimarket", "bengkel",
];

export function CategoryPicker({ categoryIds, keywords, onCategoryIds, onKeywords }: Props) {
  const { data = [], isLoading, isError } = useQuery({ queryKey: ["categories"], queryFn: api.categories });
  const [text, setText] = useState("");
  const [all, setAll] = useState(false);

  const toggle = (id: number) =>
    onCategoryIds(categoryIds.includes(id) ? categoryIds.filter((x) => x !== id) : [...categoryIds, id]);

  const add = () => {
    const incoming = text.split(",").map((t) => t.trim()).filter(Boolean);
    if (!incoming.length) return;
    const existing = new Set(keywords.map((k) => k.toLowerCase()));
    onKeywords([...keywords, ...incoming.filter((k) => !existing.has(k.toLowerCase()))]);
    setText("");
  };

  const shown = all ? data : data.filter((c) => POPULAR.includes(c.keyword) || categoryIds.includes(c.id));
  const hidden = data.length - shown.length;

  return (
    <div className="space-y-3">
      {isLoading && <p className="text-sm text-slate-500">Memuat kategori…</p>}
      {isError && <p className="text-sm text-red-600">Gagal memuat kategori.</p>}
      <div className="flex flex-wrap gap-2" role="group" aria-label="Jenis toko">
        {shown.map((c) => (
          <Chip key={c.id} on={categoryIds.includes(c.id)} onClick={() => toggle(c.id)}>
            {c.nama}
          </Chip>
        ))}
        {data.length > 0 && (hidden > 0 || all) && (
          <button type="button" onClick={() => setAll((a) => !a)}
            className="rounded-full px-3 py-1.5 text-sm text-indigo-700 hover:bg-indigo-50">
            {all ? "Tampilkan lebih sedikit" : `Lihat semua (+${hidden})`}
          </button>
        )}
      </div>

      <div>
        <label htmlFor="kw" className="sr-only">Kata kunci lain</label>
        <div className="flex gap-2">
          <input
            id="kw"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === ",") {
                e.preventDefault();
                add();
              }
            }}
            placeholder="Jenis lain, mis. pet shop, toko perlengkapan bayi"
            className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <button type="button" onClick={add} disabled={!text.trim()}
            className="rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium hover:bg-slate-50 disabled:opacity-40">
            Tambah
          </button>
        </div>
        {keywords.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {keywords.map((k) => (
              <span key={k} className="pop-in inline-flex items-center gap-1 rounded-full bg-emerald-100 py-1 pl-3 pr-1.5 text-sm text-emerald-900">
                {k}
                <button type="button" aria-label={`Hapus kata kunci ${k}`}
                  onClick={() => onKeywords(keywords.filter((x) => x !== k))}
                  className="flex h-5 w-5 items-center justify-center rounded-full hover:bg-emerald-200">
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
