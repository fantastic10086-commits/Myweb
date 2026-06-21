import os
import sys

# Vercel serverless: filesystem is read-only except /tmp
os.environ.setdefault('FLASK_ENV', 'production')
os.environ.setdefault('DATABASE_DIR', '/tmp')
os.environ.setdefault('PDF_DIR', '/tmp/pdf')
os.environ.setdefault('UPLOAD_DIR', '/tmp/uploads')

# Ensure writable directories exist
for d in ['/tmp', '/tmp/pdf', '/tmp/uploads']:
    os.makedirs(d, exist_ok=True)

from app import app
