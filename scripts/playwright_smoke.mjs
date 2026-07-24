import http from 'node:http';

const baseUrl = process.env.SMOKE_URL || 'http://127.0.0.1:5000/';

async function serverReachable(url) {
  return new Promise((resolve) => {
    const request = http.get(url, { timeout: 2500 }, (response) => {
      response.resume();
      response.on('end', () => resolve(response.statusCode >= 200 && response.statusCode < 400));
    });
    request.on('timeout', () => {
      request.destroy();
      resolve(false);
    });
    request.on('error', () => resolve(false));
  });
}

async function main() {
  if (!(await serverReachable(baseUrl))) {
    console.log(`Playwright smoke skipped: server is not reachable at ${baseUrl}`);
    return;
  }

  let chromium;
  try {
    ({ chromium } = await import('playwright'));
  } catch {
    console.log('Playwright smoke skipped: playwright package is not installed.');
    return;
  }

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
  try {
    const errors = [];
    page.on('console', (message) => {
      if (message.type() === 'error') errors.push(message.text());
    });
    page.on('pageerror', (error) => errors.push(error.message));

    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    await page.locator('#view-landing').waitFor({ state: 'attached', timeout: 5000 });
    await page.waitForFunction(() => (
      document.body.dataset.connectionStatus === 'online' &&
      document.body.dataset.stateStale === 'false'
    ), null, { timeout: 5000 });
    await page.locator('#btn-role-player').click();
    await page.locator('#view-player.active').waitFor({ state: 'attached', timeout: 5000 });
    await page.waitForFunction(() => (
      document.querySelectorAll('#board-pieces .piece').length > 0
    ), null, { timeout: 5000 });

    if (errors.length) {
      throw new Error(`Browser errors: ${errors.join(' | ')}`);
    }
    console.log('Playwright smoke passed.');
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
