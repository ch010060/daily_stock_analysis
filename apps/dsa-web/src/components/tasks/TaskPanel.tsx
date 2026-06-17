import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronDown, Clock, RefreshCw } from 'lucide-react';
import { Badge, Card, StatusDot } from '../common';
import { DashboardPanelHeader } from '../dashboard';
import type { TaskInfo } from '../../types/analysis';
import { getRequestedPhaseLabel } from '../../utils/marketPhase';

const STAGE_LABELS: Record<string, string> = {
  queued: '排隊中',
  data_fetching: '正在擷取股價與基本資料',
  optional_context: '正在整理新聞與延伸資料',
  llm_analyzing: '正在生成完整分析報告',
  report_saving: '正在儲存報告',
  completed: '分析完成',
  failed: '分析失敗',
  timeout: '分析逾時',
};

const STAGE_ORDER = ['queued', 'data_fetching', 'optional_context', 'llm_analyzing', 'report_saving'];

/**
 * Formats elapsed seconds into mm:ss.
 */
function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

interface TaskItemProps {
  task: TaskInfo;
}

const TaskItem: React.FC<TaskItemProps> = ({ task }) => {
  const isProcessing = task.status === 'processing';
  const statusLabel = isProcessing ? '分析中' : '等待中';
  const statusVariant = isProcessing ? 'info' : 'default';
  const statusTone = isProcessing ? 'info' : 'neutral';
  const progress = Math.max(0, Math.min(100, task.progress || 0));
  const traceId = (task.traceId || '').trim();
  const requestedPhaseLabel = getRequestedPhaseLabel(task.analysisPhase, 'zh');
  const requestedPhaseVariant = task.analysisPhase === 'auto' ? 'default' : 'info';

  // Elapsed time counter
  const startedAt = useMemo(
    () => (task.startedAt ? new Date(task.startedAt) : null),
    [task.startedAt],
  );
  const [elapsed, setElapsed] = useState(0);

  const updateElapsed = useCallback(() => {
    if (startedAt) {
      setElapsed(Math.floor((Date.now() - startedAt.getTime()) / 1000));
    }
  }, [startedAt]);

  useEffect(() => {
    if (!isProcessing || !startedAt) return;
    const interval = setInterval(updateElapsed, 1000);
    return () => clearInterval(interval);
  }, [isProcessing, startedAt, updateElapsed]);

  // Stage label from API or fallback to known map
  const stageKey = task.stage || '';
  const stageDisplay = task.stageLabel || STAGE_LABELS[stageKey] || '';
  const currentStageIdx = STAGE_ORDER.indexOf(stageKey);

  return (
    <div className="home-subpanel px-3 py-2.5">
      {/* Header: stock name + status */}
      <div className="flex items-center gap-3">
        <div className="shrink-0">
          {isProcessing ? (
            <StatusDot tone="info" pulse className="h-2.5 w-2.5" />
          ) : (
            <StatusDot tone="neutral" className="h-2.5 w-2.5" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-foreground truncate">
              {task.stockName || task.stockCode}
            </span>
            <span className="text-xs text-muted-text">{task.stockCode}</span>
          </div>
          {requestedPhaseLabel ? (
            <Badge variant={requestedPhaseVariant} className="mt-1 shadow-none" aria-label={requestedPhaseLabel}>{requestedPhaseLabel}</Badge>
          ) : null}
        </div>
        <div className="flex-shrink-0">
          <Badge variant={statusVariant} className="min-w-[4.75rem] justify-center gap-1.5 shadow-none" aria-label={`任务状态：${statusLabel}`}>
            <StatusDot tone={statusTone} pulse={isProcessing} className="h-1.5 w-1.5" />
            {statusLabel}
          </Badge>
        </div>
      </div>

      {/* Stage stepper (mini) */}
      {isProcessing && stageDisplay && (
        <div className="mt-2.5 rounded-lg border border-subtle bg-base/60 px-3 py-2">
          <div className="flex items-center gap-2 text-xs">
            <span className="font-medium text-foreground">{stageDisplay}</span>
            {startedAt && elapsed > 0 && (
              <span className="flex items-center gap-1 text-muted-text tabular-nums ml-auto">
                <Clock className="h-3 w-3" />
                {formatElapsed(elapsed)}
              </span>
            )}
          </div>
          {/* Mini stepper dots */}
          {currentStageIdx >= 0 && (
            <div className="mt-1.5 flex items-center gap-1">
              {STAGE_ORDER.map((s, i) => {
                const isDone = i < currentStageIdx;
                const isCurrent = i === currentStageIdx;
                return (
                  <div key={s} className="flex items-center gap-1">
                    <div
                      className={`h-1.5 w-1.5 rounded-full transition-colors ${
                        isDone ? 'bg-cyan' : isCurrent ? 'bg-cyan animate-pulse' : 'bg-white/15'
                      }`}
                    />
                    {i < STAGE_ORDER.length - 1 && (
                      <div className={`h-px w-2 ${isDone ? 'bg-cyan/50' : 'bg-white/10'}`} />
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Progress bar + percentage */}
      <div className="mt-2.5 flex items-center gap-2">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/8">
          <div
            className="h-full rounded-full bg-cyan transition-[width] duration-300 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
        <span className="shrink-0 text-[11px] text-muted-text tabular-nums">
          {progress}%
        </span>
      </div>

      {/* Message */}
      {task.message && (
        <p className="mt-1.5 text-xs text-secondary-text truncate">{task.message}</p>
      )}

      {/* Trace ID (collapsible) */}
      {traceId ? (
        <details className="group/task mt-2 text-xs">
          <summary className="flex cursor-pointer list-none items-center gap-2 text-muted-text">
            <span>运行诊断</span>
            <span className="font-mono text-[11px] text-secondary-text">
              {traceId.length > 18 ? `${traceId.slice(0, 10)}...` : traceId}
            </span>
            <ChevronDown className="h-3.5 w-3.5 transition-transform group-open/task:rotate-180" />
          </summary>
          <div className="mt-1 rounded-lg border border-subtle bg-base/50 px-2 py-1.5">
            <code className="break-all font-mono text-[11px] text-secondary-text">{traceId}</code>
          </div>
        </details>
      ) : null}
    </div>
  );
};

interface TaskPanelProps {
  tasks: TaskInfo[];
  visible?: boolean;
  title?: string;
  className?: string;
}

export const TaskPanel: React.FC<TaskPanelProps> = ({
  tasks,
  visible = true,
      title = '分析任务',
  className = '',
}) => {
  const activeTasks = useMemo(
    () => tasks.filter((t) => t.status === 'pending' || t.status === 'processing'),
    [tasks],
  );

  if (!visible || activeTasks.length === 0) {
    return null;
  }

  const pendingCount = activeTasks.filter((t) => t.status === 'pending').length;
  const processingCount = activeTasks.filter((t) => t.status === 'processing').length;

  return (
    <Card variant="bordered" padding="none" className={`home-panel-card overflow-hidden ${className}`}>
      <div className="border-b border-subtle px-3 py-3">
        <DashboardPanelHeader
          className="mb-0"
          title={title}
          titleClassName="text-sm font-medium"
          leading={<RefreshCw className="h-4 w-4 text-cyan" />}
          headingClassName="items-center"
          actions={
            <div className="flex items-center gap-2 text-xs text-muted-text">
              {processingCount > 0 && (
                <span className="flex items-center gap-1">
                  <StatusDot tone="info" pulse className="h-1.5 w-1.5" />
                  {processingCount} 进行中
                </span>
              )}
              {pendingCount > 0 && (
                <span className="flex items-center gap-1">
                  <StatusDot tone="neutral" className="h-1.5 w-1.5" />
                  {pendingCount} 等待中
                </span>
              )}
            </div>
          }
        />
      </div>
      <div className="max-h-80 overflow-y-auto p-2">
        <div className="space-y-2">
          {activeTasks.map((task) => (
            <TaskItem key={task.taskId} task={task} />
          ))}
        </div>
        {processingCount > 0 && (
          <p className="mt-2 text-center text-xs text-muted-text">
            完整分析報告正在生成，可能需要數分鐘
          </p>
        )}
      </div>
    </Card>
  );
};

export default TaskPanel;
