# -*- coding: utf-8 -*-
"""Tests for the Phase 18A value-network Mermaid appendix validator."""

import unittest

from src.services.value_network_mermaid import validate_value_network_mermaid


class ValidateValueNetworkMermaidTestCase(unittest.TestCase):
    def test_valid_flowchart_tb_is_returned_trimmed(self) -> None:
        raw = """
        flowchart TB
            subgraph S["供應商"]
                A[供應商A]
            end
        """
        result = validate_value_network_mermaid(raw)
        self.assertEqual(result, raw.strip())

    def test_valid_graph_tb_keyword_is_accepted(self) -> None:
        raw = "graph TB\n  A[公司] --> B[客戶]"
        result = validate_value_network_mermaid(raw)
        self.assertEqual(result, raw.strip())

    def test_flowchart_lr_returns_none(self) -> None:
        """Phase 18E v3: only TB is accepted now — LR would lay the fixed
        4-section A4 layout out horizontally instead of vertically."""
        raw = "flowchart LR\n  A[公司] --> B[客戶]"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_graph_td_keyword_returns_none(self) -> None:
        """Phase 18E v3: TD is semantically identical to TB in Mermaid but is
        no longer accepted — the validator now requires the literal TB token."""
        raw = "graph TD\n  A[公司] --> B[客戶]"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_none_input_returns_none(self) -> None:
        self.assertIsNone(validate_value_network_mermaid(None))

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(validate_value_network_mermaid(""))

    def test_whitespace_only_returns_none(self) -> None:
        self.assertIsNone(validate_value_network_mermaid("   \n\t  "))

    def test_non_string_input_returns_none(self) -> None:
        self.assertIsNone(validate_value_network_mermaid(12345))  # type: ignore[arg-type]

    def test_oversized_input_returns_none(self) -> None:
        raw = "flowchart TB\n" + ("  A --> B\n" * 1000)
        self.assertGreater(len(raw), 4000)
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_embedded_triple_backtick_fence_returns_none(self) -> None:
        raw = "```mermaid\nflowchart TB\n  A --> B\n```"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_missing_flowchart_or_graph_keyword_returns_none(self) -> None:
        raw = "A --> B\nB --> C"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_missing_direction_returns_none(self) -> None:
        raw = "flowchart\n  A --> B"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_forbidden_sequence_diagram_returns_none(self) -> None:
        raw = "sequenceDiagram\n  Alice->>Bob: Hello"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_forbidden_class_diagram_returns_none(self) -> None:
        raw = "flowchart TB\n  classDiagram\n  A --> B"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_forbidden_er_diagram_returns_none(self) -> None:
        raw = "flowchart TB\n  erDiagram\n  A --> B"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_forbidden_git_graph_returns_none(self) -> None:
        raw = "flowchart TB\n  gitGraph\n  A --> B"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_forbidden_state_diagram_returns_none(self) -> None:
        raw = "flowchart TB\n  stateDiagram\n  A --> B"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_forbidden_journey_returns_none(self) -> None:
        raw = "flowchart TB\n  journey\n  A --> B"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_forbidden_pie_returns_none(self) -> None:
        raw = "flowchart TB\n  pie\n  A --> B"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_forbidden_gantt_returns_none(self) -> None:
        raw = "flowchart TB\n  gantt\n  A --> B"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_script_tag_returns_none(self) -> None:
        raw = "flowchart TB\n  A[<script>alert(1)</script>] --> B"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_iframe_tag_returns_none(self) -> None:
        raw = "flowchart TB\n  A[<iframe src=x></iframe>] --> B"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_javascript_scheme_returns_none(self) -> None:
        raw = "flowchart TB\n  A[click](javascript:alert(1)) --> B"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_event_handler_attribute_returns_none(self) -> None:
        raw = 'flowchart TB\n  A["<img src=x onerror=alert(1)>"] --> B'
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_raw_http_url_returns_none(self) -> None:
        raw = "flowchart TB\n  A[http://example.com] --> B"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_raw_https_url_returns_none(self) -> None:
        raw = "flowchart TB\n  A[https://example.com] --> B"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_too_many_subgraphs_returns_none(self) -> None:
        lines = ["flowchart TB"]
        for i in range(9):
            lines.append(f"subgraph S{i}")
            lines.append(f"  N{i}[Node{i}]")
            lines.append("end")
        raw = "\n".join(lines)
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_five_subgraphs_returns_none(self) -> None:
        """Phase 18E v3: the fixed 4-section (S/K/R/P) layout allows at most 4 top-level subgraphs (was 5)."""
        lines = ["flowchart TB"]
        for i in range(5):
            lines.append(f"subgraph S{i}")
            lines.append(f"  N{i}[Node{i}]")
            lines.append("end")
        raw = "\n".join(lines)
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_four_subgraphs_is_allowed(self) -> None:
        """Phase 18E v3: exactly 4 subgraphs (供應商/客戶/競爭者/互補者) is the boundary-allowed case."""
        lines = ["flowchart TB"]
        for i in range(4):
            lines.append(f"subgraph S{i}")
            lines.append(f"  N{i}[Node{i}]")
            lines.append("end")
        raw = "\n".join(lines)
        result = validate_value_network_mermaid(raw)
        self.assertEqual(result, raw.strip())

    def test_too_many_distinct_nodes_returns_none(self) -> None:
        lines = ["flowchart TB"]
        for i in range(41):
            lines.append(f"N{i}[Node{i}] --> N{i + 1}[Node{i + 1}]")
        raw = "\n".join(lines)
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_twenty_three_distinct_nodes_returns_none(self) -> None:
        """Phase 18E v3: the 4-section x 3-card + center layout allows at most 22 distinct nodes (was 18)."""
        lines = ["flowchart TB"]
        for i in range(23):
            lines.append(f"N{i}[Node{i}]")
        raw = "\n".join(lines)
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_twenty_two_distinct_nodes_is_allowed(self) -> None:
        lines = ["flowchart TB"]
        for i in range(22):
            lines.append(f"N{i}[Node{i}]")
        raw = "\n".join(lines)
        result = validate_value_network_mermaid(raw)
        self.assertEqual(result, raw.strip())

    def test_too_many_edges_returns_none(self) -> None:
        """Phase 18E v3: at most 16 visible edges (was 12), to keep the appendix from becoming a dense spider graph."""
        lines = ["flowchart TB", "C[Center]"]
        for i in range(17):
            lines.append(f"  N{i}[Node{i}] --> C")
        raw = "\n".join(lines)
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_sixteen_edges_is_allowed(self) -> None:
        lines = ["flowchart TB", "C[Center]"]
        for i in range(16):
            lines.append(f"  N{i}[Node{i}] --> C")
        raw = "\n".join(lines)
        result = validate_value_network_mermaid(raw)
        self.assertEqual(result, raw.strip())

    def test_invisible_links_not_counted_toward_max_edges(self) -> None:
        """Phase 18E v3: "~~~" layout-only chains are deliberately excluded from _MAX_EDGES."""
        lines = ["flowchart TB"]
        for i in range(20):
            lines.append(f"N{i}[Node{i}] ~~~ N{i + 1}[Node{i + 1}]")
        raw = "\n".join(lines)
        result = validate_value_network_mermaid(raw)
        self.assertEqual(result, raw.strip())

    def test_digit_leading_node_id_returns_none(self) -> None:
        """Phase 18E: an id starting with a digit (e.g. 5G_SoC) is not a valid/reliable Mermaid identifier."""
        raw = "flowchart TB\n  5G_SoC[5G/6G SoC技術領先]\n  C[公司] --> 5G_SoC"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_chinese_text_as_edge_source_returns_none(self) -> None:
        """Phase 18E: Chinese text must stay inside node labels, not be used as a raw edge endpoint."""
        raw = "flowchart TB\n  TSMC[台積電]\n  聯發科(2454)-->|委託代工| TSMC"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_chinese_text_as_edge_target_returns_none(self) -> None:
        raw = "flowchart TB\n  C[公司]\n  C --> 台積電"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_init_directive_in_body_returns_none(self) -> None:
        """Phase 18E v3: the LLM must never produce %%{init...}%% — it is prepended by backend code instead."""
        raw = 'flowchart TB\n  A[X] --> B[Y]\n  %%{init: {"theme": "base"}}%%'
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_nested_subgraph_returns_none(self) -> None:
        """Phase 18E v3: nested subgraphs are rejected (not just a raw count of "subgraph" lines)."""
        raw = "flowchart TB\n  subgraph A\n    subgraph B\n      C1[X]\n    end\n  end"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_sibling_subgraphs_are_not_mistaken_for_nesting(self) -> None:
        raw = "flowchart TB\n  subgraph A\n    A1[X]\n  end\n  subgraph B\n    B1[Y]\n  end"
        result = validate_value_network_mermaid(raw)
        self.assertEqual(result, raw.strip())

    def test_unsafe_chinese_subgraph_id_returns_none(self) -> None:
        """Phase 18E v3: `subgraph <id>` ids must be safe ASCII identifiers, e.g. not 供應商["..."]."""
        raw = 'flowchart TB\n  subgraph 供應商["Suppliers"]\n    A[X]\n  end'
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_unquoted_label_with_parenthesis_returns_none(self) -> None:
        """An unquoted "[...]" label containing "(" (e.g. "S1[Intel (INTC.US)]")
        fails mermaid's real flowchart parser outright — confirmed against the
        installed mermaid package, not just a style preference."""
        raw = "flowchart TB\n  S1[Intel (INTC.US)<br/>CPU供應商]\n  C[Center]\n  S1 --> C"
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_quoted_label_with_parenthesis_is_allowed(self) -> None:
        raw = 'flowchart TB\n  S1["Intel (INTC.US)<br/>CPU供應商"]\n  C["Center"]\n  S1 --> C'
        result = validate_value_network_mermaid(raw)
        self.assertEqual(result, raw.strip())

    def test_digit_leading_subgraph_id_returns_none(self) -> None:
        raw = 'flowchart TB\n  subgraph 1S["Suppliers"]\n    A[X]\n  end'
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_quoted_ticker_parentheses_do_not_inflate_node_count(self) -> None:
        """Phase 18E v3: "Company (TICKER.US)"-style labels must not be misread as extra node ids."""
        raw = (
            'flowchart TB\n'
            '  C["MSFT (MSFT.US)<br/>Microsoft"]\n'
            '  S1["AI晶片<br/>NVIDIA (NVDA.US)"]\n'
            '  S1 --> C'
        )
        result = validate_value_network_mermaid(raw)
        self.assertEqual(result, raw.strip())

    def test_us_and_tw_ticker_labels_are_accepted(self) -> None:
        raw = (
            'flowchart TB\n'
            '  C["TSMC (2330.TW)<br/>台積電"]\n'
            '  R1["NVIDIA (NVDA.US)<br/>AI GPU"]\n'
            '  R1 --> C'
        )
        result = validate_value_network_mermaid(raw)
        self.assertEqual(result, raw.strip())

    def test_korean_numeric_ticker_label_is_accepted(self) -> None:
        raw = (
            'flowchart TB\n'
            '  C["MediaTek (2454.TW)<br/>聯發科"]\n'
            '  S1["記憶體<br/>Samsung (005930)"]\n'
            '  S1 --> C'
        )
        result = validate_value_network_mermaid(raw)
        self.assertEqual(result, raw.strip())

    def test_compact_msft_style_graph_is_accepted(self) -> None:
        """The exact dagre-validated MSFT baseline skeleton from
        docs/phase-18e-value-network-2x2-handover.md section 3.4/6.1."""
        raw = """flowchart TB
  C["MSFT (MSFT.US)<br/>Microsoft"]

  subgraph S["供應商"]
    direction TB
    S1["AI晶片<br/>NVIDIA (NVDA.US)"]
    S2["雲端硬體<br/>Dell (DELL.US)"]
    S3["資料中心電力<br/>REITs"]
    S1 ~~~ S2
    S2 ~~~ S3
  end

  subgraph K["客戶"]
    direction TB
    K1["企業客戶"]
    K2["開發者 / GitHub"]
    K3["政府 / 教育機構"]
    K1 ~~~ K2
    K2 ~~~ K3
  end

  subgraph R["競爭者"]
    direction TB
    R1["AWS (AMZN.US)"]
    R2["Google Cloud (GOOGL.US)"]
    R3["Apple (AAPL.US)"]
    R1 ~~~ R2
    R2 ~~~ R3
  end

  subgraph P["互補者"]
    direction TB
    P1["OpenAI 生態"]
    P2["Copilot 第三方整合商"]
    P3["雲端綁定夥伴"]
    P1 ~~~ P2
    P2 ~~~ P3
  end

  S3 --> C
  K3 --> C
  C --> R1
  C --> P1

  classDef card fill:#1f2937,stroke:#374151,color:#f9fafb
  classDef center fill:#2563eb,stroke:#1e40af,color:#ffffff
  class S1,S2,S3,K1,K2,K3,R1,R2,R3,P1,P2,P3 card
  class C center"""
        result = validate_value_network_mermaid(raw)
        self.assertEqual(result, raw.strip())

    def test_compact_2454_style_graph_is_accepted(self) -> None:
        """The exact dagre-validated MediaTek (2454) baseline skeleton from
        docs/phase-18e-value-network-2x2-handover.md section 6.2."""
        raw = """flowchart TB
  C["MediaTek (2454.TW)<br/>聯發科"]

  subgraph S["供應商"]
    direction TB
    S1["晶圓代工<br/>TSMC (2330.TW)"]
    S2["IP授權<br/>ARM"]
    S3["記憶體<br/>Samsung (005930)"]
    S1 ~~~ S2
    S2 ~~~ S3
  end

  subgraph K["客戶"]
    direction TB
    K1["手機品牌<br/>小米 / OPPO"]
    K2["IoT / 車用客戶"]
    K3["電視 / 機頂盒客戶"]
    K1 ~~~ K2
    K2 ~~~ K3
  end

  subgraph R["競爭者"]
    direction TB
    R1["Qualcomm (QCOM.US)"]
    R2["展銳"]
    R3["海思"]
    R1 ~~~ R2
    R2 ~~~ R3
  end

  subgraph P["互補者"]
    direction TB
    P1["聯詠 (3034.TW)"]
    P2["瑞昱 (2379.TW)"]
    P3["大立光 (3008.TW)"]
    P1 ~~~ P2
    P2 ~~~ P3
  end

  S3 --> C
  K3 --> C
  C --> R1
  C --> P1

  classDef card fill:#1f2937,stroke:#374151,color:#f9fafb
  classDef center fill:#2563eb,stroke:#1e40af,color:#ffffff
  class S1,S2,S3,K1,K2,K3,R1,R2,R3,P1,P2,P3 card
  class C center"""
        result = validate_value_network_mermaid(raw)
        self.assertEqual(result, raw.strip())


if __name__ == "__main__":
    unittest.main()
