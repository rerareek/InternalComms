"""Profiling Incentives: interactive shipping line profiles, incentives and tariffs."""
import pandas as pd
import altair as alt
import streamlit as st
from supabase import create_client

@st.cache_resource
def _client():
    return create_client(st.secrets['supabase']['url'], st.secrets['supabase']['key'])

def _read(table):
    return pd.DataFrame(_client().table(table).select('*').execute().data or [])

def _money(v):
    return f"${float(v):,.0f}" if pd.notna(v) else '—'

def _number(v):
    return f"{float(v):,.0f}" if pd.notna(v) else '—'

def _editor(df, table, cols, key, numeric=(), height=360, required=()):
    base=df.reindex(columns=cols).copy()
    for c in numeric:
        base[c]=pd.to_numeric(base[c],errors='coerce')
    for c in cols:
        if c not in numeric:base[c]=base[c].fillna('').astype(str)
    config={c:st.column_config.NumberColumn(c.replace('_',' ').title(),format='%.2f') for c in numeric}
    for c in required:config[c]=st.column_config.TextColumn(c.replace('_',' ').title(),required=True)
    edited=st.data_editor(base,num_rows='dynamic',hide_index=True,use_container_width=True,height=height,
                          column_config=config,key=key)
    if st.button('Save '+table.replace('_',' ').title(),type='primary',key='save_'+key):
        rows=[]
        for _,r in edited.iterrows():
            item={}
            for c in cols:
                v=r.get(c)
                item[c]=None if c in numeric and pd.isna(v) else (float(v) if c in numeric else '' if pd.isna(v) else str(v).strip())
            if all(item.get(c) for c in required):rows.append(item)
        try:
            sb=_client()
            if table=='incentive_profiles':
                if len({r['profile_id'] for r in rows})!=len(rows):
                    st.error('Profile IDs must be unique.');return
                if rows:sb.table(table).upsert(rows,on_conflict='profile_id').execute()
                old=set(df.get('profile_id',pd.Series(dtype=str)).dropna().astype(str))
                new={r['profile_id'] for r in rows}
                for removed in old-new:sb.table(table).delete().eq('profile_id',removed).execute()
            else:
                # Existing identity IDs are retained; new rows have no ID.
                oldids=set(pd.to_numeric(df.get('id',pd.Series(dtype=float)),errors='coerce').dropna().astype(int))
                newids=set()
                for r in rows:
                    idval=r.get('id')
                    if idval is None:r.pop('id',None)
                    else:newids.add(int(idval));r['id']=int(idval)
                if rows:sb.table(table).upsert(rows,on_conflict='id').execute()
                for removed in oldids-newids:sb.table(table).delete().eq('id',int(removed)).execute()
            st.success('Saved to Supabase.');st.rerun()
        except Exception as e:st.error(f'Save failed: {e}')

def render():
    st.subheader('Profiling Incentives')
    st.caption('Shipping line incentives · Seaside revenue · Rebate · Tariff reference')
    try:
        profiles=_read('incentive_profiles');benefits=_read('incentive_benefits');tariffs=_read('incentive_tariffs')
    except Exception as exc:
        st.error('Profiling tables are not available. Run profiling_incentives_schema.sql first.')
        st.code(str(exc));return
    if profiles.empty:
        st.info('No profiles yet. Run the optional seed SQL or add records in Edit Data.')
    for c in ['volume_teu','seaside_revenue_usd','rebate_usd','rebate_pct']:
        if c in profiles:profiles[c]=pd.to_numeric(profiles[c],errors='coerce')
    if 'shipping_line' in profiles and profiles['shipping_line'].duplicated().any():
        st.warning('Duplicate shipping line names exist in the source. Entries remain separate for review; totals below are source-record totals, not deduplicated totals.')
    overview,detail,tariff_tab,edit=st.tabs(['Overview','Shipping Line Profiles','Tariff Reference','Edit Data'])
    with overview:
        if not profiles.empty:
            c1,c2,c3,c4=st.columns(4)
            c1.metric('Source Profiles',len(profiles))
            c2.metric('Total Volume',_number(profiles['volume_teu'].sum())+' TEU')
            c3.metric('Seaside Revenue',_money(profiles['seaside_revenue_usd'].sum()))
            c4.metric('Total Rebate',_money(profiles['rebate_usd'].sum()))
            st.caption('Totals sum source profiles, including any duplicate entries; verify duplicates before using for financial reporting.')
            chart=profiles[['shipping_line','rebate_usd','profile_id']].dropna(subset=['rebate_usd']).copy()
            chart['Shipping Line']=chart['shipping_line']+' · '+chart['profile_id']
            st.markdown('#### Rebate by Shipping Line')
            st.altair_chart(alt.Chart(chart).mark_bar(cornerRadiusEnd=5).encode(
                y=alt.Y('Shipping Line:N',sort='-x',title=None),
                x=alt.X('rebate_usd:Q',title='Rebate (USD)'),
                tooltip=['shipping_line:N','profile_id:N',alt.Tooltip('rebate_usd:Q',format=',.0f')]
            ).properties(height=max(280,len(chart)*32)),use_container_width=True)
            st.markdown('#### Incentive Profile Summary')
            summary=profiles[['shipping_line','volume_teu','seaside_revenue_usd','rebate_usd','rebate_pct']].copy()
            st.dataframe(summary.rename(columns={'shipping_line':'Shipping Line','volume_teu':'Volume (TEU)','seaside_revenue_usd':'Seaside Revenue (USD)','rebate_usd':'Rebate (USD)','rebate_pct':'Rebate (%)'}),hide_index=True,use_container_width=True)
    with detail:
        if not profiles.empty:
            options={f"{r['shipping_line']} · {r['profile_id']}":r['profile_id'] for _,r in profiles.iterrows()}
            chosen=st.selectbox('Select Shipping Line',list(options),key='incentive_profile_selection')
            profile=profiles.loc[profiles['profile_id'].eq(options[chosen])].iloc[0]
            a,b,c,d=st.columns(4)
            a.metric('Volume',_number(profile['volume_teu'])+' TEU')
            b.metric('Seaside Revenue',_money(profile['seaside_revenue_usd']))
            c.metric('Rebate',_money(profile['rebate_usd']))
            d.metric('Rebate / Revenue',f"{profile['rebate_pct']:.2f}%" if pd.notna(profile['rebate_pct']) else '—')
            if profile.get('notes'):st.info(profile['notes'])
            st.divider()
            selected=benefits[benefits['profile_id'].eq(options[chosen])] if not benefits.empty else pd.DataFrame()
            for group in ['Annual','Quarterly','Other']:
                st.markdown('#### '+group+' Incentives')
                rows=selected[selected['category'].str.casefold().eq(group.casefold())] if not selected.empty else pd.DataFrame()
                if rows.empty:st.caption('No entries recorded.')
                else:
                    st.dataframe(rows[['description','discount_text','amount_usd','amount_note']].rename(columns={'description':'Benefit / Incentive','discount_text':'Discount','amount_usd':'Amount (USD)','amount_note':'Source Note'}),hide_index=True,use_container_width=True)
    with tariff_tab:
        st.caption('Tariffs are reference rates, separate from incentive amounts. Currency is shown explicitly.')
        if not tariffs.empty:
            for curr in ['USD','IDR']:
                st.markdown('#### '+curr+' Tariffs')
                rows=tariffs[tariffs['currency'].eq(curr)]
                if not rows.empty:st.dataframe(rows[['category','description','rate_20','rate_40']].rename(columns={'category':'Category','description':'Description','rate_20':"20'",'rate_40':"40'"}),hide_index=True,use_container_width=True)
    with edit:
        st.info('Editable source records. Changes take effect after Save. Deleting a profile also deletes its linked incentive details.')
        t1,t2,t3=st.tabs(['Profiles','Incentive Items','Tariff Rates'])
        with t1:_editor(profiles,'incentive_profiles',['profile_id','shipping_line','source_column','volume_teu','seaside_revenue_usd','rebate_usd','rebate_pct','notes'],'profiles_editor',numeric=['source_column','volume_teu','seaside_revenue_usd','rebate_usd','rebate_pct'],required=['profile_id','shipping_line'])
        with t2:_editor(benefits,'incentive_benefits',['id','profile_id','sort_order','category','description','discount_text','amount_usd','amount_note'],'benefits_editor',numeric=['id','sort_order','amount_usd'],required=['profile_id','description'])
        with t3:_editor(tariffs,'incentive_tariffs',['id','currency','category','description','rate_20','rate_40','sort_order'],'tariffs_editor',numeric=['id','rate_20','rate_40','sort_order'],required=['currency','description'])
