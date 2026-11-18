# Monthly Presentation Generator — first integrated release

A new **Monthly Presentation Generator** menu has been added to CRM UPDATE.

- Master template: `assets/templates/commercial_meeting_hpi.pptx` (the uploaded original).
- Slides 2 and 3: editable PowerPoint tables generated from live Supabase (`throughput` and `throughput_budget_2526`).
- Slide 1: original cover retained, with a generated report-date label. The original artwork may contain historical date text; review before sharing.
- Slides 4–8 and 10–11: unchanged historical template content, visibly marked REFERENCE / NOT refreshed.
- Slide 9: unchanged.
- Year selection limited to 2026 because the budget schema only has 2025/2026 series.
- Generation fails when mandatory records are missing, duplicated, or invalid.

This is a deliberately limited first implementation: it does NOT claim all 11 slides are dynamic. To automate slides 4–8 and 10–11, their source-table mapping, time-versioned contract notes, and updated berthing-window sources must be defined and validated. The original slide 3 baseline is Actual 2025, not Actual 2026.

No database migration is required. Install `python-pptx` via updated requirements.
