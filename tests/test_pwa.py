"""
Tests for Progressive Web App (PWA) configuration and server MIME types.
Verifies manifest.json, sw.js, icons, index.html links, and server MIME handling.
"""

import json
import os
import pytest

from src.dashboard.server import DashboardRequestHandler, DASHBOARD_DIR


def test_manifest_json_validity():
    """Verify manifest.json exists, is valid JSON, and contains required PWA fields."""
    manifest_path = os.path.join(DASHBOARD_DIR, "manifest.json")
    assert os.path.exists(manifest_path), "manifest.json does not exist"

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("name") == "Larsson Scanner"
    assert data.get("short_name") == "Larsson"
    assert data.get("start_url") == "/"
    assert data.get("display") == "standalone"
    assert data.get("background_color") == "#0a0a0a"
    assert data.get("theme_color") == "#FFD700"

    icons = data.get("icons", [])
    assert len(icons) >= 2, "manifest must contain at least 192x192 and 512x512 icons"

    sizes = [icon.get("sizes") for icon in icons]
    assert "192x192" in sizes
    assert "512x512" in sizes


def test_pwa_icons_exist_and_valid():
    """Verify SVG and PNG icon files exist in dashboard/icons/."""
    icons_dir = os.path.join(DASHBOARD_DIR, "icons")
    assert os.path.exists(icons_dir), "icons/ directory does not exist"

    required_icons = [
        "icon-192.svg",
        "icon-512.svg",
        "icon-192.png",
        "icon-512.png",
    ]
    for filename in required_icons:
        icon_path = os.path.join(icons_dir, filename)
        assert os.path.exists(icon_path), f"Missing icon: {filename}"
        assert os.path.getsize(icon_path) > 0, f"Icon {filename} is empty"

    # Verify PNG magic bytes
    for png_name in ["icon-192.png", "icon-512.png"]:
        png_path = os.path.join(icons_dir, png_name)
        with open(png_path, "rb") as f:
            header = f.read(8)
            assert header == b"\x89PNG\r\n\x1a\n", f"Invalid PNG magic bytes in {png_name}"


def test_service_worker_file():
    """Verify sw.js exists and contains core PWA caching strategies."""
    sw_path = os.path.join(DASHBOARD_DIR, "sw.js")
    assert os.path.exists(sw_path), "sw.js does not exist"

    with open(sw_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "CACHE_NAME" in content
    assert "STATIC_ASSETS" in content
    assert "data.json" in content
    assert "fetch" in content
    assert "install" in content


def test_index_html_pwa_integration():
    """Verify index.html includes manifest link, theme-color meta, and install button."""
    index_path = os.path.join(DASHBOARD_DIR, "index.html")
    assert os.path.exists(index_path), "index.html does not exist"

    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    assert '<link rel="manifest" href="manifest.json">' in html
    assert '<meta name="theme-color" content="#FFD700">' in html
    assert 'id="btnInstallApp"' in html
    assert 'beforeinstallprompt' in html
    assert 'serviceWorker' in html
    assert 'offlineDataBanner' in html


def test_server_pwa_mime_types():
    """Verify DashboardRequestHandler serves manifest.json and sw.js with proper MIME types."""
    handler = DashboardRequestHandler.__new__(DashboardRequestHandler)

    manifest_mime = handler.guess_type(os.path.join(DASHBOARD_DIR, "manifest.json"))
    assert manifest_mime == "application/manifest+json"

    sw_mime = handler.guess_type(os.path.join(DASHBOARD_DIR, "sw.js"))
    assert sw_mime == "application/javascript"

    svg_mime = handler.guess_type(os.path.join(DASHBOARD_DIR, "icons", "icon-192.svg"))
    assert svg_mime == "image/svg+xml"

    png_mime = handler.guess_type(os.path.join(DASHBOARD_DIR, "icons", "icon-192.png"))
    assert png_mime == "image/png"
