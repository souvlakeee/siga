import time
from tqdm import tqdm

for _ in tqdm(range(60), desc="training"):
    time.sleep(0.08)
