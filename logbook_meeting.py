import calendar
import hmac
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st
from supabase import Client, create_client

LOCATIONS = ["In JICT", "Out JICT"]
# Isi daftar PIC default di sini. PIC baru yang pernah diinput otomatis muncul juga.
DEFAULT_PICS = ["PIC 1", "PIC 2", "PIC 3"]

st.set_page_config(page_title="CRM UPDATE", page_icon="📊", layout="wide")


# ---------- Login ----------
def require_login():
    if st.session_state.get("auth"):
        return
    st.title("CRM UPDATE")
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


# ---------- Company Details: helpers ----------
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS = list(range(1, 32))


def fmt_dm(v):
    """'09-13' -> '13-Sep'"""
    if not v:
        return ""
    m, d = v.split("-")
    return f"{int(d)}-{MONTHS[int(m) - 1]}"


def to_dm(day, month_name):
    """(13, 'Sep') -> '09-13'. Kosong dua-duanya -> None."""
    if day is None and month_name is None:
        return None
    if day is None or month_name is None:
        raise ValueError("Isi tanggal dan bulan sekaligus, atau kosongkan keduanya.")
    m = MONTHS.index(month_name) + 1
    if day > calendar.monthrange(2000, m)[1]:
        raise ValueError(f"Tanggal {day} tidak valid untuk bulan {month_name}.")
    return f"{m:02d}-{day:02d}"


def split_dm(v):
    if not v:
        return None, None
    m, d = v.split("-")
    return int(d), MONTHS[int(m) - 1]


def days_until(v):
    m, d = map(int, v.split("-"))
    today = date.today()
    for yr in range(today.year, today.year + 5):
        try:
            target = date(yr, m, d)
        except ValueError:  # 29 Feb di tahun non-kabisat
            continue
        if target >= today:
            return (target - today).days
    return None


def load_companies():
    return sb.table("companies").select("*").order("shipping_line").execute().data


def load_contacts():
    return sb.table("contacts").select("*").order("id").execute().data


def flat_rows(companies, by_co, blank_repeat):
    """Baris datar ala Excel. blank_repeat=True -> kolom company dikosongkan di baris kontak ke-2 dst."""
    rows = []
    for no, c in enumerate(companies, 1):
        for i, p in enumerate(by_co.get(c["id"]) or [None]):
            show_co = i == 0 or not blank_repeat
            rows.append(
                {
                    "No": str(no) if show_co else "",
                    "Shipping Line": c["shipping_line"] if show_co else "",
                    "Address": (c.get("address") or "") if show_co else "",
                    "Company Anniversary": fmt_dm(c.get("anniversary")) if show_co else "",
                    "Name": p["name"] if p else "",
                    "Birth Date": fmt_dm(p.get("birth_date")) if p else "",
                    "Position": (p.get("position") or "") if p else "",
                    "Email": (p.get("email") or "") if p else "",
                }
            )
    return rows


def dm_inputs(label_prefix, key, current=None):
    """Dua selectbox tanggal + bulan. Return (day, month_name)."""
    d0, m0 = split_dm(current)
    c1, c2 = st.columns(2)
    day = c1.selectbox(f"{label_prefix} - Tanggal", DAYS, index=DAYS.index(d0) if d0 else None, key=f"{key}_d")
    mon = c2.selectbox(f"{label_prefix} - Bulan", MONTHS, index=MONTHS.index(m0) if m0 else None, key=f"{key}_m")
    return day, mon


# ---------- Tanjung Priok Throughput: helpers ----------
TERMINALS = ["JICT", "TPK KOJA", "MAL", "TO3", "NPCT1"]
MONTHS_ID = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus",
             "September", "Oktober", "November", "Desember"]
TERM_COLORS = ["#1f77b4", "#ff7f0e", "#17becf", "#9467bd", "#8c564b"]


def load_tp(years):
    rows = sb.table("throughput").select("year,month,terminal,value").in_("year", list(years)).execute().data
    df = pd.DataFrame(rows, columns=["year", "month", "terminal", "value"])
    return df.astype({"year": "int64", "month": "int64", "value": "float64"})


def agg(df, year, m1, m2):
    """Total per terminal untuk periode + jumlah bulan yang ada datanya."""
    d = df[(df["year"] == year) & df["month"].between(m1, m2)]
    return d.groupby("terminal")["value"].sum().reindex(TERMINALS).fillna(0), d["month"].nunique()


def year_table(df, year):
    p = pd.DataFrame(index=TERMINALS, columns=MONTHS_ID, dtype=float)
    for r in df[df["year"] == year].itertuples():
        if r.terminal in TERMINALS:
            p.at[r.terminal, MONTHS_ID[r.month - 1]] = r.value
    return p


def with_totals(p):
    t = p.copy()
    t["TOTAL"] = t.sum(axis=1, min_count=1)
    t.loc["TOTAL"] = t.sum(min_count=1)
    t["MS"] = t["TOTAL"] / t.loc["TOTAL", "TOTAL"] * 100
    return t


def ms_table(t):
    m = t.drop(columns=["MS"])
    return m.div(m.loc["TOTAL"].where(m.loc["TOTAL"] > 0), axis=1) * 100


def pie_chart(s):
    df = pd.DataFrame({"Terminal": s.index, "Throughput": s.values, "idx": range(len(s))})
    df["MS"] = df["Throughput"] / df["Throughput"].sum() * 100
    df["Label"] = df["MS"].map(lambda v: f"{v:.1f}%")
    base = alt.Chart(df).encode(
        theta=alt.Theta("Throughput:Q", stack=True),
        order=alt.Order("idx:Q"),
        color=alt.Color("Terminal:N", scale=alt.Scale(domain=TERMINALS, range=TERM_COLORS),
                        legend=None),
    )
    arcs = base.mark_arc(outerRadius=100).encode(
        tooltip=["Terminal", alt.Tooltip("Throughput:Q", format=","), alt.Tooltip("MS:Q", format=".1f", title="MS (%)")]
    )
    text = base.mark_text(radius=70, size=11, color="white", fontWeight="bold").encode(text="Label:N")
    return (arcs + text).properties(height=240)


def stats_box(s):
    """Kotak kecil: throughput + MS per terminal, di samping pie."""
    total = s.sum()
    td = "padding:2px 6px;text-align:right"
    rows = "".join(
        f"<tr><td style='padding:2px 6px'><span style='color:{c}'>●</span> {t}</td>"
        f"<td style='{td}'>{v:,.0f}</td><td style='{td}'>{v / total * 100:.1f}%</td></tr>"
        for t, v, c in zip(s.index, s.values, TERM_COLORS)
    )
    rows += (f"<tr style='font-weight:bold;border-top:1px solid rgba(128,128,128,.4)'>"
             f"<td style='padding:2px 6px'>TOTAL</td><td style='{td}'>{total:,.0f}</td><td style='{td}'>100%</td></tr>")
    return (
        "<div style='border:1px solid rgba(128,128,128,.35);border-radius:8px;padding:8px 6px'>"
        "<table style='width:100%;font-size:0.85rem;border-collapse:collapse'>"
        "<tr style='opacity:.7'><th style='padding:2px 6px;text-align:left'>Terminal</th>"
        "<th style='padding:2px 6px;text-align:right'>Throughput</th>"
        "<th style='padding:2px 6px;text-align:right'>MS</th></tr>"
        f"{rows}</table></div>"
    )


def growth_chart(g):
    base = alt.Chart(g).encode(x=alt.X("Terminal:N", sort=None, title=None),
                               y=alt.Y("Growth:Q", title="Growth (%)"))
    bars = base.mark_bar().encode(
        color=alt.condition(alt.datum.Growth >= 0, alt.value("#2ca02c"), alt.value("#d62728")),
        tooltip=["Terminal", alt.Tooltip("Growth:Q", format="+.1f")],
    )
    pos = base.transform_filter(alt.datum.Growth >= 0).mark_text(baseline="bottom", dy=-4).encode(text=alt.Text("Growth:Q", format="+.1f"))
    neg = base.transform_filter(alt.datum.Growth < 0).mark_text(baseline="top", dy=4).encode(text=alt.Text("Growth:Q", format="+.1f"))
    return (bars + pos + neg).properties(height=280)


# ---------- UI ----------
require_login()
sb = get_client()
st.title("CRM UPDATE")

MENU_LOG = "📒 Log Book Meeting"
MENU_COMPANY = "🏢 Company Details"
MENU_TP = "🚢 Tanjung Priok Throughput"
menu = st.sidebar.radio("Menu", [MENU_LOG, MENU_COMPANY, MENU_TP])

# ===== Page: Log Book Meeting =====
if menu == MENU_LOG:
    st.header("Log Book Meeting")
    st.caption("Catat kegiatan harian marketing & cek historinya.")

    df_all = load_df()
    options = pic_options(df_all)

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
                st.dataframe(show, width="stretch", hide_index=True)
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

# ===== Page: Company Details =====
elif menu == MENU_COMPANY:
    st.header("Company Details")

    companies = load_companies()
    contacts = load_contacts()
    co_by_id = {c["id"]: c for c in companies}
    by_co = {}
    for p in contacts:
        by_co.setdefault(p["company_id"], []).append(p)

    page = st.radio(
        "Menu",
        ["Daftar", "Tambah Company", "Tambah Kontak", "Edit / Hapus"],
        horizontal=True,
        key="co_page",
        label_visibility="collapsed",
    )

    # ---- Daftar ----
    if page == "Daftar":
        if not companies:
            st.info("Belum ada company. Tambah lewat menu 'Tambah Company'.")
        else:
            events = []
            for c in companies:
                n = days_until(c["anniversary"]) if c.get("anniversary") else None
                if n is not None and n <= 30:
                    events.append((n, f"🏢 Anniversary {c['shipping_line']} ({fmt_dm(c['anniversary'])})"))
            for p in contacts:
                n = days_until(p["birth_date"]) if p.get("birth_date") else None
                if n is not None and n <= 30:
                    co_name = co_by_id.get(p["company_id"], {}).get("shipping_line", "-")
                    events.append((n, f"🎂 Ulang tahun {p['name']}, {co_name} ({fmt_dm(p['birth_date'])})"))
            if events:
                with st.container(border=True):
                    st.markdown("**Dalam 30 hari ke depan**")
                    for n, text in sorted(events):
                        when = "Hari ini" if n == 0 else f"{n} hari lagi"
                        st.write(f"{when} · {text}")

            q = st.text_input("Cari (shipping line / nama / position)", key="co_search").strip().lower()
            view = st.radio("Tampilan", ["Per company", "Tabel (format Excel)"], horizontal=True, key="co_view")

            def match(c):
                if not q:
                    return True
                hay = [c["shipping_line"]]
                for p in by_co.get(c["id"], []):
                    hay += [p["name"], p.get("position") or ""]
                return any(q in h.lower() for h in hay)

            shown = [c for c in companies if match(c)]
            st.write(f"**{len(shown)}** company")

            if view == "Per company":
                for c in shown:
                    cs = by_co.get(c["id"], [])
                    with st.expander(f"{c['shipping_line']} ({len(cs)} kontak)"):
                        st.markdown(f"**Address:** {c.get('address') or '-'}")
                        st.markdown(f"**Company Anniversary:** {fmt_dm(c.get('anniversary')) or '-'}")
                        if cs:
                            st.dataframe(
                                pd.DataFrame(
                                    [
                                        {
                                            "Name": p["name"],
                                            "Birth Date": fmt_dm(p.get("birth_date")),
                                            "Position": p.get("position") or "",
                                            "Email": p.get("email") or "",
                                        }
                                        for p in cs
                                    ]
                                ),
                                width="stretch",
                                hide_index=True,
                            )
                        else:
                            st.caption("Belum ada kontak.")
            else:
                st.dataframe(pd.DataFrame(flat_rows(shown, by_co, True)), width="stretch", hide_index=True)

            st.download_button(
                "⬇️ Download CSV",
                pd.DataFrame(flat_rows(shown, by_co, False)).to_csv(index=False).encode("utf-8"),
                file_name="company_details.csv",
                mime="text/csv",
            )

    # ---- Tambah Company ----
    elif page == "Tambah Company":
        with st.form("form_company", clear_on_submit=True):
            sl = st.text_input("Shipping Line", placeholder="mis. CMA CGM")
            addr = st.text_area("Address", height=100)
            a_day, a_mon = dm_inputs("Company Anniversary", "new_anniv")
            ok = st.form_submit_button("Simpan Company", type="primary")
        if ok:
            try:
                anniv = to_dm(a_day, a_mon)
            except ValueError as e:
                st.error(str(e))
                st.stop()
            if not sl.strip():
                st.error("Shipping Line wajib diisi.")
            elif sl.strip().lower() in [c["shipping_line"].lower() for c in companies]:
                st.error("Shipping Line itu sudah ada.")
            else:
                sb.table("companies").insert(
                    {"shipping_line": sl.strip(), "address": addr.strip() or None, "anniversary": anniv}
                ).execute()
                st.success("Company tersimpan. Lanjut tambah kontak lewat menu 'Tambah Kontak'.")
                st.rerun()

    # ---- Tambah Kontak ----
    elif page == "Tambah Kontak":
        if not companies:
            st.info("Tambah company dulu.")
        else:
            with st.form("form_contact", clear_on_submit=True):
                cid = st.selectbox(
                    "Shipping Line", [c["id"] for c in companies], format_func=lambda i: co_by_id[i]["shipping_line"]
                )
                name = st.text_input("Name")
                b_day, b_mon = dm_inputs("Birth Date", "new_birth")
                pos = st.text_input("Position")
                email = st.text_input("Email")
                ok = st.form_submit_button("Simpan Kontak", type="primary")
            if ok:
                try:
                    birth = to_dm(b_day, b_mon)
                except ValueError as e:
                    st.error(str(e))
                    st.stop()
                if not name.strip():
                    st.error("Name wajib diisi.")
                elif email.strip() and "@" not in email:
                    st.error("Format email tidak valid.")
                else:
                    sb.table("contacts").insert(
                        {
                            "company_id": int(cid),
                            "name": name.strip(),
                            "birth_date": birth,
                            "position": pos.strip() or None,
                            "email": email.strip() or None,
                        }
                    ).execute()
                    st.success("Kontak tersimpan.")
                    st.rerun()

    # ---- Edit / Hapus ----
    else:
        if not companies:
            st.info("Belum ada data.")
        else:
            kind = st.radio("Yang diedit", ["Company", "Kontak"], horizontal=True, key="co_edit_kind")

            if kind == "Company":
                cid = st.selectbox(
                    "Pilih company", [c["id"] for c in companies], format_func=lambda i: co_by_id[i]["shipping_line"]
                )
                c = co_by_id[cid]
                with st.form("form_edit_company"):
                    e_sl = st.text_input("Shipping Line", value=c["shipping_line"], key=f"ec_sl_{cid}")
                    e_addr = st.text_area("Address", value=c.get("address") or "", key=f"ec_addr_{cid}")
                    e_day, e_mon = dm_inputs("Company Anniversary", f"ec_an_{cid}", c.get("anniversary"))
                    b1, b2 = st.columns(2)
                    save = b1.form_submit_button("Update", type="primary")
                    remove = b2.form_submit_button("Hapus company")
                st.caption("Menghapus company juga menghapus semua kontak di dalamnya.")
                if save:
                    try:
                        anniv = to_dm(e_day, e_mon)
                    except ValueError as e:
                        st.error(str(e))
                        st.stop()
                    others = [x["shipping_line"].lower() for x in companies if x["id"] != cid]
                    if not e_sl.strip():
                        st.error("Shipping Line wajib diisi.")
                    elif e_sl.strip().lower() in others:
                        st.error("Shipping Line itu sudah ada.")
                    else:
                        sb.table("companies").update(
                            {"shipping_line": e_sl.strip(), "address": e_addr.strip() or None, "anniversary": anniv}
                        ).eq("id", int(cid)).execute()
                        st.success("Diupdate.")
                        st.rerun()
                if remove:
                    sb.table("companies").delete().eq("id", int(cid)).execute()
                    st.warning("Company dan kontaknya dihapus.")
                    st.rerun()

            else:
                if not contacts:
                    st.info("Belum ada kontak.")
                else:
                    labels = {
                        p["id"]: f"{co_by_id.get(p['company_id'], {}).get('shipping_line', '-')} | {p['name']}"
                        for p in contacts
                    }
                    pid = st.selectbox("Pilih kontak", list(labels.keys()), format_func=lambda i: labels[i])
                    p = next(x for x in contacts if x["id"] == pid)
                    co_ids = [c["id"] for c in companies]
                    with st.form("form_edit_contact"):
                        e_cid = st.selectbox(
                            "Shipping Line",
                            co_ids,
                            index=co_ids.index(p["company_id"]),
                            format_func=lambda i: co_by_id[i]["shipping_line"],
                            key=f"ep_co_{pid}",
                        )
                        e_name = st.text_input("Name", value=p["name"], key=f"ep_name_{pid}")
                        e_day, e_mon = dm_inputs("Birth Date", f"ep_bd_{pid}", p.get("birth_date"))
                        e_pos = st.text_input("Position", value=p.get("position") or "", key=f"ep_pos_{pid}")
                        e_email = st.text_input("Email", value=p.get("email") or "", key=f"ep_email_{pid}")
                        b1, b2 = st.columns(2)
                        save = b1.form_submit_button("Update", type="primary")
                        remove = b2.form_submit_button("Hapus kontak")
                    if save:
                        try:
                            birth = to_dm(e_day, e_mon)
                        except ValueError as e:
                            st.error(str(e))
                            st.stop()
                        if not e_name.strip():
                            st.error("Name wajib diisi.")
                        elif e_email.strip() and "@" not in e_email:
                            st.error("Format email tidak valid.")
                        else:
                            sb.table("contacts").update(
                                {
                                    "company_id": int(e_cid),
                                    "name": e_name.strip(),
                                    "birth_date": birth,
                                    "position": e_pos.strip() or None,
                                    "email": e_email.strip() or None,
                                }
                            ).eq("id", int(pid)).execute()
                            st.success("Diupdate.")
                            st.rerun()
                    if remove:
                        sb.table("contacts").delete().eq("id", int(pid)).execute()
                        st.warning("Kontak dihapus.")
                        st.rerun()

# ===== Page: Tanjung Priok Throughput =====
elif menu == MENU_TP:
    st.header("Tanjung Priok Throughput")
    st.caption("Throughput Terminal Petikemas APTPI. TOTAL dan Market Share dihitung otomatis dari data bulanan.")
    tp_page = st.radio("Menu", ["Dashboard", "Tabel", "Input Data"], horizontal=True,
                       key="tp_page", label_visibility="collapsed")
    this_year = date.today().year
    years = list(range(this_year, this_year - 8, -1))

    # ---- Dashboard ----
    if tp_page == "Dashboard":
        c1, c2, c3 = st.columns(3)
        mode = c1.radio("Periode", ["Per Tahun", "Per Bulan", "Year to Date"], index=2, key="tp_mode")
        year = c2.selectbox("Tahun", years, key="tp_year")
        df = load_tp([year, year - 1, year - 2])
        have = df[df["year"] == year]["month"]
        last = int(have.max()) if len(have) else 1
        month = 12
        if mode != "Per Tahun":
            label = "Bulan" if mode == "Per Bulan" else "Sampai bulan"
            month = MONTHS_ID.index(c3.selectbox(label, MONTHS_ID, index=last - 1, key=f"tp_month_{mode}_{year}")) + 1
        M = MONTHS_ID[month - 1]

        if mode == "Year to Date":
            periods = [(f"YTD {M} {year}", year, 1, month), (f"YTD {M} {year - 1}", year - 1, 1, month),
                       (f"Full Year {year - 1}", year - 1, 1, 12), (f"Full Year {year - 2}", year - 2, 1, 12)]
        elif mode == "Per Bulan":
            periods = [(f"{M} {year}", year, month, month), (f"{M} {year - 1}", year - 1, month, month),
                       (f"Full Year {year - 1}", year - 1, 1, 12), (f"Full Year {year - 2}", year - 2, 1, 12)]
        else:
            periods = [(f"Full Year {year}", year, 1, 12), (f"Full Year {year - 1}", year - 1, 1, 12),
                       (f"Full Year {year - 2}", year - 2, 1, 12)]
        data = [agg(df, y, a, b) for _, y, a, b in periods]

        for i in range(0, len(periods), 2):
            for col, j in zip(st.columns(2), (i, i + 1)):
                if j >= len(periods):
                    break
                title, _, a, b = periods[j]
                s, n = data[j]
                with col:
                    st.markdown(f"**{title}**")
                    if s.sum() == 0:
                        st.info("Belum ada data.")
                    else:
                        pc, bc = st.columns([1, 1], vertical_alignment="center")
                        pc.altair_chart(pie_chart(s))
                        bc.markdown(stats_box(s), unsafe_allow_html=True)
                        if n < b - a + 1:
                            st.caption(f"⚠️ Baru {n} dari {b - a + 1} bulan terisi")

        t0, t1 = periods[0][0], periods[1][0]
        cur, prev = data[0][0], data[1][0]
        rows = []
        for t in TERMINALS + ["TOTAL"]:
            c = cur.sum() if t == "TOTAL" else cur[t]
            p = prev.sum() if t == "TOTAL" else prev[t]
            ms_c = c / cur.sum() * 100 if cur.sum() > 0 else None
            ms_p = p / prev.sum() * 100 if prev.sum() > 0 else None
            rows.append({
                "Terminal": t, f"Throughput {t1}": p, f"Throughput {t0}": c,
                "Growth (%)": (c - p) / p * 100 if p > 0 else None,
                f"MS {t1} (%)": ms_p, f"MS {t0} (%)": ms_c,
                "Δ MS (pp)": ms_c - ms_p if ms_c is not None and ms_p is not None else None,
            })
        comp = pd.DataFrame(rows)

        st.markdown(f"**Growth: {t0} vs {t1}**")
        g = comp[["Terminal", "Growth (%)"]].rename(columns={"Growth (%)": "Growth"}).dropna()
        if g.empty:
            st.info("Growth belum bisa dihitung (data periode pembanding kosong).")
        else:
            st.altair_chart(growth_chart(g))
        st.markdown("**Perbandingan Throughput & Market Share**")
        fmt = {f"Throughput {t0}": "{:,.0f}", f"Throughput {t1}": "{:,.0f}", "Growth (%)": "{:+.1f}",
               f"MS {t0} (%)": "{:.1f}", f"MS {t1} (%)": "{:.1f}", "Δ MS (pp)": "{:+.1f}"}
        st.dataframe(comp.style.format(fmt, na_rep="-"), hide_index=True, width="stretch")

    # ---- Tabel ----
    elif tp_page == "Tabel":
        year = st.selectbox("Tahun", years, key="tp_tbl_year")
        t = with_totals(year_table(load_tp([year]), year))
        st.markdown("**Throughput**")
        st.dataframe(t.style.format({**{m: "{:,.0f}" for m in MONTHS_ID + ["TOTAL"]}, "MS": "{:.1f}%"}, na_rep="-"),
                     width="stretch")
        st.markdown("**Market Share per bulan** (otomatis dari tabel di atas)")
        st.dataframe(ms_table(t).style.format("{:.1f}%", na_rep="-"), width="stretch")
        st.download_button("⬇️ Download CSV (throughput)", t.to_csv().encode("utf-8"),
                           file_name=f"throughput_{year}.csv", mime="text/csv")

    # ---- Input Data ----
    else:
        year = st.selectbox("Tahun", years, key="tp_in_year")
        if msg := st.session_state.pop("tp_flash", None):
            st.success(msg)
        ver = st.session_state.get("tp_ver", 0)
        orig = year_table(load_tp([year]), year)
        st.caption("Isi throughput per terminal per bulan. Kosongkan sel untuk menghapus data.")
        edited = st.data_editor(
            orig, key=f"tp_ed_{year}_{ver}", width="stretch",
            column_config={m: st.column_config.NumberColumn(min_value=0, step=1, format="%d") for m in MONTHS_ID},
        )
        if st.button("Simpan", type="primary"):
            up, dels = [], []
            for t in TERMINALS:
                for i, m in enumerate(MONTHS_ID, 1):
                    new, old = edited.at[t, m], orig.at[t, m]
                    if pd.isna(new) and pd.isna(old):
                        continue
                    if not pd.isna(new) and not pd.isna(old) and new == old:
                        continue
                    if pd.isna(new):
                        dels.append((t, i))
                    else:
                        up.append({"year": year, "month": i, "terminal": t, "value": int(new)})
            if up:
                sb.table("throughput").upsert(up, on_conflict="year,month,terminal").execute()
            for t, i in dels:
                sb.table("throughput").delete().eq("year", year).eq("month", i).eq("terminal", t).execute()
            st.session_state["tp_ver"] = ver + 1
            st.session_state["tp_flash"] = f"Tersimpan: {len(up)} diisi/diupdate, {len(dels)} dihapus."
            st.rerun()
