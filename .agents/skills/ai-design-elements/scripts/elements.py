#!/usr/bin/env python3
"""Offline element discovery and decision-record checks; no code installation."""

import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
AREAS = ("functional", "accessibility", "responsive", "performance", "visual")


class RecordError(ValueError):
    pass


def object_fields(value, fields, where):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise RecordError(f"{where}: expected fields {', '.join(fields)}")


def string(value, where):
    if not isinstance(value, str):
        raise RecordError(f"{where}: expected string")


def choice(value, options, where):
    if not isinstance(value, str) or value not in options:
        raise RecordError(f"{where}: expected one of {', '.join(options)}")


def strings(value, where):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise RecordError(f"{where}: expected list of nonempty strings")


def boolean(value, where):
    if type(value) is not bool:
        raise RecordError(f"{where}: expected boolean")


def web_url(value):
    parsed = urlsplit(value)
    return parsed.scheme in ("https", "http") and bool(parsed.hostname)


def mutable_reference(value):
    reference = value.strip().casefold()
    return (reference in ("latest", "main", "master", "head", "trunk", "develop")
            or reference.startswith(("^", "~", ">", "<", "="))
            or "*" in reference or bool(re.search(r"(?:^|\.)x(?:\.|$)", reference)))


def load_json(path):
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise RecordError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique_keys)


def validate_records(data):
    object_fields(data, ("schema_version", "components"), "registry")
    if data["schema_version"] != "1.0" or not isinstance(data["components"], list):
        raise RecordError("registry: expected schema_version 1.0 and components array")
    ids = set()
    for index, record in enumerate(data["components"]):
        where = f"components[{index}]"
        object_fields(record, ("id", "task", "mode", "project_version", "design_reference",
                               "existing", "source", "dependencies", "adaptation", "checks"), where)
        for field in ("id", "task", "project_version", "design_reference", "adaptation"):
            string(record[field], f"{where}.{field}")
        if not record["id"].strip() or not record["task"].strip() or record["id"] in ids:
            raise RecordError(f"{where}: nonempty unique id and task required")
        ids.add(record["id"])
        choice(record["mode"], ("selection", "implementation", "review"), f"{where}.mode")
        existing = record["existing"]
        object_fields(existing, ("path", "decision", "reason"), f"{where}.existing")
        for field in ("path", "reason"):
            string(existing[field], f"{where}.existing.{field}")
        choice(existing["decision"], ("reuse", "adapt", "replace", "none"), f"{where}.existing.decision")
        source = record["source"]
        object_fields(source, ("kind", "url", "revision", "files", "inspected", "license"), f"{where}.source")
        choice(source["kind"], ("local", "native", "external"), f"{where}.source.kind")
        for field in ("url", "revision"):
            string(source[field], f"{where}.source.{field}")
        strings(source["files"], f"{where}.source.files")
        boolean(source["inspected"], f"{where}.source.inspected")
        license_info = source["license"]
        object_fields(license_info, ("name", "evidence", "checked_on", "usage", "rights", "notice"), f"{where}.license")
        for field in ("name", "evidence", "checked_on", "notice"):
            string(license_info[field], f"{where}.license.{field}")
        if license_info["checked_on"]:
            try:
                parsed_date = date.fromisoformat(license_info["checked_on"])
            except ValueError as error:
                raise RecordError(f"{where}.license.checked_on: expected YYYY-MM-DD") from error
            if parsed_date.isoformat() != license_info["checked_on"]:
                raise RecordError(f"{where}.license.checked_on: expected YYYY-MM-DD")
        choice(license_info["usage"], ("site", "redistribution"), f"{where}.license.usage")
        choice(license_info["rights"], ("confirmed", "unknown", "denied"), f"{where}.license.rights")
        deps = record["dependencies"]
        object_fields(deps, ("items", "primitive_base", "reviewed", "compatibility", "evidence"), f"{where}.dependencies")
        strings(deps["items"], f"{where}.dependencies.items")
        boolean(deps["reviewed"], f"{where}.dependencies.reviewed")
        for field in ("primitive_base", "evidence"):
            string(deps[field], f"{where}.dependencies.{field}")
        choice(deps["compatibility"], ("confirmed", "unknown", "incompatible"), f"{where}.dependencies.compatibility")
        if not isinstance(record["checks"], list):
            raise RecordError(f"{where}.checks: expected array")
        for i, check in enumerate(record["checks"]):
            label = f"{where}.checks[{i}]"
            object_fields(check, ("area", "status", "version", "environment", "evidence", "reason"), label)
            choice(check["area"], AREAS, f"{label}.area")
            choice(check["status"], ("pass", "fail", "not-checked", "not-applicable"), f"{label}.status")
            for field in ("version", "environment", "evidence", "reason"):
                string(check[field], f"{label}.{field}")
    return data["components"]


def draft(identifier, task, mode):
    return {
        "id": identifier, "task": task, "mode": mode,
        "project_version": "", "design_reference": "",
        "existing": {"path": "", "decision": "none", "reason": ""},
        "source": {"kind": "local", "url": "", "revision": "", "files": [], "inspected": False,
                   "license": {"name": "", "evidence": "", "checked_on": "", "usage": "site",
                               "rights": "unknown", "notice": ""}},
        "dependencies": {"items": [], "primitive_base": "", "reviewed": False,
                         "compatibility": "unknown", "evidence": ""},
        "adaptation": "",
        "checks": [{"area": area, "status": "not-checked", "version": "", "environment": "",
                    "evidence": "", "reason": ""} for area in AREAS],
    }


def assess(record, version):
    """Evaluate declarations only. Evidence existence/content is deliberately not inferred."""
    source, deps, existing = record["source"], record["dependencies"], record["existing"]
    license_info = source["license"]
    reasons = []
    blockers = []
    if license_info["rights"] == "denied":
        blockers.append("rights denied for recorded usage")
    if deps["compatibility"] == "incompatible":
        blockers.append("incompatible with project")
    required = {
        "project_version": record["project_version"], "design_reference": record["design_reference"],
        "existing.reason": existing["reason"], "source.url": source["url"],
        "source.revision": source["revision"], "source.files": source["files"],
        "source.inspected": source["inspected"], "license.name": license_info["name"],
        "license.evidence": license_info["evidence"], "license.checked_on": license_info["checked_on"],
        "license.notice": license_info["notice"], "dependencies.reviewed": deps["reviewed"],
        "dependencies.primitive_base": deps["primitive_base"], "dependencies.evidence": deps["evidence"],
        "adaptation": record["adaptation"],
    }
    if existing["decision"] != "none":
        required["existing.path"] = existing["path"]
    for field, value in required.items():
        if not value or isinstance(value, str) and not value.strip():
            reasons.append(f"missing {field}")
    if license_info["rights"] != "confirmed":
        reasons.append("rights not confirmed for recorded usage")
    if deps["compatibility"] != "confirmed":
        reasons.append("compatibility not confirmed")
    if mutable_reference(source["revision"]):
        reasons.append("source.revision is a mutable alias or version range; pin exact version or snapshot")
    if mutable_reference(record["project_version"]):
        reasons.append("project_version must identify an exact result, not a mutable alias")
    if source["kind"] == "external":
        for label, value in (("source.url", source["url"]), ("license.evidence", license_info["evidence"])):
            if not web_url(value):
                reasons.append(f"{label} must reference HTTP(S) upstream")
    selection_gaps = list(reasons)
    if record["project_version"] != version:
        reasons.append("record belongs to a different project version")
    failed = False
    for area in AREAS:
        checks = [check for check in record["checks"] if check["area"] == area]
        if not checks:
            reasons.append(f"{area}: no checks")
        for check in checks:
            if check["version"] != version:
                reasons.append(f"{area}: stale or unversioned check")
                continue
            status = check["status"]
            if status == "fail":
                failed = True
                reasons.append(f"{area}: failed check")
            elif status == "not-checked":
                reasons.append(f"{area}: not checked")
            elif status == "not-applicable" and not check["reason"].strip():
                reasons.append(f"{area}: applicability reason missing")
            elif status == "pass" and not (check["environment"].strip() and check["evidence"].strip()):
                reasons.append(f"{area}: pass lacks environment or evidence")
    if blockers:
        status = "blocked"
    elif failed:
        status = "needs-work"
    elif selection_gaps:
        status = "candidate"
    elif reasons:
        status = "ready-to-adapt"
    else:
        status = "verified-record"
    return {"id": record["id"], "status": status, "reasons": blockers + list(dict.fromkeys(reasons))}


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def contains(value, query):
    text = json.dumps(value, ensure_ascii=False).casefold()
    return all(word in text for word in query.casefold().split())


def search(args):
    catalog = load_json(ROOT / "resources" / "catalog.json")
    resources = []
    for resource in catalog["resources"]:
        if args.id and resource["id"] != args.id:
            continue
        if args.category and resource["category"] != args.category:
            continue
        if args.access and resource["access"] != args.access:
            continue
        if args.stack and args.stack.casefold() not in resource["stack"].casefold():
            continue
        if contains(resource, args.query):
            resources.append(resource)
    resources.sort(key=lambda row: (row["priority"], row["id"]))
    local = []
    if args.records:
        records = validate_records(load_json(args.records))
        local = [record for record in records if (not args.id or record["id"] == args.id) and contains(record, args.query)]
    emit({"warning": catalog["warning"], "local_records": local[:args.limit],
          "resources": resources[:args.limit], "matched": {"local": len(local), "resources": len(resources)},
          "local_note": "Historical declarations only; recheck current project, version and intended usage."})
    return 0


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    find = commands.add_parser("search", help="Search pointers and optional local records")
    find.add_argument("query", nargs="?", default="")
    for flag in ("id", "category", "access", "stack", "records"):
        find.add_argument(f"--{flag}")
    find.add_argument("--limit", type=positive_int, default=5)
    new = commands.add_parser("new", help="Create one draft registry, refusing overwrite")
    new.add_argument("--id", required=True)
    new.add_argument("--task", required=True)
    new.add_argument("--mode", choices=("selection", "implementation", "review"), default="selection")
    new.add_argument("--out", type=Path, required=True)
    check = commands.add_parser("check", help="Check declarations, not source code or evidence")
    check.add_argument("records", type=Path)
    check.add_argument("--project-version", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "search":
            return search(args)
        if args.command == "new":
            data = {"schema_version": "1.0", "components": [draft(args.id, args.task, args.mode)]}
            validate_records(data)
            with args.out.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            emit({"created": str(args.out), "status": "candidate"})
            return 0
        if not args.project_version.strip():
            raise RecordError("project-version must be nonempty")
        records = validate_records(load_json(args.records))
        results = [assess(record, args.project_version) for record in records]
        emit({"scope": "record declarations only; evidence and source code not audited",
              "project_version": args.project_version, "components": results,
              "empty_registry": not records})
        return 0 if records and all(row["status"] == "verified-record" for row in results) else 1
    except (OSError, ValueError) as error:
        emit({"error": str(error)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
