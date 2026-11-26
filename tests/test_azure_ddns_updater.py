"""Tests for the Azure DNS updater without live network or Azure calls."""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.mgmt.dns.models import ARecord, RecordSet
from azure.mgmt.dns.operations import RecordSetsOperations
from schedule import Scheduler

import azure_ddns_updater as updater


CURRENT_IP = "203.0.113.10"
OLD_IP = "203.0.113.20"


def sample_environment(**overrides):
    """Return synthetic configuration for a single updater."""
    environment = {
        "AZURE_CLIENT_ID": "client",
        "AZURE_CLIENT_SECRET": "fixture-secret",
        "AZURE_TENANT_ID": "tenant",
        "SUBSCRIPTION_ID": "subscription",
        "RESOURCE_GROUP": "group",
        "DNS_ZONE": "example.test",
        "RECORD_NAMES": "[home]",
        "INTERVAL_MINUTES": "-1",
    }
    environment.update(overrides)
    return environment


class UpdaterTestCase(unittest.TestCase):
    """Isolate logging and the health file for every test."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.health_file = Path(directory.name) / "health.log"
        health_patch = patch.object(updater, "HEALTH_FILE", self.health_file)
        health_patch.start()
        self.addCleanup(health_patch.stop)
        log_patch = patch.object(updater, "log")
        self.log = log_patch.start()
        self.addCleanup(log_patch.stop)


class ConfigurationTests(UpdaterTestCase):
    def test_parses_names_and_default_interval_without_exposing_secret(self):
        environment = sample_environment(RECORD_NAMES=" [ home, router ] ")
        del environment["INTERVAL_MINUTES"]

        config = updater.load_config(environment)

        self.assertEqual(config.record_names, ("home", "router"))
        self.assertEqual(config.interval_minutes, 5)
        self.assertNotIn("fixture-secret", repr(config))

    def test_missing_and_blank_required_values_are_rejected(self):
        for name in sample_environment():
            if name == "INTERVAL_MINUTES":
                continue
            with self.subTest(name=name, value="missing"):
                environment = sample_environment()
                del environment[name]
                with self.assertRaisesRegex(ValueError, name):
                    updater.load_config(environment)
            with self.subTest(name=name, value="blank"):
                environment = sample_environment(**{name: "  "})
                with self.assertRaisesRegex(ValueError, name):
                    updater.load_config(environment)

    def test_invalid_names_and_intervals_are_rejected(self):
        for value in ("[]", "[home,,router]", "[home, ]"):
            with self.subTest(record_names=value):
                with self.assertRaisesRegex(ValueError, "RECORD_NAMES"):
                    updater.load_config(sample_environment(RECORD_NAMES=value))

        for value in ("", "five", "0", "-0"):
            with self.subTest(interval=value):
                with self.assertRaisesRegex(ValueError, "INTERVAL_MINUTES"):
                    updater.load_config(sample_environment(INTERVAL_MINUTES=value))

    def test_negative_and_positive_intervals_remain_valid(self):
        for value in (-1, 1, 2):
            with self.subTest(interval=value):
                config = updater.load_config(
                    sample_environment(INTERVAL_MINUTES=str(value))
                )
                self.assertEqual(config.interval_minutes, value)


class PublicIpTests(UpdaterTestCase):
    def test_retrieves_an_ipv4_address_with_timeouts(self):
        with patch.object(updater.requests, "get") as get:
            response = get.return_value.__enter__.return_value
            response.json.return_value = {"ip": CURRENT_IP}

            self.assertEqual(updater.get_public_ip(), CURRENT_IP)

        self.assertEqual(get.call_args.kwargs["timeout"], (5, 5))
        response.raise_for_status.assert_called_once()
        get.return_value.__exit__.assert_called_once()

    def test_invalid_response_shapes_and_addresses_fail(self):
        for payload in ([], {}, {"ip": ""}, {"ip": "not-an-ip"}, {"ip": "::1"}):
            with self.subTest(payload=payload):
                with patch.object(updater.requests, "get") as get:
                    get.return_value.__enter__.return_value.json.return_value = payload
                    self.assertIsNone(updater.get_public_ip())

    def test_request_and_json_failures_are_reported(self):
        with patch.object(
            updater.requests, "get", side_effect=requests.RequestException("offline")
        ):
            self.assertIsNone(updater.get_public_ip())
        with patch.object(updater.requests, "get") as get:
            get.return_value.__enter__.return_value.json.side_effect = ValueError(
                "invalid JSON"
            )
            self.assertIsNone(updater.get_public_ip())
            get.return_value.__exit__.assert_called_once()
        self.assertTrue(self.log.called)


class DnsUpdateTests(UpdaterTestCase):
    def setUp(self):
        super().setUp()
        self.config = updater.load_config(sample_environment())
        self.client = MagicMock()

    def test_matching_record_is_not_updated(self):
        self.client.record_sets.get.return_value = RecordSet(
            ttl=1200,
            a_records=[ARecord(ipv4_address=OLD_IP), ARecord(ipv4_address=CURRENT_IP)],
        )

        self.assertTrue(
            updater.update_dns_records(self.config, self.client, CURRENT_IP)
        )
        self.client.record_sets.create_or_update.assert_not_called()

    def test_changed_record_preserves_ttl_and_replaces_addresses(self):
        self.client.record_sets.get.return_value = RecordSet(
            ttl=1200, a_records=[ARecord(ipv4_address=OLD_IP)]
        )

        self.assertTrue(
            updater.update_dns_records(self.config, self.client, CURRENT_IP)
        )

        args = self.client.record_sets.create_or_update.call_args.args
        self.assertEqual(args[:4], ("group", "example.test", "home", "A"))
        self.assertEqual(args[4].ttl, 1200)
        self.assertEqual(
            [record.ipv4_address for record in args[4].a_records], [CURRENT_IP]
        )

    def test_missing_record_uses_default_ttl(self):
        self.client.record_sets.get.side_effect = ResourceNotFoundError(
            message="missing"
        )

        self.assertTrue(
            updater.update_dns_records(self.config, self.client, CURRENT_IP)
        )

        record_set = self.client.record_sets.create_or_update.call_args.args[4]
        self.assertEqual(record_set.ttl, 300)
        self.assertEqual(record_set.a_records[0].ipv4_address, CURRENT_IP)

    def test_failures_are_reported_and_do_not_skip_later_records(self):
        config = updater.load_config(
            sample_environment(RECORD_NAMES="[first,second,third]")
        )
        self.client.record_sets.get.side_effect = [
            ResourceNotFoundError(message="missing"),
            ResourceNotFoundError(message="missing"),
            HttpResponseError(message="read failed"),
        ]
        self.client.record_sets.create_or_update.side_effect = [
            HttpResponseError(message="write failed"),
            None,
        ]

        self.assertFalse(updater.update_dns_records(config, self.client, CURRENT_IP))

        reads = self.client.record_sets.get.call_args_list
        writes = self.client.record_sets.create_or_update.call_args_list
        self.assertEqual([call.args[2] for call in reads], ["first", "second", "third"])
        self.assertEqual([call.args[2] for call in writes], ["first", "second"])


class UpdateCycleTests(UpdaterTestCase):
    def setUp(self):
        super().setUp()
        self.config = updater.load_config(sample_environment())
        credential_patch = patch.object(updater, "ClientSecretCredential")
        self.credential_factory = credential_patch.start()
        self.addCleanup(credential_patch.stop)
        client_patch = patch.object(updater, "DnsManagementClient")
        self.client_factory = client_patch.start()
        self.addCleanup(client_patch.stop)
        self.client = self.client_factory.return_value.__enter__.return_value

    def test_success_updates_health_and_closes_azure_clients(self):
        self.client.record_sets.get.return_value = RecordSet(
            ttl=600, a_records=[ARecord(ipv4_address=CURRENT_IP)]
        )
        with patch.object(updater, "get_public_ip", return_value=CURRENT_IP):
            self.assertTrue(updater.run_update(self.config))

        self.assertEqual(self.health_file.read_text(encoding="utf-8"), "0")
        self.credential_factory.assert_called_once_with(
            "tenant", "client", "fixture-secret"
        )
        credential = self.credential_factory.return_value.__enter__.return_value
        self.client_factory.assert_called_once_with(credential, "subscription")
        self.client_factory.return_value.__exit__.assert_called_once()
        self.credential_factory.return_value.__exit__.assert_called_once()

    def test_ip_failure_marks_unhealthy_without_creating_azure_client(self):
        self.health_file.write_text("0", encoding="utf-8")
        with patch.object(updater, "get_public_ip", return_value=None):
            self.assertFalse(updater.run_update(self.config))

        self.assertEqual(self.health_file.read_text(encoding="utf-8"), "1")
        self.credential_factory.assert_not_called()
        self.client_factory.assert_not_called()

    def test_dns_write_failure_marks_unhealthy(self):
        self.client.record_sets.get.return_value = RecordSet(
            ttl=600, a_records=[ARecord(ipv4_address=OLD_IP)]
        )
        self.client.record_sets.create_or_update.side_effect = HttpResponseError(
            message="write failed"
        )
        with patch.object(updater, "get_public_ip", return_value=CURRENT_IP):
            self.assertFalse(updater.run_update(self.config))

        self.assertEqual(self.health_file.read_text(encoding="utf-8"), "1")

    def test_client_setup_failure_marks_unhealthy(self):
        self.credential_factory.side_effect = ValueError("invalid credentials")
        with patch.object(updater, "get_public_ip", return_value=CURRENT_IP):
            self.assertFalse(updater.run_update(self.config))

        self.assertEqual(self.health_file.read_text(encoding="utf-8"), "1")

    def test_unexpected_error_is_not_swallowed_and_marks_unhealthy(self):
        with patch.object(updater, "get_public_ip", side_effect=RuntimeError("bug")):
            with self.assertRaisesRegex(RuntimeError, "bug"):
                updater.run_update(self.config)

        self.assertEqual(self.health_file.read_text(encoding="utf-8"), "1")


class AzureSdkTests(UpdaterTestCase):
    def test_real_client_and_credential_work_with_mocked_operations(self):
        config = updater.load_config(
            sample_environment(
                AZURE_CLIENT_ID="00000000-0000-0000-0000-000000000001",
                AZURE_TENANT_ID="00000000-0000-0000-0000-000000000002",
                SUBSCRIPTION_ID="00000000-0000-0000-0000-000000000003",
            )
        )
        record_set = RecordSet(ttl=1200, a_records=[ARecord(ipv4_address=OLD_IP)])
        with (
            patch.object(updater, "get_public_ip", return_value=CURRENT_IP),
            patch.object(
                socket.socket,
                "connect",
                side_effect=AssertionError("unexpected network"),
            ),
            patch.object(
                RecordSetsOperations, "get", autospec=True, return_value=record_set
            ),
            patch.object(
                RecordSetsOperations, "create_or_update", autospec=True
            ) as write,
        ):
            self.assertTrue(updater.run_update(config))

        args = write.call_args.args
        self.assertEqual(args[1:5], ("group", "example.test", "home", "A"))
        self.assertEqual(args[5].ttl, 1200)
        self.assertEqual(args[5].a_records[0].ipv4_address, CURRENT_IP)
        self.assertEqual(self.health_file.read_text(encoding="utf-8"), "0")


class EntryPointTests(UpdaterTestCase):
    def test_import_is_inert_and_original_launcher_reports_missing_config(self):
        source_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("azure_ddns_updater.py", "azure-ddns-updater.py"):
                shutil.copyfile(source_root / name, root / name)
            environment = os.environ.copy()
            for name in sample_environment():
                environment.pop(name, None)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"

            imported = subprocess.run(
                [sys.executable, "-c", "import azure_ddns_updater"],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(imported.returncode, 0, imported.stderr)
            self.assertEqual(imported.stdout, "")
            self.assertFalse((root / "health.log").exists())

            started = subprocess.run(
                [sys.executable, str(root / "azure-ddns-updater.py")],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(started.returncode, 1)
            self.assertIn("AZURE_CLIENT_ID", started.stdout)
            self.assertEqual((root / "health.log").read_text(encoding="utf-8"), "1")

    def test_single_run_exit_code_reflects_update_result(self):
        for successful in (True, False):
            with self.subTest(successful=successful):
                with (
                    patch.dict(os.environ, sample_environment()),
                    patch.object(updater, "run_update", return_value=successful),
                    patch.object(updater, "Scheduler") as scheduler_factory,
                ):
                    self.assertEqual(updater.main(), 0 if successful else 1)
                    scheduler_factory.assert_not_called()

    def test_repeating_mode_schedules_the_same_configuration(self):
        scheduler = Scheduler()
        with (
            patch.dict(os.environ, sample_environment(INTERVAL_MINUTES="2")),
            patch.object(
                updater, "run_update", side_effect=[False, False, True]
            ) as run_update,
            patch.object(updater, "Scheduler", return_value=scheduler),
            patch.object(updater, "sleep", side_effect=KeyboardInterrupt),
        ):
            self.assertEqual(updater.main(), 0)
            self.assertEqual(run_update.call_count, 1)
            self.assertEqual(len(scheduler.jobs), 1)
            self.assertEqual(scheduler.jobs[0].interval, 2)
            self.assertEqual(scheduler.jobs[0].unit, "minutes")

            scheduler.run_all()
            scheduler.run_all()
            self.assertEqual(run_update.call_count, 3)
            self.assertEqual(len(scheduler.jobs), 1)
            self.assertEqual(run_update.call_args.args[0].record_names, ("home",))

        messages = [str(call.args[0]) for call in self.log.call_args_list]
        self.assertNotIn("fixture-secret", "\n".join(messages))

    def test_zero_interval_fails_before_network_or_scheduler(self):
        with (
            patch.dict(os.environ, sample_environment(INTERVAL_MINUTES="0")),
            patch.object(updater, "run_update") as run_update,
            patch.object(updater, "Scheduler") as scheduler_factory,
        ):
            self.assertEqual(updater.main(), 1)
            run_update.assert_not_called()
            scheduler_factory.assert_not_called()

        self.assertEqual(self.health_file.read_text(encoding="utf-8"), "1")
        messages = [str(call.args[0]) for call in self.log.call_args_list]
        self.assertTrue(
            any(
                "INTERVAL_MINUTES" in message and "zero" in message
                for message in messages
            )
        )


if __name__ == "__main__":
    unittest.main()
