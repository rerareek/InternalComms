import hmac
from datetime import date

import pandas as pd
import streamlit as st
from supabase import Client, create_client

LOCATIONS = ["In JICT", "Out JICT"]
# Isi daftar PIC default di sini. PIC baru yang pernah diinput otomatis muncul juga.
DEFAULT_PICS = ["PIC 1", "PIC 2", "PIC 3"]

st.set_page_config(page_title="Log Book Meeting", page_icon="📒", layout="wide")


# ---------- Login ----------
def require_login():
    if st.session_state.get("auth"):
        return
    st.title("📒 Log Book Meeting")
    pw = st.text_input("Password", type="password")
    if st.button("Masuk", type="primary"):
        if hmac.compare_digest(pw, st.secrets["app_password"]):
            st.session_state["auth"] = True
            st.rerun()
        else:
            st.error("Password salah.")
    st.stop()


# ---------- Supabase ----------
@st.cache_resource
def get_client() -> Client:
    return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])


sb = None  # diisi setelah login


def load_df() -> pd.DataFrame:
    res = (
        sb.table("meetings")
        .select("*")
        .order("meeting_date", desc=True)
        .order("id", desc=True)
        .execute()
    )
    df = pd.DataFrame(res.data)
    if not df.empty:
        df["meeting_date"] = pd.to_datetime(df["meeting_date"]).dt.date
    return df


def payload(d, loc, who, pics, agenda, discussion):
    return {
        "meeting_date": d.isoformat(),
        "location": loc,
        "with_whom": who,
        "pics": ", ".join(pics),
        "agenda": agenda,
        "discussion": discussion,
    }


def insert_row(*args):
    sb.table("meetings").insert(payload(*args)).execute()


def update_row(row_id, *args):
    sb.table("meetings").update(payload(*args)).eq("id", int(row_id)).execute()


def delete_row(row_id):
    sb.table("meetings").delete().eq("id", int(row_id)).execute()


def split_pics(text):
    return [p.strip() for p in str(text).split(",") if p.strip()]


def pic_options(df):
    used = set()
    if not df.empty:
        for v in df["pics"]:
            used.update(split_pics(v))
    return sorted(set(DEFAULT_PICS) | used)


# ---------- UI ----------
require_login()
sb = get_client()
df_all = load_df()
options = pic_options(df_all)

st.title("📒 Log Book Meeting")
st.caption("Catat kegiatan harian marketing & cek historinya.")

tab_input, tab_history, tab_edit = st.tabs(["➕ Input Baru", "🔎 History", "✏️ Edit / Hapus"])

# ----- Input -----
with tab_input:
    with st.form("form_input", clear_on_submit=True):
        c1, c2 = st.columns(2)
        d = c1.date_input("Date", value=date.today())
        loc = c2.radio("Lokasi", LOCATIONS, horizontal=True)
        who = st.text_input(
            "Dengan siapa / pihak terkait",
            placeholder="mis. Internal Team Marketing JICT, CMA CGM",
        )
        pics = st.multiselect("PIC (bisa lebih dari satu)", options)
        extra_pics = st.text_input("PIC lain (belum ada di list, pisahkan dengan koma)")
        agenda = st.text_area("Meeting agenda", height=100)
        discussion = st.text_area("Discussion (opsional)", height=150)
        submitted = st.form_submit_button("Simpan", type="primary")

    if submitted:
        all_pics = list(dict.fromkeys(pics + split_pics(extra_pics)))
        if not who.strip() or not all_pics or not agenda.strip():
            st.error("Lengkapi dulu: pihak terkait, minimal satu PIC, dan agenda.")
        else:
            insert_row(d, loc, who.strip(), all_pics, agenda.strip(), discussion.strip())
            st.success("Tersimpan.")
            st.rerun()

# ----- History -----
with tab_history:
    if df_all.empty:
        st.info("Belum ada data.")
    else:
        f1, f2, f3, f4 = st.columns([2, 1, 1, 2])
        min_d, max_d = df_all["meeting_date"].min(), df_all["meeting_date"].max()
        rng = f1.date_input("Rentang tanggal", value=(min_d, max_d))
        loc_f = f2.multiselect("Lokasi", LOCATIONS, default=LOCATIONS)
        pic_f = f3.multiselect("PIC", options)
        kw = f4.text_input("Cari kata kunci (pihak / agenda / discussion)")

        df = df_all.copy()
        if isinstance(rng, tuple) and len(rng) == 2:
            df = df[(df["meeting_date"] >= rng[0]) & (df["meeting_date"] <= rng[1])]
        elif not isinstance(rng, tuple):
            df = df[df["meeting_date"] == rng]
        df = df[df["location"].isin(loc_f)]
        if pic_f:
            df = df[df["pics"].apply(lambda v: any(p in split_pics(v) for p in pic_f))]
        if kw:
            k = kw.lower()
            df = df[
                df["with_whom"].str.lower().str.contains(k, na=False)
                | df["agenda"].str.lower().str.contains(k, na=False)
                | df["discussion"].fillna("").str.lower().str.contains(k, na=False)
            ]

        st.write(f"**{len(df)}** entri ditemukan")
        view = st.radio("Tampilan", ["Per hari", "Tabel"], horizontal=True)

        if view == "Tabel":
            show = df.rename(
                columns={
                    "meeting_date": "Date",
                    "location": "Lokasi",
                    "with_whom": "Dengan siapa",
                    "pics": "PIC",
                    "agenda": "Meeting agenda",
                    "discussion": "Discussion",
                }
            ).drop(columns=["created_at"])
            st.dataframe(show, use_container_width=True, hide_index=True)
        else:
            for day, grp in df.groupby("meeting_date", sort=False):
                st.subheader(day.strftime("%A, %d %B %Y"))
                for _, r in grp.iterrows():
                    with st.expander(f"[{r['location']}] {r['with_whom']} — {r['agenda'][:70]}"):
                        st.markdown(f"**PIC:** {r['pics']}")
                        st.markdown(f"**Agenda:** {r['agenda']}")
                        st.markdown("**Discussion:**")
                        st.write(r["discussion"] if r["discussion"] else "-")

        st.download_button(
            "⬇️ Download CSV",
            df.drop(columns=["created_at"]).to_csv(index=False).encode("utf-8"),
            file_name="logbook_meeting.csv",
            mime="text/csv",
        )

# ----- Edit / Hapus -----
with tab_edit:
    if df_all.empty:
        st.info("Belum ada data.")
    else:
        labels = {
            int(r["id"]): f"#{r['id']} | {r['meeting_date']} | {r['with_whom']} | {r['agenda'][:40]}"
            for _, r in df_all.iterrows()
        }
        sel = st.selectbox("Pilih entri", list(labels.keys()), format_func=lambda i: labels[i])
        row = df_all[df_all["id"] == sel].iloc[0]

        with st.form("form_edit"):
            c1, c2 = st.columns(2)
            e_date = c1.date_input("Date", value=row["meeting_date"], key=f"e_date_{sel}")
            e_loc = c2.radio(
                "Lokasi", LOCATIONS, index=LOCATIONS.index(row["location"]), horizontal=True, key=f"e_loc_{sel}"
            )
            e_who = st.text_input("Dengan siapa / pihak terkait", value=row["with_whom"], key=f"e_who_{sel}")
            cur_pics = split_pics(row["pics"])
            e_pics = st.multiselect(
                "PIC", sorted(set(options) | set(cur_pics)), default=cur_pics, key=f"e_pics_{sel}"
            )
            e_agenda = st.text_area("Meeting agenda", value=row["agenda"], key=f"e_agenda_{sel}")
            e_disc = st.text_area("Discussion", value=row["discussion"] or "", key=f"e_disc_{sel}")
            b1, b2 = st.columns(2)
            save = b1.form_submit_button("Update", type="primary")
            remove = b2.form_submit_button("Hapus entri")

        if save:
            if not e_who.strip() or not e_pics or not e_agenda.strip():
                st.error("Pihak terkait, PIC, dan agenda tidak boleh kosong.")
            else:
                update_row(sel, e_date, e_loc, e_who.strip(), e_pics, e_agenda.strip(), e_disc.strip())
                st.success("Diupdate.")
                st.rerun()
        if remove:
            delete_row(sel)
            st.warning("Entri dihapus.")
            st.rerun()
