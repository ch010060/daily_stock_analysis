import { expect, type Page, test } from '@playwright/test';
import { expectNoHorizontalOverflow } from './helpers/layout';

const MOBILE_VIEWPORTS = [
  { name: 'mobile-360', width: 360, height: 740 },
  { name: 'mobile-390', width: 390, height: 844 },
  { name: 'mobile-landscape', width: 667, height: 375 },
];

const stockHistoryItem = {
  id: 101,
  query_id: 'q-mobile-msft',
  stock_code: 'MSFT',
  stock_name: 'Microsoft Corporation',
  report_type: 'detailed',
  trend_prediction: '震盪偏多',
  analysis_summary: '測試用行動版報告摘要',
  sentiment_score: 61,
  operation_advice: '觀察',
  current_price: 505.2,
  change_pct: 0.8,
  created_at: '2026-06-29T12:00:00Z',
};

const stockReport = {
  meta: {
    id: 101,
    query_id: 'q-mobile-msft',
    stock_code: 'MSFT',
    stock_name: 'Microsoft Corporation',
    market: 'US',
    exchange: 'NASDAQ',
    google_finance_exchange: 'NASDAQ',
    exchange_source: 'fixture',
    instrument_type: 'stock',
    report_type: 'detailed',
    report_language: 'zh_TW',
    created_at: '2026-06-29T12:00:00Z',
    current_price: 505.2,
    change_pct: 0.8,
  },
  summary: {
    analysis_summary: '測試用行動版報告摘要',
    operation_advice: '觀察',
    trend_prediction: '震盪偏多',
    sentiment_score: 61,
    sentiment_label: '樂觀',
  },
  strategy: {
    ideal_buy: '500',
    secondary_buy: '490',
    stop_loss: '470',
    take_profit: '540',
  },
  details: {
    raw_result: {
      instrument_type: 'stock',
      current_price: 505.2,
      change_pct: 0.8,
      support_level: 490,
      resistance_level: 540,
      market_fear_index_snapshot: {
        market: 'us',
        kind: 'vix',
        label: 'VIX',
        value: 17.2,
        as_of: '2026-06-29',
        source: 'yfinance',
        status: 'normal',
      },
      multi_period_trend_snapshot: {
        source: 'fixture',
        as_of: '2026-06-29',
        periods: [
          { label: '1D', change_pct: 0.8, trend_status: 'up' },
          { label: '1M', change_pct: 3.2, trend_status: 'up' },
        ],
      },
    },
  },
};

const klineRows = [
  { date: '2026-06-24', open: 498, high: 504, low: 496, close: 502, volume: 21000000 },
  { date: '2026-06-25', open: 502, high: 508, low: 500, close: 506, volume: 22000000 },
  { date: '2026-06-26', open: 506, high: 509, low: 501, close: 503, volume: 21500000 },
  { date: '2026-06-29', open: 503, high: 511, low: 502, close: 509, volume: 23000000 },
];

async function setupDsaApiMocks(page: Page): Promise<void> {
  await page.addInitScript(() => {
    class MockEventSource extends EventTarget {
      static readonly CONNECTING = 0;
      static readonly OPEN = 1;
      static readonly CLOSED = 2;
      readonly url: string;
      readyState = MockEventSource.OPEN;
      withCredentials = false;
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;

      constructor(url: string) {
        super();
        this.url = url;
        window.setTimeout(() => {
          const event = new Event('open');
          this.dispatchEvent(event);
          this.onopen?.(event);
        }, 0);
      }

      close() {
        this.readyState = MockEventSource.CLOSED;
      }
    }

    window.EventSource = MockEventSource as typeof EventSource;
  });

  await page.route('**/api/v1/**', async (route) => {
    const requestUrl = new URL(route.request().url());
    const path = requestUrl.pathname;

    if (path === '/api/v1/auth/status') {
      await route.fulfill({
        json: {
          authEnabled: false,
          loggedIn: true,
          passwordSet: false,
          passwordChangeable: false,
          setupState: 'no_password',
        },
      });
      return;
    }

    if (path === '/api/v1/system/config/setup/status') {
      await route.fulfill({
        json: {
          is_complete: true,
          checks: [],
        },
      });
      return;
    }

    if (path === '/api/v1/agent/skills') {
      await route.fulfill({ json: { skills: [], default_skill_id: '' } });
      return;
    }

    if (path === '/api/v1/analysis/tasks') {
      await route.fulfill({ json: { total: 0, pending: 0, processing: 0, tasks: [] } });
      return;
    }

    if (path === '/api/v1/stocks/watchlist') {
      await route.fulfill({ json: { stock_codes: [] } });
      return;
    }

    if (path === '/api/v1/history/stocks') {
      await route.fulfill({
        json: {
          total: 1,
          items: [
            {
              id: 101,
              stock_code: 'MSFT',
              stock_name: 'Microsoft Corporation',
              report_type: 'detailed',
              analysis_count: 1,
              last_analysis_time: '2026-06-29T12:00:00Z',
              sentiment_score: 61,
              operation_advice: '觀察',
            },
          ],
        },
      });
      return;
    }

    if (path === '/api/v1/history/') {
      const stockCode = requestUrl.searchParams.get('stock_code');
      const reportType = requestUrl.searchParams.get('report_type');
      await route.fulfill({
        json: stockCode === 'MARKET' || reportType === 'market_review'
          ? { total: 0, page: 1, limit: 10, items: [] }
          : { total: 1, page: 1, limit: 20, items: [stockHistoryItem] },
      });
      return;
    }

    if (path === '/api/v1/history/101') {
      await route.fulfill({ json: stockReport });
      return;
    }

    if (path === '/api/v1/history/101/markdown') {
      await route.fulfill({
        json: {
          content: [
            '# Microsoft Corporation 行動版報告',
            '',
            '## 核心摘要',
            '',
            '這是 Playwright 行動版版面測試用報告。',
          ].join('\n'),
        },
      });
      return;
    }

    if (path === '/api/v1/history/101/kline') {
      await route.fulfill({
        json: {
          history_id: 101,
          symbol: 'MSFT',
          market: 'us',
          instrument_type: 'stock',
          range: requestUrl.searchParams.get('range') ?? '3m',
          granularity: 'daily',
          source: 'fixture',
          source_type: 'db_cache',
          as_of: '2026-06-29',
          rows: klineRows,
        },
      });
      return;
    }

    if (path === '/api/v1/history/101/news') {
      await route.fulfill({ json: { total: 0, items: [] } });
      return;
    }

    if (path === '/api/v1/history/101/diagnostics') {
      await route.fulfill({
        json: {
          status: 'normal',
          status_label: '正常',
          reason: 'fixture',
          components: {},
          copy_text: '',
        },
      });
      return;
    }

    if (path === '/api/v1/finews/latest') {
      await route.fulfill({
        json: {
          source: 'finews',
          source_url: 'https://finews.elsetech.app/',
          report_date: '2026-06-29',
          source_updated_at: '2026-06-29T08:00:00Z',
          fetched_at: '2026-06-29T09:00:00Z',
          stale: false,
          fetch_error: null,
          language_original: 'zh-CN',
          language_rendered: 'zh-TW',
          external_links: [
            { title: '測試新聞', url: 'https://example.com/news' },
            { title: 'SPY', url: 'https://finance.yahoo.com/quote/SPY' },
          ],
          section_links: {
            after_market_summary: [],
            major_news: [{ title: '測試新聞', url: 'https://example.com/news' }],
            market_temperature: [],
            major_indices: [{ title: 'SPY', url: 'https://finance.yahoo.com/quote/SPY' }],
            major_stocks: [],
            treasury_yields: [],
            fx: [],
          },
          sections: {
            after_market_summary: ['美股盤後摘要測試資料。'],
            major_news: ['測試新聞', 'Fixture · 2026-06-29', '測試新聞摘要。'],
            market_temperature: [],
            major_indices: ['S&P 500', 'SPY', '6000.00', '+0.12%'],
            major_stocks: [],
            treasury_yields: [],
            fx: [],
          },
        },
      });
      return;
    }

    await route.fulfill({ json: {} });
  });
}

async function visibleCount(locator: ReturnType<Page['getByRole']>): Promise<number> {
  const count = await locator.count();
  let visible = 0;
  for (let index = 0; index < count; index += 1) {
    if (await locator.nth(index).isVisible()) {
      visible += 1;
    }
  }
  return visible;
}

test.describe('mobile RWD baseline', () => {
  test.beforeEach(async ({ page }) => {
    await setupDsaApiMocks(page);
  });

  for (const viewport of MOBILE_VIEWPORTS) {
    test(`home shell has one mobile navigation trigger and no horizontal overflow at ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto('/');

      await expect(page.getByRole('heading', { name: /Microsoft Corporation|開始分析/ }).first()).toBeVisible();
      const menuButtons = page.getByRole('button', { name: '開啟導航選單' });
      await expect(menuButtons.first()).toBeVisible();
      expect(await visibleCount(menuButtons)).toBe(1);

      await menuButtons.first().click();
      await expect(page.getByRole('dialog', { name: '導航選單' })).toBeVisible();
      await page.getByRole('button', { name: /關閉(?:導航選單|抽屜)/ }).click();
      await expect(page.getByRole('dialog', { name: '導航選單' })).not.toBeVisible();
      await expectNoHorizontalOverflow(page);
    });
  }

  test('full report K-line section fits mobile width', async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 });
    await page.goto('/');

    await expect(page.getByRole('heading', { name: /Microsoft Corporation/ })).toBeVisible();
    await page.getByRole('button', { name: '完整分析報告' }).click();
    const klineBlock = page.getByTestId('kline-chart-block');
    await expect(klineBlock).toBeVisible();

    const metrics = await klineBlock.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      const parentRect = element.parentElement?.getBoundingClientRect();
      return {
        viewportWidth: window.innerWidth,
        left: rect.left,
        right: rect.right,
        width: rect.width,
        parentWidth: parentRect?.width ?? 0,
      };
    });

    expect(metrics.left).toBeGreaterThanOrEqual(-1);
    expect(metrics.right).toBeLessThanOrEqual(metrics.viewportWidth + 1);
    expect(metrics.width).toBeLessThanOrEqual(metrics.parentWidth + 1);

    const chartSurfaceMetrics = await page.getByTestId('kline-chart-canvas-host').evaluate((host) => {
      const hostRect = host.getBoundingClientRect();
      const canvas = host.querySelector('canvas');
      const canvasRect = canvas?.getBoundingClientRect();
      return {
        hostWidth: hostRect.width,
        canvasWidth: canvasRect?.width ?? 0,
      };
    });

    expect(chartSurfaceMetrics.canvasWidth).toBeLessThanOrEqual(chartSurfaceMetrics.hostWidth + 1);
    await expectNoHorizontalOverflow(page);
  });

  test('print/PDF full report K-line section fits mobile width', async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 });
    await page.goto('/reports/101/print?pdf=1');

    const klineBlock = page.getByTestId('kline-chart-block');
    await expect(klineBlock).toBeVisible();

    const chartSurfaceMetrics = await page.getByTestId('kline-chart-canvas-host').evaluate((host) => {
      const hostRect = host.getBoundingClientRect();
      const canvas = host.querySelector('canvas');
      const canvasRect = canvas?.getBoundingClientRect();
      return {
        viewportWidth: window.innerWidth,
        hostLeft: hostRect.left,
        hostRight: hostRect.right,
        hostWidth: hostRect.width,
        canvasWidth: canvasRect?.width ?? 0,
      };
    });

    expect(chartSurfaceMetrics.hostLeft).toBeGreaterThanOrEqual(-1);
    expect(chartSurfaceMetrics.hostRight).toBeLessThanOrEqual(chartSurfaceMetrics.viewportWidth + 1);
    expect(chartSurfaceMetrics.canvasWidth).toBeLessThanOrEqual(chartSurfaceMetrics.hostWidth + 1);
    await expectNoHorizontalOverflow(page);
  });

  test('critical mobile routes load without document overflow', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });

    await page.goto('/');
    await expect(page.getByRole('button', { name: '台股日報' })).toBeVisible();
    await expect(page.getByRole('button', { name: '美股日報' })).toBeVisible();
    await expectNoHorizontalOverflow(page);

    await page.goto('/finews');
    await expect(page.getByRole('heading', { name: '美股日報' })).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });
});
