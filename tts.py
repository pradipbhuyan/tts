import streamlit as st
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import tempfile
import math

# Initialize OpenAI client using Streamlit secrets
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="Text/URL to MP3 (OpenAI TTS)", layout="centered")
st.title("Text or URL to MP3 Converter (OpenAI TTS)")

# ---- SETTINGS ----
MODEL_NAME = "gpt-4o-mini-tts"
VOICE = "alloy"

# ⚠️ Update this if OpenAI pricing changes
COST_PER_1K_CHARS = 0.015  # Example placeholder (adjust to current pricing)

# ---- INPUT ----
option = st.radio("Choose input type:", ["Paste Text", "Enter URL"])
text_content = ""

if option == "Paste Text":
    text_content = st.text_area("Paste your text here:", height=250)

elif option == "Enter URL":
    url = st.text_input("Enter URL:")
    if url:
        try:
            response = requests.get(url, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")

            for tag in soup(["script", "style"]):
                tag.extract()

            text_content = soup.get_text(separator=" ", strip=True)

            st.success("Text extracted successfully!")
            st.text_area("Extracted text preview:", text_content[:2000], height=200)

        except Exception as e:
            st.error(f"Error fetching URL: {e}")

# ---- WORD COUNT & COST ESTIMATION ----
if text_content.strip():

    char_count = len(text_content)
    word_count = len(text_content.split())

    estimated_cost = (char_count / 1000) * COST_PER_1K_CHARS

    st.markdown("### 📊 Text Statistics")
    col1, col2, col3 = st.columns(3)
    col1.metric("Words", f"{word_count:,}")
    col2.metric("Characters", f"{char_count:,}")
    col3.metric("Est. Cost (USD)", f"${estimated_cost:.4f}")

    st.info("Cost is estimated based on character count. Actual cost may vary slightly.")

# ---- GENERATE AUDIO ----
if st.button("Generate MP3"):

    if not text_content.strip():
        st.warning("Please provide text or a valid URL.")
    else:
        try:
            with st.spinner("Generating MP3..."):

                # Chunk text safely (~4000 characters per request)
                max_chars = 4000
                chunks = [
                    text_content[i:i + max_chars]
                    for i in range(0, len(text_content), max_chars)
                ]

                final_audio = b""

                for chunk in chunks:
                    response = client.audio.speech.create(
                        model=MODEL_NAME,
                        voice=VOICE,
                        input=chunk
                    )
                    final_audio += response.content

                tmp_mp3 = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                tmp_mp3.write(final_audio)
                tmp_mp3.close()

                st.success("✅ Audio generated successfully!")

                st.audio(tmp_mp3.name, format="audio/mp3")

                with open(tmp_mp3.name, "rb") as f:
                    st.download_button(
                        label="Download MP3",
                        data=f,
                        file_name="output.mp3",
                        mime="audio/mpeg"
                    )

        except Exception as e:
            st.error(f"Error generating audio: {e}")
