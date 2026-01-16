import streamlit as st
import pandas as pd
import sqlite3
import io
from datetime import datetime
import pytz
import qrcode
from smartcard.System import readers
from smartcard.pcsc.PCSCExceptions import EstablishContextException
from smartcard.util import toHexString

# ================== NFC SAFE ==================
def read_nfc_uid():
    try:
        r = readers()
        if not r:
            return None
        reader = r[0]
        conn = reader.createConnection()
        conn.connect()
        data, sw1, sw2 = conn.transmit([0xFF, 0xCA, 0x00, 0x00, 0x00])
        if sw1 == 0x90:
            return toHexString(data).replace(" ", "")
        return None
    except EstablishContextException:
        return "PCSC_OFF"
    except:
        return None

# ================== AYAR ==================
tz = pytz.timezone("Europe/Istanbul")
conn = sqlite3.connect("personel.db", check_same_thread=False)
c = conn.cursor()

# ================== DB ==================
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password TEXT,
    role TEXT,
    approved INTEGER,
    qr_token TEXT,
    nfc_id TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS logs (
    username TEXT,
    durum TEXT,
    giris TEXT,
    cikis TEXT,
    sure INTEGER
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS notifications (
    username TEXT,
    message TEXT,
    created TEXT
)
""")

c.execute(
    "INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?, ?, ?)",
    ("admin", "1234", "Yönetici", 1, None, None)
)
conn.commit()

# ================== UI ==================
st.set_page_config("Personel Yönetim Sistemi", "🏢", layout="wide")
st.image("logo.png", width=140)
st.title("🏢 Personel Yönetim Sistemi")

# ================== GİRİŞ ==================
tab1, tab2 = st.tabs(["🔑 Giriş", "📝 Kayıt"])

with tab1:
    u = st.text_input("Kullanıcı Adı", key="lu")
    p = st.text_input("Şifre", type="password", key="lp")

    if st.button("Giriş Yap"):
        user = c.execute(
            "SELECT username, role FROM users WHERE username=? AND password=? AND approved=1",
            (u, p)
        ).fetchone()
        if user:
            st.session_state.user = user[0]
            st.session_state.role = user[1]
            st.success("Giriş başarılı ✅")
        else:
            st.error("Hatalı bilgi veya onay yok ❌")

    st.divider()
    st.subheader("📶 NFC ile Giriş")

    if st.button("NFC Kartı Okut"):
        uid = read_nfc_uid()
        if uid == "PCSC_OFF":
            st.error("❌ Akıllı Kart servisi kapalı (services.msc)")
        elif uid:
            user = c.execute(
                "SELECT username, role FROM users WHERE nfc_id=? AND approved=1",
                (uid,)
            ).fetchone()
            if user:
                st.session_state.user = user[0]
                st.session_state.role = user[1]
                st.success(f"NFC giriş: {user[0]} ✅")
            else:
                st.error("Kart tanımlı değil ❌")
        else:
            st.error("NFC okunamadı ❌")

with tab2:
    nu = st.text_input("Yeni Kullanıcı", key="ru")
    np = st.text_input("Şifre", type="password", key="rp")

    if st.button("Kayıt Ol"):
        qr = f"{nu}-{datetime.now(tz).strftime('%Y%m%d%H%M%S')}"
        try:
            c.execute(
                "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                (nu, np, "Personel", 0, qr, None)
            )
            conn.commit()
            st.success("Kayıt alındı (Admin onayı) ✅")
        except:
            st.error("Kullanıcı mevcut ❌")

# ================== PERSONEL ==================
if st.session_state.get("role") == "Personel":
    st.header("👤 Personel Paneli")

    durum = st.selectbox("Durum", ["İçeriye Gir", "Dışarıya Çık"])
    if st.button("Kaydet"):
        now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        if durum == "İçeriye Gir":
            c.execute("INSERT INTO logs VALUES (?, ?, ?, ?, ?)",
                      (st.session_state.user, "İçeride", now, None, None))
        else:
            c.execute("INSERT INTO logs VALUES (?, ?, ?, ?, ?)",
                      (st.session_state.user, "Dışarıda", None, now, None))
        conn.commit()
        st.success("Durum güncellendi ✅")

    st.subheader("📲 QR Kod")
    qr_token = c.execute(
        "SELECT qr_token FROM users WHERE username=?",
        (st.session_state.user,)
    ).fetchone()[0]

    img = qrcode.make(qr_token)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    st.image(buf.getvalue(), width=180)

    notif = pd.read_sql(
        "SELECT * FROM notifications WHERE username=? ORDER BY created DESC",
        conn, params=(st.session_state.user,)
    )
    if not notif.empty:
        st.warning(f"📢 Yönetici: {notif.iloc[0]['message']}")

# ================== YÖNETİCİ ==================
elif st.session_state.get("role") == "Yönetici":
    st.header("👨‍💼 Yönetici Paneli")

    tabA, tabB, tabC, tabD = st.tabs(
        ["📊 Dashboard", "🚶 Dışarıda Olanlar", "📢 Bildirim", "📥 Excel Rapor"]
    )

    with tabA:
        df = pd.read_sql("SELECT * FROM logs", conn)
        st.metric("Toplam Personel", df["username"].nunique())
        st.metric("Dışarıda", df[df["durum"] == "Dışarıda"]["username"].nunique())
        st.dataframe(df, use_container_width=True)

    with tabB:
        disari = pd.read_sql(
            "SELECT username, cikis FROM logs WHERE durum='Dışarıda'",
            conn
        )
        if disari.empty:
            st.success("Kimse dışarıda değil")
        else:
            st.dataframe(disari, use_container_width=True)

    with tabC:
        hedef = st.text_input("Kullanıcı adı")
        mesaj = st.text_area("Mesaj")
        if st.button("Gönder"):
            c.execute(
                "INSERT INTO notifications VALUES (?, ?, ?)",
                (hedef, mesaj, datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()
            st.success("Bildirim gönderildi ✅")

    with tabD:
        rapor = pd.read_sql("SELECT * FROM logs", conn)
        out = io.BytesIO()
        rapor.to_excel(out, index=False)
        st.download_button(
            "📥 Excel indir",
            out.getvalue(),
            "personel_rapor.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ================== FOOTER ==================
st.sidebar.info("✅ Kurumsal Final | NFC + Bildirim + Excel + Web Takip")
