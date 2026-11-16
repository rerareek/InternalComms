Fix for ModuleNotFoundError: No module named st_aggrid

This version guards the optional st_aggrid import. If AG Grid is missing, editable tables use native Streamlit st.data_editor instead of crashing the entire app. Native editor alignment is NOT guaranteed.

1. Upload all files INSIDE InternalComms-main/ to your GitHub repo root (same folder as logbook_meeting.py).
2. Verify the repository root requirements.txt includes streamlit-aggrid>=1.1.8,<2.
3. Commit and reboot/redeploy Streamlit Cloud.
4. If AG Grid still does not appear, inspect the app deployment/build logs for pip install errors, and verify the deployed branch and main-file path.

No live Streamlit Cloud / Supabase test was possible.
