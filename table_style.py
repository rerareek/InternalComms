"""Shared display styling for JICT tables (does not change underlying data)."""
import re
import pandas as pd


def display_table(st, data, *args, **kwargs):
    """Center table headers and data except the first text/category column."""
    if isinstance(data, pd.DataFrame):
        styled = data.style
        columns = list(data.columns)
    elif isinstance(data, pd.io.formats.style.Styler):
        styled = data
        columns = list(data.data.columns)
    else:
        return st.dataframe(data, *args, **kwargs)
    if columns:
        # Preserve pre-existing number formats / conditional formatting.
        styled = styled.set_table_styles([
            {"selector": "th.col_heading", "props": [("text-align", "center")]},
            {"selector": "th.col_heading.level0.col0", "props": [("text-align", "left")]},
        ], overwrite=False)
        if len(columns) > 1:
            styled = styled.set_properties(subset=columns[1:], **{"text-align": "center"})
        styled = styled.set_properties(subset=[columns[0]], **{"text-align": "left"})
    return st.dataframe(styled, *args, **kwargs)
