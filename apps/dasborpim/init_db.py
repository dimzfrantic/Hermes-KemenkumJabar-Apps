"""Script untuk inisialisasi database dan membuat user default."""

from app import create_app
from models import db, User

app = create_app()

with app.app_context():
    db.create_all()

    if not User.query.filter_by(username="admin").first():
        admin = User(username="admin", nama_lengkap="Administrator", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)
        print("User admin dibuat (username: admin, password: admin123)")

    if not User.query.filter_by(username="operator").first():
        op = User(username="operator", nama_lengkap="Operator", role="operator")
        op.set_password("operator123")
        db.session.add(op)
        print("User operator dibuat (username: operator, password: operator123)")

    if not User.query.filter_by(username="pimpinan").first():
        pimpinan = User(username="pimpinan", nama_lengkap="Pimpinan", role="pimpinan")
        pimpinan.set_password("pimpinan123")
        db.session.add(pimpinan)
        print("User pimpinan dibuat (username: pimpinan, password: pimpinan123)")

    db.session.commit()
    print("Database siap digunakan.")
