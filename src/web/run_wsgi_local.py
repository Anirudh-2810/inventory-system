"""Local WSGI runner (zero dependencies) — useful to test the production
artifact without installing gunicorn. For real production use gunicorn:

    gunicorn web.wsgi:application --bind 0.0.0.0:8000 --workers 4
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wsgiref.simple_server import make_server
from web.wsgi import application

host = os.getenv("WEB_HOST", "127.0.0.1")
port = int(os.getenv("WEB_PORT", "8000"))
httpd = make_server(host, port, application)
print(f"StockOffline WSGI (local deploy) on http://{host}:{port}")
try:
    httpd.serve_forever()
except KeyboardInterrupt:
    httpd.shutdown()
