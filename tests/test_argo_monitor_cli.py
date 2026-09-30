"""Unit tests for argo_monitor command-line interface arguments."""

import unittest
from pathlib import Path

from argo_monitor import parser


class ArgoMonitorCliTests(unittest.TestCase):
    def test_parser_defaults(self):
        args = parser().parse_args([])
        self.assertEqual(args.config, Path("config.yaml"))
        self.assertFalse(args.dry_run)
        self.assertIsNone(args.saved_export)
        self.assertEqual(args.only, "all")
        self.assertFalse(args.test)
        self.assertIsNone(args.recipient)

    def test_parser_test_and_recipient_flags(self):
        args = parser().parse_args(["--only", "daily", "--test", "--recipient", "john@kruser.org"])
        self.assertEqual(args.only, "daily")
        self.assertTrue(args.test)
        self.assertEqual(args.recipient, "john@kruser.org")


if __name__ == "__main__":
    unittest.main()
