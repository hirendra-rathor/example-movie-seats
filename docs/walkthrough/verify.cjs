// Browser verification of the actual file:// reader with networking disabled.
const {chromium} = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const {pathToFileURL} = require('node:url');
const assert = require('node:assert/strict');

(async()=>{
  const output = await fs.mkdtemp(path.join(os.tmpdir(), 'movie-seats-reader-'));
  const browser = await chromium.launch({headless:true,...(process.env.CHROME_PATH ? {executablePath:process.env.CHROME_PATH} : {})});
  const requests=[];const errors=[];const checks=[];
  try{
    const context=await browser.newContext({viewport:{width:1440,height:1080},offline:true,colorScheme:'light'});
    await context.route(/^https?:/,route=>{requests.push(route.request().url());return route.abort();});
    const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
    await page.goto(pathToFileURL(path.join(__dirname,'index.html')).href);
    await page.evaluate(async()=>{await Promise.all([...document.images].filter(image=>image.getAttribute('src')).map(async image=>{image.loading='eager';await image.decode();}));});
    assert.equal(await page.locator('.milestone:visible').count(),1);
    await page.screenshot({path:path.join(output,'desktop-prompt.png'),fullPage:true});
    const stages=['prompt','proposal','authorization','implementation','evidence'];
    for(let m=1;m<=3;m++){
      await page.locator(`[data-milestone="m${m}"]`).click();
      await page.locator(`#m${m}-prompt`).waitFor({state:'visible'});
      for(const stage of stages){
        await page.locator(`#m${m}-${stage}-tab`).click();
        await page.locator(`#m${m}-${stage}`).waitFor({state:'visible'});
        assert.equal(await page.locator(`#m${m}-${stage}`).isVisible(),true);
        assert.equal(await page.locator('.stage-panel:visible').count(),1);
        checks.push(`m${m}-${stage}`);
      }
    }
    await page.locator('[data-milestone="m3"]').click();
    await page.locator('#m3-proposal-tab').click();
    await page.locator('#m3-proposal').waitFor({state:'visible'});
    await page.locator('#m3-proposal .image-button').first().click();
    assert.equal(await page.locator('#image-viewer').isVisible(),true);
    await page.locator('#actual-image').click();
    const full=await page.locator('#viewer-image').evaluate(image=>({width:image.getBoundingClientRect().width,natural:image.naturalWidth}));
    assert.equal(full.width,full.natural);
    assert.equal(full.natural,3360);
    await page.screenshot({path:path.join(output,'diagram-full-size.png')});
    await page.locator('#fit-image').click();
    await page.screenshot({path:path.join(output,'diagram-fit.png')});
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#image-viewer').isVisible(),false);
    await page.locator('#m3-prompt-tab').click();
    await page.locator('#m3-prompt [data-copy]').click();
    await page.waitForFunction(()=>/Copied|Selected/.test(document.querySelector('#m3-prompt [data-copy]').textContent));
    assert.match(await page.locator('#m3-prompt [data-copy]').innerText(),/Copied|Selected/);
    await page.locator('#m3-prompt-tab').focus();
    await page.keyboard.press('ArrowRight');
    await page.locator('#m3-proposal').waitFor({state:'visible'});
    assert.equal(await page.locator('#m3-proposal-tab').getAttribute('aria-selected'),'true');
    await page.evaluate(()=>window.scrollTo(0,0));
    await page.screenshot({path:path.join(output,'desktop-proposal.png'),fullPage:false});
    await page.setViewportSize({width:390,height:844});
    await page.locator('[data-milestone="m2"]').click();
    await page.locator('#m2-proposal-tab').click();
    await page.locator('#m2-proposal').waitFor({state:'visible'});
    await page.evaluate(()=>window.scrollTo(0,0));
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Mobile page has horizontal overflow');
    await page.screenshot({path:path.join(output,'mobile-proposal.png'),fullPage:false});
    await page.reload();
    assert.equal(await page.locator('#m2-proposal').isVisible(),true);
    assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
    const result={result:'passed',offline:true,entry:'file://.../docs/walkthrough/index.html',stage_checks:checks.length,all_images_decoded:true,full_size_figure_width:full.natural,prompt_copy:'copied or selected fallback',keyboard_tabs:true,escape_closes_viewer:true,mobile_width:390,mobile_horizontal_overflow:false,external_requests:requests,page_errors:errors,screenshots_directory:output};
    await fs.writeFile(path.join(__dirname,'browser-verification.json'),JSON.stringify(result,null,2)+'\n');
    console.log(JSON.stringify(result,null,2));
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
