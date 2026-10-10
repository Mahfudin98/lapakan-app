def bayesian_score(v: int | None, rating: float | None, c: float, m: float) -> float | None:
    """Rata-rata Bayesian: (v/(v+m))*R + (m/(v+m))*C.

    v = jumlah ulasan, R = rating toko, C = rata-rata rating seluruh hasil, m = bobot prior.
    Toko dengan sedikit ulasan "ditarik" ke C, sehingga 5.0 dari 2 ulasan tidak mengalahkan
    4.8 dari 900 ulasan. None bila v atau rating tidak diketahui (Google tampilan terbatas
    tidak selalu menampilkan jumlah ulasan).
    """
    if v is None or rating is None:
        return None
    if m < 0 or v < 0:
        raise ValueError("v dan m tidak boleh negatif")
    if v + m == 0:
        return c
    return (v / (v + m)) * rating + (m / (v + m)) * c
