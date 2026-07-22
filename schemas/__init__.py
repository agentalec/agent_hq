# Makes schemas/ installable as package data so the __file__-relative loaders in
# engine/handoff.py and engine/runner.py resolve under a non-editable install
# (site-packages/schemas/*.json) exactly as they do in a repo checkout.
