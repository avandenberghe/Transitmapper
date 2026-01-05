#!/usr/bin/env python3
"""
Simple development server for testing the static site locally.

Usage:
    python serve.py

Then open http://localhost:8000
"""

import http.server
import socketserver
import os

PORT = 8000
DIRECTORY = "web"

os.chdir(os.path.join(os.path.dirname(__file__), DIRECTORY))

Handler = http.server.SimpleHTTPRequestHandler

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Serving TransitMapper at http://localhost:{PORT}")
    print("Press Ctrl+C to stop")
    httpd.serve_forever()
