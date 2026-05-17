from flask import Blueprint, jsonify, request
from sqlalchemy import func, extract
from datetime import datetime
from models import db, RapatHarmonisasi

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _get_query(tanggal_dari="", tanggal_sampai=""):
    """Return base query, optionally filtered by date range."""
    query = RapatHarmonisasi.query
    if tanggal_dari:
        try:
            query = query.filter(
                RapatHarmonisasi.tanggal_rapat
                >= datetime.strptime(tanggal_dari, "%Y-%m-%d").date()
            )
        except ValueError:
            pass
    if tanggal_sampai:
        try:
            query = query.filter(
                RapatHarmonisasi.tanggal_rapat
                <= datetime.strptime(tanggal_sampai, "%Y-%m-%d").date()
            )
        except ValueError:
            pass
    return query


def _apply_filters(query, filters):
    """Apply drill-down filter parameters to query."""
    if filters.get("daerah"):
        query = query.filter(RapatHarmonisasi.daerah == filters["daerah"])
    if filters.get("jenis"):
        query = query.filter(RapatHarmonisasi.jenis == filters["jenis"])
    if filters.get("program_pembentukan"):
        query = query.filter(
            RapatHarmonisasi.program_pembentukan == filters["program_pembentukan"]
        )
    if filters.get("urusan_pemerintahan"):
        query = query.filter(
            RapatHarmonisasi.urusan_pemerintahan == filters["urusan_pemerintahan"]
        )
    if filters.get("tim_kerja"):
        query = query.filter(RapatHarmonisasi.tim_kerja == filters["tim_kerja"])
    if filters.get("hasil"):
        query = query.filter(RapatHarmonisasi.hasil == filters["hasil"])
    if filters.get("metode"):
        query = query.filter(RapatHarmonisasi.metode == filters["metode"])
    return query


def _record_to_dict(r):
    return {
        "id": r.id,
        "tanggal_rapat": r.tanggal_rapat.isoformat(),
        "daerah": r.daerah,
        "jenis": r.jenis,
        "program_pembentukan": r.program_pembentukan,
        "urusan_pemerintahan": r.urusan_pemerintahan,
        "nama_raperda": r.nama_raperda,
        "tim_kerja": r.tim_kerja,
        "hasil": r.hasil,
        "metode": r.metode,
        "keterangan": r.keterangan,
    }


def _parse_date_args():
    """Ambil tanggal_dari dan tanggal_sampai dari request args."""
    return request.args.get("tanggal_dari", ""), request.args.get("tanggal_sampai", "")


KATEGORI_KOLOM = {
    "daerah": RapatHarmonisasi.daerah,
    "jenis": RapatHarmonisasi.jenis,
    "program_pembentukan": RapatHarmonisasi.program_pembentukan,
    "urusan_pemerintahan": RapatHarmonisasi.urusan_pemerintahan,
    "tim_kerja": RapatHarmonisasi.tim_kerja,
    "hasil": RapatHarmonisasi.hasil,
    "metode": RapatHarmonisasi.metode,
}


@api_bp.route("/drill")
def drill():
    """Drill-down endpoint.

    Parameter:
        tanggal_dari, tanggal_sampai: filter rentang tanggal (YYYY-MM-DD)
        daerah, jenis, program_pembentukan, urusan_pemerintahan, tim_kerja, hasil, metode: filter nilai
    """
    tanggal_dari, tanggal_sampai = _parse_date_args()
    filters = {
        "daerah": request.args.get("daerah", ""),
        "jenis": request.args.get("jenis", ""),
        "program_pembentukan": request.args.get("program_pembentukan", ""),
        "urusan_pemerintahan": request.args.get("urusan_pemerintahan", ""),
        "tim_kerja": request.args.get("tim_kerja", ""),
        "hasil": request.args.get("hasil", ""),
        "metode": request.args.get("metode", ""),
    }
    filters = {k: v for k, v in filters.items() if v}

    q = _get_query(tanggal_dari, tanggal_sampai)
    q = _apply_filters(q, filters)
    total = q.count()

    unused = [k for k in KATEGORI_KOLOM if k not in filters]

    path = []
    for k, v in filters.items():
        path.append({"kategori": k, "nilai": v})

    # Jika sisa <= 4 kategori belum dipakai → tampilkan records
    if len(unused) <= 4:
        records = q.order_by(
            RapatHarmonisasi.tanggal_rapat.desc(), RapatHarmonisasi.id.desc()
        ).all()
        return jsonify(
            {
                "type": "records",
                "total": total,
                "path": path,
                "records": [_record_to_dict(r) for r in records],
            }
        )

    # Tampilkan breakdown per kategori berikutnya
    next_kategori = unused[0]
    col = KATEGORI_KOLOM[next_kategori]
    breakdown = (
        q.with_entities(col, func.count())
        .group_by(col)
        .order_by(func.count().desc())
        .all()
    )

    # Jika hanya 1 item, auto-select dan lanjut ke level berikutnya
    if len(breakdown) == 1:
        filters[next_kategori] = breakdown[0][0]
        q2 = _get_query(tanggal_dari, tanggal_sampai)
        q2 = _apply_filters(q2, filters)
        total2 = q2.count()
        path2 = [{"kategori": k, "nilai": v} for k, v in filters.items()]
        unused2 = [k for k in KATEGORI_KOLOM if k not in filters]

        if len(unused2) <= 4:
            records = q2.order_by(
                RapatHarmonisasi.tanggal_rapat.desc(), RapatHarmonisasi.id.desc()
            ).all()
            return jsonify(
                {
                    "type": "records",
                    "total": total2,
                    "path": path2,
                    "records": [_record_to_dict(r) for r in records],
                }
            )
        else:
            next2 = unused2[0]
            col2 = KATEGORI_KOLOM[next2]
            breakdown2 = (
                q2.with_entities(col2, func.count())
                .group_by(col2)
                .order_by(func.count().desc())
                .all()
            )
            return jsonify(
                {
                    "type": "breakdown",
                    "kategori": next2,
                    "total": total2,
                    "path": path2,
                    "items": [{"nilai": r[0], "jumlah": r[1]} for r in breakdown2],
                }
            )

    return jsonify(
        {
            "type": "breakdown",
            "kategori": next_kategori,
            "total": total,
            "path": path,
            "items": [{"nilai": r[0], "jumlah": r[1]} for r in breakdown],
        }
    )


@api_bp.route("/rapat-harmonisasi")
def list_data():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    tanggal_dari, tanggal_sampai = _parse_date_args()

    filters = {
        "daerah": request.args.get("daerah", ""),
        "jenis": request.args.get("jenis", ""),
        "hasil": request.args.get("hasil", ""),
        "metode": request.args.get("metode", ""),
        "tim_kerja": request.args.get("tim_kerja", ""),
    }
    filters = {k: v for k, v in filters.items() if v}

    query = _get_query(tanggal_dari, tanggal_sampai)
    query = _apply_filters(query, filters)

    pagination = query.order_by(
        RapatHarmonisasi.tanggal_rapat.desc(), RapatHarmonisasi.id.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify(
        {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
            "items": [_record_to_dict(r) for r in pagination.items],
        }
    )


@api_bp.route("/rekapitulasi")
def rekapitulasi():
    tanggal_dari, tanggal_sampai = _parse_date_args()
    q = _get_query(tanggal_dari, tanggal_sampai)

    def _group_by(col):
        return dict(q.with_entities(col, func.count()).group_by(col).all())

    return jsonify(
        {
            "tanggal_dari": tanggal_dari or None,
            "tanggal_sampai": tanggal_sampai or None,
            "total": q.count(),
            "per_daerah": _group_by(RapatHarmonisasi.daerah),
            "per_jenis": _group_by(RapatHarmonisasi.jenis),
            "per_program": _group_by(RapatHarmonisasi.program_pembentukan),
            "per_urusan": _group_by(RapatHarmonisasi.urusan_pemerintahan),
            "per_tim_kerja": _group_by(RapatHarmonisasi.tim_kerja),
            "per_hasil": _group_by(RapatHarmonisasi.hasil),
            "per_metode": _group_by(RapatHarmonisasi.metode),
        }
    )


@api_bp.route("/chart/<kategori>")
def chart_kategori(kategori):
    tanggal_dari, tanggal_sampai = _parse_date_args()
    q = _get_query(tanggal_dari, tanggal_sampai)

    kolom_map = {
        "per-daerah": RapatHarmonisasi.daerah,
        "per-jenis": RapatHarmonisasi.jenis,
        "per-program": RapatHarmonisasi.program_pembentukan,
        "per-urusan": RapatHarmonisasi.urusan_pemerintahan,
        "per-tim-kerja": RapatHarmonisasi.tim_kerja,
        "per-hasil": RapatHarmonisasi.hasil,
        "per-metode": RapatHarmonisasi.metode,
    }

    if kategori not in kolom_map:
        return jsonify({"error": "Kategori tidak valid"}), 400

    col = kolom_map[kategori]
    results = (
        q.with_entities(col, func.count())
        .group_by(col)
        .order_by(func.count().desc())
        .all()
    )

    return jsonify(
        {
            "kategori": kategori,
            "labels": [r[0] for r in results],
            "data": [r[1] for r in results],
        }
    )


@api_bp.route("/chart/bulanan")
def chart_bulanan():
    results = (
        RapatHarmonisasi.query.with_entities(
            extract("year", RapatHarmonisasi.tanggal_rapat).label("tahun"),
            extract("month", RapatHarmonisasi.tanggal_rapat).label("bulan"),
            func.count().label("jumlah"),
        )
        .group_by("tahun", "bulan")
        .order_by("tahun", "bulan")
        .all()
    )

    return jsonify(
        {
            "chart": "bulanan",
            "labels": [f"{int(r.tahun)}-{int(r.bulan):02d}" for r in results],
            "data": [r.jumlah for r in results],
        }
    )


# ============================================================
# Endpoint khusus untuk Agent Hermes
# ============================================================


@api_bp.route("/")
def index():
    """Daftar endpoint API yang tersedia."""
    return jsonify(
        {
            "layanan": "Rapat Harmonisasi - Bidang Legal Drafter",
            "endpoints": {
                "metadata": "/api/metadata",
                "rapat-harmonisasi": "/api/rapat-harmonisasi",
                "rekapitulasi": "/api/rekapitulasi",
                "ringkuman": "/api/ringkuman",
                "bandingkan": "/api/bandingkan",
                "cari": "/api/cari",
                "drill": "/api/drill",
                "chart": {
                    "daerah": "/api/chart/per-daerah",
                    "jenis": "/api/chart/per-jenis",
                    "program": "/api/chart/per-program",
                    "urusan": "/api/chart/per-urusan",
                    "tim-kerja": "/api/chart/per-tim-kerja",
                    "hasil": "/api/chart/per-hasil",
                    "metode": "/api/chart/per-metode",
                    "bulanan": "/api/chart/bulanan",
                },
            },
        }
    )


@api_bp.route("/metadata")
def metadata():
    """Daftar semua pilihan filter yang tersedia. Agent gunakan untuk memahami data."""
    return jsonify(
        {
            "deskripsi": "Rapat Harmonisasi - Bidang Legal Drafter",
            "filter": {
                "tanggal_dari": "YYYY-MM-DD - filter tanggal awal",
                "tanggal_sampai": "YYYY-MM-DD - filter tanggal akhir",
                "daerah": "Kabupaten/Kota",
                "jenis": "Raperda (DPRD) | Raperda (Pemda) | Raperkada",
                "program_pembentukan": "Propemperda | Propemperkada | Di luar Propemperkada",
                "urusan_pemerintahan": "Bidang urusan pemerintahan",
                "tim_kerja": "Tim Kerja 1 | Tim Kerja 2 | Tim Kerja 3 | Tim Kerja 4",
                "hasil": "Selesai | Dikembalikan",
                "metode": "One Day Service | Normal",
            },
            "pilihan": {
                "daerah": RapatHarmonisasi.DAERAH_CHOICES,
                "jenis": RapatHarmonisasi.JENIS_CHOICES,
                "program_pembentukan": RapatHarmonisasi.PROGRAM_CHOICES,
                "urusan_pemerintahan": RapatHarmonisasi.URUSAN_PEMERINTAHAN_CHOICES,
                "tim_kerja": RapatHarmonisasi.TIM_KERJA_CHOICES,
                "hasil": RapatHarmonisasi.HASIL_CHOICES,
                "metode": RapatHarmonisasi.METODE_CHOICES,
            },
        }
    )


@api_bp.route("/ringkuman")
def ringkuman():
    """Ringkuman teks untuk agent. Cukup 1 request, dapat semua info."""
    tanggal_dari, tanggal_sampai = _parse_date_args()
    q = _get_query(tanggal_dari, tanggal_sampai)
    total = q.count()

    if total == 0:
        return jsonify(
            {
                "periode": _periode_label(tanggal_dari, tanggal_sampai),
                "total": 0,
                "ringkuman": "Tidak ada data rapat harmonisasi pada periode ini.",
            }
        )

    per_hasil = dict(
        q.with_entities(RapatHarmonisasi.hasil, func.count())
        .group_by(RapatHarmonisasi.hasil)
        .all()
    )
    per_metode = dict(
        q.with_entities(RapatHarmonisasi.metode, func.count())
        .group_by(RapatHarmonisasi.metode)
        .all()
    )

    top_daerah = (
        q.with_entities(RapatHarmonisasi.daerah, func.count())
        .group_by(RapatHarmonisasi.daerah)
        .order_by(func.count().desc())
        .limit(3)
        .all()
    )
    top_jenis = (
        q.with_entities(RapatHarmonisasi.jenis, func.count())
        .group_by(RapatHarmonisasi.jenis)
        .order_by(func.count().desc())
        .all()
    )

    selesai = per_hasil.get("Selesai", 0)
    dikembalikan = per_hasil.get("Dikembalikan", 0)
    ods = per_metode.get("One Day Service", 0)
    normal = per_metode.get("Normal", 0)
    pct_selesai = round(selesai / total * 100, 1) if total else 0

    return jsonify(
        {
            "periode": _periode_label(tanggal_dari, tanggal_sampai),
            "total": total,
            "selesai": selesai,
            "dikembalikan": dikembalikan,
            "persentase_selesai": pct_selesai,
            "one_day_service": ods,
            "normal": normal,
            "per_jenis": dict(top_jenis),
            "top_daerah": [{"daerah": d, "jumlah": j} for d, j in top_daerah],
        }
    )


@api_bp.route("/bandingkan")
def bandingkan():
    """Bandingkan 2 periode. Parameter:
    tanggal_dari_1, tanggal_sampai_1, tanggal_dari_2, tanggal_sampai_2
    """
    d1 = request.args.get("tanggal_dari_1", "")
    s1 = request.args.get("tanggal_sampai_1", "")
    d2 = request.args.get("tanggal_dari_2", "")
    s2 = request.args.get("tanggal_sampai_2", "")

    q1 = _get_query(d1, s1)
    q2 = _get_query(d2, s2)

    def _periode_stats(q):
        total = q.count()
        if total == 0:
            return {
                "total": 0,
                "selesai": 0,
                "dikembalikan": 0,
                "persentase_selesai": 0,
                "ods": 0,
            }
        hasil = dict(
            q.with_entities(RapatHarmonisasi.hasil, func.count())
            .group_by(RapatHarmonisasi.hasil)
            .all()
        )
        metode = dict(
            q.with_entities(RapatHarmonisasi.metode, func.count())
            .group_by(RapatHarmonisasi.metode)
            .all()
        )
        selesai = hasil.get("Selesai", 0)
        return {
            "total": total,
            "selesai": selesai,
            "dikembalikan": hasil.get("Dikembalikan", 0),
            "persentase_selesai": round(selesai / total * 100, 1),
            "ods": metode.get("One Day Service", 0),
        }

    return jsonify(
        {
            "periode_1": {
                "label": _periode_label(d1, s1),
                "dari": d1,
                "sampai": s1,
                **_periode_stats(q1),
            },
            "periode_2": {
                "label": _periode_label(d2, s2),
                "dari": d2,
                "sampai": s2,
                **_periode_stats(q2),
            },
        }
    )


@api_bp.route("/cari")
def cari():
    """Cari data berdasarkan kata kunci di nama_raperda atau keterangan."""
    q_text = request.args.get("q", "").strip()
    tanggal_dari, tanggal_sampai = _parse_date_args()

    if not q_text:
        return jsonify({"error": "Parameter 'q' wajib diisi"}), 400

    q = _get_query(tanggal_dari, tanggal_sampai)
    q = q.filter(
        db.or_(
            RapatHarmonisasi.nama_raperda.ilike(f"%{q_text}%"),
            RapatHarmonisasi.keterangan.ilike(f"%{q_text}%"),
            RapatHarmonisasi.daerah.ilike(f"%{q_text}%"),
            RapatHarmonisasi.urusan_pemerintahan.ilike(f"%{q_text}%"),
            RapatHarmonisasi.jenis.ilike(f"%{q_text}%"),
            RapatHarmonisasi.program_pembentukan.ilike(f"%{q_text}%"),
            RapatHarmonisasi.tim_kerja.ilike(f"%{q_text}%"),
            RapatHarmonisasi.hasil.ilike(f"%{q_text}%"),
            RapatHarmonisasi.metode.ilike(f"%{q_text}%"),
        )
    )

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    pagination = q.order_by(RapatHarmonisasi.tanggal_rapat.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify(
        {
            "query": q_text,
            "total": pagination.total,
            "items": [_record_to_dict(r) for r in pagination.items],
        }
    )


def _periode_label(dari, sampai):
    """Buat label periode yang mudah dibaca."""
    BULAN = {
        1: "Januari",
        2: "Februari",
        3: "Maret",
        4: "April",
        5: "Mei",
        6: "Juni",
        7: "Juli",
        8: "Agustus",
        9: "September",
        10: "Oktober",
        11: "November",
        12: "Desember",
    }
    if dari and sampai:
        try:
            d1 = datetime.strptime(dari, "%Y-%m-%d")
            d2 = datetime.strptime(sampai, "%Y-%m-%d")
            return f"{d1.day} {BULAN[d1.month]} {d1.year} - {d2.day} {BULAN[d2.month]} {d2.year}"
        except ValueError:
            pass
    elif dari:
        try:
            d1 = datetime.strptime(dari, "%Y-%m-%d")
            return f"Dari {d1.day} {BULAN[d1.month]} {d1.year}"
        except ValueError:
            pass
    elif sampai:
        try:
            d2 = datetime.strptime(sampai, "%Y-%m-%d")
            return f"Sampai {d2.day} {BULAN[d2.month]} {d2.year}"
        except ValueError:
            pass
    return "Semua Periode"
