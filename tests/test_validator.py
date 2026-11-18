import json
import tempfile
import unittest
from pathlib import Path

from api_validator import (
    RULES_PATH,
    diff_specs,
    format_sarif_report,
    load_config,
    load_rules,
    load_spec,
    main,
    parse_simple_yaml,
    validate_spec,
)


class TestAPIDesignValidator(unittest.TestCase):
    def setUp(self) -> None:
        self.rules_data = load_rules(RULES_PATH)
        self.rules_by_id = {r["id"]: r for r in self.rules_data["rules"]}
        self.base_dir = Path(__file__).resolve().parent.parent
        self.good_spec = self.base_dir / "examples" / "orders-api-good.openapi.json"
        self.good_yaml = self.base_dir / "examples" / "orders-api-good.openapi.yaml"
        self.bad_spec = self.base_dir / "examples" / "orders-api-bad.openapi.json"

    def test_rules_catalog_integrity(self) -> None:
        rules = self.rules_data["rules"]
        self.assertEqual(len(rules), 44)
        self.assertEqual(self.rules_data["metadata"]["total_rules"], 44)
        self.assertEqual(sum(1 for r in rules if r["automatable"]), 32)
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

    def test_stdlib_yaml_parser_and_yaml_spec_validation(self) -> None:
        raw_yaml = self.good_yaml.read_text(encoding="utf-8")
        parsed = parse_simple_yaml(raw_yaml)
        self.assertEqual(parsed["openapi"], "3.1.0")
        self.assertIn("/v1/orders", parsed["paths"])
        config = load_config(None, preset="strict-public-api")
        res = validate_spec(parsed, self.rules_by_id, config, spec_label=str(self.good_yaml))
        self.assertTrue(res["passed"], f"Unexpected findings: {res['findings']}")
        self.assertEqual(res["score"], 100)

    def test_bad_spec_catches_core_violations(self) -> None:
        doc = load_spec(self.bad_spec)
        config = load_config(None)
        res = validate_spec(doc, self.rules_by_id, config, spec_label=str(self.bad_spec))
        self.assertFalse(res["passed"])
        self.assertLess(res["score"], 50)
        found_ids = {f["rule_id"] for f in res["findings"]}
        expected_ids = {
            "ADP-001", "ADP-002", "ADP-003", "ADP-004", "ADP-005",
            "ADP-006", "ADP-007", "ADP-008", "ADP-009", "ADP-010",
            "ADP-012", "ADP-013", "ADP-014", "ADP-015", "ADP-016",
            "ADP-017", "ADP-018", "ADP-020", "ADP-021", "ADP-022",
            "ADP-028", "ADP-029", "ADP-030", "ADP-033", "ADP-034",
            "ADP-035",
        }
        self.assertTrue(expected_ids.issubset(found_ids), f"Missing rules: {expected_ids - found_ids}")

    def test_presets_and_team_config_overrides(self) -> None:
        doc = load_spec(self.bad_spec)
        owasp_cfg = load_config(None, preset="owasp-api-top10")
        res_owasp = validate_spec(doc, self.rules_by_id, owasp_cfg)
        found_owasp = {f["rule_id"] for f in res_owasp["findings"]}
        self.assertNotIn("ADP-002", found_owasp)
        self.assertIn("ADP-021", found_owasp)

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

    def test_diff_detects_breaking_and_additive_changes(self) -> None:
        base_doc = load_spec(self.good_spec)
        head_doc = json.loads(json.dumps(base_doc))
        # Remove DELETE operation and change amount_minor type
        del head_doc["paths"]["/v1/orders/{order_id}"]["delete"]
        head_doc["components"]["schemas"]["Order"]["properties"]["amount_minor"]["type"] = "string"
        head_doc["paths"]["/v1/customers"] = {"get": {"responses": {"200": {"description": "OK"}}}}

        diff_res = diff_specs(base_doc, head_doc)
        self.assertFalse(diff_res["passed"])
        self.assertGreaterEqual(diff_res["breaking_changes"], 2)
        self.assertGreaterEqual(diff_res["non_breaking_changes"], 1)

    def test_sarif_export_and_cli_exit_codes(self) -> None:
        doc = load_spec(self.bad_spec)
        res = validate_spec(doc, self.rules_by_id, load_config(None), spec_label="bad.json")
        sarif = json.loads(format_sarif_report([res], self.rules_by_id))
        self.assertEqual(sarif["version"], "2.1.0")
        self.assertGreater(len(sarif["runs"][0]["results"]), 0)

        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "report.sarif"
            code_bad = main(["--spec", str(self.bad_spec), "--format", "sarif", "--output", str(out_path)])
            self.assertEqual(code_bad, 1)
            self.assertTrue(out_path.exists())

            code_good = main(["--spec", str(self.good_yaml), "--preset", "strict-public-api"])
            self.assertEqual(code_good, 0)

    def test_new_core_rules_and_zalando_preset(self) -> None:
        spec = {
            "openapi": "3.1.0",
            "info": {"title": "Mixed API", "version": "1.0.0"},
            "servers": [{"url": "https://api.example.com/v1"}],
            "security": [{"BearerAuth": []}],
            "paths": {
                "/v1/orders/{order_id}/items:batch": {
                    "post": {
                        "operationId": "batchOrderItems",
                        "summary": "Batch add order items",
                        "parameters": [
                            {"name": "Idempotency-Key", "in": "header", "required": True, "schema": {"type": "string", "format": "uuid"}}
                        ],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "text/plain": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "orderId": {"type": "string", "maxLength": 64},
                                            "items": {
                                                "type": "array",
                                                "maxItems": 500,
                                                "items": {"type": "string", "maxLength": 64},
                                            },
                                        },
                                    },
                                    "example": {"orderId": "1", "items": ["sku_1"]},
                                }
                            },
                        },
                        "responses": {
                            "200": {
                                "description": "OK",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "created_at": {"type": "string", "format": "date-time"}
                                            },
                                        },
                                        "example": {"created_at": "2026-11-16T10:00:00Z"},
                                    }
                                },
                            },
                            "400": {"$ref": "#/components/responses/Problem"},
                            "429": {"$ref": "#/components/responses/Problem"},
                        },
                    }
                }
            },
            "components": {
                "securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer"}},
                "schemas": {"order_dto": {"type": "object"}},
                "responses": {
                    "Problem": {
                        "description": "Error",
                        "content": {
                            "application/problem+json": {
                                "schema": {"type": "object"},
                                "example": {"title": "Err", "status": 400},
                            }
                        },
                    }
                },
            },
        }
        zalando_cfg = load_config(None, preset="zalando")
        res = validate_spec(spec, self.rules_by_id, zalando_cfg)
        found = {f["rule_id"] for f in res["findings"]}
        for expected in ("ADP-033", "ADP-035", "ADP-036", "ADP-037", "ADP-038", "ADP-039"):
            self.assertIn(expected, found, f"Missing {expected} in {found}")

    def test_diff_detects_parameter_type_and_enum_changes(self) -> None:
        base_doc = load_spec(self.good_spec)
        head_doc = json.loads(json.dumps(base_doc))
        params = head_doc["paths"]["/v1/orders"]["get"]["parameters"]
        params[1]["schema"]["type"] = "string"
        params[2]["schema"]["enum"] = ["pending", "paid"]
        diff_res = diff_specs(base_doc, head_doc)
        self.assertFalse(diff_res["passed"])
        self.assertGreaterEqual(diff_res["breaking_changes"], 2)


if __name__ == "__main__":
    unittest.main()
