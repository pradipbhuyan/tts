import streamlit as st
import os
import uuid
import json
import math
import time
import threading
import requests
from bs4 import BeautifulSoup
from openai import OpenAI

# ---------------- CONFIG ----------------

MODEL_NAME = "gpt-4o-mini-tts"
VOICE = "alloy"

WORDS_PER_MINUTE = 160
MAX_MINUTES_PER_FILE = 25
COST_PER_1K_CHARS = 0.015  # Update if pricing changes

BASE_DIR = "jobs"
os.makedirs(BASE_DIR, exist_ok=True)

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ---------------- UTILITIES ----------------

def estimate_stats(text):
    char_count = len(text)
    word_count = len(text.split())
    minutes = word_count / WORDS_PER_MINUTE
    cost = (char_count / 1000) * COST_PER_1K_CHARS
    files = math.ceil(minutes / MAX_MINUTES_PER_FILE)
    return char_count, word_count, minutes, cost, files


def save_state(job_id, state):
    with open(os.path.join(BASE_DIR, job_id, "state.json"), "w") as f:
        json.dump(state, f)


def load_state(job_id):
    path = os.path.join(BASE_DIR, job_id, "state.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


# ---------------- BACKGROUND WORKER ----------------

def generate_audio_job(job_id):

    job_path = os.path.join(BASE_DIR, job_id)
    state = load_state(job_id)

    text = state["text"]
    words = text.split()
    words_per_file = WORDS_PER_MINUTE * MAX_MINUTES_PER_FILE

    file_chunks = [
        " ".join(words[i:i + words_per_file])
        for i in range(0, len(words), words_per_file)
    ]

    total_files = len(file_chunks)
    state["total_files"] = total_files
    save_state(job_id, state)

    for file_index in range(state["completed_files"], total_files):

        chunk = file_chunks[file_index]

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

        file_path = os.path.join(job_path, f"part_{file_index+1}.mp3")
        with open(file_path, "wb") as f:
            f.write(final_audio)

        state["completed_files"] += 1
        save_state(job_id, state)

    state["status"] = "completed"
    save_state(job_id, state)


# ---------------- UI ----------------

st.title("Persistent Text to Audiobook Generator")

menu = st.sidebar.radio("Menu", ["Create Job", "View Jobs"])

# ---------------- CREATE JOB ----------------

if menu == "Create Job":

    option = st.radio("Input Type", ["Paste Text", "Enter URL"])
    text_content = ""

    if option == "Paste Text":
        text_content = st.text_area("Paste text", height=250)

    else:
        url = st.text_input("Enter URL")
        if url:
            response = requests.get(url)
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style"]):
                tag.extract()
            text_content = soup.get_text(separator=" ", strip=True)
            st.success("Text extracted")

    if text_content.strip():

        char_count, word_count, minutes, cost, files = estimate_stats(text_content)

        st.markdown("### Estimate")
        st.write(f"Words: {word_count:,}")
        st.write(f"Estimated Duration: {minutes:.1f} minutes")
        st.write(f"Estimated Files (25 min each): {files}")
        st.write(f"Estimated Cost: ${cost:.4f}")

        if st.button("Start Background Job"):

            job_id = str(uuid.uuid4())
            job_path = os.path.join(BASE_DIR, job_id)
            os.makedirs(job_path, exist_ok=True)

            state = {
                "job_id": job_id,
                "status": "running",
                "completed_files": 0,
                "total_files": 0,
                "text": text_content
            }

            save_state(job_id, state)

            thread = threading.Thread(target=generate_audio_job, args=(job_id,))
            thread.start()

            st.success(f"Job started! Job ID: {job_id}")
            st.info("You can safely refresh or return later.")

# ---------------- VIEW JOBS ----------------

if menu == "View Jobs":

    jobs = os.listdir(BASE_DIR)

    if not jobs:
        st.info("No jobs found.")
    else:
        for job_id in jobs:

            state = load_state(job_id)
            if not state:
                continue

            st.markdown(f"---")
            st.markdown(f"### Job: {job_id}")
            st.write(f"Status: {state['status']}")
            st.write(f"Completed Files: {state['completed_files']} / {state.get('total_files', '?')}")

            job_path = os.path.join(BASE_DIR, job_id)

            for file in sorted(os.listdir(job_path)):
                if file.endswith(".mp3"):
                    with open(os.path.join(job_path, file), "rb") as f:
                        st.download_button(
                            label=f"Download {file}",
                            data=f,
                            file_name=file,
                            mime="audio/mpeg",
                            key=f"{job_id}_{file}"
                        )
