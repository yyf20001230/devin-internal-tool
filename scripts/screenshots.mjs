// Drives the running app over Chrome DevTools Protocol and saves screenshots to docs/screens/.
// Usage: node scripts/screenshots.mjs  (needs the API on :8000 and vite on :5173)
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const base = process.env.APP_URL || 'http://localhost:5173'
mkdirSync('docs/screens', { recursive: true })
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })

async function as(user, tool) {
  await page.goto(base)
  await page.evaluate(([u, t]) => { localStorage.setItem('user', u); localStorage.setItem('tool', t) }, [user, tool])
  await page.goto(base)
  await page.waitForSelector('tbody tr')
  await page.waitForTimeout(400)
}

await as('priya', 'kyc')
await page.screenshot({ path: 'docs/screens/01-kyc-analyst.png' })

await as('marcus', 'kyc')
await page.dblclick('tbody tr:first-child')
await page.waitForSelector('.pane')
await page.waitForTimeout(300)
await page.screenshot({ path: 'docs/screens/02-kyc-lead-record-pane.png' })

await as('sofia', 'refunds')
await page.screenshot({ path: 'docs/screens/03-refunds-ops.png' })

await as('dan', 'refunds')
await page.selectOption('.titlebar select', 'large')
await page.waitForTimeout(500)
await page.click('tbody tr:first-child')
await page.screenshot({ path: 'docs/screens/04-refunds-finance-large.png' })

await as('amara', 'flags')
await page.click('tbody tr:first-child')
await page.dblclick('tbody tr:first-child')
await page.waitForSelector('.pane')
await page.waitForTimeout(300)
await page.screenshot({ path: 'docs/screens/05-flags-release-manager.png' })

await as('dan', 'chargebacks')
await page.selectOption('.titlebar select', 'due48')
await page.waitForTimeout(500)
await page.screenshot({ path: 'docs/screens/06-chargebacks-4th-tool.png' })

await as('auditor', 'refunds')
await page.screenshot({ path: 'docs/screens/07-refunds-readonly-auditor.png' })

await browser.close()
console.log('done')
