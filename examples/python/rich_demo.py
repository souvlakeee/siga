import time
from rich.progress import track

for _ in track(range(60), description="Processing..."):
    time.sleep(0.08)
