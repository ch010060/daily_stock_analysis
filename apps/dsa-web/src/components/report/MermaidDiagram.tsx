import type React from 'react';
import { useEffect, useId, useRef, useState } from 'react';
import mermaid from 'mermaid';

export interface MermaidDiagramProps {
  code: string;
}

const FALLBACK_MESSAGE = '價值網路圖暫時無法渲染，已保留 Mermaid 原始內容。';
const READABLE_CLASS_DEFS = [
  'classDef center fill:#fffdfa,stroke:#1e3a5f,stroke-width:2px,color:#111827;',
  'classDef card fill:#ffffff,stroke:#cbd5e1,stroke-width:1px,color:#111827;',
].join('\n');
const VIEWBOX_PADDING = 44;

// Belt-and-suspenders client-side guard: the backend should already validate
// any mermaid source it embeds in report markdown, but we refuse to even
// attempt rendering content that looks like it carries script/HTML-event
// payloads, regardless of what mermaid's own sanitizer would do with it.
const DANGEROUS_PATTERN = /<script|<iframe|javascript:|\bon[a-z]+\s*=/i;

let mermaidInitialized = false;

function ensureMermaidInitialized(): void {
  if (mermaidInitialized) return;
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'strict',
    theme: 'base',
    themeVariables: {
      background: '#fffdfa',
      primaryColor: '#ffffff',
      primaryTextColor: '#111827',
      primaryBorderColor: '#cbd5e1',
      lineColor: '#64748b',
      clusterBkg: '#f8fafc',
      clusterBorder: '#cbd5e1',
      edgeLabelBackground: '#fffdfa',
      fontFamily: 'ui-sans-serif, system-ui, sans-serif',
      fontSize: '16px',
    },
    flowchart: {
      htmlLabels: false,
      padding: 18,
      nodeSpacing: 52,
      rankSpacing: 72,
    },
  });
  mermaidInitialized = true;
}

function normalizeMermaidSource(code: string): string {
  const withoutDarkClassDefs = code
    .split(/\r?\n/)
    .filter((line) => !/^%%\{init:/i.test(line.trim()))
    .filter((line) => !/^classDef\s+(?:center|card)\b/i.test(line.trim()))
    .join('\n')
    .trim();
  return `${withoutDarkClassDefs}\n${READABLE_CLASS_DEFS}`;
}

function setImportantStyle(element: Element, property: string, value: string): void {
  (element as HTMLElement).style.setProperty(property, value, 'important');
}

function expandSvgViewBox(svg: SVGSVGElement): void {
  const viewBox = svg.getAttribute('viewBox');
  const parts = viewBox?.trim().split(/\s+/).map(Number);

  if (parts?.length === 4 && parts.every(Number.isFinite)) {
    const [x, y, width, height] = parts;
    svg.setAttribute(
      'viewBox',
      [
        x - VIEWBOX_PADDING,
        y - VIEWBOX_PADDING,
        width + VIEWBOX_PADDING * 2,
        height + VIEWBOX_PADDING * 2,
      ].join(' ')
    );
  }

  svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
}

function applyReportMermaidDomTuning(container: HTMLElement): void {
  const svg = container.querySelector('svg');
  if (svg) {
    setImportantStyle(svg, 'overflow', 'visible');
    expandSvgViewBox(svg as SVGSVGElement);
  }

  container.querySelectorAll('foreignObject, foreignobject').forEach((element) => {
    setImportantStyle(element, 'overflow', 'visible');
  });

  container
    .querySelectorAll('text, tspan, .nodeLabel, .label, .label span, foreignObject div, foreignobject div')
    .forEach((element) => {
      setImportantStyle(element, 'color', '#111827');
      setImportantStyle(element, 'fill', '#111827');
      setImportantStyle(element, 'font-size', '13px');
      setImportantStyle(element, 'line-height', '1.16');
    });

  container.querySelectorAll('.nodeLabel p, .label p, foreignObject p, foreignobject p').forEach((element) => {
    setImportantStyle(element, 'line-height', '1.16');
    setImportantStyle(element, 'margin', '0');
    setImportantStyle(element, 'padding', '0 2px');
  });

  container
    .querySelectorAll('.node rect, .node polygon, .node circle, .node ellipse')
    .forEach((element) => {
      setImportantStyle(element, 'fill', '#fff');
      setImportantStyle(element, 'stroke', '#cbd5e1');
    });

  container
    .querySelectorAll('.node.center rect, .node.center polygon, .node.center circle, .node.center ellipse')
    .forEach((element) => {
      setImportantStyle(element, 'fill', '#fffdfa');
      setImportantStyle(element, 'stroke', '#1e3a5f');
      setImportantStyle(element, 'stroke-width', '2px');
    });

  container.querySelectorAll('.cluster rect').forEach((element) => {
    setImportantStyle(element, 'fill', '#f8fafc');
    setImportantStyle(element, 'stroke', '#cbd5e1');
  });
}

export const MermaidDiagram: React.FC<MermaidDiagramProps> = ({ code }) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [hasError, setHasError] = useState(false);
  const reactId = useId();
  const diagramId = `mermaid-diagram-${reactId.replace(/[^a-zA-Z0-9]/g, '')}`;

  useEffect(() => {
    let isMounted = true;

    const renderDiagram = async () => {
      if (DANGEROUS_PATTERN.test(code)) {
        if (isMounted) setHasError(true);
        return;
      }

      ensureMermaidInitialized();

      try {
        const { svg } = await mermaid.render(diagramId, normalizeMermaidSource(code));
        if (!isMounted) return;
        if (containerRef.current) {
          // Safe: `svg` here is Mermaid's own generated SVG output (not raw
          // user/report HTML). The defensive regex guard above already
          // rejected anything that looks like it could smuggle script/event
          // payloads into the source, and mermaid's `securityLevel: 'strict'`
          // additionally disables script tags, click handlers, and raw HTML
          // labels when generating this SVG. Injecting it via innerHTML is
          // required because react-markdown/React has no built-in way to
          // mount a pre-rendered SVG string as DOM otherwise.
          containerRef.current.innerHTML = svg;
          applyReportMermaidDomTuning(containerRef.current);
        }
        setHasError(false);
      } catch {
        if (isMounted) setHasError(true);
      }
    };

    renderDiagram();

    return () => {
      isMounted = false;
    };
  }, [code, diagramId]);

  if (hasError) {
    return (
      <div data-testid="mermaid-fallback">
        <p>{FALLBACK_MESSAGE}</p>
        <pre>
          <code>{code}</code>
        </pre>
      </div>
    );
  }

  return (
    <div
      data-testid="mermaid-diagram"
      ref={containerRef}
      style={{ overflowX: 'auto', overflowY: 'visible', maxWidth: '100%' }}
    />
  );
};
