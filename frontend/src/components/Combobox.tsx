import { useEffect, useRef, useState } from "react";

export interface Option {
  value: string;
  label: string;
}

interface Props {
  label: string;
  placeholder?: string;
  disabled?: boolean;
  disabledHint?: string;
  value: Option | null;
  options: Option[];
  loading?: boolean;
  onSearch: (text: string) => void;
  onOpenChange?: (open: boolean) => void;
  onChange: (opt: Option | null) => void;
}

/** Dropdown yang bisa dicari (pencarian dilakukan induk lewat onSearch). Mendukung keyboard. */
export function Combobox({
  label, placeholder, disabled, disabledHint, value, options, loading, onSearch, onOpenChange, onChange,
}: Props) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null);

  const setOpenState = (o: boolean) => {
    setOpen(o);
    onOpenChange?.(o);
    if (!o) {
      setText("");
      onSearch("");
    }
  };

  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpenState(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const optionKey = options.map((o) => o.value).join("|");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => setActive(0), [optionKey]);

  const pick = (o: Option | null) => {
    onChange(o);
    setOpenState(false);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(a + 1, options.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter" && open && options[active]) {
      e.preventDefault();
      pick(options[active]);
    } else if (e.key === "Escape") {
      setOpenState(false);
    }
  };

  const shown = open ? text : (value?.label ?? "");

  return (
    <div
      ref={root}
      className="relative"
      onBlur={(e) => {
        // Tab ke luar komponen: tutup daftar
        if (open && !e.currentTarget.contains(e.relatedTarget as Node | null)) setOpenState(false);
      }}
    >
      <label className="mb-1 block text-xs font-medium text-slate-600">{label}</label>
      <div className="relative">
        <input
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-label={label}
          disabled={disabled}
          value={shown}
          placeholder={disabled ? disabledHint : placeholder}
          onFocus={() => !disabled && setOpenState(true)}
          onChange={(e) => {
            setText(e.target.value);
            onSearch(e.target.value);
            if (!open) setOpenState(true);
          }}
          onKeyDown={onKey}
          className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 pr-8 text-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-100"
        />
        {value && !disabled && (
          <button
            type="button"
            aria-label={`Hapus ${label}`}
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => pick(null)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700"
          >
            ×
          </button>
        )}
      </div>
      {open && (
        <ul
          role="listbox"
          tabIndex={-1}
          className="absolute z-20 mt-1 max-h-60 w-full overflow-auto rounded-md border border-slate-200 bg-white py-1 text-sm shadow-lg"
        >
          {loading && options.length === 0 && <li className="px-3 py-2 text-slate-500">Memuat…</li>}
          {!loading && options.length === 0 && <li className="px-3 py-2 text-slate-500">Tidak ada hasil</li>}
          {options.map((o, i) => (
            <li
              key={o.value}
              role="option"
              aria-selected={value?.value === o.value}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => pick(o)}
              onMouseEnter={() => setActive(i)}
              className={`cursor-pointer px-3 py-1.5 ${i === active ? "bg-indigo-50" : ""} ${
                value?.value === o.value ? "font-semibold text-indigo-700" : ""
              }`}
            >
              {o.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
