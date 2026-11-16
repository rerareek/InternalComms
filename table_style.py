"""Read-only table renderer with reliable HTML cell alignment.

Streamlit st.dataframe uses a canvas-based grid; Pandas Styler text-align
rules are not consistently honored by that grid. Render display-only tables
as real HTML instead. Keep st.data_editor untouched for editable inputs.
"""
import html
import pandas as pd
import streamlit as st


def display_table(_st, data, *args, **kwargs):
    if not isinstance(data, (pd.DataFrame, pd.io.formats.style.Styler)):
        return _st.dataframe(data, *args, **kwargs)
    styler = data if isinstance(data, pd.io.formats.style.Styler) else data.style
    frame = styler.data
    if frame.empty:
        _st.info('No records to display.')
        return
    # Preserve any caller's Styler formatting, shading, and subtotal highlights.
    # Select columns by position so repeated header names remain valid.
    css = """
    <style>
      .jict-table-scroll {width:100%;overflow-x:auto;overflow-y:auto;
        max-height:var(--jict-max-height, 560px);border:1px solid rgba(128,128,128,.25);
        border-radius:8px;margin:.35rem 0 1rem}
      .jict-table-scroll table {border-collapse:collapse;width:100%;font-size:.88rem;}
      .jict-table-scroll thead th {position:sticky;top:0;z-index:2;
        background:var(--secondary-background-color,#f5f5f5);font-weight:650;
        text-align:center!important;white-space:nowrap;}
      .jict-table-scroll th,.jict-table-scroll td {padding:8px 12px;
        border-bottom:1px solid rgba(128,128,128,.17);text-align:center!important;vertical-align:middle;}
      .jict-table-scroll tbody tr:hover {background:rgba(128,128,128,.07);}
      .jict-table-scroll thead th:first-child,
      .jict-table-scroll tbody td:first-child,
      .jict-table-scroll tbody th:first-child {text-align:left!important;}
    </style>
    """
    # Avoid a hidden pandas index becoming the first (left-aligned) column.
    hide_index = kwargs.get('hide_index', True)
    if hide_index:
        styler = styler.hide(axis='index')
    html_table = styler.to_html()
    max_height = kwargs.get('height', 560)
    if not isinstance(max_height, (int,float)):
        max_height = 560
    _st.markdown(css + f'<div class="jict-table-scroll" style="--jict-max-height:{int(max_height)}px">' + html_table + '</div>', unsafe_allow_html=True)
