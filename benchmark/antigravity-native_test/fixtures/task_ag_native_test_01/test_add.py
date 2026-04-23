import subprocess

def test_add():
    res = subprocess.run(["python3", "add.py", "5", "7"], capture_output=True, text=True)
    assert res.stdout.strip() == "12"
    print("PASS")

if __name__ == "__main__":
    test_add()
