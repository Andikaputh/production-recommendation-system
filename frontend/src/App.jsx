import { useState, useEffect } from 'react'
import Plot from 'react-plotly.js'

// 1. Data Mockup (Diperbanyak)
const POPULAR_MOVIES = [
  { id: 1, title: "Toy Story", genre: "Animation" },
  { id: 2, title: "Jumanji", genre: "Adventure" },
  { id: 3, title: "Heat", genre: "Action" },
  { id: 4, title: "Sabrina", genre: "Romance" },
  { id: 5, title: "GoldenEye", genre: "Action" },
  { id: 6, title: "Babe", genre: "Children" }
];

const LATENT_UNIVERSE = [
  { id: 101, title: "The Matrix", x: 2.5, y: 3.1, type: "Sci-Fi" },
  { id: 102, title: "Inception", x: 2.2, y: 2.8, type: "Sci-Fi" },
  { id: 103, title: "Die Hard", x: 3.0, y: -1.5, type: "Action" },
  { id: 104, title: "Lethal Weapon", x: 2.8, y: -1.2, type: "Action" },
  { id: 105, title: "Titanic", x: -2.0, y: 1.5, type: "Romance" },
  { id: 106, title: "The Notebook", x: -2.5, y: 1.8, type: "Romance" },
  { id: 1, title: "Toy Story", x: 0.5, y: 4.0, type: "Animation" },
  { id: 3, title: "Heat", x: 2.9, y: -1.0, type: "Action" },
];

function App() {
  const [selectedMovies, setSelectedMovies] = useState([]);
  const [activeScreen, setActiveScreen] = useState('cold-start');
  
  // State untuk mengontrol sequence animasi
  const [simStep, setSimStep] = useState(0); 
  const [userCoords, setUserCoords] = useState({ x: 0, y: 0 });

  const toggleSelection = (id) => {
    if (selectedMovies.includes(id)) setSelectedMovies(selectedMovies.filter(m => m !== id));
    else if (selectedMovies.length < 3) setSelectedMovies([...selectedMovies, id]);
  };

  const processAI = () => {
    setActiveScreen('latent-space');
    
    // Hitung Titik "YOU" (Centroid dari film yang dipilih)
    // Ini menyimulasikan algoritma Folding-In SVD
    const selectedData = LATENT_UNIVERSE.filter(m => selectedMovies.includes(m.id));
    let avgX = 0, avgY = 0;
    if (selectedData.length > 0) {
      avgX = selectedData.reduce((sum, m) => sum + m.x, 0) / selectedData.length;
      avgY = selectedData.reduce((sum, m) => sum + m.y, 0) / selectedData.length;
    }
    setUserCoords({ x: avgX, y: avgY });

    // Jalankan urutan animasi
    setSimStep(1); // Tampilkan semesta dasar
    setTimeout(() => setSimStep(2), 2000); // Munculkan titik "YOU"
    setTimeout(() => setSimStep(3), 4500); // Tarik garis rekomendasi
  };

  // --- LAYAR 1: COLD START ---
  if (activeScreen === 'cold-start') {
    return (
      <div className="min-h-screen bg-gray-950 text-white flex flex-col items-center justify-center p-8">
        <h1 className="text-5xl font-bold text-blue-400 mb-8">Step 1: AI Calibration</h1>
        <p className="text-xl mb-8">Pilih maksimal 3 film agar AI bisa memetakan selera Anda.</p>
        
        <div className="flex flex-wrap justify-center gap-4 mb-12 max-w-3xl">
          {POPULAR_MOVIES.map(movie => (
            <div 
              key={movie.id} 
              onClick={() => toggleSelection(movie.id)}
              className={`p-6 w-40 border-2 rounded-xl cursor-pointer transition-all ${
                selectedMovies.includes(movie.id) ? 'border-blue-500 bg-blue-900/30 transform -translate-y-2' : 'border-gray-700 hover:border-gray-500'
              }`}
            >
              <h3 className="font-bold text-md">{movie.title}</h3>
              <p className="text-gray-400 text-sm">{movie.genre}</p>
            </div>
          ))}
        </div>

        {selectedMovies.length > 0 && (
          <button onClick={processAI} className="bg-blue-600 px-8 py-3 rounded-full text-xl font-bold hover:bg-blue-500 transition-all shadow-lg shadow-blue-500/50">
            Learn My Pattern 🚀
          </button>
        )}
      </div>
    );
  }

  // --- LAYAR 2: LATENT SPACE ANIMATION ---
  
  // Data Grafik 1: Semua Film
  const traceMovies = {
    x: LATENT_UNIVERSE.map(m => m.x),
    y: LATENT_UNIVERSE.map(m => m.y),
    text: LATENT_UNIVERSE.map(m => m.title),
    mode: 'markers+text',
    textposition: 'top center',
    marker: {
      size: LATENT_UNIVERSE.map(m => selectedMovies.includes(m.id) ? 15 : 8),
      color: LATENT_UNIVERSE.map(m => selectedMovies.includes(m.id) ? '#3b82f6' : '#4b5563'),
    },
    name: 'Movies',
    hoverinfo: 'text'
  };

  // Data Grafik 2: Titik Pengguna (Muncul di Step 2)
  const traceUser = {
    x: [userCoords.x],
    y: [userCoords.y],
    text: ['<b>YOU</b>'],
    mode: 'markers+text',
    textposition: 'bottom center',
    textfont: { size: 16, color: '#fbbf24' },
    marker: { size: 25, color: '#fbbf24', symbol: 'star' },
    name: 'Your Profile'
  };

  // Data Grafik 3: Garis Rekomendasi (Muncul di Step 3)
  // Menyimulasikan jarak terdekat (Nearest Neighbors)
  const traceLines = {
    x: [userCoords.x, 3.0, null, userCoords.x, 2.8], // Menarik garis dari YOU ke Die Hard & Lethal Weapon
    y: [userCoords.y, -1.5, null, userCoords.y, -1.2],
    mode: 'lines',
    line: { color: '#10b981', width: 2, dash: 'dot' },
    name: 'AI Recommendations'
  };

  const plotData = [traceMovies];
  if (simStep >= 2) plotData.push(traceUser);
  if (simStep >= 3) plotData.push(traceLines);

  return (
    <div className="min-h-screen bg-gray-950 text-white flex flex-col items-center p-8">
      <h1 className="text-4xl font-bold text-purple-400 mb-2">Step 2: AI Representation</h1>
      
      {/* NARRATIVE EDUKASI DINAMIS */}
      <div className="h-16 mb-4 flex items-center justify-center">
        {simStep === 1 && <p className="text-xl text-blue-300 animate-pulse">Memetakan alam semesta film (SVD Space)...</p>}
        {simStep === 2 && <p className="text-xl text-yellow-300">Mengubah preferensimu menjadi Vektor Matematika (Titik Emas)...</p>}
        {simStep === 3 && <p className="text-xl text-green-400 font-bold">AI menarik garis ke film terdekat dengan profilmu untuk menghasilkan rekomendasi!</p>}
      </div>
      
      <div className="bg-gray-900 p-2 rounded-2xl border border-gray-800 shadow-2xl">
        <Plot
          data={plotData}
          layout={{
            width: 900,
            height: 500,
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            xaxis: { showgrid: false, zeroline: true, zerolinecolor: '#374151' },
            yaxis: { showgrid: false, zeroline: true, zerolinecolor: '#374151' },
            margin: { t: 40, l: 40, r: 40, b: 40 },
            showlegend: false
          }}
          config={{ displayModeBar: false }}
        />
      </div>
      
      {simStep >= 3 && (
        <div className="mt-8 bg-gray-900 border border-green-500/30 p-6 rounded-xl w-full max-w-2xl text-center shadow-lg shadow-green-900/20">
          <h3 className="text-2xl font-bold text-green-400 mb-2">🎉 Recommendation Generated!</h3>
          <p className="text-gray-300">
            Berdasarkan posisi titik emasmu, SVD merekomendasikan film di sekitar koordinat $X: {userCoords.x.toFixed(2)}$, $Y: {userCoords.y.toFixed(2)}$.
          </p>
          <button onClick={() => {setActiveScreen('cold-start'); setSimStep(0); setSelectedMovies([]);}} className="mt-4 px-6 py-2 bg-gray-700 hover:bg-gray-600 rounded-full font-bold">
            Coba Pola Lain
          </button>
        </div>
      )}
    </div>
  )
}

export default App