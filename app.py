from datetime import datetime, date, timedelta
import pandas as pd
from sqlalchemy import create_engine, text
import streamlit as st

try:
    db_url = st.secrets["connections"]["supabase_db"]["url"]
except KeyError:
    st.error("Błąd: Brak konfiguracji bazy danych w secrets.toml!")
    st.stop()

engine = create_engine(db_url)

def generuj_siatke_godzin(start_str, koniec_str):
    """Generuje listę godzin w danym przedziale co 30 minut, bezpiecznie dla końca dnia."""
    godziny = []
    start = datetime.strptime(start_str, "%H:%M")
    # Jeśli koniec to północ, ustawiamy bezpieczną granicę dla parsowania
    if koniec_str == "24:00" or koniec_str == "23:59":
        koniec = datetime.strptime("23:30", "%H:%M") # Ostatni możliwy start sesji o tej porze
        tomek_noc = True
    else:
        koniec = datetime.strptime(koniec_str, "%H:%M")
        tomek_noc = False
        
    curr = start
    while curr <= koniec:
        godziny.append(curr.strftime("%H:%M"))
        curr += timedelta(minutes=30)
        
    # Jeśli to zmiana Tomka, pozwalamy na ostatni start o 23:00, ale nie później
    return godziny

def pobierz_rezerwacje_realizatora(wybrana_data, realizator):
    """Pobiera zajęte przedziały czasowe dla konkretnego realizatora lub blokady globalne."""
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
    if df_zajete.empty:
        return False
    t_start = datetime.strptime(start_str, "%H:%M").time()
    
    # Bezpieczne parsowanie końca dnia dla porównań
    if koniec_str == "24:00" or koniec_str == "23:59":
        t_koniec = datetime.strptime("23:59", "%H:%M").time()
    else:
        t_koniec = datetime.strptime(koniec_str, "%H:%M").time()
    
    for _, row in df_zajete.iterrows():
        z_start = datetime.strptime(row['godzina'], "%H:%M").time()
        # Obsługa starych lub specyficznych zapisów końca dnia w bazie
        z_koniec_str = row['godzina_konca']
        if z_koniec_str == "24:00" or z_koniec_str == "23:59":
            z_koniec = datetime.strptime("23:59", "%H:%M").time()
        else:
            z_koniec = datetime.strptime(z_koniec_str, "%H:%M").time()
            
        if t_start < z_koniec and t_koniec > z_start:
            return True
    return False

def zapisz_rezerwacje(data_str, g_start, g_koniec, realizator, imie, email, uwagi):
    query = """
        INSERT INTO rezerwacje (data, godzina, godzina_konca, realizator, imie_nazwisko, email, uwagi)
        VALUES (:data, :godzina, :godzina_konca, :realizator, :imie, :email, :uwagi)
    """
    with engine.begin() as connection:
        connection.execute(text(query), {
            "data": data_str, "godzina": g_start, "godzina_konca": g_koniec,
            "realizator": realizator, "imie": imie, "email": email, "uwagi": uwagi
        })

# --- INTERFEJS KLIENTA ---
st.set_page_config(page_title="Rezerwacja Studia", page_icon="🎙️")
st.header("🎙️ Rezerwacja Sesji Nagraniowej")

col1, col2 = st.columns([1, 1], gap="large")

with col1:
    st.subheader("1. Wybierz realizatora i czas")
    
    realizator = st.selectbox("Wybierz realizatora dźwięku:", ["Maciek", "Tomek"])
    
    if realizator == "Maciek":
        godzina_start_pracy = "08:00"
        godzina_koniec_pracy = "16:00"
        st.caption("🌅 Maciek pracuje w godzinach porannych i południowych (08:00 - 16:00)")
    else:
        godzina_start_pracy = "16:00"
        godzina_koniec_pracy = "23:59" # Bezpieczna północ dla Pythona
        st.caption("🌃 Tomek pracuje w godzinach popołudniowych i nocnych (16:00 - 00:00)")
        
    dlugosc_sesji = st.selectbox("Długość sesji:", [
        "1 godzina", "2 godziny", "3 godziny", "Dłuższa sesja (Kontakt telefoniczny)"
    ])
    
    if "Dłuższa" in dlugosc_sesji:
        st.info("📞 W celu rezerwacji dłuższych sesji prosimy o kontakt: **+48 XXX XXX XXX**.")
        st.stop()
        
    godziny_int = int(dlugosc_sesji.split()[0])
    wybrana_data = st.date_input("Data sesji:", min_value=date.today(), value=date.today())

    # Generowanie siatki godzin
    wszystkie_godziny = generuj_siatke_godzin(godzina_start_pracy, godzina_koniec_pracy)
    df_zajete = pobierz_rezerwacje_realizatora(wybrana_data, realizator)
    
    wolne_godziny_startu = []
    
    for g in wszystkie_godziny:
        dt_start = datetime.strptime(g, "%H:%M")
        dt_koniec_czysty = dt_start + timedelta(hours=godziny_int)
        
        # Sprawdzamy czy sesja nie wykracza poza dyżur Tomka (czyli poza północ)
        # 23:59 + bufor traktujemy jako koniec dnia
        if realizator == "Tomek" and dt_koniec_czysty > datetime.strptime("23:59", "%H:%M") + timedelta(minutes=1):
            continue
        elif realizator == "Maciek" and dt_koniec_czysty > datetime.strptime("16:00", "%H:%M"):
            continue
            
        dt_koniec_z_buforem = dt_koniec_czysty + timedelta(minutes=30)
        
        # Formatowanie tekstu końcowego do bazy danych
        if dt_koniec_z_buforem >= datetime.strptime("23:59", "%H:%M"):
            g_koniec_buf_str = "23:59"
        else:
            g_koniec_buf_str = dt_koniec_z_buforem.strftime("%H:%M")
        
        if not czy_termin_zajety(g, g_koniec_buf_str, df_zajete):
            wolne_godziny_startu.append(g)

    if wolne_godziny_startu:
        wybrana_godzina_startu = st.selectbox("Dostępne godziny rozpoczęcia:", wolne_godziny_startu)
        dt_s = datetime.strptime(wybrana_godzina_startu, "%H:%M")
        dt_k = dt_s + timedelta(hours=godziny_int)
        st.success(f"📋 Realizator: **{realizator}** | Czas sesji: **{wybrana_godzina_startu} - {dt_k.strftime('%H:%M')}**")
    else:
        # Usunięta końcówka "a" - teraz czysta zmienna realizator
        st.error(f"❌ Brak wolnych terminów u {realizator} w tym dniu.")
        wybrana_godzina_startu = None

with col2:
    st.subheader("2. Dane kontaktowe")
    
    # Inicjalizacja zmiennej kontrolującej stan ekranu
    if "sukces_rezerwacji" not in st.session_state:
        st.session_state.sukces_rezerwacji = False

    # SCENARIUSZ A: Rezerwacja zakończona sukcesem – pokazujemy tylko podziękowanie i przycisk powrotu
    if st.session_state.sukces_rezerwacji:
        st.success(f"🎉 Zarezerwowano termin u {realizator}!")
        st.markdown("### Dziękujemy za złożenie rezerwacji!")
        st.info("Potwierdzenie wraz ze szczegółami zostało przekazane do systemu studia.")
        
        # Przycisk restartujący proces rezerwacji
        if st.button("➕ Chcę dokonać kolejnej rezerwacji", type="primary", use_container_width=True):
            st.session_state.sukces_rezerwacji = False
            st.rerun()

    # SCENARIUSZ B: Standardowy widok – pokazujemy formularz do wypełnienia
    else:
        with st.form(key="formularz_rezerwacji", clear_on_submit=True):
            imie_nazwisko = st.text_input("Imię i Nazwisko / Nazwa Projektu *")
            email = st.text_input("Adres E-mail *")
            uwagi = st.text_area("Uwagi do sesji")
            submit_button = st.form_submit_button(label="Rezerwuję termin")

            if submit_button:
                if not imie_nazwisko or not email:
                    st.error("Proszę wypełnić pola obowiązkowe.")
                elif wybrana_godzina_startu is None:
                    st.error("Nie można dokonać rezerwacji (brak wybranej godziny).")
                else:
                    df_zajete_final = pobierz_rezerwacje_realizatora(wybrana_data, realizator)
                    dt_s = datetime.strptime(wybrana_godzina_startu, "%H:%M")
                    dt_k_buf = dt_s + timedelta(hours=godziny_int, minutes=30)
                    
                    if dt_k_buf >= datetime.strptime("23:59", "%H:%M"):
                        g_koniec_buf_str = "23:59"
                    else:
                        g_koniec_buf_str = dt_k_buf.strftime("%H:%M")
                    
                    if czy_termin_zajety(wybrana_godzina_startu, g_koniec_buf_str, df_zajete_final):
                        st.error("Ten termin został przed chwilą zajęty przez kogoś innego.")
                    else:
                        data_str = wybrana_data.strftime("%Y-%m-%d")
                        # Zapis do bazy danych
                        zapisz_rezerwacje(data_str, wybrana_godzina_startu, g_koniec_buf_str, realizator, imie_nazwisko, email, uwagi)
                        
                        # Aktywujemy tryb podziękowania
                        st.session_state.sukces_rezerwacji = True
                        
                        # Efektowne balony i przeładowanie widoku
                        st.balloons()
                        st.rerun()