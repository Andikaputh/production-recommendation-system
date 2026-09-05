# 1. Gunakan OS Linux ringan yang sudah terinstal Python
FROM python:3.10-slim

# 2. Tentukan folder kerja di dalam sistem Docker
WORKDIR /app

# 3. Pindahkan file requirements.txt dan instal library
COPY requirements.txt .
RUN pip install --default-timeout=1000 --no-cache-dir -r requirements.txt

# 4. Pindahkan folder src (berisi kode API) dan data (berisi database SQLite)
COPY src/ src/
COPY data/ data/

# 5. Buka port 8000 agar bisa diakses dari luar Docker
EXPOSE 8000

# 6. Perintah wajib yang dijalankan saat Docker dihidupkan
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
