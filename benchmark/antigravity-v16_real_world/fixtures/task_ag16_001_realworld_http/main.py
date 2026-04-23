# Implement a simple HTTP server using http.server that listens on port 8000.
# It should support GET requests for:
# - /health: returns "OK"
# - /metrics: returns "requests_total: <count>" where count is the total number of requests handled.
# Do not use any external dependencies.

import http.server
import socketserver

# Global counter for metrics
requests_total = 0

class MetricsHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global requests_total
        requests_total += 1
        
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"OK")
        elif self.path == '/metrics':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(f"requests_total: {requests_total}".encode())
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == "__main__":
    PORT = 8000
    with socketserver.TCPServer(("", PORT), MetricsHandler) as httpd:
        httpd.serve_forever()
