import re
import subprocess
import sys
import unittest
from pathlib import Path

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
        self.assertIn("name: 云图行业内容榜单列表", frontmatter.group(1))
        description = re.search(r"^description: (.+)$", frontmatter.group(1), re.MULTILINE)
        self.assertIsNotNone(description)
        self.assertTrue(description.group(1).startswith("适用于"))
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
        self.assertIn("受信任的纯 HTTPS 网关 URL", skill)
        self.assertIn("不得使用 IP 字面量、userinfo、查询参数或片段", skill)
        self.assertRegex(skill, r"凭证.{0,80}环境变量")
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

        self.assertRegex(skill, r"(?s)schema.{0,180}参考元数据")
        self.assertRegex(skill, r"(?s)fetch.{0,180}权威校验器")
        self.assertRegex(skill, r"空参数.{0,160}页面当前选择")

    def test_documents_list_filter_constraints_and_enumerations(self):
        skill = self.read_skill()

        for value in ("LAST_7_DAYS", "LAST_30_DAYS", "CUSTOM"):
            self.assertIn(value, skill)
        self.assertIn("Asia/Shanghai", skill)
        self.assertRegex(skill, r"(?is)today-369.{0,180}today-4")
        self.assertRegex(skill, r"44.{0,100}天")
        self.assertRegex(skill, r"多值输入.{0,180}(逗号分隔列表|JSON 数组)")
        self.assertRegex(skill, r"(?is)SPECIFIED_BRANDS.{0,180}3.{0,80}10")
        self.assertIn("ALL_INDUSTRY", skill)
        self.assertRegex(skill, r"(年龄|性别|人群|榜单).{0,200}枚举值")

    def test_documents_raw_response_retention_and_scope_boundary(self):
        skill = self.read_skill()

        self.assertIn("payload", skill)
        self.assertIn("files", skill)
        self.assertRegex(skill, r"(?s)--output.{0,160}原子替换.{0,120}已有")
        self.assertRegex(skill, r"原始网关响应.{0,160}保留")
        self.assertRegex(skill, r"不会检索外部产物")
        self.assertRegex(skill, r"不会解读结果内容")
        for out_of_scope_term in ("video", "frames", "batch", "report", "download", "analysis"):
            self.assertNotIn(out_of_scope_term, skill.lower())

    def test_openai_metadata_has_required_nested_interface_fields(self):
        metadata = OPENAI_YAML_PATH.read_text(encoding="utf-8")

        self.assertRegex(metadata, r"(?m)^interface:\s*$")
        self.assertRegex(metadata, r'(?m)^  display_name: "[^"\n]+"\s*$')
        self.assertRegex(metadata, r'(?m)^  short_description: "[^"\n]+"\s*$')
        self.assertIn(
            "$云图行业内容榜单列表",
            metadata,
        )


if __name__ == "__main__":
    unittest.main()
