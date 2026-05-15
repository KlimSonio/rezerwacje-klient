import streamlit as st
from sqlalchemy import create_engine, text
import pandas as pd
from datetime import datetime, date, timedelta

# --- 1. KONFIGURACJA STRONY ---
st.set_page_config(
    page_title="B1 Studio - Rezerwacje", 
    layout="centered"
)

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    div[data-testid="stDecoration"] {display: none;}
    </style>
""", unsafe_allow_html=True)

# --- 2. POŁĄCZENIE Z BAZĄ DANYCH ---
try:
    db_url = st.secrets["connections"]["supabase_db"]["url"]
    engine = create_engine(db_url)
except KeyError:
    st.error("❌ Błąd: Brak konfiguracji bazy danych w secrets.toml!")
    st.stop()

# --- 3. LOGIKA BIZNESOWA ---
def generuj_siatke_godzin(start_str, koniec_str):
    godziny = []
    start = datetime.strptime(start_str, "%H:%M")
    koniec = datetime.strptime("23:30" if koniec_str in ["24:00", "23:59"] else koniec_str, "%H:%M")
    curr = start
    while curr <= koniec:
        godziny.append(curr.strftime("%H:%M"))
        curr += timedelta(minutes=30)
    return godziny

def pobierz_rezerwacje_realizatora(wybrana_data, realizator):
    data_str = wybrana_data.strftime("%Y-%m-%d")
    query = """
        SELECT godzina, godzina_konca FROM rezerwacje 
        WHERE data = :data AND (realizator = :realizator OR imie_nazwisko = '🔒 BLOKADA TERMINU')
    """
    try:
        return pd.read_sql_query(text(query), con=engine, params={"data": data_str, "realizator": realizator})
    except Exception:
        return pd.DataFrame()

def czy_termin_zajety(start_str, koniec_str, df_zajete):
    if df_zajete.empty: return False
    t_start = datetime.strptime(start_str, "%H:%M").time()
    t_koniec_val = "23:59" if koniec_str in ["24:00", "23:59"] else koniec_str
    t_koniec = datetime.strptime(t_koniec_val, "%H:%M").time()
    
    for _, row in df_zajete.iterrows():
        z_start = datetime.strptime(row['godzina'], "%H:%M").time()
        z_koniec_val = "23:59" if row['godzina_konca'] in ["24:00", "23:59"] else row['godzina_konca']
        z_koniec = datetime.strptime(z_koniec_val, "%H:%M").time()
        if t_start < z_koniec and t_koniec > z_start:
            return True
    return False

def zapisz_rezerwacje(data_str, g_start, g_koniec, realizator, imie, email, telefon, uwagi):
    query = """
        INSERT INTO rezerwacje (data, godzina, godzina_konca, realizator, imie_nazwisko, email, telefon, uwagi)
        VALUES (:data, :godzina, :godzina_konca, :realizator, :imie, :email, :telefon, :uwagi)
    """
    with engine.begin() as connection:
        connection.execute(text(query), {
            "data": data_str, "godzina": g_start, "godzina_konca": g_koniec,
            "realizator": realizator, "imie": imie, "email": email, "telefon": telefon, "uwagi": uwagi
        })

# --- 4. INTERFEJS UŻYTKOWNIKA ---
st.header("🎙️ Rezerwacja Sesji w B1 Studio")

col1, col2 = st.columns([1, 1], gap="large")

with col1:
    st.subheader("1. Termin sesji")
    realizator = st.selectbox("Wybierz realizatora dźwięku:", ["Maciek", "Tomek"])
    
    g_start_p, g_koniec_p = ("08:00", "16:00") if realizator == "Maciek" else ("16:00", "23:59")
    st.caption(f"{'🌅' if realizator == 'Maciek' else '🌃'} Dyżur: {g_start_p} - {g_koniec_p.replace('23:59', '00:00')}")
        
    dlugosc = st.selectbox("Długość sesji:", ["1 godzina", "2 godziny", "3 godziny"])
    godziny_int = int(dlugosc.split()[0])
    wybrana_data = st.date_input("Data sesji:", min_value=date.today())

    wszystkie = generuj_siatke_godzin(g_start_p, g_koniec_p)
    df_zajete = pobierz_rezerwacje_realizatora(wybrana_data, realizator)
    
    wolne_starty = []
    for g in wszystkie:
        dt_s = datetime.strptime(g, "%H:%M")
        dt_k = dt_s + timedelta(hours=godziny_int)
        
        if realizator == "Tomek" and dt_k > datetime.strptime("23:59", "%H:%M") + timedelta(minutes=1): continue
        if realizator == "Maciek" and dt_k > datetime.strptime("16:00", "%H:%M"): continue
            
        dt_k_buf = dt_k + timedelta(minutes=30)
        g_k_buf_str = "23:59" if dt_k_buf >= datetime.strptime("23:59", "%H:%M") else dt_k_buf.strftime("%H:%M")
        
        if not czy_termin_zajety(g, g_k_buf_str, df_zajete):
            wolne_starty.append(g)

    brakuje_terminow = len(wolne_starty) == 0

    if not brakuje_terminow:
        wybrana_g_start = st.selectbox("Dostępne godziny startu:", wolne_starty)
        dt_k_final = datetime.strptime(wybrana_g_start, "%H:%M") + timedelta(hours=godziny_int)
        st.success(f"✅ Wybrano: {wybrana_g_start} - {dt_k_final.strftime('%H:%M')}")
    else:
        st.error("❌ Brak wolnych terminów.")
        wybrana_g_start = None

with col2:
    st.subheader("2. Twoje dane")
    if "sukces" not in st.session_state: st.session_state.sukces = False

    if st.session_state.sukces:
        st.success("🎉 Rezerwacja przyjęta!")
        if st.button("Zarezerwuj kolejną sesję"):
            st.session_state.sukces = False
            st.rerun()
    else:
        with st.form("form_rez", clear_on_submit=True):
            imie = st.text_input("Imię i Nazwisko / Projekt *")
            email = st.text_input("E-mail *")
            telefon = st.text_input("Numer telefonu *")
            uwagi = st.text_area("Uwagi (opcjonalnie)")
            
            submit = st.form_submit_button(
                "Potwierdzam Rezerwację", 
                use_container_width=True, 
                disabled=brakuje_terminow
            )

            if submit:
                if not imie or not email or not telefon:
                    st.error("Uzupełnij wszystkie pola z gwiazdką (*)")
                elif wybrana_g_start:
                    df_final = pobierz_rezerwacje_realizatora(wybrana_data, realizator)
                    dt_k_buf = datetime.strptime(wybrana_g_start, "%H:%M") + timedelta(hours=godziny_int, minutes=30)
                    g_k_buf_str = "23:59" if dt_k_buf >= datetime.strptime("23:59", "%H:%M") else dt_k_buf.strftime("%H:%M")
                    
                    if czy_termin_zajety(wybrana_g_start, g_k_buf_str, df_final):
                        st.error("Termin zajęty!")
                    else:
                        zapisz_rezerwacje(wybrana_data.strftime("%Y-%m-%d"), wybrana_g_start, g_k_buf_str, realizator, imie, email, telefon, uwagi)
                        st.session_state.sukces = True
                        st.rerun()

# --- 5. STOPKA I KONTAKT ---
st.write("") # Odstęp dla lepszego wyglądu na mobilkach
st.divider() 

col_f1, col_f2 = st.columns(2)

with col_f1:
    st.markdown("### 📞 Kontakt bezpośredni")
    st.markdown(f"""
    **Maciek:** [+48 509 344 434](tel:+48509344434)  
    **Tomek:** [+48 798 513 689](tel:+48798513689)
    """)

with col_f2:
    # 1. Kodujemy plik do formatu tekstowego (Base64)
    import base64
    with open("b1studio_logo_pion.png", "rb") as f:
        data = f.read()
        img_base64 = base64.b64encode(data).decode()

    # 2. Wyświetlamy logo i napis w jednej linii
    st.markdown(f"""
        <h3 style="margin-top: 0;">
            <img src="data:image/png;base64,{img_base64}" width="100" style="vertical-align: middle; margin-right: 10px;">
           
        </h3>
    """, unsafe_allow_html=True)
    
    st.markdown("System rezerwacji online dla klientów b1 Studio.")
    st.caption("© 2026 b1 Studio. Wszystkie prawa zastrzeżone.")