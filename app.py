import streamlit as st
import google.generativeai as genai
import os

st.title("🛠 Diagnose Modus")

# 1. Haal de sleutel op
try:
    api_key = st.secrets["google_api_key"]
    # Maskeer de sleutel voor veiligheid op scherm
    masked_key = api_key[:4] + "..." + api_key[-4:]
    st.write(f"Sleutel gevonden: `{masked_key}`")
except:
    st.error("Geen 'google_api_key' gevonden in Secrets!")
    st.stop()

# 2. Verbinden
try:
    genai.configure(api_key=api_key)
    st.success("Verbinding met Google software geslaagd.")
except Exception as e:
    st.error(f"Kon niet configureren: {e}")
    st.stop()

# 3. Vraag Google welke modellen beschikbaar zijn
st.write("Even kijken welke modellen beschikbaar zijn voor deze sleutel...")

try:
    lijst = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            lijst.append(m.name)
            
    if len(lijst) > 0:
        st.success(f"Hoera! Ik zie {len(lijst)} modellen.")
        st.json(lijst)
        st.info("Kopieer één van deze namen (bijv. `models/gemini-pro`) en zet die in je originele app.")
    else:
        st.error("Google zegt: 'Geen modellen gevonden'.")
        st.warning("Oorzaak: Waarschijnlijk is de API Key geldig, maar staat de 'Generative Language API' niet aan in je Google Project, of is er een regio-blokkade.")

except Exception as e:
    st.error(f"Fout bij ophalen modellen: {e}")
