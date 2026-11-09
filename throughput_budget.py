"""Throughput vs Budget 25/26 dashboard; data persisted in Supabase."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
SERIES = ['2025 (Actual)', 'Budget 2026', '2026 (Forecast)']
COLORS = {'2025 (Actual)':'#64748b','Budget 2026':'#0d9488','2026 (Forecast)':'#e09b35'}
DEFAULTS = {
 '2025 (Actual)': [189446,157496,160755,170987,194507,182499,190837,188937,173789,175996,197238,209818],
 'Budget 2026': [188926,173579,175511,174163,186807,187541,192604,194052,190916,192188,191149,193565],
 '2026 (Forecast)': [180106,175994,180037,180607,187996,190789,195838,195908,199437,212729,194816,194481],
}
# Totals exactly as supplied, despite 1-TEU discrepancies in two rows.
DEFAULT_TOTALS = {'2025 (Actual)':2192305,'Budget 2026':2241000,'2026 (Forecast)':2288737}

def load_data(sb):
    try:
        records = sb.table('throughput_budget_2526').select('series,month,value').execute().data or []
    except Exception as exc:
        st.warning('Could not read throughput budget data. Run throughput_budget_schema.sql in Supabase before saving. Details: '+str(exc))
        records = []
    data = {k:list(v) for k,v in DEFAULTS.items()}
    totals = DEFAULT_TOTALS.copy()
    for rec in records:
        series, month, val = rec['series'], int(rec['month']), int(rec['value'])
        if series in data and 1 <= month <= 12: data[series][month-1] = val
        elif series in data and month == 13: totals[series] = val
    return data, totals

def render(sb):
    st.header('Throughput vs Budget 25/26')
    st.caption('Clustered column chart with data table and legend keys · TEUs')
    data, totals = load_data(sb)
    df = pd.DataFrame(data, index=MONTHS).T
    totals_df = df.copy()
    totals_df['Total'] = [totals[s] for s in SERIES]
    actual, budget, forecast = (totals_df.loc[s].astype(float) for s in SERIES)
    changes = pd.DataFrame(index=MONTHS+['Total'])
    changes['Change (%) 2025 vs 2026'] = ((forecast/actual)-1)*100
    changes['Change (%) 2026 vs Budget'] = ((forecast/budget)-1)*100
    fig = go.Figure()
    for s in SERIES:
        fig.add_bar(name=s,x=MONTHS,y=df.loc[s].tolist(),marker_color=COLORS[s],hovertemplate='%{x}: %{y:,.0f} TEUs<extra>'+s+'</extra>')
    fig.update_layout(barmode='group',height=470,margin=dict(l=10,r=10,t=25,b=10),yaxis_title='TEUs',xaxis_title=None,legend=dict(orientation='h',y=-0.12,x=0),hovermode='x unified')
    fig.update_yaxes(tickformat=',d',rangemode='tozero',gridcolor='rgba(128,128,128,.15)')
    st.plotly_chart(fig,use_container_width=True)
    st.subheader('Data Table (With Legend Keys)')
    # Render as HTML so series swatches remain visible, matching Excel legend keys.
    import html
    headers = ''.join(f'<th>{m}</th>' for m in MONTHS+['Total'])
    rows = []
    for s in SERIES:
        key = f'<span style="display:inline-block;width:10px;height:10px;background:{COLORS[s]};margin-right:7px;border-radius:2px"></span>'
        vals = ''.join(f'<td>{int(v):,}</td>' for v in totals_df.loc[s])
        rows.append(f'<tr><th style="text-align:left;white-space:nowrap">{key}{html.escape(s)}</th>{vals}</tr>')
    for label in changes.columns:
        vals = ''.join(f'<td>{v:+.2f}%</td>' for v in changes[label])
        rows.append(f'<tr><th style="text-align:left;white-space:nowrap">{html.escape(label)}</th>{vals}</tr>')
    st.markdown('<div style="overflow-x:auto"><table style="width:100%;font-size:12px"><thead><tr><th>Series</th>'+headers+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>',unsafe_allow_html=True)
    st.caption('Percent changes are calculated from the current values. Total column uses the supplied total values, which differ by 1 TEU from monthly sums for Budget 2026 and Forecast 2026.')
    with st.expander('✏️ Input / Edit Data',expanded=False):
        st.caption('Edit monthly TEUs and the supplied Total. Save to Supabase to share updates with your team.')
        editor = st.data_editor(totals_df, key='budget_editor', use_container_width=True, num_rows='fixed', column_config={m:st.column_config.NumberColumn(m,min_value=0,step=1,format='%d') for m in MONTHS+['Total']})
editor = editor.fillna(totals_df)
        if st.button('Save Throughput vs Budget',type='primary'):
            try:
                records=[]
                for s in SERIES:
                    for i,m in enumerate(MONTHS,1):
                        records.append({'series':s,'month':i,'value':int(editor.at[s,m])})
                    records.append({'series':s,'month':13,'value':int(editor.at[s,'Total'])})
                sb.table('throughput_budget_2526').upsert(records,on_conflict='series,month').execute()
                st.success('Saved successfully.')
                st.rerun()
            except Exception as exc:
                st.error('Could not save. Ensure the SQL migration has been applied. '+str(exc))
        if st.button('Recalculate Totals from Months'):
            st.info('Monthly sums: '+', '.join(f'{s}: {int(editor.loc[s,MONTHS].sum()):,}' for s in SERIES)+'. Update the Total cells if you want to use these calculated values.')
