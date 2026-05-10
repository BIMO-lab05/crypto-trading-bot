"""Phase 4 plan 04-03 — operator-triggered PR pipeline.

Submodules:
  body.py     PR title + body templating (CD-01, CD-12, D-09).
  gh.py       gh CLI subprocess wrapper with auth + tool-presence checks (D-11, CD-09, CD-10).
  open_pr.py  run_open_pr orchestrator: snapshot → ensemble → significance → artifacts → gh.
"""
