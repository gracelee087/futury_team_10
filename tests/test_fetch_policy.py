"""Tests for the fetch URL policy (pipeline.registry.fetch) — fail closed, no network needed.

Literal-IP hosts and localhost keep these tests offline: getaddrinfo on a
literal IP or /etc/hosts name performs no DNS query.
"""
from __future__ import annotations

import unittest

from pipeline.registry.fetch import validate_http_url

PUBLIC_IP = "93.184.216.34"  # documented public example address, literal -> no DNS


class TestFetchPolicy(unittest.TestCase):
    def test_allows_public_https_literal_ip(self):
        url = f"https://{PUBLIC_IP}/doc.pdf"
        self.assertEqual(validate_http_url(url), url)

    def test_allows_public_http(self):
        url = f"http://8.8.8.8/doc.pdf"
        self.assertEqual(validate_http_url(url), url)

    def test_rejects_non_http_schemes(self):
        for url in (f"ftp://{PUBLIC_IP}/x", f"file:///etc/passwd", f"gopher://{PUBLIC_IP}/x"):
            with self.assertRaises(ValueError, msg=url):
                validate_http_url(url)

    def test_rejects_missing_host(self):
        with self.assertRaises(ValueError):
            validate_http_url("https:///path")

    def test_rejects_unresolvable_host(self):
        with self.assertRaises(ValueError):
            validate_http_url("https://this-host-does-not-exist.invalid/")

    def test_rejects_localhost_and_loopback(self):
        for url in ("https://localhost/x", f"https://127.0.0.1/x", "https://[::1]/x"):
            with self.assertRaises(ValueError, msg=url):
                validate_http_url(url)

    def test_rejects_private_ranges(self):
        for host in ("10.0.0.1", "172.16.0.1", "192.168.1.1"):
            with self.assertRaises(ValueError, msg=host):
                validate_http_url(f"https://{host}/x")

    def test_rejects_link_local_metadata_and_unspecified(self):
        for host in ("169.254.169.254", "0.0.0.0"):
            with self.assertRaises(ValueError, msg=host):
                validate_http_url(f"https://{host}/x")


if __name__ == "__main__":
    unittest.main()
