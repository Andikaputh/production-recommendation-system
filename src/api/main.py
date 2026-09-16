import random

@app.get("/items/universe")
def get_latent_universe():
    """
    Mengekspos 500 data film beserta koordinat SVD-nya ke Frontend Vite.
    Ini adalah bahan bakar utama untuk visualisasi 'Latent Galaxy'.
    """
    # Daftar genre untuk simulasi pengelompokan SVD
    genres = ["Action", "Sci-Fi", "Romance", "Comedy", "Drama", "Animation", "Thriller", "Adventure"]
    
    universe_data = []
    
    # Kita hasilkan 500 titik data masif
    for i in range(1, 501):
        genre = random.choice(genres)
        
        # ---------------------------------------------------------
        # THE SVD SIMULATION (Ruang Laten)
        # Di dunia nyata, nilai x dan y ini diambil langsung dari:
        # x = model.components_[0, i]
        # y = model.components_[1, i]
        # Di sini kita simulasikan pengelompokan (clustering) agar 
        # visualisasinya terlihat logis (genre sejenis saling berdekatan).
        # ---------------------------------------------------------
        if genre in ["Action", "Adventure", "Thriller"]:
            x, y = random.uniform(1.0, 5.0), random.uniform(-5.0, -1.0)
        elif genre in ["Sci-Fi", "Animation"]:
            x, y = random.uniform(1.0, 6.0), random.uniform(1.0, 6.0)
        else: # Romance, Comedy, Drama
            x, y = random.uniform(-5.0, 0.0), random.uniform(-3.0, 4.0)
            
        universe_data.append({
            "id": i,
            "title": f"Movie Title #{i}", 
            "genre": genre,
            # Menghasilkan poster gambar secara otomatis
            "image": f"https://dummyimage.com/300x450/1e1e2f/60a5fa.png&text={genre}+{i}",
            "x": round(x, 3),
            "y": round(y, 3)
        })
        
    return {
        "status": "success",
        "total_items": len(universe_data),
        "universe": universe_data
    }