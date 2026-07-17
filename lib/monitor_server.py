import os
import threading
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
import json

WEBROOT = os.path.join(os.path.dirname(__file__), "monitor")

class MonitorHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/":
            self.send_file("index.html", "text/html")
            return
        if self.path == "/style.css":
            self.send_file("style.css", "text/css")
            return
        if self.path == "/app.js":
            self.send_file("app.js", "application/javascript")
            return
        if self.path == "/status":
            self.send_status()
            return
        self.send_error(404)

    def send_file(self, filename, mime):
        path = os.path.join(WEBROOT, filename)
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_status(self):
        data = self.server.status.get()
        text = json.dumps(data)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(text)))
        self.end_headers()
        self.wfile.write(text.encode())

    def log_message(self, format, *args):
        # Prevent every HTTP request from printing to the terminal.
        pass


class MonitorHTTPServer(ThreadingHTTPServer):

    def __init__(self, address, status):
        super().__init__(address, MonitorHandler)
        self.status = status

class MonitorServer(threading.Thread):

    def __init__(self, status, host="0.0.0.0", port=8080):
        super().__init__(daemon=True)
        self.server = MonitorHTTPServer((host, port), status)
     
    def run(self):
        self.server.serve_forever()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
