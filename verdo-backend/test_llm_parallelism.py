import time
import threading
from app.services.ingester.services.LLM import LLM

def dummy_task(duration):
    print(f"Task starting on thread {threading.current_thread().name}")
    time.sleep(duration)
    print(f"Task finished on thread {threading.current_thread().name}")
    return "done"

def test_parallelism():
    print("Initializing LLM...")
    # We need to mock OPENAIKEY if it's not set, but the user has it.
    # If it fails due to missing key, we might need to patch os.getenv or set it.
    try:
        llm = LLM(maxWorkers=10)
    except RuntimeError as e:
        print(f"Caught expected error if key missing: {e}")
        import os
        os.environ["OPENAIKEY"] = "dummy"
        llm = LLM(maxWorkers=10)

    print("Submitting 5 tasks of 2 seconds each...")
    start_time = time.time()
    futures = []
    for i in range(5):
        futures.append(llm.submit(dummy_task, 2))

    print("Waiting for results...")
    for f in futures:
        f.result()
    
    end_time = time.time()
    duration = end_time - start_time
    print(f"Total duration: {duration:.2f} seconds")
    
    if duration < 3:
        print("SUCCESS: Tasks ran in parallel.")
    else:
        print("FAILURE: Tasks ran sequentially.")

if __name__ == "__main__":
    test_parallelism()
