import re
import subprocess
import sys
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "SKILL.md"
OPENAI_YAML_PATH = ROOT / "agents" / "openai.yaml"
CONNECTOR_PATH = ROOT / "scripts" / "rpa_connector.py"


class ListSkillContractTests(unittest.TestCase):
    def read_skill(self):
        return SKILL_PATH.read_text(encoding="utf-8")

    def test_frontmatter_identifies_a_trigger_only_standalone_skill(self):
        skill = self.read_skill()
        frontmatter = re.match(r"\A---\n(.*?)\n---", skill, re.DOTALL)

        self.assertIsNotNone(frontmatter)
        self.assertIn("name: yuntu-industry-content-rankings-list", frontmatter.group(1))
        description = re.search(r"^description: (.+)$", frontmatter.group(1), re.MULTILINE)
        self.assertIsNotNone(description)
        self.assertTrue(description.group(1).startswith("Use when"))
        self.assertNotIn("python", description.group(1).lower())

    def test_documents_fixed_connector_and_secure_runtime_requirements(self):
        skill = self.read_skill()

        self.assertIn("rpa.conn.juliang.yt.industry.content.rankings.list", skill)
        for environment_variable in (
            "ENV_BACKEND_HOST",
            "YUCE_AUTHORIZATION",
            "YUCE_SESSION_ID",
        ):
            self.assertIn(environment_variable, skill)
        self.assertIn("bare trusted HTTPS gateway URL", skill)
        self.assertIn("without an IP literal, userinfo, query, or fragment", skill)
        self.assertRegex(skill, r"(?i)credentials?.{0,80}environment")
        self.assertIn("list-accounts", skill)
        self.assertRegex(skill, r"(?i)shop_id.{0,120}list-accounts")

    def test_documents_all_commands_and_cli_exposes_each_fetch_option(self):
        skill = self.read_skill()
        command = "python yuntu-industry-content-rankings-list/scripts/rpa_connector.py"
        for subcommand in ("list-accounts", "schema", "self-test", "fetch"):
            self.assertIn(f"{command} {subcommand}", skill)

        result = subprocess.run(
            [sys.executable, str(CONNECTOR_PATH), "fetch", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for option in (
            "--shop-id",
            "--industry",
            "--time-range-type",
            "--custom-start-date",
            "--custom-end-date",
            "--ages",
            "--genders",
            "--crowd-groups",
            "--brand-scope-type",
            "--brands",
            "--ranking-limit-type",
            "--output",
        ):
            self.assertIn(option, result.stdout)
            self.assertIn(option, skill)

    def test_documents_schema_as_reference_and_fetch_as_authoritative_validation(self):
        skill = self.read_skill()

        self.assertRegex(skill, r"(?is)schema.{0,180}reference metadata")
        self.assertRegex(skill, r"(?is)fetch.{0,180}authoritative validator")
        self.assertRegex(skill, r"(?is)empty.{0,160}parameters.{0,160}page.*selection")

    def test_documents_list_filter_constraints_and_enumerations(self):
        skill = self.read_skill()

        for value in ("LAST_7_DAYS", "LAST_30_DAYS", "CUSTOM"):
            self.assertIn(value, skill)
        self.assertIn("Asia/Shanghai", skill)
        self.assertRegex(skill, r"(?is)today-369.{0,180}today-4")
        self.assertRegex(skill, r"(?is)44.{0,100}days")
        self.assertRegex(skill, r"(?is)multivalue.{0,180}(comma-separated|JSON array)")
        self.assertRegex(skill, r"(?is)SPECIFIED_BRANDS.{0,180}3.{0,80}10")
        self.assertIn("ALL_INDUSTRY", skill)
        self.assertRegex(skill, r"(?is)enumeration.{0,200}(age|gender|crowd|ranking)")

    def test_documents_raw_response_retention_and_scope_boundary(self):
        skill = self.read_skill()

        self.assertIn("payload", skill)
        self.assertIn("files", skill)
        self.assertRegex(skill, r"(?is)--output.{0,160}atomically replaces.{0,120}existing")
        self.assertRegex(skill, r"(?is)raw gateway response.{0,160}retained")
        self.assertRegex(skill, r"(?is)no external artifacts.{0,100}retrieved")
        self.assertRegex(skill, r"(?is)no result contents.{0,100}interpreted")
        for out_of_scope_term in ("video", "frames", "batch", "report", "download", "analysis"):
            self.assertNotIn(out_of_scope_term, skill.lower())

    def test_openai_metadata_has_required_nested_interface_fields(self):
        metadata = yaml.safe_load(OPENAI_YAML_PATH.read_text(encoding="utf-8"))
        interface = metadata["interface"]

        self.assertIsInstance(interface["display_name"], str)
        self.assertTrue(interface["display_name"].strip())
        self.assertIsInstance(interface["short_description"], str)
        self.assertTrue(interface["short_description"].strip())
        self.assertIn(
            "$yuntu-industry-content-rankings-list",
            interface["default_prompt"],
        )


if __name__ == "__main__":
    unittest.main()
