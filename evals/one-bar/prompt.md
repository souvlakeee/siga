---
description: A slow job gets exactly one ⟦bar⟧ token, no progress chatter, one final report.
tags: [behavior]
runs: 3
expected_outcome: Claude writes `⟦bar⟧` once on its own labelled line before running the job, waits without posting progress updates, and reports the result once.
---
Run this slow build for me and tell me when it's done:

for i in $(seq 1 20); do echo "[$i/20] compiling module_$i"; sleep 0.3; done
