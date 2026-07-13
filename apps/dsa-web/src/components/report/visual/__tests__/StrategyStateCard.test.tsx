import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { StrategyStateCard } from '../StrategyStateCard';

const authoritativeSnapshot = () => ({
  state: 'ACCUMULATE_ZONE',
  previousState: 'WAIT_FOR_PULLBACK',
  operationAdvice: '分批布局',
  decisionType: 'buy',
  buyZone: {
    low: 3880.0, high: 3950.0,
    basis: ['support:3880.0', 'valuation_band'],
    createdAt: '2026-07-01',
  },
  invalidationLevel: 3802.4,
  transitionRuleId: 'RULE_VALID_BUY_ZONE_ENTERED',
  transitionTriggered: true,
  daysInState: 0,
  reasons: [],
  dataLimitations: [],
  authoritative: true,
});

describe('StrategyStateCard', () => {
  it('renders the authoritative strategy section with zh_TW labels', () => {
    render(<StrategyStateCard rawSnapshot={authoritativeSnapshot()} />);
    expect(screen.getByTestId('strategy-state-card')).toBeInTheDocument();
    expect(screen.getByTestId('strategy-state-badge')).toHaveTextContent('分批布局區');
    expect(screen.getByText('分批布局')).toBeInTheDocument();
    expect(screen.getByTestId('strategy-buy-zone')).toHaveTextContent('3880～3950');
    expect(screen.getByText(/RULE_VALID_BUY_ZONE_ENTERED/)).toBeInTheDocument();
    expect(screen.getByText(/自 等待回檔 轉入/)).toBeInTheDocument();
  });

  it('renders nothing for legacy reports without a snapshot', () => {
    const { container } = render(<StrategyStateCard rawSnapshot={undefined} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing for non-authoritative (ETF UNSUPPORTED) snapshots', () => {
    const payload = authoritativeSnapshot() as Record<string, unknown>;
    payload.state = 'UNSUPPORTED';
    payload.authoritative = false;
    const { container } = render(<StrategyStateCard rawSnapshot={payload} />);
    expect(container.innerHTML).toBe('');
  });

  it('shows an explicit no-valid-zone reason instead of fabricating a range', () => {
    const payload = authoritativeSnapshot() as Record<string, unknown>;
    payload.state = 'DO_NOT_CHASE';
    payload.operationAdvice = '不追價';
    payload.buyZone = null;
    payload.reasons = ['risk_reward_below_threshold'];
    render(<StrategyStateCard rawSnapshot={payload} />);
    expect(screen.getByTestId('strategy-buy-zone')).toHaveTextContent('無有效買區（risk_reward_below_threshold）');
    expect(screen.getByTestId('strategy-state-badge')).toHaveTextContent('不追價');
  });

  it('escapes html-like text instead of rendering it', () => {
    const payload = authoritativeSnapshot() as Record<string, unknown>;
    payload.reasons = ['<img src=x onerror=alert(1)>reason'];
    const { container } = render(<StrategyStateCard rawSnapshot={payload} />);
    expect(container.querySelector('img')).toBeNull();
  });

  it('renders REDUCE_RISK with the danger badge', () => {
    const payload = authoritativeSnapshot() as Record<string, unknown>;
    payload.state = 'REDUCE_RISK';
    payload.operationAdvice = '降低風險曝險';
    payload.buyZone = null;
    render(<StrategyStateCard rawSnapshot={payload} />);
    expect(screen.getByTestId('strategy-state-badge')).toHaveTextContent('降低風險');
  });

  it('never renders "不支援" even with a stale UNSUPPORTED previousState (Phase 27.2R)', () => {
    const payload = authoritativeSnapshot() as Record<string, unknown>;
    payload.previousState = 'UNSUPPORTED';
    const { container } = render(<StrategyStateCard rawSnapshot={payload} />);
    expect(container.textContent).not.toContain('不支援');
    expect(container.textContent).not.toContain('轉入');
  });
});
