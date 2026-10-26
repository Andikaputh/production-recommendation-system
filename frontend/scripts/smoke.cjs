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
  const cases = {
   en: { build:'Build a kit', ready:'Your essentials are covered', accept:'Accept kit', accepted:'Kit accepted for consideration.', summary:'Prepare merchant summary', copy:'Copy manually. No message has been sent.', budget:'Overall budget (IDR)', impossible:'No feasible combination yet', goal:'Shopping goal', scenario:'Starting college' },
   id: { build:'Susun satu paket', ready:'Kebutuhan wajib terpenuhi', accept:'Terima paket', accepted:'Paket diterima untuk dipertimbangkan.', summary:'Siapkan ringkasan mitra', copy:'Salin manual. Tidak ada pesan yang dikirim.', budget:'Anggaran keseluruhan (rupiah)', impossible:'Belum ada kombinasi layak', goal:'Tujuan paket', scenario:'Awal kuliah' },
  };
  const report = {generated_at:new Date().toISOString(), default_language:'en', languages:{}};
  for (const [locale, labels] of Object.entries(cases)) {
   const context = await browser.newContext({viewport:{width:1440,height:1000}});
   const page = await context.newPage();
   const errors=[]; page.on('pageerror', e=>errors.push(e.message));
   await page.goto(process.env.RASA_TEST_URL || 'http://127.0.0.1:8000');
   await page.getByRole('button',{name:'Build a kit',exact:true}).waitFor();
   assert.equal(await page.locator('html').getAttribute('lang'), 'en');
   await page.getByRole('textbox',{name:'Shopping goal',exact:true}).fill('My custom semester kit');
   await page.getByRole('combobox',{name:'Language / Bahasa',exact:true}).selectOption('id');
   assert.equal(await page.getByRole('textbox',{name:'Tujuan paket',exact:true}).inputValue(),'My custom semester kit');
   if(locale==='en') await page.getByRole('combobox',{name:'Language / Bahasa',exact:true}).selectOption('en');
   await page.reload();
   assert.equal(await page.getByRole('combobox',{name:'Language / Bahasa',exact:true}).inputValue(),locale);
   await page.getByRole('button',{name:new RegExp(labels.scenario)}).click();
   await page.getByRole('button',{name:labels.build,exact:true}).click();
   await page.getByRole('heading',{name:labels.ready,exact:true}).waitFor();
   await page.getByRole('button',{name:labels.accept,exact:true}).click();
   await page.getByText(labels.accepted,{exact:false}).waitFor();
   await page.getByRole('button',{name:labels.summary,exact:true}).click();
   await page.getByText(labels.copy,{exact:true}).waitFor();
   await page.getByRole('combobox',{name:'Language / Bahasa',exact:true}).selectOption(locale==='en'?'id':'en');
   await page.getByRole('combobox',{name:'Language / Bahasa',exact:true}).selectOption(locale);
   await page.getByRole('heading',{name:labels.ready,exact:true}).waitFor();
   await page.evaluate(()=>window.scrollTo(0,0));
   await page.screenshot({path:path.join(output,`ui-desktop-${locale}.png`),fullPage:true});
   if(locale==='en') fs.copyFileSync(path.join(output,'ui-desktop-en.png'),path.join(output,'ui-desktop.png'));
   await page.getByRole('spinbutton',{name:labels.budget,exact:true}).fill('1');
   assert.equal(await page.getByRole('heading',{name:labels.ready,exact:true}).count(),0);
   await page.getByRole('button',{name:labels.build,exact:true}).click();
   await page.getByRole('heading',{name:labels.impossible,exact:true}).waitFor();
   await page.setViewportSize({width:390,height:844});
   await page.screenshot({path:path.join(output,`ui-mobile-${locale}.png`),fullPage:true});
   if(locale==='en') fs.copyFileSync(path.join(output,'ui-mobile-en.png'),path.join(output,'ui-mobile.png'));
   const overflow = await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
   await page.route('**/api/v1/pilot/missions', route=>route.abort());
   await page.getByRole('spinbutton',{name:labels.budget,exact:true}).fill('250000');
   await page.getByRole('button',{name:labels.build,exact:true}).click();
   await page.getByRole('alert').waitFor();
   assert.deepEqual(errors,[]); assert.equal(overflow,false);
   report.languages[locale]={feasible:true,acceptance:true,handoff:true,infeasible:true,api_failure:true,language_persisted:true,custom_input_preserved:true,result_preserved_on_language_switch:true,mobile_overflow:overflow,page_errors:errors};
   await context.close();
  }
  const technicalContext = await browser.newContext();
  const technicalPage = await technicalContext.newPage();
  await technicalPage.goto(process.env.RASA_TEST_URL || 'http://127.0.0.1:8000');
  await technicalPage.getByRole('button',{name:'Technical evidence & model demo',exact:true}).click();
  const maximumBudget = technicalPage.getByRole('spinbutton',{name:/^Maximum budget/});
  for (const value of ['1','1000','25000','250000','250001','750000','50000000']) {
   await maximumBudget.fill(value);
   assert.equal(await maximumBudget.evaluate(input=>input.checkValidity()),true,`Budget ${value} must be valid`);
  }
  for (const value of ['0','-1','1.5','50000001']) {
   await maximumBudget.fill(value);
   assert.equal(await maximumBudget.evaluate(input=>input.checkValidity()),false,`Budget ${value} must remain invalid`);
  }
  await maximumBudget.fill('250000');
  const recommendationResponse = technicalPage.waitForResponse(response=>response.url().endsWith('/api/v1/recommendations') && response.request().method()==='POST');
  await technicalPage.getByRole('button',{name:'Build recommendations',exact:false}).click();
  const submitted = await recommendationResponse;
  assert.equal(submitted.request().postDataJSON().mission.max_budget,250000);
  assert.equal(submitted.status(),200);
  await technicalPage.locator('.source-label.live').waitFor();
  report.maximum_budget={valid_whole_rupiah:true,invalid_bounds_and_fractions_rejected:true,submitted_budget:250000,api_status:submitted.status(),live_result_rendered:true};
  await technicalContext.close();
  fs.writeFileSync(path.join(root,'artifacts/reports/ui-smoke.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report));
 } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exit(1)});
