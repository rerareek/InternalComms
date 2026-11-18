"""Commercial Meeting generator. Keeps original JICT deck; updates only verified data.
Slides without mapped datasets remain historical and are clearly labeled.
"""
from io import BytesIO
from pathlib import Path
import calendar
import pandas as pd
import streamlit as st
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# Resolve relative to this module, independent of Streamlit's working directory.
TEMPLATE = Path(__file__).resolve().parent / 'assets' / 'templates' / 'commercial_meeting_hpi.pptx'

NAVY = RGBColor(27, 43, 76)


def fetch(sb, table, columns='*'):
    records=[]
    offset=0
    while True:
        batch=sb.table(table).select(columns).range(offset, offset+999).execute().data or []
        records.extend(batch)
        if len(batch)<1000: break
        offset+=1000
    return pd.DataFrame(records)


def _label(slide, text, x=0.5, y=6.95, w=11.8):
    box=slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(.28))
    p=box.text_frame.paragraphs[0]
    p.text=text
    p.font.name='Arial';p.font.size=Pt(10);p.font.bold=True
    p.font.color.rgb=RGBColor(158, 57, 40)


def _table(slide, headings, rows, x, y, w, h):
    table=slide.shapes.add_table(len(rows)+1,len(headings), Inches(x), Inches(y), Inches(w), Inches(h)).table
    for j,heading in enumerate(headings):
        cell=table.cell(0,j);cell.text=str(heading);cell.fill.solid();cell.fill.fore_color.rgb=NAVY
    for i,row in enumerate(rows,1):
        for j,value in enumerate(row):
            cell=table.cell(i,j);cell.text=str(value)
            if i%2==0:
                cell.fill.solid();cell.fill.fore_color.rgb=RGBColor(239,243,249)
    for i in range(len(rows)+1):
        for j in range(len(headings)):
            for p in table.cell(i,j).text_frame.paragraphs:
                p.font.name='Arial';p.font.size=Pt(10 if len(rows)>9 else 12)
                p.font.color.rgb=RGBColor(255,255,255) if i==0 else NAVY
                p.font.bold=(i==0)
    return table


def _remove_picture(slide):
    # Replace only the largest picture (data graphic); retain all other branding and shapes.
    pics=[s for s in slide.shapes if s.shape_type==13]
    if not pics: return None
    target=max(pics,key=lambda s:s.width*s.height)
    bounds=(target.left/Inches(1),target.top/Inches(1),target.width/Inches(1),target.height/Inches(1))
    target._element.getparent().remove(target._element)
    return bounds


def _replace_month_titles(slide, month, year):
    # Titles only on slides whose data are actually refreshed.
    import re
    for shape in slide.shapes:
        if not shape.has_text_frame: continue
        for paragraph in shape.text_frame.paragraphs:
            for run in paragraph.runs:
                if run.text:
                    run.text=re.sub(r'(?i)OCTOBER\s+2026',f'{calendar.month_name[month].upper()} {year}',run.text)
                    run.text=re.sub(r'(?i)OCTOBER\s+2025',f'{calendar.month_name[month].upper()} {year-1}',run.text)


def _terminal_data(sb, year, month):
    df=fetch(sb,'throughput','year,month,terminal,value')
    if df.empty: raise ValueError('Terminal throughput table has no records.')
    for col in ['year','month','value']:
        df[col]=pd.to_numeric(df[col],errors='coerce')
    if df[['year','month','value']].isna().any().any():
        raise ValueError('Terminal throughput contains invalid year, month, or volume values.')
    if df.duplicated(['year','month','terminal']).any():
        raise ValueError('Duplicate terminal/year/month records found.')
    required=[(year,month),(year-1,month),(year-1,12),(year-2,12)]
    for yr,end in required:
        months=set(df.loc[df.year.eq(yr),'month'].astype(int))
        if not set(range(1,end+1)).issubset(months):
            raise ValueError(f'Incomplete terminal records for {yr} Jan–{calendar.month_abbr[end]}.')
    terminals=sorted(df.terminal.dropna().unique())
    rows=[]
    for terminal in terminals:
        d=df[df.terminal.eq(terminal)]
        def total(yr,end):return d.loc[d.year.eq(yr)&d.month.between(1,end),'value'].sum()
        curr,prior,fullprev,fullprev2=total(year,month),total(year-1,month),total(year-1,12),total(year-2,12)
        rows.append([terminal,*(f'{v:,.0f}' for v in [curr,prior,fullprev,fullprev2]),
                     f'{curr-prior:+,.0f}',f'{(curr/prior-1)*100:+.1f}%' if prior else 'N/A'])
    return rows


def _budget_data(sb, year):
    if year!=2026: raise ValueError('Budget table currently contains only 2025/2026 series. Select 2026.')
    df=fetch(sb,'throughput_budget_2526','series,month,value')
    if df.empty: raise ValueError('Budget table is empty.')
    df['month']=pd.to_numeric(df.month,errors='coerce')
    df['value']=pd.to_numeric(df.value,errors='coerce')
    if df[['month','value']].isna().any().any():raise ValueError('Budget table contains invalid values.')
    series=['2025 (Actual)','Budget 2026','2026 (Forecast)']
    for s in series:
        subset=df[df.series.eq(s)]
        if subset.month.duplicated().any() or set(subset.month.astype(int))!=set(range(1,13)):
            raise ValueError(f'Missing or duplicate months for {s}.')
    rows=[]
    for s in series:
        total=df[df.series.eq(s)].value.sum()
        rows.append([s,f'{total:,.0f} TEU'])
    return rows


def generate(sb, year, month, meeting_date):
    if not TEMPLATE.is_file():
        raise FileNotFoundError(
            f'Commercial Meeting master template missing at: {TEMPLATE}. '
            'Upload assets/templates/commercial_meeting_hpi.pptx to the same GitHub '
            'repository directory as monthly_presentation.py. Git LFS pointer files '
            'are not supported as PowerPoint templates.'
        )
    # Preflight: don't generate a falsely current deck when a key source is incomplete.
    terminals=_terminal_data(sb,year,month)
    budget=_budget_data(sb,year)
    prs=Presentation(str(TEMPLATE))
    if len(prs.slides)!=11:raise ValueError('Expected 11 slides in the master template.')
    # Cover: update date with a new editable overlay; original title/art remain intact.
    cover=prs.slides[0]
    cover.shapes.add_textbox(Inches(0.8), Inches(6.85), Inches(10), Inches(.3)).text_frame.text=(
        f'Generated report: {meeting_date:%d %B %Y} | YTD {calendar.month_name[month]} {year}')
    # Slide 2: replace terminal data graphic with editable PowerPoint table.
    slide=prs.slides[1]
    bounds=_remove_picture(slide)
    if not bounds:raise ValueError('Terminal slide graphic not found.')
    x,y,w,h=bounds
    headings=['Terminal',f'YTD {year}',f'YTD {year-1}',f'FY {year-1}',f'FY {year-2}','YoY TEU','Growth']
    _table(slide,headings,terminals,max(.25,x),max(1.25,y),min(12.7,w),min(5.3,max(2.4,h)))
    _label(slide,'LIVE DATA · Terminal throughput · TEU; values validated for complete reporting periods')
    # Slide 3: replace old visual with editable summary table.
    slide=prs.slides[2]
    bounds=_remove_picture(slide)
    if not bounds:raise ValueError('Summary slide graphic not found.')
    x,y,w,h=bounds
    _table(slide,['Series','Full year volume'],budget,max(.7,x),max(2,y),min(10,w),min(2.4,max(1.7,h)))
    _label(slide,'LIVE DATA · 2026 forecast/budget and 2025 actual · not 2026 actual')
    # Remove old hard-coded notes on slide 3 (old values would contradict live data).
    for shape in list(slide.shapes):
        if shape.has_text_frame and ('2,288,737' in shape.text or '2.241.000' in shape.text or '2.192.305' in shape.text):
            shape._element.getparent().remove(shape._element)
    # Unmapped slides are left unchanged and explicitly marked as historical reference.
    for i in [3,4,5,6,7,9,10]:
        _label(prs.slides[i], 'REFERENCE SLIDE · Original template content; NOT refreshed for selected period')
    output=BytesIO();prs.save(output);return output.getvalue()


def render(sb):
    st.header('Monthly Presentation Generator')
    st.caption('Commercial Meeting HPI · Uses your original 11-slide JICT PowerPoint template.')
    c1,c2,c3=st.columns(3)
    with c1:year=st.selectbox('Reporting year',[2026],index=0)
    with c2:month=st.selectbox('YTD cutoff month',range(1,13),index=9,format_func=lambda m:calendar.month_name[m])
    with c3:meeting_date=st.date_input('Meeting date')
    st.info('Slides 2 and 3 use validated Supabase data and editable PowerPoint tables. '
            'Slides 4–8 and 10–11 retain their original reference content, explicitly marked as not refreshed. '
            'Slide 9 remains unchanged. This version does not automatically update all charts or notes.')
    st.caption('Slide 3 follows the source presentation: Forecast 2026, Budget 2026, Actual 2025. '
               'Actual 2026 is not substituted for the historical baseline.')
    if st.button('Prepare PowerPoint',type='primary'):
        try:
            st.session_state['commercial_pptx_bytes']=generate(sb,year,month,meeting_date)
            st.session_state['commercial_pptx_name']=f'Commercial_Meeting_HPI_YTD_{calendar.month_name[month]}_{year}.pptx'
            st.success('Presentation generated. Review the reference slides before distribution.')
        except Exception as exc:
            st.session_state.pop('commercial_pptx_bytes',None)
            st.error(f'Could not generate report: {exc}')
    if 'commercial_pptx_bytes' in st.session_state:
        st.download_button('Download PPTX',st.session_state['commercial_pptx_bytes'],
            file_name=st.session_state['commercial_pptx_name'],
            mime='application/vnd.openxmlformats-officedocument.presentationml.presentation')
