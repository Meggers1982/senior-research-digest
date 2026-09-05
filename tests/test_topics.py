"""The rotation's topic names, shared by the dashboard and the trends layer."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import build_dashboard_data as bdd  # noqa: E402
import topics  # noqa: E402
import trends  # noqa: E402


class TopicAliasTests(unittest.TestCase):
    def test_the_rename_resolves_to_one_beat(self):
        self.assertEqual(topics.normalize_topic("Fall Prevention"), "falls")
        self.assertEqual(topics.normalize_topic("falls"), "falls")

    def test_an_unaliased_topic_keeps_its_own_name(self):
        self.assertEqual(topics.normalize_topic(" Sarcopenia "), "Sarcopenia")

    def test_the_dashboard_and_trends_share_one_table(self):
        """These drifted apart once already: the dashboard learned the rename
        and trends.py did not, so the first "falls" run was told it had no
        predecessor a week after a "Fall Prevention" one."""
        self.assertIs(bdd.normalize_topic, topics.normalize_topic)
        self.assertIs(trends.normalize_topic, topics.normalize_topic)


class PreviousDigestTests(unittest.TestCase):
    def _digest(self, directory, name, focus, run_date):
        (directory / name).write_text(
            f"# Senior Living Research Digest — {focus}\n"
            f"**Focus:** {focus}\n**Run date:** {run_date}\n", encoding="utf-8")

    def test_a_renamed_topic_still_finds_its_predecessor(self):
        import tempfile
        with tempfile.TemporaryDirectory() as raw:
            d = Path(raw)
            self._digest(d, "aug-21.md", "Fall Prevention", "2026-08-21")
            found = trends._find_previous_digest("falls", d)
            self.assertIsNotNone(found, "the pre-rename digest was invisible")
            self.assertEqual(found[0].name, "aug-21.md")

    def test_an_unrelated_topic_is_not_matched(self):
        import tempfile
        with tempfile.TemporaryDirectory() as raw:
            d = Path(raw)
            self._digest(d, "aug-21.md", "Sarcopenia", "2026-08-21")
            self.assertIsNone(trends._find_previous_digest("falls", d))


if __name__ == "__main__":
    unittest.main()
