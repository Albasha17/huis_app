import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import hashlib
from streamlit_mic_recorder import speech_to_text

# --- CONFIGURATIE ---
SHEET_NAAM = "huisgids_db"
MODEL_NAAM = "models/gemini-2.5-flash" 

try:
    api_key = st.secrets["google_api_key"]
    creds_dict = st.secrets["gcp_service_account"]
    geheim_wachtwoord = st.secrets.get("guest_password", "Welkom123")
except KeyError:
    st.error("⚠️ Er ontbreken sleutels in je Secrets.")
    st.stop()

# --- PAGINA SETUP ---
st.set_page_config(page_title="Huisgids", page_icon="🏠", layout="centered")

# --- TAAL & VERTALINGEN ---
if 'lang' not in st.session_state:
    st.session_state.lang = 'nl'

def toggle_language():
    st.session_state.lang = 'en' if st.session_state.lang == 'nl' else 'nl'

T = {
    'nl': {
        'title': 'Huisgids',
        'subtitle': 'Je digitale conciërge.',
        'search_placeholder': 'Typ je vraag hier...',
        'login_title': '🔒 Beveiligd',
        'login_msg': 'Welkom! Voer het wachtwoord in.',
        'login_label': 'Wachtwoord:',
        'login_error': 'Onjuist wachtwoord',
        'shortcuts_header': 'Snelkoppelingen (Klik om te openen)',
        'btn_keys': '🔑 Sleutels', 'q_keys': 'Hoe werkt de check-out en waar laat ik de sleutels?',
        'btn_wifi': '📶 Wifi', 'q_wifi': 'Wat is de naam en het wachtwoord van de wifi?',
        'btn_cat': '🐈‍⬛ Baku', 'q_cat': 'Hoe zorg ik voor Baku? Vertel over het voeren, de kattenbak én specifiek hoe de "Cat water fountain" werkt.',
        'btn_coffee': '☕️ Koffie', 'q_coffee': 'Hoe werkt het koffiezetapparaat?',
        'btn_trash': '🗑️ Afval', 'q_trash': 'Wat zijn de regels voor het afval?',
        'btn_food': '🍕 Eten', 'q_food': 'Welke restaurants raad je aan?',
        'btn_emergency': '🩺 Nood', 'q_emergency': 'Wat zijn de noodnummers?',
        'ai_lang_instruction': 'Antwoord in het NEDERLANDS.',
        'answer_title': 'Antwoord:',
        'loading': 'Even zoeken...',
        'conn_fail': '🚨 Verbinding mislukt:',
        'conn_ok': '✅ Verbinding OK.'
    },
    'en': {
        'title': 'House Guide',
        'subtitle': 'Your digital concierge.',
        'search_placeholder': 'Type your question here...',
        'login_title': '🔒 Secured',
        'login_msg': 'Welcome! Please enter the password.',
        'login_label': 'Password:',
        'login_error': 'Incorrect password',
        'shortcuts_header': 'Shortcuts (Click to expand)',
        'btn_keys': '🔑 Keys', 'q_keys': 'How does check-out work and where do I leave the keys?',
        'btn_wifi': '📶 Wifi', 'q_wifi': 'What is the wifi name and password?',
        'btn_cat': '🐈‍⬛ Baku', 'q_cat': 'How do I care for Baku? Tell me about feeding, the litter box AND specifically how the "Cat water fountain" works.',
        'btn_coffee': '☕️ Coffee', 'q_coffee': 'How does the coffee machine work?',
        'btn_trash': '🗑️ Trash', 'q_trash': 'What are the rules for trash/recycling?',
        'btn_food': '🍕 Food', 'q_food': 'Which restaurants do you recommend?',
        'btn_emergency': '🩺 Emergency', 'q_emergency': 'What are the emergency numbers?',
        'ai_lang_instruction': 'Answer in ENGLISH.',
        'answer_title': 'Answer:',
        'loading': 'Searching...',
        'conn_fail': '🚨 Connection failed:',
        'conn_ok': '✅ Connection OK.'
    }
}
txt = T[st.session_state.lang]

# --- CSS STYLING (CRUCIAAL VOOR UITLIJNING) ---
st.markdown("""
<style>
    /* 1. Algemene knop styling */
    div.stButton > button { 
        width: 100%; 
        border-radius: 12px; 
        height: 3rem; 
        font-weight: 600; 
        border: 1px solid #eee; 
    }
    div.stButton > button:hover { border-color: #FF4B4B; color: #FF4B4B; }
    
    /* 2. Zoekbalk hoogte */
    .stTextInput > div > div > input { height: 3rem; font-size: 16px; padding: 12px; }
    
    /* 3. CAMERAKNOP HACK: Maak de file uploader compact en onzichtbaar over een icoon */
    [data-testid="stFileUploader"] {
        padding: 0px;
        margin: 0px;
    }
    [data-testid="stFileUploader"] section {
        padding: 0px;
        min-height: 0px;
        background-color: transparent;
        border: 1px solid #eee;
        border-radius: 12px;
        height: 3rem;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    /* Verberg de tekst 'Drag and drop file here' */
    [data-testid="stFileUploader"] section > div {
        display: none;
    }
    /* Laat de kleine button 'Browse files' lijken op een emoji knop */
    [data-testid="stFileUploader"] button {
        width: 100%;
        border: none;
        background: transparent;
        color: transparent; 
    }
    /* Voeg een emoji toe via CSS omdat we de text niet kunnen aanpassen */
    [data-testid="stFileUploader"] section::after {
        content: "📷";  /* Camera Emoji */
        font-size: 24px;
        position: absolute;
        pointer-events: none;
    }
    
    /* 4. Kolommen witruimte weghalen */
    [data-testid="column"] { padding-top: 0px; }
    
    /* 5. Taalknop Rechtsboven */
    .lang-btn-container { text-align: right; }
</style>
""", unsafe_allow_html=True)

# --- HEADER FUNCTIE (TITEL + TAALKNOP) ---
# Deze gebruiken we op BEIDE pagina's voor consistentie
def render_header(title_text, subtitle_text=None):
    c1, c2 = st.columns([6, 1]) # Grote linkerkolom, kleine rechterkolom
    with c1:
        st.title(title_text)
        if subtitle_text:
            st.markdown(subtitle_text)
    with c2:
        # Taalknop rechtsboven
        if st.button("🇳🇱/🇬🇧", key=f"lang_btn_{title_text}"):
            toggle_language()
            st.rerun()
    st.write("") # Witruimte

# --- AUTHENTICATIE ---
def get_password_hash(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_auth():
    if st.session_state.get('password_correct', False): return True
    query_params = st.query_params
    stored_token = query_params.get("token", None)
    correct_hash = get_password_hash(geheim_wachtwoord)
    if stored_token == correct_hash:
        st.session_state['password_correct'] = True
        return True
    
    # LOGIN SCHERM UI
    render_header(txt['login_title']) # Gebruik de header functie
    
    st.markdown(txt['login_msg'])
    pwd = st.text_input(txt['login_label'], type="password")
    
    if pwd:
        if pwd == geheim_wachtwoord:
            st.session_state['password_correct'] = True
            st.query_params["token"] = correct_hash
            st.rerun()
        else: st.error(txt['login_error'])
    return False

if not check_auth(): st.stop()

# --- CONNECTIES ---
@st.cache_resource
def connect_to_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=600)
def load_house_data():
    info = "DATABASE:\n\n"; cats, wifi, food = False, False, False
    try:
        client = connect_to_gsheets()
        sheet = client.open(SHEET_NAAM)
        def read_tab(name, head):
            nonlocal cats, wifi, food
            try:
                ws = sheet.worksheet(name); d = ws.get_all_records()
                if not d: return ""
                df = pd.DataFrame(d); t = f"--- {head} ---\n"
                for i, r in df.iterrows():
                    s = str(r).lower()
                    if "wifi" in s: wifi=True
                    if "kat" in s or "cat" in s or "baku" in s: cats=True
                    if "restaurant" in s or "pizza" in s: food=True
                    p = []
                    for k,v in r.items():
                        val=str(v).strip()
                        if val:
                            if "Maps" in k or "Link" in k: p.append(f"Maps: {val}")
                            elif "Web" in k: p.append(f"Web: {val}")
                            else: p.append(f"{k}: {val}")
                    t += "- " + ", ".join(p) + "\n"
                return t + "\n"
            except: return ""
        info += read_tab("Overig", "HUISHOUDELIJKE INFO")
        info += read_tab("Apparaten", "APPARATEN LIJST")
        info += read_tab("Buurt", "BUURT GIDS")
    except Exception as e: return f"Fout: {e}", False, False, False
    return info, wifi, cats, food

try: genai.configure(api_key=api_key)
except: pass

huis_informatie, has_wifi, has_cats, has_food = load_house_data()

# --- MAIN UI OPBOUW ---

# 1. HEADER (Titel + Taalknop)
render_header(txt['title'], txt['subtitle'])

# 2. ZOEKBALK, MIC & CAMERA (Naast elkaar op Desktop, gestapeld op Mobiel)
if "search_query" not in st.session_state: st.session_state.search_query = ""

# Layout: [Zoekbalk (6), Mic (1), Cam (1)]
# Op desktop staan ze naast elkaar. Op mobiel stapelen ze onder elkaar.
# Omdat we 'links uitgelijnd' willen op mobiel, is dit de standaard werking.
c_search, c_mic, c_cam = st.columns([6, 1, 1])

with c_search:
    text_input_val = st.text_input("Zoek", placeholder=txt['search_placeholder'], key="search_query", label_visibility="collapsed")

with c_mic:
    # Voice button
    voice_text = speech_to_text(language=st.session_state.lang, start_prompt="🎤", stop_prompt="⏹️", just_once=True, key='mic_recorder')

with c_cam:
    # Upload button (Gebruikt CSS hack om eruit te zien als 📷 knop)
    uploaded_file = st.file_uploader("Cam", type=['jpg', 'jpeg', 'png'], label_visibility="collapsed")

# Logic: Voice update
if voice_text and voice_text != st.session_state.search_query:
    st.session_state.search_query = voice_text
    st.rerun()

# Logic: Foto display
image = Image.open(uploaded_file) if uploaded_file else None
if image: st.image(image, width=200)

st.markdown("---")

# 3. SNELKOPPELINGEN (INKLAPBAAR)
vraag_van_knop = None
with st.expander(txt['shortcuts_header'], expanded=False):
    knoppen = []
    knoppen.append((txt['btn_keys'], txt['q_keys']))
    if has_wifi: knoppen.append((txt['btn_wifi'], txt['q_wifi']))
    if has_cats: knoppen.append((txt['btn_cat'], txt['q_cat']))
    knoppen.append((txt['btn_coffee'], txt['q_coffee']))
    knoppen.append((txt['btn_trash'], txt['q_trash']))
    if has_food: knoppen.append((txt['btn_food'], txt['q_food']))
    knoppen.append((txt['btn_emergency'], txt['q_emergency']))

    for i in range(0, len(knoppen), 2):
        c = st.columns(2)
        if c[0].button(knoppen[i][0]): vraag_van_knop = knoppen[i][1]
        if i+1 < len(knoppen):
            if c[1].button(knoppen[i+1][0]): vraag_van_knop = knoppen[i+1][1]

# FINALE VRAAG
final_q = vraag_van_knop if vraag_van_knop else text_input_val

if final_q:
    with st.spinner(txt['loading']):
        res = ""
        prompt = f"""Huisgids. Taal: {txt['ai_lang_instruction']}.
        DB: {huis_informatie}
        Vraag: {final_q}
        Regels:
        1. Antwoord obv DB.
        2. Apparaten: Stap-voor-stap.
        3. YouTube: "🎥 [Video](https://www.youtube.com/results?search_query=MERK+MODEL+ONDERWERP)"
        4. Maps/Web links tonen.
        """
        try:
            m = genai.GenerativeModel(MODEL_NAAM)
            inp = [prompt, image] if image else [prompt]
            r = m.generate_content(inp); res = r.text
        except:
            try:
                m = genai.GenerativeModel('gemini-1.5-flash')
                inp = [prompt, image] if image else [prompt]
                r = m.generate_content(inp); res = r.text
            except Exception as e: st.error(f"Err: {e}")
        
        if res:
            st.markdown(f"### {txt['answer_title']}")
            st.info(res)

with st.expander("🔧 Status", expanded=False):
    if "Fout" in huis_informatie: st.error(f"{txt['conn_fail']} {huis_informatie}")
    else: st.success(f"{txt['conn_ok']} - {SHEET_NAAM}")
