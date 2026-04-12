import streamlit as st
import requests
from bs4 import BeautifulSoup
from gtts import gTTS
import tempfile
import os

st.set_page_config(page_title="Text/URL to WAV", layout="centered")

st.title("Text or URL to WAV Converter")

# Input mode
option = st.radio("Choose input type:", ["Paste Text", "Enter URL"])

text_content = ""

# Get text input
if option == "Paste Text":
    text_content = st.text_area("Paste your text here:", height=250)

elif option == "Enter URL":
    url = st.text_input("Enter URL:")

    if url:
        try:
            response = requests.get(url, timeout=10)
            soup = BeautifulSoup(response.text, "html.parser")

            # Remove scripts and styles
            for tag in soup(["script", "style"]):
                tag.extract()

            text_content = soup.get_text(separator=" ", strip=True)

            st.success("Text extracted successfully!")
            st.text_area("Extracted text preview:", text_content[:2000], height=200)

        except Exception as e:
            st.error(f"Error fetching URL: {e}")

# Convert to WAV
if st.button("Convert to WAV"):
    if not text_content.strip():
        st.warning("Please provide text or a valid URL.")
    else:
        try:
            with st.spinner("Generating audio..."):
                tts = gTTS(text=text_content, lang="en")

                # Save temporarily as mp3 (gTTS default)
                tmp_mp3 = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                tts.save(tmp_mp3.name)

                # Convert mp3 to wav
                from pydub import AudioSegment
                sound = AudioSegment.from_mp3(tmp_mp3.name)

                tmp_wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
                sound.export(tmp_wav.name, format="wav")

                # Play audio
                st.audio(tmp_wav.name, format="audio/wav")

                # Download button
                with open(tmp_wav.name, "rb") as f:
                    st.download_button(
                        label="Download WAV",
                        data=f,
                        file_name="output.wav",
                        mime="audio/wav"
                    )

                os.unlink(tmp_mp3.name)

        except Exception as e:
            st.error(f"Error generating audio: {e}")
