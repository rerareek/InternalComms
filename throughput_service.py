"""Throughput Per Service: editable monthly detail, Supabase persistence and dashboard."""
import pandas as pd
import plotly.express as px
import streamlit as st

MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
FIELDS = ['Call','Local','TS']
TABLE = 'throughput_per_service'


def load(sb):
    try:
        result = []
        start = 0
        while True:
            batch = sb.table(TABLE).select('id,year,month,service_name,ship_line,calls,local_volume,ts_volume').range(start,start+999).execute().data or []
            result.extend(batch)
            if len(batch) < 1000:
                break
            start += 1000
        return pd.DataFrame(result)
    except Exception as e:
        st.error(f'Gagal mengambil data. Jalankan throughput_service_schema.sql di Supabase terlebih dahulu. Detail: {e}')
        st.stop()


def render(sb):
    st.header('Throughput Per Service')
    st.caption('2026 · Call, Local, TS dan Total per service dan shipping line')
    data = load(sb)
    if not data.empty:
        for c in ['year','month','calls','local_volume','ts_volume']:
            data[c] = pd.to_numeric(data[c],errors='coerce')
        data['total'] = data['local_volume'].fillna(0)+data['ts_volume'].fillna(0)

    with st.expander('✏️ Input / Edit Data', expanded=data.empty):
        st.caption('Satu baris = satu service + shipping line + bulan. Total dihitung otomatis. Kosongkan angka jika belum ada data.')
        with st.form('service_entry',clear_on_submit=True):
            c1,c2,c3 = st.columns(3)
            service = c1.text_input('Service Name (contoh: CIN1)')
            line = c2.text_input('Ship Line (contoh: CMA GROUP)')
            month = c3.selectbox('Month',MONTHS)
            c4,c5,c6 = st.columns(3)
            calls = c4.number_input('Call',min_value=0,step=1,value=0)
            local = c5.number_input('Local',min_value=0,step=1,value=0)
            ts = c6.number_input('TS',min_value=0,step=1,value=0)
            submitted = st.form_submit_button('Save Data',type='primary')
        if submitted:
            if not service.strip() or not line.strip():
                st.error('Service Name dan Ship Line wajib diisi.')
            else:
                record = dict(year=2026,month=MONTHS.index(month)+1,service_name=service.strip().upper(),ship_line=line.strip().upper(),calls=int(calls),local_volume=int(local),ts_volume=int(ts))
                try:
                    sb.table(TABLE).upsert(record,on_conflict='year,month,service_name,ship_line').execute()
                    st.success('Data tersimpan.')
                    st.rerun()
                except Exception as e:
                    st.error(f'Gagal menyimpan: {e}')
        if not data.empty:
            st.markdown('**Edit / Delete data yang sudah tersimpan**')
            options = data.sort_values(['service_name','ship_line','month']).copy()
            options['label'] = options.apply(lambda r: f"{r['service_name']} · {r['ship_line']} · {MONTHS[int(r['month'])-1]}",axis=1)
            selected_id = st.selectbox('Pilih data',options['id'].tolist(),format_func=lambda i:options.loc[options.id==i,'label'].iloc[0])
            selected = options.loc[options.id==selected_id].iloc[0]
            a,b,c = st.columns(3)
            ec = a.number_input('Edit Call',min_value=0,value=int(selected['calls']),key=f'ec_{selected_id}')
            el = b.number_input('Edit Local',min_value=0,value=int(selected['local_volume']),key=f'el_{selected_id}')
            et = c.number_input('Edit TS',min_value=0,value=int(selected['ts_volume']),key=f'et_{selected_id}')
            x,y = st.columns(2)
            if x.button('Update selected',key='update_service'):
                try:
                    sb.table(TABLE).update({'calls':ec,'local_volume':el,'ts_volume':et}).eq('id',int(selected_id)).execute()
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
            if y.button('Delete selected',key='delete_service'):
                try:
                    sb.table(TABLE).delete().eq('id',int(selected_id)).execute()
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    if data.empty:
        st.info('Belum ada data tersimpan. Isi Input / Edit Data lalu klik Save Data.')
        return

    c1,c2,c3 = st.columns(3)
    period = c1.selectbox('Period',MONTHS+['Full Year'],index=0)
    services = sorted(data['service_name'].dropna().unique().tolist())
    selected_services = c2.multiselect('Service',services,default=services)
    lines = sorted(data.loc[data.service_name.isin(selected_services),'ship_line'].dropna().unique().tolist())
    selected_lines = c3.multiselect('Shipping Line',lines,default=lines)
    filtered = data[data.service_name.isin(selected_services)&data.ship_line.isin(selected_lines)].copy()
    if period != 'Full Year':
        filtered = filtered[filtered.month==MONTHS.index(period)+1]
    if filtered.empty:
        st.info('Belum ada data untuk filter yang dipilih.')
        return
    total_calls = int(filtered.calls.sum())
    total_local = int(filtered.local_volume.sum())
    total_ts = int(filtered.ts_volume.sum())
    total = total_local+total_ts
    a,b,c,d = st.columns(4)
    a.metric('Total Throughput',f'{total:,}')
    b.metric('Vessel Calls',f'{total_calls:,}')
    c.metric('Local',f'{total_local:,}')
    d.metric('TS',f'{total_ts:,}')
    st.subheader('Throughput by Service')
    summary = filtered.groupby('service_name',as_index=False)[['local_volume','ts_volume','total','calls']].sum().sort_values('total',ascending=False)
    fig = px.bar(summary,x='service_name',y=['local_volume','ts_volume'],barmode='stack',labels={'service_name':'Service','value':'Throughput (TEUs)','variable':'Type'},color_discrete_map={'local_volume':'#3B82F6','ts_volume':'#14B8A6'})
    fig.for_each_trace(lambda t:t.update(name='Local' if t.name=='local_volume' else 'TS'))
    fig.update_layout(height=430,margin=dict(l=10,r=10,t=20,b=20),legend_title_text='')
    st.plotly_chart(fig,use_container_width=True)
    st.subheader('Service Details')
    details = filtered.groupby(['service_name','ship_line'],as_index=False)[['calls','local_volume','ts_volume','total']].sum()
    details.columns = ['Service Name','Ship Line','Call','Local','TS','Total']
    st.dataframe(details,use_container_width=True,hide_index=True)
    st.download_button('Download CSV',details.to_csv(index=False).encode('utf-8-sig'),'throughput_per_service.csv','text/csv')
    st.subheader('Monthly Summary')
    monthly = data[data.service_name.isin(selected_services)&data.ship_line.isin(selected_lines)].groupby('month')[['calls','local_volume','ts_volume','total']].sum().reindex(range(1,13))
    monthly.index = MONTHS
    monthly.index.name = 'Month'
    st.dataframe(monthly.rename(columns={'calls':'Call','local_volume':'Local','ts_volume':'TS','total':'Total'}),use_container_width=True)
    st.caption('Grand totals dan Total = Local + TS dihitung otomatis dari detail yang tersimpan; bukan dari subtotal manual.')
