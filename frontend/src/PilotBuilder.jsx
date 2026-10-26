import { useEffect, useState } from 'react'
import { translate, presetGoal } from './pilot-i18n'
import WelcomeTour from './WelcomeTour'
import { shouldShowWelcome } from './onboarding-state'

const base = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
const names = { bag: 'Tas', book: 'Buku', desk: 'Perlengkapan meja', drinkware: 'Botol minum', electronics: 'Elektronik', organizer: 'Penyimpanan', personal_care: 'Perawatan diri', snack: 'Camilan', stationery: 'Alat tulis', umbrella: 'Payung' }
const scenarios = [
  { title: 'Awal kuliah', goal: 'Siapkan perlengkapan awal kuliah', required: ['bag', 'stationery', 'drinkware'], budget: 250000 },
  { title: 'Meja belajar di kos', goal: 'Rapikan meja belajar di kos', required: ['desk', 'organizer', 'drinkware'], budget: 350000 },
  { title: 'Kebutuhan harian kos', goal: 'Siapkan kebutuhan harian kos', required: ['personal_care', 'drinkware', 'organizer'], budget: 200000 },
]

function session() {
  let id = sessionStorage.getItem('rasa-pilot-session')
  if (!id) { id = crypto.randomUUID(); sessionStorage.setItem('rasa-pilot-session', id) }
  return id
}

async function request(path, payload) {
  const response = await fetch(`${base}/api/v1/pilot${path}`, {
    method: payload ? 'POST' : 'GET', signal: AbortSignal.timeout(20000),
    headers: { 'Content-Type': 'application/json', 'X-Session-ID': session() },
    body: payload ? JSON.stringify(payload) : undefined,
  })
  const body = await response.json()
  if (!response.ok) throw new Error(body.error?.message || 'Permintaan gagal. Silakan coba lagi.')
  return body
}

export default function PilotBuilder({ onTechnical, language = 'en', onLanguageChange }) {
  const t = text => translate(text, language)
  const rupiah = value => new Intl.NumberFormat(language === 'id' ? 'id-ID' : 'en-US', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(value)
  const [tourOpen, setTourOpen] = useState(shouldShowWelcome)
  const [config, setConfig] = useState(null)
  const [choice, setChoice] = useState(0)
  const [goal, setGoal] = useState(presetGoal(scenarios[0].goal, language))
  const [required, setRequired] = useState(scenarios[0].required)
  const [optional, setOptional] = useState([])
  const [budget, setBudget] = useState(250000)
  const [style, setStyle] = useState('')
  const [color, setColor] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [handoff, setHandoff] = useState(null)
  const [pending, setPending] = useState(null)
  const [offline, setOffline] = useState(false)
  useEffect(() => {
    request('/config').then(setConfig).catch(() => setOffline(true))
    const last = sessionStorage.getItem('rasa-pilot-mission')
    if (last) request(`/missions/${encodeURIComponent(last)}`).then(saved => {
      setResult(saved); setGoal(saved.mission.goal); setRequired(saved.mission.required_categories)
      setOptional(saved.mission.optional_categories); setBudget(saved.mission.max_budget)
      setStyle(saved.mission.preferences.style[0] || ''); setColor(saved.mission.preferences.colors[0] || '')
    }).catch(() => sessionStorage.removeItem('rasa-pilot-mission'))
  }, [])

  function apply(index) {
    const s = scenarios[index]
    setChoice(index); setGoal(presetGoal(s.goal, language)); setRequired(s.required); setBudget(s.budget)
    setOptional([]); setResult(null); setPending(null); setHandoff(''); setNotice(''); setError('')
  }
  function category(id, value) {
    invalidate()
    setRequired(p => value === 'required' ? [...new Set([...p, id])] : p.filter(c => c !== id))
    setOptional(p => value === 'optional' ? [...new Set([...p, id])] : p.filter(c => c !== id))
  }
  function invalidate() {
    setResult(null); setHandoff(''); setNotice('')
    sessionStorage.removeItem('rasa-pilot-mission')
  }
  async function build(event) {
    event.preventDefault(); setBusy(true); setError(''); setNotice(''); setHandoff(''); setResult(null)
    const input = { mission: { goal: presetGoal(goal, language), required_categories: required, optional_categories: optional, max_budget: Number(budget), max_merchants: 1 }, preferences: { style: style ? [style] : [], colors: color ? [color] : [] } }
    const serialized = JSON.stringify(input)
    // Reuse the same ID after a lost response so network retries do not duplicate missions.
    const payload = { ...input, mission_id: pending?.input === serialized ? pending.id : crypto.randomUUID() }
    setPending({ input: serialized, id: payload.mission_id })
    try {
      setResult(await request('/missions', payload)); setOffline(false); setPending(null)
      sessionStorage.setItem('rasa-pilot-mission', payload.mission_id)
    }
    catch (e) { setError(e.message || 'Permintaan gagal. Silakan coba lagi.') }
    finally { setBusy(false) }
  }
  async function action(kind, item, replacement) {
    setBusy(true); setError(''); setNotice(''); setHandoff('')
    try {
      const next = await request(`/missions/${result.mission_id}/${kind}`, { revision: result.revision, product_id: item || null, replacement_id: replacement || null })
      setResult(next)
      setNotice(kind === 'replace' ? 'Barang diganti; seluruh paket diperiksa ulang.' : kind === 'accept' ? 'Paket diterima untuk dipertimbangkan. Ini belum merupakan pesanan.' : 'Ringkasan siap disalin. Belum dikirim ke mitra.')
      if (next.handoff) setHandoff(next.handoff)
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }
  const basket = result?.basket
  return <div className="app-shell pilot-shell" lang={language}>
    {tourOpen && <WelcomeTour language={language} onLanguageChange={onLanguageChange} onDismiss={() => setTourOpen(false)} />}
    <header className="topbar"><div className="brand"><span className="brand-mark">R</span><span><b>RASA</b><small>{t("Asisten penyusun paket")}</small></span></div><label className="language-picker"><span>{language === 'id' ? 'Bahasa' : 'Language'}</span><select aria-label="Language / Bahasa" value={language} onChange={e => onLanguageChange(e.target.value)}><option value="en">English</option><option value="id">Bahasa Indonesia</option></select></label><button type="button" data-tour-help onClick={() => setTourOpen(true)}>{language === 'id' ? 'Cara pakai' : 'How to use'}</button><button onClick={onTechnical}>{t("Bukti teknis & demo model")}</button></header>
    <main><section className="hero-section"><div className="eyebrow">{t("PERLENGKAPAN AWAL KULIAH & KOS")}</div><h1>{t("Satu paket.")}<br /><em>{t("Sesuai kebutuhanmu.")}</em></h1><p>{t("Pilih kebutuhan wajib dan anggaran. Periksa komprominya, ganti barang, lalu siapkan ringkasan untuk merchant.")}</p><p className="simulation-badge">{config?.mode === 'pilot' ? t("Pilot satu merchant · periksa status katalog pada hasil") : t("Demo sintetis · belum ada pesanan nyata")}</p><p>{t("Segmen mahasiswa dan model B2B2C masih hipotesis yang perlu diuji.")}</p></section>
      <section className="scenario-section" data-tour="scenarios"><h2>{t("1. Mulai dari kebutuhan")}</h2><div className="scenario-grid">{scenarios.map((s, i) => <button key={t(s.title)} className={`scenario-card ${choice === i ? 'selected' : ''}`} disabled={busy} onClick={() => apply(i)}><b>{t(s.title)}</b><p>{s.required.map(id => t(names[id])).join(', ')}</p><small>{rupiah(s.budget)}</small></button>)}</div></section>
      <section className="workspace"><form className="builder" onSubmit={build} onChange={invalidate}>
        <h2>{t("2. Atur paketmu")}</h2><label className="field"><span>{t("Tujuan paket")}</span><textarea disabled={busy} required minLength={3} maxLength={500} value={presetGoal(goal, language)} onChange={e => setGoal(e.target.value)} /></label>
        <fieldset data-tour="needs"><legend>{t("Kebutuhan wajib & tambahan")}</legend><p>{t("Satu barang per kategori. Tambahan boleh dilewati.")}</p>{Object.entries(names).map(([id, label]) => <label className="field-row" key={id}><span>{t(label)}</span><select disabled={busy} aria-label={`${language === 'id' ? 'Kebutuhan' : 'Need'} ${t(label)}`} value={required.includes(id) ? 'required' : optional.includes(id) ? 'optional' : ''} onChange={e => category(id, e.target.value)}><option value="">{t("Tidak perlu")}</option><option value="required">{t("Wajib")}</option><option value="optional">{t("Tambahan")}</option></select></label>)}</fieldset>
        <label className="field" data-tour="budget"><span>{t("Anggaran keseluruhan (rupiah)")}</span><input disabled={busy} required type="number" min={1} max={50000000} step={1} value={budget} onChange={e => setBudget(e.target.value)} /></label><p>{config?.shipping != null ? language === 'id' ? `Ongkir tetap ${rupiah(config.shipping)} dicadangkan dari anggaran.` : `Fixed shipping of ${rupiah(config.shipping)} is reserved from your budget.` : t("Ongkir belum diketahui. Hasil hanya menjamin subtotal barang; total akhir perlu diperiksa merchant.")}</p>
        <div className="field-row"><label className="field"><span>{t("Gaya pilihan")}</span><select disabled={busy} value={style} onChange={e => setStyle(e.target.value)}><option value="">{t("Bebas")}</option><option value="minimalist">{t("Minimalis")}</option><option value="natural">{t("Natural")}</option><option value="classic">{t("Klasik")}</option></select></label><label className="field"><span>{t("Warna pilihan")}</span><select disabled={busy} value={color} onChange={e => setColor(e.target.value)}><option value="">{t("Bebas")}</option><option value="black">{t("Hitam")}</option><option value="white">{t("Putih")}</option><option value="cream">{t("Krem")}</option><option value="green">{t("Hijau")}</option></select></label></div>
        <p>{t("Gaya dan warna boleh dikompromikan. Alur ini menggunakan satu merchant.")}</p><button className="primary-button" disabled={busy || !required.length}>{busy ? t("Memeriksa paket…") : pending ? t("Susun / coba lagi") : t("Susun satu paket")}</button><p className="privacy-note">{t("Sesi acak mengukur alur. Jangan masukkan nama, alamat, atau nomor telepon. Tidak ada pembayaran.")}</p>
      </form><section className="results has-result" data-tour="results" aria-live="polite" aria-busy={busy}>
        {error && <div className="alert" role="alert">{t(error)}</div>}{notice && <p role="status">{t(notice)}</p>}
        {!basket && <div className="empty-result"><h2>{offline ? t("API belum tersedia") : t("Paketmu akan muncul di sini")}</h2><p>{offline ? t("Jalankan API lalu coba kembali. Contoh statis tersedia melalui demo model.") : t("Pilih kebutuhan dan susun paket. Dashboard teknis bersifat opsional.")}</p></div>}
        {basket && <><div className="result-header"><div><span className="source-label">{result.source === 'pilot' ? t("KATALOG MERCHANT") : t("DATA SINTETIS / PENGUJIAN")} · {language === 'id' ? 'versi' : 'revision'} {result.revision}</span><h2>{basket.feasible ? t("Kebutuhan wajib terpenuhi") : t("Belum ada kombinasi layak")}</h2><p>{t(basket.costs.notice)}</p></div></div>
          <div className="metrics-grid">{[[t("Subtotal barang"), rupiah(basket.costs.subtotal)], [t("Total biaya"), basket.costs.total == null ? t("Belum diketahui") : rupiah(basket.costs.total)], [basket.costs.total == null ? t("Sisa sebelum ongkir") : t("Sisa anggaran"), rupiah(basket.costs.remaining)], [t("Kebutuhan wajib"), `${Math.round(basket.required_category_coverage * 100)}%`]].map(([label, value]) => <div className="metric" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>
          {!basket.feasible && <div className="suggestions">{basket.suggestions.map(s => <p key={s}>{t(s)}</p>)}<p>{t("Ubah anggaran atau kebutuhan, kemudian susun ulang.")}</p></div>}
          <div className="basket-items">{basket.items.map(item => <article className="product-card" key={item.product_id}><div className="product-main"><span>{t(names[item.category_id]) || item.category_id} · {item.role === 'required' ? t("wajib") : t("tambahan")}</span><h3>{item.product_name}</h3><p>{item.merchant_name}</p><p>{language === 'id' ? 'Skor preferensi' : 'Preference score'} {item.score.toFixed(2)} · {language === 'id' ? 'bukan peluang pembelian' : 'not a purchase probability'}</p></div><div className="product-price"><b>{rupiah(item.price)}</b></div><label className="field"><span>{language === 'id' ? 'Ganti' : 'Replace'} {item.product_name}</span><select disabled={busy} value={item.product_id} onChange={e => action('replace', item.product_id, e.target.value)}>{(basket.options[item.category_id] || []).map(o => <option key={o.product_id} value={o.product_id}>{o.product_name} · {rupiah(o.price)}</option>)}</select></label></article>)}</div>
          <details className="limitations"><summary>{t("Alasan pilihan dan kompromi")}</summary><p>{t(basket.explanation)}</p><p>{t(basket.tradeoff)}</p><p>{t("Stok dan harga diperiksa ulang dari katalog terakhir. Belum ada reservasi stok langsung.")}</p></details>
          {basket.feasible && <div className="feedback-actions"><button disabled={busy} onClick={() => action('accept')}>{t("Terima paket")}</button><button disabled={busy} onClick={() => action('handoff')}>{t("Siapkan ringkasan mitra")}</button></div>}
          {handoff && <label className="field"><span>{t("Salin manual. Tidak ada pesan yang dikirim.")}</span><textarea rows={9} readOnly value={[t(handoff.destination_label), ...basket.items.map(i => `1 x ${i.product_name} (${i.product_id}) ${rupiah(i.price)}`), `${t('Subtotal barang')}: ${rupiah(basket.total_price)}`, t(basket.costs.notice)].join('\n')} /></label>}
        </>}
      </section></section>
    </main><footer><span>{t("RASA · portfolio & pilot terbatas")}</span><span>{t("Tanpa pembayaran · tanpa pengiriman pesanan otomatis")}</span></footer>
  </div>
}
