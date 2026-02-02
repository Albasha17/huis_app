import streamlit as st
import google.generativeai as genai
from PIL import Image
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import hashlib
from streamlit_mic_recorder import speech_to_text
from typing import Tuple, Dict, Optional

# --- CONSTANTS ---
SHEET_NAME = "huisgids_db"
PRIMARY_MODEL = "models/gemini-1.5-flash"
FALLBACK_MODEL = "models/gemini-pro"

# Translations moved out of the main logic
TRANSLATIONS = {
    'nl': {
        'title': 'Huisgids', 'subtitle': 'Je digitale conciërge.',
        'search_placeholder': 'Typ je vraag hier...',
        'login_title': '🔒 Beveiligd', 'login_msg': 'Welkom! Voer het wachtwoord in.',
        'login_label': 'Wachtwoord', 'login_btn': 'Login', 'login_error': 'Onjuist wachtwoord',
        'shortcuts_header': 'Snelkoppelingen',
        'btn_keys': '🔑 Sleutels', 'q_keys': 'Hoe werkt de check-out en waar laat ik de sleutels?',
        'btn_wifi': '📶 Wifi', 'q_wifi': 'Wat is de naam en het wachtwoord van de wifi?',
        'btn_cat': '🐈‍⬛ Baku', 'q_cat': 'Hoe zorg ik voor Baku (voeren, kattenbak, waterfontein)?',
        'btn_coffee': '☕️ Koffie', 'q_coffee': 'Hoe werkt het koffiezetapparaat?',
        'btn_trash': '🗑️ Afval', 'q_trash': 'Wat zijn de regels voor het afval?',
        'btn_food': '🍕 Eten', 'q_food': 'Welke restaurants raad je aan?',
        'btn_emergency': '🩺 Nood', 'q_emergency': 'Wat zijn de noodnummers?',
        'ai_lang_instruction': 'Antwoord in het NEDERLANDS.',
        'answer_title': 'Antwoord', 'loading': 'Even zoeken...',
        'conn_fail': '🚨 Verbinding mislukt', 'conn_ok': '✅ Verbinding OK'
    },
    'en': {
        'title': 'House Guide', 'subtitle': 'Your digital concierge.',
        'search_placeholder': 'Type your question here...',
        'login_title': '🔒 Secured', 'login_msg': 'Welcome! Please enter the password.',
        'login_label': 'Password', 'login_btn': 'Login', 'login_error': 'Incorrect password',
        'shortcuts_header': 'Shortcuts',
        'btn_keys': '🔑 Keys', 'q_keys': 'How does check-out work and where do I leave the keys?',
        'btn_wifi': '📶 Wifi', 'q_wifi': 'What is the wifi name and password?',
        'btn_cat': '🐈‍⬛ Baku', 'q_cat': 'How do I care for Baku (feeding, litter, water fountain)?',
        'btn_coffee': '☕️ Coffee', 'q_coffee': 'How does the coffee machine work?',
        'btn_trash': '🗑️ Trash', 'q_trash': 'What are the rules for trash/recycling?',
        'btn_food': '🍕 Food', 'q_food': 'Which restaurants do you recommend?',
        'btn_emergency': '🩺 Emergency', 'q_emergency': 'What are the emergency numbers?',
        'ai_lang_instruction': 'Answer in ENGLISH.',
        'answer_title': 'Answer', 'loading': 'Searching...',
        'conn_fail': '🚨 Connection failed', 'conn_ok': '✅ Connection OK'
    }
}

# Minimal CSS for specific UI overrides (File Uploader as button)
CUSTOM_CSS = """
<style>
    /* Make the file uploader look like a square button */
    [data-testid="stFileUploader"] section { padding: 0; min-height: 0; }
    [data-testid="stFileUploader"] button { display: none; }
    [data-testid="stFileUploader"] div[data-testid="stFileUploaderDropzone"] {
        border: 1px solid #ddd; border-radius: 0.5rem; padding: 10px;
    }
    .stTextInput input { border-radius: 0.5rem; }
</style>
"""

class HouseGuideApp:
    def __init__(self):
        st.set_page_config(page_title="Huisgids", page_icon="🏠", layout="centered")
        st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
        
        # Initialize State
        if 'lang' not in st.session_state: st.session_state.lang = 'nl'
        if 'search_query' not in st.session_state: st.session_state.search_query = ""
        
        self.txt = TRANSLATIONS[st.session_state.lang]
        self.load_secrets()

    def load_secrets(self):
        """Safely loads secrets without crashing the app."""
        try:
            self.api_key = st.secrets["google_api_key"]
            self.creds_dict = st.secrets["gcp_service_account"]
            self.guest_password = st.secrets.get("guest_password", "Welkom123")
            genai.configure(api_key=self.api_key)
        except KeyError as e:
            st.error(f"⚠️ Configuration Error: Missing {e} in .streamlit/secrets.toml")
            st.stop()

    def check_auth(self) -> bool:
        """Handles authentication via session state or URL token."""
        if st.session_state.get('authenticated', False): return True

        # URL Token Check (for QR codes)
        token_hash = hashlib.sha256(self.guest_password.encode()).hexdigest()
        if st.query_params.get("token") == token_hash:
            st.session_state.authenticated = True
            return True

        # Login UI
        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            st.title(self.txt['login_title'])
            password = st.text_input(self.txt['login_label'], type="password")
            if st.button(self.txt['login_btn'], use_container_width=True):
                if password == self.guest_password:
                    st.session_state.authenticated = True
                    st.query_params["token"] = token_hash
                    st.rerun()
                else:
                    st.error(self.txt['login_error'])
        return False

    @st.cache_data(ttl=600, show_spinner=False)
    def fetch_data(_self) -> Tuple[str, Dict[str, bool]]:
        """Fetches Google Sheets data and detects features (Wifi/Cats/Food)."""
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        features = {'wifi': False, 'cats': False, 'food': False}
        context = "DATABASE:\n\n"

        try:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(_self.creds_dict, scope)
            client = gspread.authorize(creds)
            sheet = client.open(SHEET_NAME)

            def get_tab_content(tab_name, header):
                try:
                    ws = sheet.worksheet(tab_name)
                    data = ws.get_all_records()
                    if not data: return ""
                    
                    df = pd.DataFrame(data)
                    # Vectorized string search (faster than looping)
                    full_text = df.astype(str).apply(lambda x: x.str.lower()).to_string()
                    
                    if "wifi" in full_text: features['wifi'] = True
                    if any(k in full_text for k in ["kat", "cat", "baku"]): features['cats'] = True
                    if any(k in full_text for k in ["restaurant", "pizza", "eten"]): features['food'] = True
                    
                    return f"--- {header} ---\n{df.to_markdown(index=False)}\n\n"
                except: return ""

            context += get_tab_content("huisgids_db", "MAIN INFO")
            context += get_tab_content("Overig", "HOUSEHOLD INFO")
            context += get_tab_content("Apparaten", "APPLIANCES")
            context += get_tab_content("Buurt", "NEIGHBORHOOD")
            
            return context, features

        except Exception as e:
            return f"Error: {e}", features

    def get_ai_response(self, context: str, question: str, image: Optional[Image.Image]):
        """Queries Gemini with fallback logic."""
        prompt = f"""
        Role: Digital Concierge. Language: {self.txt['ai_lang_instruction']}
        Context: {context}
        Question: {question}
        Rules:
        1. Answer strictly based on Context.
        2. Appliances: Step-by-step.
        3. YouTube: "🎥 [Video](https://www.youtube.com/results?search_query=BRAND+MODEL+TOPIC)"
        4. Include Maps/Web links.
        """
        inputs = [prompt, image] if image else [prompt]
        
        try:
            model = genai.GenerativeModel(PRIMARY_MODEL)
            return model.generate_content(inputs).text
        except:
            try:
                # Fallback to older/stable model if Flash fails
                model = genai.GenerativeModel(FALLBACK_MODEL)
                return model.generate_content(inputs).text
            except Exception as e:
                return f"AI Error: {e}"

    def run(self):
        if not self.check_auth(): return

        # --- HEADER ---
        c1, c2 = st.columns([5, 1], vertical_alignment="center")
        c1.title(self.txt['title'])
        c1.caption(self.txt['subtitle'])
        if c2.button("🇳🇱/🇬🇧", key="lang_toggle"):
            st.session_state.lang = 'en' if st.session_state.lang == 'nl' else 'nl'
            st.rerun()

        # --- DATA LOADING ---
        db_data, feats = self.fetch_data()

        # --- SEARCH INTERFACE ---
        # Vertical alignment 'bottom' keeps the buttons aligned with the input box
        c_search, c_mic, c_cam = st.columns([6, 1, 1], vertical_alignment="bottom")
        
        with c_search:
            query = st.text_input("Search", value=st.session_state.search_query, 
                                placeholder=self.txt['search_placeholder'], label_visibility="collapsed")
        
        with c_mic:
            voice = speech_to_text(language=st.session_state.lang, start_prompt="🎤", stop_prompt="⏹️", just_once=True, key='mic')
        
        with c_cam:
            img_file = st.file_uploader("📷", type=['jpg','png'], label_visibility="collapsed")

        # Handle Voice Input
        if voice and voice != st.session_state.search_query:
            st.session_state.search_query = voice
            st.rerun()

        # --- SHORTCUT BUTTONS ---
        selected_q = None
        # Only show shortcuts if no query is typed yet
        with st.expander(self.txt['shortcuts_header'], expanded=not bool(query)):
            buttons = [(self.txt['btn_keys'], self.txt['q_keys'])]
            if feats['wifi']: buttons.append((self.txt['btn_wifi'], self.txt['q_wifi']))
            if feats['cats']: buttons.append((self.txt['btn_cat'], self.txt['q_cat']))
            buttons += [
                (self.txt['btn_coffee'], self.txt['q_coffee']),
                (self.txt['btn_trash'], self.txt['q_trash'])
            ]
            if feats['food']: buttons.append((self.txt['btn_food'], self.txt['q_food']))
            buttons.append((self.txt['btn_emergency'], self.txt['q_emergency']))

            grid = st.columns(2)
            for i, (label, q) in enumerate(buttons):
                if grid[i % 2].button(label, use_container_width=True):
                    selected_q = q

        # --- RESULT GENERATION ---
        final_q = selected_q if selected_q else query
        final_img = Image.open(img_file) if img_file else None
        
        if final_img: st.image(final_img, width=200)

        if final_q:
            st.divider()
            st.subheader(self.txt['answer_title'])
            with st.spinner(self.txt['loading']):
                response = self.get_ai_response(db_data, final_q, final_img)
                st.markdown(response)

        # Debug Footer
        if "Error" in db_data: st.sidebar.error(f"{self.txt['conn_fail']}")
        else: st.sidebar.success(f"{self.txt['conn_ok']}")

if __name__ == "__main__":
    app = HouseGuideApp()
    app.run()
