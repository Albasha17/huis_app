import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time

# --- CONFIGURATIE ---
# Haal geheime sleutels uit de kluis
try:
    api_key = st.secrets["google_api_key"]
    # We gebruiken de Google Sheets API JSON
    creds_dict = st.secrets["gcp_service_account"]
    sheet_naam = "Huisgids Database" 
except KeyError:
    st.error("⚠️ Er ontbreken sleutels in je Secrets (google_api_key of gcp_service_account).")
    st.stop()

# --- PAGINA SETUP ---
st.set_page_config(page_title="Huisgids", page_icon="🏠", layout="centered")

# CSS voor strakke knoppen en mobiel gebruik
st.markdown("""
<style>
    div.stButton > button { width: 100%; border-radius: 12px; height: 3.5em; font-weight: 600; border: 1px solid #eee; transition: all 0.2s; }
    div.stButton > button:hover { border-color: #FF4B4B; color: #FF4B4B; }
    .stTextInput > div > div > input { font-size: 16px; padding: 12px; }
    h1 { padding-bottom: 0px; }
</style>
""", unsafe_allow_html=True)

# --- WACHTWOORD CHECK ---
def check_password():
    if st.session_state.get('password_correct', False):
        return True
    
    st.title("🔒 Beveiligd")
    st.markdown("Welkom! Voer het wachtwoord in om de huisgids te openen.")
    password_input = st.text_input("Wachtwoord:", type="password")
    
    geheim_wachtwoord = st.secrets.get("guest_password", "Welkom123")
    
    if password_input:
        if password_input == geheim_wachtwoord:
            st.session_state['password_correct'] = True
            st.rerun()
        else:
            st.error("Onjuist wachtwoord")
    return False

if not check_password():
    st.stop()

# --- GOOGLE SHEETS VERBINDING ---
@st.cache_resource
def connect_to_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# --- DATA OPHALEN & VERWERKEN ---
@st.cache_data(ttl=600)
def load_house_data():
    info_text = "GEBRUIKERSHANDLEIDING & HUISGIDS:\n\n"
    # Flags om te zien welke data we hebben (voor de knoppen)
    has_cats = False
    has_wifi = False
    has_food = False
    
    try:
        client = connect_to_gsheets()
        sheet = client.open(sheet_naam)
        
        def read_tab(tab_name, header):
            nonlocal has_cats, has_wifi, has_food
            try:
                worksheet = sheet.worksheet(tab_name)
                data = worksheet.get_all_records()
                if len(data) > 0:
                    df = pd.DataFrame(data)
                    text_chunk = f"--- {header} ---\n"
                    
                    for index, row in df.iterrows():
                        # Slimme detectie voor knoppen
                        full_row_str = str(row).lower()
                        if "wifi" in full_row_str: has_wifi = True
                        if "kat" in full_row_str or "cat" in full_row_str or "petkit" in full_row_str: has_cats = True
                        if "restaurant" in full_row_str or "pizza" in full_row_str: has_food = True

                        row_parts = []
                        for k, v in row.items():
                            val = str(v).strip()
                            if val:
                                if "Maps" in k or "Link" in k:
                                    row_parts.append(f"Google Maps Link: {val}")
                                else:
                                    row_parts.append(f"{k}: {val}")
                        text_chunk += "- " + ", ".join(row_parts) + "\n"
                    return text_chunk + "\n"
                return ""
            except gspread.WorksheetNotFound:
                return ""

        # 1. Overig
        info_text += read_tab("Overig", "BELANGRIJKE HUISREGELS")
        # 2. Apparaten
        info_text += read_tab("Apparaten", "APPARATEN & LOCATIES")
        # 3. Buurt
        info_text += read_tab("Buurt", "AANBEVELINGEN IN DE BUURT")

    except Exception as e:
        return f"Fout bij Google Sheets: {e}", False, False, False
        
    return info_text, has_wifi, has_cats, has_food

# Setup Gemini
try:
    genai.configure(api_key=api_key)
except:
    pass

# Data Laden
huis_informatie, has_wifi, has_cats, has_food = load_house_data()

# --- DE UI (VOORKANT) ---
col1, col2 = st.columns([1, 5])
with col1:
    st.image("https://cdn-icons-png.flaticon.com/512/25/25694.png", width=50)
with col2:
    st.title("Huisgids")

# 1. ZOEKBALK
vraag_input = st.text_input("Waar kan ik je mee helpen?", placeholder="Typ je vraag hier...", key="search_top")

# 2. FOTO UPLOAD
with st.expander("📷 Foto uploaden (voor apparaten)"):
    uploaded_file = st.file_uploader("Upload een foto", type=['jpg', 'jpeg', 'png'], label_visibility="collapsed")
    image = Image.open(uploaded_file) if uploaded_file else None
    if image: st.image(image, width=200, caption="Geüploade foto")

st.markdown("---")

# 3. DYNAMISCHE KNOPPEN (Op basis van je Sheet inhoud)
vraag_van_knop = None
st.caption("Snelkoppelingen:")

# Lijst met knoppen opbouwen
knoppen_lijst = []

# Altijd nuttige knoppen
knoppen_lijst.append(("🔑 Sleutels & Check-out", "Hoe werkt de check-out en waar laat ik de sleutels?"))

# Voorwaardelijke knoppen
if has_wifi:
    knoppen_lijst.append(("📶 Wifi Wachtwoord", "Wat is de naam en het wachtwoord van de wifi?"))
else:
    # Fallback als wifi niet gevonden is in tekst, toch handig om te vragen
    knoppen_lijst.append(("📶 Wifi", "Hoe werkt het internet?"))

if has_cats:
    knoppen_lijst.append(("🐈 De Katten", "Hoe werkt het voeren van de katten en de kattenbak?"))

knoppen_lijst.append(("☕️ Koffie", "Hoe werkt het koffiezetapparaat?"))
knoppen_lijst.append(("🗑️ Afval", "Wat zijn de regels voor het afval?"))

if has_food:
    knoppen_lijst.append(("🍕 Eten in de buurt", "Welke restaurants raad je aan? Geef ook de Maps links."))
    knoppen_lijst.append(("🛒 Supermarkt", "Waar is de dichtstbijzijnde supermarkt?"))

knoppen_lijst.append(("🩺 Noodgevallen", "Wat zijn de noodnummers en waar is de EHBO?"))

# Knoppen tonen in een grid van 2 breed
for i in range(0, len(knoppen_lijst), 2):
    cols = st.columns(2)
    # Knop Links
    if cols[0].button(knoppen_lijst[i][0]):
        vraag_van_knop = knoppen_lijst[i][1]
    # Knop Rechts (als die bestaat)
    if i + 1 < len(knoppen_lijst):
        if cols[1].button(knoppen_lijst[i+1][0]):
            vraag_van_knop = knoppen_lijst[i+1][1]

# --- AI LOGICA (CRASH PROOF) ---
finale_vraag = vraag_van_knop if vraag_van_knop else vraag_input

if finale_vraag:
    with st.spinner('Even zoeken...'):
        response_text = ""
        
        # PROBEER 1: Het snelle model (Flash)
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = f"""Je bent de huisgids. Info: {huis_informatie}. Vraag: {finale_vraag}. Wees kort, vriendelijk en gebruik Maps links indien beschikbaar."""
            inputs = [prompt, image] if image else [prompt]
            response = model.generate_content(inputs)
            response_text = response.text
            
        except Exception as e:
            # PROBEER 2: Fallback naar het basis model (als Flash faalt)
            # Dit lost jouw Error 404 op als de library oud is!
            try:
                # print(f"Flash faalde: {e}, overschakelen naar Pro") 
                model = genai.GenerativeModel('gemini-pro')
                # Gemini Pro ondersteunt geen beelden in de oude versie, dus alleen tekst
                prompt = f"""Je bent de huisgids. Info: {huis_informatie}. Vraag: {finale_vraag}. Wees kort en vriendelijk."""
                response = model.generate_content(prompt)
                response_text = response.text + "\n\n*(Antwoord gegenereerd met basis-model)*"
            except Exception as e2:
                st.error(f"Helaas, er is een technische fout: {e2}")
        
        if response_text:
            st.markdown("### Antwoord:")
            st.info(response_text)
