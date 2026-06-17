import { expect, test } from '@playwright/test';

/*
 * Phase 11 — daily-user production readiness validation.
 *
 * This is the baseline harness. It only checks that the WebUI loads and
 * passive navigation works.  No analysis is submitted, no LLM is called,
 * no live provider is invoked, and no notification is triggered.
 *
 * Allowed Phase 11 symbols (TW + US only):
 *   TW: 2330, 2454
 *   US: AAPL, NVDA
 *
 * Explicitly excluded markets:
 *   A-share (CN), HK, crypto, forex, commodities, AlphaSift
 */

// Reserved for Phase 11.2+ daily journeys.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const PHASE11_SYMBOLS = {
  tw: ['2330', '2454'] as const,
  us: ['AAPL', 'NVDA'] as const,
} as const;

test.describe('Phase 11 daily-user baseline', () => {
  test('app shell loads and renders home page', async ({ page }) => {
    // Navigate to login – the first page an unauthenticated user sees
    await page.goto('/login');
    await page.waitForLoadState('networkidle');

    // Branding should be visible
    await expect(page.getByText('DAILY STOCK').first()).toBeVisible();
    await expect(page.getByText('Analysis Engine')).toBeVisible();

    // Password form should render (auth is enabled by default)
    await expect(page.locator('#password')).toBeVisible();
    await expect(
      page.getByRole('button', { name: /授权进入工作台|完成设置并登录/ })
    ).toBeVisible();

    // No critical console errors so far
    // (we do NOT assert console messages here to keep the test simple;
    //  Phase 11.3 will add explicit console/network capture.)
  });

  test('login page has no 500 errors from passive API calls', async ({ page }) => {
    // Track responses during passive navigation
    const serverErrors: string[] = [];

    page.on('response', (response) => {
      if (response.status() >= 500) {
        serverErrors.push(`${response.status()} ${response.url()}`);
      }
    });

    await page.goto('/login');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);

    // No 5xx responses during page load
    expect(serverErrors).toEqual([]);
  });
});
