// Capture actual service responses. Requires Playwright and an installed Chromium.
// Usage: node capture_browser.cjs BASE_URL RECORDING_DIRECTORY [RESERVATION_ID ...]
const {chromium} = require('playwright');
const fs = require('node:fs/promises');
const path = require('node:path');

(async () => {
  const [base, directory, ...ids] = process.argv.slice(2);
  const browser = await chromium.launch({headless: true, ...(process.env.CHROME_PATH ? {executablePath: process.env.CHROME_PATH} : {})});
  const captures = [];
  try {
    const page = await browser.newPage({viewport: {width: 1360, height: 1000}, colorScheme: 'light'});
    const targets = [['screening', '/screening'], ...ids.map((id, i) => [`reservation-${i + 1}`, `/reservations/${id}`])];
    for (const [name, route] of targets) {
      const response = await page.goto(base + route);
      if (response.status() !== 200) throw new Error(`${route}: ${response.status()}`);
      const file = `assets/${name}.png`;
      await page.screenshot({path: path.join(directory, file), fullPage: true});
      captures.push({file, route, status: response.status(), kind: 'browser screenshot of working JSON API', body: await response.json()});
    }
    await fs.writeFile(path.join(directory, 'screenshots.json'), JSON.stringify({viewport: {width:1360,height:1000}, captures}, null, 2) + '\n');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
