# 47. Post-motion change relative to pre-motion shape

To address experiment 45's overnight background-pattern failure, this variant saves the *change* in z-scored gate profile from 0.3–2.5 seconds before a credible motion update to two seconds after it. Each completed 20-second hold window is scored by how much that normalized shape change remains present. The last four changes are retained. No labels or raw energy feed the rule.

The variant did not resolve the main tradeoff. At support cutoff 0.5, replacement living-room occupancy is 96.2% with a 20-second false vacancy, and `labeled-loop` bathroom release improves to 23 seconds. But `labeled-walk` does not clear between/after its short visits, and the post-deploy bathroom remains occupied for **174 seconds** after exit. At cutoff 0.3, living-room occupancy rises to 98.9%, while bathroom release worsens further. The overnight control was not needed to reject this version.

No production algo code changed. [Data](results.json) and [script](analyze.py).
