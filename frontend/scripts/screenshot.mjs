// Renders the app to docs/screenshot.png. Needs the Vite dev server up
// (`npm run dev`) and the API behind it; override with E2E_BASE_URL.
import { chromium } from "@playwright/test";

const url = process.env.E2E_BASE_URL ?? "http://localhost:5173";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 900 } });
await p.goto(url);
// A scenario without a recorded bundle simulates live, which takes minutes.
await p.waitForSelector('#root [data-testid="ranked-list"] button', { timeout: 180_000 });
// Scrub the timeline so arrived contours show, then let the map settle.
await p.evaluate(() => {
  const slider = document.querySelector('[data-testid="time-slider"]');
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  setter.call(slider, 600);
  slider.dispatchEvent(new Event("input", { bubbles: true }));
});
await p.waitForTimeout(3000);
await p.screenshot({ path: "../docs/screenshot.png" });
await b.close();
console.log("wrote docs/screenshot.png");
