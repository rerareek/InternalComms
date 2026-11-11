"""Throughput & Compare Shipping Line | JICT CRM."""
import io
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

TABLE = 'throughput_shipping_compare'
OFFICIAL_TABLE = 'throughput_shipping_official_kpi'
MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
FIELDS = ['Call','Forecast 2026','Budget 2026','Actual 2025']
SERIES = ['Actual 2025','Forecast 2026','Budget 2026']
COLORS = {'Actual 2025':'#94A3B8','Forecast 2026':'#3B82F6','Budget 2026':'#F59E0B'}


def load(sb, year):
    rows=[]; offset=0
    try:
        while True:
            chunk=(sb.table(TABLE).select('shipping_line,month,calls,forecast,budget,actual').eq('year',year)
                   .range(offset,offset+999).execute().data or [])
            rows.extend(chunk)
            if len(chunk)<1000: break
            offset+=1000
    except Exception as exc:
        st.error(f'Gagal membaca tabel {TABLE}: {exc}. Jalankan file SQL migration terlebih dahulu.')
        st.stop()
    return pd.DataFrame(rows,columns=['shipping_line','month','calls','forecast','budget','actual'])


def num(v):
    if v is None or pd.isna(v) or str(v).strip() in ('','-','—','–'): return None
    try:
        f=float(str(v).strip().replace(',','').replace(' ',''))
    except (ValueError,TypeError): raise ValueError(f'Angka tidak valid: {v}')
    if not 0 <= f < 1e13: raise ValueError(f'Angka di luar rentang: {v}')
    return f


def wide_data(df):
    names=list(dict.fromkeys(df['shipping_line'].tolist())) if not df.empty else []
    cols=[f'{m} · {field}' for m in MONTHS for field in FIELDS]
    result=pd.DataFrame(index=names,columns=cols,dtype=float)
    for r in df.to_dict('records'):
        month=int(r['month'])
        if not 1<=month<=12: continue
        name=r['shipping_line']
        for field,db in zip(FIELDS,['calls','forecast','budget','actual']):
            result.at[name,f'{MONTHS[month-1]} · {field}']=r[db]
    result.index.name='Shipping Line'
    return result


def summary(df):
    if df.empty:
        return pd.DataFrame(columns=['Call','Forecast 2026','Budget 2026','Actual 2025','Vs Budget','YoY Growth','Volume Change'])
    data=df.copy()
    for c in ['calls','forecast','budget','actual']:
        data[c]=pd.to_numeric(data[c],errors='coerce')
    grouped=data.groupby('shipping_line',sort=False)[['calls','forecast','budget','actual']].sum(min_count=1)
    grouped.columns=['Call','Forecast 2026','Budget 2026','Actual 2025']
    grouped['Vs Budget']=(grouped['Forecast 2026']-grouped['Budget 2026'])/grouped['Budget 2026'].replace(0,float('nan'))
    grouped['YoY Growth']=(grouped['Forecast 2026']-grouped['Actual 2025'])/grouped['Actual 2025'].replace(0,float('nan'))
    grouped['Volume Change']=grouped['Forecast 2026']-grouped['Actual 2025']
    return grouped


def official_load(sb, year):
    try:
        rows=(sb.table(OFFICIAL_TABLE).select('*').eq('year',year).order('month').execute().data or [])
    except Exception as exc:
        st.error(f'Gagal membaca Official KPI: {exc}. Jalankan SQL migration baru di Supabase.')
        st.stop()
    return pd.DataFrame(rows)


def official_row(official, month):
    if official.empty: return None
    rows=official[official['month']==month]
    return rows.iloc[0] if not rows.empty else None


def pct(numerator, denominator):
    return numerator / denominator if pd.notna(denominator) and denominator != 0 else None


def totals_for_period(df, month=None):
    selected=df if month is None else df[df['month']==month]
    totals=selected[['forecast','budget','actual']].apply(pd.to_numeric,errors='coerce').sum() if not selected.empty else pd.Series({'forecast':0.,'budget':0.,'actual':0.})
    return totals


def reconciliation(df,official,year, *, widget_key="reconciliation"):
    st.subheader('Data Reconciliation')
    st.caption('Variance = Shipping Line Detail − Official KPI. Selisih tidak di-adjust otomatis.')
    monthly=official[official['month']>0] if not official.empty else pd.DataFrame()
    if monthly.empty:
        st.info('Official Monthly KPI belum tersedia. Rekonsiliasi bulanan memerlukan input Official KPI per bulan.')
    periods=[('Full Year',0)]+[(m,i) for i,m in enumerate(MONTHS,1)]
    rows=[]
    for label,month in periods:
        off=official_row(official,month)
        if off is None: continue
        totals=totals_for_period(df,month or None)
        for title,field in [('Actual 2025','actual'),('Forecast 2026','forecast'),('Budget 2026','budget')]:
            official_value=off[field]
            detail=float(totals[field])
            variance=detail-float(official_value) if pd.notna(official_value) else None
            rows.append({'Period':label,'Metric':title,'Official KPI':official_value,'Shipping Line Detail':detail,'Variance':variance,'Status':'Matched' if variance is not None and abs(variance)<0.005 else 'Mismatch' if variance is not None else 'No official value'})
    if rows:
        out=pd.DataFrame(rows)
        st.dataframe(out.style.format({'Official KPI':'{:,.2f}','Shipping Line Detail':'{:,.2f}','Variance':'{:+,.2f}'},na_rep='—').apply(lambda row:['background-color:#FFF4E6' if row['Status']=='Mismatch' else 'background-color:#EAF7F1' if row['Status']=='Matched' else '' for _ in row],axis=1),use_container_width=True,hide_index=True)
        st.download_button('Download Reconciliation CSV',out.to_csv(index=False).encode('utf-8-sig'),file_name=f'reconciliation_{year}.csv',mime='text/csv',key=f'{widget_key}_download_{year}')
    else:
        st.warning('Belum ada Official KPI untuk direkonsiliasi.')


def dashboard(df,official,year):
    st.subheader('Shipping Line Performance')
    period=st.selectbox('Period', ['Full Year']+MONTHS, key='shipping_period')
    month=0 if period=='Full Year' else MONTHS.index(period)+1
    selected=df if month==0 else df[df.month==month]
    off=official_row(official,month)
    if off is None:
        st.warning(f'Official KPI untuk {period} {year} belum diinput. KPI cards tidak menggunakan angka detail sebagai pengganti.')
    else:
        actual,forecast,budget=[float(off[f]) if pd.notna(off[f]) else None for f in ('actual','forecast','budget')]
        yoy=pct(forecast-actual,actual) if forecast is not None and actual is not None else None
        vs=pct(forecast-budget,budget) if forecast is not None and budget is not None else None
        change=forecast-actual if forecast is not None and actual is not None else None
        values=[actual,forecast,budget,yoy,vs,change]
        titles=['Actual 2025','Forecast 2026','Budget 2026','YoY Growth','Vs Budget','Volume Change']
        for start in (0,3):
            columns=st.columns(3)
            for i,col in enumerate(columns,start):
                val=values[i]
                display=('N/A' if val is None or pd.isna(val) else f'{val:+.2%}' if i in (3,4) else f'{val:+,.0f}' if i==5 else f'{val:,.0f}')
                col.metric(titles[i],display)
        st.caption(f"Source: Official KPI · {off['status']} · {period} {year}")
    st.divider()
    st.subheader('Monthly Throughput Volume (TEUs)')
    if not df.empty:
        monthly=df.groupby('month')[['actual','forecast','budget']].sum().reindex(range(1,13))
    else:
        monthly=pd.DataFrame(index=range(1,13),columns=['actual','forecast','budget'],dtype=float)
    monthly_off=official[official['month']>0].set_index('month') if not official.empty else pd.DataFrame()
    chart_source=st.radio('Chart data source',['Shipping Line Detail','Official Monthly KPI'],horizontal=True,key='shipping_chart_source')
    if chart_source=='Official Monthly KPI':
        if monthly_off.empty:
            st.info('Input Official Monthly KPI untuk menampilkan chart bulanan resmi.')
        else:
            monthly=monthly_off.reindex(range(1,13))
    if chart_source=='Shipping Line Detail' or not monthly_off.empty:
        fig=go.Figure()
        for name,field in [('Actual 2025','actual'),('Forecast 2026','forecast'),('Budget 2026','budget')]:
            fig.add_trace(go.Scatter(x=MONTHS,y=monthly[field],name=name,mode='lines+markers',line=dict(color=COLORS[name],width=2.5),hovertemplate='%{x}: %{y:,.2f} TEUs<extra>'+name+'</extra>'))
        fig.update_layout(height=400,hovermode='x unified',legend=dict(orientation='h',y=-.22),margin=dict(l=10,r=10,t=10,b=20),yaxis_title='TEUs')
        fig.update_yaxes(tickformat=',.0f',gridcolor='rgba(128,128,128,.15)')
        st.plotly_chart(fig,use_container_width=True)
    st.subheader('Top Shipping Lines · Detail Input')
    if df.empty:
        st.info('Belum ada shipping line detail untuk tahun ini.')
    else:
        sm=summary(selected)
        metric=st.selectbox('Ranking based on',SERIES,index=1)
        max_n=len(sm)
        top_n=st.selectbox('Number of shipping lines',sorted(set([min(5,max_n),min(10,max_n),min(20,max_n),max_n])),index=0)
        chart=sm.sort_values(metric,ascending=False).head(top_n)
        fig2=go.Figure()
        for name in ['Forecast 2026','Budget 2026','Actual 2025']:
            fig2.add_bar(x=chart.index.tolist(),y=chart[name],name=name,marker_color=COLORS[name],hovertemplate='%{x}<br>%{y:,.2f} TEUs<extra>'+name+'</extra>')
        fig2.update_layout(barmode='group',height=480,hovermode='x unified',margin=dict(l=10,r=10,t=10,b=80),legend=dict(orientation='h',y=-.35),yaxis_title='TEUs')
        fig2.update_xaxes(tickangle=-35)
        st.plotly_chart(fig2,use_container_width=True)
        st.subheader('Shipping Line Comparison — Full Year' if period=='Full Year' else f'Shipping Line Comparison — {period}')
        show=sm.copy()
        total=totals_for_period(df,month or None)
        f,b,a=[float(total[k]) for k in ('forecast','budget','actual')]
        show.loc['GRAND TOTAL',['Call','Forecast 2026','Budget 2026','Actual 2025']]=[pd.to_numeric(selected['calls'],errors='coerce').sum(),f,b,a]
        show.loc['GRAND TOTAL','Vs Budget']=pct(f-b,b)
        show.loc['GRAND TOTAL','YoY Growth']=pct(f-a,a)
        show.loc['GRAND TOTAL','Volume Change']=f-a
        styled=show.style.format({'Call':'{:,.0f}','Forecast 2026':'{:,.2f}','Budget 2026':'{:,.2f}','Actual 2025':'{:,.2f}','Vs Budget':'{:+.2%}','YoY Growth':'{:+.2%}','Volume Change':'{:+,.2f}'},na_rep='—').apply(lambda row:['background-color:#EAF4F7;font-weight:bold' if row.name=='GRAND TOTAL' else '' for _ in row],axis=1)
        st.dataframe(styled,use_container_width=True,height=490)
        st.download_button('Download comparison CSV',show.to_csv().encode('utf-8-sig'),file_name=f'shipping_compare_{year}.csv',mime='text/csv')
    st.divider()
    reconciliation(df,official,year,widget_key="dashboard_reconciliation")


def official_input(sb,official,year):
    st.subheader('Official KPI · Input & Approval')
    st.caption('Official KPI disimpan terpisah dari detail shipping line. Annual KPI tidak otomatis berubah saat data detail diedit atau dihapus.')
    period=st.selectbox('Official KPI Period',['Full Year']+MONTHS,key=f'official_period_{year}')
    month=0 if period=='Full Year' else MONTHS.index(period)+1
    current=official_row(official,month)
    status=str(current['status']) if current is not None else 'Draft'
    if status=='Approved':
        st.warning('Data ini berstatus Approved. Untuk revisi, wajib mengisi alasan perubahan.')
    with st.form(f'official_form_{year}_{month}'):
        actual=st.number_input('Actual 2025 (TEUs)',min_value=0.,value=float(current['actual']) if current is not None and pd.notna(current['actual']) else 0.,step=1.,format='%.2f')
        forecast=st.number_input('Forecast 2026 (TEUs)',min_value=0.,value=float(current['forecast']) if current is not None and pd.notna(current['forecast']) else 0.,step=1.,format='%.2f')
        budget=st.number_input('Budget 2026 (TEUs)',min_value=0.,value=float(current['budget']) if current is not None and pd.notna(current['budget']) else 0.,step=1.,format='%.2f')
        new_status=st.selectbox('Status',['Draft','Approved'],index=['Draft','Approved'].index(status))
        reason=st.text_input('Reason / revision note',placeholder='Misalnya: approved forecast revision v2')
        confirmed=st.checkbox('Confirm saving official figures')
        submitted=st.form_submit_button('Save Official KPI',type='primary')
    if submitted:
        if not confirmed:
            st.error('Centang konfirmasi sebelum menyimpan.')
        elif status=='Approved' and not reason.strip():
            st.error('Perubahan Approved KPI wajib menyertakan alasan.')
        elif new_status=='Approved' and not reason.strip():
            st.error('Approval wajib menyertakan alasan / referensi dokumen.')
        else:
            payload={'year':year,'month':month,'actual':actual,'forecast':forecast,'budget':budget,'status':new_status,'revision_note':reason.strip() or None}
            try:
                sb.table(OFFICIAL_TABLE).upsert(payload,on_conflict='year,month').execute()
                st.success('Official KPI berhasil disimpan.')
                st.rerun()
            except Exception as exc:
                st.error(f'Gagal menyimpan Official KPI: {exc}')
    st.caption('Full Year = month 0. Monthly KPI opsional dan harus diisi terpisah; sistem tidak membagi annual KPI secara asumtif.')
    if not official.empty:
        view=official[['month','actual','forecast','budget','status','revision_note']].copy()
        view['Period']=view['month'].map(lambda m:'Full Year' if m==0 else MONTHS[m-1])
        st.dataframe(view[['Period','actual','forecast','budget','status','revision_note']],hide_index=True,use_container_width=True)


def manage_data(sb, df, year):
    st.divider()
    st.subheader('Manage Data — Delete Records')
    st.caption('Hapus data yang sudah tersimpan di Supabase. Penghapusan permanen dan Dashboard akan diperbarui setelah berhasil.')
    if df.empty:
        st.info(f'Belum ada data untuk tahun {year}.')
        return

    scope = st.radio('Delete scope', ['One shipping line · one month', 'One shipping line · full year', 'All shipping lines · one month', 'All data · full year'], horizontal=False, key=f'delete_scope_{year}')
    names = sorted(df['shipping_line'].dropna().unique().tolist())
    line = None
    month = None
    if scope.startswith('One shipping line'):
        line = st.selectbox('Shipping Line', names, key=f'delete_line_{year}')
    if scope.endswith('one month'):
        month_name = st.selectbox('Month', MONTHS, key=f'delete_month_{year}')
        month = MONTHS.index(month_name) + 1

    matching = df.copy()
    if line is not None:
        matching = matching[matching['shipping_line'] == line]
    if month is not None:
        matching = matching[matching['month'] == month]
    st.write(f'**{len(matching)} record(s)** akan dihapus dari tahun **{year}**.')
    if matching.empty:
        st.info('Tidak ada record yang cocok dengan pilihan ini.')
        return
    st.dataframe(matching.sort_values(['shipping_line', 'month']), hide_index=True, use_container_width=True, height=min(300, 45 + len(matching) * 35))
    confirm = st.checkbox('Saya memahami bahwa data yang dipilih akan dihapus permanen.', key=f'confirm_delete_{year}_{scope}_{line}_{month}')
    if st.button('Delete Selected Data', type='secondary', disabled=not confirm, key=f'delete_shipping_{year}'):
        try:
            query = sb.table(TABLE).delete().eq('year', year)
            if line is not None:
                query = query.eq('shipping_line', line)
            if month is not None:
                query = query.eq('month', month)
            query.execute()
            st.success(f'{len(matching)} record(s) dihapus. Dashboard diperbarui.')
            st.rerun()
        except Exception as exc:
            st.error(f'Gagal menghapus data dari Supabase: {exc}')


def input_data(sb,df,year):
    st.subheader('Input / Edit Shipping Line Data')
    st.caption('Isi Call, Forecast 2026, Budget 2026, Actual 2025. Total dan growth dihitung otomatis; tidak perlu diinput.')
    t1,t2=st.tabs(['Spreadsheet Editor','Bulk Paste from Excel'])
    with t1:
        st.caption('Edit langsung di tabel; tambah shipping line melalui baris baru. Kolom bulan ditampilkan berurutan.')
        wide=wide_data(df).reset_index()
        if wide.empty: wide=pd.DataFrame(columns=['Shipping Line']+[f'{m} · {f}' for m in MONTHS for f in FIELDS])
        edited=st.data_editor(wide,num_rows='dynamic',hide_index=True,use_container_width=True,height=440,key=f'shipping_editor_{year}',column_config={'Shipping Line':st.column_config.TextColumn('Shipping Line',required=True)})
        if st.button('Save Spreadsheet Data',type='primary',key='save_shipping_editor'):
            try:
                records=records_from_wide(edited,year)
                save(sb,records,year)
            except Exception as exc: st.error(str(exc))
    with t2:
        st.caption('Copy dari Excel mulai kolom SHIPPING (VESSEL OPERATOR), diikuti 12 × (Call, Forecast, Budget 2026, Actual 2025). Tanpa NO, TOTAL, atau GROWTH. Bisa paste sebagian bulan: sisanya tidak diubah.')
        st.code('Shipping Line\tJan Call\tJan Forecast\tJan Budget\tJan Actual\tFeb Call\tFeb Forecast\tFeb Budget\tFeb Actual\t...',language='text')
        raw=st.text_area('Paste cells copied from Excel (tab-separated)',height=170,key='shipping_bulk')
        if raw.strip():
            try:
                frame=pd.read_csv(io.StringIO(raw),sep='\t',header=None,dtype=str,keep_default_na=False)
                if frame.shape[1]<5: raise ValueError('Minimal 5 kolom: Shipping Line, Call, Forecast, Budget, Actual.')
                if (frame.shape[1]-1)%4: raise ValueError('Jumlah kolom setelah Shipping Line harus kelipatan 4 (Call, Forecast, Budget, Actual).')
                if frame.shape[1]>49: raise ValueError('Maksimal 49 kolom (Shipping Line + 12 bulan × 4).')
                records=[]
                for i,row in frame.iterrows():
                    line=str(row.iloc[0]).strip()
                    if not line or line.upper() in ('SHIPPING (VESSEL OPERATOR)','SHIPPING LINE','TOTAL','GRAND TOTAL'): continue
                    for m in range((frame.shape[1]-1)//4):
                        vals=[num(v) for v in row.iloc[1+4*m:5+4*m]]
                        if all(v is None for v in vals): continue
                        records.append({'year':year,'month':m+1,'shipping_line':line.upper(),'calls':int(vals[0]) if vals[0] is not None else None,'forecast':vals[1],'budget':vals[2],'actual':vals[3]})
                st.success(f'{len(records)} monthly records siap disimpan.')
                st.dataframe(pd.DataFrame(records).head(50),hide_index=True,use_container_width=True)
                if st.button('Save Bulk Data',type='primary',key='save_shipping_bulk'):
                    save(sb,records,year)
            except Exception as exc: st.error(f'Format paste tidak sesuai: {exc}')
    st.caption('Catatan: baris yang sudah tersimpan akan diperbarui berdasarkan Year + Month + Shipping Line, bukan diduplikasi.')
    manage_data(sb, df, year)


def records_from_wide(frame,year):
    records=[]; seen=set()
    for _,row in frame.iterrows():
        line=str(row.get('Shipping Line') or '').strip().upper()
        if line in ('','NAN','NONE'): continue
        if line in seen: raise ValueError(f'Shipping Line duplikat: {line}')
        seen.add(line)
        for m,month in enumerate(MONTHS,1):
            vals=[num(row.get(f'{month} · {field}')) for field in FIELDS]
            if all(v is None for v in vals): continue
            if vals[0] is not None and vals[0]!=int(vals[0]): raise ValueError(f'Call harus integer: {line} {month}')
            records.append({'year':year,'month':m,'shipping_line':line,'calls':int(vals[0]) if vals[0] is not None else None,'forecast':vals[1],'budget':vals[2],'actual':vals[3]})
    return records


def save(sb,records,year):
    if not records:
        st.warning('Tidak ada data untuk disimpan.')
        return
    for r in records:
        if r['calls'] is not None and (r['calls']<0 or r['calls']!=int(r['calls'])): raise ValueError('Call harus bilangan bulat positif.')
    try:
        for start in range(0,len(records),250):
            sb.table(TABLE).upsert(records[start:start+250],on_conflict='year,month,shipping_line').execute()
        st.success(f'{len(records)} records berhasil disimpan. Dashboard akan diperbarui.')
        st.rerun()
    except Exception as exc:
        st.error(f'Gagal menyimpan ke Supabase: {exc}')


def render(sb):
    st.header('Throughput & Compare Shipping Line')
    st.caption('Marketing Seaside · Monthly shipping line performance · TEUs')
    year=st.number_input('Forecast Year',min_value=2020,max_value=2100,value=2026,step=1,key='shipping_year')
    df=load(sb,int(year))
    official=official_load(sb,int(year))
    dash,inp=st.tabs(['Dashboard','Input Data'])
    with dash: dashboard(df,official,int(year))
    with inp:
        official_tab,detail_tab,reconcile_tab=st.tabs(['Official KPI','Shipping Line Data','Data Reconciliation'])
        with official_tab: official_input(sb,official,int(year))
        with detail_tab: input_data(sb,df,int(year))
        with reconcile_tab: reconciliation(df,official,int(year),widget_key="input_reconciliation")
