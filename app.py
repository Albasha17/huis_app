import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import urllib.parse # Nodig voor de YouTube links

# --- CONFIGURATIE ---
SHEET_NAAM = "huisgids_db"
MODEL_NAAM = "models/gemini-2.0-flash" # Even geupdate naar 2.0 (is nieuwer/sneller), of gebruik 1.5

# Haal geheime sleutels uit de kluis
try:
    api_key = st.secrets["google_api_key"]
    creds_dict = st.secrets["gcp_service_account"]
except KeyError:
    st.error("⚠️ Er ontbreken sleutels in je Secrets.")
    st.stop()

# --- PAGINA SETUP ---
st.set_page_config(page_title="Huisgids", page_icon="🏠", layout="centered")

# CSS
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
    st.markdown("Welkom! Voer het wachtwoord in.")
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

# --- CONNECTIES ---
@st.cache_resource
def connect_to_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=600)
def load_house_data():
    info_text = "DATABASE MET APPARATEN EN LOCATIES:\n\n"
    has_cats, has_wifi, has_food = False, False, False
    
    try:
        client = connect_to_gsheets()
        sheet = client.open(SHEET_NAAM)
        
        def read_tab(tab_name, header):
            nonlocal has_cats, has_wifi, has_food
            try:
                worksheet = sheet.worksheet(tab_name)
                data = worksheet.get_all_records()
                if len(data) > 0:
                    df = pd.DataFrame(data)
                    text_chunk = f"--- {header} ---\n"
                    for index, row in df.iterrows():
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

        info_text += read_tab("Overig", "HUISHOUDELIJKE INFO")
        info_text += read_tab("Apparaten", "APPARATEN LIJST (Merk & Model)")
        info_text += read_tab("Buurt", "BUURT GIDS")

    except Exception as e:
        return f"Fout: {e}", False, False, False
        
    return info_text, has_wifi, has_cats, has_food

try:
    genai.configure(api_key=api_key)
except:
    pass

huis_informatie, has_wifi, has_cats, has_food = load_house_data()

# --- UI ---
col1, col2 = st.columns([1, 5])
with col1:
    st.image("https://cdn-icons-png.flaticon.com/512/25/25694.png", width=50)
with col2:
    st.title("Huisgids")

vraag_input = st.text_input("Waar kan ik je mee helpen?", placeholder="Typ je vraag hier...", key="search_top")

with st.expander("📷 Foto uploaden (voor apparaten)"):
    uploaded_file = st.file_uploader("Upload een foto", type=['jpg', 'jpeg', 'png'], label_visibility="collapsed")
    image = Image.open(uploaded_file) if uploaded_file else None
    if image: st.image(image, width=200)

st.markdown("---")

vraag_van_knop = None
st.caption("Snelkoppelingen:")
knoppen_lijst = []
knoppen_lijst.append(("🔑 Sleutels & Check-out", "Hoe werkt de check-out en waar laat ik de sleutels?"))
if has_wifi: knoppen_lijst.append(("📶 Wifi", "Wat is de naam en het wachtwoord van de wifi?"))
if has_cats: knoppen_lijst.append(("🐈 De Katten", "Hoe werkt het voeren van de katten en de kattenbak?"))
knoppen_lijst.append(("☕️ Koffie", "Hoe werkt het koffiezetapparaat?"))
knoppen_lijst.append(("🗑️ Afval", "Wat zijn de regels voor het afval?"))
if has_food: knoppen_lijst.append(("🍕 Eten in de buurt", "Welke restaurants raad je aan?"))
knoppen_lijst.append(("🩺 Noodgevallen", "Wat zijn de noodnummers?"))

for i in range(0, len(knoppen_lijst), 2):
    cols = st.columns(2)
    if cols[0].button(knoppen_lijst[i][0]): vraag_van_knop = knoppen_lijst[i][1]
    if i + 1 < len(knoppen_lijst):
        if cols[1].button(knoppen_lijst[i+1][0]): vraag_van_knop = knoppen_lijst[i+1][1]

finale_vraag = vraag_van_knop if vraag_van_knop else vraag_input

# --- AI ANTWOORD GENERATOR ---
if finale_vraag:
    with st.spinner('Handleidingen raadplegen...'):
        response_text = ""
        
        # We bouwen een slimme prompt die vraagt om uitgebreide stappenplannen
        prompt = f"""
        Je bent de pro-actieve huisgids. Gebruik de database hieronder.
        
        DATABASE MET APPARATEN EN REGELS:
        {huis_informatie}
        
        VRAAG VAN GAST: {finale_vraag}
        
        INSTRUCTIES VOOR JOUW ANTWOORD:
        1. Identificatie: Kijk eerst of de vraag over een apparaat gaat dat in de lijst staat. Zo ja, zoek het Merk en Model erbij.
        2. Handleiding Kennis: Als het een "Hoe werkt dit?" of "Probleem" vraag is:
           - Gebruik jouw algemene AI-kennis van dit specifieke merk en model.
           - Geef een duidelijk STAPPENPLAN (Stap 1, Stap 2, etc.) hoe het werkt. Wees heel praktisch.
        3. YouTube Link: Als het over een apparaat gaat, genereer dan ONDERAAN je antwoord een YouTube zoek-link in dit formaat:
           "🎥 [Bekijk instructievideo op YouTube](https://www.youtube.com/results?search_query=MERK+MODEL+ONDERWERP)"
           (Vul MERK, MODEL en ONDERWERP zelf in op basis van de vraag).
        4. Locaties: Als het over restaurants gaat, toon ALTIJD de Google Maps link als die in de data staat.
        5. Wees vriendelijk.
        """

        try:
            # Probeer eerst het nieuwste model
            model = genai.GenerativeModel('gemini-1.5-flash') # Of 2.0-flash als beschikbaar
            inputs = [prompt, image] if image else [prompt]
            response = model.generate_content(inputs)
            response_text = response.text
            
        except Exception as e:
            try:
                # Fallback naar Pro
                model = genai.GenerativeModel('gemini-pro')
                response = model.generate_content(prompt)
                response_text = response.text
            except Exception as e2:
                st.error("Technische fout. Probeer het later nog eens.")
        
        if response_text:
            st.markdown("### Antwoord:")
            st.info(response_text)

# Debug
with st.expander("🔧 Beheerder: Check verbinding", expanded=False):
    if "Fout" in huis_informatie:
        st.error(f"🚨 Verbinding mislukt met '{SHEET_NAAM}'.")
        st.code(huis_informatie)
    else:
        st.success(f"✅ Verbinding met '{SHEET_NAAM}' is goed!")
