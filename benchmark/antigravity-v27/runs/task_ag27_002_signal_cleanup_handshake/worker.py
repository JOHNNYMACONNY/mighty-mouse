import signal

# Global flag to signal background worker termination
TERMINATE_REQUESTED = False

def setup_signal_handler():
    global TERMINATE_REQUESTED
    # Initializing termination state
    TERMINATE_REQUESTED = False
    
    def handle_sigusr1(signum, frame):
        # Closure handler to capture and print cleanup status
        global TERMINATE_REQUESTED
        TERMINATE_REQUESTED = True
        print("CLEANUP_INITIATED")
        
    # Registering the custom signal handler for SIGUSR1
    signal.signal(signal.SIGUSR1, handle_sigusr1)
