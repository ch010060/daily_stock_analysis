import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { HistoryList } from '../HistoryList';
import type { HistoryItem } from '../../../types/analysis';

const baseProps = {
  isLoading: false,
  isLoadingMore: false,
  hasMore: false,
  selectedIds: new Set<number>(),
  onItemClick: vi.fn(),
  onLoadMore: vi.fn(),
  onToggleItemSelection: vi.fn(),
  onToggleSelectAll: vi.fn(),
  onDeleteSelected: vi.fn(),
};

const items: HistoryItem[] = [
  {
    id: 1,
    queryId: 'q-1',
    stockCode: '2330',
    stockName: '台積電',
    sentimentScore: 82,
    operationAdvice: '買進',
    createdAt: '2026-03-15T08:00:00Z',
  },
];

const longChineseNameItem: HistoryItem = {
  id: 2,
  queryId: 'q-2',
  stockCode: '2330',
  stockName: '台積電股份有限公司',
  sentimentScore: 75,
  operationAdvice: '持有',
  createdAt: '2026-03-16T08:00:00Z',
  marketPhaseSummary: {
    market: 'CN',
    phase: 'non_trading',
    warnings: [],
  },
};

describe('HistoryList', () => {
  it('shows the empty state copy when no history exists', () => {
    const { container } = render(<HistoryList {...baseProps} items={[]} />);

    expect(screen.getByText('暫無歷史分析記錄')).toBeInTheDocument();
    expect(screen.getByText('完成首次分析後，這裡會保留最近結果。')).toBeInTheDocument();
    expect(screen.getByText('歷史分析')).toBeInTheDocument();
    expect(container.querySelector('.glass-card')).toBeTruthy();
  });

  it('renders selected count and forwards item interactions', () => {
    const onItemClick = vi.fn();
    const onToggleItemSelection = vi.fn();

    render(
      <HistoryList
        {...baseProps}
        items={items}
        selectedIds={new Set([1])}
        selectedId={1}
        onItemClick={onItemClick}
        onToggleItemSelection={onToggleItemSelection}
      />,
    );

    expect(screen.getByText('已選 1')).toBeInTheDocument();
    expect(screen.getByText('買進 82')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /台積電/i }));
    expect(onItemClick).toHaveBeenCalledWith(1);

    fireEvent.click(screen.getAllByRole('checkbox')[1]);
    expect(onToggleItemSelection).toHaveBeenCalledWith(1);
  });

  it('toggles select-all when clicking the label text', () => {
    const onToggleSelectAll = vi.fn();

    render(
      <HistoryList
        {...baseProps}
        items={items}
        onToggleSelectAll={onToggleSelectAll}
      />,
    );

    fireEvent.click(screen.getByText('全選當前'));

    expect(onToggleSelectAll).toHaveBeenCalledTimes(1);
  });

  it('disables delete when nothing is selected', () => {
    render(<HistoryList {...baseProps} items={items} />);

    expect(screen.getByRole('button', { name: '刪除' })).toBeDisabled();
  });

  it('truncates long stock names with trailing dot', () => {
    render(
      <HistoryList
        {...baseProps}
        items={[longChineseNameItem]}
      />,
    );

    // '台積電股份有限公司' (12 Chinese chars) should be truncated to '台積電股票股份.' (8 chars + dot)
    expect(screen.getByText('台積電股票股份.')).toBeInTheDocument();
    expect(screen.queryByText('台積電股份有限公司')).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', {
        name: /^台積電股份有限公司 2330 歷史記錄$/,
      }),
    ).toBeInTheDocument();

    const actions = screen.getByTestId('history-card-actions');
    const meta = screen.getByTestId('history-card-meta');
    expect(within(actions).queryByText('CN · 非交易日')).not.toBeInTheDocument();
    expect(within(meta).getByText('CN · 非交易日')).toBeVisible();
  });

  it('generates unique select-all ids across multiple instances', () => {
    const { container } = render(
      <>
        <HistoryList {...baseProps} items={items} />
        <HistoryList {...baseProps} items={items} />
      </>,
    );

    const labels = container.querySelectorAll('label[for]');
    const ids = Array.from(labels).map((label) => label.getAttribute('for'));

    expect(ids).toHaveLength(2);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
