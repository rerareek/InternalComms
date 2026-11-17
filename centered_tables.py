"""Consistent center-aligned read-only tables without additional dependencies."""
import html
import re
import pandas as pd
import streamlit as st


def _display_header(column):
    """Standardize visible units without changing source field names."""
    label = str(column)
    label = re.sub(r'\bTEUs?\b(?!\s*\))', '(TEU)', label, flags=re.IGNORECASE)
    label = re.sub(r'\b(Share|Growth|Change|Variance|Rebate)\s*%(?!\s*\))',
                   lambda m: m.group(1) + ' (%)', label, flags=re.IGNORECASE)
    label = re.sub(r'\b(20\d{2})\s*%(?!\s*\))', r'\1 Share (%)', label)
    return label


def centered_dataframe(data, *args, **kwargs):
    """Render a read-only table: first column left, remaining columns centered.

    Falls back to Streamlit's native table for unsupported data types.
    Note: HTML tables do not support Streamlit's native sorting interactions.
    """
    try:
        styler = isinstance(data, pd.io.formats.style.Styler)
        df = data.data if styler else pd.DataFrame(data)
        if df.empty:
            return st.dataframe(data, *args, **kwargs)
        # Keep existing Styler formatting and row highlighting where possible.
        if styler:
            obj = data.rename(columns=_display_header)
            obj = obj.set_table_styles([
                {'selector':'th.col_heading','props':[('text-align','center !important')]},
                {'selector':'td','props':[('text-align','center !important')]},
                {'selector':'th.col_heading.level0.col0','props':[('text-align','left !important')]},
                {'selector':'td.col0','props':[('text-align','left !important')]},
            ],overwrite=False)
            html_table = obj.to_html(index=not kwargs.get('hide_index',False))
        else:
            fmt = df.copy()
            fmt.columns = [_display_header(c) for c in fmt.columns]
            for col in fmt.columns:
                fmt[col] = fmt[col].map(lambda v: '—' if pd.isna(v) else (f'{v:,.0f}' if isinstance(v,(int,float)) and not isinstance(v,bool) and float(v).is_integer() else f'{v:,.2f}' if isinstance(v,(int,float)) and not isinstance(v,bool) else str(v)))
            html_table = fmt.to_html(index=not kwargs.get('hide_index',False),escape=True,border=0,classes='jict-centered-table')
        st.markdown("<style>.jict-table-wrap{width:100%;overflow-x:auto;max-height:580px;overflow-y:auto;border:1px solid #aaa;border-radius:8px}.jict-table-wrap table{border-collapse:collapse;width:100%;font-size:.88rem}.jict-table-wrap th,.jict-table-wrap td{padding:9px 12px;border-bottom:1px solid #ddd;text-align:center!important;white-space:nowrap}.jict-table-wrap tbody td:first-child,.jict-table-wrap thead th:first-child{text-align:left!important}.jict-table-wrap thead th{position:sticky;top:0;background:#f0f2f6;color:#222;z-index:1}</style><div class='jict-table-wrap'>" + html_table + "</div>",unsafe_allow_html=True)
    except Exception as exc:
        st.dataframe(data, *args, **kwargs)
