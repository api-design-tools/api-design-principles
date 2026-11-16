import json
import tempfile
import unittest
from pathlib import Path

from api_validator import (
    RULES_PATH,
    load_config,
    load_rules,
    load_spec,
    main,
    validate_spec,
)


class TestAPIDesignValidator(unittest.TestCase):
    def setUp(self) -> None:
        self.rules_data = load_rules(RULES_PATH)
        self.rules_by_id = {r["id"]: r for r in self.rules_data["rules"]}
        self.base_dir = Path(__file__).resolve().parent.parent
        self.good_spec = self.base_dir / "examples" / "orders-api-good.openapi.json"
        self.bad_spec = self.base_dir / "examples" / "orders-api-bad.openapi.json"

    def test_rules_catalog_integrity(self) -> None:
        rules = self.rules_data["rules"]
        self.assertGreaterEqual(len(rules), 30)
        seen_ids = set()
        for rule in rules:
            self.assertIn("id", rule)
            self.assertIn("severity", rule)
            self.assertIn("standard_ref", rule)
            self.assertEqual(rule.get("last_verified"), "2026-11-16")
            self.assertNotIn(rule["id"], seen_ids)
            seen_ids.add(rule["id"])

    def test_good_reference_spec_passes_perfectly(self) -> None:
        doc = load_spec(self.good_spec)
        config = load_config(None)
        config["fail_on"] = "warning"
        res = validate_spec(doc, self.rules_by_id, config, spec_label=str(self.good_spec))
        self.assertTrue(res["passed"])
        self.assertEqual(res["score"], 100)
        self.assertEqual(res["summary"]["errors"], 0)
        self.assertEqual(res["summary"]["warnings"], 0)
        self.assertEqual(res["findings"], [])

    def test_bad_spec_catches_core_violations(self) -> None:
        doc = load_spec(self.bad_spec)
        config = load_config(None)
        res = validate_spec(doc, self.rules_by_id, config, spec_label=str(self.bad_spec))
        self.assertFalse(res["passed"])
        self.assertLess(res["score"], 50)
        found_ids = {f["rule_id"] for f in res["findings"]}
        expected_ids = {
            "ADP-001",  # CRUD verbs in paths
            "ADP-002",  # camelCase / snake_case
            "ADP-003",  # trailing slash
            "ADP-004",  # missing /v1
            "ADP-005",  # GET requestBody
            "ADP-006",  # DELETE requestBody + missing 204
            "ADP-007",  # POST 200 instead of 201
            "ADP-008",  # missing application/problem+json
            "ADP-009",  # missing 4xx
            "ADP-010",  # missing pagination
            "ADP-012",  # missing Idempotency-Key
            "ADP-013",  # missing 429 / RateLimit
            "ADP-014",  # http:// server
            "ADP-015",  # missing securitySchemes
            "ADP-016",  # api_key in query
            "ADP-017",  # duplicate/missing operationId
            "ADP-018",  # deprecated without Sunset
            "ADP-020",  # PUT without If-Match
            "ADP-021",  # unbounded strings/arrays
            "ADP-022",  # created_at missing date-time
        }
        self.assertTrue(expected_ids.issubset(found_ids), f"Missing rules: {expected_ids - found_ids}")

    def test_team_config_disables_and_overrides_rules(self) -> None:
        doc = load_spec(self.bad_spec)
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "team-rules.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "disabled_rules": ["ADP-014", "ADP-018"],
                        "severity_overrides": {"ADP-002": "error"},
                    }
                ),
                encoding="utf-8",
            )
            config = load_config(cfg_path)
            res = validate_spec(doc, self.rules_by_id, config)
            found_ids = {f["rule_id"] for f in res["findings"]}
            self.assertNotIn("ADP-014", found_ids)
            self.assertNotIn("ADP-018", found_ids)
            adp_002_sevs = {f["severity"] for f in res["findings"] if f["rule_id"] == "ADP-002"}
            self.assertEqual(adp_002_sevs, {"error"})

    def test_cli_exit_codes_and_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "report.json"
            code_good = main(["--spec", str(self.good_spec), "--format", "json", "--output", str(out_path)])
            self.assertEqual(code_good, 0)
            self.assertTrue(out_path.exists())
            parsed = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(parsed["results"][0]["score"], 100)

            code_bad = main(["--spec", str(self.bad_spec), "--fail-on", "error"])
            self.assertEqual(code_bad, 1)


if __name__ == "__main__":
    unittest.main()
