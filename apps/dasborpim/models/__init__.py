from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="operator")
    nama_lengkap = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_operator(self):
        return self.role == "operator"

    @property
    def is_pimpinan(self):
        return self.role == "pimpinan"

    @property
    def is_admin(self):
        return self.role == "admin"


class RapatHarmonisasi(db.Model):
    """Data Rapat Harmonisasi - Bidang Legal Drafter"""

    __tablename__ = "rapat_harmonisasi"

    id = db.Column(db.Integer, primary_key=True)
    tanggal_rapat = db.Column(db.Date, nullable=False)
    daerah = db.Column(db.String(200), nullable=False)
    jenis = db.Column(db.String(50), nullable=False)
    program_pembentukan = db.Column(db.String(50), nullable=False)
    urusan_pemerintahan = db.Column(db.String(300), nullable=False)
    nama_raperda = db.Column(db.Text, nullable=False)
    tim_kerja = db.Column(db.String(20), nullable=False)
    hasil = db.Column(db.String(20), nullable=False, default="Selesai")
    metode = db.Column(db.String(20), nullable=False, default="Normal")
    keterangan = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    operator = db.relationship("User", backref="rapat_harmonisasi")

    JENIS_CHOICES = ["Raperda (DPRD)", "Raperda (Pemda)", "Raperkada"]
    PROGRAM_CHOICES = ["Propemperda", "Propemperkada", "Di luar Propemperkada"]
    TIM_KERJA_CHOICES = ["Tim Kerja 1", "Tim Kerja 2", "Tim Kerja 3", "Tim Kerja 4"]
    HASIL_CHOICES = ["Selesai", "Dikembalikan"]
    METODE_CHOICES = ["One Day Service", "Normal"]

    URUSAN_PEMERINTAHAN_CHOICES = [
        "Kesehatan",
        "Pendidikan",
        "Perhubungan",
        "Perindustrian",
        "Pekerjaan Umum dan Penataan Ruang",
        "Perumahan Rakyat dan Kawasan Permukiman",
        "Perpustakaan",
        "Komunikasi dan Informatika",
        "Pemberdayaan Masyarakat dan Desa",
        "Pemberdayaan Perempuan dan Pelindungan Anak",
        "Kepemudaan dan Olah Raga",
        "Urusan Unsur Penunjang (perencanaan, pengawasan, kepegawaian, keuangan, pendidikan dan latihan, penelitian dan pengembangan)",
        "Urusan Unsur Pendukung (Sekretariat Daerah)",
    ]

    DAERAH_CHOICES = [
        "Kabupaten Bandung",
        "Kabupaten Bandung Barat",
        "Kabupaten Bekasi",
        "Kabupaten Bogor",
        "Kabupaten Ciamis",
        "Kabupaten Cianjur",
        "Kabupaten Cirebon",
        "Kabupaten Garut",
        "Kabupaten Indramayu",
        "Kabupaten Karawang",
        "Kabupaten Kuningan",
        "Kabupaten Majalengka",
        "Kabupaten Pangandaran",
        "Kabupaten Purwakarta",
        "Kabupaten Subang",
        "Kabupaten Sukabumi",
        "Kabupaten Sumedang",
        "Kabupaten Tasikmalaya",
        "Kota Bandung",
        "Kota Banjar",
        "Kota Bekasi",
        "Kota Bogor",
        "Kota Cimahi",
        "Kota Cirebon",
        "Kota Depok",
        "Kota Sukabumi",
        "Kota Tasikmalaya",
    ]
