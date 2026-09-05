import json
import requests
import urllib3
import streamlit as st
import google.generativeai as genai
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
def get_formatted_date():
    day_map = {"Monday": "Senin", "Tuesday": "Selasa", "Wednesday": "Rabu", "Thursday": "Kamis", "Friday": "Jumat", "Saturday": "Sabtu", "Sunday": "Minggu"}
    month_map = {"January": "Januari", "February": "Februari", "March": "Maret", "April": "April", "May": "Mei", "June": "Juni", "July": "Juli", "August": "Agustus", "September": "September", "October": "Oktober", "November": "November", "December": "Desember"}
    now = datetime.now()
    day = day_map.get(now.strftime("%A"), now.strftime("%A"))
    month = month_map.get(now.strftime("%B"), now.strftime("%B"))
    return f"{day}, {now.strftime('%d')} {month} {now.strftime('%Y')}"
today = get_formatted_date()
st.set_page_config(page_title="Chatbot RSA UGM", page_icon="🏥", layout="centered")
st.title("🏥 Chatbot Informasi Jadwal Dokter RSA UGM")
st.caption(f"📅 Data Jadwal Berdasarkan Hari Ini: **{today}**")

#Konfigurasi API Key Gemini
api_key = None
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]

with st.sidebar:
    st.header("Konfigurasi GEMINI API KEY")
    if not api_key:
        api_key = st.text_input("Masukkan Gemini API Key:", type="password")
        if not api_key:
            st.warning("Silakan masukkan API Key Gemini untuk mulai bertanya.")

if api_key:
    genai.configure(api_key=api_key)

#Get data dari API
@st.cache_data(ttl=3600)
def fetch_jadwal_from_api():
    today_date = datetime.now().strftime("%Y-%m-%d")
    url = f"https://info.rsa.ugm.ac.id/jadwaldr/api/index.php?date={today_date}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, verify=False, timeout=10)
        if response.status_code == 200:
            data_res = response.json()
            schedules = data_res.get("schedules", {})
            
            data_jadwal = []
            for klinik_name, dokter_list in schedules.items():
                for item in dokter_list:
                    dokter_nm = item.get("employee_nm") or item.get("location_nm") or "-"
                    jam_start = item.get("start_time", "")
                    jam_stop = item.get("stop_time", "")
                    jam_praktik = f"{jam_start} - {jam_stop}" if jam_start and jam_stop else "-"
                    no_schedule = item.get("no_schedule", 0)
                    
                    data_jadwal.append({
                        "spesialis_klinik": klinik_name,
                        "nama_dokter": dokter_nm,
                        "lokasi_klinik": item.get("location_nm", "-"),
                        "jam_praktik": jam_praktik,
                        "status": "Tidak Praktik" if no_schedule == 1 else "Praktik"
                    })
            return data_jadwal
    except Exception as e:
        st.error(f"Gagal terhubung ke API RSA UGM: {e}")
        
    return []

#Load data dari API
jadwal_data = fetch_jadwal_from_api()

#Status Data di Sidebar
# Status Data di Sidebar
with st.sidebar:
    st.header("Status Data API")
    st.info(f"Date: {today}")
    if jadwal_data:
        st.success(f"Berhasil menarik **{len(jadwal_data)}** data jadwal dari API RSA UGM.")
    else:
        st.warning("Data API tidak ditemukan atau sedang tidak tersedia.")

#Chat History & Opening
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Halo! Saya asisten virtual RSA UGM. Ada yang bisa saya bantu terkait jadwal dokter atau klinik hari ini?"
        }
    ]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Prompt
if prompt := st.chat_input("Tanyakan jadwal dokter (contoh: Dokter anak praktik jam berapa?)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    prompt_clean = prompt.strip().lower()

    simple_greetings = {"halo", "hai", "hi", "pagi", "siang", "sore", "malam", "ping", "assalamualaikum", "p"}
    prompt_words = prompt_clean.split()
    is_pure_greeting = prompt_clean in simple_greetings or (
        len(prompt_words) <= 2 and all(w in simple_greetings for w in prompt_words)
    )

    if is_pure_greeting:
        reply = "Halo! Silakan tanyakan jadwal dokter atau spesialisasi yang Anda butuhkan."
        with st.chat_message("assistant"):
            st.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})

    else:
        system_instruction = f"""
        Kamu adalah asisten virtual RSA UGM yang ramah dan sigap. Jawab pertanyaan jadwal dokter tanggal {today} berdasarkan data jadwal dokter berikut.

        Aturan:
        1. Berikan jawaban secara langsung dan ramah tanpa perkenalan ulang di awal.
        2. Cocokkan kata kunci dan sinonim secara fleksibel (contoh: jiwa = Kejiwaan, obgyn = Kebidanan/Obsgin, orto = Ortopedi).
        3. Filter berdasarkan jam praktik jika pertanyaan menyebutkan waktu (pagi/siang/sore/malam).
        4. Tampilkan nama klinik, nama dokter, jam praktik, dan status dalam bullet point rapi.
        5. Jika jadwal yang dicari tidak ada, sampaikan dengan santun bahwa jadwal tersebut tidak tersedia untuk hari ini, tanpa menampilkan spesialis lain yang tidak ditanyakan.

        Data jadwal dokter RSA UGM:
        {json.dumps(jadwal_data, ensure_ascii=False)}
        """

        models_to_try = [
            "gemini-3.1-flash-lite",  
            "gemini-2.5-flash"
        ]

        response_text = None
        with st.spinner("Processing..."):
            for model_name in models_to_try:
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(f"{system_instruction}\n\nPertanyaan Pengguna: {prompt}")
                    response_text = response.text
                    break
                except Exception as e:
                    if "429" in str(e) or "ResourceExhausted" in str(e):
                        continue
                    else:
                        st.error(f"Terjadi kesalahan pada model {model_name}: {e}")
                        break

        if response_text:
            with st.chat_message("assistant"):
                st.markdown(response_text)
            st.session_state.messages.append({"role": "assistant", "content": response_text})