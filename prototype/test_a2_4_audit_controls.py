"""Run committed A2.4 audit scripts inside the established prototype CI.

This wrapper lives under prototype/ so the repository's existing Prototype
validation workflow discovers it on PRs. It executes the exact committed
script files as subprocesses; it does not duplicate their assertions.
"""
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "research" / "audits" / "sfc_scce_a2_4_2026-11-11"


class A24AuditControlScriptsTest(unittest.TestCase):
    def _run_script(self, script_name):
        script = AUDIT_DIR / script_name
        self.assertTrue(script.is_file(), f"missing audit control script: {script}")
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=60,
            check=False,
        )
        self.assertEqual(
            result.returncode, 0,
            f"{script_name} exited {result.returncode}:\n{result.stdout}",
        )
        self.assertIn("PASS", result.stdout, result.stdout)

    def test_audit_sfc_six_sector(self):
        self._run_script("audit_sfc_six_sector.py")

    def test_audit_capital_bridge(self):
        self._run_script("audit_capital_bridge.py")

    def test_audit_same_cohort_capital(self):
        self._run_script("audit_same_cohort_capital.py")

    def test_audit_b81_cohort_contract(self):
        self._run_script("audit_b81_cohort_contract.py")

    def test_audit_product_dimensions(self):
        self._run_script("audit_product_dimensions.py")

    def test_audit_product_valuation_adapter(self):
        self._run_script("audit_product_valuation_adapter.py")

    def test_audit_physical_flow_register(self):
        self._run_script("audit_physical_flow_register.py")

    def test_audit_financial_events(self):
        self._run_script("audit_financial_events.py")

    def test_audit_financial_journal(self):
        self._run_script("audit_financial_journal.py")

    def test_audit_instrument_stock_flow(self):
        self._run_script("audit_instrument_stock_flow.py")

    def test_audit_labour_consent(self):
        self._run_script("audit_labour_consent.py")


if __name__ == "__main__":
    unittest.main()
