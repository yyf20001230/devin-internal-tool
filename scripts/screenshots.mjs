// Drives the running app and saves screenshots to docs/screens/.
// Usage: APP_URL=http://localhost:8000 node scripts/screenshots.mjs
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const base = process.env.APP_URL || 'http://localhost:8000'
mkdirSync('docs/screens', { recursive: true })
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } })
const shot = (name) => page.screenshot({ path: `docs/screens/${name}.png` })

async function signOut() {
  await page.goto(base)
  await page.evaluate(() => localStorage.clear())
  await page.goto(base)
  await page.waitForSelector('.signin')
}
async function as(user, tool) {
  await page.goto(base)
  await page.evaluate(([u, t]) => { localStorage.setItem('user', u); localStorage.setItem('tool', t) }, [user, tool])
  await page.goto(base)
  await page.waitForSelector('tbody tr')
  await page.waitForTimeout(400)
}
const view = (id) => page.click(`.grid-wrap .view:has-text("${id}")`)

await signOut()
await shot('00-sign-in')

await as('priya', 'kyc')
await page.click('.avatar-btn')
await page.waitForSelector('.menu')
await shot('01-kyc-analyst-profile-menu')
await page.keyboard.press('Escape')
await page.mouse.click(600, 300)

await page.click('tbody tr:first-child')
await page.waitForSelector('.pane .ai')
await page.waitForFunction(() => !document.querySelector('.pane .ai')?.textContent?.includes('Summarising'), null, { timeout: 45000 })
await page.waitForTimeout(500)
await shot('02-kyc-case-pane-ai-summary-policy')

await page.fill('.ask input', 'high risk cases missing proof of address')
await page.press('.ask input', 'Enter')
await page.waitForSelector('.nl-explain')
await page.waitForTimeout(400)
await shot('03-kyc-natural-language-filter')

await as('marcus', 'kyc')
await page.click('.ai-btn')
await page.waitForSelector('.report')
await page.waitForTimeout(500)
await shot('04-kyc-devin-policy-review-run')
await page.click('.rep-item.red .link')
await page.waitForSelector('.ai-decision')
await page.$$eval('.pane .chk-row', els => els[0]?.click())
await page.waitForTimeout(400)
await shot('04b-kyc-policy-evidence-in-record')
page.once('dialog', d => d.accept('False positive - applicant is a verified UK sole trader'))
await page.click('.ai-decision button:has-text("Reset AI decision")')
await page.waitForSelector('.toast')
await page.waitForTimeout(300)
await shot('04c-kyc-after-reset-ai-decision')

await as('sofia', 'refunds')
await page.click('th:has-text("Amount")')
await page.waitForTimeout(200)
await shot('05-refunds-ops-sorted-by-amount')

await as('dan', 'refunds')
await view('Over 1,000')
await page.waitForTimeout(500)
await page.click('tbody tr:first-child')
await page.waitForSelector('.pane .ai')
await page.waitForFunction(() => !document.querySelector('.pane .ai')?.textContent?.includes('Summarising'), null, { timeout: 45000 })
await page.waitForTimeout(400)
await shot('06-refunds-finance-large-pane')

await as('amara', 'flags')
await page.click('tbody tr:first-child')
await page.waitForSelector('.pane')
await page.waitForTimeout(300)
await shot('07-flags-release-manager')

await as('dan', 'chargebacks')
await shot('08-chargebacks-4th-tool')

await as('auditor', 'refunds')
await shot('09-refunds-readonly-auditor')

await browser.close()
console.log('done')
