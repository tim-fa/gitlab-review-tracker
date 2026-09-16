"""Entry point for the GitLab review tracker desktop app.

See review_tracker/ui/tkinter/app.py for the Tkinter UI, review_tracker/core
for the UI-agnostic use-cases, and review_tracker/data for GitLab/git/JSON
storage access.
"""
from review_tracker.ui.tkinter.app import main

if __name__ == "__main__":
    main()
