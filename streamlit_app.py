"""Community Cloud entrypoint; local demos continue to use app.py."""
import os
from pathlib import Path
import runpy

import streamlit as st

os.environ["EQUALSTART_PUBLIC"] = "1"
# Root-level Community Cloud secrets become environment variables when loaded.
try:
    st.secrets.to_dict()
except FileNotFoundError:
    pass
# Use cohort inference credits for the hosted app; explicit secrets can override.
os.environ.setdefault("LLM_PROVIDER", "nebius")
st.set_option("client.showErrorDetails", "none")
st.set_option("client.toolbarMode", "viewer")
runpy.run_path(str(Path(__file__).with_name("app.py")), run_name="__main__")
