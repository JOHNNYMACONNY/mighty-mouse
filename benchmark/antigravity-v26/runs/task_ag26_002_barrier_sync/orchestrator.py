def sync_work(barrier, worker_id, results_list):
    # Phase 1: Local Setup
    # Workers record their setup status in the shared results list
    results_list.append(f"SETUP_DONE_{worker_id}")
    
    # Phase 2: Synchronization Point
    # All processes must wait here until the specified number of workers (num_workers) reach this point
    barrier.wait()
    
    # Phase 3: Synchronized Execution
    # Execution starts only after all workers have signaled setup completion
    results_list.append(f"EXEC_START_{worker_id}")
