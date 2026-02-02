import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import hashlib
# Nieuwe import voor spraak
from streamlit_mic_recorder import speech_to_text

# --- CONFIGURATIE ---
SHEET_NAAM = "huisgids_db"
MODEL_NAAM = "models/gemini-2.5-flash" 

# Haal geheime sleutels uit de kluis
try:
    api_key = st.secrets["google_api_key"]
    creds_dict = st.secrets["gcp_service_account"]
    geheim_wachtwoord = st.secrets.get("guest_password", "Welkom123")
except KeyError:
    st.error("⚠️ Er ontbreken sleutels in je Secrets.")
    st.stop()

# --- PAGINA SETUP ---
st.set_page_config(page_title="Huisgids / House Guide", page_icon="🏠", layout="centered")

# --- TAAL INSTELLINGEN ---
if 'lang' not in st.session_state:
    st.session_state.lang = 'nl'

def toggle_language():
    st.session_state.lang = 'en' if st.session_state.lang == 'nl' else 'nl'

# Woordenboek voor vertalingen
T = {
    'nl': {
        'title': 'Huisgids',
        'subtitle': 'Je digitale conciërge.',
        'search_placeholder': 'Typ je vraag hier...',
        'voice_btn': '🎤 Spreek je vraag in',
        'voice_instruction': 'Klik om te spreken',
        'upload_text': '📷 Foto uploaden (voor apparaten)',
        'upload_btn': 'Upload een foto',
        'login_title': '🔒 Beveiligd',
        'login_msg': 'Welkom! Voer het wachtwoord in.',
        'login_label': 'Wachtwoord:',
        'login_error': 'Onjuist wachtwoord',
        'shortcuts': 'Snelkoppelingen:',
        'btn_keys': '🔑 Sleutels',
        'q_keys': 'Hoe werkt de check-out en waar laat ik de sleutels?',
        'btn_wifi': '📶 Wifi',
        'q_wifi': 'Wat is de naam en het wachtwoord van de wifi?',
        'btn_cat': '🐈‍⬛ Baku',
        # HIER IS DE AANPASSING VOOR DE WATERFONTEIN:
        'q_cat': 'Hoe zorg ik voor Baku? Vertel over het voeren, de kattenbak én specifiek hoe de "Cat water fountain" werkt.',
        'btn_coffee': '☕️ Koffie',
        'q_coffee': 'Hoe werkt het koffiezetapparaat?',
        'btn_trash': '🗑️ Afval',
        'q_trash': 'Wat zijn de regels voor het afval?',
        'btn_food': '🍕 Eten',
        'q_food': 'Welke restaurants raad je aan?',
        'btn_emergency': '🩺 Nood',
        'q_emergency': 'Wat zijn de noodnummers?',
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
        'voice_btn': '🎤 Speak your question',
        'voice_instruction': 'Click to speak',
        'upload_text': '📷 Upload photo (for devices)',
        'upload_btn': 'Upload a photo',
        'login_title': '🔒 Secured',
        'login_msg': 'Welcome! Please enter the password.',
        'login_label': 'Password:',
        'login_error': 'Incorrect password',
        'shortcuts': 'Shortcuts:',
        'btn_keys': '🔑 Keys',
        'q_keys': 'How does check-out work and where do I leave the keys?',
        'btn_wifi': '📶 Wifi',
        'q_wifi': 'What is the wifi name and password?',
        'btn_cat': '🐈‍⬛ Baku',
        # ENGELSE AANPASSING VOOR WATERFONTEIN:
        'q_cat': 'How do I care for Baku? Tell me about feeding, the litter box AND specifically how the "Cat water fountain" works.',
        'btn_coffee': '☕️ Coffee',
        'q_coffee': 'How does the coffee machine work?',
        'btn_trash': '🗑️ Trash',
        'q_trash': 'What are the rules for trash/recycling?',
        'btn_food': '🍕 Food',
        'q_food': 'Which restaurants do you recommend?',
        'btn_emergency': '🩺 Emergency',
        'q_emergency': 'What are the emergency numbers?',
        'ai_lang_instruction': 'Answer in ENGLISH.',
        'answer_title': 'Answer:',
        'loading': 'Searching...',
        'conn_fail': '🚨 Connection failed:',
        'conn_ok': '✅ Connection OK.'
    }
}

txt = T[st.session_state.lang]

# --- CSS ---
st.markdown("""
<style>
    div.stButton > button { width: 100%; border-radius: 12px; height: 3.5em; font-weight: 600; border: 1px solid #eee; transition: all 0.2s; }
    div.stButton > button:hover { border-color: #FF4B4B; color: #FF4B4B; }
    .stTextInput > div > div > input { font-size: 16px; padding: 12px; }
    /* Mobiele kolommen fix */
    [data-testid="column"] { width: 50% !important; flex: 1 1 50% !important; min-width: 50% !important; }
    h1 { padding-bottom: 0px; }
</style>
""", unsafe_allow_html=True)

# --- AUTHENTICATIE ---
def get_password_hash(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_auth():
    if st.session_state.get('password_correct', False):
        return True
    
    query_params = st.query_params
    stored_token = query_params.get("token", None)
    correct_hash = get_password_hash(geheim_wachtwoord)

    if stored_token == correct_hash:
        st.session_state['password_correct'] = True
        return True

    st.title(txt['login_title'])
    st.markdown(txt['login_msg'])
    st.button("🇳🇱 / 🇬🇧", on_click=toggle_language)
    
    password_input = st.text_input(txt['login_label'], type="password")
    if password_input:
        if password_input == geheim_wachtwoord:
            st.session_state['password_correct'] = True
            st.query_params["token"] = correct_hash
            st.rerun()
        else:
            st.error(txt['login_error'])
    return False

if not check_auth():
    st.stop()

# --- CONNECTIES ---
@st.cache_resource
def connect_to_gsheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=600)
def load_house_data():
    info_text = "DATABASE:\n\n"
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
                        if "kat" in full_row_str or "cat" in full_row_str or "baku" in full_row_str: has_cats = True
                        if "restaurant" in full_row_str or "pizza" in full_row_str: has_food = True

                        row_parts = []
                        for k, v in row.items():
                            val = str(v).strip()
                            if val:
                                if "Maps" in k or "Link" in k:
                                    row_parts.append(f"Google Maps Link: {val}")
                                elif "Web" in k or "Site" in k:
                                    row_parts.append(f"Website: {val}")
                                else:
                                    row_parts.append(f"{k}: {val}")
                        text_chunk += "- " + ", ".join(row_parts) + "\n"
                    return text_chunk + "\n"
                return ""
            except gspread.WorksheetNotFound:
                return ""

        info_text += read_tab("Overig", "HUISHOUDELIJKE INFO")
        info_text += read_tab("Apparaten", "APPARATEN LIJST")
        info_text += read_tab("Buurt", "BUURT GIDS")

    except Exception as e:
        return f"Fout: {e}", False, False, False
        
    return info_text, has_wifi, has_cats, has_food

try:
    genai.configure(api_key=api_key)
except:
    pass

huis_informatie, has_wifi, has_cats, has_food = load_house_data()

# --- UI OPBOUW ---
col_head1, col_head2 = st.columns([5, 1])
with col_head1:
    st.title(txt['title'])
with col_head2:
    if st.button("🇳🇱/🇬🇧"):
        toggle_language()
        st.rerun()

st.markdown(txt['subtitle'])

# --- NIEUW: SPRAAK GEDEELTE ---
# We maken twee kolommen: links tekst input, rechts microfoon
col_search, col_mic = st.columns([4, 1])

with col_search:
    text_input_val = st.text_input("", placeholder=txt['search_placeholder'], key="search_text_field")

with col_mic:
    # De microfoon knop. Als je spreekt, komt de tekst in 'voice_text'
    # Justify zorgt dat hij mooi uitlijnt
    st.write("") # Klein beetje witruimte
    st.write("") 
    voice_text = speech_to_text(language=st.session_state.lang, start_prompt="🎤", stop_prompt="⏹️", just_once=True, key='mic')

# Bepaal wat de input is: stem of typen?
vraag_input = None
if voice_text:
    vraag_input = voice_text
elif text_input_val:
    vraag_input = text_input_val

# Upload
with st.expander(txt['upload_text']):
    uploaded_file = st.file_uploader(txt['upload_btn'], type=['jpg', 'jpeg', 'png'], label_visibility="collapsed")
    image = Image.open(uploaded_file) if uploaded_file else None
    if image: st.image(image, width=200)

st.markdown("---")

# --- KNOPPEN ---
vraag_van_knop = None
st.caption(txt['shortcuts'])
knoppen_lijst = []

knoppen_lijst.append((txt['btn_keys'], txt['q_keys']))
if has_wifi: knoppen_lijst.append((txt['btn_wifi'], txt['q_wifi']))
if has_cats: knoppen_lijst.append((txt['btn_cat'], txt['q_cat'])) # Bevat nu waterfontein instructie
knoppen_lijst.append((txt['btn_coffee'], txt['q_coffee']))
knoppen_lijst.append((txt['btn_trash'], txt['q_trash']))
if has_food: knoppen_lijst.append((txt['btn_food'], txt['q_food']))
knoppen_lijst.append((txt['btn_emergency'], txt['q_emergency']))

for i in range(0, len(knoppen_lijst), 2):
    cols = st.columns(2)
    if cols[0].button(knoppen_lijst[i][0]): vraag_van_knop = knoppen_lijst[i][1]
    if i + 1 < len(knoppen_lijst):
        if cols[1].button(knoppen_lijst[i+1][0]): vraag_van_knop = knoppen_lijst[i+1][1]

finale_vraag = vraag_van_knop if vraag_van_knop else vraag_input

# --- AI ANTWOORD GENERATOR ---
if finale_vraag:
    # Als het van voice komt, toon even wat er verstaan is
    if voice_text:
        st.info(f"🎤: \"{voice_text}\"")
        
    with st.spinner(txt['loading']):
        response_text = ""
        
        prompt = f"""
        Je bent de huisgids.
        TAAL INSTRUCTIE: {txt['ai_lang_instruction']}
        
        DATABASE:
        {huis_informatie}
        
        VRAAG: {finale_vraag}
        
        REGELS:
        1. Zoek antwoord in database.
        2. Apparaten: Leg stap-voor-stap uit.
        3. YouTube: Link toevoegen "🎥 [Video](https://www.youtube.com/results?search_query=MERK+MODEL+ONDERWERP)"
        4. Maps/Web: Geef links als beschikbaar.
        """

        try:
            model = genai.GenerativeModel(MODEL_NAAM)
            inputs = [prompt, image] if image else [prompt]
            response = model.generate_content(inputs)
            response_text = response.text
        except Exception as e:
            try:
                model = genai.GenerativeModel('gemini-1.5-flash')
                inputs = [prompt, image] if image else [prompt]
                response = model.generate_content(inputs)
                response_text = response.text
            except Exception as e2:
                st.error(f"Error: {e2}")
        
        if response_text:
            st.markdown(f"### {txt['answer_title']}")
            st.info(response_text)

with st.expander("🔧 Status", expanded=False):
    if "Fout" in huis_informatie:
        st.error(f"{txt['conn_fail']} {huis_informatie}")
    else:
        st.success(f"{txt['conn_ok']} - {SHEET_NAAM}")
