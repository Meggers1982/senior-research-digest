"""The dashboard is plain JS reading JSON that Python writes.

Nothing but these tests connects the two, so a renamed field fails silently in
the browser rather than in CI. Two layers: a contract check that reads the inline
script as text, and a render check that actually executes it in Node over a real
run — because reading the source cannot catch a ReferenceError, and one shipped
that way in the sibling repo under a green pipeline.
"""
import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import build_dashboard_data as bdd  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = REPO_ROOT / "docs" / "index.html"
DOCS_DIR = REPO_ROOT / "docs"
HARNESS = Path(__file__).with_name("dashboard_harness.mjs")
NODE = shutil.which("node")


def dashboard_html() -> str:
    return DASHBOARD.read_text(encoding="utf-8")


def dashboard_js() -> str:
    match = re.search(r"<script>(.*?)</script>", dashboard_html(), re.S)
    assert match, "dashboard has no inline script"
    return match.group(1)


def _top_level_items(source: str) -> list:
    """Split a JS array body on its own commas, ignoring nested calls and
    strings — the row builder has both, so str.split(",") miscounts it."""
    items, depth, quote, current = [], 0, None, ""
    for char in source:
        if quote:
            current += char
            if char == quote:
                quote = None
            continue
        if char in "\"'":
            quote, current = char, current + char
        elif char in "([{":
            depth, current = depth + 1, current + char
        elif char in ")]}":
            depth, current = depth - 1, current + char
        elif char == "," and depth == 0:
            items.append(current)
            current = ""
        else:
            current += char
    if current.strip():
        items.append(current)
    return [i for i in items if i.strip()]


def js_function(name: str) -> str:
    """One function's source.

    The contract checks have to be scoped to where the contract actually lives:
    `s` and `r` are also used for a fact-check summary and a citation row in the
    export code, so a script-wide regex reports those as missing study fields.
    """
    js = dashboard_js()
    start = js.index(f"function {name}(")
    end = js.index("\n}", start)
    return js[start:end]


class ContractTests(unittest.TestCase):
    """Every field the script reads has to exist in what the builder writes."""

    @classmethod
    def setUpClass(cls):
        cls.js = dashboard_js()
        runs = bdd.build()
        assert runs, "no runs to check the contract against"
        cls.run_doc = runs[0]
        cls.study = cls.run_doc["studies"][0]
        cls.entry = bdd._index_entry(cls.run_doc)

    def test_every_run_field_the_dashboard_reads_exists(self):
        used = set(re.findall(r"\brun\.([a-z_]+)", self.js))
        self.assertTrue(used, "no run fields found; the regex needs updating")
        self.assertEqual(sorted(f for f in used if f not in self.run_doc), [])

    def test_every_study_field_the_dashboard_reads_exists(self):
        used = set(re.findall(r"\bstudy\.([a-z_0-9]+)", js_function("renderStudy")))
        self.assertTrue(used, "no study fields found; the regex needs updating")
        self.assertEqual(sorted(f for f in used if f not in self.study), [])

    def test_every_index_field_the_dashboard_reads_exists(self):
        used = set(re.findall(r"\br\.([a-z_]+)", js_function("renderSidebar")))
        self.assertTrue(used, "no index fields found; the regex needs updating")
        self.assertEqual(sorted(f for f in used if f not in self.entry), [])

    def test_the_csv_export_writes_the_fields_it_names(self):
        """The header and the row builder are two lists that must stay aligned."""
        source = js_function("exportRunToCsv")
        header = re.search(r"const header = \[(.*?)\];", source, re.S).group(1)
        names = re.findall(r'"([a-z_]+)"', header)
        self.assertEqual(len(names), len(set(names)))
        rows = re.search(r"const rows = run\.studies\.map\(s => \[(.*?)\]\);",
                         source, re.S).group(1)
        self.assertEqual(len(names), len(_top_level_items(rows)))

    def test_the_dashboard_fetches_the_paths_the_builder_writes(self):
        self.assertIn('fetch("data/index.json")', self.js)
        self.assertIn("data/runs/", self.js)
        self.assertTrue((DOCS_DIR / "data" / "index.json").exists())

    def test_scoring_reaches_the_page(self):
        """The whole point of the scorer is that a reader can filter on it."""
        for field in ("score", "band", "evidence_type", "coverage_state", "tags"):
            self.assertIn(field, self.study, field)
            self.assertIn(field, self.js, field)

    def test_every_jump_target_is_a_real_section(self):
        targets = set(re.findall(r'href="#([a-z-]+)"', self.js))
        targets |= {m for m in re.findall(r'\["([a-z-]+)", "[A-Z]', self.js)}
        built = set(re.findall(r'sectionBlock\("([a-z-]+)"', self.js))
        self.assertTrue(built)
        self.assertEqual(targets - built - {""}, set())

    def test_the_run_document_is_json_serializable(self):
        json.dumps(self.run_doc, ensure_ascii=False)


class BehaviourTests(unittest.TestCase):
    """Things a past fix put in that a restyle could quietly take back out."""

    @classmethod
    def setUpClass(cls):
        cls.js = dashboard_js()
        cls.html = dashboard_html()

    def test_light_is_the_default_rather_than_the_os_preference(self):
        """The [data-theme] rules existed for months with nothing setting the
        attribute, so a dark-mode browser could never reach the light palette."""
        self.assertIn('<html lang="en" data-theme="light">', self.html)
        self.assertIn("document.documentElement.dataset.theme", self.js)
        self.assertIn('getElementById("theme-toggle")', self.js)

    def test_the_collapse_control_stays_findable(self):
        """It shipped invisible once; the caret size and the hint's resting
        opacity are the fix, not decoration."""
        self.assertRegex(self.html, r"\.section-caret\s*\{[^}]*font-size:\s*1\.25rem")
        self.assertRegex(self.html, r"\.section-hint\s*\{[^}]*opacity:\s*0\.6")

    def test_the_pitch_comes_before_the_studies(self):
        """It used to sit below ~21 study cards, which is where the reader gives
        up. The section order in renderMain is the whole fix."""
        body = self.js[self.js.index("main.innerHTML = `"):]
        self.assertLess(body.index("${pitchHtml}"), body.index("${studiesHtml}"))
        self.assertLess(body.index("${pitchIdeasHtml}"), body.index("${studiesHtml}"))

    def test_status_and_collapse_state_are_persisted(self):
        self.assertIn("STATUS_KEY", self.js)
        self.assertIn("localStorage.setItem(STATUS_KEY", self.js)
        self.assertIn("COLLAPSE_KEY", self.js)

    def test_both_exports_are_wired(self):
        self.assertIn("export-docx-btn", self.js)
        self.assertIn("export-csv-btn", self.js)

    def test_the_limits_panel_is_built_from_the_run_not_boilerplate(self):
        self.assertIn("function limitNotes(run)", self.js)
        self.assertIn("coverage_state", self.js)


@unittest.skipIf(NODE is None, "node is not installed")
class RenderTests(unittest.TestCase):
    """Actually execute the script. The rest of this file reads it as text."""

    @classmethod
    def setUpClass(cls):
        cls.rendered = cls._render(dashboard_html())

    @staticmethod
    def _render(html: str) -> str:
        script = re.search(r"<script>(.*?)</script>", html, re.S)
        assert script, "dashboard has no inline script"
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "script.js").write_text(script.group(1), encoding="utf-8")
            (root / "page.html").write_text(html, encoding="utf-8")
            result = subprocess.run(
                [NODE, str(HARNESS), str(root / "script.js"),
                 str(root / "page.html"), str(DOCS_DIR)],
                capture_output=True, text=True, timeout=60,
            )
        if result.returncode != 0:
            raise AssertionError(result.stderr.strip() or "render failed")
        return result.stdout

    def test_the_page_renders_without_throwing(self):
        self.assertGreater(len(self.rendered), 500)

    def test_the_sections_a_reader_comes_for_are_present(self):
        for section in ("feature-pitch", "studies", "limits"):
            self.assertIn(f'id="{section}"', self.rendered, section)

    def test_the_stat_tiles_render_numbers(self):
        self.assertIn("studies selected", self.rendered)
        self.assertIn("scored as leads", self.rendered)

    def test_studies_render_with_their_band_and_score(self):
        self.assertIn("band-chip", self.rendered)
        self.assertIn("score-chip", self.rendered)

    def test_the_facets_render(self):
        self.assertIn('data-facet="band"', self.rendered)
        self.assertIn("status-picker", self.rendered)

    def test_a_reference_error_would_fail_this_test(self):
        """Guards the guard: if the harness stopped detecting errors, every test
        above would pass against a broken page."""
        broken = dashboard_html().replace(
            "function renderStudy(", "function renderStudy(){ return nope.missing; }\nfunction _unused(", 1
        )
        with self.assertRaises(AssertionError):
            self._render(broken)


if __name__ == "__main__":
    unittest.main()
