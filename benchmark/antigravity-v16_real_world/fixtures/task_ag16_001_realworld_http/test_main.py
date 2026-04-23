import urllib.request
import urllib.error
import time
import subprocess
import os

def test_server():
    # Start server in background
    p = subprocess.Popen(["python3", "main.py"])
    time.sleep(1) # wait for server to start

    try:
        # Test /health
        req = urllib.request.Request("http://localhost:8000/health")
        with urllib.request.urlopen(req) as response:
            assert response.status == 200
            assert response.read().decode() == "OK"
        
        # Test /metrics
        req = urllib.request.Request("http://localhost:8000/metrics")
        with urllib.request.urlopen(req) as response:
            assert response.status == 200
            assert "requests_total" in response.read().decode()
            
        print("PASS")
    finally:
        p.terminate()
        p.wait()

if __name__ == "__main__":
    test_server()
