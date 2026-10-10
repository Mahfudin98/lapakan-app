import { useEffect, useRef, useState } from "react";
import type { JobStatus } from "../api/types";
import { STATUS_LABEL } from "../lib/format";

export function Segmented<T extends string>({
  value, options, onChange, label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-lg bg-slate-200/70 p-0.5 text-sm">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={`rounded-md px-3.5 py-1.5 font-medium transition ${
            value === o.value ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Chip({
  on, onClick, children, title,
}: {
  on: boolean;
  onClick: () => void;
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      title={title}
      onClick={onClick}
      className={`whitespace-nowrap rounded-full border px-3 py-1.5 text-sm transition ${
        on
          ? "border-indigo-600 bg-indigo-600 text-white shadow-sm"
          : "border-slate-300 bg-white text-slate-700 hover:border-indigo-400 hover:text-indigo-700"
      }`}
    >
      {children}
    </button>
  );
}

const PILL: Record<JobStatus, string> = {
  queued: "bg-slate-200 text-slate-700",
  running: "bg-blue-100 text-blue-800",
  done: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-800",
  blocked: "bg-amber-100 text-amber-900",
  cancelled: "bg-slate-200 text-slate-600",
};

export function StatusPill({ status }: { status: JobStatus }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${PILL[status]}`}>
      {(status === "running" || status === "queued") && <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-current" />}
      {STATUS_LABEL[status]}
    </span>
  );
}

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={`spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" opacity="0.25" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function ProgressBar({ pct, status }: { pct: number; status: JobStatus }) {
  const color =
    status === "done" ? "bg-emerald-500"
    : status === "failed" ? "bg-red-500"
    : status === "blocked" ? "bg-amber-500"
    : status === "cancelled" ? "bg-slate-400"
    : "bg-indigo-500";
  const animated = status === "running" || status === "queued";
  return (
    <div role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}
      className="h-2.5 overflow-hidden rounded-full bg-slate-200">
      <div className={`h-full rounded-full transition-all duration-500 ${color} ${animated ? "stripes" : ""}`}
        style={{ width: `${Math.max(status === "queued" ? 4 : 0, Math.min(100, pct))}%` }} />
    </div>
  );
}

/** Menu tarik-turun: menutup saat klik di luar, tombol Esc, atau setelah memilih item. */
export function DropdownMenu({
  label, children, align = "right",
}: {
  label: React.ReactNode;
  children: (close: () => void) => React.ReactNode;
  align?: "left" | "right";
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={root} className="relative">
      <button type="button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}
        className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50">
        {label}
      </button>
      {open && (
        <div role="menu" className={`absolute z-50 mt-1 w-44 overflow-hidden rounded-lg border border-slate-200 bg-white py-1 text-sm shadow-lg ${align === "right" ? "right-0" : "left-0"}`}>
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}
