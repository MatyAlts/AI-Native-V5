#!/usr/bin/env node
import { chromium } from "playwright";
import { mkdir } from "fs/promises";

const targets = [
  { name: "web-admin",   url: "http://localhost:5173/" },
  { name: "web-teacher", url: "http://localhost:5174/" },
  { name: "web-student", url: "http://localhost:5175/" },
];

await mkdir(".dev-logs/screenshots", { recursive: true });

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });

for (const t of targets) {
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") errors.push(`console.error: ${m.text()}`); });
  try {
    await page.goto(t.url, { waitUntil: "networkidle", timeout: 15000 });
    await page.waitForTimeout(1500);
    const out = `.dev-logs/screenshots/${t.name}.png`;
    await page.screenshot({ path: out, fullPage: true });
    const title = await page.title();
    console.log(`OK  ${t.name}  title="${title}"  ${out}`);
    if (errors.length) {
      console.log(`    errors:`);
      errors.forEach((e) => console.log(`      - ${e}`));
    }
  } catch (err) {
    console.log(`FAIL ${t.name}  ${err.message}`);
  } finally {
    await page.close();
  }
}

await browser.close();
