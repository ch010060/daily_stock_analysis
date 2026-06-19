import type React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createApiError, createParsedApiError } from '../../api/error';
import PortfolioPage from '../PortfolioPage';

const {
  getAccounts,
  getSnapshot,
  getRisk,
  refreshFx,
  listImportBrokers,
  listTrades,
  listCashLedger,
  listCorporateActions,
  createTrade,
  deleteTrade,
  createCashLedger,
  deleteCashLedger,
  createCorporateAction,
  deleteCorporateAction,
  parseCsvImport,
  commitCsvImport,
  createAccount,
} = vi.hoisted(() => ({
  getAccounts: vi.fn(),
  getSnapshot: vi.fn(),
  getRisk: vi.fn(),
  refreshFx: vi.fn(),
  listImportBrokers: vi.fn(),
  listTrades: vi.fn(),
  listCashLedger: vi.fn(),
  listCorporateActions: vi.fn(),
  createTrade: vi.fn(),
  deleteTrade: vi.fn(),
  createCashLedger: vi.fn(),
  deleteCashLedger: vi.fn(),
  createCorporateAction: vi.fn(),
  deleteCorporateAction: vi.fn(),
  parseCsvImport: vi.fn(),
  commitCsvImport: vi.fn(),
  createAccount: vi.fn(),
}));

vi.mock('../../api/portfolio', () => ({
  portfolioApi: {
    getAccounts,
    getSnapshot,
    getRisk,
    refreshFx,
    listImportBrokers,
    listTrades,
    listCashLedger,
    listCorporateActions,
    createTrade,
    deleteTrade,
    createCashLedger,
    deleteCashLedger,
    createCorporateAction,
    deleteCorporateAction,
    parseCsvImport,
    commitCsvImport,
    createAccount,
  },
}));

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PieChart: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Pie: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Tooltip: () => null,
  Legend: () => null,
  Cell: () => null,
}));

type AccountItem = {
  id: number;
  name: string;
  market?: 'tw' | 'cn' | 'hk' | 'us';
  baseCurrency?: string;
};

function makeAccounts(items: AccountItem[] = [{ id: 1, name: 'Main' }]) {
  return {
    accounts: items.map((item) => ({
      id: item.id,
      name: item.name,
      broker: 'Demo',
      market: item.market ?? 'us',
      baseCurrency: item.baseCurrency ?? 'CNY',
      isActive: true,
      ownerId: null,
      createdAt: '2026-03-19T00:00:00Z',
      updatedAt: '2026-03-19T00:00:00Z',
    })),
  };
}

function makeSnapshot(options: {
  accountId?: number;
  currency?: string;
  fxStale?: boolean;
  accountCount?: number;
  totalCash?: number | null;
  totalMarketValue?: number | null;
  totalEquity?: number | null;
  convertedTotalAvailable?: boolean;
  aggregateIsStale?: boolean;
  fxMissing?: boolean;
  fxWarnings?: string[];
  fxRatesUsed?: Array<Record<string, unknown>>;
  positions?: Array<Record<string, unknown>>;
  totalsByCurrency?: Record<string, Record<string, unknown>>;
} = {}) {
  const accountId = options.accountId ?? 1;
  return {
    asOf: '2026-03-19',
    costMethod: 'fifo' as const,
    currency: options.currency ?? 'CNY',
    accountCount: options.accountCount ?? 1,
    totalCash: options.totalCash === undefined ? 1000 : options.totalCash,
    totalMarketValue: options.totalMarketValue === undefined ? 2000 : options.totalMarketValue,
    totalEquity: options.totalEquity === undefined ? 3000 : options.totalEquity,
    realizedPnl: 0,
    unrealizedPnl: 0,
    feeTotal: 0,
    taxTotal: 0,
    fxStale: options.fxStale ?? true,
    convertedTotalAvailable: options.convertedTotalAvailable ?? true,
    aggregateIsStale: options.aggregateIsStale ?? (options.fxStale ?? true),
    fxMissing: options.fxMissing ?? false,
    fxWarnings: options.fxWarnings ?? [],
    fxRatesUsed: options.fxRatesUsed ?? [],
    totalsByCurrency: options.totalsByCurrency ?? {
      cny: {
        currency: 'CNY',
        accountCount: options.accountCount ?? 1,
        totalCash: 1000,
        totalMarketValue: 2000,
        totalEquity: 3000,
        realizedPnl: 0,
        unrealizedPnl: 0,
        feeTotal: 0,
        taxTotal: 0,
      },
    },
    accounts: [
      {
        accountId,
        accountName: `Account ${accountId}`,
        ownerId: null,
        broker: 'Demo',
        market: 'us',
        baseCurrency: 'CNY',
        asOf: '2026-03-19',
        costMethod: 'fifo' as const,
        totalCash: 1000,
        totalMarketValue: 2000,
        totalEquity: 3000,
        realizedPnl: 0,
        unrealizedPnl: 0,
        feeTotal: 0,
        taxTotal: 0,
        fxStale: options.fxStale ?? true,
        positions: options.positions ?? [],
      },
    ],
  };
}

function makeRisk() {
  return {
    asOf: '2026-03-19',
    accountId: null,
    costMethod: 'fifo' as const,
    currency: 'CNY',
    thresholds: {},
    concentration: {
      totalMarketValue: 0,
      topWeightPct: 0,
      alert: false,
      topPositions: [],
    },
    sectorConcentration: {
      totalMarketValue: 0,
      topWeightPct: 0,
      alert: false,
      topSectors: [],
      coverage: {},
      errors: [],
    },
    drawdown: {
      seriesPoints: 0,
      maxDrawdownPct: 0,
      currentDrawdownPct: 0,
      alert: false,
      fxStale: false,
    },
    stopLoss: {
      nearAlert: false,
      triggeredCount: 0,
      nearCount: 0,
      items: [],
    },
  };
}

function deferredPromise<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function waitForInitialLoad() {
  await waitFor(() => expect(getAccounts).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(getSnapshot).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(getRisk).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(listTrades).toHaveBeenCalledTimes(1));
}

describe('PortfolioPage FX refresh', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    getAccounts.mockResolvedValue(makeAccounts());
    getSnapshot.mockImplementation(async ({ accountId }: { accountId?: number } = {}) => makeSnapshot({ accountId, fxStale: true }));
    getRisk.mockResolvedValue(makeRisk());
    refreshFx.mockResolvedValue({
      asOf: '2026-03-19',
      accountCount: 1,
      refreshEnabled: true,
      disabledReason: null,
      pairCount: 1,
      updatedCount: 1,
      staleCount: 0,
      errorCount: 0,
    });
    listImportBrokers.mockResolvedValue({
      brokers: [{ broker: 'huatai', aliases: [], displayName: '華泰' }],
    });
    listTrades.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 });
    listCashLedger.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 });
    listCorporateActions.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 });
    createTrade.mockResolvedValue({ id: 1 });
    deleteTrade.mockResolvedValue({ deleted: 1 });
    createCashLedger.mockResolvedValue({ id: 1 });
    deleteCashLedger.mockResolvedValue({ deleted: 1 });
    createCorporateAction.mockResolvedValue({ id: 1 });
    deleteCorporateAction.mockResolvedValue({ deleted: 1 });
    parseCsvImport.mockResolvedValue({ broker: 'huatai', recordCount: 0, skippedCount: 0, errorCount: 0, records: [], errors: [] });
    commitCsvImport.mockResolvedValue({
      accountId: 1,
      recordCount: 0,
      insertedCount: 0,
      duplicateCount: 0,
      failedCount: 0,
      dryRun: true,
      errors: [],
    });
    createAccount.mockResolvedValue({ id: 1 });
  });

  it('renders stale FX status with a manual refresh button', async () => {
    render(<PortfolioPage />);

    await waitForInitialLoad();

    expect(await screen.findByText('過期')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新整理匯率' })).toBeInTheDocument();
  });

  it('only offers TW/US in the new-account market dropdown', async () => {
    getAccounts.mockResolvedValueOnce({ accounts: [] });
    getSnapshot.mockResolvedValueOnce(makeSnapshot({ accountCount: 0 }));

    render(<PortfolioPage />);

    await waitFor(() => expect(getAccounts).toHaveBeenCalledTimes(1));

    const marketSelect = await screen.findByDisplayValue('市場：台股（tw）');
    const optionValues = within(marketSelect as HTMLSelectElement)
      .getAllByRole('option')
      .map((option) => (option as HTMLOptionElement).value);

    expect(optionValues).toEqual(['tw', 'us']);
  });

  it('renders per-currency subtotal cards when accounts hold mixed TWD/USD currencies', async () => {
    getSnapshot.mockResolvedValueOnce(
      makeSnapshot({
        totalsByCurrency: {
          twd: {
            currency: 'TWD',
            accountCount: 1,
            totalCash: 10000,
            totalMarketValue: 0,
            totalEquity: 10000,
            realizedPnl: 0,
            unrealizedPnl: 0,
            feeTotal: 0,
            taxTotal: 0,
          },
          usd: {
            currency: 'USD',
            accountCount: 1,
            totalCash: 5000,
            totalMarketValue: 0,
            totalEquity: 5000,
            realizedPnl: 0,
            unrealizedPnl: 0,
            feeTotal: 0,
            taxTotal: 0,
          },
        },
      }),
    );

    render(<PortfolioPage />);

    await waitForInitialLoad();

    expect(await screen.findByText('分幣別小計')).toBeInTheDocument();
    expect(screen.getByText('TWD 10,000.00')).toBeInTheDocument();
    expect(screen.getByText('USD 5,000.00')).toBeInTheDocument();
  });

  it('shows converted TWD aggregate and FX metadata when valid USD/TWD FX is available', async () => {
    getSnapshot.mockResolvedValueOnce(
      makeSnapshot({
        currency: 'TWD',
        fxStale: false,
        totalCash: 170000,
        totalMarketValue: 0,
        totalEquity: 170000,
        convertedTotalAvailable: true,
        aggregateIsStale: false,
        fxMissing: false,
        fxRatesUsed: [
          {
            fromCurrency: 'TWD',
            toCurrency: 'USD',
            rate: 0.03125,
            conversionFromCurrency: 'USD',
            conversionToCurrency: 'TWD',
            conversionRate: 32,
            direction: 'inverse',
            rateDate: '2026-03-19',
            isStale: false,
          },
        ],
        totalsByCurrency: {
          twd: {
            currency: 'TWD',
            accountCount: 1,
            totalCash: 10000,
            totalMarketValue: 0,
            totalEquity: 10000,
            realizedPnl: 0,
            unrealizedPnl: 0,
            feeTotal: 0,
            taxTotal: 0,
          },
          usd: {
            currency: 'USD',
            accountCount: 1,
            totalCash: 5000,
            totalMarketValue: 0,
            totalEquity: 5000,
            realizedPnl: 0,
            unrealizedPnl: 0,
            feeTotal: 0,
            taxTotal: 0,
          },
        },
      }),
    );

    render(<PortfolioPage />);

    await waitForInitialLoad();

    expect(screen.getAllByText('TWD 170,000.00').length).toBeGreaterThan(0);
    expect(screen.getByText(/USD\/TWD/)).toBeInTheDocument();
    expect(screen.getByText(/32\.0000/)).toBeInTheDocument();
    expect(screen.getByText('TWD 10,000.00')).toBeInTheDocument();
    expect(screen.getByText('USD 5,000.00')).toBeInTheDocument();
  });

  it('shows FX unavailable warning instead of fake TWD aggregate when mixed FX is missing', async () => {
    getSnapshot.mockResolvedValueOnce(
      makeSnapshot({
        currency: 'TWD',
        totalCash: null,
        totalMarketValue: null,
        totalEquity: null,
        convertedTotalAvailable: false,
        aggregateIsStale: true,
        fxMissing: true,
        fxWarnings: ['匯率不可用，無法計算換算總額。'],
        totalsByCurrency: {
          twd: {
            currency: 'TWD',
            accountCount: 1,
            totalCash: 10000,
            totalMarketValue: 0,
            totalEquity: 10000,
            realizedPnl: 0,
            unrealizedPnl: 0,
            feeTotal: 0,
            taxTotal: 0,
          },
          usd: {
            currency: 'USD',
            accountCount: 1,
            totalCash: 5000,
            totalMarketValue: 0,
            totalEquity: 5000,
            realizedPnl: 0,
            unrealizedPnl: 0,
            feeTotal: 0,
            taxTotal: 0,
          },
        },
      }),
    );

    render(<PortfolioPage />);

    await waitForInitialLoad();

    expect(screen.getByText('匯率不可用，無法計算換算總額。')).toBeInTheDocument();
    expect(screen.queryByText('TWD 15,000.00')).not.toBeInTheDocument();
    expect(screen.getByText('TWD 10,000.00')).toBeInTheDocument();
    expect(screen.getByText('USD 5,000.00')).toBeInTheDocument();
  });

  it('does not render the per-currency subtotal section for a single-currency portfolio', async () => {
    getSnapshot.mockResolvedValueOnce(makeSnapshot({}));

    render(<PortfolioPage />);

    await waitForInitialLoad();

    expect(screen.queryByText('分幣別小計')).not.toBeInTheDocument();
  });

  it('refreshes FX for a single selected account and only reloads snapshot/risk', async () => {
    getSnapshot
      .mockResolvedValueOnce(makeSnapshot({ fxStale: true }))
      .mockResolvedValueOnce(makeSnapshot({ accountId: 1, fxStale: true }))
      .mockResolvedValueOnce(makeSnapshot({ accountId: 1, fxStale: false }));

    render(<PortfolioPage />);

    await waitForInitialLoad();

    const accountSelect = screen.getAllByRole('combobox')[0];
    fireEvent.change(accountSelect, { target: { value: '1' } });

    await waitFor(() => {
      expect(getSnapshot).toHaveBeenLastCalledWith({ accountId: 1, costMethod: 'fifo' });
    });

    const snapshotCallsBeforeRefresh = getSnapshot.mock.calls.length;
    const riskCallsBeforeRefresh = getRisk.mock.calls.length;
    const tradeCallsBeforeRefresh = listTrades.mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: '重新整理匯率' }));

    await waitFor(() => expect(refreshFx).toHaveBeenCalledWith({ accountId: 1 }));
    expect(await screen.findByText('匯率已重新整理，共更新 1 對。')).toBeInTheDocument();
    await waitFor(() => expect(getSnapshot).toHaveBeenCalledTimes(snapshotCallsBeforeRefresh + 1));
    await waitFor(() => expect(getRisk).toHaveBeenCalledTimes(riskCallsBeforeRefresh + 1));
    expect(listTrades).toHaveBeenCalledTimes(tradeCallsBeforeRefresh);
    expect(listCashLedger).not.toHaveBeenCalled();
    expect(listCorporateActions).not.toHaveBeenCalled();
    expect(screen.getByText('最新')).toBeInTheDocument();
  });

  it('refreshes FX for the full portfolio without sending accountId and shows neutral feedback when no pair exists', async () => {
    refreshFx.mockResolvedValueOnce({
      asOf: '2026-03-19',
      accountCount: 1,
      refreshEnabled: true,
      disabledReason: null,
      pairCount: 0,
      updatedCount: 0,
      staleCount: 0,
      errorCount: 0,
    });

    render(<PortfolioPage />);

    await waitForInitialLoad();

    fireEvent.click(screen.getByRole('button', { name: '重新整理匯率' }));

    await waitFor(() => expect(refreshFx).toHaveBeenCalledWith({ accountId: undefined }));
    expect(await screen.findByText('當前範圍無可重新整理的匯率對。')).toBeInTheDocument();
  });

  it('shows disabled feedback when FX online refresh is disabled even without a disabled reason', async () => {
    refreshFx.mockResolvedValueOnce({
      asOf: '2026-03-19',
      accountCount: 1,
      refreshEnabled: false,
      pairCount: 1,
      updatedCount: 0,
      staleCount: 0,
      errorCount: 0,
    });

    render(<PortfolioPage />);

    await waitForInitialLoad();

    fireEvent.click(screen.getByRole('button', { name: '重新整理匯率' }));

    expect(await screen.findByText('匯率線上重新整理已被禁用。')).toBeInTheDocument();
  });

  it('renders backend-provided position valuation fields and stale missing-price hint', async () => {
    getSnapshot.mockResolvedValueOnce(makeSnapshot({ fxStale: true, positions: [
      { symbol: 'HK00700', market: 'hk', currency: 'HKD', quantity: 10, avgCost: 400, totalCost: 4000, lastPrice: 420, marketValueBase: 4200, unrealizedPnlBase: 200, unrealizedPnlPct: 5, valuationCurrency: 'HKD', priceSource: 'history_close', priceDate: '2026-03-18', priceStale: true, priceAvailable: true },
      { symbol: 'AAPL', market: 'us', currency: 'USD', quantity: 5, avgCost: 100, totalCost: 500, lastPrice: 0, marketValueBase: 0, unrealizedPnlBase: 0, unrealizedPnlPct: null, valuationCurrency: 'USD', priceSource: 'missing', priceDate: null, priceStale: true, priceAvailable: false },
    ] }));

    render(<PortfolioPage />);

    await waitForInitialLoad();

    expect(await screen.findByText('HK00700')).toBeInTheDocument();
    expect(screen.getByText('420.0000')).toBeInTheDocument();
    expect(screen.getByText('HKD 4,200.00')).toBeInTheDocument();
    expect(screen.getByText('+5.00%')).toBeInTheDocument();
    expect(screen.getByText('收盤價 · 2026-03-18')).toBeInTheDocument();
    expect(screen.getByText('缺價')).toBeInTheDocument();
    expect(screen.getAllByText('--').length).toBeGreaterThanOrEqual(2);

    const hkRow = screen.getByText('HK00700').closest('tr');
    const aaplRow = screen.getByText('AAPL').closest('tr');
    expect(hkRow).not.toBeNull();
    expect(aaplRow).not.toBeNull();

    const hkRowCells = within(hkRow as HTMLTableRowElement).getAllByRole('cell');
    const aaplRowCells = within(aaplRow as HTMLTableRowElement).getAllByRole('cell');
    expect(hkRowCells.at(-1)).toHaveClass('text-success');
    expect(aaplRowCells.at(-1)).toHaveClass('text-secondary');
  });

  it('prefers disabled feedback over empty-pair feedback when refresh is disabled', async () => {
    refreshFx.mockResolvedValueOnce({
      asOf: '2026-03-19',
      accountCount: 1,
      refreshEnabled: false,
      disabledReason: 'portfolio_fx_update_disabled',
      pairCount: 0,
      updatedCount: 0,
      staleCount: 0,
      errorCount: 0,
    });

    render(<PortfolioPage />);

    await waitForInitialLoad();

    fireEvent.click(screen.getByRole('button', { name: '重新整理匯率' }));

    expect(await screen.findByText('匯率線上重新整理已被禁用。')).toBeInTheDocument();
    expect(screen.queryByText('當前範圍無可重新整理的匯率對。')).not.toBeInTheDocument();
  });

  it('shows warning feedback when FX refresh still falls back to stale rates', async () => {
    refreshFx.mockResolvedValueOnce({
      asOf: '2026-03-19',
      accountCount: 1,
      pairCount: 2,
      updatedCount: 1,
      staleCount: 1,
      errorCount: 0,
    });

    render(<PortfolioPage />);

    await waitForInitialLoad();

    fireEvent.click(screen.getByRole('button', { name: '重新整理匯率' }));

    expect(await screen.findByText(/stale\/fallback 匯率/)).toBeInTheDocument();
  });

  it('shows warning feedback when FX refresh returns online errors without stale pairs', async () => {
    refreshFx.mockResolvedValueOnce({
      asOf: '2026-03-19',
      accountCount: 1,
      pairCount: 1,
      updatedCount: 0,
      staleCount: 0,
      errorCount: 1,
    });

    render(<PortfolioPage />);

    await waitForInitialLoad();

    const snapshotCallsBeforeRefresh = getSnapshot.mock.calls.length;
    const riskCallsBeforeRefresh = getRisk.mock.calls.length;
    const tradeCallsBeforeRefresh = listTrades.mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: '重新整理匯率' }));

    expect(await screen.findByText(/線上重新整理未完全成功/)).toBeInTheDocument();
    await waitFor(() => expect(getSnapshot).toHaveBeenCalledTimes(snapshotCallsBeforeRefresh + 1));
    await waitFor(() => expect(getRisk).toHaveBeenCalledTimes(riskCallsBeforeRefresh + 1));
    expect(listTrades).toHaveBeenCalledTimes(tradeCallsBeforeRefresh);
    expect(listCashLedger).not.toHaveBeenCalled();
    expect(listCorporateActions).not.toHaveBeenCalled();
  });

  it('restores the button state and shows the existing error alert when FX refresh fails', async () => {
    refreshFx.mockRejectedValueOnce(
      createApiError(
        createParsedApiError({
          title: '重新整理失敗',
          message: '匯率服務暫時不可用',
        }),
      ),
    );

    render(<PortfolioPage />);

    await waitForInitialLoad();

    const refreshButton = screen.getByRole('button', { name: '重新整理匯率' });
    fireEvent.click(refreshButton);

    const fxAlertTitle = await screen.findByText('重新整理失敗');
    expect(fxAlertTitle.closest('[role="alert"]')).toHaveTextContent('匯率服務暫時不可用');
    await waitFor(() => expect(screen.getByRole('button', { name: '重新整理匯率' })).not.toBeDisabled());
  });

  it('does not keep success feedback when snapshot reload fails after FX refresh succeeds', async () => {
    getSnapshot
      .mockResolvedValueOnce(makeSnapshot({ fxStale: true }))
      .mockRejectedValueOnce(
        createApiError(
          createParsedApiError({
            title: '快照重新整理失敗',
            message: '無法載入最新持股快照',
          }),
        ),
      );

    render(<PortfolioPage />);

    await waitForInitialLoad();

    fireEvent.click(screen.getByRole('button', { name: '重新整理匯率' }));

    const fxAlertTitle = await screen.findByText('快照重新整理失敗');
    expect(fxAlertTitle.closest('[role="alert"]')).toHaveTextContent('無法載入最新持股快照');
    await waitFor(() => expect(screen.queryByText('匯率已重新整理，共更新 1 對。')).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByRole('button', { name: '重新整理匯率' })).not.toBeDisabled());
  });

  it('drops late FX refresh results after switching to another account scope', async () => {
    getAccounts.mockResolvedValueOnce(makeAccounts([{ id: 1, name: 'Main' }, { id: 2, name: 'Alt' }]));
    getSnapshot.mockImplementation(async ({ accountId }: { accountId?: number } = {}) => {
      if (accountId === 2) {
        return makeSnapshot({ accountId: 2, fxStale: false });
      }
      return makeSnapshot({ accountId: accountId ?? 1, fxStale: true, accountCount: accountId ? 1 : 2 });
    });

    const pendingRefresh = deferredPromise<{
      asOf: string;
      accountCount: number;
      pairCount: number;
      updatedCount: number;
      staleCount: number;
      errorCount: number;
    }>();
    refreshFx.mockImplementationOnce(() => pendingRefresh.promise);

    render(<PortfolioPage />);

    await waitForInitialLoad();

    const accountSelect = screen.getAllByRole('combobox')[0];
    fireEvent.change(accountSelect, { target: { value: '1' } });
    await waitFor(() => expect(getSnapshot).toHaveBeenLastCalledWith({ accountId: 1, costMethod: 'fifo' }));

    fireEvent.click(screen.getByRole('button', { name: '重新整理匯率' }));
    expect(await screen.findByRole('button', { name: '重新整理中...' })).toBeDisabled();

    fireEvent.change(accountSelect, { target: { value: '2' } });
    await waitFor(() => expect(getSnapshot).toHaveBeenLastCalledWith({ accountId: 2, costMethod: 'fifo' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '重新整理匯率' })).not.toBeDisabled());

    const snapshotCallsAfterSwitch = getSnapshot.mock.calls.length;
    const riskCallsAfterSwitch = getRisk.mock.calls.length;

    await act(async () => {
      pendingRefresh.resolve({
        asOf: '2026-03-19',
        accountCount: 1,
        pairCount: 1,
        updatedCount: 1,
        staleCount: 0,
        errorCount: 0,
      });
      await pendingRefresh.promise;
    });

    expect(getSnapshot).toHaveBeenCalledTimes(snapshotCallsAfterSwitch);
    expect(getRisk).toHaveBeenCalledTimes(riskCallsAfterSwitch);
    expect(screen.queryByText('匯率已重新整理，共更新 1 對。')).not.toBeInTheDocument();
  });

  it('drops late FX refresh results after switching cost method', async () => {
    const pendingRefresh = deferredPromise<{
      asOf: string;
      accountCount: number;
      pairCount: number;
      updatedCount: number;
      staleCount: number;
      errorCount: number;
    }>();
    refreshFx.mockImplementationOnce(() => pendingRefresh.promise);

    render(<PortfolioPage />);

    await waitForInitialLoad();

    const costMethodSelect = screen.getAllByRole('combobox')[1];

    fireEvent.click(screen.getByRole('button', { name: '重新整理匯率' }));
    expect(await screen.findByRole('button', { name: '重新整理中...' })).toBeDisabled();

    fireEvent.change(costMethodSelect, { target: { value: 'avg' } });
    await waitFor(() => expect(getSnapshot).toHaveBeenLastCalledWith({ accountId: undefined, costMethod: 'avg' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '重新整理匯率' })).not.toBeDisabled());

    const snapshotCallsAfterSwitch = getSnapshot.mock.calls.length;
    const riskCallsAfterSwitch = getRisk.mock.calls.length;

    await act(async () => {
      pendingRefresh.resolve({
        asOf: '2026-03-19',
        accountCount: 1,
        pairCount: 1,
        updatedCount: 1,
        staleCount: 0,
        errorCount: 0,
      });
      await pendingRefresh.promise;
    });

    expect(getSnapshot).toHaveBeenCalledTimes(snapshotCallsAfterSwitch);
    expect(getRisk).toHaveBeenCalledTimes(riskCallsAfterSwitch);
    expect(screen.queryByText('匯率已重新整理，共更新 1 對。')).not.toBeInTheDocument();
  });
});

describe('PortfolioPage manual-entry currency selectors', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    getAccounts.mockResolvedValue(makeAccounts());
    getSnapshot.mockImplementation(async ({ accountId }: { accountId?: number } = {}) => makeSnapshot({ accountId, fxStale: true }));
    getRisk.mockResolvedValue(makeRisk());
    refreshFx.mockResolvedValue({
      asOf: '2026-03-19',
      accountCount: 1,
      refreshEnabled: true,
      disabledReason: null,
      pairCount: 1,
      updatedCount: 1,
      staleCount: 0,
      errorCount: 0,
    });
    listImportBrokers.mockResolvedValue({
      brokers: [{ broker: 'huatai', aliases: [], displayName: '華泰' }],
    });
    listTrades.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 });
    listCashLedger.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 });
    listCorporateActions.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 20 });
    createTrade.mockResolvedValue({ id: 1 });
    deleteTrade.mockResolvedValue({ deleted: 1 });
    createCashLedger.mockResolvedValue({ id: 1 });
    deleteCashLedger.mockResolvedValue({ deleted: 1 });
    createCorporateAction.mockResolvedValue({ id: 1 });
    deleteCorporateAction.mockResolvedValue({ deleted: 1 });
    parseCsvImport.mockResolvedValue({ broker: 'huatai', recordCount: 0, skippedCount: 0, errorCount: 0, records: [], errors: [] });
    commitCsvImport.mockResolvedValue({
      accountId: 1,
      recordCount: 0,
      insertedCount: 0,
      duplicateCount: 0,
      failedCount: 0,
      dryRun: true,
      errors: [],
    });
    createAccount.mockResolvedValue({ id: 1 });
  });

  it('renders explicit TWD/USD-only currency selectors for all manual-entry forms', async () => {
    getAccounts.mockResolvedValueOnce(
      makeAccounts([
        { id: 1, name: 'TW Account', market: 'tw', baseCurrency: 'TWD' },
        { id: 2, name: 'US Account', market: 'us', baseCurrency: 'USD' },
      ]),
    );

    render(<PortfolioPage />);

    await waitForInitialLoad();

    const selectors = [
      screen.getByLabelText('交易幣別'),
      screen.getByLabelText('資金流水幣別'),
      screen.getByLabelText('公司行為幣別'),
    ] as HTMLSelectElement[];

    selectors.forEach((selector) => {
      expect(selector).toHaveValue('TWD');
      expect(within(selector).getByRole('option', { name: 'TWD' })).toBeInTheDocument();
      expect(within(selector).getByRole('option', { name: 'USD' })).toBeInTheDocument();
      expect(within(selector).queryByRole('option', { name: 'CNY' })).not.toBeInTheDocument();
      expect(within(selector).queryByRole('option', { name: 'HKD' })).not.toBeInTheDocument();
    });
  });

  it('defaults manual-entry currencies from the selected account base currency', async () => {
    getAccounts.mockResolvedValueOnce(
      makeAccounts([
        { id: 1, name: 'TW Account', market: 'tw', baseCurrency: 'TWD' },
        { id: 2, name: 'US Account', market: 'us', baseCurrency: 'USD' },
      ]),
    );
    getSnapshot.mockImplementation(async ({ accountId }: { accountId?: number } = {}) =>
      makeSnapshot({ accountId, fxStale: false, accountCount: accountId ? 1 : 2 }),
    );

    render(<PortfolioPage />);

    await waitForInitialLoad();

    const accountSelect = screen.getAllByRole('combobox')[0];

    fireEvent.change(accountSelect, { target: { value: '1' } });
    await waitFor(() => expect(getSnapshot).toHaveBeenLastCalledWith({ accountId: 1, costMethod: 'fifo' }));
    expect(screen.getByLabelText('交易幣別')).toHaveValue('TWD');
    expect(screen.getByLabelText('資金流水幣別')).toHaveValue('TWD');
    expect(screen.getByLabelText('公司行為幣別')).toHaveValue('TWD');

    fireEvent.change(accountSelect, { target: { value: '2' } });
    await waitFor(() => expect(getSnapshot).toHaveBeenLastCalledWith({ accountId: 2, costMethod: 'fifo' }));
    expect(screen.getByLabelText('交易幣別')).toHaveValue('USD');
    expect(screen.getByLabelText('資金流水幣別')).toHaveValue('USD');
    expect(screen.getByLabelText('公司行為幣別')).toHaveValue('USD');
  });
});
