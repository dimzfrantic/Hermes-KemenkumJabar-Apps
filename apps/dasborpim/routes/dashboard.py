from flask import Blueprint, render_template, request
from flask_login import current_user
from sqlalchemy import func, extract
from datetime import datetime
from models import db, RapatHarmonisasi

dashboard_bp = Blueprint("dashboard", __name__)


def get_query_filtered(tanggal_dari="", tanggal_sampai=""):
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


def get_ringkasan(tanggal_dari="", tanggal_sampai=""):
    """Ringkasan dasar: total, per hasil, per metode."""
    q = get_query_filtered(tanggal_dari, tanggal_sampai)
    total = q.count()
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
    return {"total": total, "per_hasil": per_hasil, "per_metode": per_metode}


def get_rekapitulasi(tanggal_dari="", tanggal_sampai=""):
    """Rekapitulasi lengkap seperti di sheet."""
    q = get_query_filtered(tanggal_dari, tanggal_sampai)

    rekap = {}
    rekap["per_daerah"] = dict(
        q.with_entities(RapatHarmonisasi.daerah, func.count())
        .group_by(RapatHarmonisasi.daerah)
        .order_by(func.count().desc())
        .all()
    )
    rekap["per_jenis"] = dict(
        q.with_entities(RapatHarmonisasi.jenis, func.count())
        .group_by(RapatHarmonisasi.jenis)
        .all()
    )
    rekap["per_program"] = dict(
        q.with_entities(RapatHarmonisasi.program_pembentukan, func.count())
        .group_by(RapatHarmonisasi.program_pembentukan)
        .all()
    )
    rekap["per_urusan"] = dict(
        q.with_entities(RapatHarmonisasi.urusan_pemerintahan, func.count())
        .group_by(RapatHarmonisasi.urusan_pemerintahan)
        .order_by(func.count().desc())
        .all()
    )
    rekap["per_tim_kerja"] = dict(
        q.with_entities(RapatHarmonisasi.tim_kerja, func.count())
        .group_by(RapatHarmonisasi.tim_kerja)
        .all()
    )
    rekap["per_hasil"] = dict(
        q.with_entities(RapatHarmonisasi.hasil, func.count())
        .group_by(RapatHarmonisasi.hasil)
        .all()
    )
    rekap["per_metode"] = dict(
        q.with_entities(RapatHarmonisasi.metode, func.count())
        .group_by(RapatHarmonisasi.metode)
        .all()
    )
    rekap["total"] = q.count()
    return rekap


@dashboard_bp.route("/")
def index():
    tanggal_dari = request.args.get("tanggal_dari", "")
    tanggal_sampai = request.args.get("tanggal_sampai", "")
    is_pimpinan = current_user.is_authenticated and current_user.is_pimpinan
    ringkasan = get_ringkasan(tanggal_dari, tanggal_sampai)
    rekapitulasi = (
        get_rekapitulasi(tanggal_dari, tanggal_sampai) if is_pimpinan else None
    )
    return render_template(
        "dashboard/index.html",
        ringkasan=ringkasan,
        rekapitulasi=rekapitulasi,
        is_pimpinan=is_pimpinan,
        tanggal_dari=tanggal_dari,
        tanggal_sampai=tanggal_sampai,
    )
