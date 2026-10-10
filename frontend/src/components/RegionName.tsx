import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { pretty } from "../lib/format";

/** Nama wilayah lengkap dari kode: "Andir, Kota Bandung, Jawa Barat". */
export function RegionName({ kode, short = false }: { kode: string; short?: boolean }) {
  const { data } = useQuery({
    queryKey: ["region", kode],
    queryFn: () => api.region(kode),
    staleTime: Infinity,
  });
  if (!data) return <>{kode}</>;
  const names = data.path.map((r) => pretty(r.nama)).reverse();
  return <>{(short ? names.slice(0, 2) : names).join(", ")}</>;
}
