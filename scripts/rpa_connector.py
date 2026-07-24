#!/usr/bin/env python3
"""Call the Yuce RPA gateway for Yuntu industry-content ranking lists."""

import argparse
from datetime import date, datetime, timedelta
import ipaddress
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import requests


FUNCTION_CODE = "rpa.conn.juliang.yt.industry.content.rankings.list"
PLATFORM = "RPA_JULIANG_YT_ACCOUNT_PASSWORD"
DATA_SOURCE_TYPE = "rpa"
HEADERS = {"Content-Type": "application/json"}
REQUIRED_ENVIRONMENT = (
    "ENV_BACKEND_HOST",
    "YUCE_AUTHORIZATION",
    "YUCE_SESSION_ID",
)
DATE_RANGE_TYPES = {"LAST_7_DAYS", "LAST_30_DAYS", "CUSTOM"}
AGE_VALUES = {
    "AGE_18_19",
    "AGE_20_23",
    "AGE_24_30",
    "AGE_31_35",
    "AGE_36_40",
    "AGE_41_45",
    "AGE_46_50",
    "AGE_51_55",
    "AGE_56_59",
    "AGE_60_PLUS",
}
GENDER_VALUES = {"MALE", "FEMALE"}
CROWD_GROUP_VALUES = {
    "TOWN_YOUTH",
    "GENZ",
    "SENIOR_MIDDLE",
    "REFINED_MOM",
    "NEW_WHITE_COLLAR",
    "URBAN_SILVER",
    "TOWN_MIDDLE_ELDER",
    "URBAN_BLUE_COLLAR",
}
RANKING_LIMIT_VALUES = {
    "EXPOSURE_TOP1000",
    "CTR_TOP1000",
    "INTERACTION_RATE_TOP1000",
    "COMPLETION_RATE_TOP1000",
}
BRAND_SCOPE_VALUES = {"ALL_INDUSTRY", "SPECIFIED_BRANDS"}
SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")

BUSINESS_PARAMS_SCHEMA = {
    "schema_type": "reference_metadata",
    "title": "Yuntu industry content rankings list query",
    "validation_note": (
        "Reference metadata only; fetch performs authoritative validation, "
        "including cross-field, date-window, and multi-value rules."
    ),
    "fields": {
        "industry": {"accepted_form": "nonblank string"},
        "time_range_type": {"allowed_values": sorted(DATE_RANGE_TYPES)},
        "custom_start_date": {"accepted_form": "YYYYMMDD or YYYY-MM-DD"},
        "custom_end_date": {"accepted_form": "YYYYMMDD or YYYY-MM-DD"},
        "ages": {"allowed_values": sorted(AGE_VALUES)},
        "genders": {"allowed_values": sorted(GENDER_VALUES)},
        "crowd_groups": {"allowed_values": sorted(CROWD_GROUP_VALUES)},
        "brand_scope_type": {"allowed_values": sorted(BRAND_SCOPE_VALUES)},
        "brands": {"accepted_form": "comma-separated string or JSON array"},
        "ranking_limit_type": {"allowed_values": sorted(RANKING_LIMIT_VALUES)},
    },
}


class RpaConnectorError(RuntimeError):
    """Raised when a query cannot safely produce an output file."""


def shanghai_today(now=None):
    """Return the current calendar date in the connector's business timezone."""
    if now is None:
        return datetime.now(SHANGHAI_TIMEZONE).date()
    return now.astimezone(SHANGHAI_TIMEZONE).date()


def runtime_config(environ=None):
    environment = os.environ if environ is None else environ
    missing = [
        name
        for name in REQUIRED_ENVIRONMENT
        if not str(environment.get(name) or "").strip()
    ]
    if missing:
        raise RpaConnectorError(
            "missing RPA runtime environment variables: " + ", ".join(missing)
        )

    api_base = environment["ENV_BACKEND_HOST"].strip().rstrip("/")
    parsed = urlsplit(api_base)
    try:
        valid_port = parsed.port is None or parsed.port > 0
    except ValueError:
        valid_port = False
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or "@" in parsed.netloc
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or not valid_port
    ):
        raise RpaConnectorError(
            "ENV_BACKEND_HOST must be an HTTPS URL without credentials, query, or fragment"
        )
    try:
        ipaddress.ip_address(parsed.hostname)
    except ValueError:
        pass
    else:
        raise RpaConnectorError("ENV_BACKEND_HOST must use a hostname, not an IP literal")

    authorization = environment["YUCE_AUTHORIZATION"].strip()
    session_id = environment["YUCE_SESSION_ID"].strip()
    return api_base, authorization, session_id, {"YCSESSIONID": authorization}


def _parse_date(value, field_name):
    if not isinstance(value, str):
        raise RpaConnectorError(f"{field_name} must use YYYYMMDD or YYYY-MM-DD format")
    for pattern in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    raise RpaConnectorError(f"{field_name} must use YYYYMMDD or YYYY-MM-DD format")


def _normalize_multivalue(value, field_name, allowed_values=None):
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            try:
                values = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise RpaConnectorError(f"{field_name} must be a comma-separated string or JSON array") from exc
        else:
            values = value.split(",")
    elif isinstance(value, list):
        values = value
    else:
        raise RpaConnectorError(f"{field_name} must be a comma-separated string or JSON array")

    if not isinstance(values, list) or not values:
        raise RpaConnectorError(f"{field_name} must contain one or more strings")
    normalized = []
    for item in values:
        if not isinstance(item, str):
            raise RpaConnectorError(f"{field_name} values must be strings")
        item = item.strip()
        if not item:
            raise RpaConnectorError(f"{field_name} values cannot be blank")
        if item in normalized:
            raise RpaConnectorError(f"{field_name} cannot contain duplicates")
        if allowed_values is not None and item not in allowed_values:
            raise RpaConnectorError(f"{field_name} contains an unsupported value: {item}")
        normalized.append(item)
    return normalized


def validate_business_params(raw_params):
    if not isinstance(raw_params, dict):
        raise RpaConnectorError("business_params must be an object")
    allowed_fields = set(BUSINESS_PARAMS_SCHEMA["fields"])
    unexpected = set(raw_params) - allowed_fields
    if unexpected:
        raise RpaConnectorError(
            "unexpected business parameters: " + ", ".join(sorted(unexpected))
        )

    params = {}
    if "industry" in raw_params:
        industry = raw_params["industry"]
        if not isinstance(industry, str) or not industry.strip():
            raise RpaConnectorError("industry must be a nonblank string")
        params["industry"] = industry.strip()

    date_range_type = raw_params.get("time_range_type")
    if date_range_type is not None:
        if not isinstance(date_range_type, str) or date_range_type not in DATE_RANGE_TYPES:
            raise RpaConnectorError(
                "time_range_type must be one of: " + ", ".join(sorted(DATE_RANGE_TYPES))
            )
        params["time_range_type"] = date_range_type

    custom_start = raw_params.get("custom_start_date")
    custom_end = raw_params.get("custom_end_date")
    if date_range_type == "CUSTOM":
        if not custom_start or not custom_end:
            raise RpaConnectorError("CUSTOM requires custom_start_date and custom_end_date")
        start = _parse_date(custom_start, "custom_start_date")
        end = _parse_date(custom_end, "custom_end_date")
        today = shanghai_today()
        if start < today - timedelta(days=369):
            raise RpaConnectorError("custom_start_date cannot be more than 369 days before today")
        if end > today - timedelta(days=4):
            raise RpaConnectorError("custom_end_date cannot be later than today-4")
        if end < start:
            raise RpaConnectorError("custom_end_date cannot be earlier than custom_start_date")
        if (end - start).days > 44:
            raise RpaConnectorError("custom date span cannot exceed 44 days")
        params["custom_start_date"] = custom_start
        params["custom_end_date"] = custom_end
    elif custom_start is not None or custom_end is not None:
        raise RpaConnectorError(
            "custom_start_date and custom_end_date are only valid for CUSTOM"
        )

    for field_name, allowed_values in (
        ("ages", AGE_VALUES),
        ("genders", GENDER_VALUES),
        ("crowd_groups", CROWD_GROUP_VALUES),
    ):
        if field_name in raw_params:
            params[field_name] = _normalize_multivalue(
                raw_params[field_name], field_name, allowed_values
            )

    if "brand_scope_type" in raw_params:
        scope = raw_params["brand_scope_type"]
        if not isinstance(scope, str) or scope not in BRAND_SCOPE_VALUES:
            raise RpaConnectorError(
                "brand_scope_type must be one of: " + ", ".join(sorted(BRAND_SCOPE_VALUES))
            )
        params["brand_scope_type"] = scope
    else:
        scope = None

    if "brands" in raw_params:
        brands = _normalize_multivalue(raw_params["brands"], "brands")
        if scope != "SPECIFIED_BRANDS":
            raise RpaConnectorError("brands requires brand_scope_type SPECIFIED_BRANDS")
        if not 3 <= len(brands) <= 10:
            raise RpaConnectorError("brands must contain 3 to 10 values")
        params["brands"] = brands
    elif scope == "SPECIFIED_BRANDS":
        raise RpaConnectorError("SPECIFIED_BRANDS requires brands")

    if "ranking_limit_type" in raw_params:
        ranking_limit_type = raw_params["ranking_limit_type"]
        if (
            not isinstance(ranking_limit_type, str)
            or ranking_limit_type not in RANKING_LIMIT_VALUES
        ):
            raise RpaConnectorError(
                "ranking_limit_type must be one of: "
                + ", ".join(sorted(RANKING_LIMIT_VALUES))
            )
        params["ranking_limit_type"] = ranking_limit_type
    return params


def _default_session():
    return requests.Session()


def _raise_for_status(response, action):
    try:
        response.raise_for_status()
    except Exception as exc:
        raise RpaConnectorError(f"unable to {action}: {exc}") from exc


def _response_json(response, action):
    try:
        return response.json()
    except Exception as exc:
        raise RpaConnectorError(f"unable to decode {action} response as JSON: {exc}") from exc


def _require_successful_result(result):
    if not isinstance(result, dict) or result.get("success") is not True:
        raise RpaConnectorError("gateway returned an unsuccessful result")
    return result


def list_accounts(environ=None, session=None):
    session = _default_session() if session is None else session
    api_base, authorization, _session_id, cookies = runtime_config(environ)
    try:
        response = session.post(
            f"{api_base}/adg/v1/agent/rpa/authorizations/query",
            json={"authorization": authorization, "platform": PLATFORM},
            headers=HEADERS,
            cookies=cookies,
            timeout=30,
        )
    except Exception as exc:
        raise RpaConnectorError("unable to list RPA accounts: transport request failed") from exc
    _raise_for_status(response, "list RPA accounts")
    return _require_successful_result(_response_json(response, "list RPA accounts"))


def invoke(shop_id, business_params, environ=None, session=None):
    if not isinstance(shop_id, str) or not shop_id.strip():
        raise RpaConnectorError("shop_id is required")
    session = _default_session() if session is None else session
    api_base, authorization, session_id, cookies = runtime_config(environ)
    try:
        response = session.post(
            f"{api_base}/adg/v1/agent/invoke",
            json={
                "authorization": authorization,
                "agent_session_id": session_id,
                "data_source_type": DATA_SOURCE_TYPE,
                "platform": PLATFORM,
                "function_code": FUNCTION_CODE,
                "business_params": business_params,
                "shop_id": shop_id.strip(),
            },
            headers=HEADERS,
            cookies=cookies,
            timeout=3600,
        )
    except Exception as exc:
        raise RpaConnectorError("unable to fetch RPA list: transport request failed") from exc
    _raise_for_status(response, "fetch RPA list")
    return _require_successful_result(_response_json(response, "fetch RPA list"))


def write_json_atomically(result, output_path):
    target = Path(output_path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as staging_file:
            staging_path = Path(staging_file.name)
            json.dump(result, staging_file, ensure_ascii=False, indent=2)
            staging_file.write("\n")
        os.replace(staging_path, target)
    except Exception as exc:
        if "staging_path" in locals():
            try:
                staging_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise RpaConnectorError(f"unable to write JSON output: {exc}") from exc
    return target


def fetch(*, shop_id, raw_business_params, output_path, environ=None, session=None):
    return write_json_atomically(
        invoke(
            shop_id,
            validate_business_params(raw_business_params),
            environ=environ,
            session=session,
        ),
        output_path,
    )


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-accounts", help="List available RPA accounts")
    commands.add_parser("schema", help="Print business-parameter reference metadata")
    commands.add_parser("self-test", help="Run offline connector checks")
    fetch_parser = commands.add_parser("fetch", help="Fetch and save a list response")
    fetch_parser.add_argument("--shop-id", required=True)
    fetch_parser.add_argument("--industry")
    fetch_parser.add_argument("--time-range-type")
    fetch_parser.add_argument("--custom-start-date")
    fetch_parser.add_argument("--custom-end-date")
    fetch_parser.add_argument("--ages")
    fetch_parser.add_argument("--genders")
    fetch_parser.add_argument("--crowd-groups")
    fetch_parser.add_argument("--brand-scope-type")
    fetch_parser.add_argument("--brands")
    fetch_parser.add_argument("--ranking-limit-type")
    fetch_parser.add_argument("--output", required=True)
    return parser


def _cmd_self_test():
    if FUNCTION_CODE != "rpa.conn.juliang.yt.industry.content.rankings.list":
        raise RpaConnectorError("unexpected function code")
    if PLATFORM != "RPA_JULIANG_YT_ACCOUNT_PASSWORD" or DATA_SOURCE_TYPE != "rpa":
        raise RpaConnectorError("unexpected fixed gateway metadata")
    validate_business_params({})
    today = shanghai_today()
    validate_business_params(
        {
            "time_range_type": "CUSTOM",
            "custom_start_date": (today - timedelta(days=10)).strftime("%Y%m%d"),
            "custom_end_date": (today - timedelta(days=4)).isoformat(),
            "brand_scope_type": "SPECIFIED_BRANDS",
            "brands": "燕之屋,王老吉,Oreo/奥利奥",
        }
    )
    print("self-test passed")


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "list-accounts":
            print(json.dumps(list_accounts(), ensure_ascii=False, indent=2))
        elif args.command == "schema":
            print(json.dumps(BUSINESS_PARAMS_SCHEMA, ensure_ascii=False, indent=2))
        elif args.command == "self-test":
            _cmd_self_test()
        elif args.command == "fetch":
            raw_business_params = {
                field: value
                for field, value in {
                    "industry": args.industry,
                    "time_range_type": args.time_range_type,
                    "custom_start_date": args.custom_start_date,
                    "custom_end_date": args.custom_end_date,
                    "ages": args.ages,
                    "genders": args.genders,
                    "crowd_groups": args.crowd_groups,
                    "brand_scope_type": args.brand_scope_type,
                    "brands": args.brands,
                    "ranking_limit_type": args.ranking_limit_type,
                }.items()
                if value is not None
            }
            print(
                fetch(
                    shop_id=args.shop_id,
                    raw_business_params=raw_business_params,
                    output_path=args.output,
                )
            )
    except RpaConnectorError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
