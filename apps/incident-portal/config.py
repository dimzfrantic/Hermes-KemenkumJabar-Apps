import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / 'instance'
UPLOAD_DIR = BASE_DIR / 'uploads'

load_dotenv(BASE_DIR / '.env')
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'incident-portal-dev-secret')
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        f"sqlite:///{(INSTANCE_DIR / 'incident_portal.db').as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    UPLOAD_FOLDER = str(UPLOAD_DIR)
    INCIDENTS_DIR = os.getenv('INCIDENTS_DIR', '/home/ubnt/incidents')
    INCIDENT_WRITER_PATH = os.getenv('INCIDENT_WRITER_PATH', '/home/ubnt/incidents/incident_writer.py')
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_GROUP_ID = os.getenv('TELEGRAM_GROUP_ID', '')
    TELEGRAM_TOPIC_INSIDEN_ID = os.getenv('TELEGRAM_TOPIC_INSIDEN_ID', os.getenv('TOPIC_INSIDEN_ID', ''))
    INCIDENT_CACHE_SYNC_INTERVAL_SECONDS = int(os.getenv('INCIDENT_CACHE_SYNC_INTERVAL_SECONDS', '5'))
    INCIDENT_DATABASE_URL = os.getenv('INCIDENT_DATABASE_URL', os.getenv('DATABASE_URL', ''))
    DEFAULT_EMPLOYEE_PASSWORD = os.getenv('DEFAULT_EMPLOYEE_PASSWORD', 'ChangeMe123!')
    ADMIN_NIP = os.getenv('ADMIN_NIP', 'admin')
    ADMIN_NAME = os.getenv('ADMIN_NAME', 'Administrator Portal TI')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'Admin123!')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'pdf'}
    TICKET_CATEGORIES = {
        'NETWORK': 'Network',
        'APPLICATION': 'Application',
        'HARDWARE': 'Hardware',
        'OTHER': 'Other',
    }
