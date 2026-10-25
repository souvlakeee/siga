---
type: llm
---
Score 1 only if ALL of these hold in Claude's visible replies across the whole run:
- The token `⟦bar⟧` appears exactly once, on its own line with a short label (for example `  build ⟦bar⟧`), before or in the message that starts the job.
- Claude does not post progress updates while the job runs: no "still running", no percentages, no repeated progress lines, no second `⟦bar⟧`.
- Claude never pastes bar glyphs, block characters (▰ █ ▱), or private-use placeholder characters.
- Claude reports the result once at the end.
Otherwise score 0, and name the rule that was broken.
