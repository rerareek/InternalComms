"""Throughput & Compare Shipping Line | JICT CRM."""
import io
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

TABLE = 'throughput_shipping_compare'
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


def dashboard(df,year):
    st.subheader('Shipping Line Performance')
    if df.empty:
        st.info('Belum ada data. Buka tab Input Data untuk mulai mengisi.')
        return
    period=st.selectbox('Period', ['Full Year']+MONTHS, key='shipping_period')
    selected=df if period=='Full Year' else df[df.month==MONTHS.index(period)+1]
    sm=summary(selected)
    all_tot=sm[['Call','Forecast 2026','Budget 2026','Actual 2025']].sum()
    forecast=all_tot['Forecast 2026']; actual=all_tot['Actual 2025']; budget=all_tot['Budget 2026']
    yoy=(forecast-actual)/actual if actual else None
    vs=(forecast-budget)/budget if budget else None
    values=[actual,forecast,budget,yoy,vs,forecast-actual]
    titles=['Actual 2025','Forecast 2026','Budget 2026','YoY Growth','Vs Budget','Volume Change']
    for start in (0,3):
        columns=st.columns(3)
        for i,col in enumerate(columns,start):
            val=values[i]
            display=('N/A' if val is None or pd.isna(val) else f'{val:+.2%}' if i in (3,4) else f'{val:+,.0f}' if i==5 else f'{val:,.0f}')
            col.metric(titles[i],display)
    st.divider()
    st.subheader('Monthly Throughput Volume (TEUs)')
    monthly=df.groupby('month')[['actual','forecast','budget']].sum().reindex(range(1,13))
    fig=go.Figure()
    for name,field in [('Actual 2025','actual'),('Forecast 2026','forecast'),('Budget 2026','budget')]:
        fig.add_trace(go.Scatter(x=MONTHS,y=monthly[field],name=name,mode='lines+markers',line=dict(color=COLORS[name],width=2.5),hovertemplate='%{x}: %{y:,.0f} TEUs<extra>'+name+'</extra>'))
    fig.update_layout(height=400,hovermode='x unified',legend=dict(orientation='h',y=-.22),margin=dict(l=10,r=10,t=10,b=20),yaxis_title='TEUs')
    fig.update_yaxes(tickformat=',.0f',gridcolor='rgba(128,128,128,.15)')
    st.plotly_chart(fig,use_container_width=True)
    st.subheader('Top Shipping Lines')
    metric=st.selectbox('Ranking based on',SERIES,index=1)
    top_n=st.slider('Number of shipping lines',5,max(5,len(sm)),min(20,max(5,len(sm))))
    chart=sm.sort_values(metric,ascending=False).head(top_n)
    fig2=go.Figure()
    for name in ['Forecast 2026','Budget 2026','Actual 2025']:
        fig2.add_bar(x=chart.index.tolist(),y=chart[name],name=name,marker_color=COLORS[name],hovertemplate='%{x}<br>%{y:,.0f} TEUs<extra>'+name+'</extra>')
    fig2.update_layout(barmode='group',height=480,hovermode='x unified',margin=dict(l=10,r=10,t=10,b=80),legend=dict(orientation='h',y=-.35),yaxis_title='TEUs')
    fig2.update_xaxes(tickangle=-35)
    st.plotly_chart(fig2,use_container_width=True)
    st.subheader('Shipping Line Comparison — Full Year' if period=='Full Year' else f'Shipping Line Comparison — {period}')
    show=sm.copy()
    show.loc['GRAND TOTAL',['Call','Forecast 2026','Budget 2026','Actual 2025']]=all_tot
    show.loc['GRAND TOTAL','Vs Budget']=vs
    show.loc['GRAND TOTAL','YoY Growth']=yoy
    show.loc['GRAND TOTAL','Volume Change']=forecast-actual
    styled=show.style.format({'Call':'{:,.0f}','Forecast 2026':'{:,.2f}','Budget 2026':'{:,.2f}','Actual 2025':'{:,.2f}','Vs Budget':'{:+.2%}','YoY Growth':'{:+.2%}','Volume Change':'{:+,.2f}'},na_rep='—').apply(lambda row:['background-color:#EAF4F7;font-weight:bold' if row.name=='GRAND TOTAL' else '' for _ in row],axis=1)
    st.dataframe(styled,use_container_width=True,height=490)
    st.download_button('Download comparison CSV',show.to_csv().encode('utf-8-sig'),file_name=f'shipping_compare_{year}.csv',mime='text/csv')


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
    dash,inp=st.tabs(['Dashboard','Input Data'])
    with dash: dashboard(df,int(year))
    with inp: input_data(sb,df,int(year))
