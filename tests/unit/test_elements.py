"""Contract tests use synthetic declarations, never claims of real UI verification."""

import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / ".agents/skills/ai-design-elements"
SCRIPT = SKILL / "scripts/elements.py"
SPEC = importlib.util.spec_from_file_location("elements", SCRIPT)
elements = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(elements)
VERSION = "synthetic/site-a@v1"


def complete_record():
    record = elements.draft("contact-form", "форма связи, contact form", "implementation")
    record.update(project_version=VERSION, design_reference="synthetic DESIGN v1",
                  adaptation="Synthetic token mapping; no animation; not a rendered UI test")
    record["existing"] = {"path": "synthetic/components/contact.html", "decision": "reuse",
                          "reason": "Existing native form fits synthetic task"}
    record["source"].update(url="synthetic/components/contact.html", revision="synthetic-v1",
                            files=["synthetic/components/contact.html"], inspected=True)
    record["source"]["license"].update(name="Synthetic owner-authored fixture",
        evidence="synthetic/provenance.md", checked_on="2026-10-19", rights="confirmed",
        notice="Not applicable: synthetic authored fixture")
    record["dependencies"].update(reviewed=True, compatibility="confirmed", primitive_base="native HTML",
                                    evidence="Synthetic dependency review: no new dependencies")
    for check in record["checks"]:
        check.update(status="pass", version=VERSION, environment="synthetic test declarations",
                     evidence=f"synthetic/{check['area']}.txt")
    return record


def registry(record=None):
    return {"schema_version": "1.0", "components": [record or complete_record()]}


class RecordTests(unittest.TestCase):
    def assess(self, record):
        elements.validate_records(registry(record))
        return elements.assess(record, VERSION)

    def test_complete_declarations_are_only_verified_record(self):
        result = self.assess(complete_record())
        self.assertEqual(result, {"id": "contact-form", "status": "verified-record", "reasons": []})

    def test_unknown_rights_stay_candidate(self):
        record = complete_record()
        record["source"]["license"]["rights"] = "unknown"
        self.assertEqual(self.assess(record)["status"], "candidate")

    def test_denied_redistribution_is_blocked_even_with_passes(self):
        record = complete_record()
        record["source"]["license"].update(usage="redistribution", rights="denied")
        self.assertEqual(self.assess(record)["status"], "blocked")

    def test_incompatible_stack_is_blocked(self):
        record = complete_record()
        record["dependencies"]["compatibility"] = "incompatible"
        self.assertEqual(self.assess(record)["status"], "blocked")

    def test_unreviewed_dependencies_and_missing_notices(self):
        for path in (("dependencies", "reviewed"), ("source", "inspected"),
                     ("source", "license", "notice")):
            with self.subTest(path=path):
                record = complete_record()
                target = record
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = False if path[-1] in ("reviewed", "inspected") else ""
                self.assertEqual(self.assess(record)["status"], "candidate")

    def test_external_component_needs_upstream_license(self):
        record = complete_record()
        record["source"].update(kind="external", url="https://example.org/components/form")
        result = self.assess(record)
        self.assertEqual(result["status"], "candidate")
        self.assertTrue(any("license.evidence" in reason for reason in result["reasons"]))
        record["source"]["license"]["evidence"] = "https://example.org/commit/123/LICENSE"
        self.assertEqual(self.assess(record)["status"], "verified-record")

    def test_record_version_mismatch_reopens_verification(self):
        record = complete_record()
        record["project_version"] = "synthetic/site-b@v1"
        self.assertEqual(self.assess(record)["status"], "ready-to-adapt")

    def test_stale_check_does_not_count(self):
        record = complete_record()
        record["checks"][0]["version"] = "old"
        self.assertEqual(self.assess(record)["status"], "ready-to-adapt")

    def test_mutable_upstream_reference_does_not_complete_selection(self):
        for revision in ("latest", "main", "HEAD", "^1.2.0", "~1.2.0", "*"):
            with self.subTest(revision=revision):
                record = complete_record()
                record["source"]["revision"] = revision
                self.assertEqual(self.assess(record)["status"], "candidate")

    def test_additional_failure_is_not_hidden_by_pass(self):
        record = complete_record()
        failure = copy.deepcopy(record["checks"][1])
        failure.update(status="fail", reason="Synthetic keyboard failure")
        record["checks"].append(failure)
        self.assertEqual(self.assess(record)["status"], "needs-work")

    def test_additional_unchecked_test_keeps_area_open(self):
        record = complete_record()
        record["checks"].append(dict(record["checks"][1], status="not-checked"))
        self.assertEqual(self.assess(record)["status"], "ready-to-adapt")

    def test_missing_area_or_evidence_cannot_pass(self):
        for scenario in ("missing-area", "no-evidence", "no-environment"):
            with self.subTest(scenario=scenario):
                record = complete_record()
                if scenario == "missing-area":
                    record["checks"].pop()
                else:
                    record["checks"][0]["evidence" if scenario == "no-evidence" else "environment"] = " "
                self.assertEqual(self.assess(record)["status"], "ready-to-adapt")

    def test_not_applicable_needs_current_version_and_reason(self):
        record = complete_record()
        record["checks"][3].update(status="not-applicable", evidence="", reason="")
        self.assertEqual(self.assess(record)["status"], "ready-to-adapt")
        record["checks"][3]["reason"] = "Synthetic scope has no runtime change"
        self.assertEqual(self.assess(record)["status"], "verified-record")

    def test_invalid_field_type_duplicate_id_and_date_are_rejected(self):
        bad_values = []
        for field, value in (("approved", True), ("checks", "pass"), ("id", 17)):
            data = registry()
            data["components"][0][field] = value
            bad_values.append(data)
        data = registry()
        data["components"][0]["source"]["inspected"] = "false"
        bad_values.append(data)
        data = registry()
        data["components"].append(copy.deepcopy(data["components"][0]))
        bad_values.append(data)
        data = registry()
        data["components"][0]["source"]["license"]["checked_on"] = "2026-99-99"
        bad_values.append(data)
        for data in bad_values:
            with self.subTest(data=data):
                with self.assertRaises(elements.RecordError):
                    elements.validate_records(data)


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="elements tests ")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)

    def run_cli(self, *args, script=SCRIPT):
        result = subprocess.run([sys.executable, str(script), *map(str, args)], cwd=self.work,
                                capture_output=True, text=True, timeout=10)
        return result.returncode, json.loads(result.stdout)

    def save(self, data):
        path = self.work / "records.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def test_russian_and_english_search(self):
        for query in ("форма", "form"):
            code, result = self.run_cli("search", query, "--stack", "react", "--limit", "43")
            self.assertEqual(code, 0)
            self.assertTrue(result["resources"])
            self.assertTrue(all("react" in row["stack"].lower() for row in result["resources"]))
            self.assertTrue(all("evidence_status" in row for row in result["resources"]))

    def test_category_free_html_filter_and_no_matches(self):
        _, result = self.run_cli("search", "--category", "headless")
        self.assertTrue(result["resources"])
        self.assertTrue(all(row["category"] == "headless" for row in result["resources"]))
        _, result = self.run_cli("search", "кнопка", "--stack", "html", "--access", "free")
        self.assertTrue(result["resources"])
        self.assertTrue(all(row["access"] == "free" and "html" in row["stack"].lower()
                            for row in result["resources"]))
        _, result = self.run_cli("search", "no-such-synthetic-source")
        self.assertEqual(result["matched"], {"local": 0, "resources": 0})

    def test_exact_source_exposes_license_caveat(self):
        _, result = self.run_cli("search", "--id", "react-bits")
        self.assertEqual(len(result["resources"]), 1)
        self.assertIn("Commons Clause", result["resources"][0]["license_note"])
        self.assertEqual(result["resources"][0]["review_status"], "catalogued-not-security-audited")

    def test_catalog_keeps_source_claims_separate_from_component_approval(self):
        catalog = elements.load_json(SKILL / "resources/catalog.json")
        rows = {row["id"]: row for row in catalog["resources"]}
        self.assertEqual(len(rows), 43)
        self.assertEqual(len(catalog["resources"]), len(rows))
        checked = [row["id"] for row in rows.values() if row["source_checks"]]
        self.assertCountEqual(checked, ["shadcn-ui", "react-bits"])
        for row in rows.values():
            self.assertEqual(row["review_status"], "catalogued-not-security-audited")
            self.assertEqual(row["evidence_status"], "source-docs-checked" if row["source_checks"] else "research-only")
            self.assertTrue(row["search_terms_en"] and row["search_terms_ru"])

    def test_local_registry_search_and_read_only_commands(self):
        path = self.save(registry())
        before = path.read_bytes()
        _, result = self.run_cli("search", "форма", "--records", path)
        self.assertEqual(result["local_records"][0]["existing"]["decision"], "reuse")
        self.assertEqual(path.read_bytes(), before)
        code, result = self.run_cli("check", path, "--project-version", "synthetic/site-b@v1")
        self.assertEqual(code, 1)
        self.assertNotEqual(result["components"][0]["status"], "verified-record")
        self.assertEqual(path.read_bytes(), before)

    def test_new_refuses_existing_file_and_symlink(self):
        path = self.work / "ELEMENTS.json"
        code, _ = self.run_cli("new", "--id", "form", "--task", "Связаться", "--out", path)
        self.assertEqual(code, 0)
        before = path.read_bytes()
        code, _ = self.run_cli("new", "--id", "other", "--task", "Other", "--out", path)
        self.assertEqual(code, 2)
        self.assertEqual(path.read_bytes(), before)
        link = self.work / "linked.json"
        link.symlink_to(path)
        code, _ = self.run_cli("new", "--id", "other", "--task", "Other", "--out", link)
        self.assertEqual(code, 2)
        self.assertEqual(path.read_bytes(), before)
        code, result = self.run_cli("check", path, "--project-version", VERSION)
        self.assertEqual(code, 1)
        self.assertEqual(result["components"][0]["status"], "candidate")

    def test_check_success_empty_and_invalid_exit_codes(self):
        path = self.save(registry())
        code, result = self.run_cli("check", path, "--project-version", VERSION)
        self.assertEqual(code, 0)
        self.assertIn("record declarations only", result["scope"])
        path = self.save({"schema_version": "1.0", "components": []})
        self.assertEqual(self.run_cli("check", path, "--project-version", VERSION)[0], 1)
        path.write_text('{"schema_version":"1.0","components":[],"components":[]}', encoding="utf-8")
        self.assertEqual(self.run_cli("check", path, "--project-version", VERSION)[0], 2)
        path.write_text('null', encoding="utf-8")
        self.assertEqual(self.run_cli("check", path, "--project-version", VERSION)[0], 2)
        path.write_text('{', encoding="utf-8")
        self.assertEqual(self.run_cli("check", path, "--project-version", VERSION)[0], 2)

    def test_portable_copy_runs_without_framework_docs(self):
        package = self.work / "isolated skill with spaces"
        shutil.copytree(SKILL, package, ignore=shutil.ignore_patterns("__pycache__"))
        code, result = self.run_cli("search", "форма", script=package / "scripts/elements.py")
        self.assertEqual(code, 0)
        self.assertTrue(result["resources"])


if __name__ == "__main__":
    unittest.main()
