from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, Column, Integer, Float
from sqlalchemy.orm import declarative_base, sessionmaker
import os

app = FastAPI(title="Production Recommendation API")

# 1. Setup Koneksi Database (Sama seperti di Notebook)
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data/recommendations.db'))
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. Skema Tabel (Harus sama persis dengan yang dibuat di Notebook)
class PopularItem(Base):
    __tablename__ = 'popular_items'
    id = Column(Integer, primary_key=True, autoincrement=True)
    item_id = Column(Integer, unique=True, index=True)
    score = Column(Float)

@app.get("/")
def root():
    return {"message": "API is running with Database Serving!"}

@app.get("/recommendations/{user_id}")
def get_recommendations(user_id: int, top_k: int = 5):
    """
    Endpoint ini sekarang membaca dari Database SQL, bukan dari file CSV di RAM.
    """
    session = SessionLocal()
    try:
        # Mengambil data dari database dengan query SQL (diurutkan berdasarkan skor tertinggi)
        results = session.query(PopularItem).order_by(PopularItem.score.desc()).limit(top_k).all()
        
        if not results:
            raise HTTPException(status_code=404, detail="Data rekomendasi tidak ditemukan")
        
        recommendations = []
        for row in results:
            recommendations.append({
                "item_id": row.item_id,
                "score": row.score
            })
            
        return {
            "user_id": user_id,
            "recommendation_type": "popularity_from_db",
            "recommendations": recommendations
        }
    finally:
        session.close() # Wajib menutup sesi database agar memori tidak bocor