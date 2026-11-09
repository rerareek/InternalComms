"""Throughput vs Budget 25/26 dashboard; data persisted in Supabase."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
SERIES = ['2025 (Actual)', 'Budget 2026', '2026 (Forecast)']
COLORS = {'2025 (Actual)':'#C61B31','Budget 2026':'#AFD1C2','2026 (Forecast)':'#ADC4BC'}
def load_data(sb):
    try:
        records = sb.table('throughput_budget_2526').select('series,month,value').execute().data or []
    except Exception as exc:
        st.error('Could not read throughput budget data: ' + str(exc))
        st.stop()
    data = pd.DataFrame(index=SERIES, columns=MONTHS + ['Total'], dtype=float)
    for rec in records:
        series, month = rec.get('series'), rec.get('month')
        if series in SERIES and month is not None and 1 <= int(month) <= 13:
            column = MONTHS[int(month)-1] if int(month) <= 12 else 'Total'
            data.at[series, column] = rec.get('value')
    return data

def render(sb):
    st.header('Throughput vs Budget 25/26')
    st.caption('Clustered column chart with data table and legend keys · TEUs')
    totals_df = load_data(sb)
    df = totals_df[MONTHS]
    has_saved_data = totals_df.notna().any().any()
    actual, budget, forecast = (totals_df.loc[s].astype(float) for s in SERIES)
    changes = pd.DataFrame(index=MONTHS + ['Total'])
    changes['Change (%) 2025 vs 2026'] = ((forecast / actual.replace(0, float('nan'))) - 1) * 100
    changes['Change (%) 2026 vs Budget'] = ((forecast / budget.replace(0, float('nan'))) - 1) * 100
    fig = go.Figure()
    for s in SERIES:
        fig.add_bar(name=s,x=MONTHS,y=df.loc[s].tolist(),marker_color=COLORS[s],hovertemplate='%{x}: %{y:,.0f} TEUs<extra>'+s+'</extra>')
    fig.update_layout(barmode='group',height=470,margin=dict(l=10,r=10,t=25,b=10),yaxis_title='TEUs',xaxis_title=None,legend=dict(orientation='h',y=-0.12,x=0),hovermode='x unified')
    fig.update_yaxes(tickformat=',d',rangemode='tozero',gridcolor='rgba(128,128,128,.15)')
    if has_saved_data:
        st.plotly_chart(fig,use_container_width=True)
    else:
        st.info('Belum ada data. Isi Input / Edit Data lalu klik Save.')
    st.subheader('Data Table (With Legend Keys)')
    # Render as HTML so series swatches remain visible, matching Excel legend keys.
    import html
    headers = ''.join(f'<th>{m}</th>' for m in MONTHS+['Total'])
    rows = []
    for s in SERIES:
        key = f'<span style="display:inline-block;width:10px;height:10px;background:{COLORS[s]};margin-right:7px;border-radius:2px"></span>'
        vals = ''.join(f'<td>{int(v):,}</td>' if pd.notna(v) else '<td>—</td>' for v in totals_df.loc[s])
        rows.append(f'<tr><th style="text-align:left;white-space:nowrap">{key}{html.escape(s)}</th>{vals}</tr>')
    for label in changes.columns:
        vals = ''.join(f'<td>{v:+.2f}%</td>' if pd.notna(v) else '<td>—</td>' for v in changes[label])
        rows.append(f'<tr><th style="text-align:left;white-space:nowrap">{html.escape(label)}</th>{vals}</tr>')
    if has_saved_data:
        st.markdown('<div style="overflow-x:auto"><table style="width:100%;font-size:12px"><thead><tr><th>Series</th>'+headers+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>',unsafe_allow_html=True)
    st.caption('Change (%) dihitung otomatis dari angka yang tersimpan.')
    with st.expander('✏️ Input / Edit Data',expanded=False):
        st.caption('Edit monthly TEUs and the supplied Total. Save to Supabase to share updates with your team.')
        editor = st.data_editor(totals_df, key='budget_editor',use_container_width=True,num_rows='fixed',column_config={m:st.column_config.NumberColumn(m,min_value=0,step=1,format='%d') for m in MONTHS+['Total']})
        if st.button('Save Throughput vs Budget',type='primary'):
            try:
                records=[]
                for s in SERIES:
                    for i,m in enumerate(MONTHS,1):
                        value = editor.at[s,m]
                        if pd.notna(value):
                            records.append({'series':s,'month':i,'value':int(value)})
                    value = editor.at[s,'Total']
                    if pd.notna(value):
                        records.append({'series':s,'month':13,'value':int(value)})
                if not records:
                    st.warning('Isi minimal satu angka sebelum Save.')
                    st.stop()
                sb.table('throughput_budget_2526').delete().neq('month', 0).execute()
                sb.table('throughput_budget_2526').upsert(records,on_conflict='series,month').execute()
                st.success('Saved successfully.')
                st.rerun()
            except Exception as exc:
                st.error('Could not save. Ensure the SQL migration has been applied. '+str(exc))
        if st.button('Recalculate Totals from Months'):
            st.info('Monthly sums: '+', '.join(f'{s}: {int(editor.loc[s,MONTHS].sum()):,}' for s in SERIES)+'. Update the Total cells if you want to use these calculated values.')
