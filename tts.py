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

MODEL_TTS = "gpt-4o-mini-tts"
MODEL_TEXT = "gpt-4o-mini"
VOICE = "alloy"

WORDS_PER_MINUTE = 160
MAX_MINUTES_PER_FILE = 25
COST_PER_1K_CHARS = 0.015

BASE_DIR = "jobs"
os.makedirs(BASE_DIR, exist_ok=True)

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

STUCK_TIMEOUT = 120
MAX_RETRIES = 3

# ---------------- STATE SAFETY ----------------

def normalize_state(state):
    state.setdefault("status", "unknown")
    state.setdefault("completed_files", 0)
    state.setdefault("total_files", 0)

    state.setdefault("story_status", "not_started")
    state.setdefault("story_progress", 0)
    state.setdefault("story_started_at", None)
    state.setdefault("story_last_heartbeat", None)
    state.setdefault("story_completed_at", None)
    state.setdefault("story_error", None)
    state.setdefault("story_retry_count", 0)
    state.setdefault("story_title", "Indian_Story")

    return state


def save_state(job_id, state):
    with open(os.path.join(BASE_DIR, job_id, "state.json"), "w") as f:
        json.dump(state, f)


def load_state(job_id):
    path = os.path.join(BASE_DIR, job_id, "state.json")
    if os.path.exists(path):
        with open(path) as f:
            state = json.load(f)
        return normalize_state(state)
    return None


def clean_job(job_id):
    shutil.rmtree(os.path.join(BASE_DIR, job_id), ignore_errors=True)


# ---------------- ESTIMATION ----------------

def estimate_stats(text):
    char_count = len(text)
    word_count = len(text.split())
    minutes = word_count / WORDS_PER_MINUTE
    files = math.ceil(minutes / MAX_MINUTES_PER_FILE)
    cost = (char_count / 1000) * COST_PER_1K_CHARS
    return word_count, minutes, files, cost


# ---------------- AUDIO WORKER ----------------

def generate_audio_job(job_id):

    state = load_state(job_id)
    state["status"] = "running"
    save_state(job_id, state)

    job_path = os.path.join(BASE_DIR, job_id)
    text = state["text"]

    words = text.split()
    words_per_file = WORDS_PER_MINUTE * MAX_MINUTES_PER_FILE

    chunks = [
        " ".join(words[i:i + words_per_file])
        for i in range(0, len(words), words_per_file)
    ]

    state["total_files"] = len(chunks)
    save_state(job_id, state)

    for i in range(state["completed_files"], len(chunks)):

        part_text = chunks[i]
        api_chunks = [part_text[j:j+4000] for j in range(0, len(part_text), 4000)]

        final_audio = b""

        for piece in api_chunks:
            response = client.audio.speech.create(
                model=MODEL_TTS,
                voice=VOICE,
                input=piece
            )
            final_audio += response.content

        filename = f"Original_part_{i+1}.mp3"
        with open(os.path.join(job_path, filename), "wb") as f:
            f.write(final_audio)

        state["completed_files"] += 1
        save_state(job_id, state)

    state["status"] = "completed"
    save_state(job_id, state)


# ---------------- STORY WORKER ----------------

def generate_story_job(job_id):

    state = load_state(job_id)

    if state["story_retry_count"] >= MAX_RETRIES:
        return

    try:
        state["story_status"] = "generating"
        state["story_started_at"] = time.time()
        state["story_last_heartbeat"] = time.time()
        state["story_progress"] = 5
        save_state(job_id, state)

        original_text = state["text"]

        prompt = f"""
Rewrite this story in Indian cultural context.
Keep similar emotional arc and structure.
Generate an Indian title.

Return format:
TITLE: <title>
STORY:
<full story>

Original:
{original_text[:12000]}
"""

        response = client.chat.completions.create(
            model=MODEL_TEXT,
            messages=[
                {"role": "system", "content": "You are a skilled Indian novelist."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
        )

        state["story_progress"] = 80
        state["story_last_heartbeat"] = time.time()
        save_state(job_id, state)

        content = response.choices[0].message.content

        title = content.split("\n")[0].replace("TITLE:", "").strip()
        story_text = content.split("STORY:", 1)[-1].strip()

        safe_title = "".join(c for c in title if c.isalnum() or c in " _-")
        state["story_title"] = safe_title

        job_path = os.path.join(BASE_DIR, job_id)
        with open(os.path.join(job_path, f"{safe_title}.txt"), "w", encoding="utf-8") as f:
            f.write(story_text)

        state["story_progress"] = 100
        state["story_status"] = "completed"
        state["story_completed_at"] = time.time()
        save_state(job_id, state)

    except Exception as e:
        state["story_retry_count"] += 1
        state["story_error"] = str(e)
        state["story_status"] = "retrying"
        save_state(job_id, state)

        time.sleep(3)
        generate_story_job(job_id)


# ---------------- UI ----------------

st.title("Persistent Audiobook + Indian Story Generator")

menu = st.sidebar.radio("Menu", ["Create Job", "View Jobs", "Clean Jobs"])


# ---------------- CREATE JOB ----------------

if menu == "Create Job":

    input_type = st.radio("Input Type", ["Paste Text", "Enter URL"])
    text_content = ""

    if input_type == "Paste Text":
        text_content = st.text_area("Paste text", height=250)

    else:
        url = st.text_input("Enter URL")
        if url:
            try:
                response = requests.get(url, timeout=10)
                soup = BeautifulSoup(response.text, "html.parser")
                for tag in soup(["script", "style"]):
                    tag.extract()
                text_content = soup.get_text(separator=" ", strip=True)
                st.success("Text extracted.")
            except Exception as e:
                st.error(f"URL Error: {e}")

    if text_content.strip():

        words, minutes, files, cost = estimate_stats(text_content)

        st.markdown("### Estimate")
        st.write(f"Words: {words:,}")
        st.write(f"Estimated Duration: {minutes:.1f} min")
        st.write(f"Estimated Files: {files}")
        st.write(f"Estimated Audio Cost: ${cost:.4f}")

        if st.button("Confirm & Start"):

            job_id = str(uuid.uuid4())
            os.makedirs(os.path.join(BASE_DIR, job_id), exist_ok=True)

            state = {
                "job_id": job_id,
                "text": text_content,
                "status": "queued",
                "completed_files": 0,
                "story_status": "queued"
            }

            save_state(job_id, state)

            threading.Thread(target=generate_audio_job, args=(job_id,), daemon=True).start()
            threading.Thread(target=generate_story_job, args=(job_id,), daemon=True).start()

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

        # ---- Stuck Detection ----
        if state["story_status"] == "generating":
            last = state.get("story_last_heartbeat")
            if last and time.time() - last > STUCK_TIMEOUT:
                state["story_status"] = "stuck"
                save_state(job_id, state)

        st.write(f"Audio Status: {state.get('status')}")
        st.write(f"Story Status: {state.get('story_status')}")

        st.progress(state.get("story_progress", 0) / 100)

        if state["story_status"] == "generating":
            started = state.get("story_started_at")
            if started:
                elapsed = (time.time() - started) / 60
                remaining = max((elapsed / max(state["story_progress"],1)) * (100 - state["story_progress"]), 0)
                st.info(f"Elapsed: {elapsed:.1f} min | Est. Remaining: {remaining:.1f} min")

        if state["story_status"] == "retrying":
            st.warning(f"Retrying... Attempt {state['story_retry_count']}")

        if state["story_status"] == "failed":
            st.error(state.get("story_error"))

        job_path = os.path.join(BASE_DIR, job_id)

        for file in os.listdir(job_path):
            if file.endswith(".mp3") or file.endswith(".txt"):
                with open(os.path.join(job_path, file), "rb") as f:
                    st.download_button(
                        f"Download {file}",
                        data=f,
                        file_name=file,
                        key=f"{job_id}_{file}"
                    )


# ---------------- CLEAN JOBS ----------------

if menu == "Clean Jobs":

    jobs = os.listdir(BASE_DIR)

    if jobs:
        selected = st.selectbox("Select Job", jobs)

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
        st.info("No jobs available.")
