def sync_work(barrier, worker_id, results_list):
    results_list.append(f"SETUP_DONE_{worker_id}")
    results_list.append(f"EXEC_START_{worker_id}")
