from centered_tables import centered_dataframe
"""Executive Dashboard for JICT CRM. Reads the same live Supabase tables as source menus.
No cached snapshots, no writes, and no hard-coded KPI values.
"""
from datetime import date
from html import escape
import pandas as pd
import altair as alt
import streamlit as st

MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
TERMINALS = ['JICT','TPK KOJA','MAL','TO3','NPCT1']
SERIES = ['2025 (Actual)','Budget 2026','2026 (Forecast)']


def read(sb, table, columns='*', filters=None):
    """Paginate to avoid Supabase's common 1,000-row response limit."""
    rows = []
    offset = 0
    while True:
        q = sb.table(table).select(columns)
        for key, value in (filters or {}).items():
            q = q.eq(key, value)
        batch = q.range(offset, offset+999).execute().data or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return pd.DataFrame(rows)


def source(sb, table, columns='*', filters=None):
    try:
        return read(sb, table, columns, filters)
    except Exception as exc:
        st.warning(f'Sumber {table} belum bisa dibaca: {exc}')
        return pd.DataFrame()


def num(df, column):
    return pd.to_numeric(df[column], errors='coerce') if column in df else pd.Series(dtype=float)


def fmt(value, suffix='', digits=0):
    return f'{value:,.{digits}f}{suffix}' if value is not None and pd.notna(value) else '—'


def pct(current, previous):
    return (current / previous - 1) * 100 if current is not None and previous is not None and previous > 0 else None


def chart(data, x='Month', y='TEUs', color='Series', kind='line', height=290, order=None):
    base = alt.Chart(data).encode(
        x=alt.X(f'{x}:N', sort=order if order is not None else None, title=None),
        y=alt.Y(f'{y}:Q', title=y, axis=alt.Axis(format=',.0f')),
        color=alt.Color(f'{color}:N', title=None),
        tooltip=[alt.Tooltip(f'{x}:N'), alt.Tooltip(f'{color}:N'), alt.Tooltip(f'{y}:Q', format=',.2f')],
    )
    if kind == 'bar':
        return base.mark_bar(cornerRadiusTopLeft=3,cornerRadiusTopRight=3).properties(height=height)
    return (base.mark_line(point=True,strokeWidth=2.5) + base.mark_point(size=48)).properties(height=height)


def section(title, description=None):
    st.markdown("<div class='jict-section-divider' aria-hidden='true'></div>", unsafe_allow_html=True)
    st.subheader(title)
    if description:
        st.caption(description)


def render_kpi_cards(items):
    """Responsive, accessible executive KPI cards; values are passed from live queries."""
    st.markdown("""<style>
    .jict-kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;margin:8px 0 24px}
    .jict-kpi{position:relative;overflow:hidden;border:1px solid rgba(128,145,166,.22);
      border-radius:16px;padding:18px 18px 16px;background:var(--secondary-background-color,#f8fafc);
      min-height:150px;box-shadow:0 4px 16px rgba(17,24,39,.045)}
    .jict-kpi:before{content:'';position:absolute;top:0;left:0;right:0;height:4px;background:var(--kpi-accent)}
    .jict-kpi .kpi-top{display:flex;align-items:center;justify-content:space-between;gap:8px}
    .jict-kpi .kpi-label{font-size:.78rem;font-weight:650;letter-spacing:.01em;opacity:.78;line-height:1.4}
    .jict-kpi .kpi-icon{font-size:1.15rem;opacity:.9}
    .jict-kpi .kpi-value{font-size:clamp(1.3rem,2vw,1.95rem);font-weight:760;line-height:1.25;
      letter-spacing:-.035em;margin:17px 0 7px;overflow-wrap:anywhere;color:var(--text-color,#172033)}
    .jict-kpi .kpi-unit{font-size:.76rem;font-weight:550;opacity:.65;letter-spacing:0}
    .jict-kpi .kpi-note{font-size:.74rem;opacity:.7;line-height:1.35}
    .jict-kpi .kpi-trend{font-size:.74rem;font-weight:700;color:var(--kpi-accent)}
    @media(max-width:1100px){.jict-kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media(max-width:560px){.jict-kpi-grid{grid-template-columns:minmax(0,1fr)}}
    </style>""",unsafe_allow_html=True)
    blocks=[]
    for item in items:
        label,value,unit,note,icon,accent=item
        blocks.append(
            f'<div class="jict-kpi" style="--kpi-accent:{accent}">'
            f'<div class="kpi-top"><span class="kpi-label">{escape(label)}</span>'
            f'<span class="kpi-icon" aria-hidden="true">{icon}</span></div>'
            f'<div class="kpi-value">{escape(value)} <span class="kpi-unit">{escape(unit)}</span></div>'
            f'<div class="kpi-note">{escape(note)}</div></div>'
        )
    st.markdown('<div class="jict-kpi-grid">'+''.join(blocks)+'</div>',unsafe_allow_html=True)


def growth_display(value):
    if value is None or pd.isna(value):
        return '—', 'No comparison available', '#64748b'
    if value > 0:
        return f'+{value:,.2f}%', '▲ Increase vs baseline', '#15956c'
    if value < 0:
        return f'{value:,.2f}%', '▼ Decrease vs baseline', '#db5b53'
    return '0.00%', 'No change vs baseline', '#64748b'



def _operational_ytd_table(data, cutoff, measure, series_order, key, mode="average", unit=""):
    """Compact monthly wide table; the YTD summary uses all months through cutoff."""
    if data.empty:
        st.info("Belum ada data YTD.")
        return
    choices = [3, 6, 9, 12]
    count = st.selectbox(
        "Show latest months", choices, index=0,
        format_func=lambda n: f"Last {n} months", key=f"{key}_months",
    )
    base = data.loc[data["month"].between(1, cutoff), ["month", "Series", measure]].copy()
    base[measure] = pd.to_numeric(base[measure], errors="coerce")
    base = base.dropna(subset=[measure])
    if base.empty:
        st.info("Belum ada data sampai bulan terpilih.")
        return
    # Summarize duplicates within each month/series, without treating missing values as zero.
    aggregation = "mean" if mode == "average" else "sum"
    wide = base.pivot_table(index="month", columns="Series", values=measure, aggfunc=aggregation)
    wide = wide.reindex(columns=series_order)
    # A compact window changes only visible monthly rows, never the YTD calculation.
    start = max(1, cutoff - count + 1)
    visible = wide.loc[(wide.index >= start) & (wide.index <= cutoff)].copy()
    if visible.empty:
        st.info("Tidak ada data untuk rentang bulan ini.")
        return
    visible.index = [MONTHS[int(m) - 1] for m in visible.index]
    visible.index.name = "Month"
    visible = visible.reset_index()
    # The YTD (Year) column identifies the reporting period; avoid adding
    # unrelated series (e.g. dwelling-time categories) into a fabricated total.
    visible["YTD (Year)"] = ""
    summary = {"Month": f"YTD Jan–{MONTHS[cutoff-1]}"}
    for series in series_order:
        vals = base.loc[base["Series"].eq(series), measure]
        summary[series] = vals.mean() if mode == "average" and not vals.empty else (vals.sum() if not vals.empty else float('nan'))
    summary["YTD (Year)"] = str(st.session_state.get("exec_year", ""))
    visible = pd.concat([visible, pd.DataFrame([summary])], ignore_index=True)
    for series in series_order:
        visible[series] = visible[series].map(lambda x: f"{x:,.2f}" if pd.notna(x) and mode == "average" else (f"{x:,.0f}" if pd.notna(x) else "—"))
    st.caption(f"{unit} · YTD {'monthly average' if mode == 'average' else 'cumulative volume'} through {MONTHS[cutoff-1]}. Last row includes all available months Jan–{MONTHS[cutoff-1]}.")
    centered_dataframe(visible, hide_index=True, use_container_width=True, height=min(490, 95 + 37 * len(visible)))


def render(sb):
    st.markdown('''<style>
    .jict-section-divider{height:1px;background:linear-gradient(90deg,transparent 0%,rgba(100,116,139,.38) 12%,rgba(100,116,139,.38) 88%,transparent 100%);margin:38px 0 27px}
    .jict-comparison-heading{font-size:.9rem;font-weight:700;margin:4px 0 0}
    .jict-comparison-caption{font-size:.78rem;opacity:.7;margin-bottom:9px}

    .jict-mini-wrap{border:1px solid rgba(100,116,139,.25);border-radius:13px;padding:10px 12px;background:var(--secondary-background-color,#f8fafc);overflow-x:auto;margin:8px 0 16px}
    .jict-mini-title{font-size:.78rem;font-weight:700;margin-bottom:6px;opacity:.85}
    .jict-mini-table{width:100%;border-collapse:collapse;font-size:.74rem;font-variant-numeric:tabular-nums;white-space:nowrap}
    .jict-mini-table th,.jict-mini-table td{padding:4px 7px;border-bottom:1px solid rgba(100,116,139,.14);text-align:right}
    .jict-mini-table th:first-child,.jict-mini-table td:first-child{text-align:left}
    .jict-mini-table thead th{font-weight:700;color:inherit;opacity:.85}
    .jict-mini-table .jict-mini-total td{font-weight:800;border-top:1px solid rgba(100,116,139,.3);border-bottom:0}
    .jict-share-delta{border:1px solid rgba(100,116,139,.25);border-radius:13px;padding:12px 15px;margin:8px 0 16px;background:var(--secondary-background-color,#f8fafc)}
    .jict-share-delta-label{font-size:.78rem;opacity:.75}
    .jict-share-delta-value{font-size:1.45rem;font-weight:750;margin:3px 0}
    </style>''',unsafe_allow_html=True)
    st.header('Executive Dashboard')
    st.caption('JICT · Marketing & Seaside Intelligence | Live data from existing Supabase menus')
    a,b,c = st.columns([1,1,2])
    with a:
        year = st.selectbox('Reporting Year', [2026,2025,2027,2028,2024], key='exec_year')
    with b:
        month = st.selectbox('YTD Through', list(range(1,13)), index=9, format_func=lambda m:MONTHS[m-1], key='exec_month')
    with c:
        st.caption('Angka diperbarui saat halaman dimuat ulang. Pilih bulan sesuai periode data terakhir yang sudah lengkap.')
        if st.button('↻ Refresh Data', key='exec_refresh'):
            st.rerun()

    budget = source(sb, 'throughput_budget_2526', 'series,month,value')
    tp = source(sb, 'throughput', 'year,month,terminal,value')
    shipping_official = source(sb, 'throughput_shipping_official_kpi', '*', {'year':year})
    shipping_detail = source(sb, 'throughput_shipping_compare', 'shipping_line,month,forecast,budget,actual', {'year':year})
    ytd = source(sb, 'ytd_shipping_lines', '*', {'year':year,'month':month})
    ytd_official = source(sb, 'ytd_shipping_official_totals', '*', {'year':year,'month':month})
    operational = source(sb, 'operational_monthly_metrics', '*', {'year':year})
    divert = source(sb, 'operational_divert', '*', {'year':year})

    for frame in [budget,tp,shipping_official,shipping_detail,ytd,ytd_official,operational,divert]:
        if 'month' in frame:
            frame['month'] = pd.to_numeric(frame['month'],errors='coerce')
    if not budget.empty:
        budget['value'] = num(budget,'value')
    if not tp.empty:
        tp['value'] = num(tp,'value')
        tp['year'] = num(tp,'year')
    if not operational.empty:
        operational['value'] = num(operational,'value')

    # Annual KPI priority: official shipping KPI if a full-year total row exists;
    # otherwise budget menu's explicit Total (month 13); monthly sums only as a fallback.
    def annual_budget(label):
        if budget.empty:
            return None
        d = budget[budget['series'].eq(label)]
        if d.empty:
            return None
        total = d.loc[d['month'].eq(13),'value'].dropna()
        if not total.empty:
            return float(total.iloc[-1])
        monthly = d[d['month'].between(1,12)]['value'].dropna()
        return float(monthly.sum()) if len(monthly)==12 else None

    forecast = annual_budget('2026 (Forecast)') if year == 2026 else None
    annual_budget26 = annual_budget('Budget 2026') if year == 2026 else None
    actual25 = annual_budget('2025 (Actual)') if year == 2026 else None
    if year == 2026 and not shipping_official.empty:
        # Official KPI schema uses month=0 for Full Year; do not override with monthly rows.
        off = shipping_official.copy()
        for field, variable in [('forecast','forecast'),('budget','annual_budget26'),('actual','actual25')]:
            if field not in off: continue
            full = off.loc[off['month'].eq(0),field].dropna()
            if len(full):
                try:
                    val=float(full.iloc[-1])
                    if variable=='forecast': forecast=val
                    elif variable=='budget': annual_budget26=val
                    else: actual25=val
                except (ValueError,TypeError): pass

    # Market share is computed using Tanjung Priok terminal throughput (same periods).
    def terminal_slice(y):
        if tp.empty: return pd.DataFrame(columns=['terminal','value'])
        d=tp[tp['year'].eq(y)&tp['month'].between(1,month)&tp['terminal'].isin(TERMINALS)]
        return d.groupby('terminal',as_index=False)['value'].sum()
    current_term=terminal_slice(year)
    prev_term=terminal_slice(year-1)
    tp_total=float(current_term['value'].sum()) if not current_term.empty else None
    jict=float(current_term.loc[current_term['terminal'].eq('JICT'),'value'].sum()) if not current_term.empty else None
    ms=jict/tp_total*100 if tp_total and jict is not None else None

    # YTD official totals take priority; detail is fallback and clearly disclosed.
    ytd_source='Official YTD Totals' if not ytd_official.empty else 'Shipping Line Detail (fallback)'
    ytd_row=ytd_official.iloc[0] if not ytd_official.empty else None
    def pair_total(frame, prefix):
        if frame.empty: return None
        cols=[f'full_{prefix}',f'empty_{prefix}']
        if not all(c in frame for c in cols): return None
        vals=[num(frame,c) for c in cols]
        if not any(v.notna().any() for v in vals): return None
        return float(sum(v.sum() for v in vals))
    ytd_volume=pair_total(ytd_official,'2026') if ytd_row is not None else pair_total(ytd,'2026')

    st.markdown('### Performance at a Glance')
    yoy_val, yoy_note, yoy_color = growth_display(pct(forecast,actual25))
    budget_val, budget_note, budget_color = growth_display(pct(forecast,annual_budget26))
    render_kpi_cards([
        ('Forecast 2026',fmt(forecast),'TEU','Full-year projected volume','◈','#2563eb'),
        ('Budget 2026',fmt(annual_budget26),'TEU','Full-year target','◎','#7c3aed'),
        ('Actual 2025',fmt(actual25),'TEU','Previous-year actual','▥','#0891b2'),
        ('Growth 2026 vs 2025',yoy_val,'',yoy_note,'↗',yoy_color),
        ('Growth vs Budget 2026',budget_val,'',budget_note,'↗',budget_color),
        (f'YTD {MONTHS[month-1]} {year} Volume',fmt(ytd_volume),'TEU',f'January–{MONTHS[month-1]} {year} · {ytd_source}','▤','#0f766e'),
        (f'JICT Market Share {year}',fmt(ms,digits=2),'%',f'Tanjung Priok · YTD {MONTHS[month-1]}','◉','#d97706'),
    ])
    if year != 2026:
        st.info('Annual Forecast 2026 / Budget 2026 / Actual 2025 cards and YTD shipping-line year columns are designed for 2026. Select 2026 for the intended comparison.')

    section('JICT Throughput Summary', 'Monthly volume comparison · TEU · Live from Throughput vs Budget')
    if not budget.empty:
        d = budget[budget['month'].between(1, 12) & budget['series'].isin(SERIES)].copy()
        d['Month'] = d['month'].astype(int).map(dict(enumerate(MONTHS, 1)))
        d = d.rename(columns={'series': 'Series', 'value': 'TEUs'}).dropna(subset=['TEUs'])
        if not d.empty:
            palette = alt.Scale(domain=SERIES, range=['#ef4444', '#16a34a', '#7e22ce'])
            bars = (alt.Chart(d).mark_bar().encode(
                x=alt.X('Month:N', sort=MONTHS, title=None, axis=alt.Axis(labelAngle=0)),
                xOffset=alt.XOffset('Series:N', sort=SERIES),
                y=alt.Y('TEUs:Q', title='Throughput (TEU)', axis=alt.Axis(format=',.0f')),
                color=alt.Color('Series:N', scale=palette, sort=SERIES, title=None),
                tooltip=[alt.Tooltip('Month:N'), alt.Tooltip('Series:N'), alt.Tooltip('TEUs:Q', format=',.2f')]
            ).properties(height=350))
            st.altair_chart(bars, use_container_width=True)

            monthly = d.pivot_table(index='Month', columns='Series', values='TEUs', aggfunc='sum').reindex(MONTHS)
            for series_name in SERIES:
                if series_name not in monthly.columns:
                    monthly[series_name] = float('nan')
            monthly = monthly[SERIES]
            def growth_series(numerator, denominator):
                return ((numerator / denominator) - 1) * 100.0
            table = monthly.copy()
            table['Change (%) 2026 vs 2025'] = growth_series(table['2026 (Forecast)'], table['2025 (Actual)'].replace(0, float('nan')))
            table['Change (%) 2026 vs Budget'] = growth_series(table['2026 (Forecast)'], table['Budget 2026'].replace(0, float('nan')))
            totals = monthly.sum(min_count=1)
            # Use annual official KPI figures for the total column when available.
            annuals = {'2025 (Actual)': actual25, 'Budget 2026': annual_budget26, '2026 (Forecast)': forecast}
            for label, official_value in annuals.items():
                if official_value is not None:
                    totals[label] = official_value
            total_row = totals.to_dict()
            total_row['Change (%) 2026 vs 2025'] = pct(totals['2026 (Forecast)'], totals['2025 (Actual)'])
            total_row['Change (%) 2026 vs Budget'] = pct(totals['2026 (Forecast)'], totals['Budget 2026'])
            table.loc['Total'] = total_row
            display = table.T
            display.index.name = 'Metric'
            display = display.reset_index()
            display = display.rename(columns={'2025 (Actual)': '2025 (Actual)', '2026 (Forecast)': '2026 (Forecast)'})
            formatted = display.copy()
            for month_label in MONTHS + ['Total']:
                formatted[month_label] = [
                    (f'{v:+.2f}%' if pd.notna(v) else '—') if str(metric).startswith('Change (%)')
                    else (f'{v:,.2f}'.rstrip('0').rstrip('.') if pd.notna(v) else '—')
                    for metric, v in zip(display['Metric'], display[month_label])
                ]
            st.caption('Monthly throughput and YoY / budget changes · Total growth is calculated from annual totals, not monthly percentage averages.')
            centered_dataframe(formatted, hide_index=True, use_container_width=True)
            with st.expander('Percentage change by month', expanded=False):
                change_long = table.loc[MONTHS, ['Change (%) 2026 vs 2025', 'Change (%) 2026 vs Budget']].reset_index().rename(columns={'Month': 'Month'})
                change_long = change_long.rename(columns={'index': 'Month'}).melt(id_vars='Month', var_name='Comparison', value_name='Change (%)').dropna()
                pct_chart = alt.Chart(change_long).mark_line(point=True, strokeWidth=2.5).encode(
                    x=alt.X('Month:N', sort=MONTHS, title=None),
                    y=alt.Y('Change (%):Q', title='Change (%)', axis=alt.Axis(format='+,.1f')),
                    color='Comparison:N', tooltip=['Month:N', 'Comparison:N', alt.Tooltip('Change (%):Q', format='+,.2f')]
                ).properties(height=200)
                st.altair_chart(pct_chart, use_container_width=True)
        else:
            st.info('Belum ada data throughput bulanan.')
    else:
        st.info('Belum ada data Throughput vs Budget.')

    # One consolidated market-share overview: current KPIs + YoY donuts + compact comparison.
    section(f'Tanjung Priok Market Share Overview · YTD {MONTHS[month-1]} {year}',
            f'Current market position and {year-1} vs {year} comparison · same YTD cutoff')
    if tp_total:
        share_cards = [
            ('Total Tanjung Priok', fmt(tp_total), 'TEU', f'Combined terminal throughput · YTD {MONTHS[month-1]}', '▦', '#2563eb'),
            ('JICT Throughput', fmt(jict), 'TEU', f'JICT volume · YTD {MONTHS[month-1]}', '▥', '#0d9488'),
            ('JICT Market Share', fmt(ms, digits=2), '%', 'Share of Tanjung Priok throughput', '◉', '#7c3aed'),
        ]
        st.markdown("""<style>
        .jict-share-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:10px 0 18px}
        .jict-share-card{position:relative;overflow:hidden;min-width:0;border:1px solid rgba(128,145,166,.25);
          border-radius:16px;background:var(--secondary-background-color,#f8fafc);
          padding:17px 19px;min-height:128px;box-shadow:0 3px 12px rgba(15,23,42,.04)}
        .jict-share-card:before{content:'';position:absolute;inset:0 auto 0 0;width:4px;background:var(--share-accent)}
        .jict-share-label{font-size:.83rem;font-weight:650;opacity:.8}
        .jict-share-value{font-size:clamp(1.4rem,2.3vw,2rem);font-weight:780;letter-spacing:-.035em;
          line-height:1.25;margin:12px 0 6px;overflow-wrap:anywhere}
        .jict-share-unit{font-size:.77rem;font-weight:600;opacity:.65;letter-spacing:0}
        .jict-share-note{font-size:.75rem;opacity:.7;line-height:1.4}
        @media(max-width:800px){.jict-share-grid{grid-template-columns:1fr}}
        </style>""", unsafe_allow_html=True)
        cards_html = []
        for label, value, unit, note, icon, accent in share_cards:
            cards_html.append(
                f'<div class="jict-share-card" style="--share-accent:{accent}">'
                f'<div class="jict-share-label">{escape(label)} <span style="float:right">{icon}</span></div>'
                f'<div class="jict-share-value">{escape(value)} <span class="jict-share-unit">{escape(unit)}</span></div>'
                f'<div class="jict-share-note">{escape(note)}</div></div>'
            )
        st.markdown('<div class="jict-share-grid">'+''.join(cards_html)+'</div>', unsafe_allow_html=True)
    else:
        st.info('Belum ada data market share untuk periode ini.')

    st.markdown(f'**Terminal Market Share · {year-1} vs {year}**')
    share_parts = []
    for yr, frame in [(year-1, prev_term), (year, current_term)]:
        if not frame.empty and frame['value'].sum() > 0:
            temp = frame.copy()
            temp['Year'] = str(yr)
            temp['Share (%)'] = temp['value'] / temp['value'].sum() * 100
            share_parts.append(temp)
    if share_parts:
        combined = pd.concat(share_parts, ignore_index=True)
        # Consistent colors across both donuts make changes easier to compare.
        terminal_colors = alt.Scale(domain=TERMINALS,
                                    range=['#1677b8','#f59e0b','#10b981','#8b5cf6','#ef6c63'])
        left, right = st.columns(2, gap='large')
        for col, yr in zip([left, right], [year-1, year]):
            d = combined[combined['Year'].eq(str(yr))].copy()
            with col:
                st.markdown(f'<div class="jict-comparison-heading">{yr} · YTD {MONTHS[month-1]}</div>', unsafe_allow_html=True)
                if d.empty:
                    st.info('Belum ada data untuk tahun ini.')
                    continue
                total = float(d['value'].sum())
                jict_share = float(d.loc[d['terminal'].eq('JICT'), 'Share (%)'].sum())
                st.markdown(f'<div class="jict-comparison-caption">Total terminal throughput: <b>{total:,.0f} TEU</b></div>',unsafe_allow_html=True)
                arc = alt.Chart(d).mark_arc(innerRadius=83, outerRadius=124, padAngle=0.018, cornerRadius=4).encode(
                    theta=alt.Theta('value:Q', stack=True),
                    color=alt.Color('terminal:N', scale=terminal_colors, sort=TERMINALS,
                                    legend=alt.Legend(title=None, orient='bottom', columns=3)),
                    tooltip=[alt.Tooltip('terminal:N',title='Terminal'),
                             alt.Tooltip('value:Q',title='YTD TEU',format=',.0f'),
                             alt.Tooltip('Share (%):Q',title='Share',format='.2f')]
                )
                center = alt.Chart(pd.DataFrame({'label':[f'{jict_share:.2f}%'], 'subtitle':['JICT SHARE']})).mark_text(
                    fontSize=23,fontWeight='bold',dy=-7,color='#1677b8').encode(text='label:N')
                subtitle = alt.Chart(pd.DataFrame({'label':['JICT SHARE']})).mark_text(
                    fontSize=10,dy=18,color='#64748b').encode(text='label:N')
                st.altair_chart((arc + center + subtitle).properties(height=300),use_container_width=True)
        # Comparison table highlights movement in percentage points, not volume growth.
        pivot = combined.pivot_table(index='terminal', columns='Year', values='Share (%)', aggfunc='sum')
        prev_col, now_col = str(year-1), str(year)
        if prev_col in pivot.columns and now_col in pivot.columns:
            pivot = pivot.reindex(TERMINALS).dropna(how='all').fillna(0)
            pivot['Change (pp)'] = pivot[now_col] - pivot[prev_col]
            jict_delta = float(pivot.loc['JICT','Change (pp)']) if 'JICT' in pivot.index else None
            # Compact side-by-side movement KPI and always-visible terminal figures.
            movement_col, figures_col = st.columns([1, 2.15], gap='medium')
            with movement_col:
                if jict_delta is not None:
                    sign = '+' if jict_delta > 0 else ''
                    direction = '▲' if jict_delta > 0 else ('▼' if jict_delta < 0 else '●')
                    color = '#15956c' if jict_delta > 0 else ('#db5b53' if jict_delta < 0 else '#64748b')
                    st.markdown(f'<div class="jict-share-delta"><div class="jict-share-delta-label">JICT market share movement · {year-1} → {year}</div><div class="jict-share-delta-value" style="color:{color}">{direction} {sign}{jict_delta:.2f} pp</div><div class="jict-share-delta-label">Percentage-point change at the same YTD cutoff</div></div>', unsafe_allow_html=True)
            with figures_col:
                # Native Streamlit table: reliable across themes/versions, no HTML/CSS dependency.
                volume_pivot = combined.pivot_table(
                    index='terminal', columns='Year', values='value', aggfunc='sum'
                )
                compact_rows = []
                for terminal in TERMINALS:
                    if terminal not in pivot.index and terminal not in volume_pivot.index:
                        continue
                    vol_old = float(volume_pivot.loc[terminal, prev_col]) if terminal in volume_pivot.index and prev_col in volume_pivot.columns and pd.notna(volume_pivot.loc[terminal, prev_col]) else 0.0
                    vol_new = float(volume_pivot.loc[terminal, now_col]) if terminal in volume_pivot.index and now_col in volume_pivot.columns and pd.notna(volume_pivot.loc[terminal, now_col]) else 0.0
                    share_old = float(pivot.loc[terminal, prev_col]) if terminal in pivot.index else 0.0
                    share_new = float(pivot.loc[terminal, now_col]) if terminal in pivot.index else 0.0
                    compact_rows.append({
                        'Terminal': terminal,
                        f'{year-1} (TEU)': vol_old,
                        f'{year-1} Share (%)': share_old,
                        f'{year} (TEU)': vol_new,
                        f'{year} Share (%)': share_new,
                        'Change (pp)': share_new - share_old,
                    })
                compact_rows.append({
                    'Terminal': 'TOTAL',
                    f'{year-1} (TEU)': float(combined.loc[combined['Year'].eq(prev_col), 'value'].sum()),
                    f'{year-1} Share (%)': 100.0,
                    f'{year} (TEU)': float(combined.loc[combined['Year'].eq(now_col), 'value'].sum()),
                    f'{year} Share (%)': 100.0,
                    'Change (pp)': 0.0,
                })
                st.markdown("**Terminal share · detailed figures**")
                st.dataframe(
                    pd.DataFrame(compact_rows),
                    hide_index=True,
                    use_container_width=True,
                    height=284,
                    column_config={
                        'Terminal': st.column_config.TextColumn('Terminal', width='small'),
                        f'{year-1} (TEU)': st.column_config.NumberColumn(f'{year-1} (TEU)', format='%,.0f'),
                        f'{year-1} Share (%)': st.column_config.NumberColumn(f'{year-1} Share (%)', format='%.2f%%'),
                        f'{year} (TEU)': st.column_config.NumberColumn(f'{year} (TEU)', format='%,.0f'),
                        f'{year} Share (%)': st.column_config.NumberColumn(f'{year} Share (%)', format='%.2f%%'),
                        'Change (pp)': st.column_config.NumberColumn('Δ pp', format='%+.2f'),
                    },
                )
        else:
            st.caption('Perbandingan perubahan market share tersedia setelah kedua tahun memiliki data.')
    else:
        st.info('Belum ada data market share untuk perbandingan tahun.')

    section(f'Shipping Line Share · YTD {MONTHS[month-1]} {year}', 'Pangsa shipping line berdasarkan Full + Empty; OTHERS tetap masuk total')
    if not ytd.empty and all(c in ytd for c in ['shipping_line','full_2026','empty_2026']):
        lines=ytd.copy()
        lines['TEUs']=num(lines,'full_2026').fillna(0)+num(lines,'empty_2026').fillna(0)
        lines=lines.groupby('shipping_line',as_index=False)['TEUs'].sum().sort_values('TEUs',ascending=False)
        if lines['TEUs'].sum()>0:
            lines['Share (%)']=lines['TEUs']/lines['TEUs'].sum()*100
            p1,p2=st.columns([1,1])
            with p1:
                st.altair_chart(alt.Chart(lines).mark_arc(innerRadius=65).encode(theta='TEUs:Q',color=alt.Color('shipping_line:N',title='Shipping Line'),tooltip=['shipping_line:N',alt.Tooltip('TEUs:Q',format=',.0f'),alt.Tooltip('Share (%):Q',format='.2f')]).properties(height=330),use_container_width=True)
            with p2:
                centered_dataframe(lines.rename(columns={'shipping_line':'Shipping Line'}).style.format({'TEUs':'{:,.0f}','Share (%)':'{:.2f}%'}),hide_index=True,use_container_width=True,height=330)
            if ytd_volume is not None and abs(lines['TEUs'].sum()-ytd_volume)>0.01:
                st.warning(f'Reconciliation: total shipping-line detail {lines["TEUs"].sum():,.2f} vs {ytd_source} {ytd_volume:,.2f} TEU.')
        else: st.info('Volume shipping line belum diisi.')
    else: st.info('Belum ada data Shipping Line YTD untuk bulan ini.')

    section('Top 10 Shipping Lines and Volume', 'Ranking berdasarkan YTD 2026 Full + Empty · OTHERS tidak masuk ranking')
    if not ytd.empty and all(c in ytd for c in ['shipping_line','full_2026','empty_2026']):
        rank=ytd.copy()
        rank['TEUs']=num(rank,'full_2026').fillna(0)+num(rank,'empty_2026').fillna(0)
        rank=rank.groupby('shipping_line',as_index=False)['TEUs'].sum()
        rank=rank[~rank['shipping_line'].astype(str).str.strip().str.upper().eq('OTHERS')]
        rank=rank[rank['TEUs']>0].nlargest(10,'TEUs').sort_values('TEUs')
        if not rank.empty:
            # Keep both views tied to the exact same YTD ranking dataset.
            rank_display = rank.sort_values('TEUs', ascending=False).reset_index(drop=True)
            rank_display.insert(0, 'Rank', range(1, len(rank_display) + 1))
            chart_col, table_col = st.columns([1.65, 1], gap='medium')
            with chart_col:
                st.altair_chart(alt.Chart(rank).mark_bar(cornerRadiusEnd=4,color='#2474B5').encode(
                    y=alt.Y('shipping_line:N',sort=rank['shipping_line'].tolist(),title=None),
                    x=alt.X('TEUs:Q',title='YTD TEUs'),
                    tooltip=['shipping_line:N',alt.Tooltip('TEUs:Q',format=',.2f')]
                ).properties(height=340),use_container_width=True)
            with table_col:
                st.markdown('**Top 10 · Volume Detail**')
                centered_dataframe(
                    rank_display.rename(columns={'shipping_line': 'Shipping Line', 'TEUs': 'Volume (TEU)'}),
                    hide_index=True,
                    use_container_width=True,
                    height=340,
                    column_config={
                        'Rank': st.column_config.NumberColumn('#', format='%d', width='small'),
                        'Shipping Line': st.column_config.TextColumn('Shipping Line', width='medium'),
                        'Volume (TEU)': st.column_config.NumberColumn('Volume (TEU)', format='%,.2f', width='medium'),
                    },
                )
        else: st.info('Belum ada data ranking.')
    else: st.info('Belum ada data ranking Shipping Line.')

    section('Gross Crane Rate & Vessel Operating Rate', f'Operational Performance · {year}')
    if not operational.empty:
        op=operational[operational['metric'].isin(['Gross QC Rate','Vess. Op. Rate']) & operational['month'].between(1,12)].dropna(subset=['value']).copy()
        if not op.empty:
            op['Month']=op['month'].astype(int).map(dict(enumerate(MONTHS,1)))
            op=op.rename(columns={'metric':'Series','value':'Rate'})
            left,right=st.columns([2.1,1],gap='medium')
            with left:
                st.altair_chart(chart(op,y='Rate',order=MONTHS),use_container_width=True)
            with right:
                st.markdown('**Monthly YTD · GCR / VOR**')
                _operational_ytd_table(op,month,'Rate',['Gross QC Rate','Vess. Op. Rate'],'gcr_vor',mode='average',unit='Rate')
            a,b=st.columns(2)
            for col,name in zip([a,b],['Gross QC Rate','Vess. Op. Rate']):
                vals=op.loc[op['Series'].eq(name)&op['month'].le(month),'Rate']
                col.metric(f'{name} · Average YTD',fmt(vals.mean(),digits=2) if not vals.empty else '—')
        else: st.info('Belum ada data GCR/VOR.')
    else: st.info('Belum ada data GCR/VOR.')

    section(f'Dwelling Time · {year}', 'Import Full, Export Full, Overall · days · Average YTD excludes missing months')
    if not operational.empty:
        dwell=operational[operational['metric'].isin(['Import Full','Export Full','Overall'])&operational['month'].between(1,12)].dropna(subset=['value']).copy()
        if not dwell.empty:
            dwell['Month']=dwell['month'].astype(int).map(dict(enumerate(MONTHS,1)))
            dwell=dwell.rename(columns={'metric':'Series','value':'Days'})
            left,right=st.columns([2.1,1],gap='medium')
            with left:
                st.altair_chart(chart(dwell,y='Days',order=MONTHS),use_container_width=True)
            with right:
                st.markdown('**Monthly YTD · Dwelling Time**')
                _operational_ytd_table(dwell,month,'Days',['Export Full','Import Full','Overall'],'dwelling',mode='average',unit='Days')
            cols=st.columns(3)
            for col,name in zip(cols,['Import Full','Export Full','Overall']):
                vals=dwell.loc[dwell['Series'].eq(name)&dwell['month'].le(month),'Days']
                col.metric(f'{name} · Average YTD',fmt(vals.mean(),' days',2) if not vals.empty else '—')
        else: st.info('Belum ada data Dwelling.')
    else: st.info('Belum ada data Dwelling.')

    section('Divert · To Koja vs From Koja', f'Operational Performance · {year}')
    if not divert.empty and all(c in divert for c in ['month','to_koja','from_koja']):
        d=divert[divert['month'].between(1,12)].copy()
        for c in ['to_koja','from_koja']: d[c]=num(d,c).fillna(0)
        d=d.groupby('month',as_index=False)[['to_koja','from_koja']].sum()
        d['Month']=d['month'].astype(int).map(dict(enumerate(MONTHS,1)))
        d=d.melt(id_vars=['month','Month'],value_vars=['to_koja','from_koja'],var_name='Series',value_name='TEUs')
        d['Series']=d['Series'].map({'to_koja':'To Koja','from_koja':'From Koja'})
        if not d.empty:
            left,right=st.columns([2.1,1],gap='medium')
            with left:
                st.altair_chart(chart(d,kind='bar',order=MONTHS),use_container_width=True)
            with right:
                st.markdown('**Monthly YTD · Divert (TEU)**')
                _operational_ytd_table(d,month,'TEUs',['To Koja','From Koja'],'divert',mode='sum',unit='TEU')
    else: st.info('Belum ada data Divert.')

    st.caption('Data sources: throughput_budget_2526 · throughput · throughput_shipping_official_kpi · ytd_shipping_lines · ytd_shipping_official_totals · operational_monthly_metrics · operational_divert. All charts use calendar month order. Missing values are not silently replaced with forecasts.')
