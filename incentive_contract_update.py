"""Editable Incentive & Contract Update tracker, backed by Supabase."""
import pandas as pd
import streamlit as st
from supabase import create_client

TABLE = "incentive_contract_updates"
FIELDS = ["no","shipping","service","actual_2024","actual_2025","forecast_2026","budget_2026","contract_update","remark","document_type","incentive_details"]
NUMERIC = ["actual_2024","actual_2025","forecast_2026","budget_2026"]
LABELS = {
    "no":"No", "shipping":"Shipping Line", "service":"Service",
    "actual_2024":"Actual 2024 (TEU)", "actual_2025":"Actual 2025 (TEU)",
    "forecast_2026":"Forecast 3QF 2026 (TEU)", "budget_2026":"Budget 2026 (TEU)",
    "contract_update":"Contract Update", "remark":"Remark",
    "document_type":"Document Type", "incentive_details":"Incentive Details"
}

def client():
    return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])

def load():
    response = client().table(TABLE).select("*").order("sort_order").execute()
    return pd.DataFrame(response.data or [])

def render():
    st.title("Incentive & Contract Update")
    st.caption("Editable contract and incentive tracker · changes persist in Supabase after Save.")
    try:
        original = load()
    except Exception as exc:
        st.error("Cannot load contract tracker. Run the included SQL migration first and check Supabase permissions.")
        st.code(str(exc))
        return

    if original.empty:
        st.info("No records yet. Add records below, or import the supplied Excel-format sample using the optional seed SQL.")
    view = original.reindex(columns=FIELDS).copy()
    for col in NUMERIC:
        view[col] = pd.to_numeric(view[col], errors="coerce")
    for col in FIELDS:
        if col not in NUMERIC:
            view[col] = view[col].fillna("").astype(str)

    if not view.empty:
        a,b,c = st.columns(3)
        a.metric("Shipping Line Records", f"{len(view):,}")
        b.metric("Forecast 2026", f"{view['forecast_2026'].sum():,.2f} TEU")
        c.metric("Budget 2026", f"{view['budget_2026'].sum():,.2f} TEU")
    st.subheader("Contract & Incentive Register")
    st.caption("Click any cell to edit. Add or remove rows using the editor. Save Changes to persist.")
    cfg = {k:st.column_config.NumberColumn(LABELS[k],format="%.2f",min_value=0) for k in NUMERIC}
    cfg.update({
        "shipping":st.column_config.TextColumn("Shipping Line",required=True),
        "service":st.column_config.TextColumn("Service",width="large"),
        "contract_update":st.column_config.TextColumn("Contract Update",width="large",help="Preserved as original text; confirm date validity before updating."),
        "remark":st.column_config.TextColumn("Remark",width="large"),
        "incentive_details":st.column_config.TextColumn("Incentive Details",width="large"),
    })
    edited = st.data_editor(view, num_rows="dynamic", hide_index=True, use_container_width=True,
                            column_config=cfg, key="contract_update_editor")
    with st.expander("Important data notes"):
        st.write("The supplied reference lists contract periods, remarks and document types, but does not include incentive amounts or terms. The Incentive Details field is blank until entered.")
        st.write("Contract periods from the source are kept as text, including possible date typos; they are not silently corrected.")
        st.write("The summary totals above are calculated from saved records, not unsaved edits.")
    if st.button("Save Changes",type="primary",key="save_contract_updates"):
        clean = edited.copy()
        clean["shipping"] = clean["shipping"].fillna("").astype(str).str.strip()
        clean = clean[clean["shipping"] != ""]
        if clean["shipping"].duplicated().any():
            st.error("Shipping Line must be unique for each record. Combine or rename duplicates before saving.")
            return
        records = []
        for i,(_,row) in enumerate(clean.iterrows()):
            obj = {}
            for field in FIELDS:
                v = row.get(field)
                if field in NUMERIC:
                    obj[field] = None if pd.isna(v) or str(v).strip()=="" else float(v)
                else:
                    obj[field] = "" if pd.isna(v) else str(v).strip()
            obj["sort_order"] = i
            records.append(obj)
        try:
            sb=client()
            # Save first, then delete removed records to avoid accidental loss on a failed write.
            if records:
                sb.table(TABLE).upsert(records,on_conflict="shipping").execute()
            old_names=set(original.get("shipping",pd.Series(dtype=str)).dropna().astype(str))
            new_names={r["shipping"] for r in records}
            for removed in old_names-new_names:
                sb.table(TABLE).delete().eq("shipping",removed).execute()
            st.success("Changes saved to Supabase.")
            st.rerun()
        except Exception as exc:
            st.error(f"Save failed: {exc}")
