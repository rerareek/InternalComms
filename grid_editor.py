"""Shared editable AG Grid: centered headers/values, first label column left aligned.

Returns a pandas DataFrame compatible with existing Supabase save handlers.
"""
import pandas as pd
import streamlit as st
try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
    _AGGRID_AVAILABLE = True
except ImportError:
    # Do not crash the whole application when optional AG Grid is unavailable.
    _AGGRID_AVAILABLE = False


def edit_table(_st, data, *args, **kwargs):
    if not isinstance(data, pd.DataFrame):
        raise TypeError('edit_table expects a pandas DataFrame')
    if not _AGGRID_AVAILABLE:
        # Streamlit's native editor is a safe functional fallback; its cell
        # alignment is controlled by Streamlit, not by our CSS.
        return _st.data_editor(data, *args, **kwargs)
    key = kwargs.get('key', 'jict_editor')
    dynamic = kwargs.get('num_rows', 'fixed') == 'dynamic'
    hide_index = kwargs.get('hide_index', False)
    disabled = kwargs.get('disabled', [])
    disabled = set(disabled if isinstance(disabled, (list, tuple, set)) else ([disabled] if disabled else []))
    original = data.copy()
    index_name = original.index.name or 'Category'
    index_field = '__jict_index__'
    if not hide_index:
        work = original.reset_index(drop=True)
        work.insert(0, index_field, original.index.astype(str))
    else:
        work = original.reset_index(drop=True)
    # AG Grid and Streamlit's native editor have different empty-value conventions.
    work = work.astype(object).where(pd.notna(work), None)
    pending = _st.session_state.get(f'{key}_pending')
    if pending is not None:
        work = pd.DataFrame(pending).reindex(columns=work.columns)
    gb = GridOptionsBuilder.from_dataframe(work)
    gb.configure_default_column(editable=True, resizable=True, sortable=True,
                                cellStyle={'textAlign': 'center'},
                                headerClass='jict-centered-header')
    for i, col in enumerate(work.columns):
        left = i == 0
        gb.configure_column(col, headerName=index_name if col == index_field else str(col),
                            editable=(col != index_field and col not in disabled),
                            cellStyle={'textAlign': 'left' if left else 'center'},
                            headerClass='jict-left-header' if left else 'jict-centered-header')
    if dynamic:
        gb.configure_grid_options(rowSelection='multiple', suppressRowClickSelection=True)
    gb.configure_grid_options(stopEditingWhenCellsLoseFocus=True,
                              ensureDomOrder=True, singleClickEdit=True)
    opts = gb.build()
    if dynamic:
        opts['sideBar'] = False
    _st.markdown('''<style>
    .ag-header-cell-label {justify-content:center!important}
    .ag-header-cell.jict-left-header .ag-header-cell-label {justify-content:flex-start!important}
    .ag-cell {text-align:center}
    </style>''', unsafe_allow_html=True)
    if dynamic:
        _st.caption('Edit cells directly. Use Add Row or select rows and Delete Selected Rows. Click the existing Save button to persist.')
    result = AgGrid(work, gridOptions=opts, key=key,
                    height=kwargs.get('height', min(480, max(190, 38*(len(work)+2)))),
                    fit_columns_on_grid_load=False,
                    update_mode=GridUpdateMode.VALUE_CHANGED | GridUpdateMode.SELECTION_CHANGED,
                    data_return_mode=DataReturnMode.AS_INPUT,
                    allow_unsafe_jscode=False, theme='streamlit',
                    reload_data=False)
    edited = pd.DataFrame(result['data']).reindex(columns=work.columns)
    _st.session_state[f'{key}_pending'] = edited.to_dict('records')
    if dynamic:
        c1, c2 = _st.columns(2)
        if c1.button('＋ Add Row', key=f'{key}_add'):
            new = {c: None for c in work.columns}
            edited = pd.concat([edited, pd.DataFrame([new])], ignore_index=True)
            _st.session_state[f'{key}_pending'] = edited.to_dict('records')
            _st.rerun()
        if c2.button('− Delete Selected Rows', key=f'{key}_delete'):
            selected = result.get('selected_rows')
            if isinstance(selected, pd.DataFrame):
                selected = selected.to_dict('records')
            selected = selected or []
            if selected:
                # Row identity is based on full-row matching (works without an ID column).
                for row in selected:
                    matches = edited.fillna('').eq(pd.Series(row).reindex(edited.columns).fillna('')).all(axis=1)
                    if matches.any():
                        edited = edited.drop(index=matches[matches].index[0])
                edited = edited.reset_index(drop=True)
                _st.session_state[f'{key}_pending'] = edited.to_dict('records')
                _st.rerun()
    if not hide_index:
        if index_field in edited:
            edited.index = edited[index_field].astype(str)
        else:
            edited.index = original.index[:len(edited)] if len(edited) <= len(original) else range(len(edited))
        edited = edited.drop(columns=[index_field])
        edited.index.name = original.index.name
    for col in original.select_dtypes(include='number').columns:
        if col in edited.columns:
            edited[col] = pd.to_numeric(edited[col], errors='coerce')
    return edited
