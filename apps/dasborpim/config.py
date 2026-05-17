import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "ganti-dengan-secret-key-yang-aman")

    # Default: SQLite untuk development. Untuk produksi, set DATABASE_URL ke PostgreSQL.
    # Contoh PostgreSQL: postgresql://postgres:postgres@localhost:5432/dasborpim
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///dasborpim.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
