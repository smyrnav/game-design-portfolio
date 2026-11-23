"""Static file server for blue-moon-3d with caching disabled, so texture
updates are always picked up on a plain refresh."""
import http.server

class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Expires", "0")
        super().end_headers()

if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("127.0.0.1", 8642), NoCacheHandler).serve_forever()
