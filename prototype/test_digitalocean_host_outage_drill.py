"""Security tests for the live DigitalOcean recovery transport."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from research.infra import digitalocean_host_outage_drill as drill


class PinnedSshTransportTests(unittest.TestCase):
    def test_transport_disables_tofu_and_global_known_hosts(self):
        options = drill.ssh_transport_options("/tmp/key", "/tmp/known_hosts")
        self.assertIn("StrictHostKeyChecking=yes", options)
        self.assertIn("IdentitiesOnly=yes", options)
        self.assertIn("UserKnownHostsFile=/tmp/known_hosts", options)
        self.assertIn("GlobalKnownHostsFile=/dev/null", options)
        self.assertNotIn("StrictHostKeyChecking=accept-new", options)

    def test_missing_known_hosts_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                drill.validate_pinned_host_key("192.0.2.10", str(Path(tmp) / "missing"))

    def test_empty_known_hosts_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "known_hosts"
            path.write_text("", encoding="utf-8")
            with self.assertRaises(SystemExit):
                drill.validate_pinned_host_key("192.0.2.10", str(path))

    @patch("research.infra.digitalocean_host_outage_drill.subprocess.run")
    def test_exact_target_key_must_be_found(self, run):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "known_hosts"
            path.write_text("192.0.2.10 ssh-ed25519 AAAATEST\n", encoding="utf-8")
            run.return_value = Mock(returncode=0, stdout="# Host 192.0.2.10 found: line 1\n", stderr="")
            drill.validate_pinned_host_key("192.0.2.10", str(path))
            self.assertEqual(run.call_args.args[0], ["ssh-keygen", "-F", "192.0.2.10", "-f", str(path)])

    @patch("research.infra.digitalocean_host_outage_drill.subprocess.run")
    def test_unpinned_target_fails_closed(self, run):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "known_hosts"
            path.write_text("192.0.2.11 ssh-ed25519 AAAATEST\n", encoding="utf-8")
            run.return_value = Mock(returncode=1, stdout="", stderr="")
            with self.assertRaises(SystemExit):
                drill.validate_pinned_host_key("192.0.2.10", str(path))


if __name__ == "__main__":
    unittest.main()
