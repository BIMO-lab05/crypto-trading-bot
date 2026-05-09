#!/usr/bin/env node
/**
 * Frontend smoke test using Playwright (vanilla node, no test runner).
 *
 * Visits each route in light + dark, on desktop (1366x900) and mobile (375x812),
 * captures: HTTP status, title, console errors/warnings, network 4xx/5xx,
 * stuck "Loading..." text, viewport screenshots, and a real-data check
 * (looks for $, %, SOL/BNB/ADA, ISO timestamps).
 *
 * Usage: node scripts/frontend_smoke.mjs
 */

import playwright from '/mnt/d/Bimo_max/node_modules/playwright/index.js';
const { chromium } = playwright;
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';

const BASE = 'http://localhost:3000';
const ROUTES = ['/', '/phase1', '/phase3', '/performance', '/settings'];
const VIEWPORTS = [
  { name: 'desktop', width: 1366, height: 900 },
  { name: 'mobile', width: 375, height: 812 },
];
const THEMES = ['light', 'dark'];
const SCREENSHOT_DIR = resolve('/mnt/d/Bimo_max/crypto-trading-bot/scripts/screenshots');
const STUCK_LOADING_WAIT_MS = 8000;

await mkdir(SCREENSHOT_DIR, { recursive: true });

function realDataCheck(text) {
  const findings = {
    dollar: /\$\s?[\d,]+(\.\d+)?/.test(text),
    percent: /-?\d+(\.\d+)?\s?%/.test(text),
    symbols: /\b(SOL|BNB|ADA)(USDT|\/USDT|\b)/.test(text),
    timestamp:
      /\d{4}-\d{2}-\d{2}/.test(text) ||
      /\b\d{1,2}:\d{2}(:\d{2})?\b/.test(text),
  };
  findings.score = Object.values(findings).filter(Boolean).length;
  return findings;
}

async function detectStuckLoading(page) {
  // Wait briefly, then check for visible "Loading..." text after 8s.
  await page.waitForTimeout(STUCK_LOADING_WAIT_MS);
  const stuck = await page
    .locator('text=/Loading/i')
    .filter({ hasText: /Loading/i })
    .all();
  const visible = [];
  for (const loc of stuck) {
    try {
      if (await loc.isVisible()) visible.push((await loc.textContent())?.trim() || 'Loading');
    } catch (_) {}
  }
  return visible;
}

// (theme setting is now done inline via addInitScript + post-mount evaluate)

async function runOne(browser, route, theme, viewport) {
  const ctx = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    userAgent:
      viewport.name === 'mobile'
        ? 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'
        : undefined,
  });
  const page = await ctx.newPage();

  const consoleErrors = [];
  const consoleWarnings = [];
  const networkFailures = [];

  page.on('console', (msg) => {
    const t = msg.type();
    if (t === 'error') consoleErrors.push(msg.text());
    else if (t === 'warning') consoleWarnings.push(msg.text());
  });
  page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`));
  page.on('response', (resp) => {
    const s = resp.status();
    if (s >= 400) {
      networkFailures.push(`${s} ${resp.request().method()} ${resp.url()}`);
    }
  });

  // Use addInitScript so localStorage is set before any page script runs on
  // every navigation (avoids races with React mount writing to localStorage).
  await ctx.addInitScript((t) => {
    try {
      window.localStorage.setItem('theme', t);
    } catch (_) {}
  }, theme);

  let resp = null;
  let httpStatus = null;
  try {
    resp = await page.goto(`${BASE}${route}`, { waitUntil: 'domcontentloaded', timeout: 20000 });
  } catch (e) {
    consoleErrors.push(`goto error: ${e.message}`);
  }
  if (resp) httpStatus = resp.status();

  // Apply theme to <html> class after mount (best-effort)
  try {
    await page.evaluate((t) => {
      try {
        localStorage.setItem('theme', t);
        const root = document.documentElement;
        if (t === 'dark') root.classList.add('dark');
        else root.classList.remove('dark');
      } catch (_) {}
    }, theme);
  } catch (_) {}

  let title = '';
  try {
    title = await page.title();
  } catch (_) {}

  // Wait for network idle-ish before reading text.
  try {
    await page.waitForLoadState('networkidle', { timeout: 7000 });
  } catch (_) {}

  const stuckLoading = await detectStuckLoading(page);

  let bodyText = '';
  try {
    bodyText = (await page.locator('body').innerText()) || '';
  } catch (_) {}
  const data = realDataCheck(bodyText);

  // Test theme toggle if present (only run once per route at desktop)
  let themeToggleClicked = false;
  if (viewport.name === 'desktop' && theme === 'light') {
    const toggle = page.locator('button[aria-label*="mode" i], button[aria-label*="theme" i]').first();
    try {
      if (await toggle.count()) {
        await toggle.click({ timeout: 2000 });
        themeToggleClicked = true;
        await page.waitForTimeout(400);
      }
    } catch (_) {}
    // Restore requested theme after toggling
    try {
      await page.evaluate((t) => {
        localStorage.setItem('theme', t);
        const root = document.documentElement;
        if (t === 'dark') root.classList.add('dark');
        else root.classList.remove('dark');
      }, theme);
    } catch (_) {}
  }

  const safeRoute = route === '/' ? 'root' : route.replace(/^\//, '').replace(/\//g, '-');
  const shotPath = resolve(SCREENSHOT_DIR, `${safeRoute}-${theme}-${viewport.name}.png`);
  try {
    await page.screenshot({ path: shotPath, fullPage: false });
  } catch (e) {
    consoleErrors.push(`screenshot error: ${e.message}`);
  }

  await ctx.close();
  return {
    route,
    theme,
    viewport: viewport.name,
    httpStatus,
    title,
    consoleErrors,
    consoleWarnings,
    networkFailures,
    stuckLoading,
    realData: data,
    bodyTextLen: bodyText.length,
    themeToggleClicked,
    screenshot: shotPath,
  };
}

const browser = await chromium.launch({ headless: true });
const results = [];

for (const route of ROUTES) {
  for (const theme of THEMES) {
    for (const vp of VIEWPORTS) {
      process.stderr.write(`[run] ${route} theme=${theme} vp=${vp.name}\n`);
      try {
        const r = await runOne(browser, route, theme, vp);
        results.push(r);
      } catch (e) {
        results.push({
          route,
          theme,
          viewport: vp.name,
          fatal: e.message,
        });
      }
    }
  }
}

await browser.close();

// Compact summary
const summary = results.map((r) => {
  if (r.fatal) return { ...r };
  return {
    route: r.route,
    theme: r.theme,
    vp: r.viewport,
    status: r.httpStatus,
    title: r.title,
    errs: r.consoleErrors.length,
    warns: r.consoleWarnings.length,
    netFail: r.networkFailures.length,
    stuck: r.stuckLoading.length,
    dataScore: r.realData.score,
    bodyLen: r.bodyTextLen,
    toggle: r.themeToggleClicked,
  };
});
console.log('===SUMMARY===');
console.log(JSON.stringify(summary, null, 2));
console.log('===DETAIL===');
console.log(JSON.stringify(results, null, 2));
