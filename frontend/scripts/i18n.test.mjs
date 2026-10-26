import assert from 'node:assert/strict'
import test from 'node:test'
import { translate, presetGoal } from '../src/pilot-i18n.js'

test('English is the default; Indonesian is selectable', () => {
  assert.equal(translate('Terima paket'), 'Accept kit')
  assert.equal(translate('Terima paket', 'id'), 'Terima paket')
  assert.match(translate('Ongkir belum diketahui; total akhir belum dapat dipastikan.'), /Shipping is unknown/)
})

test('Only known preset goals are translated, preserving custom user content', () => {
  assert.equal(presetGoal('Siapkan perlengkapan awal kuliah', 'en'), 'Prepare a college starter kit')
  assert.equal(presetGoal('Prepare a college starter kit', 'id'), 'Siapkan perlengkapan awal kuliah')
  assert.equal(presetGoal('My own kit for semester two', 'id'), 'My own kit for semester two')
  assert.equal(presetGoal('One complete kit.', 'id'), 'One complete kit.')
})

test('Dynamic infeasibility suggestions keep factual categories and cost bounds', () => {
  assert.match(translate('Belum ada stok atau metadata sesuai filter untuk: bag. Ubah kebutuhan atau filter rating.'), /^No stock.*bag/)
  assert.match(translate('Batas bawah biaya kebutuhan wajib Rp110,000. Coba anggaran lebih besar atau kurangi kebutuhan wajib; batas ini belum menjamin kombinasi layak.'), /IDR 110,000.*does not guarantee feasibility/)
})
