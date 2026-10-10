import type { JobStatus } from "../api/types";

/** "KOTA ADM. JAKARTA PUSAT" -> "Kota Jakarta Pusat" (selaras dengan teks query di backend) */
export function pretty(nama: string): string {
  return nama
    .replace(/\b(?:adm\.?|administrasi)(?=\s|$)/gi, "")
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

export const LEVEL_LABEL: Record<number, string> = {
  1: "Provinsi",
  2: "Kabupaten / Kota",
  3: "Kecamatan",
  4: "Desa / Kelurahan",
};

export const STATUS_LABEL: Record<JobStatus, string> = {
  queued: "Antre",
  running: "Berjalan",
  done: "Selesai",
  failed: "Gagal",
  blocked: "Diblokir",
  cancelled: "Dibatalkan",
};

export const PHASE_LABEL: Record<string, string> = {
  queued: "menunggu worker",
  starting: "menyiapkan",
  checking_cache: "mengecek cache",
  loading: "membuka Google Maps",
  scrolling: "menggulir daftar hasil",
  detail: "mengambil detail tiap toko",
  done: "selesai",
};

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });
}

export function relativeTime(iso: string): string {
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 45) return "baru saja";
  if (s < 3600) return `${Math.round(s / 60)} menit lalu`;
  if (s < 86400) return `${Math.round(s / 3600)} jam lalu`;
  if (s < 86400 * 7) return `${Math.round(s / 86400)} hari lalu`;
  return formatTime(iso);
}

export const BUSINESS_STATUS: Record<string, string> = {
  operational: "Beroperasi",
  closed_permanently: "Tutup permanen",
  closed_temporarily: "Tutup sementara",
};
