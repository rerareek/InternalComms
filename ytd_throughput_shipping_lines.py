"""YTD Throughput by Shipping Lines — independent CRM menu."""
import io
import pandas as pd
import plotly.express as px
import streamlit as st

TABLE = 'ytd_shipping_lines'
OFFICIAL = 'ytd_shipping_official_totals'
CATEGORIES = ('Full / Empty', 'Export / Import')
MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December']
INPUTS = ['2026 Full','2026 Empty','2025 Full','2025 Empty','2026 Export','2026 Import','2025 Export','2025 Import']
DB_COLS = ['full_2026','empty_2026','full_2025','empty_2025','export_2026','import_2026','export_2025','import_2025']


def _fetch(sb, table, year, month):
    try:
        result = (sb.table(table).select('*').eq('year', year).eq('month', month).execute())
        return result.data or []
    except Exception as exc:
        st.error(f'Could not load {table}: {exc}. Run the supplied SQL migration in Supabase.')
        st.stop()


def _number(value):
    if value is None or pd.isna(value):
        return None
    s = str(value).replace(',','').strip()
    if not s or s in ('-','—','–'):
        return None
    try:
        n = float(s)
    except ValueError:
        raise ValueError(f'Invalid numeric value: {value}')
    if n < 0 or n > 1e12:
        raise ValueError(f'Value must be between 0 and 1 trillion: {value}')
    return n


def _sum(data, field):
    return float(pd.to_numeric(data[field],errors='coerce').sum()) if field in data else 0.0


def _fmt(x):
    return f'{x:,.0f}'


def _ratio(num, den):
    return num / den if den else None


def _percent(num, den):
    x = _ratio(num,den)
    return f'{x:.1%}' if x is not None else '—'


def _prepare(rows, kind):
    cols = ['shipping_line'] + DB_COLS
    df = pd.DataFrame(rows, columns=cols)
    if df.empty:
        return pd.DataFrame(columns=['Shipping Line','2026 A','2026 B','2026 Total','2026 Contribution','2026 B %','2025 A','2025 B','2025 Total','2025 Contribution','2025 B %','Growth'])
    for c in DB_COLS:
        df[c] = pd.to_numeric(df[c],errors='coerce').fillna(0)
    if kind == CATEGORIES[0]:
        a,b,c,d = 'full_2026','empty_2026','full_2025','empty_2025'
    else:
        a,b,c,d = 'export_2026','import_2026','export_2025','import_2025'
    df['2026 Total'] = df[a]+df[b]
    df['2025 Total'] = df[c]+df[d]
    grand26 = df['2026 Total'].sum()
    grand25 = df['2025 Total'].sum()
    result = pd.DataFrame({
        'Shipping Line':df['shipping_line'], '2026 A':df[a], '2026 B':df[b],
        '2026 Total':df['2026 Total'],
        '2026 Contribution':df['2026 Total'].div(grand26).where(grand26!=0),
        '2026 B %':df[b].div(df['2026 Total'].replace(0,float('nan'))),
        '2025 A':df[c], '2025 B':df[d], '2025 Total':df['2025 Total'],
        '2025 Contribution':df['2025 Total'].div(grand25).where(grand25!=0),
        '2025 B %':df[d].div(df['2025 Total'].replace(0,float('nan'))),
        'Growth':(df['2026 Total']-df['2025 Total']).div(df['2025 Total'].replace(0,float('nan'))),
    })
    return result.sort_values('2026 Total',ascending=False).reset_index(drop=True)


def _display(df,kind):
    if df.empty:
        st.info('No shipping line data yet. Open Input Data to add it.')
        return
    a,b = ('Full','Empty') if kind == CATEGORIES[0] else ('Export','Import')
    names={'2026 A':f'2026 {a}','2026 B':f'2026 {b}','2026 B %':f'2026 {b} %',
           '2025 A':f'2025 {a}','2025 B':f'2025 {b}','2025 B %':f'2025 {b} %'}
    view=df.rename(columns=names)
    pct=['2026 Contribution',f'2026 {b} %','2025 Contribution',f'2025 {b} %','Growth']
    fmt={c:'{:,.0f}' for c in view.columns if c not in ['Shipping Line']+pct}
    fmt.update({c:'{:.1%}' for c in pct})
    st.dataframe(view.style.format(fmt,na_rep='—'),use_container_width=True,hide_index=True)
    csv=view.to_csv(index=False).encode('utf-8-sig')
    st.download_button('Download detailed CSV',csv,file_name=f'ytd_{kind.replace(" / ","_").lower()}.csv',mime='text/csv',key=f'ytd_dl_{kind}')


def _official_editor(sb, year, month, official):
    st.subheader('Official YTD Totals')
    st.caption('Official figures are stored separately from shipping line detail. Do not force detail values to match them.')
    fields=['2026 Full','2026 Empty','2025 Full','2025 Empty','2026 Export','2026 Import','2025 Export','2025 Import']
    record=official[0] if official else {}
    with st.form('ytd_official_form'):
        cols=st.columns(2)
        values={}
        for i,(label,db) in enumerate(zip(fields,DB_COLS)):
            with cols[i%2]:
                values[db]=st.number_input(label,min_value=0.0,value=float(record.get(db) or 0),step=1.0,format='%.2f',key=f'ytd_off_{db}')
        if st.form_submit_button('Save Official YTD Totals',type='primary'):
            try:
                sb.table(OFFICIAL).upsert({'year':year,'month':month,**values},on_conflict='year,month').execute()
                st.success('Official totals saved.')
                st.rerun()
            except Exception as exc:
                st.error(f'Save failed: {exc}')


def _editor(sb,year,month,rows):
    st.subheader('Shipping Line Spreadsheet Editor')
    st.caption('One row per shipping line. Full, Empty, Export, Import are entered; totals and percentages are calculated automatically.')
    frame=pd.DataFrame(rows)
    if frame.empty:
        frame=pd.DataFrame(columns=['shipping_line']+DB_COLS)
    frame=frame.reindex(columns=['shipping_line']+DB_COLS).rename(columns={'shipping_line':'Shipping Line',**dict(zip(DB_COLS,INPUTS))})
    edited=st.data_editor(frame,num_rows='dynamic',hide_index=True,use_container_width=True,key='ytd_detail_editor',column_config={'Shipping Line':st.column_config.TextColumn(required=True),**{c:st.column_config.NumberColumn(min_value=0,step=1,format='%.2f') for c in INPUTS}})
    if st.button('Save Shipping Line Data',type='primary',key='ytd_save_editor'):
        payload=[]; seen=set()
        try:
            for _,row in edited.iterrows():
                name=str(row['Shipping Line']).strip().upper() if pd.notna(row['Shipping Line']) else ''
                if not name: continue
                if name in seen: raise ValueError(f'Duplicate shipping line: {name}')
                seen.add(name)
                rec={'year':year,'month':month,'shipping_line':name}
                for label,db in zip(INPUTS,DB_COLS): rec[db]=_number(row[label])
                payload.append(rec)
            if not payload: st.warning('No rows to save.')
            else:
                for i in range(0,len(payload),200): sb.table(TABLE).upsert(payload[i:i+200],on_conflict='year,month,shipping_line').execute()
                st.success(f'Saved {len(payload)} shipping lines.'); st.rerun()
        except Exception as exc: st.error(f'Could not save: {exc}')
    st.caption('To remove existing shipping lines, use Delete Data below. Clearing a row in the editor does not delete its database record.')


def _bulk(sb,year,month):
    st.subheader('Bulk Paste from Excel')
    st.caption('Paste 9 tab-separated columns: Shipping Line, 2026 Full, 2026 Empty, 2025 Full, 2025 Empty, 2026 Export, 2026 Import, 2025 Export, 2025 Import. No totals or percentages.')
    paste=st.text_area('Paste Excel cells',height=140,key='ytd_bulk_text')
    if st.button('Import Pasted Data',key='ytd_bulk_import'):
        if not paste.strip(): st.warning('Paste some data first.'); return
        try:
            raw=pd.read_csv(io.StringIO(paste),sep='\t',header=None,dtype=str,keep_default_na=False)
            if raw.shape[1]!=9: raise ValueError(f'Expected 9 columns, found {raw.shape[1]}.')
            records=[]; seen=set()
            for vals in raw.itertuples(index=False,name=None):
                name=str(vals[0]).strip().upper()
                if name.lower() in ('shipping line','shipping_line',''): continue
                if name in seen: raise ValueError(f'Duplicate shipping line: {name}')
                seen.add(name)
                records.append({'year':year,'month':month,'shipping_line':name,**{db:_number(v) for db,v in zip(DB_COLS,vals[1:])}})
            if not records: raise ValueError('No data rows found.')
            sb.table(TABLE).upsert(records,on_conflict='year,month,shipping_line').execute()
            st.success(f'Imported {len(records)} shipping lines.'); st.rerun()
        except Exception as exc: st.error(f'Import failed: {exc}')


def _delete(sb,year,month,rows):
    st.subheader('Delete Data')
    if not rows: st.caption('No records to delete for this period.'); return
    names=sorted({r['shipping_line'] for r in rows})
    selected=st.selectbox('Shipping Line',names,key='ytd_delete_name')
    confirm=st.checkbox(f'Confirm delete {selected} for YTD {MONTHS[month-1]} {year}',key='ytd_delete_confirm')
    if st.button('Delete selected shipping line',disabled=not confirm,key='ytd_delete_button'):
        try:
            sb.table(TABLE).delete().eq('year',year).eq('month',month).eq('shipping_line',selected).execute()
            st.success('Record deleted.'); st.rerun()
        except Exception as exc: st.error(f'Delete failed: {exc}')


def _reconcile(rows, official):
    if not official:
        st.info('Official YTD totals not set yet. Add them in Input Data → Official Totals to activate reconciliation.')
        return
    df=pd.DataFrame(rows)
    off=official[0]
    checks=[]
    for db,label in zip(DB_COLS,INPUTS):
        detail=_sum(df,db)
        target=float(off.get(db) or 0)
        checks.append({'Metric':label,'Official':target,'Detail Sum':detail,'Variance':detail-target,'Status':'Matched' if abs(detail-target)<0.01 else 'Mismatch'})
    st.dataframe(pd.DataFrame(checks),hide_index=True,use_container_width=True,column_config={'Official':st.column_config.NumberColumn(format='%.2f'),'Detail Sum':st.column_config.NumberColumn(format='%.2f'),'Variance':st.column_config.NumberColumn(format='%+.2f')})
    if any(c['Status']=='Mismatch' for c in checks):
        st.warning('Detail totals differ from official figures. Check the source spreadsheet and missing/duplicate lines; no automatic adjustment was applied.')
    else: st.success('All 8 components match the official totals.')
    df=pd.DataFrame(rows)
    for year in (2026,2025):
        full=_sum(df,f'full_{year}'); empty=_sum(df,f'empty_{year}')
        exp=_sum(df,f'export_{year}'); imp=_sum(df,f'import_{year}')
        diff=(full+empty)-(exp+imp)
        if abs(diff)>0.01: st.warning(f'{year}: Full + Empty differs from Export + Import by {diff:+,.2f} TEUs.')


def render(sb):
    st.header('YTD Throughput by Shipping Lines')
    st.caption('Marketing Seaside · Year-to-date throughput comparison · TEUs')
    col1,col2=st.columns(2)
    with col1: year=int(st.number_input('Reporting year',2020,2100,2026,key='ytd_year'))
    with col2: month=int(st.selectbox('YTD through',range(1,13),index=9,format_func=lambda m:MONTHS[m-1],key='ytd_month'))
    rows=_fetch(sb,TABLE,year,month)
    official=_fetch(sb,OFFICIAL,year,month)
    dashboard,input_tab=st.tabs(['Dashboard','Input Data'])
    with dashboard:
        detail=pd.DataFrame(rows)
        f26=_sum(detail,'full_2026')+_sum(detail,'empty_2026')
        f25=_sum(detail,'full_2025')+_sum(detail,'empty_2025')
        if official:
            o=official[0]
            total26=float(o.get('full_2026') or 0)+float(o.get('empty_2026') or 0)
            total25=float(o.get('full_2025') or 0)+float(o.get('empty_2025') or 0)
            st.caption('KPI cards: Official YTD Totals. Detailed charts and tables: Shipping Line Data.')
        else:
            total26,total25=f26,f25
            st.caption('KPI cards currently use detail sums. Enter Official Totals to make official numbers authoritative.')
        a,b,c,d=st.columns(4)
        a.metric(f'YTD {year} Throughput',_fmt(total26)+' TEUs')
        b.metric(f'YTD {year-1} Throughput',_fmt(total25)+' TEUs')
        c.metric('YoY Growth',_percent(total26-total25,total25))
        d.metric('Volume Change',f'{total26-total25:+,.0f} TEUs')
        kind=st.segmented_control('Breakdown',CATEGORIES,default=CATEGORIES[0],key='ytd_breakdown')
        result=_prepare(rows,kind)
        if not result.empty:
            chart_data=result.head(10)[['Shipping Line','2026 Total','2025 Total']].melt(id_vars='Shipping Line',var_name='Year',value_name='TEUs')
            fig=px.bar(chart_data,x='Shipping Line',y='TEUs',color='Year',barmode='group',title='Top Shipping Lines — YTD Comparison',color_discrete_map={'2026 Total':'#3B82F6','2025 Total':'#94A3B8'})
            fig.update_layout(xaxis_tickangle=-30,legend_title_text='')
            st.plotly_chart(fig,use_container_width=True,key=f'ytd_chart_{kind}')
        _display(result,kind)
        st.subheader('Reconciliation & Data Quality')
        _reconcile(rows,official)
    with input_tab:
        off_tab,detail_tab,bulk_tab,delete_tab=st.tabs(['Official Totals','Spreadsheet Editor','Bulk Paste','Delete Data'])
        with off_tab: _official_editor(sb,year,month,official)
        with detail_tab: _editor(sb,year,month,rows)
        with bulk_tab: _bulk(sb,year,month)
        with delete_tab: _delete(sb,year,month,rows)
