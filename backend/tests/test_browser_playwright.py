from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from pathlib import Path

import pytest

from app.services.browser_controller import BrowserController
from app.services.page_extractor import (
    parse_google_results_from_html,
    parse_linkedin_posts_from_html,
    parse_youtube_about_from_html,
)


MOCK_LINKEDIN_HTML = """
<!doctype html>
<html>
<head><title>Real Estate Podcast Search | LinkedIn</title></head>
<body>
  <input id="search-box" type="text" placeholder="Search" />
  <button id="latest-btn" onclick="document.getElementById('status').innerText='Sorted by Latest'">Latest</button>
  <div id="status">Top</div>
  <div class="feed-shared-update-v2">
    <a class="update-components-actor__name" href="https://www.linkedin.com/in/alex-rivera-re">Alex Rivera</a>
    <a href="https://www.linkedin.com/feed/update/urn:li:activity:777888999">View post</a>
    <time>2d</time>
    <p class="feed-shared-update-v2__description">
      Welcome back to the Skyline Real Estate Podcast Episode 42! Hosted by Alex Rivera, Founder at Skyline Realty Capital.
      Today we welcome special guest Jordan Blake to discuss commercial real estate syndication.
      Watch the full episode on YouTube: https://www.youtube.com/@SkylineRealEstatePodcast
    </p>
    <video width="1280" height="720" poster=""></video>
  </div>
  <div style="height: 1500px;">Spacer</div>
</body>
</html>
"""

MOCK_YOUTUBE_ABOUT_HTML = """
<!doctype html>
<html>
<head><title>Skyline Real Estate Podcast - YouTube</title></head>
<body>
  <h1>Skyline Real Estate Podcast</h1>
  <div id="description">
    Weekly interviews with commercial real estate operators.
    Business inquiries: studio@skylinerealtycapital.com
    Website: https://skylinerealtycapital.com
  </div>
</body>
</html>
"""

MOCK_LOGIN_WALL_HTML = """
<!doctype html>
<html>
<head><title>Sign In to LinkedIn</title></head>
<body>
  <h1>Sign in</h1>
  <p>Join now or Sign in to view more posts.</p>
</body>
</html>
"""


@pytest.fixture(scope="module")
def local_site():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path.startswith("/linkedin"):
                body = MOCK_LINKEDIN_HTML.encode("utf-8")
            elif self.path.startswith("/youtube/about"):
                body = MOCK_YOUTUBE_ABOUT_HTML.encode("utf-8")
            elif self.path.startswith("/authwall"):
                body = MOCK_LOGIN_WALL_HTML.encode("utf-8")
            else:
                body = b"<html><head><title>Test Home</title></head><body><a href='/linkedin'>Go LinkedIn</a></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()


@pytest.mark.asyncio
async def test_playwright_navigation_click_type_scroll_screenshot_and_gate(local_site: str, tmp_path: Path):
    bc = BrowserController()
    try:
        await bc.start(headless=True)
        assert bc.is_active

        # Navigation + screenshot + DOM extraction
        res = await bc.open_url(f"{local_site}/linkedin", screenshot_label="test_li")
        assert res.success
        assert res.screenshot_path and Path(res.screenshot_path).exists()
        assert res.gate and not res.gate.restricted

        # Typing & clicking
        type_res = await bc.type_text("#search-box", "Real Estate Podcast")
        assert type_res.success
        click_res = await bc.click("#latest-btn")
        assert click_res.success
        txt = await bc.read_visible_text()
        assert "Sorted by Latest" in txt

        # Scroll & Tab management
        scroll_res = await bc.scroll("down", 600)
        assert scroll_res.success
        tab_res = await bc.open_tab(f"{local_site}/youtube/about")
        assert tab_res.success
        yt_html = await bc.get_html()
        yt_info = parse_youtube_about_from_html(yt_html, f"{local_site}/youtube")
        assert "studio@skylinerealtycapital.com" in yt_info["emails"]

        # Switch back & test LinkedIn HTML parsing
        back_tab = await bc.switch_tab(0)
        assert back_tab.success
        li_posts = parse_linkedin_posts_from_html(await bc.get_html())
        assert len(li_posts) == 1
        assert li_posts[0]["posting_account"] == "Alex Rivera"
        assert "https://www.youtube.com/@SkylineRealEstatePodcast" in li_posts[0]["external_urls"]

        # Access gate detection (Login wall)
        await bc.open_url(f"{local_site}/authwall", screenshot_label="test_gate")
        gate_text = await bc.read_visible_text()
        assert "Sign in" in gate_text
    finally:
        await bc.stop()


def test_google_results_parser():
    sample_google = """
    <html><body>
      <a href="/url?q=https://www.youtube.com/@CrePodcast&sa=U"><h3>CRE Podcast - YouTube</h3></a>
      <a href="https://example.com/cre-podcast"><h3>CRE Podcast Official</h3></a>
    </body></html>
    """
    parsed = parse_google_results_from_html(sample_google)
    assert len(parsed) == 2
    assert parsed[0]["url"] == "https://www.youtube.com/@CrePodcast"

