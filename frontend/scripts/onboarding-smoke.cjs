const { chromium } = require(process.env.RASA_PLAYWRIGHT_MODULE || 'playwright');
const path = require('node:path');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '../..');
const output = path.join(root, '.cache');
fs.mkdirSync(output, {recursive:true});

(async () => {
 const browser = await chromium.launch({headless:true, ...(process.env.RASA_BROWSER_EXECUTABLE ? {executablePath:process.env.RASA_BROWSER_EXECUTABLE} : {})});
 try {
  const context = await browser.newContext({viewport:{width:1280,height:900}});
  const page = await context.newPage();
  const errors=[]; page.on('pageerror',error=>errors.push(error.message));
  await page.goto(process.env.RASA_TEST_URL || 'http://127.0.0.1:8000');
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('heading',{name:'Welcome to RASA',exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>document.activeElement.textContent.trim()), 'Show me how →');
  await page.screenshot({path:path.join(output,'welcome-en.png')});
  await dialog.getByRole('button',{name:'Skip tutorial',exact:true}).click();
  await page.reload();
  assert.equal(await dialog.count(),0);
  const goal = page.getByRole('textbox',{name:'Shopping goal',exact:true});
  await goal.fill('My own first kit');
  const originalBudget = await page.getByRole('spinbutton',{name:'Overall budget (IDR)',exact:true}).inputValue();
  await page.getByRole('button',{name:'How to use',exact:true}).click();
  await dialog.getByRole('combobox',{name:'Tutorial language / Bahasa panduan',exact:true}).selectOption('id');
  await dialog.getByRole('heading',{name:'Selamat datang di RASA',exact:true}).waitFor();
  await page.keyboard.press('Escape');
  assert.equal(await dialog.count(),0);
  assert.equal(await page.evaluate(()=>document.activeElement.textContent.trim()), 'Cara pakai');
  await page.getByRole('button',{name:'Cara pakai',exact:true}).click();
  await dialog.getByRole('button',{name:'Ajari saya',exact:true}).click();
  await dialog.getByRole('heading',{name:'Pilih titik awal',exact:true}).waitFor();
  // Native modal focus stays inside the tutorial while tabbing in either direction.
  for (let i=0;i<12;i++) {
   await page.keyboard.press(i < 6 ? 'Tab' : 'Shift+Tab');
   assert.equal(await page.evaluate(()=>Boolean(document.activeElement.closest('dialog'))),true);
  }
  await dialog.getByRole('button',{name:'Lanjut',exact:true}).click();
  await dialog.getByRole('heading',{name:'Tentukan yang penting',exact:true}).waitFor();
  await dialog.getByRole('button',{name:'Kembali',exact:true}).click();
  await dialog.getByRole('heading',{name:'Pilih titik awal',exact:true}).waitFor();
  await dialog.getByRole('button',{name:'Lanjut',exact:true}).click();
  await dialog.getByRole('button',{name:'Lanjut',exact:true}).click();
  await dialog.getByRole('heading',{name:'Tentukan anggaran',exact:true}).waitFor();
  const clearOfBudget = () => page.evaluate(() => {
   const card = document.querySelector('.tour-card').getBoundingClientRect();
   const budget = document.querySelector('[data-tour="budget"]').getBoundingClientRect();
   return card.right <= budget.left || card.left >= budget.right || card.bottom <= budget.top || card.top >= budget.bottom;
  });
  assert.equal(await clearOfBudget(),true);
  await page.screenshot({path:path.join(output,'tour-budget.png')});
  await dialog.getByRole('button',{name:'Lanjut',exact:true}).click();
  await dialog.getByRole('heading',{name:'Periksa, ganti, dan putuskan',exact:true}).waitFor();
  await dialog.getByRole('button',{name:'Mulai menyusun',exact:true}).click();
  assert.equal(await dialog.count(),0);
  assert.equal(await page.getByRole('textbox',{name:'Tujuan paket',exact:true}).inputValue(),'My own first kit');
  assert.equal(await page.getByRole('spinbutton',{name:'Anggaran keseluruhan (rupiah)',exact:true}).inputValue(),originalBudget);
  await page.setViewportSize({width:390,height:844});
  await page.getByRole('button',{name:'Cara pakai',exact:true}).click();
  await page.screenshot({path:path.join(output,'welcome-mobile.png')});
  const bounds = await dialog.locator('.tour-card').boundingBox();
  assert(bounds.x>=0 && bounds.x+bounds.width<=390 && bounds.y>=0 && bounds.y+bounds.height<=844);
  await dialog.getByRole('button',{name:'Ajari saya',exact:true}).click();
  await dialog.getByRole('button',{name:'Lanjut',exact:true}).click();
  await dialog.getByRole('button',{name:'Lanjut',exact:true}).click();
  await dialog.getByRole('heading',{name:'Tentukan anggaran',exact:true}).waitFor();
  assert.equal(await clearOfBudget(),true);
  await dialog.getByRole('button',{name:'Tutup tutorial',exact:true}).click();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false);
  await page.reload();
  assert.equal(await dialog.count(),0);
  assert.deepEqual(errors,[]);
  const restricted = await browser.newContext();
  await restricted.addInitScript(() => Object.defineProperty(window,'localStorage',{value:{getItem(){throw new Error('Storage unavailable');},setItem(){throw new Error('Storage unavailable');}}}));
  const restrictedPage = await restricted.newPage();
  await restrictedPage.goto(process.env.RASA_TEST_URL || 'http://127.0.0.1:8000');
  await restrictedPage.getByRole('button',{name:'Skip tutorial',exact:true}).click();
  assert.equal(await restrictedPage.getByRole('dialog').count(),0);
  await restrictedPage.getByRole('button',{name:'Build a kit',exact:true}).waitFor();
  await restricted.close();
  const report={generated_at:new Date().toISOString(),first_visit_welcome:true,skip_persisted:true,replay:true,english_and_indonesian:true,all_four_steps:true,back_navigation:true,escape_and_close:true,focus_contained_and_restored:true,input_preserved:true,mobile_dialog_within_viewport:true,storage_unavailable_can_dismiss:true,page_errors:errors};
  fs.writeFileSync(path.join(root,'artifacts/reports/onboarding-smoke.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report));
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
