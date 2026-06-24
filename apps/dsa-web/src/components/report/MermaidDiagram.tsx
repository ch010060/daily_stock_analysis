import type React from 'react';
import { useEffect, useId, useRef, useState } from 'react';
import mermaid from 'mermaid';

export interface MermaidDiagramProps {
  code: string;
}

const FALLBACK_MESSAGE = '價值網路圖暫時無法渲染，已保留 Mermaid 原始內容。';

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
    theme: 'dark',
  });
  mermaidInitialized = true;
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
        const { svg } = await mermaid.render(diagramId, code);
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

  return <div data-testid="mermaid-diagram" ref={containerRef} />;
};
