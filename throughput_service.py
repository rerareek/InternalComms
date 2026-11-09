"""Throughput Per Service — dashboard and manual / Excel clipboard entry."""
import io
import re
import pandas as pd
import plotly.express as px
import streamlit as st

MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
TABLE = 'throughput_per_service'
PASTE_COLS = ['No', 'Service Name', 'Ship Line', 'Call', 'Local', 'TS']


def load(sb):
    try:
        rows, offset = [], 0
        while True:
            batch = (sb.table(TABLE)
                     .select('id,year,month,service_name,ship_line,calls,local_volume,ts_volume')
                     .range(offset, offset + 999).execute().data or [])
            rows.extend(batch)
            if len(batch) < 1000:
                break
            offset += 1000
        df = pd.DataFrame(rows)
        if not df.empty:
            for col in ['year','month','calls','local_volume','ts_volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype('int64')
            df['total'] = df.local_volume + df.ts_volume
        return df
    except Exception as exc:
        st.error(f'Gagal membaca data Supabase. Pastikan schema SQL sudah dijalankan. {exc}')
        st.stop()


def parse_number(value):
    if pd.isna(value) or str(value).strip() in ('', '-', '–', '—'):
        return 0
    raw = str(value).strip().replace(',', '').replace(' ', '')
    if raw.startswith('(') and raw.endswith(')'):
        raw = '-' + raw[1:-1]
    if raw.upper() in ('#VALUE!', '#REF!', '#N/A', '#DIV/0!'):
        raise ValueError(f'Nilai Excel error: {raw}')
    number = float(raw)
    if not number.is_integer() or number < 0:
        raise ValueError(f'Harus bilangan bulat positif: {value}')
    return int(number)


def normalize_paste(frame, year, month):
    """Supports six or five columns (No optional), and blank service cells."""
    records, issues, notes = [], [], []
    current_service = ''
    seen = set()
    for i, (_, row) in enumerate(frame.iterrows(), 1):
        service = str(row.get('Service Name', '') or '').strip()
        line = str(row.get('Ship Line', '') or '').strip()
        if service.lower() in ('nan', 'none'):
            service = ''
        if line.lower() in ('nan', 'none'):
            line = ''
        if service:
            if service.upper() in ('SERVICE NAME', 'GRAND TOTAL') or service.upper().endswith(' TOTAL'):
                continue
            current_service = service.upper()
        if not line or line.upper() in ('SHIP LINE', 'TOTAL'):
            continue
        if not current_service:
            issues.append(f'Baris {i}: Service Name belum diketahui. Isi nama service di baris pertama grup.')
            continue
        try:
            calls = parse_number(row.get('Call'))
            local = parse_number(row.get('Local'))
            ts = parse_number(row.get('TS'))
            key = (current_service, line.upper())
            if key in seen:
                issues.append(f'Baris {i}: Duplikat service + ship line: {key[0]} / {key[1]}.')
                continue
            seen.add(key)
            records.append(dict(year=int(year), month=int(month), service_name=current_service,
                                ship_line=line.upper(), calls=calls, local_volume=local,
                                ts_volume=ts))
        except (ValueError, TypeError) as exc:
            issues.append(f'Baris {i} ({current_service} / {line}): {exc}')
    return records, issues, notes


def parse_clipboard(raw):
    """Clipboard text pasted directly from Excel, with or without the No column."""
    if not raw.strip():
        return pd.DataFrame(columns=PASTE_COLS)
    lines = [line.split('\t') for line in raw.splitlines() if line.strip()]
    width = max(len(x) for x in lines)
    if width not in (5, 6):
        raise ValueError('Copy kolom No sampai TS (6 kolom), atau Service Name sampai TS (5 kolom), untuk satu bulan saja. Jangan sertakan kolom Total.')
    rows = [r + [''] * (width - len(r)) for r in lines]
    df = pd.DataFrame(rows, columns=PASTE_COLS if width == 6 else PASTE_COLS[1:])
    if width == 5:
        df.insert(0, 'No', '')
    return df


def save_batch(sb, records):
    for offset in range(0, len(records), 200):
        sb.table(TABLE).upsert(records[offset:offset + 200],
                               on_conflict='year,month,service_name,ship_line').execute()


def dashboard(data):
    st.caption('Analisis throughput berdasarkan service dan shipping line')
    if data.empty:
        st.info('Belum ada data. Buka tab Input Data untuk mulai mengisi.')
        return
    c1, c2, c3, c4 = st.columns(4)
    years = sorted(data.year.unique().tolist(), reverse=True)
    year = c1.selectbox('Year', years, key='svc_dash_year')
    period = c2.selectbox('Period', MONTHS + ['Full Year'], key='svc_dash_period')
    base = data[data.year == year]
    services = sorted(base.service_name.unique().tolist())
    # Reconcile saved widget selections with newly inserted services.
    # When the dashboard was first opened with no data, Streamlit can retain [].
    old_services = st.session_state.get('svc_dash_services')
    if old_services is None or not old_services or set(services) != set(st.session_state.get('svc_dash_service_options', [])):
        st.session_state['svc_dash_services'] = services.copy()
    st.session_state['svc_dash_service_options'] = services.copy()
    chosen_services = c3.multiselect('Service', services, key='svc_dash_services')
    lines = sorted(base.loc[base.service_name.isin(chosen_services), 'ship_line'].unique().tolist())
    old_lines = st.session_state.get('svc_dash_lines')
    if old_lines is None or not old_lines or set(lines) != set(st.session_state.get('svc_dash_line_options', [])):
        st.session_state['svc_dash_lines'] = lines.copy()
    st.session_state['svc_dash_line_options'] = lines.copy()
    chosen_lines = c4.multiselect('Ship Line', lines, key='svc_dash_lines')
    filtered = base[base.service_name.isin(chosen_services) & base.ship_line.isin(chosen_lines)]
    if period != 'Full Year':
        filtered = filtered[filtered.month == MONTHS.index(period) + 1]
    if filtered.empty:
        st.info('Tidak ada data untuk filter yang dipilih.')
        return
    total_local = int(filtered.local_volume.sum())
    total_ts = int(filtered.ts_volume.sum())
    a, b, c, d = st.columns(4)
    a.metric('Total Throughput', f'{total_local + total_ts:,} TEU')
    b.metric('Vessel Calls', f'{int(filtered.calls.sum()):,}')
    c.metric('Local', f'{total_local:,}')
    d.metric('TS', f'{total_ts:,}')
    summary = (filtered.groupby('service_name', as_index=False)[['local_volume','ts_volume','total','calls']]
               .sum().sort_values('total', ascending=False))
    st.subheader('Throughput by Service')
    fig = px.bar(summary, x='service_name', y=['local_volume','ts_volume'], barmode='stack',
                 labels={'service_name':'Service','value':'Throughput (TEU)','variable':'Type'},
                 color_discrete_map={'local_volume':'#3B82F6','ts_volume':'#14B8A6'})
    fig.for_each_trace(lambda t: t.update(name='Local' if t.name == 'local_volume' else 'TS'))
    fig.update_layout(height=420, margin=dict(l=10,r=10,t=20,b=20), legend_title_text='')
    st.plotly_chart(fig, use_container_width=True)
    st.subheader('Service Details')
    details = filtered.groupby(['service_name','ship_line'], as_index=False)[['calls','local_volume','ts_volume','total']].sum()
    details.columns = ['Service Name','Ship Line','Call','Local','TS','Total']
    st.dataframe(details, use_container_width=True, hide_index=True)
    st.download_button('Download CSV', details.to_csv(index=False).encode('utf-8-sig'),
                       'throughput_per_service.csv', 'text/csv')
    st.subheader('Monthly Summary')
    monthly = (base[base.service_name.isin(chosen_services) & base.ship_line.isin(chosen_lines)]
               .groupby('month')[['calls','local_volume','ts_volume','total']].sum().reindex(range(1,13), fill_value=0))
    monthly.index = MONTHS
    monthly.index.name = 'Month'
    st.dataframe(monthly.rename(columns={'calls':'Call','local_volume':'Local','ts_volume':'TS','total':'Total'}),
                 use_container_width=True)
    st.subheader('Throughput Per Service — Full Year Detail')
    st.caption('Format seperti Excel: Service Name → Ship Line, Jan–Dec (Call / Local / TS / Total), subtotal per service, dan Grand Total. Geser tabel ke kanan untuk melihat bulan berikutnya.')
    matrix = annual_service_matrix(base[base.service_name.isin(chosen_services) &
                                        base.ship_line.isin(chosen_lines)], year)
    if not matrix.empty:
        def highlight_totals(row):
            service = str(row.name[0]).strip().upper()
            is_total = service.endswith(' TOTAL') or service == 'GRAND TOTAL'
            return ['font-weight: bold' if is_total else '' for _ in row]

        st.dataframe(matrix.style.format('{:,.0f}').apply(highlight_totals, axis=1),
                     use_container_width=True, height=520)
        export = matrix.copy()
        export.index = pd.MultiIndex.from_tuples(export.index, names=['Service Name', 'Ship Line'])
        st.download_button('Download Full Year Detail (CSV)',
                           export.to_csv().encode('utf-8-sig'),
                           f'throughput_service_detail_{year}.csv', 'text/csv',
                           key='svc_detail_export')



def annual_service_matrix(data, year):
    """Excel-style Jan-Dec + Full Year matrix with dynamic service/line groups."""
    base = data[data.year == year].copy()
    if base.empty:
        return pd.DataFrame()
    fields = [('Call', 'calls'), ('Local', 'local_volume'),
              ('TS', 'ts_volume'), ('Total', 'total')]
    periods = MONTHS + ['Full Year']
    columns = pd.MultiIndex.from_tuples(
        [(period, label) for period in periods for label, _ in fields],
        names=['Period', 'Metric'])
    records = []
    labels = []

    def make_values(part):
        values = []
        for month_number in range(1, 13):
            sub = part[part.month == month_number]
            values.extend(int(sub[field].sum()) for _, field in fields)
        values.extend(int(part[field].sum()) for _, field in fields)
        return values

    for service in sorted(base.service_name.dropna().unique()):
        service_rows = base[base.service_name == service]
        for line in sorted(service_rows.ship_line.dropna().unique()):
            records.append(make_values(service_rows[service_rows.ship_line == line]))
            labels.append((service, line))
        records.append(make_values(service_rows))
        labels.append((f'{service} Total', ''))
    records.append(make_values(base))
    labels.append(('GRAND TOTAL', ''))
    result = pd.DataFrame(records, index=pd.MultiIndex.from_tuples(
        labels, names=['Service Name', 'Ship Line']), columns=columns)
    return result


def manual_input(sb, data):
    st.caption('Satu record = satu Service Name + Ship Line + Month. Nama service dan shipping line bebas ditambah.')
    with st.form('svc_manual_form', clear_on_submit=True):
        a,b,c,d = st.columns(4)
        year = a.number_input('Year', min_value=2020, max_value=2100, value=2026, step=1)
        month = b.selectbox('Month', MONTHS)
        service = c.text_input('Service Name', placeholder='CIN1')
        line = d.text_input('Ship Line', placeholder='CMA GROUP')
        x,y,z = st.columns(3)
        calls = x.number_input('Call', min_value=0, step=1, value=0)
        local = y.number_input('Local', min_value=0, step=1, value=0)
        ts = z.number_input('TS', min_value=0, step=1, value=0)
        st.caption(f'Total otomatis: {int(local) + int(ts):,} TEU')
        submit = st.form_submit_button('Save Data', type='primary')
    if submit:
        if not service.strip() or not line.strip():
            st.error('Service Name dan Ship Line wajib diisi.')
        else:
            record = dict(year=int(year), month=MONTHS.index(month)+1,
                          service_name=service.strip().upper(), ship_line=line.strip().upper(),
                          calls=int(calls), local_volume=int(local), ts_volume=int(ts))
            try:
                save_batch(sb, [record])
                st.success('Data tersimpan.')
                st.rerun()
            except Exception as exc:
                st.error(f'Gagal menyimpan: {exc}')
    if data.empty:
        return
    st.divider()
    st.markdown('**Edit / Delete data tersimpan**')
    options = data.sort_values(['year','service_name','ship_line','month']).copy()
    labels = {int(r.id): f'{r.year} · {MONTHS[int(r.month)-1]} · {r.service_name} / {r.ship_line}'
              for r in options.itertuples()}
    chosen = st.selectbox('Pilih record', list(labels), format_func=lambda k: labels[k])
    selected = options[options.id == chosen].iloc[0]
    a,b,c = st.columns(3)
    ec = a.number_input('Edit Call', min_value=0, value=int(selected.calls), key=f'svc_ec_{chosen}')
    el = b.number_input('Edit Local', min_value=0, value=int(selected.local_volume), key=f'svc_el_{chosen}')
    et = c.number_input('Edit TS', min_value=0, value=int(selected.ts_volume), key=f'svc_et_{chosen}')
    left, right = st.columns(2)
    if left.button('Update Selected', key='svc_update'):
        try:
            sb.table(TABLE).update({'calls':int(ec),'local_volume':int(el),'ts_volume':int(et)}).eq('id',int(chosen)).execute()
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    if right.button('Delete Selected', key='svc_delete'):
        st.session_state['svc_delete_pending'] = chosen
    if st.session_state.get('svc_delete_pending') == chosen:
        st.warning('Yakin ingin menghapus record ini?')
        if st.button('Confirm Delete', key='svc_confirm_delete'):
            try:
                sb.table(TABLE).delete().eq('id',int(chosen)).execute()
                st.session_state.pop('svc_delete_pending', None)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


def bulk_input(sb):
    st.caption('Copy data dari Excel untuk satu bulan: No (opsional), Service Name, Ship Line, Call, Local, TS. Kolom Total tidak perlu disertakan karena dihitung otomatis.')
    a,b = st.columns(2)
    year = a.number_input('Year', min_value=2020, max_value=2100, value=2026, step=1, key='svc_bulk_year')
    month_name = b.selectbox('Month', MONTHS, key='svc_bulk_month')
    mode = st.radio('Cara paste', ['Paste ke tabel', 'Paste langsung dari Excel (Ctrl+V)'], horizontal=True,
                    key='svc_bulk_mode')
    if mode == 'Paste ke tabel':
        st.caption('Klik sel pertama tabel → Ctrl+V dari Excel. Baris baru bisa ditambah otomatis. Kalau paste Excel tidak cocok, pilih mode paste langsung.')
        empty = pd.DataFrame([{col:'' for col in PASTE_COLS} for _ in range(4)])
        frame = st.data_editor(empty, num_rows='dynamic', hide_index=True, use_container_width=True,
                               key='svc_bulk_editor', column_config={col:st.column_config.TextColumn(col) for col in PASTE_COLS})
    else:
        raw = st.text_area('Paste sel Excel di sini (Ctrl+V)', height=180, key='svc_bulk_raw',
                           placeholder='1\tCIN1\tCMA GROUP\t2\t14,964\t362')
        try:
            frame = parse_clipboard(raw)
        except ValueError as exc:
            st.error(str(exc))
            return
    records, errors, warnings = normalize_paste(frame, year, MONTHS.index(month_name)+1)
    if errors:
        st.error(f'{len(errors)} masalah ditemukan. Perbaiki sebelum Save.')
        for message in errors[:15]:
            st.write('•', message)
        if len(errors) > 15:
            st.caption(f'Dan {len(errors)-15} masalah lainnya.')
    if records:
        preview = pd.DataFrame(records).rename(columns={'service_name':'Service Name','ship_line':'Ship Line',
                                                          'calls':'Call','local_volume':'Local','ts_volume':'TS'})
        preview['Total'] = preview['Local'] + preview['TS']
        st.markdown(f'**Preview: {len(records)} record siap disimpan — {month_name} {year}**')
        st.dataframe(preview[['Service Name','Ship Line','Call','Local','TS','Total']],
                     hide_index=True, use_container_width=True)
    st.caption('Baris subtotal seperti CIN1 Total / GRAND TOTAL dilewati. Service Name kosong mengikuti service terakhir. Total dihitung dari Local + TS.')
    st.caption('Save menggunakan upsert: record dengan Year + Month + Service + Ship Line yang sama akan di-update; record lain tidak dihapus.')
    if st.button(f'Save {len(records)} Records to Supabase', type='primary',
                 disabled=bool(errors) or not records, key='svc_bulk_save'):
        try:
            save_batch(sb, records)
            st.session_state['svc_saved_message'] = f'{len(records)} record berhasil disimpan / diperbarui. Buka tab Dashboard untuk melihat hasilnya.'
            st.rerun()
        except Exception as exc:
            st.error(f'Gagal menyimpan: {exc}')


def render(sb):
    st.header('Throughput Per Service')
    st.caption('Call, Local, TS & Total · per service dan shipping line')
    if st.session_state.pop('svc_saved_message', None):
        st.success('Data Copy–Paste berhasil disimpan ke Supabase. Cek Dashboard (Year, Period, Service, Ship Line).')
    tab_dashboard, tab_input = st.tabs(['📊 Dashboard', '✏️ Input Data'])
    with tab_dashboard:
        dashboard(load(sb))
    with tab_input:
        manual, bulk = st.tabs(['Manual Input', 'Bulk Data Entry'])
        with manual:
            manual_input(sb, load(sb))
        with bulk:
            bulk_input(sb)
