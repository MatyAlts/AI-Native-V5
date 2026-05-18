#!/usr/bin/env node
import { chromium } from "playwright";
import { mkdir } from "fs/promises";

const targets = [
  // web-admin — internal pages
  { name: "admin-universidades",  url: "http://localhost:5173/#/universidades" },
  { name: "admin-comisiones",     url: "http://localhost:5173/#/comisiones" },
  { name: "admin-bulk-import",    url: "http://localhost:5173/#/bulk-import" },
  { name: "admin-auditoria",      url: "http://localhost:5173/#/auditoria" },
  // web-teacher — try with comision query param
  { name: "teacher-progresion",   url: "http://localhost:5174/progression?comisionId=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" },
  { name: "teacher-tareas",       url: "http://localhost:5174/tareas-practicas?comisionId=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" },
  { name: "teacher-templates",    url: "http://localhost:5174/templates" },
  { name: "teacher-kappa",        url: "http://localhost:5174/kappa" },
  // web-student — try the comision selector with one selected
  // (we'll trigger select via click first)
];

await mkdir(".dev-logs/screenshots", { recursive: true });

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });

for (const t of targets) {
  const page = await ctx.newPage();
  try {
    await page.goto(t.url, { waitUntil: "networkidle", timeout: 15000 });
    await page.waitForTimeout(2000);
    const out = `.dev-logs/screenshots/${t.name}.png`;
    await page.screenshot({ path: out, fullPage: true });
    console.log(`OK  ${t.name}  ${out}`);
  } catch (err) {
    console.log(`FAIL ${t.name}  ${err.message}`);
  } finally {
    await page.close();
  }
}

// Web-student: click on selector and take a populated view
const stuPage = await ctx.newPage();
try {
  await stuPage.goto("http://localhost:5175/", { waitUntil: "networkidle", timeout: 15000 });
  await stuPage.waitForTimeout(1500);
  // try to select a comision via dropdown
  const select = await stuPage.$("select");
  if (select) {
    const options = await stuPage.$$eval("select option", (els) => els.map((e) => ({ value: e.value, text: e.textContent })));
    console.log("student selector options:", JSON.stringify(options));
    // pick first non-empty
    const target = options.find((o) => o.value && o.value.length > 0);
    if (target) {
      await stuPage.selectOption("select", target.value);
      await stuPage.waitForTimeout(2000);
    }
  }
  await stuPage.screenshot({ path: ".dev-logs/screenshots/student-with-comision.png", fullPage: true });
  console.log("OK  student-with-comision");
} catch (err) {
  console.log(`FAIL student-with-comision  ${err.message}`);
} finally {
  await stuPage.close();
}

await browser.close();
