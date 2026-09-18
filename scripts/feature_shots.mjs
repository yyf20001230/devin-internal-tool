// Five feature screenshots for the README, taken against a running instance.
// Usage: APP_URL=http://localhost:8080 node scripts/feature_shots.mjs
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const base = process.env.APP_URL || 'http://localhost:8000'
mkdirSync('docs/screens', { recursive: true })
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1500, height: 860 }, deviceScaleFactor: 1 })
const shot = (name) => page.screenshot({ path: `docs/screens/${name}.png` })
const settled = () => page.waitForFunction(() => !document.querySelector('.pane .ai')?.textContent?.includes('Summarising'), null, { timeout: 60000 })

async function as(user, tool) {
  await page.goto(base)
  await page.evaluate(([u, t]) => { localStorage.setItem('user', u); localStorage.setItem('tool', t) }, [user, tool])
  await page.goto(base)
  await page.waitForSelector('tbody tr')
  await page.waitForTimeout(400)
}

// 1. sign-in: personas + roles, boards scoped per role
await page.goto(base)
await page.evaluate(() => localStorage.clear())
await page.goto(base)
await page.waitForSelector('.signin')
await shot('f1-sign-in')

// 2. KYC board: lean grid + Summary tab (decisions + AI case summary)
await as('marcus', 'kyc')
await page.click('tbody tr:first-child')
await page.waitForSelector('.pane .ai')
await settled()
await page.waitForTimeout(400)
await shot('f2-kyc-summary-decisions')

// 3. Policy check tab: clause checks + ask-the-policy answer with citations
await page.click('.pane-tabs .view:has-text("Policy check")')
await page.waitForSelector('.ask-row input')
await page.fill('.ask-row input', 'can I approve without proof of address?')
await page.press('.ask-row input', 'Enter')
await page.waitForSelector('.ai-answer', { timeout: 60000 })
await page.waitForTimeout(400)
await shot('f3-kyc-policy-check-ask')

// 4. Refunds: ops approving a >1,000 refund → advisory warning modal (proceed anyway = audited override)
await as('sofia', 'refunds')
await page.click('th:has-text("Amount")')
await page.waitForTimeout(200)
await page.click('th:has-text("Amount")')
await page.waitForTimeout(300)
await page.click('tbody tr:first-child')
await page.waitForSelector('.pane .decisions')
await settled()
await page.click('.pane .decisions button:has-text("Approve")')
await page.waitForSelector('.modal')
await page.waitForTimeout(300)
await shot('f4-refund-policy-warning-modal')
await page.click('.modal .btn.secondary')

// 5. Feature flags: dashboard + UAT/PROD indicators, release-manager pane
await as('lin', 'flags')
await page.click('tbody tr:nth-child(2)')
await page.waitForSelector('.pane .ai')
await settled()
await page.waitForTimeout(400)
await shot('f5-flags-board')

await browser.close()
console.log('done')
