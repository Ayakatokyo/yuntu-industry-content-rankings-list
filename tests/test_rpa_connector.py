import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_DIR / "scripts" / "rpa_connector.py"


def load_connector():
    spec = importlib.util.spec_from_file_location("list_rpa_connector", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload, status_error=None, json_error=None):
        self.payload = payload
        self.status_error = status_error
        self.json_error = json_error

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


class RecordingSession:
    def __init__(self, response):
        self.response = response
        self.posts = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return self.response


class RaisingSession:
    def __init__(self, error):
        self.error = error
        self.posts = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        raise self.error


class RpaConnectorTest(unittest.TestCase):
    def connector(self):
        self.assertTrue(SCRIPT_PATH.exists(), "list connector has not been implemented")
        return load_connector()

    def runtime_environment(self):
        return {
            "ENV_BACKEND_HOST": "https://gateway.example/",
            "YUCE_AUTHORIZATION": "authorization-token",
            "YUCE_SESSION_ID": "agent-session-123",
        }

    def test_connector_script_exists(self):
        self.assertTrue(SCRIPT_PATH.exists(), "list connector has not been implemented")

    def test_fixed_connector_metadata(self):
        connector = self.connector()
        self.assertEqual(
            connector.FUNCTION_CODE,
            "rpa.conn.juliang.yt.industry.content.rankings.list",
        )
        self.assertEqual(connector.PLATFORM, "RPA_JULIANG_YT_ACCOUNT_PASSWORD")
        self.assertEqual(connector.DATA_SOURCE_TYPE, "rpa")

    def test_runtime_config_requires_nonblank_values_and_safe_https_host(self):
        connector = self.connector()
        for name in connector.REQUIRED_ENVIRONMENT:
            for value in (None, "", "   "):
                with self.subTest(name=name, value=value):
                    environment = self.runtime_environment()
                    if value is None:
                        del environment[name]
                    else:
                        environment[name] = value
                    with self.assertRaisesRegex(connector.RpaConnectorError, name):
                        connector.runtime_config(environment)

        unsafe_hosts = (
            "http://gateway.example",
            "gateway.example",
            "https://user:password@gateway.example",
            "https://gateway.example/not-a-base-url",
            "https://gateway.example/?query=value",
            "https://gateway.example/#fragment",
        )
        for host in unsafe_hosts:
            with self.subTest(host=host):
                environment = self.runtime_environment()
                environment["ENV_BACKEND_HOST"] = host
                session = RecordingSession(FakeResponse({"data": []}))
                with self.assertRaisesRegex(connector.RpaConnectorError, "HTTPS"):
                    connector.list_accounts(environ=environment, session=session)
                self.assertEqual(session.posts, [])

    def test_validate_business_params_allows_an_empty_filter_set(self):
        connector = self.connector()
        self.assertEqual(connector.validate_business_params({}), {})

    def test_validate_business_params_normalizes_multiselects(self):
        connector = self.connector()
        params = connector.validate_business_params(
            {
                "industry": "食品饮料",
                "time_range_type": "LAST_7_DAYS",
                "ages": "AGE_24_30,AGE_31_35",
                "genders": ["FEMALE"],
                "crowd_groups": '["REFINED_MOM", "NEW_WHITE_COLLAR"]',
                "brand_scope_type": "SPECIFIED_BRANDS",
                "brands": "燕之屋,王老吉,Oreo/奥利奥",
                "ranking_limit_type": "CTR_TOP1000",
            }
        )
        self.assertEqual(
            params,
            {
                "industry": "食品饮料",
                "time_range_type": "LAST_7_DAYS",
                "ages": ["AGE_24_30", "AGE_31_35"],
                "genders": ["FEMALE"],
                "crowd_groups": ["REFINED_MOM", "NEW_WHITE_COLLAR"],
                "brand_scope_type": "SPECIFIED_BRANDS",
                "brands": ["燕之屋", "王老吉", "Oreo/奥利奥"],
                "ranking_limit_type": "CTR_TOP1000",
            },
        )

    def test_validate_business_params_rejects_unknown_invalid_or_duplicate_values(self):
        connector = self.connector()
        invalid_cases = (
            ({"unrecognized": "value"}, "unexpected"),
            ({"industry": " "}, "industry"),
            ({"ages": "AGE_24_30,AGE_24_30"}, "duplicates"),
            ({"genders": "OTHER"}, "genders"),
            ({"crowd_groups": ["GENZ", ""]}, "blank"),
            ({"ranking_limit_type": "TOP10"}, "ranking_limit_type"),
            ({"ages": '["AGE_24_30", 1]'}, "strings"),
        )
        for raw_params, message in invalid_cases:
            with self.subTest(raw_params=raw_params):
                with self.assertRaisesRegex(connector.RpaConnectorError, message):
                    connector.validate_business_params(raw_params)

    def test_validate_business_params_requires_consistent_brand_scope(self):
        connector = self.connector()
        invalid_cases = (
            ({"brands": "燕之屋,王老吉,Oreo/奥利奥"}, "SPECIFIED_BRANDS"),
            ({"brand_scope_type": "SPECIFIED_BRANDS"}, "brands"),
            (
                {
                    "brand_scope_type": "ALL_INDUSTRY",
                    "brands": "燕之屋,王老吉,Oreo/奥利奥",
                },
                "SPECIFIED_BRANDS",
            ),
            (
                {
                    "brand_scope_type": "SPECIFIED_BRANDS",
                    "brands": "燕之屋,王老吉",
                },
                "3 to 10",
            ),
            (
                {
                    "brand_scope_type": "SPECIFIED_BRANDS",
                    "brands": [str(index) for index in range(11)],
                },
                "3 to 10",
            ),
        )
        for raw_params, message in invalid_cases:
            with self.subTest(raw_params=raw_params):
                with self.assertRaisesRegex(connector.RpaConnectorError, message):
                    connector.validate_business_params(raw_params)

    def test_validate_business_params_enforces_custom_date_window(self):
        connector = self.connector()
        today = date.today()
        valid = connector.validate_business_params(
            {
                "time_range_type": "CUSTOM",
                "custom_start_date": (today - timedelta(days=48)).strftime("%Y%m%d"),
                "custom_end_date": (today - timedelta(days=4)).isoformat(),
            }
        )
        self.assertEqual(valid["time_range_type"], "CUSTOM")

        invalid_cases = (
            ({"time_range_type": "CUSTOM"}, "CUSTOM requires"),
            (
                {
                    "time_range_type": "CUSTOM",
                    "custom_start_date": (today - timedelta(days=370)).isoformat(),
                    "custom_end_date": (today - timedelta(days=4)).isoformat(),
                },
                "369",
            ),
            (
                {
                    "time_range_type": "CUSTOM",
                    "custom_start_date": (today - timedelta(days=5)).isoformat(),
                    "custom_end_date": (today - timedelta(days=3)).isoformat(),
                },
                "today-4",
            ),
            (
                {
                    "time_range_type": "CUSTOM",
                    "custom_start_date": (today - timedelta(days=60)).isoformat(),
                    "custom_end_date": (today - timedelta(days=5)).isoformat(),
                },
                "44",
            ),
            (
                {
                    "time_range_type": "LAST_30_DAYS",
                    "custom_start_date": "2026-01-01",
                    "custom_end_date": "2026-01-02",
                },
                "only valid for CUSTOM",
            ),
        )
        for raw_params, message in invalid_cases:
            with self.subTest(raw_params=raw_params):
                with self.assertRaisesRegex(connector.RpaConnectorError, message):
                    connector.validate_business_params(raw_params)

    def test_validate_business_params_rejects_custom_end_before_start(self):
        connector = self.connector()
        today = date.today()

        with self.assertRaisesRegex(
            connector.RpaConnectorError,
            "earlier than custom_start_date",
        ):
            connector.validate_business_params(
                {
                    "time_range_type": "CUSTOM",
                    "custom_start_date": (today - timedelta(days=10)).isoformat(),
                    "custom_end_date": (today - timedelta(days=11)).strftime("%Y%m%d"),
                }
            )

    def test_fetch_uses_fixed_gateway_payload_and_writes_json_atomically(self):
        connector = self.connector()
        response_payload = {"success": True, "data": {"items": []}}
        session = RecordingSession(FakeResponse(response_payload))
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "nested" / "result.json"
            written = connector.fetch(
                shop_id="shop-42",
                raw_business_params={
                    "industry": "食品饮料",
                    "time_range_type": "LAST_7_DAYS",
                    "ages": "AGE_24_30,AGE_31_35",
                },
                output_path=output,
                environ=self.runtime_environment(),
                session=session,
            )

            self.assertEqual(written, output)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), response_payload)
            self.assertEqual(
                session.posts,
                [
                    (
                        "https://gateway.example/adg/v1/agent/invoke",
                        {
                            "json": {
                                "authorization": "authorization-token",
                                "agent_session_id": "agent-session-123",
                                "data_source_type": "rpa",
                                "platform": "RPA_JULIANG_YT_ACCOUNT_PASSWORD",
                                "function_code": "rpa.conn.juliang.yt.industry.content.rankings.list",
                                "business_params": {
                                    "industry": "食品饮料",
                                    "time_range_type": "LAST_7_DAYS",
                                    "ages": ["AGE_24_30", "AGE_31_35"],
                                },
                                "shop_id": "shop-42",
                            },
                            "headers": {"Content-Type": "application/json"},
                            "cookies": {"YCSESSIONID": "authorization-token"},
                            "timeout": 3600,
                        },
                    )
                ],
            )
            self.assertEqual(list(output.parent.glob("*.tmp")), [])

    def test_gateway_failures_are_credential_safe_and_do_not_write_output(self):
        connector = self.connector()
        scenarios = (
            (RecordingSession(FakeResponse({}, status_error=RuntimeError("down"))), "fetch"),
            (RecordingSession(FakeResponse({"success": False})), "unsuccessful"),
            (RaisingSession(RuntimeError("network unavailable")), "fetch"),
        )
        for session, message in scenarios:
            with self.subTest(session=type(session).__name__):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    output = Path(temporary_directory) / "result.json"
                    with self.assertRaisesRegex(connector.RpaConnectorError, message) as context:
                        connector.fetch(
                            shop_id="shop-42",
                            raw_business_params={},
                            output_path=output,
                            environ=self.runtime_environment(),
                            session=session,
                        )
                    self.assertNotIn("authorization-token", str(context.exception))
                    self.assertFalse(output.exists())

    def test_fetch_rejects_invalid_gateway_success_envelopes_without_writing_output(self):
        connector = self.connector()
        invalid_results = ({}, [], {"success": 1}, {"success": "true"}, {"success": False})
        for result in invalid_results:
            with self.subTest(result=result), tempfile.TemporaryDirectory() as temporary_directory:
                output = Path(temporary_directory) / "result.json"
                with self.assertRaisesRegex(connector.RpaConnectorError, "successful"):
                    connector.fetch(
                        shop_id="shop-42",
                        raw_business_params={},
                        output_path=output,
                        environ=self.runtime_environment(),
                        session=RecordingSession(FakeResponse(result)),
                    )
                self.assertFalse(output.exists())

    def test_validate_business_params_rejects_non_string_scalar_enums(self):
        connector = self.connector()
        for field_name in ("time_range_type", "brand_scope_type", "ranking_limit_type"):
            for value in ([], {}, 1, True):
                with self.subTest(field_name=field_name, value=value):
                    with self.assertRaises(connector.RpaConnectorError):
                        connector.validate_business_params({field_name: value})

    def test_runtime_config_rejects_ip_literal_gateway_hosts_before_post(self):
        connector = self.connector()
        ip_hosts = (
            "https://127.0.0.1",
            "https://192.168.0.8",
            "https://169.254.1.8",
            "https://[::1]",
            "https://[fe80::1]",
        )
        for host in ip_hosts:
            with self.subTest(host=host):
                environment = self.runtime_environment()
                environment["ENV_BACKEND_HOST"] = host
                session = RecordingSession(FakeResponse({"success": True, "data": []}))
                with self.assertRaisesRegex(connector.RpaConnectorError, "hostname"):
                    connector.list_accounts(environ=environment, session=session)
                self.assertEqual(session.posts, [])

    def test_schema_command_labels_metadata_and_fetch_as_authoritative(self):
        connector = self.connector()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            connector.main(["schema"])
        schema = json.loads(output.getvalue())

        self.assertNotIn("$schema", schema)
        self.assertEqual(schema["schema_type"], "reference_metadata")
        self.assertIn("fetch performs authoritative validation", schema["validation_note"])

    def test_schema_cli_help_calls_output_reference_metadata(self):
        connector = self.connector()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as exit_context:
                connector.main(["--help"])

        self.assertEqual(exit_context.exception.code, 0)
        self.assertIn("Print business-parameter reference metadata", output.getvalue())
        self.assertNotIn("JSON schema", output.getvalue())

    def test_shanghai_today_uses_asia_shanghai_timezone(self):
        connector = self.connector()
        utc_before_shanghai_midnight = datetime(2026, 7, 24, 16, 30, tzinfo=timezone.utc)

        self.assertEqual(connector.SHANGHAI_TIMEZONE.key, "Asia/Shanghai")
        self.assertEqual(
            connector.shanghai_today(utc_before_shanghai_midnight),
            date(2026, 7, 25),
        )

    def test_atomic_write_preserves_existing_output_when_replace_fails(self):
        connector = self.connector()
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "result.json"
            output.write_text(json.dumps({"preserve": True}), encoding="utf-8")
            with mock.patch.object(connector.os, "replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(connector.RpaConnectorError, "write"):
                    connector.write_json_atomically({"new": "result"}, output)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {"preserve": True})
            self.assertEqual(list(output.parent.glob("*.tmp")), [])

    def test_list_accounts_uses_fixed_platform_and_rejects_business_failures(self):
        connector = self.connector()
        session = RecordingSession(FakeResponse({"success": True, "data": []}))
        self.assertEqual(
            connector.list_accounts(environ=self.runtime_environment(), session=session),
            {"success": True, "data": []},
        )
        self.assertEqual(
            session.posts,
            [
                (
                    "https://gateway.example/adg/v1/agent/rpa/authorizations/query",
                    {
                        "json": {
                            "authorization": "authorization-token",
                            "platform": "RPA_JULIANG_YT_ACCOUNT_PASSWORD",
                        },
                        "headers": {"Content-Type": "application/json"},
                        "cookies": {"YCSESSIONID": "authorization-token"},
                        "timeout": 30,
                    },
                )
            ],
        )
        with self.assertRaisesRegex(connector.RpaConnectorError, "unsuccessful") as context:
            connector.list_accounts(
                environ=self.runtime_environment(),
                session=RecordingSession(FakeResponse({"success": False})),
            )
        self.assertNotIn("authorization-token", str(context.exception))

    def test_cli_commands_and_help_are_available_without_live_network(self):
        connector = self.connector()
        for argv in ([], ["--help"], ["list-accounts", "--help"], ["schema", "--help"], ["self-test", "--help"], ["fetch", "--help"]):
            with self.subTest(argv=argv):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as exit_context:
                        connector.main(argv)
                self.assertEqual(exit_context.exception.code, 0 if argv else 2)

        schema_output = io.StringIO()
        with contextlib.redirect_stdout(schema_output):
            connector.main(["schema"])
        self.assertEqual(json.loads(schema_output.getvalue()), connector.BUSINESS_PARAMS_SCHEMA)

        self_test_output = io.StringIO()
        with contextlib.redirect_stdout(self_test_output):
            connector.main(["self-test"])
        self.assertIn("self-test passed", self_test_output.getvalue())


if __name__ == "__main__":
    unittest.main()
