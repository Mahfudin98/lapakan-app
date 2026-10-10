"""Validasi apakah sebuah toko berada di wilayah terpilih, berdasarkan teks alamat.

Tidak ada poligon wilayah di dataset, jadi koordinat tidak bisa dipakai untuk memastikan batas
administratif. Yang dipakai: pola eksplisit di alamat ("Kec. X", "Kota/Kabupaten Y", "Kel./Desa Z").

Hasil:
  True    alamat menyebut wilayah pada level terdalam target dan tidak ada yang bertentangan
  False   alamat menyebut kecamatan/kab/kota/desa LAIN daripada target
  None    tidak cukup informasi (alamat pendek tanpa nama wilayah): "unknown"
"""
import re
from dataclasses import dataclass, field

_ABBREV = re.compile(r"\b(kec|kab|kel|kota|desa)\.\s*")
_ADM = re.compile(r"\b(adm\.?|administrasi)\b")
_PREFIXES = {
    "kec": "kec", "kecamatan": "kec",
    "kota": "kota", "kabupaten": "kabupaten", "kab": "kabupaten",
    "kel": "desa", "kelurahan": "desa", "desa": "desa",
}
_SEG_PREFIX = re.compile(r"^(kecamatan|kec|kota|kabupaten|kab|kelurahan|kel|desa)\s+(.+)$")


def norm(text: str) -> str:
    t = text.lower()
    t = _ADM.sub(" ", t)
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return " ".join(t.split())


def split_kab(nama: str) -> tuple[str | None, str]:
    """'KOTA BANDUNG' -> ('kota', 'bandung'); 'KABUPATEN BANDUNG BARAT' -> ('kabupaten', 'bandung barat')."""
    n = norm(nama)
    for prefix in ("kota", "kabupaten", "kab"):
        if n.startswith(prefix + " "):
            return ("kota" if prefix == "kota" else "kabupaten"), n[len(prefix) + 1 :]
    return None, n


@dataclass
class RegionMatcher:
    """target = wilayah terpilih user. `names` = nama mentah per level (1..4) dari atas ke bawah."""

    level: int
    names: list[str]
    districts: dict[str, str] = field(default_factory=dict)  # nama kecamatan ternormalisasi -> kode

    def _name(self, level: int) -> str | None:
        return self.names[level - 1] if len(self.names) >= level else None

    def evaluate(self, alamat: str | None) -> tuple[bool | None, str | None]:
        """Return (in_region, kode_kecamatan_terdeteksi|None)."""
        if not alamat or not alamat.strip():
            return None, None

        text = _ABBREV.sub(lambda m: m.group(1) + " ", alamat.lower())
        explicit: dict[str, tuple[str | None, str]] = {}
        for seg in (s.strip() for s in text.split(",")):
            seg = re.sub(r"\b\d{5}\b", "", seg)  # kode pos
            m = _SEG_PREFIX.match(norm(seg))
            if m:
                kind = _PREFIXES[m.group(1)]
                explicit.setdefault("kab" if kind in ("kota", "kabupaten") else kind, (kind, m.group(2)))

        kec_kode = None
        if "kec" in explicit:
            kec_kode = self.districts.get(explicit["kec"][1])

        conflict = False
        matched_deepest = False

        kab_raw = self._name(2)
        if "kab" in explicit and kab_raw:
            t_type, t_base = split_kab(kab_raw)
            e_type, e_base = explicit["kab"]
            same = e_base == t_base and (t_type is None or t_type == e_type)
            if same:
                matched_deepest |= self.level == 2
            else:
                conflict = True

        kec_raw = self._name(3)
        if "kec" in explicit and kec_raw and self.level >= 3:
            if explicit["kec"][1] == norm(kec_raw):
                matched_deepest |= self.level == 3
            else:
                conflict = True

        desa_raw = self._name(4)
        if "desa" in explicit and desa_raw and self.level == 4:
            if explicit["desa"][1] == norm(desa_raw):
                matched_deepest = True
            else:
                conflict = True

        if conflict:
            return False, kec_kode
        if matched_deepest:
            return True, kec_kode

        # fallback: nama wilayah terdalam muncul sebagai kata utuh di alamat
        deepest = self._name(self.level)
        if deepest:
            base = split_kab(deepest)[1] if self.level == 2 else norm(deepest)
            if base and re.search(rf"\b{re.escape(base)}\b", norm(text)):
                return True, kec_kode
        return None, kec_kode
