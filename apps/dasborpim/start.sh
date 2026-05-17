#!/bin/bash
cd /home/ubnt/dasborpim
source .venv/bin/activate
exec gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 "app:create_app()"
