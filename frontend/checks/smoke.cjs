/* Optional development verification; runtime UI has no dependency on Playwright.
   Run against the SÜSIE bridge (itsg.webserver) so backend wiring is covered:
     python3 -m itsg.webserver --port 8766
   Synthetic-fallback behaviour is covered via routed /api failures. */
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..');
const output=path.join(root,'verification');
const base=(process.env.SUSIE_BASE_URL||'http://127.0.0.1:8766').replace(/\/$/,'');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.SUSIE_CHROMIUM_EXECUTABLE?{executablePath:process.env.SUSIE_CHROMIUM_EXECUTABLE}:{})});
 const page=await browser.newPage();const errors=[];const failedResponses=[];const checks=[];
 page.on('pageerror',error=>errors.push(error.message));
 page.on('response',response=>{if(response.status()>=400)failedResponses.push({url:response.url(),status:response.status()});});
 fs.mkdirSync(path.join(output,'screenshots'),{recursive:true});
 function assert(value,message){if(!value)throw Error(message);}
 try {
  await page.goto(base+'/');await page.waitForURL('**/pruefakte.html');assert(page.url().includes('pruefakte.html'),'index entry must resolve');
  // Backend wiring: badge connected, 4 backend cases
  await page.waitForFunction(()=>document.querySelector('#backend-badge-text')&&document.querySelector('#backend-badge-text').textContent.length>0);
  assert(!(await page.locator('#backend-badge').getAttribute('class')).includes('offline'),'backend badge connected');
  assert(await page.locator('#case-rows tr').count()===4,'backend serves 4 cases');
  checks.push('backend wiring: /api/state drives table, connected badge, 4 cases');
  for(const theme of ['casual','contrast'])for(const mode of ['light','dark']){
   await page.goto(`${base}/pruefakte.html?theme=${theme}&mode=${mode}&lang=de`);
   assert(await page.locator('html').getAttribute('data-theme')===theme,'theme applied');
   assert(await page.locator('html').getAttribute('data-mode')===mode,'mode applied');
   assert(await page.locator('.brand-logo').evaluate(async image=>{try{await image.decode();}catch{}return image.complete&&image.naturalWidth>=100&&image.currentSrc.includes('susie-logo');}),'repo logo loads (srcset display size)');
   if(theme==='casual'){
    assert(await page.locator('.rail').evaluate(rail=>getComputedStyle(rail).boxShadow!=='none'),'sidebar elevation shadow (casual)');
   }else{
    assert(await page.locator('.rail').evaluate(rail=>getComputedStyle(rail).borderRightWidth==='1px'),'sidebar elevation border (contrast)');
   }
   for(const [width,height] of [[1440,1050],[768,1024],[390,844]]){
    await page.setViewportSize({width,height});
    assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),'page overflow '+theme+'/'+mode+'/'+width);
    await page.screenshot({path:path.join(output,'screenshots',`${theme}-${mode}-${width}.png`),fullPage:true});
   }
   await page.setViewportSize({width:1440,height:1050});
   checks.push(`${theme}/${mode}: logo, theme state, sidebar elevation, 1440/768/390 layout and screenshots`);
  }
  await page.goto(base+'/pruefakte.html?theme=casual&mode=light&lang=de');
  await page.waitForFunction(()=>document.querySelectorAll('#case-rows tr').length===4);
  // Filters, search, open findings
  await page.locator('#case-search').fill('NETTO');assert(await page.locator('#case-rows tr:visible').count()===1,'search matches field (NETTO-1 in TC-1)');
  await page.locator('#case-search').fill('EAZ-BEGINN');assert(await page.locator('#case-rows tr:visible').count()===2,'search matches field (EAZ-BEGINN-1 in TC-1 and TC-2)');
  await page.locator('#case-search').fill('no such case');assert(await page.locator('#cases .empty').isVisible(),'empty');
  await page.locator('[data-reset-filter]').click();assert(await page.locator('#case-rows tr:visible').count()===4,'reset');
  await page.locator('#result-filter').selectOption('NOT_EVALUATED');assert(await page.locator('#case-rows tr:visible').count()===1,'status filter');
  await page.locator('#result-filter').selectOption('');
  const klar=page.locator('[data-open-findings]');await klar.click();assert(await page.locator('#case-rows tr:visible').count()===2,'open-findings filter');
  assert((await klar.getAttribute('aria-pressed'))==='true','open-findings pressed');
  await klar.click();assert((await klar.getAttribute('aria-pressed'))==='false','open-findings toggles off');
  assert(await page.locator('#case-rows tr:visible').count()===4,'all rows restored');
  checks.push('search, empty/reset, status filter, open-findings toggle (backend data)');
  // Story suites view (backend stories/cases)
  assert(await page.locator('nav [data-view="stories"]').isVisible(),'stories nav present');
  await page.locator('nav [data-view="stories"]').click();
  await page.waitForFunction(()=>document.querySelectorAll('#story-rows tr').length>0,null,{timeout:15000});
  assert(await page.locator('.story-card').count()===4,'four story cards');
  assert(await page.locator('#story-rows tr').count()===200,'200 story cases rendered');
  await page.locator('#story-filter').selectOption('1');assert(await page.locator('#story-rows tr').count()===40,'story filter 1 → 40 cases');
  await page.locator('#story-defects').click();assert(await page.locator('#story-rows tr').count()>0&&await page.locator('#story-rows tr').count()<40,'defects-only filter');
  await page.locator('#story-defects').click();
  await page.locator('#story-filter').selectOption('');
  await page.locator('#story-search').fill('S1-001');assert(await page.locator('#story-rows tr').count()===1,'story search by id');
  await page.locator('#story-rows tr').first().locator('.case-link').click();
  assert((await page.locator('#story-detail-title').textContent()).includes('S1-'),'story case detail opens');
  assert((await page.locator('#story-detail').textContent()).includes('ABGABEGRUND'),'story detail shows expected record');
  await page.locator('#story-search').fill('');
  checks.push('story suites view: cards, 200 cases, story/defect filters, search, case detail with expected record');
  // Note: cases view still intact after story tables exist
  await page.locator('nav [data-view="cases"]').click();assert(await page.locator('#case-rows tr').count()===4,'cases table intact after stories');
  // Case selection + run evidence
  await page.locator('[data-open-case="2"]').click();assert((await page.locator('#detail-title').textContent()).includes('TC-2'),'case selection');
  await page.locator('[data-run]').click();assert((await page.locator('#run-evidence pre').textContent()).includes('EAZ-BEGINN-1'),'output evidence shows DTA fields');
  // Note lifecycle (validation, draft restore, save, report list, two-step delete)
  await page.locator('[data-review]').click();await page.locator('[data-save]').click();assert(await page.locator('#note-error').isVisible(),'note validation');
  const note='Repository verification <img src=x onerror=alert(1)> العربية 中文';
  await page.locator('textarea').fill(note);await page.reload();await page.locator('[data-review]').click();assert(await page.locator('textarea').inputValue()===note,'draft restored');
  await page.locator('[data-save]').click();await page.reload();await page.locator('nav [data-view="audit"]').click();
  assert((await page.locator('.timeline').textContent()).includes(note),'note restored');assert(await page.locator('.timeline img').count()===0,'literal safe text');
  await page.locator('nav [data-view="cases"]').click();await page.locator('[data-sort="0"]').click();await page.locator('[data-sort="0"]').click();assert(await page.locator('#case-rows tr').first().getAttribute('data-case')==='1','sort descending by case id');
  await page.locator('nav [data-view="sources"]').click();await page.reload();assert(await page.locator('#sources').isVisible(),'deep link restore');
  assert((await page.locator('#sources-paper').textContent()).includes('GKV-Spitzenverband'),'backend source rendered');
  await page.locator('nav [data-view="report"]').click();assert(await page.locator('#report button:disabled').count()===1,'release blocked');
  await page.locator('#report-note-list').scrollIntoViewIfNeeded();
  const reportNote=page.locator('#report-note-list .note-text',{hasText:note});assert(await reportNote.count()===1,'note visible in report');
  assert(await page.locator('#report-note-list img').count()===0,'report literal safe text');
  const del=page.locator('#report-note-list .note-delete');await del.click();assert((await del.textContent())==='Wirklich löschen?','delete two-step confirm');
  await del.click();assert(await page.locator('#report-note-list li').count()===0,'note deleted');
  const pendingDownload=page.waitForEvent('download');await page.locator('[data-export]').click();const download=await pendingDownload;
  const exported=JSON.parse(fs.readFileSync(await download.path(),'utf8'));
  assert(exported.synthetic===false&&exported.compliance_claim===false&&exported.findings.length===4,'export boundary (backend)');
  checks.push('case/run evidence, note validation, reload recovery, literal multilingual text, sorting, deep links, backend source view, blocked release, report notes, two-step delete, JSON export');
  // Report view: review runs (harness + reports + offline generate)
  assert(await page.locator('#report-runs .run-stat').count()>=5,'harness big numbers present');
  assert((await page.locator('#report-runs').textContent()).includes('RPT-'),'latest review reports listed');
  assert(await page.locator('#report-runs table').count()>=1,'findings table present');
  await page.locator('#report-run-review').click();
  await page.waitForFunction(()=>{const t=document.querySelector('#report-runs')?document.querySelector('#report-runs').textContent:'';return t.includes('erzeugt')||t.includes('generated')||document.querySelectorAll('#report-runs .run-review-list li, #report-runs [data-run-id]').length>0;},null,{timeout:120000});
  checks.push('review runs section: harness numbers, latest reports, findings table, offline review generation');
  // Language switch (rail quick control + settings persistence)
  await page.locator('.quick-controls [data-set-lang="en"]').click();
  assert(await page.locator('html').getAttribute('lang')==='en','html lang switched');
  assert((await page.locator('nav [data-view="cases"]').textContent())==='Cases','nav translated');
  assert((await page.locator('#backend-badge-text').textContent()).includes('connected'),'backend badge translated');
  await page.reload();assert(await page.locator('html').getAttribute('lang')==='en','language persisted');
  await page.locator('.quick-controls [data-set-lang="de"]').click();
  assert((await page.locator('nav [data-view="cases"]').textContent())==='Prüffälle','nav back to German');
  checks.push('language selector EN/DE: live switch, persistence, translated chrome');
  // Theme cycle icon rotates through all four variants
  const cycleSequence=[['casual','dark'],['contrast','dark'],['contrast','light'],['casual','light']];
  for(const [theme,mode] of cycleSequence){await page.locator('#theme-cycle').click();
   assert(await page.locator('html').getAttribute('data-theme')===theme,'cycle theme '+theme);
   assert(await page.locator('html').getAttribute('data-mode')===mode,'cycle mode '+mode);}
  checks.push('theme cycle icon rotates casual/light → casual/dark → contrast/dark → contrast/light');
  // Settings menu: API config + connection check + offline re-run
  assert(await page.locator('#api-endpoint').isVisible(),'settings menu visible with API endpoint field');await page.locator('#api-endpoint').fill('');
  await page.locator('#api-check').click();
  await page.waitForFunction(()=>document.querySelector('#api-status').textContent.length>0&&document.querySelector('#api-status').textContent.includes('Verbunden'));
  await page.locator('#api-run-offline').click();
  await page.waitForFunction(()=>document.querySelector('#api-status').textContent.includes('neu ausgeführt'),null,{timeout:30000});
  assert(await page.locator('#case-rows tr').count()===4,'offline re-run rebuilds 4 cases');
  checks.push('settings menu: API endpoint field, connection check, offline demo re-run');
  // Responsive extremes, zoom, motion, forced colors, print
  await page.locator('nav [data-view="cases"]').click();
  for(const [width,height] of [[320,812],[812,375],[2560,1440]]){await page.setViewportSize({width,height});assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),'wide/small overflow');}
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>document.documentElement.style.fontSize='32px');assert(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),'200% font');await page.evaluate(()=>document.documentElement.style.fontSize='');
  await page.emulateMedia({reducedMotion:'reduce'});await page.locator('[data-open-case="0"]').click();assert(!await page.evaluate(()=>document.getAnimations().some(animation=>animation.playState==='running')),'reduced motion');
  await page.emulateMedia({forcedColors:'active'});await page.locator('[data-open-case="1"]').click();
  await page.emulateMedia({media:'print',forcedColors:'none'});assert(!await page.locator('.rail').isVisible(),'print chrome');
  checks.push('appearance persistence, 320/812-landscape/2560 layouts, 200% root font, reduced motion, forced-colors interaction, print chrome');
  // Synthetic fallback: block the API, expect honest offline banner + 3 synthetic cases
  const fallback=await browser.newPage();const fallbackErrors=[];fallback.on('pageerror',error=>fallbackErrors.push(error.message));
  await fallback.route('**/api/**',route=>route.abort());
  await fallback.goto(base+'/pruefakte.html?lang=de');
  assert((await fallback.locator('#backend-badge').getAttribute('class')).includes('offline'),'fallback badge offline');
  assert((await fallback.locator('#backend-badge-text').textContent()).includes('synthetisch'),'fallback banner honest');
  assert(await fallback.locator('tbody tr').count()===3,'synthetic fallback 3 cases');
  await fallback.locator('#case-search').fill('NETTO');assert(await fallback.locator('tbody tr:visible').count()===1,'synthetic search');
  assert(fallbackErrors.length===0,'no JS errors in fallback');
  await fallback.close();
  checks.push('synthetic fallback with explicit offline banner when API is unreachable');
  // Denied storage
  const denied=await browser.newPage();await denied.addInitScript(()=>{for(const name of ['sessionStorage','localStorage'])Object.defineProperty(window,name,{get(){throw new DOMException('Denied','SecurityError');}});});
  await denied.goto(base+'/pruefakte.html?lang=de');await denied.locator('[data-review]').click();await denied.locator('textarea').fill('Synthetic storage-denial check');await denied.locator('[data-save]').click();assert((await denied.locator('#note-help').textContent()).includes('nicht verfügbar'),'denied storage recovery');await denied.close();
  // Broken logo
  const broken=await browser.newPage();await broken.route('**/assets/susie-logo*.png',route=>route.abort());await broken.goto(base+'/pruefakte.html');assert(await broken.locator('.brand-fallback').isVisible(),'logo fallback');await broken.close();
  checks.push('denied browser storage and broken-image recovery');
  assert(errors.length===0,'JavaScript errors');assert(failedResponses.length===0,'HTTP failures');
  const report={status:'PASS',timestamp:new Date().toISOString(),base_url:base,frontend_directory:root,engine:'Chromium via Playwright (SÜSIE bridge)',checks,errors,failedResponses,limits:['Backend = itsg demo store via stdlib bridge; not a production service','No Safari, physical-device or screen-reader validation'],command:'SUSIE_BASE_URL='+base+' PLAYWRIGHT_MODULE=<installed package> SUSIE_CHROMIUM_EXECUTABLE=<installed Chromium> node frontend/checks/smoke.cjs (against python3 -m itsg.webserver)'};
  fs.writeFileSync(path.join(output,'repo-browser-checks.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
