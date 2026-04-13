import streamlit as st
import os
import uuid
import json
import math
import threading
import requests
import time
import shutil
from bs4 import BeautifulSoup
from openai import OpenAI

# ---------------- CONFIG ----------------

MODEL_NAME = "gpt-4o-mini-tts"
TEXT_MODEL = "gpt-4o-mini"
VOICE = "alloy"

WORDS_PER_MINUTE = 160
MAX_MINUTES_PER_FILE = 25
COST_PER_1K_CHARS = 0.015

BASE_DIR = "jobs"
os.makedirs(BASE_DIR, exist_ok=True)

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ---------------- UTILITIES ----------------

def save_state(job_id, state):
    with open(os.path.join(BASE_DIR, job_id, "state.json"), "w") as f:
        json.dump(state, f)

def load_state(job_id):
    path = os.path.join(BASE_DIR, job_id, "state.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None

def clean_job(job_id):
    shutil.rmtree(os.path.join(BASE_DIR, job_id), ignore_errors=True)

def estimate_minutes(text):
    return len(text.split()) / WORDS_PER_MINUTE

# ---------------- STORY WORKER ----------------

def generate_indian_story_job(job_id, generate_hindi_audio):

    job_path = os.path.join(BASE_DIR, job_id)
    state = load_state(job_id)

    state["story_status"] = "running"
    state["story_started_at"] = time.time()
    save_state(job_id, state)

    try:
        original_text = state["text"]

        prompt = f"""
Rewrite this story in Indian cultural context.
Generate a proper Indian title.

Return format:
TITLE: <title>
STORY:
<full rewritten story>

Original:
{original_text[:12000]}
"""

        response = client.chat.completions.create(
            model=TEXT_MODEL,
            messages=[
                {"role": "system", "content": "You are an expert Indian novelist."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
        )

        content = response.choices[0].message.content

        title_line = content.split("\n")[0]
        title = title_line.replace("TITLE:", "").strip()
        story_text = content.split("STORY:", 1)[-1].strip()

        safe_title = "".join(c for c in title if c.isalnum() or c in " _-")
        state["story_title"] = safe_title

        story_file = os.path.join(job_path, f"{safe_title}.txt")
        with open(story_file, "w", encoding="utf-8") as f:
            f.write(story_text)

        state["story_status"] = "completed"
        state["story_completed_at"] = time.time()

        # ---- Optional Hindi Version ----
        if generate_hindi_audio:

            state["hindi_status"] = "translating"
            save_state(job_id, state)

            translate_prompt = f"Translate this story into natural Hindi:\n\n{story_text}"

            response_hi = client.chat.completions.create(
                model=TEXT_MODEL,
                messages=[{"role": "user", "content": translate_prompt}],
            )

            hindi_story = response_hi.choices[0].message.content

            state["hindi_status"] = "generating_audio"
            save_state(job_id, state)

            generate_audio_from_text(
                job_id,
                hindi_story,
                base_name=f"{safe_title}_HINDI",
                state_key="hindi_completed_files"
            )

            state["hindi_status"] = "completed"

    except Exception as e:
        state["story_status"] = "failed"
        state["story_error"] = str(e)

    save_state(job_id, state)

# ---------------- AUDIO FUNCTION ----------------

def generate_audio_from_text(job_id, text, base_name, state_key):

    job_path = os.path.join(BASE_DIR, job_id)
    state = load_state(job_id)

    words = text.split()
    words_per_file = WORDS_PER_MINUTE * MAX_MINUTES_PER_FILE

    file_chunks = [
        " ".join(words[i:i + words_per_file])
        for i in range(0, len(words), words_per_file)
    ]

    state.setdefault(state_key, 0)
    save_state(job_id, state)

    for file_index in range(state[state_key], len(file_chunks)):

        chunk = file_chunks[file_index]
        api_chunks = [chunk[i:i + 4000] for i in range(0, len(chunk), 4000)]

        final_audio = b""

        for part in api_chunks:
            response = client.audio.speech.create(
                model=MODEL_NAME,
                voice=VOICE,
                input=part
            )
            final_audio += response.content

        file_name = f"{base_name}_part_{file_index+1}.mp3"
        file_path = os.path.join(job_path, file_name)

        with open(file_path, "wb") as f:
            f.write(final_audio)

        state[state_key] += 1
        save_state(job_id, state)

# ---------------- MAIN AUDIO WORKER ----------------

def generate_audio_job(job_id):

    state = load_state(job_id)
    state["status"] = "running"
    save_state(job_id, state)

    generate_audio_from_text(
        job_id,
        state["text"],
        base_name="Original_Audio",
        state_key="completed_files"
    )

    state["status"] = "completed"
    save_state(job_id, state)

# ---------------- UI ----------------

st.title("Advanced Audiobook Generator")

menu = st.sidebar.radio("Menu", ["Create Job", "View Jobs", "Clean Jobs"])

# ---------------- CREATE JOB ----------------

if menu == "Create Job":

    text_content = st.text_area("Paste Text", height=250)
    generate_hindi = st.checkbox("Generate Hindi Audiobook Version")

    if text_content.strip():

        st.write(f"Estimated Duration: {estimate_minutes(text_content):.1f} min")

        if st.button("Start Background Job"):

            job_id = str(uuid.uuid4())
            job_path = os.path.join(BASE_DIR, job_id)
            os.makedirs(job_path, exist_ok=True)

            state = {
                "job_id": job_id,
                "text": text_content,
                "status": "queued",
                "completed_files": 0,
                "story_status": "queued",
                "hindi_status": "not_requested"
            }

            if generate_hindi:
                state["hindi_status"] = "queued"

            save_state(job_id, state)

            threading.Thread(
                target=generate_audio_job,
                args=(job_id,),
                daemon=True
            ).start()

            threading.Thread(
                target=generate_indian_story_job,
                args=(job_id, generate_hindi),
                daemon=True
            ).start()

            st.success(f"Job started: {job_id}")

# ---------------- VIEW JOBS ----------------

if menu == "View Jobs":

    jobs = os.listdir(BASE_DIR)

    for job_id in jobs:

        state = load_state(job_id)
        if not state:
            continue

        st.markdown("---")
        st.markdown(f"### Job: {job_id}")

        st.write(f"Audio Status: {state['status']}")
        st.write(f"Story Status: {state['story_status']}")
        st.write(f"Hindi Status: {state.get('hindi_status')}")

        # ---- Live Story Elapsed Time ----
        if state.get("story_status") == "running":
            started = state.get("story_started_at")
            if started:
                elapsed = (time.time() - started) / 60
                st.info(f"Story generation running for {elapsed:.1f} minutes")

        job_path = os.path.join(BASE_DIR, job_id)

        for file in os.listdir(job_path):
            if file.endswith(".mp3") or file.endswith(".txt"):
                with open(os.path.join(job_path, file), "rb") as f:
                    st.download_button(
                        label=f"Download {file}",
                        data=f,
                        file_name=file,
                        key=f"{job_id}_{file}"
                    )

# ---------------- CLEAN JOBS ----------------

if menu == "Clean Jobs":

    jobs = os.listdir(BASE_DIR)

    if jobs:
        selected = st.selectbox("Select job", jobs)

        if st.button("Delete Selected"):
            clean_job(selected)
            st.success("Deleted.")
            st.rerun()

        if st.button("Delete ALL"):
            for j in jobs:
                clean_job(j)
            st.success("All deleted.")
            st.rerun()
    else:
        st.info("No jobs to delete.")
