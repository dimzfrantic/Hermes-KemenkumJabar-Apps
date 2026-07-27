import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / 'instance'
RUNTIME_DIR = INSTANCE_DIR / 'runtime'
PREVIEW_DIR = INSTANCE_DIR / 'previews'
JOB_DIR = INSTANCE_DIR / 'jobs'
AUTO_EVENT_DIR = INSTANCE_DIR / 'auto-events'
AUTO_EVENT_RUNTIME_DIR = RUNTIME_DIR / 'auto-events'

load_dotenv(BASE_DIR / '.env')
for path in (INSTANCE_DIR, RUNTIME_DIR, PREVIEW_DIR, JOB_DIR, AUTO_EVENT_DIR, AUTO_EVENT_RUNTIME_DIR):
    path.mkdir(parents=True, exist_ok=True)


def _required_env(name: str) -> str:
    value = os.getenv(name, '').strip()
    if not value:
        raise RuntimeError(f'Environment variable wajib belum diisi: {name}')
    return value


class Config:
    SECRET_KEY = _required_env('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        f"sqlite:///{(INSTANCE_DIR / 'certificate_generator.db').as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024

    APP_NAME = os.getenv('APP_NAME', 'Layanan e-sertifikat Kemenkum Jabar')
    APP_TIMEZONE = os.getenv('APP_TIMEZONE', 'Asia/Jakarta')
    ADMIN_USERNAME = _required_env('ADMIN_USERNAME')
    ADMIN_PASSWORD = _required_env('ADMIN_PASSWORD')
    ADMIN_DISPLAY_NAME = _required_env('ADMIN_DISPLAY_NAME')

    GOOGLE_TOKEN_PATH = os.getenv('GOOGLE_TOKEN_PATH', str(Path.home() / '.hermes' / 'google_token.json'))
    DRIVE_SCOPES = [
        'https://www.googleapis.com/auth/drive.file',
        'https://www.googleapis.com/auth/drive.readonly',
    ]
    SHEETS_SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets.readonly',
    ]

    RUNTIME_DIR = str(RUNTIME_DIR)
    PREVIEW_DIR = str(PREVIEW_DIR)
    JOB_DIR = str(JOB_DIR)
    AUTO_EVENT_DIR = str(AUTO_EVENT_DIR)
    AUTO_EVENT_RUNTIME_DIR = str(AUTO_EVENT_RUNTIME_DIR)
    PREVIEW_SAMPLE_COUNT = int(os.getenv('PREVIEW_SAMPLE_COUNT', '3'))
    PREVIEW_RETENTION_HOURS = int(os.getenv('PREVIEW_RETENTION_HOURS', '6'))
    JOB_RETENTION_HOURS = int(os.getenv('JOB_RETENTION_HOURS', '24'))
    GENERATION_BATCH_SIZE = int(os.getenv('GENERATION_BATCH_SIZE', '25'))
    DB_COMMIT_BATCH_SIZE = int(os.getenv('DB_COMMIT_BATCH_SIZE', '25'))
    MAX_PARALLEL_WORKERS = int(os.getenv('MAX_PARALLEL_WORKERS', '3'))
    JOB_RETRY_COUNT = int(os.getenv('JOB_RETRY_COUNT', '1'))
    AUTO_EVENT_MAX_WORKERS = int(os.getenv('AUTO_EVENT_MAX_WORKERS', '2'))
    AUTO_EVENT_DEFAULT_INTERVAL_MINUTES = int(os.getenv('AUTO_EVENT_DEFAULT_INTERVAL_MINUTES', '5'))
    ALLOWED_TEMPLATE_EXTENSIONS = {'pptx'}
    ALLOWED_DATA_EXTENSIONS = {'xlsx'}
    PPT_PLACEHOLDERS = []
    SOFFICE_PATH = os.getenv('SOFFICE_PATH', '')
