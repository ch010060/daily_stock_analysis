import type React from 'react';
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '../../utils/cn';

interface TooltipProps {
  content: React.ReactNode;
  children: React.ReactNode;
  side?: 'top' | 'bottom';
  focusable?: boolean;
  className?: string;
  contentClassName?: string;
}

type TooltipStyle = {
  top: number;
  left: number;
};

const TOOLTIP_OPEN_EVENT = 'dsa-tooltip-open';

export const Tooltip: React.FC<TooltipProps> = ({
  content,
  children,
  side = 'top',
  focusable = false,
  className = '',
  contentClassName = '',
}) => {
  const triggerRef = useRef<HTMLSpanElement | null>(null);
  const tooltipRef = useRef<HTMLSpanElement | null>(null);
  const tooltipId = useId();
  const [open, setOpen] = useState(false);
  const [resolvedSide, setResolvedSide] = useState<'top' | 'bottom'>(side);
  const [style, setStyle] = useState<TooltipStyle>({ top: 0, left: 0 });

  const show = useCallback(() => {
    window.dispatchEvent(new CustomEvent(TOOLTIP_OPEN_EVENT, { detail: tooltipId }));
    setOpen(true);
  }, [tooltipId]);

  const hide = useCallback(() => {
    setOpen(false);
  }, []);

  const updatePosition = useCallback(() => {
    const trigger = triggerRef.current;
    const tooltip = tooltipRef.current;
    if (!trigger || !tooltip) {
      return;
    }

    const triggerRect = trigger.getBoundingClientRect();
    const tooltipRect = tooltip.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const gap = 10;
    const margin = 8;

    let nextSide = side;
    let top =
      side === 'top'
        ? triggerRect.top - tooltipRect.height - gap
        : triggerRect.bottom + gap;

    if (side === 'top' && top < margin) {
      nextSide = 'bottom';
      top = triggerRect.bottom + gap;
    } else if (side === 'bottom' && top + tooltipRect.height > viewportHeight - margin) {
      nextSide = 'top';
      top = triggerRect.top - tooltipRect.height - gap;
    }

    let left = triggerRect.left + triggerRect.width / 2 - tooltipRect.width / 2;
    left = Math.max(margin, Math.min(left, viewportWidth - tooltipRect.width - margin));
    top = Math.max(margin, Math.min(top, viewportHeight - tooltipRect.height - margin));

    setResolvedSide(nextSide);
    setStyle({ top, left });
  }, [side]);

  useLayoutEffect(() => {
    if (!open) {
      return;
    }

    const frameId = window.requestAnimationFrame(() => {
      updatePosition();
    });

    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [open, content, updatePosition]);

  useEffect(() => {
    const handleOtherTooltip = (event: Event) => {
      if ((event as CustomEvent<string>).detail !== tooltipId) {
        setOpen(false);
      }
    };
    window.addEventListener(TOOLTIP_OPEN_EVENT, handleOtherTooltip);
    return () => {
      window.removeEventListener(TOOLTIP_OPEN_EVENT, handleOtherTooltip);
    };
  }, [tooltipId]);

  useEffect(() => {
    if (!open) {
      return;
    }

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (
        target &&
        (triggerRef.current?.contains(target) || tooltipRef.current?.contains(target))
      ) {
        return;
      }
      setOpen(false);
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false);
      }
    };
    const handleViewportChange = () => updatePosition();
    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleEscape);
    window.addEventListener('resize', handleViewportChange);
    window.addEventListener('scroll', handleViewportChange, true);

    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleEscape);
      window.removeEventListener('resize', handleViewportChange);
      window.removeEventListener('scroll', handleViewportChange, true);
    };
  }, [open, updatePosition]);

  if (!content) {
    return <>{children}</>;
  }

  return (
    <>
      <span
        ref={triggerRef}
        className={cn('inline-flex', className)}
        onMouseEnter={show}
        onMouseLeave={hide}
        onClick={(event) => {
          event.stopPropagation();
          if (open) {
            hide();
          } else {
            show();
          }
        }}
        onFocus={show}
        onBlur={hide}
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            hide();
          }
        }}
        tabIndex={focusable ? 0 : undefined}
        aria-describedby={open ? tooltipId : undefined}
      >
        {children}
      </span>

      {typeof document !== 'undefined' && open
        ? createPortal(
            <span
              ref={tooltipRef}
              id={tooltipId}
              role="tooltip"
              style={{
                position: 'fixed',
                top: style.top,
                left: style.left,
              }}
              className={cn(
                'pointer-events-none z-[120] min-w-max max-w-[18rem] rounded-xl border border-border/70 bg-elevated/95 px-3 py-1.5 text-xs leading-5 text-foreground shadow-[0_16px_40px_rgba(3,8,20,0.18)] backdrop-blur-xl',
                resolvedSide === 'top' ? 'origin-bottom' : 'origin-top',
                contentClassName,
              )}
            >
              {content}
            </span>,
            document.body,
          )
        : null}
    </>
  );
};
