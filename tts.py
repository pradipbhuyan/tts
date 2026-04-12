import streamlit as st
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import tempfile
import math

# ------------------ CONFIG ------------------

MODEL_NAME = "gpt-4o-mini-tts"
VOICE = "alloy"

# ⚠️ Update if pricing changes
COST_PER_1K_CHARS = 0.015  # USD per 1000 characters (approx)

# Speech assumptions
WORDS_PER_MINUTE = 160  # Average natural speech speed
MAX_MINUTES_PER_FILE = 25

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.set_page_config(page_title="Advanced Text to MP3", layout="centered")
st.title("Text / URL to MP3 (OpenAI TTS)")

# ------------------ INPUT ------------------

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

# ------------------ ESTIMATION ------------------

if text_content.strip():

    char_count = len(text_content)
    word_count = len(text_content.split())

    estimated_cost = (char_count / 1000) * COST_PER_1K_CHARS

    estimated_minutes = word_count / WORDS_PER_MINUTE
    estimated_hours = estimated_minutes / 60

    number_of_files = math.ceil(estimated_minutes / MAX_MINUTES_PER_FILE)

    st.markdown("### 📊 Estimated Overview")

    col1, col2 = st.columns(2)
    col1.metric("Words", f"{word_count:,}")
    col2.metric("Characters", f"{char_count:,}")

    col3, col4 = st.columns(2)
    col3.metric("Estimated Duration", f"{estimated_minutes:.1f} min (~{estimated_hours:.2f} hrs)")
    col4.metric("Estimated Cost (USD)", f"${estimated_cost:.4f}")

    st.info(f"Audio will be split into approximately {number_of_files} file(s), each up to 25 minutes.")

    confirm = st.checkbox("I confirm and want to generate the audio files")

# ------------------ GENERATION ------------------

if text_content.strip() and "confirm" in locals() and confirm:

    if st.button("Generate Audio Files"):

        try:
            with st.spinner("Generating audio files..."):

                words = text_content.split()
                words_per_file = WORDS_PER_MINUTE * MAX_MINUTES_PER_FILE

                file_chunks = [
                    " ".join(words[i:i + words_per_file])
                    for i in range(0, len(words), words_per_file)
                ]

                generated_files = []

                for idx, chunk in enumerate(file_chunks):

                    # Further safe chunking for API (~4000 chars)
                    api_chunks = [
                        chunk[i:i + 4000]
                        for i in range(0, len(chunk), 4000)
                    ]

                    final_audio = b""

                    for part in api_chunks:
                        response = client.audio.speech.create(
                            model=MODEL_NAME,
                            voice=VOICE,
                            input=part
                        )
                        final_audio += response.content

                    tmp_mp3 = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
                    tmp_mp3.write(final_audio)
                    tmp_mp3.close()

                    generated_files.append((idx + 1, tmp_mp3.name))

                st.success("✅ Audio files generated successfully!")

                for file_number, file_path in generated_files:
                    st.markdown(f"### 🎧 Part {file_number}")
                    st.audio(file_path, format="audio/mp3")

                    with open(file_path, "rb") as f:
                        st.download_button(
                            label=f"Download Part {file_number}",
                            data=f,
                            file_name=f"output_part_{file_number}.mp3",
                            mime="audio/mpeg"
                        )

        except Exception as e:
            st.error(f"Error generating audio: {e}")
