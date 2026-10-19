"""Regression found by independent BE-07; no assertions of component suitability."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / ".agents/skills/ai-design-elements/scripts/elements.py"


class SearchRegression(unittest.TestCase):
    def test_dialog_search_indexes_both_languages_for_svelte_pointer(self):
        matches = []
        for query in ("dialog", "диалог"):
            result = subprocess.run([sys.executable, str(SCRIPT), "search", query,
                "--stack", "svelte", "--limit", "43"], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0)
            rows = json.loads(result.stdout)["resources"]
            ids = {row["id"] for row in rows}
            self.assertIn("bits-ui", ids)
            self.assertTrue(all(row["review_status"] == "catalogued-not-security-audited" for row in rows))
            matches.append(ids)
        self.assertEqual(matches[0], matches[1])


if __name__ == "__main__":
    unittest.main()
