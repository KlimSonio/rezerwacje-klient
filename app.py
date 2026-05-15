import streamlit as st
from datetime import datetime, date, timedelta
import pandas as pd
from sqlalchemy import create_engine, text

# --- 1. KONFIGURACJA STRONY I STYLE CSS (STYL BOOKSY + INTER) ---
st.set_page_config(page_title="Rezerwacja Studia", page_icon="🎙️", layout="centered")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');

    html, body, [data-testid="stWidgetLabel"], .main, button, input, select, textarea {
        font-family: 'Inter', sans-serif !important;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    div[data-testid="stDecoration"] {display: none;}
    
    h1, h2, h3 {
        font-family: 'Inter', sans-serif !important;
        font-weight: 700 !important;
        color: #111827;
        letter-spacing: -0.02em;
    }

    .main-title {
        margin-top: -40px;
        text-align: center;
        padding-bottom: 5px;
    }

    /* Box braku miejsc - ciepły i pomocny */
    .no-slots-box {
        background-color: #fff7ed;
        border: 1px solid #ffedd5;
        border-left: 5px solid #f97316;
        padding: 20px;
        border-radius: 12px;
        color: #9a3412;
        font-size: 0.9rem;
        margin-top: 10px;
    }

    .status-pending {
        background-color: #f0fdf4;
        border: 1px solid #dcfce7;
        color: #166534;
        padding: 15px;
        border-radius: 8px;
        font-size: 0.9rem;
        margin-top: 15px;
        border-left: 5px solid #22c55e;
    }
    
    .weekend-info-box {
        background-color: #f0f9ff;
        border: 1px solid #e0f2fe;
        border-left: 5px solid #0ea5e9;
        padding: 15px;
        border-radius: 8px;
        color: #0c4a6e;
        font-size: 0.85rem;
        margin-top: 10px;
    }

    .contact-box {
        background-color: #f9fafb;
        border: 1px solid #f3f4f6;
        padding: 20px;
        border-radius: 12px;
        text-align: center;
        border-left: 5px solid #9ca3af;
    }

    .call-button {
        background-color: #374151;
        color: #ffffff !important;
        padding: 12px 24px;
        border-radius: 8px;
        text-decoration: none;
        display: inline-block;
        font-weight: 600;
        margin-top: 10px;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<h1 class="main-title">Rezerwacja sesji nagraniowej</h1>', unsafe_allow_html=True)

# --- 3. POŁĄCZENIE Z BAZĄ ---
db_url = st.secrets["connections"]["supabase_db"]["url"]
engine = create_engine(db_url)

# --- 4. FUNKCJE LOGICZNE ---
def pobierz_zajete_terminy(wybrana_data, realizator_id):
    data_str = wybrana_data.strftime("%Y-%m-%d")
    query = """
        SELECT godzina, godzina_konca 
        FROM rezerwacje 
        WHERE data = :data 
        AND (realizator = :realizator OR imie_nazwisko = '🔒 BLOKADA TERMINU')
        AND status != 'odrzucona'
    """
    return pd.read_sql_query(text(query), con=engine, params={"data": data_str, "realizator": realizator_id})

def czy_slot_wolny(start_str, koniec_str, df_zajete):
    t_start = datetime.strptime(start_str, "%H:%M").time()
    t_koniec = datetime.strptime("23:59" if koniec_str in ["00:00", "24:00"] else koniec_str, "%H:%M").time()
    for _, row in df_zajete.iterrows():
        z_start = datetime.strptime(row['godzina'], "%H:%M").time()
        z_koniec_raw = row['godzina_konca']
        z_koniec = datetime.strptime("23:59" if z_koniec_raw in ["00:00", "24:00"] else z_koniec_raw, "%H:%M").time()
        if t_start < z_koniec and t_koniec > z_start:
            return False
    return True

# --- 5. INTERFEJS ---
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. Termin")
    wybrana_data = st.date_input("Data:", min_value=date.today())
    czy_weekend = wybrana_data.weekday() >= 5
    
    opcje = ["Maciek", "Tomek"]
    if czy_weekend:
        opcje = ["Tomek"]
        st.markdown('<div class="weekend-info-box"><b>Weekend:</b> Sesje z Tomkiem (12:00 – 22:00).</div>', unsafe_allow_html=True)
    
    wybor = st.radio("Realizator:", opcje, horizontal=True, label_visibility="collapsed")
    
    if wybor == "Maciek":
        realizator_id, h_start, h_end = "Maciek", 8, 15
        st.caption("Dostępność: 08:00 – 15:00")
    else:
        if czy_weekend:
            realizator_id, h_start, h_end = "Tomek", 12, 22
            st.caption("Dostępność: 12:00 – 22:00")
        else:
            realizator_id, h_start, h_end = "Tomek", 15, 23
            st.caption("Dostępność: 15:00 – 00:00")

    dlugosc = st.selectbox("Długość sesji:", ["1 godzina", "2 godziny", "3 godziny", "Więcej (kontakt)"])
    
    godzina_start = None
    if "Więcej" not in dlugosc:
        ile_h = int(dlugosc.split()[0])
        df_zajete = pobierz_zajete_terminy(wybrana_data, realizator_id)
        wolne_godziny = []
        teraz = datetime.now()
        current_time = datetime.strptime(f"{h_start}:00", "%H:%M")
        
        while True:
            end_session = current_time + timedelta(hours=ile_h)
            limit = datetime.strptime(f"{h_end}:00", "%H:%M") if not (realizator_id == "Tomek" and not czy_weekend) else datetime.strptime("23:59", "%H:%M")
            if end_session > limit and not (realizator_id == "Tomek" and end_session.hour == 0): break

            slot_start_str = current_time.strftime("%H:%M")
            if czy_slot_wolny(slot_start_str, end_session.strftime("%H:%M"), df_zajete):
                if not (wybrana_data == date.today() and datetime.combine(date.today(), current_time.time()) < teraz + timedelta(minutes=30)):
                    wolne_godziny.append(slot_start_str)
            current_time += timedelta(minutes=30)
            if current_time.hour == 0 and current_time.minute == 0: break

        if wolne_godziny:
            godzina_start = st.selectbox("Godzina startu:", wolne_godziny)
        else:
            st.markdown(f"""
                <div class="no-slots-box">
                    <p style="margin: 0; font-size: 1.05rem;">☕ <b>{wybor} nie ma już wolnych miejsc.</b></p>
                    <p style="margin: 5px 0 0 0; opacity: 0.85; font-size: 0.85rem;">
                        Wybierz inną datę lub napisz do nas na Instagramie – spróbujemy coś wymyślić!
                    </p>
                </div>
            """, unsafe_allow_html=True)

with col2:
    st.subheader("2. Twoje dane")
    if "Więcej" in dlugosc:
        st.markdown('<div class="contact-box"><p>Dłuższe sesje ustalamy telefonicznie.</p><a href="tel:+48000000000" class="call-button">Zadzwoń</a></div>', unsafe_allow_html=True)
    else:
        with st.form("booking_form", clear_on_submit=True):
            klient = st.text_input("Imię i Nazwisko / Projekt *")
            mail = st.text_input("E-mail *")
            telefon = st.text_input("Numer telefonu *")
            opis = st.text_area("Uwagi")
            submit = st.form_submit_button("REZERWUJĘ", use_container_width=True, disabled=not godzina_start)
            
            if submit:
                if klient and mail and telefon:
                    try:
                        dt_k = datetime.strptime(godzina_start, "%H:%M") + timedelta(hours=ile_h)
                        g_koniec = dt_k.strftime("%H:%M") if not (dt_k.hour == 0 and dt_k.minute == 0) else "23:59"
                        with engine.begin() as conn:
                            conn.execute(text("INSERT INTO rezerwacje (data, godzina, godzina_konca, realizator, imie_nazwisko, email, telefon, uwagi, status) VALUES (:d, :gs, :gk, :r, :n, :e, :t, :u, 'oczekuje')"),
                            {"d": wybrana_data, "gs": godzina_start, "gk": g_koniec, "r": realizator_id, "n": klient, "e": mail, "t": telefon, "u": opis})
                        st.markdown(f"""
                            <div class="status-pending">
                                <b>Wysłano!</b> Rezerwacja na {wybrana_data} o {godzina_start} czeka na potwierdzenie. Odezwiemy się wkrótce! ⏳
                            </div>
                        """, unsafe_allow_html=True)
                        st.balloons()
                    except Exception as e: st.error("Błąd zapisu.")
                else: st.warning("Uzupełnij pola z *")

# --- 6. STOPKA ---
st.markdown("---")
social_html = """
<div style="display: flex; justify-content: center; gap: 35px; margin-top: 10px; margin-bottom: 25px;">
    <a href="#" style="color: #E4405F;"><svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="5" ry="5"></rect><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"></path><line x1="17.5" y1="6.5" x2="17.51" y2="6.5"></line></svg></a>
    <a href="#" style="color: #1877F2;"><svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z"></path></svg></a>
    <a href="#" style="color: #34D399;"><svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg></a>
</div>
"""
st.markdown(social_html, unsafe_allow_html=True)