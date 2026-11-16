#!/usr/bin/env python3
"""
API Design Principles & OpenAPI 3.x Validator CLI

Zero-dependency OpenAPI 3.0/3.1 linter (JSON + YAML), breaking-change diff
checker, SARIF 2.1.0 exporter, and rules explorer.
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
PRESETS_DIR = BASE_DIR / "presets"

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
PAGINATION_PARAMS = {
    "cursor", "after", "before", "page_token", "pageToken",
    "limit", "page_size", "pageSize", "per_page", "page",
}
CURSOR_PARAMS = {"cursor", "after", "before", "page_token", "pageToken", "starting_after"}
OFFSET_PARAMS = {"offset", "skip"}
TIMESTAMP_NAMES = ("_at", "timestamp", "createdat", "updatedat", "deletedat", "expiresat")


def _strip_yaml_comment(line: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    for idx, ch in enumerate(line):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_double:
            escaped = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if idx == 0 or line[idx - 1].isspace():
                return line[:idx].rstrip()
    return line.rstrip()


def _split_top_level(text: str, sep: str = ",") -> List[str]:
    parts: List[str] = []
    buf: List[str] = []
    depth = 0
    in_s = False
    in_d = False
    esc = False
    for ch in text:
        if esc:
            buf.append(ch)
            esc = False
            continue
        if ch == "\\" and in_d:
            buf.append(ch)
            esc = True
            continue
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif not in_s and not in_d:
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth = max(0, depth - 1)
            elif ch == sep and depth == 0:
                parts.append("".join(buf).strip())
                buf = []
                continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _parse_yaml_scalar(raw: str) -> Any:
    val = raw.strip()
    if not val or val in {"null", "~", "Null", "NULL"}:
        return None
    if val in {"true", "True", "TRUE"}:
        return True
    if val in {"false", "False", "FALSE"}:
        return False
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        if val.startswith('"'):
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return val[1:-1]
        return val[1:-1].replace("''", "'")
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        return [_parse_yaml_scalar(p) for p in _split_top_level(inner)]
    if val.startswith("{") and val.endswith("}"):
        inner = val[1:-1].strip()
        if not inner:
            return {}
        out: Dict[str, Any] = {}
        for item in _split_top_level(inner):
            k, sep, v = item.partition(":")
            if sep:
                out[str(_parse_yaml_scalar(k))] = _parse_yaml_scalar(v)
        return out
    if re.fullmatch(r"-?\d+", val):
        return int(val)
    if re.fullmatch(r"-?\d+\.\d+", val):
        return float(val)
    return val


def _find_yaml_kv(text: str) -> Tuple[Optional[str], Optional[str]]:
    in_s = False
    in_d = False
    esc = False
    for idx, ch in enumerate(text):
        if esc:
            esc = False
            continue
        if ch == "\\" and in_d:
            esc = True
            continue
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == ":" and not in_s and not in_d:
            if idx + 1 == len(text) or text[idx + 1].isspace():
                key = text[:idx].strip()
                rest = text[idx + 1 :].strip()
                return key, rest
    return None, None


def parse_simple_yaml(raw_text: str) -> Any:
    """Parse common OpenAPI YAML documents using only Python stdlib."""
    raw_lines = raw_text.splitlines()
    tokens: List[Tuple[int, str]] = []
    i = 0
    while i < len(raw_lines):
        line = _strip_yaml_comment(raw_lines[i])
        stripped = line.strip()
        if not stripped or stripped in {"---", "..."}:
            i += 1
            continue
        indent = len(line) - len(line.lstrip(" "))
        # Handle block scalars (| or >)
        _, rest = _find_yaml_kv(stripped)
        if rest in {"|", "|-", ">", ">-"}:
            block_lines: List[str] = []
            j = i + 1
            block_indent: Optional[int] = None
            while j < len(raw_lines):
                nxt = raw_lines[j]
                if not nxt.strip():
                    block_lines.append("")
                    j += 1
                    continue
                nxt_ind = len(nxt) - len(nxt.lstrip(" "))
                if nxt_ind <= indent:
                    break
                if block_indent is None:
                    block_indent = nxt_ind
                block_lines.append(nxt[block_indent:])
                j += 1
            joined = (" ".join(block_lines) if rest.startswith(">") else "\n".join(block_lines)).strip()
            key_part, _ = _find_yaml_kv(stripped)
            tokens.append((indent, f"{key_part}: {json.dumps(joined)}"))
            i = j
            continue
        tokens.append((indent, stripped))
        i += 1

    if not tokens:
        return {}

    def parse_block(idx: int, min_indent: int) -> Tuple[Any, int]:
        if idx >= len(tokens):
            return {}, idx
        cur_indent, cur_text = tokens[idx]
        if cur_text.startswith("- ") or cur_text == "-":
            arr: List[Any] = []
            while idx < len(tokens):
                ind, txt = tokens[idx]
                if ind < min_indent or ind != cur_indent or not (txt.startswith("- ") or txt == "-"):
                    break
                item_body = txt[1:].strip()
                if not item_body:
                    val, idx = parse_block(idx + 1, cur_indent + 1)
                    arr.append(val)
                else:
                    k, v = _find_yaml_kv(item_body)
                    if k is not None:
                        item_dict: Dict[str, Any] = {}
                        key_str = str(_parse_yaml_scalar(k))
                        if v == "":
                            sub_val, idx = parse_block(idx + 1, cur_indent + 2)
                            item_dict[key_str] = sub_val
                        else:
                            item_dict[key_str] = _parse_yaml_scalar(v)
                            idx += 1
                        if idx < len(tokens) and tokens[idx][0] > cur_indent:
                            extra, idx = parse_block(idx, cur_indent + 1)
                            if isinstance(extra, dict):
                                item_dict.update(extra)
                        arr.append(item_dict)
                    else:
                        arr.append(_parse_yaml_scalar(item_body))
                        idx += 1
            return arr, idx

        mapping: Dict[str, Any] = {}
        while idx < len(tokens):
            ind, txt = tokens[idx]
            if ind < min_indent or ind != cur_indent:
                break
            if txt.startswith("- ") or txt == "-":
                break
            k, v = _find_yaml_kv(txt)
            if k is None:
                idx += 1
                continue
            key_str = str(_parse_yaml_scalar(k))
            if v == "":
                if idx + 1 < len(tokens) and tokens[idx + 1][0] > cur_indent:
                    sub_val, idx = parse_block(idx + 1, cur_indent + 1)
                    mapping[key_str] = sub_val
                elif idx + 1 < len(tokens) and tokens[idx + 1][0] == cur_indent and tokens[idx + 1][1].startswith("- "):
                    sub_val, idx = parse_block(idx + 1, cur_indent)
                    mapping[key_str] = sub_val
                else:
                    mapping[key_str] = None
                    idx += 1
            else:
                mapping[key_str] = _parse_yaml_scalar(v)
                idx += 1
        return mapping, idx

    parsed, _ = parse_block(0, tokens[0][0])
    return parsed


def load_rules(path: Path = RULES_PATH) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_spec(spec_path: Path) -> Dict[str, Any]:
    raw = spec_path.read_text(encoding="utf-8")
    suffix = spec_path.suffix.lower()
    if suffix in {".yaml", ".yml"} or raw.lstrip().startswith(("openapi:", "swagger:")):
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(raw)
        except ImportError:
            data = parse_simple_yaml(raw)
        if not isinstance(data, dict):
            raise ValueError(f"Spec '{spec_path}' did not parse into an object.")
        return data
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Spec '{spec_path}' root must be a JSON object.")
    return data


def load_config(config_path: Optional[Path], preset: Optional[str] = None) -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "organization": "default",
        "ruleset_name": "API Design Principles Standard (2026)",
        "fail_on": "error",
        "allowed_version_prefixes": [],
        "ignore_paths": ["/health", "/healthz", "/readyz", "/metrics"],
        "disabled_rules": [],
        "severity_overrides": {},
    }
    merged = dict(defaults)
    if preset:
        preset_file = PRESETS_DIR / f"{preset}.json"
        if not preset_file.exists():
            available = ", ".join(p.stem for p in sorted(PRESETS_DIR.glob("*.json")))
            raise ValueError(f"Unknown preset '{preset}'. Available presets: {available}")
        preset_data = json.loads(preset_file.read_text(encoding="utf-8"))
        merged.update(preset_data)
    if config_path:
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("Config file must contain a JSON object.")
        merged.update(loaded)
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
    if clean.lower() in {"settings", "orders", "returns", "checks", "records", "posts", "sets"}:
        return False
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
        add_finding("ADP-009", "paths", "OpenAPI specification contains no paths to validate.")

    seen_operation_ids: Dict[str, str] = {}
    operation_count = 0

    if isinstance(paths, dict):
        for path_str, raw_path_item in paths.items():
            if path_str in ignore_paths or not isinstance(raw_path_item, dict):
                continue

            if len(path_str) > 1 and path_str.endswith("/"):
                add_finding(
                    "ADP-003",
                    path_str,
                    f"Path '{path_str}' has a trailing slash; normalize to '{path_str.rstrip('/')}'.",
                )

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
                    add_finding("ADP-017", op_loc, "Missing concise operation summary.")

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

                for p in params:
                    p_in = str(p.get("in", "")).lower()
                    p_name = str(p.get("name", ""))
                    if p_in == "query" and p_name.lower() in SENSITIVE_QUERY_NAMES:
                        add_finding(
                            "ADP-016",
                            f"{op_loc} (query:{p_name})",
                            f"Sensitive credential parameter '{p_name}' passed in URL query string; move to Authorization header.",
                        )

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

                if method == "PUT" and "if-match" not in header_names_lower:
                    add_finding(
                        "ADP-020",
                        op_loc,
                        "PUT replacement without If-Match header risks lost updates; prefer PATCH or add ETag/If-Match.",
                    )

                if method == "POST" and not path_str.endswith(":search"):
                    if "idempotency-key" not in header_names_lower:
                        add_finding(
                            "ADP-012",
                            op_loc,
                            "POST mutation does not declare an Idempotency-Key header parameter for safe client retries.",
                        )

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

                responses = raw_op.get("responses", {})
                if not isinstance(responses, dict):
                    responses = {}
                resp_codes = {str(k) for k in responses.keys()}

                if method == "POST" and is_collection_path(path_str) and not path_str.endswith(":search"):
                    if "201" not in resp_codes and "202" not in resp_codes:
                        add_finding(
                            "ADP-007",
                            op_loc,
                            "Resource-creating POST should return 201 Created (with Location) or 202 Accepted instead of only 200.",
                        )

                if method == "DELETE" and "204" not in resp_codes and "202" not in resp_codes:
                    add_finding(
                        "ADP-006",
                        op_loc,
                        "DELETE operation should document 204 No Content or 202 Accepted.",
                    )

                has_error_resp = any(
                    c.startswith("4") or c == "4XX" or c == "default" for c in resp_codes
                )
                if not has_error_resp:
                    add_finding(
                        "ADP-009",
                        op_loc,
                        "Operation defines no explicit 4xx or default error responses.",
                    )

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

                has_429 = "429" in resp_codes
                has_rl_headers = False
                for raw_r in responses.values():
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


def _extract_schema_props(doc: Dict[str, Any], schema: Any) -> Tuple[Dict[str, Dict[str, Any]], Set[str]]:
    resolved = resolve_ref(doc, schema)
    if not isinstance(resolved, dict):
        return {}, set()
    props: Dict[str, Dict[str, Any]] = {}
    req: Set[str] = set()
    if isinstance(resolved.get("required"), list):
        req.update(str(r) for r in resolved["required"])
    raw_props = resolved.get("properties")
    if isinstance(raw_props, dict):
        for k, v in raw_props.items():
            rv = resolve_ref(doc, v)
            if isinstance(rv, dict):
                props[str(k)] = rv
    for comp in ("allOf",):
        if isinstance(resolved.get(comp), list):
            for sub in resolved[comp]:
                sub_p, sub_r = _extract_schema_props(doc, sub)
                props.update(sub_p)
                req.update(sub_r)
    return props, req


def diff_specs(
    base_doc: Dict[str, Any],
    head_doc: Dict[str, Any],
    base_label: str = "base",
    head_label: str = "head",
) -> Dict[str, Any]:
    """Compare two OpenAPI specs and report breaking and non-breaking contract changes."""
    changes: List[Dict[str, str]] = []

    def add_change(kind: str, location: str, message: str) -> None:
        changes.append({"severity": kind, "location": location, "message": message})

    base_paths = base_doc.get("paths", {}) if isinstance(base_doc.get("paths"), dict) else {}
    head_paths = head_doc.get("paths", {}) if isinstance(head_doc.get("paths"), dict) else {}

    for path_str, b_item in base_paths.items():
        if not isinstance(b_item, dict):
            continue
        if path_str not in head_paths or not isinstance(head_paths.get(path_str), dict):
            add_change("breaking", path_str, f"Endpoint path '{path_str}' was removed.")
            continue
        h_item = head_paths[path_str]

        for m in HTTP_METHODS:
            b_op = b_item.get(m)
            if not isinstance(b_op, dict):
                continue
            h_op = h_item.get(m)
            op_loc = f"{m.upper()} {path_str}"
            if not isinstance(h_op, dict):
                add_change("breaking", op_loc, f"Operation '{op_loc}' was removed.")
                continue

            b_params = {(p["in"], p["name"]): p for p in merge_parameters(base_doc, b_item, b_op)}
            h_params = {(p["in"], p["name"]): p for p in merge_parameters(head_doc, h_item, h_op)}

            for pk, bp in b_params.items():
                if pk not in h_params:
                    add_change("breaking", op_loc, f"Parameter '{pk[1]}' ({pk[0]}) was removed.")
                else:
                    hp = h_params[pk]
                    if not bp.get("required") and hp.get("required"):
                        add_change("breaking", op_loc, f"Optional parameter '{pk[1]}' became required.")

            for pk, hp in h_params.items():
                if pk not in b_params and hp.get("required"):
                    add_change("breaking", op_loc, f"New required parameter '{pk[1]}' ({pk[0]}) added.")

            b_rb = resolve_ref(base_doc, b_op.get("requestBody"))
            h_rb = resolve_ref(head_doc, h_op.get("requestBody"))
            if isinstance(h_rb, dict) and h_rb.get("required") and not (isinstance(b_rb, dict) and b_rb.get("required")):
                add_change("breaking", op_loc, "Request body became required.")

            if isinstance(b_rb, dict) and isinstance(h_rb, dict):
                b_cnt = b_rb.get("content", {})
                h_cnt = h_rb.get("content", {})
                for mt, b_m in b_cnt.items():
                    if mt not in h_cnt:
                        add_change("breaking", op_loc, f"Request media type '{mt}' was removed.")
                        continue
                    b_props, b_req = _extract_schema_props(base_doc, b_m.get("schema"))
                    h_props, h_req = _extract_schema_props(head_doc, h_cnt[mt].get("schema"))
                    for new_req in sorted(h_req - b_req):
                        add_change("breaking", f"{op_loc}.requestBody", f"Property '{new_req}' became required.")
                    for p_name, bp in b_props.items():
                        if p_name in h_props:
                            hp = h_props[p_name]
                            if bp.get("type") and hp.get("type") and bp.get("type") != hp.get("type"):
                                add_change(
                                    "breaking",
                                    f"{op_loc}.requestBody.{p_name}",
                                    f"Type changed from '{bp.get('type')}' to '{hp.get('type')}'.",
                                )
                            if isinstance(bp.get("enum"), list) and isinstance(hp.get("enum"), list):
                                removed_vals = set(bp["enum"]) - set(hp["enum"])
                                if removed_vals:
                                    add_change(
                                        "breaking",
                                        f"{op_loc}.requestBody.{p_name}",
                                        f"Enum values removed: {sorted(map(str, removed_vals))}.",
                                    )

            b_resps = b_op.get("responses", {})
            h_resps = h_op.get("responses", {})
            for rc in b_resps:
                if rc.startswith("2") and rc not in h_resps:
                    add_change("breaking", op_loc, f"Success response '{rc}' was removed.")
                elif rc.startswith("2") and rc in h_resps:
                    b_r = resolve_ref(base_doc, b_resps[rc])
                    h_r = resolve_ref(head_doc, h_resps[rc])
                    if isinstance(b_r, dict) and isinstance(h_r, dict):
                        b_c = b_r.get("content", {})
                        h_c = h_r.get("content", {})
                        for mt, b_m in b_c.items():
                            if mt in h_c:
                                b_props, _ = _extract_schema_props(base_doc, b_m.get("schema"))
                                h_props, _ = _extract_schema_props(head_doc, h_c[mt].get("schema"))
                                for p_name, bp in b_props.items():
                                    if p_name not in h_props:
                                        add_change(
                                            "breaking",
                                            f"{op_loc}.{rc}",
                                            f"Response property '{p_name}' was removed.",
                                        )
                                    elif bp.get("type") and h_props[p_name].get("type") and bp.get("type") != h_props[p_name].get("type"):
                                        add_change(
                                            "breaking",
                                            f"{op_loc}.{rc}.{p_name}",
                                            f"Response type changed from '{bp.get('type')}' to '{h_props[p_name].get('type')}'.",
                                        )

    for path_str, h_item in head_paths.items():
        if not isinstance(h_item, dict):
            continue
        if path_str not in base_paths:
            add_change("non-breaking", path_str, f"New endpoint path '{path_str}' added.")
            continue
        b_item = base_paths[path_str]
        for m in HTTP_METHODS:
            if isinstance(h_item.get(m), dict) and not isinstance(b_item.get(m), dict):
                add_change("non-breaking", f"{m.upper()} {path_str}", f"New operation '{m.upper()} {path_str}' added.")

    breaking_count = sum(1 for c in changes if c["severity"] == "breaking")
    return {
        "base": base_label,
        "head": head_label,
        "breaking_changes": breaking_count,
        "non_breaking_changes": len(changes) - breaking_count,
        "passed": breaking_count == 0,
        "changes": changes,
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
        lines.append(f"[{status}] {res['title']} ({res['spec']}) - OpenAPI {res['openapi_version']}")
        lines.append(
            f"Score: {res['score']}/100 | Operations: {res['operations_checked']} | "
            f"Errors: {s['errors']} | Warnings: {s['warnings']} | Info: {s['info']}"
        )
        lines.append("-" * 78)
        if not res["findings"]:
            lines.append("No rule violations detected.")
        else:
            for f in res["findings"]:
                lines.append(f"[{f['severity'].upper():7}] {f['rule_id']} @ {f['location']}")
                lines.append(f"          {f['message']}")
                if f.get("remediation"):
                    lines.append(f"          Fix: {f['remediation']} ({f['standard_ref']})")
        lines.append("")
    return "\n".join(lines)


def format_markdown_report(results: List[Dict[str, Any]]) -> str:
    lines: List[str] = ["## API Design Principles Validation Report", ""]
    for res in results:
        badge = _status_label(res)
        s = res["summary"]
        lines.append(f"### `{res['spec']}` ({res['title']}): **{badge}**, Score `{res['score']}/100`")
        lines.append("")
        lines.append(
            f"- OpenAPI Version: `{res['openapi_version']}` | Operations Checked: `{res['operations_checked']}`"
        )
        lines.append(
            f"- Violations: `{s['errors']}` Errors, `{s['warnings']}` Warnings, `{s['info']}` Info"
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


def format_sarif_report(
    results: List[Dict[str, Any]], rules_by_id: Dict[str, Dict[str, Any]]
) -> str:
    sarif_rules = []
    for rid, r in sorted(rules_by_id.items()):
        if not r.get("automatable"):
            continue
        level = "error" if r.get("severity") == "error" else ("warning" if r.get("severity") == "warning" else "note")
        sarif_rules.append(
            {
                "id": rid,
                "name": r.get("slug", rid),
                "shortDescription": {"text": r.get("title", rid)},
                "fullDescription": {"text": r.get("principle", "")},
                "defaultConfiguration": {"level": level},
                "properties": {"tags": ["api-design", r.get("category", "rest")], "standard": r.get("standard_ref", "")},
            }
        )

    sarif_results = []
    for res in results:
        spec_uri = res["spec"]
        for f in res["findings"]:
            sev = f["severity"]
            level = "error" if sev == "error" else ("warning" if sev == "warning" else "note")
            sarif_results.append(
                {
                    "ruleId": f["rule_id"],
                    "level": level,
                    "message": {"text": f"[{f['location']}] {f['message']} Fix: {f['remediation']}"},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": spec_uri},
                                "region": {"startLine": 1},
                            },
                            "logicalLocations": [{"fullyQualifiedName": f["location"]}],
                        }
                    ],
                }
            )

    sarif_doc = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "api-design-principles",
                        "informationUri": "https://github.com/api-design-tools/api-design-principles",
                        "rules": sarif_rules,
                    }
                },
                "results": sarif_results,
            }
        ],
    }
    return json.dumps(sarif_doc, indent=2)


def format_diff_report(diff_res: Dict[str, Any], fmt: str) -> str:
    if fmt == "json":
        return json.dumps(diff_res, indent=2)
    if fmt == "markdown":
        status = "PASS" if diff_res["passed"] else "FAIL (Breaking Changes Detected)"
        lines = [
            f"## OpenAPI Contract Diff: `{diff_res['base']}` -> `{diff_res['head']}` (**{status}**)",
            "",
            f"- Breaking changes: `{diff_res['breaking_changes']}` | Additive changes: `{diff_res['non_breaking_changes']}`",
            "",
        ]
        if diff_res["changes"]:
            lines.append("| Type | Location | Change |")
            lines.append("| :--- | :--- | :--- |")
            for c in diff_res["changes"]:
                lines.append(f"| `{c['severity'].upper()}` | `{c['location']}` | {c['message']} |")
        else:
            lines.append("> No contract differences detected.")
        return "\n".join(lines)

    lines = [
        f"OpenAPI Diff ({diff_res['base']} -> {diff_res['head']}): "
        f"{diff_res['breaking_changes']} breaking, {diff_res['non_breaking_changes']} non-breaking"
    ]
    for c in diff_res["changes"]:
        lines.append(f"[{c['severity'].upper():12}] {c['location']} : {c['message']}")
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
        print(f"- [ ] **{r['id']}** ({r['severity'].upper()}, {tag}): {r['title']} ({r['standard_ref']})")


def print_paradigm_comparison() -> None:
    print("REST vs GraphQL vs gRPC vs Webhooks/SSE (2026 Selection Matrix)")
    print("=" * 88)
    rows = [
        ("REST (OpenAPI 3.1)", "Public APIs, SaaS, CRUD, CDN caching", "HTTP/1.1-HTTP/3 + JSON", "RFC 9110 + RFC 9457"),
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
        help="Path(s) or glob pattern(s) to OpenAPI 3.0/3.1 JSON or YAML specification(s).",
    )
    parser.add_argument(
        "--diff",
        nargs=2,
        metavar=("BASE_SPEC", "HEAD_SPEC"),
        help="Compare BASE_SPEC against HEAD_SPEC to detect breaking contract changes.",
    )
    parser.add_argument(
        "--preset",
        choices=["google-aip", "stripe-style", "owasp-api-top10", "strict-public-api"],
        help="Apply a built-in industry preset from presets/.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional team ruleset JSON config (e.g. .api-rules.example.json).",
    )
    parser.add_argument(
        "--format",
        choices=["text", "markdown", "json", "sarif"],
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
        help="Minimum severity that causes non-zero exit code.",
    )
    parser.add_argument("--rules", action="store_true", help="List all API design principles in rules.json.")
    parser.add_argument("--category", help="Filter --rules by category.")
    parser.add_argument("--severity", choices=["error", "warning", "info"], help="Filter --rules by severity.")
    parser.add_argument("--automatable", action="store_true", help="With --rules, show only automated OpenAPI rules.")
    parser.add_argument("--checklist", action="store_true", help="Print a Markdown pre-production checklist.")
    parser.add_argument("--compare", action="store_true", help="Print REST vs GraphQL vs gRPC vs Webhooks matrix.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    rules_data = load_rules()
    rules_by_id = {r["id"]: r for r in rules_data["rules"]}

    if args.rules:
        print_rules(rules_data, category=args.category, severity=args.severity, automatable_only=args.automatable)
        return 0
    if args.checklist:
        print_checklist(rules_data)
        return 0
    if args.compare:
        print_paradigm_comparison()
        return 0

    if args.diff:
        base_p, head_p = Path(args.diff[0]), Path(args.diff[1])
        if not base_p.exists() or not head_p.exists():
            print("Error: both BASE_SPEC and HEAD_SPEC must exist for --diff.", file=sys.stderr)
            return 2
        diff_res = diff_specs(load_spec(base_p), load_spec(head_p), str(base_p), str(head_p))
        fmt = "json" if args.format == "sarif" else args.format
        payload = format_diff_report(diff_res, fmt)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload + "\n", encoding="utf-8")
        print(payload)
        if args.fail_on == "none":
            return 0
        return 0 if diff_res["passed"] else 1

    if not args.spec:
        parser.print_help()
        return 0

    config = load_config(args.config, preset=args.preset)
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
        payload = json.dumps({"ruleset_version": rules_data["metadata"]["version"], "results": results}, indent=2)
    elif args.format == "markdown":
        payload = format_markdown_report(results)
    elif args.format == "sarif":
        payload = format_sarif_report(results, rules_by_id)
    else:
        payload = format_text_report(results)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")

    print(payload)

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
