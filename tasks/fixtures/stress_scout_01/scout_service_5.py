import scout_config_v1

def run_service():
    backoff = scout_config_v1.get_backoff(1)
    print(f"Service 5 running with backoff: {backoff}")

if __name__ == "__main__":
    run_service()
