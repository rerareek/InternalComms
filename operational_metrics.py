"""JICT operational performance: Dwelling, Productivity GCR & VOR, Divert."""
import pandas as pd
import streamlit as st
import altair as alt

MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
METRICS = {'Dwelling':['Import Full','Export Full','Overall'], 'Productivity GCR & VOR':['Gross QC Rate','Vess. Op. Rate']}
TABLE_METRICS = 'operational_monthly_metrics'
TABLE_DIVERT = 'operational_divert'


def _client(sb):
    return sb


def _load(sb, table, year):
    result = sb.table(table).select('*').eq('year',year).execute()
    return pd.DataFrame(result.data or [])


def _number(v):
    if pd.isna(v) or str(v).strip() == '':
        return None
    if isinstance(v,str):
        v=v.strip().replace(',','')
    return float(v)


def _monthly_chart(data, title, kind='line'):
    """Plot months in calendar order, never alphabetical order."""
    if data.empty:
        st.info('No data available for this chart.')
        return
    base = alt.Chart(data).encode(
        x=alt.X('Month:N', sort=MONTHS, title='Month'),
        y=alt.Y('Value:Q', title=title),
        color=alt.Color('Series:N', title='Metric'),
        tooltip=[alt.Tooltip('Month:N'), alt.Tooltip('Series:N'), alt.Tooltip('Value:Q', format=',.2f')],
    )
    chart = base.mark_line(point=True) if kind == 'line' else base.mark_bar()
    st.altair_chart(chart, use_container_width=True)


def _overview(sb, year):
    st.subheader('Operational Performance — Executive Dashboard')
    st.caption(f'Monthly operational trends for {year}. Months always run January through December. Blank months are excluded from YTD averages.')
    metrics = _load(sb, TABLE_METRICS, year)
    divert = _load(sb, TABLE_DIVERT, year)
    if not metrics.empty:
        metrics = metrics.copy()
        metrics['month'] = pd.to_numeric(metrics['month'], errors='coerce')
        metrics['value'] = pd.to_numeric(metrics['value'], errors='coerce')
    if not divert.empty:
        divert = divert.copy()
        divert['month'] = pd.to_numeric(divert['month'], errors='coerce')
        for col in ('to_koja', 'from_koja'):
            divert[col] = pd.to_numeric(divert[col], errors='coerce')

    st.markdown('#### Dwelling')
    d = metrics[metrics['category'] == 'Dwelling'] if not metrics.empty else pd.DataFrame()
    if not d.empty:
        cols = st.columns(3)
        for i, name in enumerate(METRICS['Dwelling']):
            v = d.loc[d['metric'] == name, 'value'].dropna()
            cols[i].metric(f'{name} · Average YTD', f'{v.mean():,.2f}' if not v.empty else '—')
        plot = d[d['metric'].isin(METRICS['Dwelling'])].dropna(subset=['month','value']).copy()
        plot['Month'] = plot['month'].astype(int).map(dict(enumerate(MONTHS, 1)))
        plot = plot.rename(columns={'metric':'Series','value':'Value'})
        _monthly_chart(plot[['Month','Series','Value']], 'Dwelling (days)')
    else:
        st.info('No Dwelling data for the selected year.')

    st.markdown('#### Productivity GCR & VOR')
    prod = metrics[metrics['category'] == 'Productivity GCR & VOR'] if not metrics.empty else pd.DataFrame()
    if not prod.empty:
        cols = st.columns(2)
        for i, name in enumerate(METRICS['Productivity GCR & VOR']):
            v = prod.loc[prod['metric'] == name, 'value'].dropna()
            cols[i].metric(f'{name} · Average YTD', f'{v.mean():,.2f}' if not v.empty else '—')
        plot = prod[prod['metric'].isin(METRICS['Productivity GCR & VOR'])].dropna(subset=['month','value']).copy()
        plot['Month'] = plot['month'].astype(int).map(dict(enumerate(MONTHS, 1)))
        plot = plot.rename(columns={'metric':'Series','value':'Value'})
        _monthly_chart(plot[['Month','Series','Value']], 'Productivity rate')
    else:
        st.info('No Productivity data for the selected year.')

    st.markdown('#### Divert — To Koja vs From Koja')
    if not divert.empty:
        to_total = divert['to_koja'].sum()
        from_total = divert['from_koja'].sum()
        c1,c2,c3 = st.columns(3)
        c1.metric('To Koja · YTD', f'{to_total:,.2f}')
        c2.metric('From Koja · YTD', f'{from_total:,.2f}')
        c3.metric('Total Divert · YTD', f'{to_total+from_total:,.2f}')
        monthly = divert.groupby('month', as_index=False)[['to_koja','from_koja']].sum()
        monthly['Month'] = monthly['month'].astype(int).map(dict(enumerate(MONTHS,1)))
        plot = monthly.melt(id_vars='Month',value_vars=['to_koja','from_koja'],var_name='Series',value_name='Value')
        plot['Series'] = plot['Series'].map({'to_koja':'To Koja','from_koja':'From Koja'})
        _monthly_chart(plot[['Month','Series','Value']], 'Divert volume', kind='bar')
    else:
        st.info('No Divert data for the selected year.')


def _metric_page(sb, kind, year):
    st.caption('Monthly values are stored with decimal precision. Average YTD excludes months without data.')
    df=_load(sb,TABLE_METRICS,year)
    if not df.empty:
        df=df[df['category']==kind]
    records=[]
    for name in METRICS[kind]:
        row={'Metric':name}
        for i,m in enumerate(MONTHS,1):
            hit=df[(df['metric']==name)&(df['month']==i)] if not df.empty else pd.DataFrame()
            row[m]=float(hit.iloc[0]['value']) if not hit.empty and pd.notna(hit.iloc[0]['value']) else None
        records.append(row)
    wide=pd.DataFrame(records)
    average=wide[MONTHS].mean(axis=1,skipna=True)
    display=wide.copy()
    display['Average YTD']=average
    dash,inp=st.tabs(['Dashboard','Input Data'])
    with dash:
        st.subheader(kind)
        st.dataframe(display,hide_index=True,use_container_width=True,column_config={**{m:st.column_config.NumberColumn(m,format='%.2f') for m in MONTHS},'Average YTD':st.column_config.NumberColumn('Average YTD',format='%.2f')})
        chart=wide.melt(id_vars='Metric',value_vars=MONTHS,var_name='Month',value_name='Value').dropna(subset=['Value'])
        _monthly_chart(chart.rename(columns={'Metric':'Series'}), 'Dwelling (days)' if kind == 'Dwelling' else 'Productivity rate')
        st.info('Average YTD is the arithmetic mean of available monthly values; it is not weighted by container volume or vessel calls.')
    with inp:
        st.write('Edit monthly values; leave future months blank. Average YTD is calculated automatically.')
        edited=st.data_editor(wide,hide_index=True,use_container_width=True,key=f'operational_editor_{kind}_{year}',disabled=['Metric'],column_config={m:st.column_config.NumberColumn(m,format='%.2f',step=0.01) for m in MONTHS})
        if st.button('Save Data',key=f'operational_save_{kind}_{year}',type='primary'):
            payload=[]
            for _,r in edited.iterrows():
                for i,m in enumerate(MONTHS,1):
                    payload.append({'year':year,'category':kind,'metric':r['Metric'],'month':i,'value':_number(r[m])})
            try:
                sb.table(TABLE_METRICS).upsert(payload,on_conflict='year,category,metric,month').execute()
                st.success('Saved to Supabase.'); st.rerun()
            except Exception as e:
                st.error(f'Save failed: {e}')
        with st.expander('Delete monthly data'):
            metric=st.selectbox('Metric',METRICS[kind],key=f'delmetric_{kind}_{year}')
            month=st.selectbox('Month',MONTHS,key=f'delmonth_{kind}_{year}')
            confirm=st.checkbox('Confirm permanent deletion',key=f'delconfirm_{kind}_{year}')
            if st.button('Delete selected month',disabled=not confirm,key=f'delbutton_{kind}_{year}'):
                sb.table(TABLE_METRICS).delete().eq('year',year).eq('category',kind).eq('metric',metric).eq('month',MONTHS.index(month)+1).execute()
                st.success('Deleted'); st.rerun()


def _divert_page(sb,year):
    df=_load(sb,TABLE_DIVERT,year)
    lines=sorted(set(df['shipping_line'].dropna().astype(str))) if not df.empty else []
    if not lines: lines=['CMA','COSCO','HAS','KMTC','NSS','ONE','SINOKOR','TS LINE']
    rows=[]
    for line in lines:
        row={'Shipping Line':line}
        for i,m in enumerate(MONTHS,1):
            hit=df[(df['shipping_line']==line)&(df['month']==i)] if not df.empty else pd.DataFrame()
            for col,field in [('To Koja','to_koja'),('From Koja','from_koja')]:
                row[f'{m} {col}']=float(hit.iloc[0][field]) if not hit.empty and pd.notna(hit.iloc[0][field]) else None
        rows.append(row)
    wide=pd.DataFrame(rows)
    tocols=[f'{m} To Koja' for m in MONTHS]; fromcols=[f'{m} From Koja' for m in MONTHS]
    totals=wide[['Shipping Line']].copy()
    totals['To Koja']=wide[tocols].sum(axis=1,min_count=1).fillna(0)
    totals['From Koja']=wide[fromcols].sum(axis=1,min_count=1).fillna(0)
    totals['Total Divert']=totals['To Koja']+totals['From Koja']
    dash,inp=st.tabs(['Dashboard','Input Data'])
    with dash:
        st.subheader('Divert — To Koja / From Koja')
        a,b,c=st.columns(3)
        a.metric('To Koja',f"{totals['To Koja'].sum():,.2f}")
        b.metric('From Koja',f"{totals['From Koja'].sum():,.2f}")
        c.metric('Total Divert',f"{totals['Total Divert'].sum():,.2f}")
        st.dataframe(totals,hide_index=True,use_container_width=True)
        st.bar_chart(totals.set_index('Shipping Line')[['To Koja','From Koja']],use_container_width=True)
        monthly=pd.DataFrame({'Month':MONTHS,'To Koja':[wide[c].sum() for c in tocols],'From Koja':[wide[c].sum() for c in fromcols]}).set_index('Month')
        st.subheader('Monthly Divert')
        monthly_plot=monthly.reset_index().melt(id_vars='Month',var_name='Series',value_name='Value')
        _monthly_chart(monthly_plot, 'Divert volume', kind='bar')
        with st.expander('Full Year Detail'):
            st.dataframe(wide,hide_index=True,use_container_width=True)
    with inp:
        st.caption('One row per shipping line. Blank months remain blank; totals are calculated automatically.')
        edited=st.data_editor(wide,hide_index=True,num_rows='dynamic',use_container_width=True,key=f'divert_editor_{year}',column_config={c:st.column_config.NumberColumn(c,format='%.2f',step=0.01) for c in tocols+fromcols})
        if st.button('Save Divert Data',type='primary',key=f'divert_save_{year}'):
            payload=[]
            for _,r in edited.iterrows():
                name=str(r.get('Shipping Line') or '').strip().upper()
                if not name or name=='NAN':continue
                for i,m in enumerate(MONTHS,1):
                    payload.append({'year':year,'shipping_line':name,'month':i,'to_koja':_number(r[f'{m} To Koja']),'from_koja':_number(r[f'{m} From Koja'])})
            try:
                if payload:sb.table(TABLE_DIVERT).upsert(payload,on_conflict='year,shipping_line,month').execute()
                st.success('Saved to Supabase.');st.rerun()
            except Exception as e:st.error(f'Save failed: {e}')
        with st.expander('Delete shipping line'):
            line=st.selectbox('Shipping line',lines,key=f'divert_del_line_{year}')
            confirmed=st.checkbox('Confirm permanent deletion for selected year',key=f'divert_del_confirm_{year}')
            if st.button('Delete Shipping Line',disabled=not confirmed,key=f'divert_del_btn_{year}'):
                sb.table(TABLE_DIVERT).delete().eq('year',year).eq('shipping_line',line).execute()
                st.success('Deleted');st.rerun()


def render(sb):
    st.title('Operational Performance')
    year=st.selectbox('Reporting Year',list(range(2024,2031)),index=2,key='operational_year')
    overview_tab,a,b,c=st.tabs(['Dashboard','Dwelling','Productivity GCR & VOR','Divert'])
    with overview_tab:_overview(sb,year)
    with a:_metric_page(sb,'Dwelling',year)
    with b:_metric_page(sb,'Productivity GCR & VOR',year)
    with c:_divert_page(sb,year)
