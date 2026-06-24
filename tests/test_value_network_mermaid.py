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

    def test_eight_subgraphs_is_allowed(self) -> None:
        lines = ["flowchart TB"]
        for i in range(8):
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


if __name__ == "__main__":
    unittest.main()
