import { useEffect, useMemo, useState } from 'react'
import './App.css'
import PilotBuilder from './PilotBuilder'

const API_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

const fallbackCategories = [
  ['bag', 'Bags'], ['book', 'Books'], ['desk', 'Desk Accessories'],
  ['drinkware', 'Drinkware'], ['electronics', 'Electronics'],
  ['organizer', 'Organizers'], ['personal_care', 'Personal Care'],
  ['snack', 'Snacks'], ['stationery', 'Stationery'], ['umbrella', 'Umbrellas'],
].map(([category_id, category_name]) => ({ category_id, category_name }))

const fallbackScenarios = [
  {
    scenario_id: 'budget-campus', title: 'Budget campus kit',
    description: 'A bag, stationery, and drinkware for everyday campus life.',
    mission: { goal: 'Build a minimalist everyday campus kit', required_categories: ['bag', 'stationery', 'drinkware'], optional_categories: ['organizer'], max_budget: 250000, max_merchants: 2 },
    preferences: { style: ['minimalist', 'natural'], colors: ['black', 'gray', 'cream'], brands: [], minimum_rating: 4.2 },
  },
  {
    scenario_id: 'remote-work', title: 'Remote workspace',
    description: 'Comfortable, organized essentials for remote work.',
    mission: { goal: 'Create a comfortable and organized remote workspace', required_categories: ['desk', 'electronics', 'drinkware'], optional_categories: ['organizer'], max_budget: 750000, max_merchants: 3 },
    preferences: { style: ['minimalist', 'classic'], colors: ['black', 'white'], brands: [], minimum_rating: 4.3 },
  },
  {
    scenario_id: 'infeasible-case', title: 'Constraint test',
    description: 'An intentionally tight budget that demonstrates recovery suggestions.',
    mission: { goal: 'Buy a power bank on a very limited budget', required_categories: ['electronics'], optional_categories: [], max_budget: 25000, max_merchants: 1 },
    preferences: { style: [], colors: [], brands: [], minimum_rating: 4.5 },
  },
]

const demoCatalog = {
  bag: ['Cendana Tote Bag', 173000, 'Cendana Gift'],
  stationery: ['Bumi Notebook', 12000, 'Cendana Gift'],
  drinkware: ['Sagara Bottle', 30000, 'Karsa Technology'],
  organizer: ['Lentera Cable Organizer', 16500, 'Karsa Technology'],
  desk: ['Nusa Desk Lamp', 185000, 'Karsa Technology'],
  electronics: ['Volta Power Bank', 289000, 'Karsa Technology'],
  book: ['Planner Aksara', 68000, 'Cendana Gift'],
  personal_care: ['Aruna Hygiene Pouch', 39000, 'Cendana Gift'],
  snack: ['Bumi Granola', 27000, 'Karsa Technology'],
  umbrella: ['Nusa Folding Umbrella', 82000, 'Cendana Gift'],
}

function formatCurrency(value) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'IDR', currencyDisplay: 'code', maximumFractionDigits: 0 }).format(Number(value || 0))
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
    const [name, price, merchant] = demoCatalog[category] || [`Demo product ${category}`, 75000, 'Demo Store']
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
      suggestions: feasible ? [] : [`The minimum budget for this static example is ${formatCurrency(total)}. Increase the budget or relax the required categories.`],
    },
    explanations: feasible ? [
      { code: 'fallback_notice', label: 'Stored example', detail: 'This is a static example shown when the API is unavailable, not a live model inference.' },
      { code: 'constraints', label: 'Constraints satisfied', detail: `The total is within budget and uses ${merchants} merchants.` },
    ] : [],
    alternatives: { products: {}, baskets: [] }, recommendations: chosen,
    limitations: ['Static fallback mode is active. This result is not a live model inference.', 'Prices and inventory are simulated.'],
    meta: { data_mode: 'static_fallback', notice: 'Static example stored in the frontend.' },
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

function TechnicalApp() {
  const [view, setView] = useState('demo')
  const [categories, setCategories] = useState(fallbackCategories)
  const [scenarios, setScenarios] = useState(fallbackScenarios)
  const [selectedScenario, setSelectedScenario] = useState('budget-campus')
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
      setError(`Mission extraction is unavailable: ${requestError.message}`)
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
      setError('Select at least one required category.')
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
      setError(`The live API is unavailable (${requestError.message}). A clearly labeled static example is shown instead.`)
    } finally {
      setLoading(false)
    }
  }

  async function sendFeedback(productId, eventType) {
    if (source !== 'live') {
      setFeedback((current) => ({ ...current, [productId]: 'Feedback is not submitted in static mode.' }))
      return
    }
    try {
      await api('/api/v1/feedback', { method: 'POST', body: JSON.stringify({ session_id: sessionId(), product_id: productId, event_type: eventType, metadata: { surface: 'recommendation_result' } }) })
      setFeedback((current) => ({ ...current, [productId]: eventType === 'save' ? 'Saved' : 'Marked as irrelevant' }))
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
        <button className="brand" onClick={() => setView('demo')} aria-label="Open the RASA demo">
          <span className="brand-mark">R</span><span><b>RASA</b><small>Relevance-aware shopping</small></span>
        </button>
        <nav aria-label="Primary navigation">
          <button className={view === 'demo' ? 'active' : ''} onClick={() => setView('demo')}>Demo</button>
          <button className={view === 'insights' ? 'active' : ''} onClick={() => setView('insights')}>System insights</button>
          <button className={view === 'method' ? 'active' : ''} onClick={() => setView('method')}>Methodology</button>
        </nav>
        <div className={`status-pill ${apiHealth}`}><i />{apiHealth === 'ok' ? 'Live API' : apiHealth === 'checking' ? 'Checking API' : 'Demo fallback'}</div>
      </header>

      {view === 'demo' && <main>
        <section className="hero-section">
          <div className="eyebrow">DECISION INTELLIGENCE FOR SHOPPING</div>
          <h1>Beyond popular products.<br /><em>A basket that makes sense.</em></h1>
          <p>RASA turns a shopping goal into a relevant, available product bundle that respects both budget and merchant limits.</p>
          <div className="hero-facts">
            <span><b>600</b> synthetic products</span><span><b>4</b> decision layers</span><span>Anonymous demo sessions</span>
          </div>
        </section>

        <section className="scenario-section" aria-labelledby="scenario-title">
          <div className="section-heading"><div><span>Step 1</span><h2 id="scenario-title">Start with a mission</h2></div><p>Choose a scenario or define your own needs.</p></div>
          <div className="scenario-grid">
            {scenarios.slice(0, 6).map((scenario, index) => <button key={scenario.scenario_id} className={`scenario-card ${selectedScenario === scenario.scenario_id ? 'selected' : ''}`} onClick={() => applyScenario(scenario)}>
              <span className="scenario-number">{String(index + 1).padStart(2, '0')}</span><b>{scenario.title}</b><p>{scenario.description}</p><small>{formatCurrency(scenario.mission.max_budget)} · max. {scenario.mission.max_merchants} merchants</small>
            </button>)}
          </div>
        </section>

        <section className="workspace">
          <form className="builder" onSubmit={recommend}>
            <div className="panel-title"><div><span>Step 2</span><h2>Define constraints</h2></div><span className="simulation-badge">Simulated data</span></div>
            <label className="field"><span>Shopping goal</span><textarea value={mission.goal} onChange={(event) => setMission({ ...mission, goal: event.target.value })} minLength="3" maxLength="500" required /></label>

            <details className="nl-box">
              <summary>Quick fill from natural language <span>optional</span></summary>
              <textarea placeholder="Example: I need a bag, stationery, and a bottle for no more than IDR 250,000 from two merchants." value={naturalText} onChange={(event) => setNaturalText(event.target.value)} />
              <button type="button" className="secondary-button" onClick={parseMission}>Extract and review</button>
              {parseResult && <div className="parse-preview"><b>Review the extracted fields before applying them</b><pre>{JSON.stringify(parseResult.draft || parseResult.mission || parseResult, null, 2)}</pre><button type="button" onClick={applyParsed}>Apply to form</button></div>}
            </details>

            <fieldset><legend>Categories <small>Click: optional → required → clear</small></legend><div className="chip-grid">
              {categories.map((category) => {
                const state = mission.required_categories.includes(category.category_id) ? 'required' : mission.optional_categories.includes(category.category_id) ? 'optional' : 'none'
                return <button type="button" key={category.category_id} className={`category-chip ${state}`} onClick={() => cycleCategory(category.category_id)}><i>{state === 'required' ? 'W' : state === 'optional' ? 'O' : '+'}</i>{category.category_name}</button>
              })}
            </div><div className="legend"><span><i className="required-dot" /> Required</span><span><i className="optional-dot" /> Optional</span></div></fieldset>

            <div className="field-row">
              <label className="field"><span>Maximum budget</span><div className="input-prefix"><b>IDR</b><input type="number" min="1" max="50000000" step="1" value={mission.max_budget} onChange={(event) => setMission({ ...mission, max_budget: event.target.value })} required /></div></label>
              <label className="field"><span>Maximum merchants</span><input type="number" min="1" max="10" value={mission.max_merchants} onChange={(event) => setMission({ ...mission, max_merchants: event.target.value })} required /></label>
            </div>
            <div className="field-row">
              <label className="field"><span>Minimum rating</span><input type="number" min="0" max="5" step="0.1" value={preferences.minimum_rating || ''} onChange={(event) => setPreferences({ ...preferences, minimum_rating: event.target.value })} placeholder="No limit" /></label>
              <label className="field"><span>Styles <small>comma-separated</small></span><input value={(preferences.style || []).join(', ')} onChange={(event) => setPreferences({ ...preferences, style: event.target.value.split(',').map((item) => item.trim()).filter(Boolean) })} /></label>
            </div>
            <label className="compare-toggle"><input type="checkbox" checked={compare} onChange={(event) => setCompare(event.target.checked)} /><span>Compare with the independent baseline</span></label>
            {error && <div className="alert" role="alert">{error}</div>}
            <button className="primary-button" disabled={loading}>{loading ? <><i className="spinner" /> Building basket...</> : <>Build recommendations <span>→</span></>}</button>
            <p className="privacy-note">No login required. A random session ID is used only for anonymous demo events.</p>
          </form>

          <section className={`results ${result ? 'has-result' : ''}`} aria-live="polite">
            {!result && <div className="empty-result"><div className="basket-illustration"><span /><span /><span /></div><h2>Your basket will appear here</h2><p>RASA scores candidates, enforces hard constraints, and selects the best combination.</p><ol><li>Candidate retrieval</li><li>Hybrid ranking</li><li>Basket optimization</li><li>Explanation</li></ol></div>}
            {result && <>
              <div className="result-header"><div><span className={`source-label ${source}`}>{source === 'live' ? '● LIVE INFERENCE' : '● STATIC FALLBACK'}</span><h2>{result.basket.feasible ? 'Mission fulfilled' : 'No feasible combination yet'}</h2><p>{result.basket.feasible ? 'All required categories and hard constraints are satisfied.' : 'RASA never removes constraints silently. Try one of the suggestions below.'}</p></div><span className={`feasibility ${result.basket.feasible ? 'yes' : 'no'}`}>{result.basket.feasible ? 'Feasible' : 'Infeasible'}</span></div>
              <div className="metrics-grid">
                <Metric label="Total" value={formatCurrency(result.basket.total_price)} />
                <Metric label="Budget remaining" value={formatCurrency(result.basket.budget_remaining)} />
                <Metric label="Merchants" value={`${result.basket.merchant_count}/${mission.max_merchants}`} />
                <Metric label="Required coverage" value={`${Math.round((result.basket.required_category_coverage || 0) * 100)}%`} />
              </div>
              {result.basket.suggestions?.length > 0 && <div className="suggestions"><b>Constraint relaxation suggestions</b>{result.basket.suggestions.map((item) => <p key={item}>→ {item}</p>)}</div>}
              <div className="basket-items">
                {result.basket.items?.map((item, index) => <article className="product-card" key={item.product_id}>
                  <div className="product-index">{String(index + 1).padStart(2, '0')}</div>
                  <div className="product-main"><span>{item.category_name || categoryName[item.category_id]}</span><h3>{item.product_name}</h3><p>{item.merchant_name} · ★ {Number(item.rating).toFixed(1)}</p></div>
                  <div className="product-price"><b>{formatCurrency(item.price)}</b><small>available · simulated</small></div>
                  <div className="feedback-actions"><button onClick={() => sendFeedback(item.product_id, 'save')} aria-label={`Save ${item.product_name}`}>Save</button><button onClick={() => sendFeedback(item.product_id, 'dismiss')} aria-label={`Mark ${item.product_name} as irrelevant`}>Not relevant</button>{feedback[item.product_id] && <small>{feedback[item.product_id]}</small>}</div>
                </article>)}
              </div>
              {result.explanations?.length > 0 && <div className="explanation-panel"><span>Why this combination?</span>{result.explanations.map((reason, index) => <div key={`${reason.code || 'reason'}-${index}`}><i>{index + 1}</i><p><b>{reason.label}</b>{reason.detail}</p></div>)}</div>}
              {result.comparison && <div className="comparison"><h3>Optimization vs. baseline</h3><div><Metric label="Price difference" value={formatCurrency(result.comparison.deltas.total_price)} /><Metric label="Merchant difference" value={result.comparison.deltas.merchant_count} /><Metric label="Coverage difference" value={`${Math.round(result.comparison.deltas.required_category_coverage * 100)} points`} /></div><p>{result.comparison.label}</p></div>}
              {result.limitations?.length > 0 && <details className="limitations"><summary>Result limitations</summary>{result.limitations.map((item) => <p key={item}>- {item}</p>)}</details>}
            </>}
          </section>
        </section>
      </main>}

      {view === 'insights' && <main className="content-page"><div className="page-intro"><span>OFFLINE EVALUATION + DEMO EVENTS</span><h1>System insights</h1><p>These metrics come from a temporal holdout on synthetic data and anonymous demo events. They are not evidence of real business impact.</p></div>
        <section className="insight-filters" aria-label="Insight filters"><label>Period<select value={insightDays} onChange={(event) => setInsightDays(event.target.value)}><option value="7">7 days</option><option value="30">30 days</option><option value="90">90 days</option></select></label><label>Model<select value={insightModel} onChange={(event) => setInsightModel(event.target.value)}><option value="">All models</option><option value="hybrid-v1">hybrid-v1</option></select></label><label>Strategy<select value={insightStrategy} onChange={(event) => setInsightStrategy(event.target.value)}><option value="">All strategies</option><option value="hybrid_mission">Hybrid mission</option><option value="content">Content</option><option value="popularity_category">Category popularity</option></select></label></section>
        <section className="insight-grid">
          <Metric label="NDCG@10" value={Number(primaryMetrics['ndcg@10'] || 0).toFixed(3)} hint="Holdout temporal" />
          <Metric label="Recall@10" value={Number(primaryMetrics['recall@10'] || 0).toFixed(3)} hint="Holdout temporal" />
          <Metric label="Demo requests" value={analytics?.sample_sizes?.recommendation_requests ?? 'N/A'} hint="Last 30 days" />
          <Metric label="API p95" value={analytics?.system_health?.api_latency_ms?.p95 ? `${Math.round(analytics.system_health.api_latency_ms.p95)} ms` : 'N/A'} hint="Observed sample" />
        </section>
        <section className="insight-panels"><div><h2>Mission quality</h2><dl><dt>Budget feasibility</dt><dd>{Math.round((analytics?.mission_quality?.budget_feasibility_rate || 0) * 100)}%</dd><dt>Average category coverage</dt><dd>{Math.round((analytics?.mission_quality?.avg_required_category_coverage || 0) * 100)}%</dd><dt>Average merchant count</dt><dd>{analytics?.mission_quality?.avg_merchant_count ?? 'N/A'}</dd></dl></div><div><h2>Product exposure</h2><dl><dt>Catalog coverage</dt><dd>{Math.round((analytics?.recommendation_quality?.catalog_coverage || 0) * 100)}%</dd><dt>Long-tail share</dt><dd>{Math.round((analytics?.product_exposure?.long_tail_share || 0) * 100)}%</dd><dt>Exposure Gini</dt><dd>{analytics?.product_exposure?.gini ?? 'N/A'}</dd></dl></div></section>
        {analytics?.warnings?.length > 0 && <div className="warning-list"><b>Interpretation notes</b>{analytics.warnings.map((warning) => <p key={warning}>- {warning}</p>)}</div>}
      </main>}

      {view === 'method' && <main className="content-page"><div className="page-intro"><span>HOW IT WORKS</span><h1>From mission to decision</h1><p>The model does not replace business constraints. Ranking expresses preferences, then the optimizer keeps the final result feasible.</p></div><section className="pipeline">
        {[['01', 'Candidate generation', 'Categories, attributes, popularity, and history form the candidate pool.'], ['02', 'Hybrid ranking', 'Content, collaborative, mission, quality, and affinity signals are combined with validated weights.'], ['03', 'Feasibility', 'Inventory, ratings, per-item prices, and required categories are filtered before optimization.'], ['04', 'Basket optimization', 'An ILP selects a combination that respects the budget and merchant limit.'], ['05', 'Explanation & feedback', 'The factors actually used become human-readable reasons, and anonymous responses are recorded as events.']].map(([number, title, copy]) => <article key={number}><span>{number}</span><div><h2>{title}</h2><p>{copy}</p></div></article>)}
      </section><section className="method-note"><h2>Claim boundaries</h2><p>The catalog, prices, inventory, merchants, profiles, and interactions are entirely synthetic. Internal scores are not purchase probabilities. The A/B simulation is not an online experiment and does not establish causal effects.</p></section></main>}

      <footer><span>RASA · portfolio engineering project</span><span>Synthetic data · no transactions · no identity required</span></footer>
    </div>
  )
}

export default function App() {
  const [technical, setTechnical] = useState(false)
  const [language, setLanguage] = useState(() => localStorage.getItem('rasa-language') === 'id' ? 'id' : 'en')
  useEffect(() => {
    localStorage.setItem('rasa-language', language)
    document.documentElement.lang = technical ? 'en' : language
  }, [language, technical])
  return technical ? <div lang="en"><button className="secondary-button" onClick={() => setTechnical(false)}>{language === 'id' ? '← Kembali ke penyusunan paket' : '← Back to kit builder'}</button><TechnicalApp /></div> : <PilotBuilder language={language} onLanguageChange={setLanguage} onTechnical={() => setTechnical(true)} />
}
