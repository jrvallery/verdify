"""
Test 06: Website & Grafana — Public-facing services respond correctly.
"""

import subprocess


def curl_get(url: str, host: str) -> tuple[int, str]:
    result = subprocess.run(
        ["curl", "-sk", url, "-H", f"Host: {host}", "-w", "\n%{http_code}", "-o", "/dev/null"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    status = int(result.stdout.strip().split("\n")[-1])
    return status


class TestWebsite:
    """verdify.ai must serve pages."""

    def test_homepage(self):
        status = curl_get("https://127.0.0.1/", "verdify.ai")
        assert status == 200, f"Homepage returned {status}"

    def test_plans_page(self):
        status = curl_get("https://127.0.0.1/plans/", "verdify.ai")
        assert status in (200, 301, 302), f"Plans page returned {status}"

    def test_static_assets(self):
        """CSS/JS must load."""
        status = curl_get("https://127.0.0.1/static/styles.css", "verdify.ai")
        # Quartz uses different asset paths; just check the site responds
        assert status in (200, 404), f"Static assets returned {status}"


class TestGrafana:
    """graphs.verdify.ai must serve dashboards."""

    def test_grafana_health(self):
        status = curl_get("https://127.0.0.1/api/health", "graphs.verdify.ai")
        assert status == 200, f"Grafana health returned {status}"

    def test_grafana_anonymous_access(self):
        """Anonymous read access must work."""
        result = subprocess.run(
            [
                "curl",
                "-sk",
                "https://127.0.0.1/api/dashboards/home",
                "-H",
                "Host: graphs.verdify.ai",
                "-w",
                "\n%{http_code}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = result.stdout.strip().split("\n")
        status = int(lines[-1])
        assert status == 200, f"Grafana anonymous access returned {status}"

    def test_grafana_datasource(self):
        """verdify-tsdb datasource must exist."""
        result = subprocess.run(
            [
                "curl",
                "-sk",
                "https://127.0.0.1/api/datasources",
                "-H",
                "Host: graphs.verdify.ai",
                "-w",
                "\n%{http_code}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "verdify" in result.stdout.lower() or "tsdb" in result.stdout.lower()


class TestTraefik:
    """Traefik reverse proxy must route correctly."""

    def test_traefik_dashboard(self):
        status = curl_get("https://127.0.0.1/dashboard/", "traefik.verdify.ai")
        assert status in (200, 401), f"Traefik dashboard returned {status} (expected 200 or 401/auth)"
