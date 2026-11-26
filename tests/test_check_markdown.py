"""Tests for whitespace not covered by the Markdown formatter and linter."""

import unittest

from scripts.check_markdown import whitespace_errors


class MarkdownWhitespaceTests(unittest.TestCase):
    def test_fenced_code_and_blank_line_whitespace_is_rejected(self):
        text = "# Title\n\n```text\nfixture  \n```\n\t\n"
        self.assertEqual(
            whitespace_errors(text),
            ["4: trailing whitespace", "6: trailing whitespace"],
        )

    def test_two_space_hard_break_is_rejected(self):
        self.assertEqual(
            whitespace_errors("# Title\n\nFirst  \nSecond\n"),
            ["3: trailing whitespace"],
        )

    def test_explicit_hard_break_passes(self):
        self.assertEqual(whitespace_errors("# Title\n\nFirst\\\nSecond\n"), [])

    def test_missing_final_newline_is_rejected(self):
        self.assertEqual(
            whitespace_errors("# Title"),
            ["1: missing final newline"],
        )


if __name__ == "__main__":
    unittest.main()
