import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from scripts import team_ops


VALID_FIELDS = {
    "bottom_line": "Ship the charts, but block the guardrail — its threshold is broken.",
    "scope": "Whether the plan is safe to call engineering-unblocked.",
    "found": "The 2.0x threshold is unreachable at the stated inputs (max is 1.346x).",
    "why": "The wiki would declare the work unblocked on a number that cannot exist.",
    "call": "NEEDS WORK, blocking; fixable in one cycle.",
    "confidence": "high",
    "confidence_basis": "Re-ran compute()/computeM2() against the actual code.",
    "dissent": "Waving it through now — rejected: the mechanism is proven, the number is not.",
}


def build_output(overrides=None, *, drop=None, fence=True):
    """Assemble a realistic worker output: five-part prose + Position + the
    fenced REPORT block. Only the block is what validate_report reads."""
    fields = dict(VALID_FIELDS)
    if overrides:
        fields.update(overrides)
    if drop:
        for key in drop:
            fields.pop(key, None)
    block = "\n".join(
        [team_ops.REPORT_BEGIN]
        + [f'{k}: "{v}"' for k, v in fields.items()]
        + [team_ops.REPORT_END])
    prose = (
        f"**Bottom line** — {fields.get('bottom_line', '')}\n\n"
        "## Position (self-authored)\nSame, distilled to one paragraph.")
    return prose + "\n\n" + block if fence else prose


def _write(td, text):
    path = Path(td) / "report.md"
    path.write_text(text)
    return path


class TestValidateReport(unittest.TestCase):
    def test_valid_report_passes(self):
        with tempfile.TemporaryDirectory() as td:
            result = team_ops.validate_report(_write(td, build_output()))
            self.assertTrue(result["ok"], result["errors"])
            self.assertEqual(result["errors"], [])
            self.assertEqual(result["fields"]["confidence"], "high")

    def test_missing_fence_is_error(self):
        with tempfile.TemporaryDirectory() as td:
            result = team_ops.validate_report(_write(td, build_output(fence=False)))
            self.assertFalse(result["ok"])
            self.assertTrue(any("missing REPORT block" in e for e in result["errors"]),
                            result["errors"])

    def test_each_missing_field_is_error(self):
        for field in team_ops.REPORT_REQUIRED_FIELDS:
            with tempfile.TemporaryDirectory() as td:
                result = team_ops.validate_report(
                    _write(td, build_output(drop=[field])))
                self.assertFalse(result["ok"], field)
                self.assertIn(f"missing field: {field}", result["errors"])

    def test_empty_field_is_error(self):
        with tempfile.TemporaryDirectory() as td:
            result = team_ops.validate_report(
                _write(td, build_output({"found": ""})))
            self.assertFalse(result["ok"])
            self.assertIn("empty field: found", result["errors"])

    def test_bad_confidence_is_error(self):
        with tempfile.TemporaryDirectory() as td:
            result = team_ops.validate_report(
                _write(td, build_output({"confidence": "pretty sure"})))
            self.assertFalse(result["ok"])
            self.assertTrue(any("confidence must be" in e for e in result["errors"]),
                            result["errors"])

    def test_confidence_values_case_insensitive(self):
        for value in ("high", "Medium", "LOW"):
            with tempfile.TemporaryDirectory() as td:
                result = team_ops.validate_report(
                    _write(td, build_output({"confidence": value})))
                self.assertTrue(result["ok"], f"{value}: {result['errors']}")

    def test_bottom_line_over_budget_is_error(self):
        with tempfile.TemporaryDirectory() as td:
            result = team_ops.validate_report(
                _write(td, build_output({"bottom_line": "x" * 400})))
            self.assertFalse(result["ok"])
            self.assertTrue(any("bottom_line exceeds" in e for e in result["errors"]),
                            result["errors"])

    def test_field_over_budget_is_error(self):
        with tempfile.TemporaryDirectory() as td:
            result = team_ops.validate_report(
                _write(td, build_output({"why": "x" * 1600})))
            self.assertFalse(result["ok"])
            self.assertTrue(any("why exceeds" in e for e in result["errors"]),
                            result["errors"])


class TestParseReportBlock(unittest.TestCase):
    def test_quotes_are_stripped(self):
        fields = team_ops.parse_report_block(build_output())
        self.assertEqual(fields["call"], VALID_FIELDS["call"])
        self.assertFalse(fields["call"].startswith('"'))

    def test_last_duplicate_key_wins(self):
        block = (f"{team_ops.REPORT_BEGIN}\n"
                 'confidence: "high"\nconfidence: "low"\n'
                 f"{team_ops.REPORT_END}")
        self.assertEqual(team_ops.parse_report_block(block)["confidence"], "low")

    def test_none_without_fence(self):
        self.assertIsNone(team_ops.parse_report_block("no fence here"))

    def test_prose_lines_inside_block_ignored(self):
        block = (f"{team_ops.REPORT_BEGIN}\n"
                 "This is a stray note.\n\n"
                 'bottom_line: "the answer"\n'
                 f"{team_ops.REPORT_END}")
        fields = team_ops.parse_report_block(block)
        self.assertEqual(fields, {"bottom_line": "the answer"})


class TestValidateReportCli(unittest.TestCase):
    def _run(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = team_ops.main(argv)
        return code, json.loads(buf.getvalue())

    def test_cli_ok_exit_0(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write(td, build_output())
            code, payload = self._run(["validate-report", str(path)])
            self.assertEqual(code, 0)
            self.assertTrue(payload["ok"])

    def test_cli_invalid_exit_1(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write(td, build_output(drop=["dissent"]))
            code, payload = self._run(["validate-report", str(path)])
            self.assertEqual(code, 1)
            self.assertFalse(payload["ok"])

    def test_cli_missing_file_exit_2(self):
        code, payload = self._run(["validate-report", "/no/such/report.md"])
        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])


if __name__ == "__main__":
    unittest.main()
