import os
import sys
import yaml

def estimate_tokens(config_path):
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    total_chars = 0
    for segment_path in config.get('segments', []):
        if os.path.exists(segment_path):
            with open(segment_path, 'r') as sf:
                total_chars += len(sf.read())
    
    # 1 token approx 4 chars
    tokens = total_chars / 4.0
    print(f"{tokens:.2f}")

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    estimate_tokens(sys.argv[1])
