from config import Config
from app import App

def test_config_injection():
    c1 = Config(port=8080)
    app1 = App(c1)
    assert app1.run() == "App running on port 8080"
    
    c2 = Config(port=9090)
    app2 = App(c2)
    assert app2.run() == "App running on port 9090"
    
    print("PASS")

if __name__ == "__main__":
    test_config_injection()
