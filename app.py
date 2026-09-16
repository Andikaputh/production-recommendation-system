import streamlit as st
import requests

st.set_page_config(page_title="AI Recommender - Ultimate", page_icon="🛍️", layout="wide")

# State Management
if 'halaman' not in st.session_state:
    st.session_state.halaman = 'beranda'
if 'item_terpilih' not in st.session_state:
    st.session_state.item_terpilih = None

API_URL = "http://127.0.0.1:8000"

katalog_item = {
    1: {"nama": "Toy Story (1995)", "kategori": "Animation", "gambar": "https://dummyimage.com/200x300/ff7f7f/333333.png&text=Toy+Story", "deskripsi": "Kisah petualangan mainan koboi dan astronot."},
    4: {"nama": "Get Shorty (1995)", "kategori": "Comedy", "gambar": "https://dummyimage.com/200x300/7fbfff/333333.png&text=Get+Shorty", "deskripsi": "Seorang penagih utang mafia pergi ke Hollywood."},
    7: {"nama": "Twelve Monkeys (1995)", "kategori": "Sci-Fi", "gambar": "https://dummyimage.com/200x300/7fff7f/333333.png&text=12+Monkeys", "deskripsi": "Penjelajah waktu dari masa depan pasca-apokaliptik."},
    8: {"nama": "Babe (1995)", "kategori": "Children", "gambar": "https://dummyimage.com/200x300/ffff7f/333333.png&text=Babe", "deskripsi": "Seekor babi kecil yang belajar menjadi anjing gembala."},
    9: {"nama": "Dead Man Walking", "kategori": "Drama", "gambar": "https://dummyimage.com/200x300/bf7fff/333333.png&text=Dead+Man", "deskripsi": "Kisah nyata pendampingan terpidana mati."}
}

def ke_detail(item_id):
    st.session_state.item_terpilih = item_id
    st.session_state.halaman = 'detail'

def ke_beranda():
    st.session_state.halaman = 'beranda'
    st.session_state.item_terpilih = None

def kirim_feedback(user_id, item_id, rating):
    try:
        payload = {"user_id": user_id, "item_id": item_id, "rating": rating}
        res = requests.post(f"{API_URL}/feedback", json=payload)
        if res.status_code == 200:
            st.toast(f"✅ Interaksi terekam ke Database sebagai bahan belajar AI!")
        else:
            st.error("Gagal merekam interaksi.")
    except Exception as e:
        st.error(f"Koneksi API terputus: {e}")

user_id_aktif = st.sidebar.number_input("Login sebagai User ID:", min_value=1, value=123)
st.sidebar.info("💡 Interaksi Anda (Klik Detail / Suka) akan direkam oleh sistem.")

# ==========================================
# HALAMAN 1: BERANDA
# ==========================================
if st.session_state.halaman == 'beranda':
    st.title("🛍️ AI Personalized Recommender")
    st.markdown("Etalase dinamis terintegrasi dengan *Machine Learning Feedback Loop*.")
    
    if st.button("Muat Rekomendasi 🚀"):
        with st.spinner("Menarik data dari API lokal..."):
            try:
                response = requests.get(f"{API_URL}/recommendations/{user_id_aktif}")
                if response.status_code == 200:
                    data = response.json()
                    rekomendasi = data.get("recommendations", [])
                    
                    cols = st.columns(len(rekomendasi))
                    for idx, item in enumerate(rekomendasi):
                        item_id = item["item_id"]
                        info = katalog_item.get(item_id, {"nama": f"Produk #{item_id}", "kategori": "Lainnya", "gambar": f"https://dummyimage.com/200x300/cccccc/000000.png&text=Produk+{item_id}"})
                        
                        with cols[idx]:
                            st.image(info["gambar"], use_container_width=True)
                            st.write(f"**{info['nama']}**")
                            st.button("Lihat Detail", key=f"btn_{item_id}", on_click=ke_detail, args=(item_id,))
                            
                            # Tombol Feedback Cepat
                            if st.button("Suka 👍", key=f"suka_{item_id}"):
                                kirim_feedback(user_id_aktif, item_id, 5.0)
                else:
                    st.error("Gagal terhubung ke API lokal. Pastikan Uvicorn menyala di folder src/api.")
            except Exception as e:
                st.error(f"Error: {e}")

# ==========================================
# HALAMAN 2: DETAIL PRODUK
# ==========================================
elif st.session_state.halaman == 'detail':
    item_id = st.session_state.item_terpilih
    info = katalog_item.get(item_id, {"nama": f"Produk #{item_id}", "kategori": "Lainnya", "gambar": f"https://dummyimage.com/200x300/cccccc/000000.png&text=Produk+{item_id}", "deskripsi": "-"})
    
    st.button("⬅️ Kembali ke Etalase", on_click=ke_beranda)
    st.markdown("---")
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.image(info["gambar"], use_container_width=True)
    with col2:
        st.header(info["nama"])
        st.caption(f"🏷️ Kategori: {info['kategori']}")
        st.write(info["deskripsi"])
        
        # Tombol Feedback di Halaman Detail
        st.write("Apakah Anda menyukai rekomendasi ini?")
        if st.button("⭐ Tambahkan ke Favorit"):
            kirim_feedback(user_id_aktif, item_id, 5.0)
    
    st.markdown("---")
    st.subheader("Anda Mungkin Juga Suka...")
    cols = st.columns(4)
    simulasi_serupa = [k for k in katalog_item.keys() if k != item_id][:4]
    for idx, s_id in enumerate(simulasi_serupa):
        s_info = katalog_item[s_id]
        with cols[idx]:
            st.image(s_info["gambar"], use_container_width=True)
            st.write(f"**{s_info['nama']}**")