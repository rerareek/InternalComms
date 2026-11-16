NEW MENU: Shipping Data Maintenence
1. Upload all changed/new Python files to GitHub, including shipping_data_maintenance.py and updated logbook_meeting.py.
2. Run shipping_data_maintenance.sql ONCE in Supabase SQL Editor to create and seed 21 service records. This does not overwrite existing service rows.
3. Commit changes and reboot Streamlit Cloud.
4. In the sidebar, Shipping Data Maintenence appears directly after Profilling Incentives & Contract Update.
5. Input Data tab allows edits, additions, deletion, and Save Changes. Service names must be unique. Renaming a service is treated as inserting the new name and deleting the old one.
6. SQL enables RLS and expects existing service_role key in Streamlit secrets; no public policies are added.
7. Original source 'NO' sequence 8 then 7 is preserved, and average volume per call is kept as text (e.g. 5000 Teus).
