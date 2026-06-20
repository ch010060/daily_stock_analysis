import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AlertRuleForm } from '../AlertRuleForm';

const { getAccounts } = vi.hoisted(() => ({
  getAccounts: vi.fn(),
}));

vi.mock('../../../api/portfolio', () => ({
  portfolioApi: {
    getAccounts,
  },
}));

describe('AlertRuleForm', () => {
  const onSubmit = vi.fn();

  beforeEach(() => {
    onSubmit.mockReset();
    onSubmit.mockResolvedValue(undefined);
    getAccounts.mockReset();
    getAccounts.mockResolvedValue({ accounts: [{ id: 9, name: 'Main', market: 'us', baseCurrency: 'USD', isActive: true }] });
  });

  it('submits a price_cross rule payload', async () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('規則名稱'), { target: { value: '台積電突破壓力' } });
    fireEvent.change(screen.getByLabelText('標的代號'), { target: { value: '2330' } });
    fireEvent.change(screen.getByLabelText('價格閾值'), { target: { value: '800' } });
    fireEvent.click(screen.getByRole('button', { name: '建立規則' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith({
        name: '台積電突破壓力',
        targetScope: 'single_symbol',
        target: '2330',
        alertType: 'price_cross',
        parameters: { direction: 'above', price: 800 },
        severity: 'warning',
        enabled: true,
      });
    });
  });

  it('submits a price_change_percent rule payload', async () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('標的代號'), { target: { value: 'aapl' } });
    fireEvent.change(screen.getByLabelText('規則型別'), { target: { value: 'price_change_percent' } });
    fireEvent.change(screen.getByLabelText('方向'), { target: { value: 'down' } });
    fireEvent.change(screen.getByLabelText('漲跌幅閾值（%）'), { target: { value: '3.5' } });
    fireEvent.change(screen.getByLabelText('嚴重級別'), { target: { value: 'critical' } });
    fireEvent.click(screen.getByRole('button', { name: '建立規則' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        target: 'AAPL',
        alertType: 'price_change_percent',
        parameters: { direction: 'down', changePct: 3.5 },
        severity: 'critical',
      }));
    });
  });

  it('submits a volume_spike rule payload and supports disabled creation', async () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('標的代號'), { target: { value: 'msft' } });
    fireEvent.change(screen.getByLabelText('規則型別'), { target: { value: 'volume_spike' } });
    fireEvent.change(screen.getByLabelText('成交量放大倍數'), { target: { value: '2.5' } });
    fireEvent.click(screen.getByLabelText('建立後立即啟用'));
    fireEvent.click(screen.getByRole('button', { name: '建立規則' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        target: 'MSFT',
        alertType: 'volume_spike',
        parameters: { multiplier: 2.5 },
        enabled: false,
      }));
    });
  });

  it('submits technical indicator rule payloads', async () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('標的代號'), { target: { value: '600519' } });
    fireEvent.change(screen.getByLabelText('規則型別'), { target: { value: 'macd_cross' } });
    fireEvent.change(screen.getByLabelText('交叉方向'), { target: { value: 'bearish_cross' } });
    fireEvent.change(screen.getByLabelText('快線週期'), { target: { value: '6' } });
    fireEvent.change(screen.getByLabelText('慢線週期'), { target: { value: '13' } });
    fireEvent.change(screen.getByLabelText('訊號週期'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: '建立規則' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        target: '600519',
        alertType: 'macd_cross',
        parameters: {
          direction: 'bearish_cross',
          fastPeriod: 6,
          slowPeriod: 13,
          signalPeriod: 5,
        },
      }));
    });
  });

  it('rejects invalid technical indicator boundaries before submit', () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('標的代號'), { target: { value: '600519' } });
    fireEvent.change(screen.getByLabelText('規則型別'), { target: { value: 'rsi_threshold' } });
    fireEvent.change(screen.getByLabelText('RSI 閾值'), { target: { value: '200' } });
    fireEvent.click(screen.getByRole('button', { name: '建立規則' }));

    expect(screen.getByRole('alert')).toHaveTextContent('RSI 閾值必須在 0 到 100 之間');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('rejects indicator period combinations that exceed fetchable history', () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('標的代號'), { target: { value: '600519' } });
    fireEvent.change(screen.getByLabelText('規則型別'), { target: { value: 'macd_cross' } });
    fireEvent.change(screen.getByLabelText('快線週期'), { target: { value: '2' } });
    fireEvent.change(screen.getByLabelText('慢線週期'), { target: { value: '250' } });
    fireEvent.change(screen.getByLabelText('訊號週期'), { target: { value: '250' } });
    fireEvent.click(screen.getByRole('button', { name: '建立規則' }));

    expect(screen.getByRole('alert')).toHaveTextContent('MACD 週期組合需要 501 根日線，最多支援 365 根');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('rejects empty required technical indicator thresholds before submit', () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('標的代號'), { target: { value: '600519' } });
    fireEvent.change(screen.getByLabelText('規則型別'), { target: { value: 'rsi_threshold' } });
    fireEvent.click(screen.getByRole('button', { name: '建立規則' }));

    expect(screen.getByRole('alert')).toHaveTextContent('RSI 閾值不能為空');
    expect(onSubmit).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText('規則型別'), { target: { value: 'cci_threshold' } });
    fireEvent.click(screen.getByRole('button', { name: '建立規則' }));

    expect(screen.getByRole('alert')).toHaveTextContent('CCI 閾值不能為空');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('rejects invalid numeric thresholds before submit', () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('標的代號'), { target: { value: '600519' } });
    fireEvent.change(screen.getByLabelText('價格閾值'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: '建立規則' }));

    expect(screen.getByRole('alert')).toHaveTextContent('價格閾值必須是大於 0 的數字');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('rejects invalid stock code format before submit', () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('標的代號'), { target: { value: 'aapl-2026' } });
    fireEvent.change(screen.getByLabelText('價格閾值'), { target: { value: '200' } });
    fireEvent.click(screen.getByRole('button', { name: '建立規則' }));

    expect(screen.getByRole('alert')).toHaveTextContent('股票代號格式不正確');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('filters alert types and submits a watchlist rule payload', async () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('目標範圍'), { target: { value: 'watchlist' } });
    expect(screen.queryByText('組合止損')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('價格閾值'), { target: { value: '10' } });
    fireEvent.click(screen.getByRole('button', { name: '建立規則' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        targetScope: 'watchlist',
        target: 'default',
        alertType: 'price_cross',
        parameters: { direction: 'above', price: 10 },
      }));
    });
  });

  it('loads accounts and submits portfolio stop-loss mode', async () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('目標範圍'), { target: { value: 'portfolio_account' } });
    await waitFor(() => expect(getAccounts).toHaveBeenCalledWith(false));
    expect(screen.queryByText('價格突破')).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('帳戶'), { target: { value: '9' } });
    fireEvent.change(screen.getByLabelText('止損模式'), { target: { value: 'breach' } });
    fireEvent.click(screen.getByRole('button', { name: '建立規則' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        targetScope: 'portfolio_account',
        target: '9',
        alertType: 'portfolio_stop_loss',
        parameters: { mode: 'breach' },
      }));
    });
  });

  it('submits a market light status rule payload', async () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('目標範圍'), { target: { value: 'market' } });
    fireEvent.change(screen.getByLabelText('市場區域'), { target: { value: 'hk' } });
    fireEvent.click(screen.getByRole('button', { name: '建立規則' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        targetScope: 'market',
        target: 'hk',
        alertType: 'market_light_status',
        parameters: { statuses: ['red', 'yellow'] },
      }));
    });
  });

  it('submits a market light score-drop rule payload', async () => {
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('目標範圍'), { target: { value: 'market' } });
    fireEvent.change(screen.getByLabelText('市場區域'), { target: { value: 'us' } });
    fireEvent.change(screen.getByLabelText('規則型別'), { target: { value: 'market_light_score_drop' } });
    fireEvent.change(screen.getByLabelText('Score 下降閾值'), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: '建立規則' }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
        targetScope: 'market',
        target: 'us',
        alertType: 'market_light_score_drop',
        parameters: { minDrop: 12 },
      }));
    });
  });

  it('keeps all account option when account loading fails', async () => {
    getAccounts.mockRejectedValueOnce(new Error('boom'));
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('目標範圍'), { target: { value: 'portfolio_holdings' } });
    expect(await screen.findByRole('alert')).toHaveTextContent('boom');
    expect(screen.getByLabelText('帳戶')).toHaveValue('all');
  });

  it('keeps form values when submit reports failure', async () => {
    onSubmit.mockResolvedValueOnce(false);
    render(<AlertRuleForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText('標的代號'), { target: { value: 'aapl' } });
    fireEvent.change(screen.getByLabelText('價格閾值'), { target: { value: '200' } });
    fireEvent.click(screen.getByRole('button', { name: '建立規則' }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(screen.getByLabelText('標的代號')).toHaveValue('aapl');
    expect(screen.getByLabelText('價格閾值')).toHaveValue(200);
  });
});
