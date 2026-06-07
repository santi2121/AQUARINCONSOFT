import sys
import os

path = "/home/YOUR_USERNAME/aquarincon"
if path not in sys.path:
    sys.path.append(path)

os.environ["FLASK_ENV"] = "production"
os.environ["SESSION_COOKIE_SECURE"] = "1"

from app import app as application
