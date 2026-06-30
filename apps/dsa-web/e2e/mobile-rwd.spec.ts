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

const routeSmokeTargets = [
  { name: 'home', path: '/', text: /台股日報|開始分析/ },
  { name: 'chat', path: '/chat', text: /問股/ },
  { name: 'portfolio', path: '/portfolio', text: /持股管理/ },
  { name: 'screening', path: '/screening', text: /AlphaSift 選股發現/ },
  { name: 'backtest', path: '/backtest', text: /執行回測|暫無結果/ },
  { name: 'alerts', path: '/alerts', text: /警告中心/ },
  { name: 'usage', path: '/usage', text: /用量|Token|呼叫/ },
  { name: 'finews', path: '/finews', text: /美股日報/ },
  { name: 'settings', path: '/settings', text: /系統設定/ },
  { name: 'print-report', path: '/reports/101/print?pdf=1', text: /Microsoft Corporation|行動版報告/ },
  { name: 'login-boundary', path: '/login', text: /台股日報|開始分析/ },
  { name: 'not-found', path: '/not-a-real-route', text: /頁面未找到/ },
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
          ready_for_smoke: true,
          required_missing_keys: [],
          checks: [],
        },
      });
      return;
    }

    if (path === '/api/v1/system/config') {
      const configItems = [
        ['BASE_URL', 'https://fixture.local', 'base', '基礎網址'],
        ['DATA_PROVIDER', 'finmind', 'data_source', '資料來源'],
        ['DEFAULT_MODEL', 'gpt-mobile-fixture', 'ai_model', '預設模型'],
        ['NOTIFY_ENABLED', 'false', 'notification', '通知開關'],
        ['SYSTEM_LOCALE', 'zh_TW', 'system', '系統語系'],
        ['AGENT_ENABLED', 'true', 'agent', 'Agent 開關'],
        ['BACKTEST_WINDOW_DAYS', '5', 'backtest', '回測視窗'],
      ];

      await route.fulfill({
        json: {
          config_version: 'mobile-rwd-fixture',
          mask_token: '******',
          updated_at: '2026-06-29T09:00:00Z',
          items: configItems.map(([key, value, category, title], index) => ({
            key,
            value,
            raw_value_exists: true,
            is_masked: false,
            schema: {
              key,
              title,
              description: `${title}行動版測試欄位`,
              category,
              data_type: key === 'BACKTEST_WINDOW_DAYS' ? 'integer' : 'string',
              ui_control: key === 'NOTIFY_ENABLED' || key === 'AGENT_ENABLED' ? 'switch' : 'text',
              is_sensitive: false,
              is_required: false,
              is_editable: true,
              options: [],
              validation: {},
              display_order: index + 1,
            },
          })),
        },
      });
      return;
    }

    if (path === '/api/v1/system/config/schema') {
      const categories = [
        ['base', '基礎設定'],
        ['data_source', '資料來源'],
        ['ai_model', 'AI 模型'],
        ['notification', '通知'],
        ['system', '系統'],
        ['agent', 'Agent'],
        ['backtest', '回測'],
      ].map(([category, title], index) => ({
        category,
        title,
        description: `${title}設定`,
        display_order: index + 1,
        fields: [
          {
            key: `${category.toUpperCase()}_MOBILE_FIXTURE`,
            title,
            description: `${title}行動版測試欄位`,
            category,
            data_type: 'string',
            ui_control: 'text',
            is_sensitive: false,
            is_required: false,
            is_editable: true,
            options: [],
            validation: {},
            display_order: 1,
          },
        ],
      }));

      await route.fulfill({
        json: {
          schema_version: 'mobile-rwd-fixture',
          categories,
        },
      });
      return;
    }

    if (path === '/api/v1/agent/skills') {
      await route.fulfill({ json: { skills: [], default_skill_id: '' } });
      return;
    }

    if (path === '/api/v1/agent/chat/sessions') {
      await route.fulfill({ json: { sessions: [] } });
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

    if (path === '/api/v1/alphasift/status') {
      await route.fulfill({ json: { enabled: false, installed: false, status: 'disabled' } });
      return;
    }

    if (path === '/api/v1/alphasift/strategies') {
      await route.fulfill({ json: { strategies: [] } });
      return;
    }

    if (path === '/api/v1/backtest/results') {
      await route.fulfill({ json: { total: 0, page: 1, limit: 20, items: [] } });
      return;
    }

    if (path === '/api/v1/backtest/performance' || path.startsWith('/api/v1/backtest/performance/')) {
      await route.fulfill({
        json: {
          scope: 'all',
          eval_window_days: 5,
          engine_version: 'fixture',
          computed_at: '2026-06-29T09:00:00Z',
          total_evaluations: 0,
          completed_count: 0,
          insufficient_count: 0,
          long_count: 0,
          cash_count: 0,
          win_count: 0,
          loss_count: 0,
          neutral_count: 0,
          advice_breakdown: {},
          diagnostics: {},
        },
      });
      return;
    }

    if (path === '/api/v1/usage/dashboard') {
      await route.fulfill({
        json: {
          period: requestUrl.searchParams.get('period') ?? 'month',
          from_date: '2026-06-01',
          to_date: '2026-06-29',
          total_calls: 2,
          total_prompt_tokens: 1200,
          total_completion_tokens: 800,
          total_tokens: 2000,
          by_call_type: [
            { call_type: 'analysis', calls: 1, prompt_tokens: 800, completion_tokens: 500, total_tokens: 1300 },
          ],
          by_model: [
            {
              model: 'gpt-mobile-fixture-long-model-name-for-wrapping',
              calls: 1,
              prompt_tokens: 800,
              completion_tokens: 500,
              total_tokens: 1300,
              max_total_tokens: 1300,
            },
          ],
          recent_calls: [],
        },
      });
      return;
    }

    if (path === '/api/v1/portfolio/accounts') {
      await route.fulfill({ json: { accounts: [] } });
      return;
    }

    if (path === '/api/v1/portfolio/snapshot') {
      await route.fulfill({
        json: {
          as_of: '2026-06-29',
          cost_method: 'fifo',
          currency: 'TWD',
          account_count: 0,
          total_cash: 0,
          total_market_value: 0,
          total_equity: 0,
          realized_pnl: 0,
          unrealized_pnl: 0,
          fee_total: 0,
          tax_total: 0,
          fx_stale: false,
          converted_total_available: true,
          aggregate_is_stale: false,
          fx_missing: false,
          fx_warnings: [],
          fx_rates_used: [],
          accounts: [],
          totals_by_currency: {},
        },
      });
      return;
    }

    if (path === '/api/v1/portfolio/risk') {
      await route.fulfill({
        json: {
          as_of: '2026-06-29',
          account_id: null,
          cost_method: 'fifo',
          currency: 'TWD',
          thresholds: {},
          concentration: { total_market_value: 0, top_weight_pct: 0, alert: false, top_positions: [] },
          sector_concentration: {
            total_market_value: 0,
            top_weight_pct: 0,
            alert: false,
            top_sectors: [],
            coverage: {},
            errors: [],
          },
          drawdown: { series_points: 0, max_drawdown_pct: 0, current_drawdown_pct: 0, alert: false, fx_stale: false },
          stop_loss: { near_alert: false, triggered_count: 0, near_count: 0, items: [] },
        },
      });
      return;
    }

    if (
      path === '/api/v1/portfolio/trades'
      || path === '/api/v1/portfolio/cash-ledger'
      || path === '/api/v1/portfolio/corporate-actions'
    ) {
      await route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 20 } });
      return;
    }

    if (path === '/api/v1/portfolio/imports/csv/brokers') {
      await route.fulfill({ json: { brokers: [] } });
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

    if (path === '/api/v1/alerts/rules') {
      await route.fulfill({
        json: {
          total: 1,
          page: 1,
          page_size: 20,
          items: [
            {
              id: 301,
              name: '台積電突破壓力',
              target_scope: 'single_symbol',
              target: '2330',
              alert_type: 'price_cross',
              parameters: { direction: 'above', price: 800 },
              severity: 'warning',
              enabled: true,
              source: 'fixture',
              cooldown_policy: null,
              notification_policy: null,
              last_triggered_at: null,
              cooldown_until: null,
              cooldown_active: false,
              created_at: '2026-06-29T09:00:00Z',
              updated_at: '2026-06-29T09:30:00Z',
            },
          ],
        },
      });
      return;
    }

    if (path === '/api/v1/alerts/triggers') {
      await route.fulfill({
        json: {
          total: 1,
          page: 1,
          page_size: 20,
          items: [
            {
              id: 401,
              rule_id: 301,
              target: '2330',
              observed_value: 805,
              threshold: 800,
              reason: 'Fixture trigger',
              data_source: 'fixture',
              data_timestamp: '2026-06-29T09:00:00Z',
              triggered_at: '2026-06-29T09:35:00Z',
              status: 'triggered',
              diagnostics: null,
            },
          ],
        },
      });
      return;
    }

    if (path === '/api/v1/alerts/notifications') {
      await route.fulfill({ json: { total: 0, page: 1, page_size: 20, items: [] } });
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

  for (const viewport of MOBILE_VIEWPORTS) {
    for (const routeTarget of routeSmokeTargets) {
      test(`${routeTarget.name} route is usable without mobile document overflow at ${viewport.name}`, async ({ page }) => {
        const consoleErrors: string[] = [];
        const pageErrors: string[] = [];

        page.on('console', (message) => {
          if (message.type() === 'error') {
            consoleErrors.push(message.text());
          }
        });
        page.on('pageerror', (error) => {
          pageErrors.push(error.message);
        });

        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        await page.goto(routeTarget.path);

        await expect(page.locator('body')).toContainText(routeTarget.text);
        await expectNoHorizontalOverflow(page);
        expect(pageErrors, pageErrors.join('\n')).toEqual([]);
        expect(consoleErrors, consoleErrors.join('\n')).toEqual([]);
      });
    }
  }

  test('settings categories remain usable on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/settings');

    for (const category of ['基礎設定', '資料來源', 'AI 模型', '通知', '系統', 'Agent', '回測']) {
      await page.getByRole('button', { name: new RegExp(category) }).first().click();
      await expect(page.locator('body')).toContainText(category);
      await expectNoHorizontalOverflow(page);
    }
  });

  for (const viewport of MOBILE_VIEWPORTS) {
    test(`alerts page has no document overflow at ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.goto('/alerts');

      await expect(page.getByRole('heading', { name: '警告中心' })).toBeVisible();
      await expect(page.getByRole('button', { name: '建立規則' })).toBeVisible();
      await expect(page.getByRole('heading', { name: '警告規則', exact: true })).toBeVisible();
      await expectNoHorizontalOverflow(page);
    });
  }
});
