# --- PAGINA SETUP MOET ALTIJD EERST ---
import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="Huisgids", page_icon="🏠", layout="centered")

# --- BEVEILIGING CHECK ---
def check_password():
    """Geeft True terug als de gebruiker het juiste wachtwoord heeft."""
    
    # 1. Kijk of we het wachtwoord al weten in deze sessie
    if st.session_state.get('password_correct', False):
        return True

    # 2. Toon invulveld
    st.title("🔒 Beveiligde Huisgids")
    password_input = st.text_input("Voer het wachtwoord in:", type="password")

    # 3. Check het wachtwoord
    if password_input:
        if password_input == st.secrets["guest_password"]:
            st.session_state['password_correct'] = True
            st.rerun()  # Herlaad de pagina om de app te tonen
        else:
            st.error("😕 Dat wachtwoord klopt niet.")
    
    return False

# Als het wachtwoord NIET goed is, STOP hier.
if not check_password():
    st.stop()

# --- HIERONDER BEGINT PAS JE ECHTE APP ---
# (Plak hier de rest van je code: CSS, Imports, Google Sheets connectie, etc.)
st.title("🏠 Welkom Thuis")
# ... de rest van je app ...

# --- CONFIGURATIE ---
# We halen de API key nu veilig uit de secrets (zowel lokaal als online)
try:
    api_key = st.secrets["google_api_key"]
except KeyError:
    st.error("⚠️ Je bent de 'google_api_key' vergeten in je Secrets te zetten!")
    st.stop()

# De naam van je sheet
sheet_naam = "huisgids_db"

# --- SETUP GOOGLE SHEETS API ---
# We halen de inloggegevens veilig uit st.secrets
def connect_to_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # Haal de credentials uit secrets.toml
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

# --- FUNCTIE: DATA OPHALEN ---
@st.cache_data(ttl=600)
def load_house_data():
    info_text = "GEBRUIKERSHANDLEIDING & HUISGIDS:\n\n"
    
    try:
        client = connect_to_gsheets()
        sheet = client.open(sheet_naam)
        
        # Hulpfunctie om tabblad te lezen
        def read_tab(tab_name, header):
            try:
                worksheet = sheet.worksheet(tab_name)
                data = worksheet.get_all_records()
                df = pd.DataFrame(data)
                
                text_chunk = f"--- {header} ---\n"
                for index, row in df.iterrows():
                    # Plak alle cellen van een rij aan elkaar
                    row_text = ", ".join([f"{k}: {v}" for k, v in row.items() if str(v).strip() != ""])
                    text_chunk += f"- {row_text}\n"
                return text_chunk + "\n"
            except gspread.WorksheetNotFound:
                return "" # Tabblad bestaat niet, negeren

        # 1. Overig / Huisregels
        info_text += read_tab("Overig", "BELANGRIJKE HUISREGELS")
        
        # 2. Apparaten
        info_text += read_tab("Apparaten", "APPARATEN & LOCATIES")
        
        # 3. Buurt
        info_text += read_tab("Buurt", "AANBEVELINGEN IN DE BUURT")

    except Exception as e:
        return f"Fout bij verbinden met Google Sheets: {e}"
        
    return info_text

# Setup Gemini
try:
    genai.configure(api_key=api_key)
except:
    pass

# Laad data
huis_informatie = load_house_data()

# --- PAGINA SETUP ---
st.set_page_config(page_title="Huisgids", page_icon="🏠", layout="centered")

# CSS
st.markdown("""
<style>
    div.stButton > button { width: 100%; border-radius: 12px; height: 3em; font-weight: bold; border: 1px solid #eee; }
    .stTextInput > div > div > input { font-size: 16px; }
</style>
""", unsafe_allow_html=True)

st.title("🏠 Welkom Thuis")
st.markdown("Ik ben je digitale conciërge. Klik op een voorbeeld of typ je vraag.")

# --- KNOPPEN ---
col1, col2 = st.columns(2)
vraag_van_knop = None

with col1:
    if st.button("🔑 Sleutels & Regels"): vraag_van_knop = "Vertel me over de sleutels en huisregels"
    if st.button("🗑️ Afval"): vraag_van_knop = "Wanneer moet het afval weg?"
    if st.button("📶 Wifi"): vraag_van_knop = "Wat is de wifi code?"
    if st.button("☕️ Apparatuur"): vraag_van_knop = "Hoe werkt de apparatuur in de keuken?"

with col2:
    if st.button("🍕 Restaurants"): vraag_van_knop = "Welke restaurants raad je aan?"
    if st.button("🛒 Winkels"): vraag_van_knop = "Waar zijn winkels in de buurt?"
    if st.button("🐈 De Katten"): vraag_van_knop = "Instructies voor de katten?"
    if st.button("🩺 Nood"): vraag_van_knop = "Noodnummers en dokter?"

st.markdown("---")

# --- FOTO & INPUT ---
st.write("**Iets onduidelijk? Maak een foto!**")
uploaded_file = st.file_uploader("Upload foto", type=['jpg', 'jpeg', 'png'], label_visibility="collapsed")
image = Image.open(uploaded_file) if uploaded_file else None
if image: st.image(image, width=200)

vraag_input = st.text_input("Of typ hier je vraag:", key="input_field")
finale_vraag = vraag_van_knop if vraag_van_knop else vraag_input

# --- ANTWOORD ---
if finale_vraag:
    if "PLAK" in api_key:
        st.warning("⚠️ Check je API key in de code.")
    else:
        with st.spinner('Contact maken met het huis...'):
            try:
                model = genai.GenerativeModel('models/gemini-2.5-flash'
                prompt = f"""
                Je bent de huisgids. Gebruik deze database:
                {huis_informatie}
                
                VRAAG: {finale_vraag}
                Antwoord vriendelijk en kort.
                """
                inputs = [prompt, image] if image else [prompt]
                response = model.generate_content(inputs)
                st.markdown("### Antwoord:")
                st.info(response.text)
            except Exception as e:
                st.error(f"Error: {e}")
