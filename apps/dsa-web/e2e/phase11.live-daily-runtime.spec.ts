import { expect, test, type Page } from '@playwright/test';

const smokePassword = process.env.DSA_WEB_SMOKE_PASSWORD;
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const LIVE_SYMBOLS = { required: [{ market: 'TW', symbol: '2330' }, { market: 'US', symbol: 'AAPL' }] } as const;

async function login(page: Page) {
  test.skip(!smokePassword, 'DSA_WEB_SMOKE_PASSWORD required.');
  test.skip(process.env.PHASE11_LIVE_RUNTIME !== 'true', 'PHASE11_LIVE_RUNTIME=true required.');
  await page.goto('/login');
  await page.waitForLoadState('networkidle');
  const passwordInput = page.locator('#password');
  const submitButton = page.getByRole('button', { name: /授权进入工作台|完成设置并登录/ });
  await expect(passwordInput).toBeVisible({ timeout: 10_000 });
  await passwordInput.fill(smokePassword!);
  await expect(submitButton).toBeVisible();
  await Promise.all([
    page.waitForResponse((r) => r.url().includes('/api/v1/auth/login') && r.status() === 200, { timeout: 15_000 }),
    submitButton.click(),
  ]);
  await page.waitForURL('/', { timeout: 15_000 });
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);
}

async function openReport(page: Page, symbol: string) {
  await expect(page.getByText(symbol).first()).toBeVisible({ timeout: 15_000 });
  const historyItem = page.locator('.home-history-item').filter({ hasText: symbol }).first();
  await expect(historyItem).toBeVisible({ timeout: 5_000 });
  await historyItem.click();
  await page.waitForTimeout(1000);
  const detailedButton = page.getByRole('button', { name: '完整分析报告' });
  await expect(detailedButton).toBeVisible({ timeout: 5_000 });
  await detailedButton.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible({ timeout: 10_000 });
  const text = await dialog.textContent();
  expect(text).toBeTruthy();
  expect(text!.length).toBeGreaterThan(100);
  expect(text).not.toContain('Traceback');
  await page.keyboard.press('Escape');
}

test.describe('Phase 11.2 daily runtime UI verification', () => {
  test.setTimeout(600_000); // 10 min for full reports

  test('Home page shows history', async ({ page }) => {
    await login(page);
    await expect(page.getByText('2330').first()).toBeVisible({ timeout: 15_000 });
  });

  test('Open TW:2330 report from history', async ({ page }) => {
    await login(page);
    await openReport(page, '2330');
  });

  test('Open US:AAPL report from history', async ({ page }) => {
    await login(page);
    await openReport(page, 'AAPL');
  });

  test('Token usage dashboard loads', async ({ page }) => {
    await login(page);
    await page.getByRole('link', { name: '用量' }).click();
    await page.waitForLoadState('networkidle');
    await expect(page.locator('table').first()).toBeVisible({ timeout: 10_000 });
    const pageText = await page.textContent('body');
    expect(pageText).toBeTruthy();
    expect(pageText!.length).toBeGreaterThan(50);
  });
});
