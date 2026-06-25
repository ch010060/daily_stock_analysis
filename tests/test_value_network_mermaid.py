# -*- coding: utf-8 -*-
"""Tests for the Phase 18A value-network Mermaid appendix validator."""

import unittest

from src.services.value_network_mermaid import validate_value_network_mermaid


class ValidateValueNetworkMermaidTestCase(unittest.TestCase):
    def test_valid_flowchart_tb_is_returned_trimmed(self) -> None:
        raw = """
        flowchart TB
            subgraph 供應商
                A[供應商A]
            end
        """
        result = validate_value_network_mermaid(raw)
        self.assertEqual(result, raw.strip())

    def test_valid_flowchart_lr_is_returned_trimmed(self) -> None:
        raw = "flowchart LR\n  A[公司] --> B[客戶]"
        result = validate_value_network_mermaid(raw)
        self.assertEqual(result, raw.strip())

    def test_valid_graph_td_keyword_is_accepted(self) -> None:
        raw = "graph TD\n  A[公司] --> B[客戶]"
        result = validate_value_network_mermaid(raw)
        self.assertEqual(result, raw.strip())

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

    def test_six_subgraphs_returns_none(self) -> None:
        """Phase 18E: the compact appendix allows at most 5 subgraphs (was 8)."""
        lines = ["flowchart TB"]
        for i in range(6):
            lines.append(f"subgraph S{i}")
            lines.append(f"  N{i}[Node{i}]")
            lines.append("end")
        raw = "\n".join(lines)
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_five_subgraphs_is_allowed(self) -> None:
        """Phase 18E: exactly 5 subgraphs (center/供應商/客戶/競爭者/互補者/護城河 shape) is the boundary-allowed case."""
        lines = ["flowchart TB"]
        for i in range(5):
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

    def test_twenty_distinct_nodes_returns_none(self) -> None:
        """Phase 18E: the compact appendix allows at most 18 distinct nodes (was 40)."""
        lines = ["flowchart TB"]
        for i in range(20):
            lines.append(f"N{i}[Node{i}]")
        raw = "\n".join(lines)
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_eighteen_distinct_nodes_is_allowed(self) -> None:
        lines = ["flowchart TB"]
        for i in range(18):
            lines.append(f"N{i}[Node{i}]")
        raw = "\n".join(lines)
        result = validate_value_network_mermaid(raw)
        self.assertEqual(result, raw.strip())

    def test_too_many_edges_returns_none(self) -> None:
        """Phase 18E: at most 12 edges, to keep the appendix from becoming a dense spider graph."""
        lines = ["flowchart TB", "C[Center]"]
        for i in range(13):
            lines.append(f"  N{i}[Node{i}] --> C")
        raw = "\n".join(lines)
        self.assertIsNone(validate_value_network_mermaid(raw))

    def test_twelve_edges_is_allowed(self) -> None:
        lines = ["flowchart TB", "C[Center]"]
        for i in range(12):
            lines.append(f"  N{i}[Node{i}] --> C")
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

    def test_compact_msft_style_graph_is_accepted(self) -> None:
        raw = """flowchart TB
  C["MSFT<br/>Microsoft"]

  subgraph S["供應商"]
    S1["AI晶片<br/>NVIDIA / AMD"]
    S2["資料中心<br/>電力 / REITs"]
  end

  subgraph K["客戶"]
    K1["企業客戶"]
    K2["開發者 / GitHub"]
  end

  subgraph R["競爭者"]
    R1["AWS / Google Cloud"]
    R2["Apple / Salesforce"]
  end

  subgraph P["互補者"]
    P1["OpenAI / Copilot"]
  end

  subgraph M["護城河"]
    M1["雲端 + Office 綁定"]
  end

  S1 --> C
  S2 --> C
  C --> K1
  C --> K2
  R1 -.競爭.-> C
  P1 -.強化.-> C
  C -.支撐.-> M1"""
        result = validate_value_network_mermaid(raw)
        self.assertEqual(result, raw.strip())

    def test_compact_2454_style_graph_is_accepted(self) -> None:
        raw = """flowchart TB
  C["2454<br/>聯發科"]

  subgraph S["供應商"]
    S1["晶圓代工<br/>台積電"]
    S2["IP授權<br/>ARM"]
  end

  subgraph K["客戶"]
    K1["手機品牌<br/>小米 / OPPO"]
    K2["IoT / 車用客戶"]
  end

  subgraph R["競爭者"]
    R1["高通"]
    R2["展銳 / 海思"]
  end

  subgraph P["互補者"]
    P1["聯詠 / 瑞昱"]
  end

  S1 --> C
  C --> K1
  R1 -.競爭.-> C
  P1 -.生態.-> C"""
        result = validate_value_network_mermaid(raw)
        self.assertEqual(result, raw.strip())


if __name__ == "__main__":
    unittest.main()
