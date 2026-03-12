#!/usr/bin/env python3
"""Serve the static site locally."""

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import os


ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)

server = ThreadingHTTPServer(("127.0.0.1", 8000), SimpleHTTPRequestHandler)
print("Serving SharpLine Daily at http://127.0.0.1:8000")
server.serve_forever()
