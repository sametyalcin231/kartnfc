import streamlit as st
import pandas as pd
import sqlite3
import io
from datetime import datetime
import pytz
import qrcode

# ------------------ AYARLAR ------------------
tz = pytz.timezone("Europe/Istanbul")
st.set_page_config(page_title="Personel Sistemi", layout="wide")

# ------------------ DB ------------------
conn = sqlite3.connect("personel.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT,
    role TEXT,
    approved INTEGER,
    qr_token TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS logs (
    username TEXT,
    durum TEXT,
    zaman TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS notifications (
    username TEXT,
    message TEXT,
    created TEXT
)
""")
conn.commit()

# admin
c.execute("""
INSERT OR IGNORE INTO users VALUES (?,?,?,?,?)
""", ("admin", "1234", "Yönetici", 1, "ADMIN"))
conn.commit()

# ------------------ HEADER ------------------
st.title("🏢 Personel Yönetim Sistemi (QR)")

# ------------------ LOGIN ------------------
if "user" not in st.session_state:
    tab1, tab2 = st.tabs(["🔑 Giriş", "📝 Kayıt"])

    with tab1:
        u = st.text_input("Kullanıcı Adı", key="login_u")
        p = st.text_input("Şifre", type="password", key="login_p")
        if st.button("Giriş"):
            r = c.execute(
                "SELECT * FROM users WHERE username=? AND password=? AND approved=1",
                (u, p)
            ).fetchone()
            if r:
                st.session_state.user = r[0]
                st.session_state.role = r[2]
                st.rerun()
            else:
                st.error("Giriş başarısız")

    with tab2:
        nu = st.text_input("Yeni Kullanıcı", key="reg_u")
        np = st.text_input("Şifre", type="password", key="reg_p")
        if st.button("Kayıt Ol"):
            try:
                token = f"{nu}-{int(datetime.now().timestamp())}"
                c.execute(
                    "INSERT INTO users VALUES (?,?,?,?,?)",
                    (nu, np, "Personel", 0, token)
                )
                conn.commit()
                st.success("Kayıt alındı (admin onayı bekleniyor)")
            except:
                st.error("Kullanıcı var")

    st.stop()

# ------------------ QR İŞLEM ------------------
def qr_islem(qr_token):
    user = c.execute(
        "SELECT username FROM users WHERE qr_token=? AND approved=1",
        (qr_token,)
    ).fetchone()
    if not user:
        return False, "Geçersiz QR"

    username = user[0]
    last = c.execute(
        "SELECT durum FROM logs WHERE username=? ORDER BY zaman DESC LIMIT 1",
        (username,)
    ).fetchone()

    yeni = "İçeri Girdi" if not last or last[0] == "Dışarı Çıktı" else "Dışarı Çıktı"

    c.execute(
        "INSERT INTO logs VALUES (?,?,?)",
        (username, yeni, datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    return True, f"{username} → {yeni}"

# ------------------ PERSONEL ------------------
if st.session_state.role == "Personel":
    st.subheader("👤 Personel Paneli")

    qr_token = c.execute(
        "SELECT qr_token FROM users WHERE username=?",
        (st.session_state.user,)
    ).fetchone()[0]

    st.markdown("### 📲 QR Kodun")
    img = qrcode.make(qr_token)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    st.image(buf.getvalue(), width=200)

    df = pd.read_sql(
        "SELECT * FROM logs WHERE username=? ORDER BY zaman DESC",
        conn,
        params=(st.session_state.user,)
    )
    st.dataframe(df, use_container_width=True)

# ------------------ YÖNETİCİ ------------------
if st.session_state.role == "Yönetici":
    tabs = st.tabs(["📷 QR Okut", "📊 Dashboard", "📥 Excel", "👥 Kullanıcılar", "📢 Bildirim"])

    # --- QR OKUT ---
    with tabs[0]:
        qr_input = st.text_input("QR Token", key="qr_input")
        if st.button("Giriş / Çıkış Yap"):
            ok, msg = qr_islem(qr_input)
            st.success(msg) if ok else st.error(msg)

    # --- DASHBOARD ---
    with tabs[1]:
        df = pd.read_sql("SELECT * FROM logs", conn)
        st.metric("Toplam Log", len(df))
        st.metric("Personel", df["username"].nunique())
        st.dataframe(df, use_container_width=True)

    # --- EXCEL ---
    with tabs[2]:
        df = pd.read_sql("SELECT * FROM logs", conn)
        out = io.BytesIO()
        df.to_excel(out, index=False)
        st.download_button(
            "Excel İndir",
            out.getvalue(),
            file_name="personel_rapor.xlsx"
        )

    # --- KULLANICI ONAY ---
    with tabs[3]:
        pending = pd.read_sql("SELECT username FROM users WHERE approved=0", conn)
        for _, r in pending.iterrows():
            if st.button(f"Onayla: {r['username']}"):
                c.execute("UPDATE users SET approved=1 WHERE username=?", (r["username"],))
                conn.commit()
                st.rerun()

    # --- BİLDİRİM ---
    with tabs[4]:
        tu = st.text_input("Kullanıcı", key="notif_u")
        msg = st.text_area("Mesaj", key="notif_m")
        if st.button("Gönder"):
            c.execute(
                "INSERT INTO notifications VALUES (?,?,?)",
                (tu, msg, datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()
            st.success("Gönderildi")

# ------------------ ÇIKIŞ ------------------
st.sidebar.button("Çıkış", on_click=lambda: st.session_state.clear())
