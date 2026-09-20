import { chromium } from '@playwright/test';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 900 } });
await p.goto('http://localhost:5000');
await p.waitForSelector('#root [data-testid="ranked-list"] button', { timeout: 20000 });
// Scrub the timeline to ~150 min so arrived contours show, then settle.
await p.evaluate(() => {
  const slider = document.querySelector('[data-testid="time-slider"]');
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  setter.call(slider, 150);
  slider.dispatchEvent(new Event('input', { bubbles: true }));
});
await p.waitForTimeout(2500);
await p.screenshot({ path: '../../docs/screenshot.png' });
await b.close();
