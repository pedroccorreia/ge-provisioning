#!/usr/bin/env python3
"""
Red Team Adversarial / Negative Testing Harness for Affiliate Provisioning.

Systematically verifies:
1. allocate_licenses.py failure on missing config file.
2. allocate_licenses.py failure on malformed config JSON.
3. allocate_licenses.py failure on missing required fields (billing_account, subscription_id, allocations).
4. allocate_licenses.py preflight failure on project number mismatch.
5. allocate_licenses.py preflight failure on insufficient pool seats.
6. allocate_licenses.py safety: --dry-run does NOT execute destructive writes.
7. verify.py handling of missing arguments and invalid project IDs.
8. Data Scrubbing: 0 leaked customer identifiers, domains, tokens, or UUIDs in git tracked files.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Ensure repo root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import scripts.allocate_licenses as alloc_module
import scripts.verify as verify_module


class TestAllocateLicensesNegative(unittest.TestCase):
    """Negative and adversarial test cases for allocate_licenses.py."""

    def test_missing_config_file_fails_loudly(self):
        """Test failure when the specified config file does not exist."""
        non_existent_file = os.path.join(tempfile.gettempdir(), "non_existent_license_config_9999.json")
        if os.path.exists(non_existent_file):
            os.remove(non_existent_file)

        # 1. Direct function call test
        with self.assertRaises(FileNotFoundError) as ctx:
            alloc_module.load_config(non_existent_file)
        self.assertIn("Configuration file not found", str(ctx.exception))

        # 2. CLI invocation test
        res = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "scripts", "allocate_licenses.py"), "--config-file", non_existent_file, "--list"],
            capture_output=True,
            text=True
        )
        self.assertNotEqual(res.returncode, 0, f"Expected non-zero exit code, got {res.returncode}")
        self.assertIn("Configuration file not found", res.stderr)

    def test_malformed_config_json_fails_loudly(self):
        """Test failure when the configuration file contains corrupted JSON."""
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{\n  \"billing_account\": \"000000-111111-222222\",\n  BROKEN_JSON: true\n")
            temp_path = f.name

        try:
            # 1. Direct function call test
            with self.assertRaises(ValueError) as ctx:
                alloc_module.load_config(temp_path)
            self.assertIn("Invalid JSON format", str(ctx.exception))

            # 2. CLI invocation test
            res = subprocess.run(
                [sys.executable, os.path.join(REPO_ROOT, "scripts", "allocate_licenses.py"), "--config-file", temp_path, "--list"],
                capture_output=True,
                text=True
            )
            self.assertNotEqual(res.returncode, 0, f"Expected non-zero exit code, got {res.returncode}")
            self.assertIn("Invalid JSON format", res.stderr)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_missing_required_fields_in_config(self):
        """Test failure when required fields (billing_account, subscription_id, allocations) are missing."""
        required_fields = ["billing_account", "subscription_id", "allocations"]

        base_valid_config = {
            "licensing_project": "test-licensing-proj",
            "billing_account": "000000-111111-222222",
            "license_config_id": "test-lic-cfg-001",
            "subscription_id": "sub-12345",
            "allocations": [
                {"project_id": "test-p1", "project_number": "111111", "seat_count": 2}
            ]
        }

        for field in required_fields:
            corrupted = dict(base_valid_config)
            del corrupted[field]

            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
                json.dump(corrupted, f)
                temp_path = f.name

            try:
                # Direct function call
                with self.assertRaises(ValueError) as ctx:
                    alloc_module.load_config(temp_path)
                self.assertIn(f"Missing required field(s)", str(ctx.exception))
                self.assertIn(field, str(ctx.exception))

                # CLI test
                res = subprocess.run(
                    [sys.executable, os.path.join(REPO_ROOT, "scripts", "allocate_licenses.py"), "--config-file", temp_path, "--list"],
                    capture_output=True,
                    text=True
                )
                self.assertNotEqual(res.returncode, 0)
                self.assertIn(f"Missing required field(s)", res.stderr)
                self.assertIn(field, res.stderr)
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

    @patch("scripts.allocate_licenses.get_project_metadata")
    def test_preflight_failure_on_project_number_mismatch(self, mock_get_metadata):
        """Test that preflight assertion aborts if actual GCP project number does not match expected."""
        mock_get_metadata.return_value = {
            "projectNumber": "999999999999",  # CRM has this number
            "lifecycleState": "ACTIVE"
        }

        allocations = [
            {
                "project_id": "sample-customer-prod",
                "project_number": "123456789012",  # Config expects this number -> MISMATCH
                "seat_count": 5
            }
        ]

        with self.assertRaises(ValueError) as ctx:
            alloc_module.run_preflight_assertions(
                allocations=allocations,
                billing_account="012345-6789AB-CDEF01",
                license_config_id="lic-cfg-001",
                central_project="billing-project",
                location="global",
                token="dummy-token",
                dry_run=False
            )
        err_msg = str(ctx.exception)
        self.assertIn("Preflight assertion failed for project 'sample-customer-prod'", err_msg)
        self.assertIn("Expected Project Number: 123456789012", err_msg)
        self.assertIn("Actual GCP Project Number: 999999999999", err_msg)

    @patch("scripts.allocate_licenses.get_project_metadata")
    def test_preflight_failure_on_inactive_project(self, mock_get_metadata):
        """Test that preflight assertion aborts if project is not ACTIVE (e.g. DELETE_REQUESTED)."""
        mock_get_metadata.return_value = {
            "projectNumber": "123456789012",
            "lifecycleState": "DELETE_REQUESTED"
        }

        allocations = [
            {"project_id": "sample-customer-prod", "project_number": "123456789012", "seat_count": 5}
        ]

        with self.assertRaises(ValueError) as ctx:
            alloc_module.run_preflight_assertions(
                allocations=allocations,
                billing_account="012345-6789AB-CDEF01",
                license_config_id="lic-cfg-001",
                central_project="billing-project",
                location="global",
                token="dummy-token"
            )
        self.assertIn("lifecycle state is 'DELETE_REQUESTED'", str(ctx.exception))

    @patch("scripts.allocate_licenses.get_project_metadata")
    @patch("scripts.allocate_licenses.get_billing_account_license_config")
    def test_preflight_failure_on_insufficient_pool_seats(self, mock_get_billing_cfg, mock_get_metadata):
        """Test that preflight assertion aborts if requested seats exceed available billing pool capacity."""
        mock_get_metadata.return_value = {
            "projectNumber": "123456789012",
            "lifecycleState": "ACTIVE"
        }
        # Billing account only has 2 seats available, but allocations request 5 seats
        mock_get_billing_cfg.return_value = {
            "licenseCount": "10",
            "availableLicenseCount": "2"
        }

        allocations = [
            {
                "project_id": "sample-customer-prod",
                "project_number": "123456789012",
                "seat_count": 5
            }
        ]

        with self.assertRaises(ValueError) as ctx:
            alloc_module.run_preflight_assertions(
                allocations=allocations,
                billing_account="012345-6789AB-CDEF01",
                license_config_id="lic-cfg-001",
                central_project="billing-project",
                location="global",
                token="dummy-token",
                dry_run=False
            )
        err_msg = str(ctx.exception)
        self.assertIn("Insufficient license seats in billing pool", err_msg)
        self.assertIn("Requested: 5", err_msg)
        self.assertIn("Available: 2", err_msg)

    @patch("scripts.allocate_licenses.make_request")
    def test_dry_run_does_not_execute_destructive_writes(self, mock_make_request):
        """Test that --dry-run guarantees zero write/mutation API calls."""
        # 1. Test distribute_license_config with dry_run=True
        dist_res = alloc_module.distribute_license_config(
            billing_account="012345-6789AB-CDEF01",
            license_config_id="lic-cfg-001",
            project_number="123456789012",
            seat_count=5,
            token="dummy-token",
            central_project="billing-project",
            dry_run=True
        )
        self.assertEqual(dist_res, {})
        mock_make_request.assert_not_called()

        # 2. Test configure_auto_register with dry_run=True
        auto_res = alloc_module.configure_auto_register(
            target_project_id="sample-customer-prod",
            location="global",
            full_license_config_name="projects/123/locations/global/licenseConfigs/cfg-1",
            token="dummy-token",
            seat_count=5,
            dry_run=True
        )
        self.assertEqual(auto_res, {})
        mock_make_request.assert_not_called()


class TestVerifyNegative(unittest.TestCase):
    """Negative and adversarial test cases for verify.py."""

    def test_verify_missing_explicit_config_fails(self):
        """Test that verify.py exits with error when an explicit non-existent config file is passed."""
        res = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "scripts", "verify.py"), "--config-file", "does_not_exist.json"],
            capture_output=True,
            text=True
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Configuration file not found", res.stderr)

    @patch("scripts.verify.make_request")
    def test_verify_project_with_invalid_id_returns_failures(self, mock_make_request):
        """Test that verify_project fails gracefully on invalid/non-existent project ID."""
        # Mock 404 / 401 response for all Discovery Engine endpoints
        mock_make_request.return_value = {
            "_error": 404,
            "_message": "Project 'invalid-project-xyz' not found."
        }

        success = verify_module.verify_project(
            project_id="invalid-project-xyz",
            location="global",
            token="dummy-token"
        )
        self.assertFalse(success, "verify_project should return False when components fail or return 404")


class TestDataScrubbing(unittest.TestCase):
    """Red Team Data Scrubbing validation across all git-tracked files."""

    LEAK_PATTERNS = [
        "rwg",
        "Ray White",
        "altostrat",
        "pcorreia",
        "trusty-legend-405710",
        "affiliates-bootstrap",
        "0111AA-12FED7-0F6152",
        "ca1a2f23-797f-4cf7-ab6f-74fd5f3ca651",
        "05eab18d-9cd5-4ba6-966f-ff796c7d27a8",
    ]

    def test_no_leaks_in_tracked_files(self):
        """Systematically search all git-tracked files for customer names, domains, or real IDs."""
        tracked_files = subprocess.check_output(
            ["git", "ls-files"],
            cwd=REPO_ROOT,
            text=True
        ).splitlines()

        self.assertTrue(len(tracked_files) > 0, "Expected git tracked files to be non-empty")

        leaks_found = []
        for file_rel in tracked_files:
            file_abs = os.path.join(REPO_ROOT, file_rel)
            if not os.path.isfile(file_abs):
                continue

            try:
                with open(file_abs, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception as e:
                self.fail(f"Could not read tracked file {file_rel}: {e}")

            for pattern in self.LEAK_PATTERNS:
                if pattern.lower() in content.lower():
                    # If file is this test file itself, ignore matching pattern string definitions
                    if file_rel == "scripts/test_red.py":
                        continue
                    leaks_found.append((file_rel, pattern))

        self.assertEqual(
            len(leaks_found), 0,
            f"Sensitive patterns leaked in git-tracked files: {leaks_found}"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
