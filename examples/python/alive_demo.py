import time
from alive_progress import alive_bar

with alive_bar(60, title="Indexing") as bar:
    for _ in range(60):
        time.sleep(0.08)
        bar()
