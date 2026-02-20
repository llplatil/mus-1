"""
Legacy Streamlit entrypoint (shim).

The MUS1 web app was refactored into smaller modules under `mus1.web.*`.
This file is kept so existing launchers that call:

  streamlit run .../experiment_browser.py

continue to work.
"""

from mus1.web.app import main


if __name__ == "__main__":
    main()

