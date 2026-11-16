from centered_tables import centered_dataframe
"""Shipping Data Maintenence — editable shipping service master data."""
import pandas as pd
import streamlit as st
from supabase import create_client

TABLE = 'shipping_data_maintenance'
COLUMNS = ['no','service_name','consortium','window','loa','berth','ave_volume_per_call','port_rotation','phase_in','phase_out','remark']
LABELS = {'no':'NO','service_name':'SERVICE NAME','consortium':'CONSORTIUM','window':'WINDOW','loa':'LOA','berth':'BERTH','ave_volume_per_call':'AVE VOLUME PER CALL','port_rotation':'PORT ROTATION','phase_in':'PHASE IN','phase_out':'PHASE OUT','remark':'REMARK'}

@st.cache_resource
def _client():
    return create_client(st.secrets['supabase']['url'],st.secrets['supabase']['key'])

def _load():
    return pd.DataFrame(_client().table(TABLE).select('*').order('sort_order').execute().data or [])

def render():
    st.title('Shipping Data Maintenence')
    st.caption('Shipping service master data · Consortium · Berthing window · Port rotation · Phase in/out')
    try:
        original=_load()
    except Exception as exc:
        st.error('Shipping data table is unavailable. Run shipping_data_maintenance.sql in Supabase SQL Editor first.')
        st.code(str(exc))
        return
    df=original.reindex(columns=COLUMNS).copy()
    df['no']=pd.to_numeric(df['no'],errors='coerce').astype('Int64')
    for col in COLUMNS[1:]:
        df[col]=df[col].fillna('').astype(str)
    overview,editor=st.tabs(['Shipping Service Overview','Input Data'])
    with overview:
        c1,c2,c3=st.columns(3)
        c1.metric('Total Service Records',len(df))
        c2.metric('North Berth',int(df['berth'].str.upper().eq('NORTH').sum()))
        c3.metric('West Berth',int(df['berth'].str.upper().eq('WEST').sum()))
        a,b=st.columns([2,1])
        search=a.text_input('Search services, consortium, rotation or remarks',key='ship_maintenance_search')
        berth=b.selectbox('Berth',['All','NORTH','WEST'],key='ship_maintenance_berth')
        shown=df.copy()
        if search.strip():
            mask=shown.fillna('').astype(str).apply(lambda col:col.str.contains(search.strip(),case=False,regex=False)).any(axis=1)
            shown=shown.loc[mask]
        if berth!='All':
            shown=shown.loc[shown['berth'].str.upper().eq(berth)]
        centered_dataframe(shown.rename(columns=LABELS),hide_index=True,use_container_width=True,height=530,
                     column_config={'NO':st.column_config.NumberColumn('NO',format='%d')})
        st.download_button('Download Excel-compatible CSV',shown.rename(columns=LABELS).to_csv(index=False).encode('utf-8-sig'),
                           file_name='shipping_data_maintenance.csv',mime='text/csv')
    with editor:
        st.info('Edit records, add rows, or delete rows. Click Save Changes to write to Supabase. Deleting a row here removes it from the database after saving.')
        config={'no':st.column_config.NumberColumn('NO',min_value=1,step=1,format='%d'),
                'service_name':st.column_config.TextColumn('SERVICE NAME',required=True),
                'port_rotation':st.column_config.TextColumn('PORT ROTATION',width='large'),
                'phase_in':st.column_config.TextColumn('PHASE IN',width='large'),
                'phase_out':st.column_config.TextColumn('PHASE OUT',width='large'),
                'remark':st.column_config.TextColumn('REMARK',width='large')}
        edited=st.data_editor(df,hide_index=True,num_rows='dynamic',use_container_width=True,height=580,
                              column_config=config,key='shipping_maintenance_editor')
        if st.button('Save Changes',type='primary',key='shipping_maintenance_save'):
            clean=edited.copy()
            clean['service_name']=clean['service_name'].fillna('').astype(str).str.strip()
            clean=clean.loc[clean['service_name'].ne('')]
            if clean['service_name'].duplicated().any():
                st.error('SERVICE NAME must be unique. Please fix duplicate names before saving.')
                return
            rows=[]
            for index,(_,r) in enumerate(clean.iterrows()):
                row={col:(None if pd.isna(r[col]) else int(r[col])) if col=='no' else ('' if pd.isna(r[col]) else str(r[col]).strip()) for col in COLUMNS}
                row['sort_order']=index
                rows.append(row)
            try:
                sb=_client()
                if rows:
                    sb.table(TABLE).upsert(rows,on_conflict='service_name').execute()
                old=set(original.get('service_name',pd.Series(dtype=str)).dropna().astype(str))
                new={r['service_name'] for r in rows}
                for removed in old-new:
                    sb.table(TABLE).delete().eq('service_name',removed).execute()
                st.success('Shipping service records saved.')
                st.rerun()
            except Exception as exc:
                st.error(f'Save failed: {exc}')
