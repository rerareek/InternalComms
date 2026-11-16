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


def render(sb):
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
            st.dataframe(formatted, hide_index=True, use_container_width=True)
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

    section(f'Tanjung Priok Market Share · YTD {MONTHS[month-1]} {year}',
            'Terminal throughput: JICT, TPK KOJA, MAL, TO3, NPCT1')
    if tp_total:
        # A single aligned KPI row prevents the tall stack of st.metric widgets
        # from leaving a large empty region beside the market-share donut.
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

        left, right = st.columns([1.05, 1], gap='medium', vertical_alignment='top')
        with left:
            st.markdown('**Terminal Breakdown · YTD TEU**')
            breakdown = current_term.rename(columns={'terminal':'Terminal','value':'YTD TEU'}).copy()
            breakdown['Share (%)'] = breakdown['YTD TEU'] / tp_total * 100
            breakdown['YTD TEU'] = breakdown['YTD TEU'].map(lambda v: f'{v:,.0f}')
            breakdown['Share (%)'] = breakdown['Share (%)'].map(lambda v: f'{v:.2f}%')
            st.dataframe(breakdown, hide_index=True, use_container_width=True, height=260)
        with right:
            st.markdown('**Market Share Distribution**')
            pie = alt.Chart(current_term).mark_arc(innerRadius=75, outerRadius=116).encode(
                theta=alt.Theta('value:Q'),
                color=alt.Color('terminal:N', title='Terminal', sort=TERMINALS),
                tooltip=[alt.Tooltip('terminal:N', title='Terminal'), alt.Tooltip('value:Q', title='YTD TEU', format=',.0f')]
            ).properties(height=260)
            st.altair_chart(pie, use_container_width=True)
    else:
        st.info('Belum ada data market share untuk periode ini.')

    section(f'Market Share Tanjung Priok · {year-1} vs {year}', 'Perbandingan YTD dengan cutoff bulan yang sama')
    share_parts=[]
    for yr,frame in [(year-1,prev_term),(year,current_term)]:
        if not frame.empty and frame['value'].sum()>0:
            temp=frame.copy(); temp['Year']=str(yr);temp['Share (%)']=temp['value']/temp['value'].sum()*100
            share_parts.append(temp)
    if share_parts:
        combined=pd.concat(share_parts,ignore_index=True)
        cols=st.columns(2)
        for col,yr in zip(cols,[year-1,year]):
            d=combined[combined['Year'].eq(str(yr))]
            with col:
                st.markdown(f'**{yr} YTD**')
                if d.empty: st.info('Belum ada data.')
                else:
                    st.altair_chart(alt.Chart(d).mark_arc(innerRadius=45).encode(theta='value:Q',color='terminal:N',tooltip=['terminal:N',alt.Tooltip('Share (%):Q',format='.2f')]).properties(height=235),use_container_width=True)
    else: st.info('Belum ada data market share 2025/2026.')

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
                st.dataframe(lines.rename(columns={'shipping_line':'Shipping Line'}).style.format({'TEUs':'{:,.0f}','Share (%)':'{:.2f}%'}),hide_index=True,use_container_width=True,height=330)
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
            st.altair_chart(alt.Chart(rank).mark_bar(cornerRadiusEnd=4,color='#2474B5').encode(
                y=alt.Y('shipping_line:N',sort=rank['shipping_line'].tolist(),title=None),
                x=alt.X('TEUs:Q',title='YTD TEUs'),tooltip=['shipping_line:N',alt.Tooltip('TEUs:Q',format=',.2f')]
            ).properties(height=340),use_container_width=True)
        else: st.info('Belum ada data ranking.')
    else: st.info('Belum ada data ranking Shipping Line.')

    section('Gross Crane Rate & Vessel Operating Rate', f'Operational Performance · {year}')
    if not operational.empty:
        op=operational[operational['metric'].isin(['Gross QC Rate','Vess. Op. Rate']) & operational['month'].between(1,12)].dropna(subset=['value']).copy()
        if not op.empty:
            op['Month']=op['month'].astype(int).map(dict(enumerate(MONTHS,1)))
            op=op.rename(columns={'metric':'Series','value':'Rate'})
            st.altair_chart(chart(op,y='Rate',order=MONTHS),use_container_width=True)
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
            st.altair_chart(chart(dwell,y='Days',order=MONTHS),use_container_width=True)
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
        d=d.melt(id_vars='Month',value_vars=['to_koja','from_koja'],var_name='Series',value_name='TEUs')
        if not d.empty: st.altair_chart(chart(d,kind='bar',order=MONTHS),use_container_width=True)
    else: st.info('Belum ada data Divert.')

    st.caption('Data sources: throughput_budget_2526 · throughput · throughput_shipping_official_kpi · ytd_shipping_lines · ytd_shipping_official_totals · operational_monthly_metrics · operational_divert. All charts use calendar month order. Missing values are not silently replaced with forecasts.')
