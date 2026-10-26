import { useEffect, useRef, useState } from 'react'
import { rememberWelcome } from './onboarding-state'

const content = {
  en: {
    label: 'Quick start', welcome: 'Welcome to RASA', intro: 'Let’s put your first kit together.',
    description: 'Tell us what you need and your budget. RASA helps you find a complete combination and understand the trade-offs.',
    start: 'Show me how', skip: 'Skip tutorial', next: 'Next', back: 'Back', done: 'Start building', close: 'Close tutorial',
    hint: 'You can reopen this guide anytime using “How to use”.', progress: 'Step', of: 'of', language: 'Language',
    steps: [
      ['Pick a starting point', 'Choose a college or boarding scenario to fill in a starter list. You can still change everything to suit your needs.', 'scenarios'],
      ['Tell us what matters', 'Mark essentials as Required. Use Optional for extras that can be left out. Choose a style or color if you have a preference.', 'needs'],
      ['Set your budget', 'Enter your overall budget in whole rupiah, then choose Build a kit. If shipping is unknown, the result clearly separates the merchandise subtotal from the final cost.', 'budget'],
      ['Review, swap, and decide', 'Your kit appears here with costs and required coverage. You can replace an item, accept the kit, and prepare a merchant summary. This does not place an order. If no kit fits, adjust your budget or needs.', 'results'],
    ],
  },
  id: {
    label: 'Panduan singkat', welcome: 'Selamat datang di RASA', intro: 'Yuk, susun paket pertamamu.',
    description: 'Pilih kebutuhan dan anggaranmu. RASA membantu mencari satu paket lengkap serta menjelaskan kompromi pilihannya.',
    start: 'Ajari saya', skip: 'Lewati tutorial', next: 'Lanjut', back: 'Kembali', done: 'Mulai menyusun', close: 'Tutup tutorial',
    hint: 'Panduan ini bisa dibuka lagi lewat tombol “Cara pakai”.', progress: 'Langkah', of: 'dari', language: 'Bahasa',
    steps: [
      ['Pilih titik awal', 'Pilih skenario awal kuliah atau kos untuk mengisi daftar awal. Semua pilihan tetap bisa kamu ubah sesuai kebutuhan.', 'scenarios'],
      ['Tentukan yang penting', 'Tandai kebutuhan utama sebagai Wajib. Pilih Tambahan untuk barang yang boleh dilewati. Isi gaya atau warna jika ada preferensi.', 'needs'],
      ['Tentukan anggaran', 'Masukkan anggaran keseluruhan dalam rupiah bulat, lalu pilih Susun satu paket. Jika ongkir belum diketahui, hasil akan memisahkan subtotal barang dari biaya akhir.', 'budget'],
      ['Periksa, ganti, dan putuskan', 'Paket muncul di sini bersama biaya dan kebutuhan yang terpenuhi. Kamu bisa mengganti barang, menerima paket, lalu menyiapkan ringkasan mitra. Ini belum membuat pesanan. Jika belum layak, ubah anggaran atau kebutuhan.', 'results'],
    ],
  },
}

export default function WelcomeTour({ language, onLanguageChange, onDismiss }) {
  const [step, setStep] = useState(0)
  const dialog = useRef(null)
  const card = useRef(null)
  const spotlight = useRef(null)
  const primary = useRef(null)
  const copy = content[language] || content.en

  function dismiss() {
    rememberWelcome()
    onDismiss()
  }

  function containFocus(event) {
    if (event.key !== 'Tab') return
    const controls = [...dialog.current.querySelectorAll('button:not([disabled]), select:not([disabled])')]
    const first = controls[0]
    const last = controls[controls.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  useEffect(() => {
    const element = dialog.current
    const previous = document.activeElement
    const overflow = document.body.style.overflow
    element.showModal()
    document.body.style.overflow = 'hidden'
    primary.current.focus()
    return () => {
      element.close()
      document.body.style.overflow = overflow
      const focusTarget = previous instanceof HTMLElement && previous !== document.body && previous.isConnected ? previous : document.querySelector('[data-tour-help]')
      focusTarget?.focus({ preventScroll: true })
    }
  }, [])

  useEffect(() => {
    const target = step ? document.querySelector(`[data-tour="${copy.steps[step - 1][2]}"]`) : null
    target?.scrollIntoView({ behavior: 'instant', block: window.innerWidth > 700 ? 'center' : 'start' })
    if (target && window.innerWidth <= 700) {
      const headerHeight = document.querySelector('.pilot-shell .topbar')?.getBoundingClientRect().height || 100
      window.scrollBy({ top: -headerHeight - 20, behavior: 'instant' })
    }
    let frame
    function position() {
      const margin = 16
      const width = Math.min(430, window.innerWidth - margin * 2)
      const height = card.current.getBoundingClientRect().height
      const rect = target?.getBoundingClientRect()
      let left = (window.innerWidth - width) / 2
      let top = !rect ? Math.max(margin, (window.innerHeight - height) / 2) : rect.bottom + height + 24 < window.innerHeight ? rect.bottom + 12 : Math.max(margin, window.innerHeight - height - margin)
      if (rect && window.innerWidth > 700) {
        if (window.innerWidth - rect.right >= width + margin * 2) left = rect.right + margin
        else if (rect.left >= width + margin * 2) left = rect.left - width - margin
        else left = Math.max(margin, Math.min(rect.left, window.innerWidth - width - margin))
        if (left >= rect.right || left + width <= rect.left) top = Math.max(margin, Math.min(rect.top + (rect.height - height) / 2, window.innerHeight - height - margin))
      }
      Object.assign(card.current.style, { width: `${width}px`, left: `${left}px`, top: `${top}px` })
      Object.assign(spotlight.current.style, rect ? {
        left: `${Math.max(8, rect.left - 6)}px`, top: `${Math.max(8, rect.top - 6)}px`,
        width: `${Math.min(rect.width + 12, window.innerWidth - 16)}px`, height: `${Math.max(0, Math.min(rect.bottom + 6, window.innerHeight - 8) - Math.max(8, rect.top - 6))}px`,
        background: 'transparent', borderRadius: '16px', boxShadow: '0 0 0 9999px rgba(9, 28, 19, .55)', border: '2px solid #c9f368',
      } : { left: '0', top: '0', width: '100%', height: '100%', background: 'rgba(9, 28, 19, .55)', borderRadius: '0', boxShadow: 'none', border: '0' })
    }
    function schedule() { cancelAnimationFrame(frame); frame = requestAnimationFrame(position) }
    position()
    window.addEventListener('resize', schedule)
    window.addEventListener('scroll', schedule, true)
    return () => { cancelAnimationFrame(frame); window.removeEventListener('resize', schedule); window.removeEventListener('scroll', schedule, true) }
  }, [step, copy])

  return <dialog className="welcome-tour" ref={dialog} aria-labelledby="tour-title" aria-describedby="tour-description" onKeyDown={containFocus} onCancel={event => { event.preventDefault(); dismiss() }} lang={language}>
    <div ref={spotlight} className="tour-spotlight" aria-hidden="true" />
    <div ref={card} className="tour-card">
      <div className="tour-toolbar"><span>{copy.label}</span><select aria-label="Tutorial language / Bahasa panduan" value={language} onChange={event => onLanguageChange(event.target.value)}><option value="en">English</option><option value="id">Bahasa Indonesia</option></select><button type="button" className="tour-close" aria-label={copy.close} onClick={dismiss}>×</button></div>
      <div className="tour-symbol" aria-hidden="true">{step ? `0${step}` : 'R'}</div>
      <p className="tour-kicker" role="status">{step ? `${copy.progress} ${step} ${copy.of} ${copy.steps.length}` : copy.intro}</p>
      <h2 id="tour-title">{step ? copy.steps[step - 1][0] : copy.welcome}</h2>
      <p id="tour-description">{step ? copy.steps[step - 1][1] : copy.description}</p>
      <div className="tour-dots" aria-hidden="true">{[0, 1, 2, 3, 4].map(index => <span key={index} className={index === step ? 'active' : ''} />)}</div>
      <div className="tour-actions">{step > 0 && <button type="button" className="tour-back" onClick={() => setStep(step - 1)}>{copy.back}</button>}<button type="button" className="tour-primary" ref={primary} onClick={() => step === copy.steps.length ? dismiss() : setStep(step + 1)}>{step === 0 ? copy.start : step === copy.steps.length ? copy.done : copy.next}<span aria-hidden="true"> →</span></button></div>
      <button type="button" className="tour-skip" onClick={dismiss}>{copy.skip}</button>
      <p className="tour-hint">{copy.hint}</p>
    </div>
  </dialog>
}
