import { expect, test, type Page } from '@playwright/test';

const smokePassword = process.env.DSA_WEB_SMOKE_PASSWORD;
const LIVE_AGENT_SMOKE_ENABLED = process.env.DSA_WEB_LIVE_AGENT_SMOKE === 'true';

async function login(page: Page) {
  test.skip(!smokePassword, 'Set DSA_WEB_SMOKE_PASSWORD to run authenticated smoke tests.');

  await page.goto('/login');
  await page.waitForLoadState('domcontentloaded');

  const passwordInput = page.locator('#password');
  const submitButton = page.getByRole('button', { name: /授權進入工作臺|完成設定並登入/ });
  const homeLink = page.getByRole('link', { name: '首頁' });

  const isAlreadyAuthenticated =
    page.url().endsWith('/') ||
    await homeLink.isVisible({ timeout: 2_000 }).catch(() => false);

  if (isAlreadyAuthenticated) {
    await page.waitForLoadState('domcontentloaded');
    return;
  }

  await expect(passwordInput).toBeVisible({ timeout: 10_000 });
  await passwordInput.fill(smokePassword!);
  await expect(submitButton).toBeVisible();

  await Promise.all([
    page.waitForResponse(
      (response) => response.url().includes('/api/v1/auth/login') && response.status() === 200,
      { timeout: 15_000 }
    ),
    submitButton.click(),
  ]);

  await page.waitForURL('/', { timeout: 15_000 });
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(1000);
}

test.describe('web smoke', () => {
  test('login page renders password form', async ({ page }) => {
    await page.goto('/login');
    await page.waitForLoadState('domcontentloaded');

    // Check for branding
    await expect(page.getByText('DAILY STOCK').first()).toBeVisible();
    await expect(page.getByText('Analysis Engine')).toBeVisible();

    // Check for password input
    await expect(page.locator('#password')).toBeVisible();

    // Check for submit button
    await expect(page.getByRole('button', { name: /授權進入工作臺|完成設定並登入/ })).toBeVisible();
  });

  test('home page shows analysis entry and history panel after login', async ({ page }) => {
    await login(page);

    const stockInput = page.getByPlaceholder('輸入股票程式碼或名稱，如 2330、AAPL');
    await expect(stockInput).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('link', { name: '首頁' })).toBeVisible();
    await expect(page.getByRole('link', { name: '問股' })).toBeVisible();
    await expect(page.getByText('歷史分析')).toBeVisible();

    await stockInput.fill('2330');
    const analyzeButton = page.getByRole('button', { name: '分析', exact: true });
    await expect(analyzeButton).toBeVisible();
  });

  test('chat page allows entering a question and starts a request', async ({ page }) => {
    test.skip(!LIVE_AGENT_SMOKE_ENABLED, 'live agent smoke requires DSA_WEB_LIVE_AGENT_SMOKE=true');
    await login(page);

    // Navigate to chat page by clicking the link
    await page.getByRole('link', { name: '問股' }).click();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    await expect(page.getByTestId('chat-workspace')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('chat-session-list-scroll')).toBeVisible();
    await expect(page.getByTestId('chat-message-scroll')).toBeVisible();

    const input = page.getByPlaceholder(/分析 2330/);
    await expect(input).toBeVisible({ timeout: 5000 });
    await expect(page.getByText('策略', { exact: true })).toBeVisible();

    const prompt = '請簡要分析 2330';
    await input.fill(prompt);
    await page.getByRole('button', { name: '傳送' }).click();

    await expect(page.locator('p').filter({ hasText: prompt }).last()).toBeVisible({ timeout: 5000 });
  });

  test('chat page uses accessible labels instead of native title attributes for key actions', async ({ page }) => {
    await login(page);

    await page.getByRole('link', { name: '問股' }).click();
    await page.waitForLoadState('domcontentloaded');

    const sendButton = page.getByRole('button', { name: '傳送' });
    const composer = page.getByPlaceholder(/分析 2330/);

    await expect(page.getByTestId('chat-workspace')).toBeVisible({ timeout: 10_000 });
    await expect(sendButton).toBeVisible({ timeout: 10_000 });
    await expect(composer).toBeVisible({ timeout: 10_000 });

    await expect(sendButton).not.toHaveAttribute('title', /.+/);
    await expect(composer).not.toHaveAttribute('title', /.+/);
  });

  test('mobile shell opens navigation drawer after login', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page);

    // Try to open navigation menu
    const menuButton = page.getByRole('button', { name: /開啟導航|選單/i });
    if (await menuButton.isVisible({ timeout: 2000 }).catch(() => false)) {
      await menuButton.click();
    }

    // Check if navigation is visible
    await expect(page.getByRole('link', { name: '回測' })).toBeVisible({ timeout: 5000 });
  });

  test('settings page renders title and save actions after login', async ({ page }) => {
    await login(page);

    // Navigate to settings page by clicking the link
    await page.getByRole('link', { name: '設定' }).click();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    // Use heading role for more precise selection
    await expect(page.getByRole('heading', { name: '系統設定' })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('button', { name: '重置' })).toBeVisible();
    await expect(page.getByRole('button', { name: /儲存配置/ })).toBeVisible();
  });

  test('backtest page renders filter controls after login', async ({ page }) => {
    await login(page);

    // Navigate to backtest page by clicking the link
    await page.getByRole('link', { name: '回測' }).click();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    // Check for filter controls
    const filterInput = page.getByPlaceholder('按股票程式碼篩選（留空表示全部）');
    await expect(filterInput).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole('button', { name: '篩選' })).toBeVisible();
    await expect(page.getByRole('button', { name: '執行回測' })).toBeVisible();
  });
});
