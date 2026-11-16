#!/usr/bin/env python3
"""
API Design Principles & OpenAPI 3.x Validator CLI (2026)

Zero-dependency OpenAPI 3.0/3.1 linter, team ruleset enforcer, and interactive
API design principles explorer. Designed for local CLI checks and GitHub Actions CI/CD.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

BASE_DIR = Path(__file__).resolve().parent
RULES_PATH = BASE_DIR / "rules.json"

VERB_PREFIX_RE = re.compile(
    r"^(get|list|fetch|read|retrieve|create|add|new|insert|update|edit|modify|"
    r"patch|delete|remove|destroy|erase|set|save|post|put|find|search|query|"
    r"check|verify|validate|send|run|exec|execute|process|handle)[A-Z_-]?",
    re.IGNORECASE,
)
CRUD_EXACT_WORDS = {
    "get", "list", "fetch", "create", "add", "update", "edit",
    "delete", "remove", "destroy", "find", "search", "query",
}
VERSION_SEGMENT_RE = re.compile(r"^/v\d+(?:/|$)|^/api/v\d+(?:/|$)", re.IGNORECASE)
KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
SENSITIVE_QUERY_NAMES = {
    "api_key", "apikey", "token", "access_token", "auth", "authorization",
    "secret", "client_secret", "password", "passwd", "pwd", "jwt", "bearer",
}
PAGINATION_PARAMS = {"cursor", "after", "before", "page_token", "pageToken", "limit", "page_size", "pageSize", "per_page", "page"}
CURSOR_PARAMS = {"cursor", "after", "before", "page_token", "pageToken", "starting_after"}
OFFSET_PARAMS = {"offset", "skip"}
TIMESTAMP_NAMES = ("_at", "timestamp", "createdat", "updatedat", "deletedat", "expiresat")


def load_rules(path: Path = RULES_PATH) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_spec(spec_path: Path) -> Dict[str, Any]:
    raw = spec_path.read_text(encoding="utf-8")
    suffix = spec_path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                f"Cannot parse YAML spec '{spec_path}' without PyYAML. "
                "Convert to OpenAPI JSON or install PyYAML (`pip install pyyaml`)."
            ) from exc
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            raise ValueError(f"Spec '{spec_path}' did not parse into an object.")
        return data
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Spec '{spec_path}' root must be a JSON object.")
    return data


def load_config(config_path: Optional[Path]) -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "organization": "default",
        "ruleset_name": "API Design Principles Standard (2026)",
        "fail_on": "error",
        "allowed_version_prefixes": [],
        "ignore_paths": ["/health", "/healthz", "/readyz", "/metrics"],
        "disabled_rules": [],
        "severity_overrides": {},
    }
    if not config_path:
        return defaults
    loaded = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("Config file must contain a JSON object.")
    merged = {**defaults, **loaded}
    return merged


def resolve_ref(doc: Dict[str, Any], obj: Any, seen: Optional[Set[str]] = None) -> Any:
    if seen is None:
        seen = set()
    if not isinstance(obj, dict):
        return obj
    ref = obj.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return obj
    if ref in seen:
        return obj
    seen.add(ref)
    target: Any = doc
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(target, dict) and part in target:
            target = target[part]
        else:
            return obj
    return resolve_ref(doc, target, seen)


def merge_parameters(
    doc: Dict[str, Any], path_item: Dict[str, Any], operation: Dict[str, Any]
) -> List[Dict[str, Any]]:
    by_key: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for source in (path_item.get("parameters", []), operation.get("parameters", [])):
        if not isinstance(source, list):
            continue
        for raw_param in source:
            param = resolve_ref(doc, raw_param)
            if isinstance(param, dict) and "name" in param and "in" in param:
                by_key[(str(param["in"]), str(param["name"]))] = param
    return list(by_key.values())


def is_collection_path(path: str) -> bool:
    segments = [s for s in path.split("/") if s]
    if not segments:
        return False
    return not (segments[-1].startswith("{") and segments[-1].endswith("}"))


def path_looks_like_action_noun(segment: str) -> bool:
    clean = segment.split(":")[0]
    if clean.lower() in CRUD_EXACT_WORDS:
        return True
    match = VERB_PREFIX_RE.match(clean)
    if not match:
        return False
    prefix = match.group(1).lower()
    # Avoid false positives like "settings", "orders", "returns", "checks"
    if clean.lower() in {"settings", "orders", "returns", "checks", "records", "posts", "sets"}:
        return False
    # Flag camelCase/snake_case/kebab-case CRUD verbs like getUsers, create-order, delete_item
    if len(clean) > len(prefix) and (
        clean[len(prefix)].isupper() or clean[len(prefix)] in {"-", "_"}
    ):
        return True
    return clean.lower() == prefix


def iter_schema_nodes(
    doc: Dict[str, Any], schema: Any, pointer: str, visited: Optional[Set[int]] = None
) -> List[Tuple[str, Dict[str, Any]]]:
    if visited is None:
        visited = set()
    resolved = resolve_ref(doc, schema)
    if not isinstance(resolved, dict):
        return []
    obj_id = id(resolved)
    if obj_id in visited:
        return []
    visited.add(obj_id)
    nodes: List[Tuple[str, Dict[str, Any]]] = [(pointer, resolved)]
    props = resolved.get("properties")
    if isinstance(props, dict):
        for prop_name, prop_schema in props.items():
            nodes.extend(iter_schema_nodes(doc, prop_schema, f"{pointer}.{prop_name}", visited))
    if "items" in resolved:
        nodes.extend(iter_schema_nodes(doc, resolved["items"], f"{pointer}[]", visited))
    for composite in ("allOf", "oneOf", "anyOf"):
        if isinstance(resolved.get(composite), list):
            for idx, sub in enumerate(resolved[composite]):
                nodes.extend(iter_schema_nodes(doc, sub, f"{pointer}.{composite}[{idx}]", visited))
    return nodes


def has_example(doc: Dict[str, Any], media_obj: Dict[str, Any]) -> bool:
    if "example" in media_obj or "examples" in media_obj:
        return True
    schema = resolve_ref(doc, media_obj.get("schema"))
    if not isinstance(schema, dict):
        return False
    if "example" in schema or "examples" in schema:
        return True
    props = schema.get("properties")
    if isinstance(props, dict):
        for prop in props.values():
            r_prop = resolve_ref(doc, prop)
            if isinstance(r_prop, dict) and ("example" in r_prop or "examples" in r_prop):
                return True
    return False


def validate_spec(
    doc: Dict[str, Any],
    rules_by_id: Dict[str, Dict[str, Any]],
    config: Dict[str, Any],
    spec_label: str = "openapi.json",
) -> Dict[str, Any]:
    disabled = set(config.get("disabled_rules", []))
    overrides: Dict[str, str] = config.get("severity_overrides", {})
    ignore_paths = set(config.get("ignore_paths", []))
    allowed_prefixes: List[str] = config.get("allowed_version_prefixes", [])

    findings: List[Dict[str, Any]] = []

    def add_finding(rule_id: str, location: str, message: str) -> None:
        if rule_id in disabled:
            return
        rule = rules_by_id.get(rule_id, {})
        severity = overrides.get(rule_id, rule.get("severity", "warning"))
        findings.append(
            {
                "rule_id": rule_id,
                "severity": severity,
                "category": rule.get("category", "general"),
                "title": rule.get("title", rule_id),
                "standard_ref": rule.get("standard_ref", ""),
                "location": location,
                "message": message,
                "remediation": rule.get("remediation", ""),
            }
        )

    # Global Server HTTPS Check (ADP-014) & base path version detection
    servers = doc.get("servers", [])
    server_has_version = False
    if isinstance(servers, list):
        for idx, srv in enumerate(servers):
            if not isinstance(srv, dict):
                continue
            url = str(srv.get("url", ""))
            if url.startswith("http://") and not any(
                local in url for local in ("localhost", "127.0.0.1", "[::1]")
            ):
                add_finding(
                    "ADP-014",
                    f"servers[{idx}].url",
                    f"Insecure HTTP server URL '{url}' detected; production servers must use https://.",
                )
            if re.search(r"/v\d+(?:/|$)", url, re.IGNORECASE):
                server_has_version = True

    # Global security schemes check (ADP-015)
    components = doc.get("components", {}) if isinstance(doc.get("components"), dict) else {}
    security_schemes = components.get("securitySchemes", {})
    global_security = doc.get("security")
    if not isinstance(security_schemes, dict) or not security_schemes:
        add_finding(
            "ADP-015",
            "components.securitySchemes",
            "No securitySchemes declared in components; explicitly define OAuth2, Bearer JWT, or API Key auth.",
        )

    paths = doc.get("paths", {})
    if not isinstance(paths, dict) or not paths:
        add_finding(
            "ADP-009",
            "paths",
            "OpenAPI specification contains no paths to validate.",
        )

    seen_operation_ids: Dict[str, str] = {}
    operation_count = 0

    if isinstance(paths, dict):
        for path_str, raw_path_item in paths.items():
            if path_str in ignore_paths or not isinstance(raw_path_item, dict):
                continue

            # ADP-003: No trailing slash
            if len(path_str) > 1 and path_str.endswith("/"):
                add_finding(
                    "ADP-003",
                    path_str,
                    f"Path '{path_str}' has a trailing slash; normalize to '{path_str.rstrip('/')}'.",
                )

            # ADP-004: Versioned path or versioned server base URL
            has_allowed_prefix = (
                any(path_str.startswith(p) for p in allowed_prefixes)
                if allowed_prefixes
                else bool(VERSION_SEGMENT_RE.match(path_str))
            )
            if not has_allowed_prefix and not server_has_version:
                add_finding(
                    "ADP-004",
                    path_str,
                    f"Endpoint '{path_str}' has no explicit major version prefix (e.g. /v1/...) and no versioned server URL.",
                )

            # Segment checks: ADP-001 (no verbs) & ADP-002 (kebab-case)
            segments = [s for s in path_str.split("/") if s]
            for seg in segments:
                if seg.startswith("{") and seg.endswith("}"):
                    continue
                if re.fullmatch(r"v\d+", seg, re.IGNORECASE) or seg == "api":
                    continue
                if path_looks_like_action_noun(seg):
                    add_finding(
                        "ADP-001",
                        path_str,
                        f"Segment '{seg}' looks like a CRUD verb; use plural resource nouns and HTTP methods.",
                    )
                if not KEBAB_CASE_RE.match(seg.split(":")[0]):
                    add_finding(
                        "ADP-002",
                        path_str,
                        f"Segment '{seg}' is not lowercase kebab-case (avoid camelCase or snake_case in URIs).",
                    )

            for method_lower, raw_op in raw_path_item.items():
                if method_lower.lower() not in HTTP_METHODS or not isinstance(raw_op, dict):
                    continue
                method = method_lower.upper()
                op_loc = f"{method} {path_str}"
                operation_count += 1

                # ADP-017: Unique operationId & summary
                op_id = raw_op.get("operationId")
                summary = raw_op.get("summary")
                if not isinstance(op_id, str) or not op_id.strip():
                    add_finding(
                        "ADP-017",
                        op_loc,
                        "Missing operationId; deterministic IDs are required for SDK generation and AI/MCP tools.",
                    )
                else:
                    if op_id in seen_operation_ids:
                        add_finding(
                            "ADP-017",
                            op_loc,
                            f"Duplicate operationId '{op_id}' (already used at {seen_operation_ids[op_id]}).",
                        )
                    else:
                        seen_operation_ids[op_id] = op_loc
                if not isinstance(summary, str) or not summary.strip():
                    add_finding(
                        "ADP-017",
                        op_loc,
                        "Missing concise operation summary.",
                    )

                # ADP-015: Operation security
                if "security" not in raw_op and not global_security:
                    if isinstance(security_schemes, dict) and security_schemes:
                        add_finding(
                            "ADP-015",
                            op_loc,
                            "Operation has neither global nor operation-level security applied.",
                        )

                params = merge_parameters(doc, raw_path_item, raw_op)
                param_names = {str(p.get("name", "")) for p in params}
                header_names_lower = {
                    str(p.get("name", "")).lower()
                    for p in params
                    if str(p.get("in", "")).lower() == "header"
                }

                # ADP-016: Sensitive credentials in query params
                for p in params:
                    p_in = str(p.get("in", "")).lower()
                    p_name = str(p.get("name", ""))
                    if p_in == "query" and p_name.lower() in SENSITIVE_QUERY_NAMES:
                        add_finding(
                            "ADP-016",
                            f"{op_loc} (query:{p_name})",
                            f"Sensitive credential parameter '{p_name}' passed in URL query string; move to Authorization header.",
                        )

                # Request body checks
                req_body = resolve_ref(doc, raw_op.get("requestBody"))
                if method in {"GET", "HEAD"} and isinstance(req_body, dict):
                    add_finding(
                        "ADP-005",
                        op_loc,
                        f"{method} operation declares a requestBody, which violates RFC 9110 §9.3.1.",
                    )

                if method == "DELETE" and isinstance(req_body, dict) and req_body.get("required"):
                    add_finding(
                        "ADP-006",
                        op_loc,
                        "DELETE operation requires a requestBody; resource deletion should be self-contained in the URI.",
                    )

                # ADP-020: PUT without If-Match / PATCH recommendation
                if method == "PUT" and "if-match" not in header_names_lower:
                    add_finding(
                        "ADP-020",
                        op_loc,
                        "PUT replacement without If-Match header risks lost updates; prefer PATCH or add ETag/If-Match.",
                    )

                # ADP-012: Idempotency-Key on POST mutations
                if method == "POST" and not path_str.endswith(":search"):
                    if "idempotency-key" not in header_names_lower:
                        add_finding(
                            "ADP-012",
                            op_loc,
                            "POST mutation does not declare an Idempotency-Key header parameter for safe client retries.",
                        )

                # ADP-019 & ADP-021 & ADP-022 on requestBody schemas
                if isinstance(req_body, dict) and isinstance(req_body.get("content"), dict):
                    for media_type, media_obj in req_body["content"].items():
                        if not isinstance(media_obj, dict):
                            continue
                        if not has_example(doc, media_obj):
                            add_finding(
                                "ADP-019",
                                f"{op_loc} requestBody ({media_type})",
                                "Request body lacks an example/examples payload.",
                            )
                        for ptr, node in iter_schema_nodes(
                            doc, media_obj.get("schema"), f"{op_loc}.requestBody"
                        ):
                            n_type = node.get("type")
                            if n_type == "array" and "maxItems" not in node:
                                add_finding(
                                    "ADP-021",
                                    ptr,
                                    "Input array schema has no maxItems bound (OWASP API4:2023 risk).",
                                )
                            if (
                                n_type == "string"
                                and "maxLength" not in node
                                and "enum" not in node
                                and node.get("format") not in {"uuid", "date", "date-time", "email"}
                            ):
                                add_finding(
                                    "ADP-021",
                                    ptr,
                                    "Input string schema has no maxLength or enum bound (OWASP API4:2023 risk).",
                                )

                # Responses analysis
                responses = raw_op.get("responses", {})
                if not isinstance(responses, dict):
                    responses = {}
                resp_codes = {str(k) for k in responses.keys()}

                # ADP-007: POST creation should return 201 or 202
                if method == "POST" and is_collection_path(path_str) and not path_str.endswith(":search"):
                    if "201" not in resp_codes and "202" not in resp_codes:
                        add_finding(
                            "ADP-007",
                            op_loc,
                            "Resource-creating POST should return 201 Created (with Location) or 202 Accepted instead of only 200.",
                        )

                # ADP-006: DELETE should return 204 or 202
                if method == "DELETE" and "204" not in resp_codes and "202" not in resp_codes:
                    add_finding(
                        "ADP-006",
                        op_loc,
                        "DELETE operation should document 204 No Content or 202 Accepted.",
                    )

                # ADP-009: Explicit 4xx / default error responses
                has_error_resp = any(
                    c.startswith("4") or c == "4XX" or c == "default" for c in resp_codes
                )
                if not has_error_resp:
                    add_finding(
                        "ADP-009",
                        op_loc,
                        "Operation defines no explicit 4xx or default error responses.",
                    )

                # ADP-008: RFC 9457 application/problem+json on 4xx/5xx
                error_codes = [
                    c for c in resp_codes if c.startswith("4") or c.startswith("5") or c in {"4XX", "5XX", "default"}
                ]
                if error_codes:
                    non_problem_codes: List[str] = []
                    for ec in error_codes:
                        r_obj = resolve_ref(doc, responses.get(ec))
                        if not isinstance(r_obj, dict):
                            continue
                        content = r_obj.get("content", {})
                        if isinstance(content, dict) and content:
                            if "application/problem+json" not in content:
                                non_problem_codes.append(ec)
                    if non_problem_codes:
                        add_finding(
                            "ADP-008",
                            f"{op_loc} ({','.join(sorted(non_problem_codes))})",
                            "Error responses do not use RFC 9457 media type 'application/problem+json'.",
                        )

                # ADP-013: 429 & RateLimit headers
                has_429 = "429" in resp_codes
                has_rl_headers = False
                for rc, raw_r in responses.items():
                    r_obj = resolve_ref(doc, raw_r)
                    if isinstance(r_obj, dict) and isinstance(r_obj.get("headers"), dict):
                        hdrs_lower = {h.lower() for h in r_obj["headers"].keys()}
                        if any(
                            h.startswith("ratelimit") or h.startswith("x-ratelimit") or h == "retry-after"
                            for h in hdrs_lower
                        ):
                            has_rl_headers = True
                if not has_429 and not has_rl_headers:
                    add_finding(
                        "ADP-013",
                        op_loc,
                        "Operation does not document 429 Too Many Requests or standard RateLimit/Retry-After headers.",
                    )

                # ADP-010 & ADP-011: Collection GET pagination
                if method == "GET" and is_collection_path(path_str):
                    if not (param_names & PAGINATION_PARAMS):
                        add_finding(
                            "ADP-010",
                            op_loc,
                            "Collection GET endpoint has no pagination parameters (cursor/after/limit/page_size).",
                        )
                    elif (param_names & OFFSET_PARAMS) and not (param_names & CURSOR_PARAMS):
                        add_finding(
                            "ADP-011",
                            op_loc,
                            "Collection GET uses offset/skip pagination without keyset cursor; prefer cursor/after for O(1) scaling.",
                        )

                # ADP-018: Deprecated endpoints should expose Deprecation / Sunset headers
                if raw_op.get("deprecated") is True:
                    has_sunset = False
                    for raw_r in responses.values():
                        r_obj = resolve_ref(doc, raw_r)
                        if isinstance(r_obj, dict) and isinstance(r_obj.get("headers"), dict):
                            hdrs_lower = {h.lower() for h in r_obj["headers"].keys()}
                            if "sunset" in hdrs_lower or "deprecation" in hdrs_lower:
                                has_sunset = True
                    if not has_sunset:
                        add_finding(
                            "ADP-018",
                            op_loc,
                            "Deprecated operation lacks Deprecation or Sunset headers (RFC 8594 / RFC 9745).",
                        )

                # ADP-019 & ADP-022 on 2xx response bodies
                for rc, raw_r in responses.items():
                    if not rc.startswith("2"):
                        continue
                    r_obj = resolve_ref(doc, raw_r)
                    if not isinstance(r_obj, dict) or not isinstance(r_obj.get("content"), dict):
                        continue
                    for media_type, media_obj in r_obj["content"].items():
                        if not isinstance(media_obj, dict):
                            continue
                        if not has_example(doc, media_obj):
                            add_finding(
                                "ADP-019",
                                f"{op_loc} {rc} ({media_type})",
                                "Success response lacks an example/examples payload.",
                            )
                        for ptr, node in iter_schema_nodes(
                            doc, media_obj.get("schema"), f"{op_loc}.{rc}"
                        ):
                            leaf_name = ptr.split(".")[-1].lower()
                            if (
                                any(leaf_name.endswith(ts) for ts in TIMESTAMP_NAMES)
                                and node.get("type") == "string"
                                and node.get("format") != "date-time"
                            ):
                                add_finding(
                                    "ADP-022",
                                    ptr,
                                    f"Timestamp property '{leaf_name}' should specify format: date-time (ISO 8601 UTC).",
                                )

    errors = sum(1 for f in findings if f["severity"] == "error")
    warnings = sum(1 for f in findings if f["severity"] == "warning")
    infos = sum(1 for f in findings if f["severity"] == "info")

    # Deduplicate rule penalty slightly so large specs still score fairly while rewarding zero errors
    unique_error_rules = len({f["rule_id"] for f in findings if f["severity"] == "error"})
    unique_warn_rules = len({f["rule_id"] for f in findings if f["severity"] == "warning"})
    penalty = (unique_error_rules * 8) + (errors * 2) + (unique_warn_rules * 3) + warnings + infos
    score = max(0, min(100, 100 - penalty))

    fail_on = config.get("fail_on", "error")
    passed = True
    if fail_on == "error" and errors > 0:
        passed = False
    elif fail_on == "warning" and (errors > 0 or warnings > 0):
        passed = False

    return {
        "spec": spec_label,
        "title": doc.get("info", {}).get("title", "Untitled API"),
        "openapi_version": doc.get("openapi", "unknown"),
        "operations_checked": operation_count,
        "score": score,
        "passed": passed,
        "summary": {
            "errors": errors,
            "warnings": warnings,
            "info": infos,
            "total_violations": len(findings),
        },
        "findings": findings,
    }


def _status_label(res: Dict[str, Any]) -> str:
    if not res["passed"]:
        return "FAIL"
    if res["summary"]["errors"] > 0:
        return "WARN (non-blocking)"
    return "PASS"


def format_text_report(results: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for res in results:
        status = _status_label(res)
        s = res["summary"]
        lines.append("=" * 78)
        lines.append(f"[{status}] {res['title']} ({res['spec']}) — OpenAPI {res['openapi_version']}")
        lines.append(
            f"Score: {res['score']}/100 | Operations: {res['operations_checked']} | "
            f"Errors: {s['errors']} | Warnings: {s['warnings']} | Info: {s['info']}"
        )
        lines.append("-" * 78)
        if not res["findings"]:
            lines.append("No rule violations detected. Specification adheres to all automated principles.")
        else:
            for f in res["findings"]:
                lines.append(
                    f"[{f['severity'].upper():7}] {f['rule_id']} @ {f['location']}"
                )
                lines.append(f"          {f['message']}")
                if f.get("remediation"):
                    lines.append(f"          Fix: {f['remediation']} ({f['standard_ref']})")
        lines.append("")
    return "\n".join(lines)


def format_markdown_report(results: List[Dict[str, Any]]) -> str:
    lines: List[str] = ["## API Design Principles — Validation Report", ""]
    for res in results:
        badge = _status_label(res)
        s = res["summary"]
        lines.append(f"### `{res['spec']}` — {res['title']} (**{badge}**, Score: `{res['score']}/100`)")
        lines.append("")
        lines.append(
            f"- **OpenAPI Version:** `{res['openapi_version']}` • **Operations Checked:** `{res['operations_checked']}`"
        )
        lines.append(
            f"- **Violations:** `{s['errors']}` Errors • `{s['warnings']}` Warnings • `{s['info']}` Info"
        )
        lines.append("")
        if not res["findings"]:
            lines.append("> All automated API design checks passed.")
            lines.append("")
            continue
        lines.append("| Severity | Rule | Location | Violation | Standard |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")
        for f in res["findings"]:
            msg = f["message"].replace("|", "\\|")
            loc = f["location"].replace("|", "\\|")
            ref = f["standard_ref"].replace("|", "\\|")
            lines.append(f"| `{f['severity'].upper()}` | **{f['rule_id']}** | `{loc}` | {msg} | {ref} |")
        lines.append("")
    return "\n".join(lines)


def print_rules(
    rules_data: Dict[str, Any],
    category: Optional[str] = None,
    severity: Optional[str] = None,
    automatable_only: bool = False,
) -> None:
    rules = rules_data["rules"]
    filtered = [
        r
        for r in rules
        if (not category or r["category"] == category)
        and (not severity or r["severity"] == severity)
        and (not automatable_only or r["automatable"])
    ]
    print(f"API Design Principles Ruleset v{rules_data['metadata']['version']} ({len(filtered)} rules shown)")
    print("-" * 88)
    for r in filtered:
        auto_tag = "AUTO" if r["automatable"] else "ARCH"
        print(f"{r['id']} [{r['severity'].upper():7}] [{auto_tag}] ({r['category']}) {r['title']}")
        print(f"        Ref: {r['standard_ref']}")
        print(f"        Good: {r['good_example']}")
        print(f"        Bad:  {r['bad_example']}\n")


def print_checklist(rules_data: Dict[str, Any]) -> None:
    print("# Pre-Production API Design Review Checklist (2026)\n")
    for r in rules_data["rules"]:
        tag = "OpenAPI Lint" if r["automatable"] else "Architecture Review"
        print(f"- [ ] **{r['id']}** ({r['severity'].upper()}, {tag}): {r['title']} — _{r['standard_ref']}_")


def print_paradigm_comparison() -> None:
    print("REST vs GraphQL vs gRPC vs Webhooks/SSE — 2026 Selection Matrix")
    print("=" * 88)
    rows = [
        ("REST (OpenAPI 3.1)", "Public APIs, SaaS, CRUD, CDN caching", "HTTP/1.1–HTTP/3 + JSON", "RFC 9110 + RFC 9457"),
        ("GraphQL", "Multi-entity UI BFFs, mobile clients", "POST JSON + Typed Schema", "Persisted Queries + Depth Limits"),
        ("gRPC (Protobuf)", "Low-latency internal microservices", "HTTP/2 + Binary Protobuf", "Strict .proto contracts + TLS"),
        ("Webhooks / SSE", "Async events, billing, AI token streams", "HTTP POST / text/event-stream", "HMAC-SHA256 + Idempotency"),
    ]
    for name, best, transport, guard in rows:
        print(f"{name:20} | Best: {best:38} | {transport:24} | {guard}")


def expand_spec_inputs(patterns: List[str]) -> List[Path]:
    resolved: List[Path] = []
    for pat in patterns:
        matches = glob.glob(pat, recursive=True)
        if matches:
            resolved.extend(Path(m) for m in sorted(matches) if Path(m).is_file())
        else:
            resolved.append(Path(pat))
    # Deduplicate preserving order
    unique: List[Path] = []
    seen: Set[Path] = set()
    for p in resolved:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            unique.append(p)
    return unique


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="API Design Principles Handbook & Zero-Dependency OpenAPI 3.x Validator"
    )
    parser.add_argument(
        "--spec",
        nargs="+",
        help="Path(s) or glob pattern(s) to OpenAPI 3.0/3.1 JSON (or YAML with PyYAML) specification(s).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional team ruleset JSON config (e.g. .api-rules.example.json).",
    )
    parser.add_argument(
        "--format",
        choices=["text", "markdown", "json"],
        default="text",
        help="Violation report output format (default: text).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output file path for the generated report.",
    )
    parser.add_argument(
        "--fail-on",
        choices=["error", "warning", "none"],
        default=None,
        help="Minimum severity that causes non-zero exit code (default: config fail_on or 'error').",
    )
    parser.add_argument(
        "--rules",
        action="store_true",
        help="List all API design principles in rules.json.",
    )
    parser.add_argument(
        "--category",
        help="Filter --rules by category (naming, methods, errors, pagination, versioning, idempotency, rate-limiting, security, documentation, evolution).",
    )
    parser.add_argument(
        "--severity",
        choices=["error", "warning", "info"],
        help="Filter --rules by severity.",
    )
    parser.add_argument(
        "--automatable",
        action="store_true",
        help="With --rules, show only rules enforced automatically on OpenAPI specs.",
    )
    parser.add_argument(
        "--checklist",
        action="store_true",
        help="Print a Markdown pre-production API design checklist.",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Print REST vs GraphQL vs gRPC vs Webhooks decision matrix.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    rules_data = load_rules()
    rules_by_id = {r["id"]: r for r in rules_data["rules"]}

    if args.rules:
        print_rules(
            rules_data,
            category=args.category,
            severity=args.severity,
            automatable_only=args.automatable,
        )
        return 0

    if args.checklist:
        print_checklist(rules_data)
        return 0

    if args.compare:
        print_paradigm_comparison()
        return 0

    if not args.spec:
        parser.print_help()
        return 0

    config = load_config(args.config)
    if args.fail_on is not None:
        config["fail_on"] = args.fail_on

    spec_paths = expand_spec_inputs(args.spec)
    results: List[Dict[str, Any]] = []
    for sp in spec_paths:
        if not sp.exists():
            print(f"Error: OpenAPI spec not found: {sp}", file=sys.stderr)
            return 2
        doc = load_spec(sp)
        results.append(validate_spec(doc, rules_by_id, config, spec_label=str(sp)))

    if args.format == "json":
        payload = json.dumps(
            {"ruleset_version": rules_data["metadata"]["version"], "results": results},
            indent=2,
        )
    elif args.format == "markdown":
        payload = format_markdown_report(results)
    else:
        payload = format_text_report(results)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")

    print(payload)

    # Set GitHub Actions outputs if running inside Actions
    gh_output = os.environ.get("GITHUB_OUTPUT")
    if gh_output and results:
        total_err = sum(r["summary"]["errors"] for r in results)
        total_warn = sum(r["summary"]["warnings"] for r in results)
        avg_score = round(sum(r["score"] for r in results) / len(results))
        all_passed = all(r["passed"] for r in results)
        with open(gh_output, "a", encoding="utf-8") as gh_fh:
            gh_fh.write(f"score={avg_score}\n")
            gh_fh.write(f"errors={total_err}\n")
            gh_fh.write(f"warnings={total_warn}\n")
            gh_fh.write(f"passed={'true' if all_passed else 'false'}\n")
            if args.output:
                gh_fh.write(f"report-path={args.output}\n")

    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
