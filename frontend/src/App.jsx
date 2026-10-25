import { useEffect, useMemo, useState } from 'react'
import './App.css'

const API_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

const fallbackCategories = [
  ['bag', 'Tas'], ['book', 'Buku'], ['desk', 'Perlengkapan Meja'],
  ['drinkware', 'Botol Minum'], ['electronics', 'Elektronik'],
  ['organizer', 'Organizer'], ['personal_care', 'Perawatan Diri'],
  ['snack', 'Camilan'], ['stationery', 'Alat Tulis'], ['umbrella', 'Payung'],
].map(([category_id, category_name]) => ({ category_id, category_name }))

const fallbackScenarios = [
  {
    scenario_id: 'kuliah-hemat', title: 'Kuliah hemat',
    description: 'Tas, alat tulis, dan botol minum untuk rutinitas kampus.',
    mission: { goal: 'Menyiapkan perlengkapan kuliah harian yang minimalis', required_categories: ['bag', 'stationery', 'drinkware'], optional_categories: ['organizer'], max_budget: 250000, max_merchants: 2 },
    preferences: { style: ['minimalist', 'natural'], colors: ['hitam', 'abu', 'krem'], brands: [], minimum_rating: 4.2 },
  },
  {
    scenario_id: 'kerja-remote', title: 'Meja kerja',
    description: 'Perlengkapan kerja remote yang nyaman dan tetap rapi.',
    mission: { goal: 'Menyiapkan meja kerja remote yang nyaman dan rapi', required_categories: ['desk', 'electronics', 'drinkware'], optional_categories: ['organizer'], max_budget: 750000, max_merchants: 3 },
    preferences: { style: ['minimalist', 'klasik'], colors: ['hitam', 'putih'], brands: [], minimum_rating: 4.3 },
  },
  {
    scenario_id: 'tanpa-solusi', title: 'Uji batasan',
    description: 'Anggaran sengaja terlalu kecil untuk melihat saran sistem.',
    mission: { goal: 'Membeli power bank dengan anggaran sangat terbatas', required_categories: ['electronics'], optional_categories: [], max_budget: 25000, max_merchants: 1 },
    preferences: { style: [], colors: [], brands: [], minimum_rating: 4.5 },
  },
]

const demoCatalog = {
  bag: ['Tas Tote Cendana', 173000, 'Cendana Gift'],
  stationery: ['Buku Catatan Bumi', 12000, 'Cendana Gift'],
  drinkware: ['Botol Sagara', 30000, 'Karsa Teknologi'],
  organizer: ['Pengatur Kabel Lentera', 16500, 'Karsa Teknologi'],
  desk: ['Lampu Meja Nusa', 185000, 'Karsa Teknologi'],
  electronics: ['Power Bank Volta', 289000, 'Karsa Teknologi'],
  book: ['Planner Aksara', 68000, 'Cendana Gift'],
  personal_care: ['Pouch Higienis Aruna', 39000, 'Cendana Gift'],
  snack: ['Granola Bumi', 27000, 'Karsa Teknologi'],
  umbrella: ['Payung Lipat Nusa', 82000, 'Cendana Gift'],
}

function rupiah(value) {
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(Number(value || 0))
}

function sessionId() {
  const saved = sessionStorage.getItem('rasa-session')
  if (saved) return saved
  const id = `demo-${crypto.randomUUID().slice(0, 12)}`
  sessionStorage.setItem('rasa-session', id)
  return id
}

function staticFallback(mission, categories) {
  const chosen = mission.required_categories.map((category) => {
    const [name, price, merchant] = demoCatalog[category] || [`Produk demo ${category}`, 75000, 'Toko Demo']
    const categoryName = categories.find((item) => item.category_id === category)?.category_name || category
    return {
      product_id: `fallback-${category}`, product_name: name, category_id: category,
      category_name: categoryName, price, merchant_name: merchant, merchant_id: `fallback-${merchant}`,
      rating: 4.6, score: 0, role: 'required', reasons: [],
    }
  })
  const total = chosen.reduce((sum, item) => sum + item.price, 0)
  const merchants = new Set(chosen.map((item) => item.merchant_name)).size
  const feasible = total <= mission.max_budget && merchants <= mission.max_merchants
  return {
    status: feasible ? 'success' : 'infeasible', model_version: 'static-demo-v1',
    strategy: 'static_fallback', mission,
    basket: {
      feasible, status: feasible ? 'feasible' : 'infeasible', items: feasible ? chosen : [],
      total_price: feasible ? total : 0, budget_remaining: feasible ? mission.max_budget - total : mission.max_budget,
      merchant_count: feasible ? merchants : 0, required_category_coverage: feasible ? 1 : 0,
      suggestions: feasible ? [] : [`Anggaran minimum untuk contoh statis ini adalah ${rupiah(total)}. Naikkan anggaran atau longgarkan kategori wajib.`],
    },
    explanations: feasible ? [
      { code: 'fallback_notice', label: 'Contoh tersimpan', detail: 'Kombinasi ini adalah contoh statis saat API tidak dapat dijangkau; bukan hasil inferensi langsung.' },
      { code: 'constraints', label: 'Batasan terpenuhi', detail: `Total berada di bawah anggaran dan menggunakan ${merchants} toko.` },
    ] : [],
    alternatives: { products: {}, baskets: [] }, recommendations: chosen,
    limitations: ['Mode fallback statis aktif. Hasil ini bukan inferensi model langsung.', 'Harga dan stok adalah data simulasi.'],
    meta: { data_mode: 'static_fallback', notice: 'Contoh tersimpan di frontend.' },
  }
}

async function api(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(body?.error?.message || body?.detail?.message || body?.detail || `HTTP ${response.status}`)
  }
  return body
}

function Metric({ label, value, hint }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong>{hint && <small>{hint}</small>}</div>
}

function App() {
  const [view, setView] = useState('demo')
  const [categories, setCategories] = useState(fallbackCategories)
  const [scenarios, setScenarios] = useState(fallbackScenarios)
  const [selectedScenario, setSelectedScenario] = useState('kuliah-hemat')
  const [mission, setMission] = useState(fallbackScenarios[0].mission)
  const [preferences, setPreferences] = useState(fallbackScenarios[0].preferences)
  const [naturalText, setNaturalText] = useState('')
  const [parseResult, setParseResult] = useState(null)
  const [result, setResult] = useState(null)
  const [source, setSource] = useState('idle')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [feedback, setFeedback] = useState({})
  const [analytics, setAnalytics] = useState(null)
  const [benchmark, setBenchmark] = useState(null)
  const [insightDays, setInsightDays] = useState('30')
  const [insightStrategy, setInsightStrategy] = useState('')
  const [insightModel, setInsightModel] = useState('')
  const [apiHealth, setApiHealth] = useState('checking')
  const [compare, setCompare] = useState(false)

  useEffect(() => {
    Promise.allSettled([
      api('/api/v1/catalog/categories'), api('/api/v1/scenarios'), api('/health'),
    ]).then(([categoryResponse, scenarioResponse, healthResponse]) => {
      if (categoryResponse.status === 'fulfilled' && categoryResponse.value.items?.length) setCategories(categoryResponse.value.items)
      if (scenarioResponse.status === 'fulfilled' && scenarioResponse.value.scenarios?.length) setScenarios(scenarioResponse.value.scenarios)
      setApiHealth(healthResponse.status === 'fulfilled' ? healthResponse.value.status : 'offline')
    })
  }, [])

  useEffect(() => {
    if (view !== 'insights') return
    const query = new URLSearchParams({ days: insightDays })
    if (insightStrategy) query.set('strategy', insightStrategy)
    if (insightModel) query.set('model_version', insightModel)
    Promise.allSettled([api(`/api/v1/analytics/summary?${query}`), api('/api/v1/benchmark')])
      .then(([analyticsResponse, benchmarkResponse]) => {
        if (analyticsResponse.status === 'fulfilled') setAnalytics(analyticsResponse.value)
        if (benchmarkResponse.status === 'fulfilled') setBenchmark(benchmarkResponse.value)
      })
  }, [view, insightDays, insightStrategy, insightModel])

  const categoryName = useMemo(() => Object.fromEntries(categories.map((item) => [item.category_id, item.category_name])), [categories])

  function applyScenario(scenario) {
    setSelectedScenario(scenario.scenario_id)
    setMission(structuredClone(scenario.mission))
    setPreferences(structuredClone(scenario.preferences || {}))
    setResult(null)
    setError('')
  }

  function cycleCategory(id) {
    const required = mission.required_categories.includes(id)
    const optional = mission.optional_categories.includes(id)
    setMission((current) => ({
      ...current,
      required_categories: required
        ? current.required_categories.filter((item) => item !== id)
        : optional ? [...current.required_categories, id] : current.required_categories,
      optional_categories: required
        ? current.optional_categories
        : optional ? current.optional_categories.filter((item) => item !== id) : [...current.optional_categories, id],
    }))
  }

  async function parseMission() {
    if (naturalText.trim().length < 3) return
    setError('')
    try {
      const parsed = await api('/api/v1/missions/parse', { method: 'POST', body: JSON.stringify({ text: naturalText }) })
      setParseResult(parsed)
    } catch (requestError) {
      setError(`Ekstraksi misi belum tersedia: ${requestError.message}`)
    }
  }

  function applyParsed() {
    const parsed = parseResult?.draft || parseResult?.mission || parseResult
    const parsedPreferences = parseResult?.preferences || parsed?.preferences
    if (!parsed) return
    setMission((current) => ({
      ...current,
      goal: parsed.goal || naturalText,
      required_categories: parsed.required_categories?.length ? parsed.required_categories : current.required_categories,
      optional_categories: parsed.optional_categories || current.optional_categories,
      max_budget: parsed.max_budget || current.max_budget,
      max_merchants: parsed.max_merchants || current.max_merchants,
    }))
    if (parsedPreferences) {
      setPreferences((current) => ({ ...current, ...parsedPreferences }))
    }
    setParseResult(null)
  }

  async function recommend(event) {
    event.preventDefault()
    setError('')
    if (!mission.required_categories.length) {
      setError('Pilih minimal satu kategori wajib.')
      return
    }
    setLoading(true)
    const payload = {
      mission: { ...mission, max_budget: Number(mission.max_budget), max_merchants: Number(mission.max_merchants) },
      preferences: { ...preferences, minimum_rating: preferences.minimum_rating ? Number(preferences.minimum_rating) : null },
      context: { session_id: sessionId(), strategy: 'hybrid_mission', top_k: 10, include_comparison: compare },
    }
    try {
      const recommendation = await api('/api/v1/recommendations', { method: 'POST', body: JSON.stringify(payload) })
      setResult(recommendation)
      setSource('live')
      setApiHealth('ok')
    } catch (requestError) {
      setResult(staticFallback(payload.mission, categories))
      setSource('fallback')
      setApiHealth('offline')
      setError(`Live API tidak dapat dipakai (${requestError.message}). Contoh statis ditampilkan dan diberi label.`)
    } finally {
      setLoading(false)
    }
  }

  async function sendFeedback(productId, eventType) {
    if (source !== 'live') {
      setFeedback((current) => ({ ...current, [productId]: 'Feedback tidak dikirim dalam mode statis.' }))
      return
    }
    try {
      await api('/api/v1/feedback', { method: 'POST', body: JSON.stringify({ session_id: sessionId(), product_id: productId, event_type: eventType, metadata: { surface: 'recommendation_result' } }) })
      setFeedback((current) => ({ ...current, [productId]: eventType === 'save' ? 'Disimpan' : 'Ditandai tidak relevan' }))
    } catch (requestError) {
      setFeedback((current) => ({ ...current, [productId]: requestError.message }))
    }
  }

  const ranking = benchmark?.evaluation?.ranking || analytics?.recommendation_quality?.offline_metrics || {}
  const primaryRanking = ranking['EXP-006'] || Object.values(ranking)[0]
  const primaryMetrics = primaryRanking?.metrics || primaryRanking || {}

  return (
    <div className="app-shell">
      <header className="topbar">
        <button className="brand" onClick={() => setView('demo')} aria-label="Buka demo RASA">
          <span className="brand-mark">R</span><span><b>RASA</b><small>Relevance-aware shopping</small></span>
        </button>
        <nav aria-label="Navigasi utama">
          <button className={view === 'demo' ? 'active' : ''} onClick={() => setView('demo')}>Demo</button>
          <button className={view === 'insights' ? 'active' : ''} onClick={() => setView('insights')}>System insights</button>
          <button className={view === 'method' ? 'active' : ''} onClick={() => setView('method')}>Metodologi</button>
        </nav>
        <div className={`status-pill ${apiHealth}`}><i />{apiHealth === 'ok' ? 'Live API' : apiHealth === 'checking' ? 'Memeriksa API' : 'Demo fallback'}</div>
      </header>

      {view === 'demo' && <main>
        <section className="hero-section">
          <div className="eyebrow">DECISION INTELLIGENCE UNTUK BELANJA</div>
          <h1>Bukan sekadar produk populer.<br /><em>Keranjang yang masuk akal.</em></h1>
          <p>RASA menerjemahkan tujuan belanja menjadi kombinasi produk yang relevan, tersedia, dan patuh pada anggaran serta batas jumlah toko.</p>
          <div className="hero-facts">
            <span><b>600</b> produk sintetis</span><span><b>4</b> lapisan keputusan</span><span><b>100%</b> tanpa data pribadi</span>
          </div>
        </section>

        <section className="scenario-section" aria-labelledby="scenario-title">
          <div className="section-heading"><div><span>Langkah 1</span><h2 id="scenario-title">Mulai dari sebuah misi</h2></div><p>Pilih skenario atau susun kebutuhan sendiri.</p></div>
          <div className="scenario-grid">
            {scenarios.slice(0, 6).map((scenario, index) => <button key={scenario.scenario_id} className={`scenario-card ${selectedScenario === scenario.scenario_id ? 'selected' : ''}`} onClick={() => applyScenario(scenario)}>
              <span className="scenario-number">{String(index + 1).padStart(2, '0')}</span><b>{scenario.title}</b><p>{scenario.description}</p><small>{rupiah(scenario.mission.max_budget)} · maks. {scenario.mission.max_merchants} toko</small>
            </button>)}
          </div>
        </section>

        <section className="workspace">
          <form className="builder" onSubmit={recommend}>
            <div className="panel-title"><div><span>Langkah 2</span><h2>Rancang batasan</h2></div><span className="simulation-badge">Data simulasi</span></div>
            <label className="field"><span>Tujuan belanja</span><textarea value={mission.goal} onChange={(event) => setMission({ ...mission, goal: event.target.value })} minLength="3" maxLength="500" required /></label>

            <details className="nl-box">
              <summary>Isi cepat dari kalimat bebas <span>opsional</span></summary>
              <textarea placeholder="Contoh: Saya butuh tas, alat tulis, dan botol minum maksimal 250 ribu dari 2 toko." value={naturalText} onChange={(event) => setNaturalText(event.target.value)} />
              <button type="button" className="secondary-button" onClick={parseMission}>Ekstrak & tinjau</button>
              {parseResult && <div className="parse-preview"><b>Hasil ekstraksi perlu konfirmasi</b><pre>{JSON.stringify(parseResult.draft || parseResult.mission || parseResult, null, 2)}</pre><button type="button" onClick={applyParsed}>Terapkan ke formulir</button></div>}
            </details>

            <fieldset><legend>Kategori <small>Klik: opsional → wajib → kosong</small></legend><div className="chip-grid">
              {categories.map((category) => {
                const state = mission.required_categories.includes(category.category_id) ? 'required' : mission.optional_categories.includes(category.category_id) ? 'optional' : 'none'
                return <button type="button" key={category.category_id} className={`category-chip ${state}`} onClick={() => cycleCategory(category.category_id)}><i>{state === 'required' ? 'W' : state === 'optional' ? 'O' : '+'}</i>{category.category_name}</button>
              })}
            </div><div className="legend"><span><i className="required-dot" /> Wajib</span><span><i className="optional-dot" /> Opsional</span></div></fieldset>

            <div className="field-row">
              <label className="field"><span>Anggaran maksimum</span><div className="input-prefix"><b>Rp</b><input type="number" min="1" max="50000000" step="1000" value={mission.max_budget} onChange={(event) => setMission({ ...mission, max_budget: event.target.value })} required /></div></label>
              <label className="field"><span>Maksimum toko</span><input type="number" min="1" max="10" value={mission.max_merchants} onChange={(event) => setMission({ ...mission, max_merchants: event.target.value })} required /></label>
            </div>
            <div className="field-row">
              <label className="field"><span>Rating minimum</span><input type="number" min="0" max="5" step="0.1" value={preferences.minimum_rating || ''} onChange={(event) => setPreferences({ ...preferences, minimum_rating: event.target.value })} placeholder="Tanpa batas" /></label>
              <label className="field"><span>Gaya <small>pisahkan koma</small></span><input value={(preferences.style || []).join(', ')} onChange={(event) => setPreferences({ ...preferences, style: event.target.value.split(',').map((item) => item.trim()).filter(Boolean) })} /></label>
            </div>
            <label className="compare-toggle"><input type="checkbox" checked={compare} onChange={(event) => setCompare(event.target.checked)} /><span>Bandingkan dengan baseline independen</span></label>
            {error && <div className="alert" role="alert">{error}</div>}
            <button className="primary-button" disabled={loading}>{loading ? <><i className="spinner" /> Menyusun keranjang…</> : <>Susun rekomendasi <span>→</span></>}</button>
            <p className="privacy-note">Tidak perlu login. Session ID acak hanya dipakai untuk event demo anonim.</p>
          </form>

          <section className={`results ${result ? 'has-result' : ''}`} aria-live="polite">
            {!result && <div className="empty-result"><div className="basket-illustration"><span /><span /><span /></div><h2>Keranjangmu akan muncul di sini</h2><p>RASA akan menilai kandidat, menerapkan batasan keras, lalu memilih kombinasi terbaik.</p><ol><li>Candidate retrieval</li><li>Hybrid ranking</li><li>Basket optimization</li><li>Explanation</li></ol></div>}
            {result && <>
              <div className="result-header"><div><span className={`source-label ${source}`}>{source === 'live' ? '● LIVE INFERENCE' : '● STATIC FALLBACK'}</span><h2>{result.basket.feasible ? 'Misi dapat dipenuhi' : 'Belum ada kombinasi yang feasible'}</h2><p>{result.basket.feasible ? 'Semua kategori wajib dan batasan keras terpenuhi.' : 'RASA tidak menghapus batasan secara diam-diam. Coba saran berikut.'}</p></div><span className={`feasibility ${result.basket.feasible ? 'yes' : 'no'}`}>{result.basket.feasible ? 'Feasible' : 'Infeasible'}</span></div>
              <div className="metrics-grid">
                <Metric label="Total" value={rupiah(result.basket.total_price)} />
                <Metric label="Sisa anggaran" value={rupiah(result.basket.budget_remaining)} />
                <Metric label="Jumlah toko" value={`${result.basket.merchant_count}/${mission.max_merchants}`} />
                <Metric label="Cakupan wajib" value={`${Math.round((result.basket.required_category_coverage || 0) * 100)}%`} />
              </div>
              {result.basket.suggestions?.length > 0 && <div className="suggestions"><b>Saran pelonggaran</b>{result.basket.suggestions.map((item) => <p key={item}>→ {item}</p>)}</div>}
              <div className="basket-items">
                {result.basket.items?.map((item, index) => <article className="product-card" key={item.product_id}>
                  <div className="product-index">{String(index + 1).padStart(2, '0')}</div>
                  <div className="product-main"><span>{item.category_name || categoryName[item.category_id]}</span><h3>{item.product_name}</h3><p>{item.merchant_name} · ★ {Number(item.rating).toFixed(1)}</p></div>
                  <div className="product-price"><b>{rupiah(item.price)}</b><small>tersedia · simulasi</small></div>
                  <div className="feedback-actions"><button onClick={() => sendFeedback(item.product_id, 'save')} aria-label={`Simpan ${item.product_name}`}>Simpan</button><button onClick={() => sendFeedback(item.product_id, 'dismiss')} aria-label={`Tandai ${item.product_name} tidak relevan`}>Tidak relevan</button>{feedback[item.product_id] && <small>{feedback[item.product_id]}</small>}</div>
                </article>)}
              </div>
              {result.explanations?.length > 0 && <div className="explanation-panel"><span>Mengapa kombinasi ini?</span>{result.explanations.map((reason, index) => <div key={`${reason.code || 'reason'}-${index}`}><i>{index + 1}</i><p><b>{reason.label}</b>{reason.detail}</p></div>)}</div>}
              {result.comparison && <div className="comparison"><h3>Optimasi vs baseline</h3><div><Metric label="Selisih harga" value={rupiah(result.comparison.deltas.total_price)} /><Metric label="Selisih toko" value={result.comparison.deltas.merchant_count} /><Metric label="Selisih cakupan" value={`${Math.round(result.comparison.deltas.required_category_coverage * 100)} poin`} /></div><p>{result.comparison.label}</p></div>}
              {result.limitations?.length > 0 && <details className="limitations"><summary>Batasan hasil</summary>{result.limitations.map((item) => <p key={item}>— {item}</p>)}</details>}
            </>}
          </section>
        </section>
      </main>}

      {view === 'insights' && <main className="content-page"><div className="page-intro"><span>OFFLINE EVALUATION + DEMO EVENTS</span><h1>System insights</h1><p>Metrik di bawah berasal dari holdout temporal pada data sintetis dan event demo anonim. Bukan bukti dampak bisnis nyata.</p></div>
        <section className="insight-filters" aria-label="Filter insight"><label>Periode<select value={insightDays} onChange={(event) => setInsightDays(event.target.value)}><option value="7">7 hari</option><option value="30">30 hari</option><option value="90">90 hari</option></select></label><label>Model<select value={insightModel} onChange={(event) => setInsightModel(event.target.value)}><option value="">Semua model</option><option value="hybrid-v1">hybrid-v1</option></select></label><label>Strategi<select value={insightStrategy} onChange={(event) => setInsightStrategy(event.target.value)}><option value="">Semua strategi</option><option value="hybrid_mission">Hybrid mission</option><option value="content">Content</option><option value="popularity_category">Category popularity</option></select></label></section>
        <section className="insight-grid">
          <Metric label="NDCG@10" value={Number(primaryMetrics['ndcg@10'] || 0).toFixed(3)} hint="Holdout temporal" />
          <Metric label="Recall@10" value={Number(primaryMetrics['recall@10'] || 0).toFixed(3)} hint="Holdout temporal" />
          <Metric label="Request demo" value={analytics?.sample_sizes?.recommendation_requests ?? '—'} hint="30 hari terakhir" />
          <Metric label="p95 API" value={analytics?.system_health?.api_latency_ms?.p95 ? `${Math.round(analytics.system_health.api_latency_ms.p95)} ms` : '—'} hint="Sampel aktual" />
        </section>
        <section className="insight-panels"><div><h2>Kualitas misi</h2><dl><dt>Budget feasibility</dt><dd>{Math.round((analytics?.mission_quality?.budget_feasibility_rate || 0) * 100)}%</dd><dt>Cakupan kategori rata-rata</dt><dd>{Math.round((analytics?.mission_quality?.avg_required_category_coverage || 0) * 100)}%</dd><dt>Rata-rata jumlah toko</dt><dd>{analytics?.mission_quality?.avg_merchant_count ?? '—'}</dd></dl></div><div><h2>Exposure produk</h2><dl><dt>Catalog coverage</dt><dd>{Math.round((analytics?.recommendation_quality?.catalog_coverage || 0) * 100)}%</dd><dt>Long-tail share</dt><dd>{Math.round((analytics?.product_exposure?.long_tail_share || 0) * 100)}%</dd><dt>Exposure Gini</dt><dd>{analytics?.product_exposure?.gini ?? '—'}</dd></dl></div></section>
        {analytics?.warnings?.length > 0 && <div className="warning-list"><b>Catatan interpretasi</b>{analytics.warnings.map((warning) => <p key={warning}>— {warning}</p>)}</div>}
      </main>}

      {view === 'method' && <main className="content-page"><div className="page-intro"><span>HOW IT WORKS</span><h1>Dari misi ke keputusan</h1><p>Model tidak menggantikan batasan bisnis. Ranking menghasilkan preferensi, lalu optimizer memastikan hasil akhir tetap layak.</p></div><section className="pipeline">
        {[['01', 'Candidate generation', 'Kategori, atribut, popularitas, dan histori membentuk kumpulan kandidat.'], ['02', 'Hybrid ranking', 'Sinyal content, collaborative, mission, kualitas, dan affinity digabung dengan bobot tervalidasi.'], ['03', 'Feasibility', 'Stok, rating, harga individual, serta kategori wajib disaring sebelum optimasi.'], ['04', 'Basket optimization', 'ILP memilih kombinasi yang patuh pada anggaran dan batas jumlah toko.'], ['05', 'Explanation & feedback', 'Faktor yang benar-benar dipakai diterjemahkan ke alasan; respons anonim dicatat sebagai event.']].map(([number, title, copy]) => <article key={number}><span>{number}</span><div><h2>{title}</h2><p>{copy}</p></div></article>)}
      </section><section className="method-note"><h2>Batas klaim</h2><p>Katalog, harga, stok, merchant, profil, dan interaksi sepenuhnya sintetis. Skor internal bukan probabilitas pembelian. Simulasi A/B bukan eksperimen online dan tidak membuktikan efek kausal.</p></section></main>}

      <footer><span>RASA · portfolio engineering project</span><span>Data sintetis · tanpa transaksi · tanpa data pribadi</span></footer>
    </div>
  )
}

export default App
