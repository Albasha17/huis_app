import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURATIE ---
# Haal geheime sleutels uit de kluis
try:
    api_key = st.secrets["google_api_key"]
    sheet_naam = "Huisgids Database" # Zorg dat je Google Sheet precies zo heet
except KeyError:
    st.error("⚠️ Er ontbreken sleutels in je Secrets (google_api_key).")
    st.stop()

# --- PAGINA SETUP ---
st.set_page_config(page_title="Huisgids", page_icon="🏠", layout="centered")

# CSS voor strakke knoppen en mobiel gebruik
st.markdown("""
<style>
    div.stButton > button { width: 100%; border-radius: 12px; height: 3em; font-weight: bold; border: 1px solid #eee; }
    .stTextInput > div > div > input { font-size: 16px; padding: 12px; }
    h1 { padding-bottom: 0px; }
</style>
""", unsafe_allow_html=True)

# --- WACHTWOORD CHECK ---
def check_password():
    if st.session_state.get('password_correct', False):
        return True
    
    st.title("🔒 Beveiligd")
    password_input = st.text_input("Wachtwoord:", type="password")
    
    # Haal wachtwoord uit secrets, of gebruik een fallback als test
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
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# --- DATA OPHALEN & VERWERKEN ---
@st.cache_data(ttl=600)
def load_house_data():
    info_text = "GEBRUIKERSHANDLEIDING & HUISGIDS:\n\n"
    
    # We houden bij welke data we hebben gevonden voor de knoppen
    found_flags = {"overig": False, "apparaten": False, "buurt": False}
    
    try:
        client = connect_to_gsheets()
        sheet = client.open(sheet_naam)
        
        def read_tab(tab_name, header, flag_key):
            try:
                worksheet = sheet.worksheet(tab_name)
                data = worksheet.get_all_records()
                
                # Check of er wel data in zit (meer dan 0 rijen)
                if len(data) > 0:
                    found_flags[flag_key] = True
                    df = pd.DataFrame(data)
                    text_chunk = f"--- {header} ---\n"
                    
                    for index, row in df.iterrows():
                        # Maak een nette zin van elke rij
                        # Specifiek: Zorg dat Google Maps links goed worden labelen
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
                return "" # Tabblad bestaat niet

        # 1. Overig / Huisregels
        info_text += read_tab("Overig", "BELANGRIJKE HUISREGELS", "overig")
        
        # 2. Apparaten
        info_text += read_tab("Apparaten", "APPARATEN & LOCATIES", "apparaten")
        
        # 3. Buurt
        info_text += read_tab("Buurt", "AANBEVELINGEN IN DE BUURT", "buurt")

    except Exception as e:
        return f"Fout bij Google Sheets: {e}", found_flags
        
    return info_text, found_flags

# Setup Gemini
try:
    genai.configure(api_key=api_key)
except:
    pass

# Laad de data (en de flags)
huis_informatie, data_flags = load_house_data()

# --- DE UI (VOORKANT) ---

st.title("🏠 Welkom op Sumatraplantsoen 100")
st.markdown("Ik ben je digitale conciërge. Typ je vraag hieronder.")

# 1. ZOEKBALK (Nu bovenaan!)
vraag_input = st.text_input("Waar kan ik je mee helpen?", placeholder="Bijv: Hoe werkt de koffie? of Waar kan ik lekker eten?", key="search_top")

# 2. FOTO UPLOAD (Direct onder zoekbalk)
uploaded_file = st.file_uploader("Of maak een foto van een apparaat", type=['jpg', 'jpeg', 'png'], label_visibility="collapsed")
image = Image.open(uploaded_file) if uploaded_file else None
if image: st.image(image, width=200, caption="Geüploade foto")

st.markdown("---")

# 3. VOORBEELD KNOPPEN (Alleen tonen als er data is)
vraag_van_knop = None

# We kijken welke categorieën data hebben en tonen alleen die knoppen
beschikbare_knoppen = []

if data_flags["overig"]:
    beschikbare_knoppen.append(("🔑 Sleutels & Regels", "Vertel me over de sleutels en huisregels"))
    beschikbare_knoppen.append(("🗑️ Afval & Ramen", "Wat zijn de regels voor afval en ramen?"))

if data_flags["apparaten"]:
    beschikbare_knoppen.append(("📶 Wifi", "Wat is de wifi naam en code?"))
    beschikbare_knoppen.append(("☕️ Koffie & Keuken", "Hoe werkt de koffiemachine en apparatuur?"))

if data_flags["buurt"]:
    beschikbare_knoppen.append(("🍕 Eten in de buurt", "Welke restaurants raad je aan? Geef ook de Google Maps links."))
    beschikbare_knoppen.append(("🛒 Supermarkten", "Waar zijn winkels in de buurt? Geef de Google Maps links."))

# Als er knoppen zijn, toon ze in een grid
if beschikbare_knoppen:
    st.caption("Of kies een snelkoppeling:")
    # Maak rijen van 2 kolommen
    for i in range(0, len(beschikbare_knoppen), 2):
        cols = st.columns(2)
        # Knop 1
        if cols[0].button(beschikbare_knoppen[i][0]):
            vraag_van_knop = beschikbare_knoppen[i][1]
        
        # Knop 2 (als die bestaat in deze rij)
        if i + 1 < len(beschikbare_knoppen):
            if cols[1].button(beschikbare_knoppen[i+1][0]):
                vraag_van_knop = beschikbare_knoppen[i+1][1]

# --- HET AI BREIN ---
finale_vraag = vraag_van_knop if vraag_van_knop else vraag_input

if finale_vraag:
    with st.spinner('Even voor je uitzoeken...'):
        try:
            # We gebruiken gemini-1.5-flash (Zorg dat requirements.txt up to date is!)
            # Als dit model errors geeft, verander naar 'gemini-pro'
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            prompt = f"""
            Je bent de gastvrije, behulpzame digitale gids van dit huis.
            Gebruik de onderstaande database om de vraag te beantwoorden.
            
            DATABASE:
            {huis_informatie}
            
            VRAAG VAN GAST: {finale_vraag}
            
            BELANGRIJKE REGELS VOOR JOUW ANTWOORD:
            1. Wees vriendelijk en kort.
            2. Als je informatie geeft over een locatie (restaurant, winkel, etc.) en er staat een 'Google Maps Link' in de data, MOET je deze tonen.
            3. Gebruik dit formaat voor links: [Naam van plek](De Link).
            4. Verzin geen feiten. Als het niet in de database staat, zeg dat dan eerlijk.
            """
            
            inputs = [prompt, image] if image else [prompt]
            response = model.generate_content(inputs)
            
            st.markdown("### Antwoord:")
            st.info(response.text)
            
        except Exception as e:
            st.error(f"Er ging iets mis: {e}")
            st.caption("Tip: Check of je Google API key klopt en of het model 'gemini-1.5-flash' beschikbaar is.")
