import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { TaskPanel } from '../TaskPanel';
import type { TaskInfo } from '../../../types/analysis';

const baseTask: TaskInfo = {
  taskId: 'task-1',
  stockCode: '2330',
  stockName: '台積電',
  status: 'processing',
  progress: 40,
  message: '正在抓取最新行情',
  reportType: 'detailed',
  createdAt: '2026-03-21T08:00:00Z',
};

describe('TaskPanel', () => {
  it('renders requested analysis phase badges for active tasks', () => {
    render(
      <TaskPanel
        tasks={[
          {
            ...baseTask,
            analysisPhase: 'intraday',
          },
          {
            ...baseTask,
            taskId: 'task-2',
            stockCode: 'AAPL',
            stockName: 'Apple',
            status: 'pending',
            analysisPhase: 'auto',
          },
        ]}
      />,
    );

    expect(screen.getByLabelText('請求階段: 盤中')).toBeInTheDocument();
    expect(screen.getByLabelText('請求階段: 自動階段')).toBeInTheDocument();
  });

  it('renders active tasks with preserved dashboard panel styling', () => {
    const { container } = render(
      <TaskPanel
        tasks={[
          {
            ...baseTask,
            traceId: 'trace-task-1',
          },
          {
            ...baseTask,
            taskId: 'task-2',
            stockCode: 'AAPL',
            stockName: 'Apple',
            status: 'pending',
            message: '等待分析佇列',
          },
        ]}
      />,
    );

    expect(screen.getByText('分析任務')).toBeInTheDocument();
    expect(screen.getByText('1 進行中')).toBeInTheDocument();
    expect(screen.getByText('1 等待中')).toBeInTheDocument();
    expect(screen.getByText('台積電')).toBeInTheDocument();
    expect(screen.getByText('AAPL')).toBeInTheDocument();
    expect(screen.getByLabelText('任務狀態：分析中')).toBeInTheDocument();
    expect(screen.getByText('執行診斷')).toBeInTheDocument();
    expect(screen.getAllByText('trace-task-1')).toHaveLength(2);
    expect(screen.queryByText(/請求階段:/)).not.toBeInTheDocument();
    expect(container.querySelector('.home-panel-card')).toBeTruthy();
    expect(container.querySelector('.home-subpanel')).toBeTruthy();
  });

  it('does not render when there are no active tasks', () => {
    const { container } = render(
      <TaskPanel
        tasks={[
          {
            ...baseTask,
            status: 'completed',
          },
        ]}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
