import { chromium } from 'playwright'

const base = process.env.APP_URL || 'http://localhost:8000'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
async function as(user, tool) {
  await page.goto(base)
  await page.evaluate(([u, t]) => { localStorage.setItem('user', u); localStorage.setItem('tool', t) }, [user, tool])
  await page.goto(base)
  await page.waitForSelector('tbody tr')
  await page.waitForTimeout(400)
}
await as('marcus', 'kyc')
await page.screenshot({ path: 'docs/screens/07-kyc-lean-rows.png' })
await page.click('tbody tr:nth-child(1)')
await page.waitForTimeout(800)
await page.screenshot({ path: 'docs/screens/07b-kyc-detail-actions.png' })
await as('sofia', 'refunds')
await page.screenshot({ path: 'docs/screens/08-refunds-lean-rows.png' })
await as('lin', 'flags')
await page.screenshot({ path: 'docs/screens/09-flags-lean-rows.png' })
await browser.close()
