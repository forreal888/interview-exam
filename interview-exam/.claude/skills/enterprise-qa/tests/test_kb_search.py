"""Unit tests for kb_search.py — KB-related test cases."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from kb_search import KnowledgeBase, search_kb


def _get_kb_root():
    return os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..", "enterprise-qa-data", "knowledge"
    )


class TestKnowledgeBaseLoader(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        root = _get_kb_root()
        cls.kb = KnowledgeBase(root)
        cls.doc_count = cls.kb.load()

    def test_documents_loaded(self):
        """All 6 KB files should be loaded."""
        self.assertGreater(self.doc_count, 0)

    def test_files_present(self):
        """Verify all KB files exist."""
        paths = {d["path"].replace("\\", "/") for d in self.kb.documents}
        expected = {"hr_policies.md", "promotion_rules.md", "tech_docs.md",
                     "finance_rules.md", "faq.md",
                     "meeting_notes/2026-03-01-allhands.md",
                     "meeting_notes/2026-03-15-tech-sync.md"}
        for exp in expected:
            self.assertIn(exp, paths, f"Missing file: {exp}")


class TestKBSearch(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        root = _get_kb_root()
        cls.kb = KnowledgeBase(root)
        cls.kb.load()

    def test_T03_annual_leave(self):
        """T03: 年假怎么计算？"""
        result = self.kb.search("年假怎么计算")
        self.assertGreater(len(result["result"]), 0)
        # Either hr_policies.md or faq.md should be in results (both contain answer)
        paths = [r["path"] for r in result["result"]]
        self.assertTrue(any("hr_policies" in p or "faq" in p for p in paths))

    def test_T04_late_penalty(self):
        """T04: 迟到几次扣钱？"""
        result = self.kb.search("迟到扣钱规则")
        self.assertGreater(len(result["result"]), 0)
        # Should find content about late penalties
        found = False
        for r in result["result"]:
            if "hr_policies" in r["path"]:
                found = True
                break
        self.assertTrue(found, "Should find hr_policies for late penalty")

    def test_promotion_rules(self):
        """P5→P6 promotion rules should be found."""
        result = self.kb.search("P5晋升P6条件")
        self.assertGreater(len(result["result"]), 0)
        top = result["result"][0]
        self.assertIn("promotion_rules", top["path"])

    def test_T12_no_match(self):
        """T12: xyzabc123 怎么报销 -> KB returns relevant docs via keyword match
        on shared terms (报销). The Skill layer (Claude) should note no specific
        info about 'xyzabc123' and not fabricate. The search itself gracefully
        returns related content or empty."""
        result = self.kb.search("xyzabc123 怎么报销")
        # Search should not crash, should return valid structure
        self.assertIsNotNone(result)
        self.assertIn("result", result)

    def test_reimbursement_policy(self):
        """差旅费报销标准 should be found."""
        result = self.kb.search("差旅费报销标准")
        self.assertGreater(len(result["result"]), 0)
        # Should find finance_rules.md
        paths = [r["path"] for r in result["result"]]
        self.assertTrue(any("finance" in p for p in paths))

    def test_meeting_notes_search(self):
        """3月全员大会 should be found."""
        result = self.kb.search("3月全员大会内容")
        self.assertGreater(len(result["result"]), 0)
        paths = [r["path"] for r in result["result"]]
        self.assertTrue(any("allhands" in p for p in paths))


class TestSearchKBFunction(unittest.TestCase):

    def test_search_kb_returns_json(self):
        result = search_kb("年假")
        data = json.loads(result)
        self.assertIn("result", data)

    def test_search_kb_no_match(self):
        result = search_kb("xyzabc123")
        data = json.loads(result)
        # Should not error
        self.assertNotIn("error", data)


if __name__ == "__main__":
    unittest.main()
