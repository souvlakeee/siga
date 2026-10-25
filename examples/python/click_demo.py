import time
import click

with click.progressbar(range(60), label="Uploading") as items:
    for _ in items:
        time.sleep(0.08)
