import os

def run_benchmarks():
    # This generates temp files
    with open("temp_1.log", "w") as f: f.write("data")
    with open("tmp_2.log", "w") as f: f.write("data")
    # Bug: crashes here
    raise ValueError("Runner crashed")

def cleanup():
    # Only cleans up tmp_ files
    for f in os.listdir("."):
        if f.startswith("tmp_"):
            os.remove(f)
