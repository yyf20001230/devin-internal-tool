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
await page.hover('tbody tr:nth-child(2)')
await page.waitForTimeout(200)
await page.screenshot({ path: 'docs/screens/07-kyc-lean-rows-quick-actions.png' })
await as('sofia', 'refunds')
await page.hover('tbody tr:nth-child(1)')
await page.waitForTimeout(200)
await page.screenshot({ path: 'docs/screens/08-refunds-lean-rows.png' })
await as('lin', 'flags')
await page.hover('tbody tr:nth-child(1)')
await page.waitForTimeout(200)
await page.screenshot({ path: 'docs/screens/09-flags-quick-actions.png' })
await browser.close()
