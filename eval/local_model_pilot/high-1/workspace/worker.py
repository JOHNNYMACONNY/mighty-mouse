def process_job(job, store, handler):
    handler(job)
    store.mark_completed(job["id"])
    return "processed"
