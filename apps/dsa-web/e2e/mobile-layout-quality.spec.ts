import { mkdir } from 'node:fs/promises';
import { expect, type Locator, type Page, test } from '@playwright/test';
import { expectNoHorizontalOverflow } from './helpers/layout';

const SCREENSHOT_DIR = '/private/tmp/phase23_1b_mobile_layout_quality';

const MOBILE_VIEWPORTS = [
  { name: 'mobile-360', width: 360, height: 740 },
  { name: 'mobile-390', width: 390, height: 844 },
  { name: 'mobile-landscape', width: 667, height: 375 },
];

const stockReport = {
  meta: {
    id: 101,
    query_id: 'q-mobile-msft',
    stock_code: 'MSFT',
    stock_name: 'Microsoft Corporation',
    market: 'US',
    exchange: 'NASDAQ',
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
    },
  },
};

const klineRows = [
  { date: '2026-06-24', open: 498, high: 504, low: 496, close: 502, volume: 21000000 },
  { date: '2026-06-25', open: 502, high: 508, low: 500, close: 506, volume: 22000000 },
  { date: '2026-06-26', open: 506, high: 509, low: 501, close: 503, volume: 21500000 },
  { date: '2026-06-29', open: 503, high: 511, low: 502, close: 509, volume: 23000000 },
];

const qualityRoutes = [
  { name: 'home', path: '/', text: /台股日報|開始分析/, screenshot: 'home_header_360.png' },
  { name: 'chat', path: '/chat', text: /問股/, screenshot: 'chat_360.png' },
  { name: 'portfolio', path: '/portfolio', text: /持股管理/, screenshot: 'portfolio_360.png' },
  { name: 'settings', path: '/settings', text: /系統設定/, screenshot: 'settings_tabs_360.png' },
  { name: 'usage', path: '/usage', text: /用量|Token|呼叫/, screenshot: 'usage_360.png' },
  { name: 'finews', path: '/finews', text: /美股日報/, screenshot: 'finews_360.png' },
  { name: 'backtest', path: '/backtest', text: /執行回測|暫無結果/, screenshot: 'backtest_360.png' },
  { name: 'screening', path: '/screening', text: /AlphaSift 選股發現/, screenshot: 'screening_360.png' },
  { name: 'print-report', path: '/reports/101/print?pdf=1', text: /Microsoft Corporation|行動版報告/, screenshot: 'report_print_360.png' },
  { name: 'alerts', path: '/alerts', text: /警告中心/, screenshot: 'alerts_360.png' },
];

async function setupQualityApiMocks(page: Page): Promise<void> {
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
        setTimeout(() => this.onopen?.(new Event('open')), 0);
      }

      close(): void {
        this.readyState = MockEventSource.CLOSED;
      }
    }

    window.EventSource = MockEventSource as unknown as typeof EventSource;
  });

  await page.route('**/api/v1/**', async (route) => {
    const requestUrl = new URL(route.request().url());
    const path = requestUrl.pathname;

    if (path === '/api/v1/system/config/setup/status') {
      await route.fulfill({ json: { is_complete: true, ready_for_smoke: true, required_missing_keys: [], checks: [] } });
      return;
    }

    if (path === '/api/v1/system/config') {
      const items = [
        ['BASE_URL', 'https://fixture.local', 'base', '基礎網址'],
        ['DATA_PROVIDER', 'finmind', 'data_source', '資料來源'],
        ['DEFAULT_MODEL', 'gpt-mobile-fixture-long-model-name-for-wrapping', 'ai_model', '預設模型'],
        ['NOTIFY_ENABLED', 'false', 'notification', '通知開關'],
        ['SYSTEM_LOCALE', 'zh_TW', 'system', '系統語系'],
        ['AGENT_ENABLED', 'true', 'agent', 'Agent 開關'],
        ['BACKTEST_WINDOW_DAYS', '5', 'backtest', '回測視窗'],
      ];
      await route.fulfill({
        json: {
          config_version: 'mobile-quality-fixture',
          mask_token: '******',
          updated_at: '2026-06-29T09:00:00Z',
          items: items.map(([key, value, category, title], index) => ({
            key,
            value,
            raw_value_exists: true,
            is_masked: false,
            schema: {
              key,
              title,
              description: `${title}行動版品質測試欄位`,
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
      const categories = ['base', 'data_source', 'ai_model', 'notification', 'system', 'agent', 'backtest'];
      const titles = ['基礎設定', '資料來源', 'AI 模型', '通知', '系統', 'Agent', '回測'];
      await route.fulfill({
        json: {
          schema_version: 'mobile-quality-fixture',
          categories: categories.map((category, index) => ({
            category,
            title: titles[index],
            description: `${titles[index]}設定`,
            display_order: index + 1,
            fields: [],
          })),
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

    if (path === '/api/v1/analysis/progress') {
      await route.fulfill({ json: { tasks: {} } });
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
      await route.fulfill({
        json: {
          total: 1,
          page: 1,
          limit: 20,
          items: [
            {
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
            },
          ],
        },
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
            '',
            '| 指標 | 數值 |',
            '| --- | --- |',
            '| 長文字測試 | https://example.com/a/mobile/report/url/that/should/stay/inside/local/markdown/scroll |',
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
      await route.fulfill({ json: { status: 'normal', status_label: '正常', reason: 'fixture', components: {}, copy_text: '' } });
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
          sector_concentration: { total_market_value: 0, top_weight_pct: 0, alert: false, top_sectors: [], coverage: {}, errors: [] },
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
      || path === '/api/v1/backtest/results'
    ) {
      await route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 20 } });
      return;
    }

    if (path === '/api/v1/portfolio/imports/csv/brokers') {
      await route.fulfill({ json: { brokers: [] } });
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

    if (path === '/api/v1/alphasift/status') {
      await route.fulfill({ json: { enabled: false, installed: false, status: 'disabled' } });
      return;
    }

    if (path === '/api/v1/alphasift/strategies') {
      await route.fulfill({ json: { strategies: [] } });
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
          by_call_type: [{ call_type: 'analysis', calls: 1, prompt_tokens: 800, completion_tokens: 500, total_tokens: 1300 }],
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
              created_at: '2026-06-29T09:00:00Z',
              updated_at: '2026-06-29T09:30:00Z',
            },
          ],
        },
      });
      return;
    }

    if (path === '/api/v1/alerts/triggers') {
      await route.fulfill({ json: { total: 0, page: 1, page_size: 20, items: [] } });
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
          external_links: [],
          section_links: {
            after_market_summary: [],
            major_news: [{ title: '長標題測試新聞', url: 'https://example.com/news' }],
            market_temperature: [],
            major_indices: [{ title: 'SPY', url: 'https://finance.yahoo.com/quote/SPY' }],
            major_stocks: [{ title: 'QQQ', url: 'https://finance.yahoo.com/quote/QQQ' }],
            treasury_yields: [],
            fx: [],
          },
          sections: {
            after_market_summary: ['美股盤後摘要測試資料。'],
            major_news: ['長標題測試新聞', 'Fixture · 2026-06-29', '測試新聞摘要。'],
            market_temperature: ['估值溫度', '74°', 'PE 31.7 · 近 20 年 · 2026-06-29'],
            major_indices: ['S&P 500', 'SPY', '6000.00', '+0.12%'],
            major_stocks: ['Invesco QQQ Trust', 'QQQ', '550.00', '+0.22%'],
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

async function capture(page: Page, fileName: string): Promise<void> {
  await mkdir(SCREENSHOT_DIR, { recursive: true });
  await page.screenshot({ path: `${SCREENSHOT_DIR}/${fileName}`, fullPage: true });
}

async function expectLocalOverflowContained(page: Page): Promise<void> {
  const offenders = await page.evaluate(() => {
    const viewportWidth = window.innerWidth;
    const overflowPattern = /(auto|scroll|hidden|clip)/;

    function isVisible(element: Element): boolean {
      const rect = element.getBoundingClientRect();
      const style = window.getComputedStyle(element);
      return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
    }

    function hasLocalOverflowOwner(element: Element): boolean {
      let parent = element.parentElement;
      while (parent && parent !== document.body) {
        const style = window.getComputedStyle(parent);
        const rect = parent.getBoundingClientRect();
        if (overflowPattern.test(style.overflowX) && rect.width <= viewportWidth + 1) {
          return true;
        }
        parent = parent.parentElement;
      }
      return false;
    }

    return Array.from(document.querySelectorAll('table, pre, code'))
      .filter((element) => isVisible(element))
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          tag: element.tagName,
          text: (element.textContent ?? '').trim().slice(0, 80),
          left: rect.left,
          right: rect.right,
          width: rect.width,
          contained: rect.left >= -1 && rect.right <= viewportWidth + 1 ? true : hasLocalOverflowOwner(element),
        };
      })
      .filter((item) => !item.contained);
  });

  expect(offenders, JSON.stringify(offenders, null, 2)).toEqual([]);
}

async function expectImportantControlsUsable(page: Page): Promise<void> {
  const failures = await page.evaluate(() => {
    const importantLabel = /送出|儲存|搜尋|建立|新增|歷史|導航|完整|關閉|登入|套用|執行|開始|刪除|問股|複製|查看/i;

    function visible(element: HTMLElement): boolean {
      const rect = element.getBoundingClientRect();
      const style = window.getComputedStyle(element);
      return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
    }

    return Array.from(document.querySelectorAll<HTMLElement>('button, input, textarea, select, a[href]'))
      .filter((element) => visible(element) && !element.hasAttribute('disabled'))
      .map((element) => {
        const rect = element.getBoundingClientRect();
        const inputType = element instanceof HTMLInputElement ? element.type : '';
        const nativeSmallControl = element.tagName === 'INPUT' && ['checkbox', 'radio', 'range', 'hidden'].includes(inputType);
        const label = [
          element.innerText,
          element.getAttribute('aria-label'),
          element.getAttribute('title'),
          element.getAttribute('placeholder'),
        ].filter(Boolean).join(' ');
        const isFormControl = ['INPUT', 'TEXTAREA', 'SELECT'].includes(element.tagName);
        const isImportant = !nativeSmallControl && (isFormControl || importantLabel.test(label));
        return {
          tag: element.tagName,
          label: label.trim().slice(0, 80),
          width: rect.width,
          height: rect.height,
          isImportant,
        };
      })
      .filter((item) => item.isImportant && (item.width < 30 || item.height < 30));
  });

  expect(failures, JSON.stringify(failures, null, 2)).toEqual([]);
}

async function expectNoBrokenDateEllipsis(page: Page): Promise<void> {
  const bodyText = await page.locator('body').innerText();
  expect(bodyText).not.toMatch(/20\d{2}\.\.\./);
}

async function expectNoStickyOcclusion(page: Page, target: Locator): Promise<void> {
  if (!(await target.first().isVisible().catch(() => false))) {
    return;
  }

  await target.first().scrollIntoViewIfNeeded();
  const result = await target.first().evaluate((element) => {
    const targetRect = element.getBoundingClientRect();
    const targetArea = Math.max(targetRect.width * targetRect.height, 1);

    const offenders = Array.from(document.querySelectorAll<HTMLElement>('*'))
      .filter((candidate) => candidate !== element && !candidate.contains(element))
      .map((candidate) => {
        const style = window.getComputedStyle(candidate);
        const rect = candidate.getBoundingClientRect();
        const fixedLike = style.position === 'fixed' || style.position === 'sticky';
        const visible = rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none' && style.pointerEvents !== 'none';
        if (!fixedLike || !visible) {
          return null;
        }

        const overlapWidth = Math.max(0, Math.min(targetRect.right, rect.right) - Math.max(targetRect.left, rect.left));
        const overlapHeight = Math.max(0, Math.min(targetRect.bottom, rect.bottom) - Math.max(targetRect.top, rect.top));
        const overlapRatio = (overlapWidth * overlapHeight) / targetArea;
        return overlapRatio > 0.25
          ? {
            tag: candidate.tagName,
            className: String(candidate.className || '').slice(0, 120),
            text: (candidate.textContent ?? '').trim().slice(0, 80),
            overlapRatio,
          }
          : null;
      })
      .filter(Boolean);

    return { target: (element.textContent ?? element.getAttribute('aria-label') ?? '').trim().slice(0, 80), offenders };
  });

  expect(result.offenders, JSON.stringify(result, null, 2)).toEqual([]);
}

async function expectCardLikeBlocksWithinViewport(page: Page): Promise<void> {
  const failures = await page.evaluate(() => {
    const viewportWidth = window.innerWidth;
    return Array.from(document.querySelectorAll<HTMLElement>('main .terminal-card, main .rounded-2xl, main .rounded-xl, [role="dialog"] .rounded-2xl'))
      .map((element) => {
        const rect = element.getBoundingClientRect();
        const style = window.getComputedStyle(element);
        return {
          tag: element.tagName,
          text: (element.textContent ?? '').trim().slice(0, 80),
          left: rect.left,
          right: rect.right,
          width: rect.width,
          visible: rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none',
        };
      })
      .filter((item) => item.visible && !['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(item.tag) && (item.left < -1 || item.right > viewportWidth + 1));
  });

  expect(failures, JSON.stringify(failures, null, 2)).toEqual([]);
}

async function assertLayoutQuality(page: Page): Promise<void> {
  await expectNoHorizontalOverflow(page);
  await expectLocalOverflowContained(page);
  await expectImportantControlsUsable(page);
  await expectNoBrokenDateEllipsis(page);
  await expectCardLikeBlocksWithinViewport(page);
}

test.describe('mobile layout quality audit', () => {
  test.beforeEach(async ({ page }) => {
    await setupQualityApiMocks(page);
  });

  for (const viewport of MOBILE_VIEWPORTS) {
    test(`priority routes pass mobile layout quality rules at ${viewport.name}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });

      for (const routeTarget of qualityRoutes) {
        await test.step(routeTarget.name, async () => {
          await page.goto(routeTarget.path);
          await expect(page.locator('body')).toContainText(routeTarget.text);
          if (viewport.name === 'mobile-360') {
            await capture(page, routeTarget.screenshot);
          }
          await assertLayoutQuality(page);
        });
      }
    });
  }

  test('home history drawer and report drawer do not occlude mobile controls', async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 });
    await page.goto('/');

    const historyButton = page.getByRole('button', { name: '歷史記錄' }).first();
    await expectNoStickyOcclusion(page, historyButton);
    await expect(page.locator('body')).toContainText(/Microsoft Corporation|台股日報/);
    await assertLayoutQuality(page);
    await capture(page, 'home_history_drawer_360.png');

    await page.getByRole('button', { name: '完整分析報告' }).click();
    await expect(page.getByTestId('kline-chart-block')).toBeVisible();
    await expectNoStickyOcclusion(page, page.getByRole('button', { name: /關閉/ }).first());
    await assertLayoutQuality(page);
    await capture(page, 'report_drawer_360.png');
  });

  test('settings tabs and form cards keep aligned mobile rows', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/settings');

    for (const category of ['基礎設定', '資料來源', 'AI 模型', '通知', '系統', 'Agent', '回測']) {
      const tab = page.getByRole('button', { name: new RegExp(category) }).first();
      await tab.click();
      await expect(page.locator('body')).toContainText(category);
      await expectNoStickyOcclusion(page, tab);
      await assertLayoutQuality(page);
    }
  });
});
