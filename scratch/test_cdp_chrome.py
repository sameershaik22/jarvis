import subprocess
import time
import urllib.request
from playwright.sync_api import sync_playwright

def test_cdp():
    chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    user_data = r"C:\Users\samee\OneDrive\Desktop\javis\data\browser_profile"
    port = 9222
    url = "https://www.linkedin.com/login"

    # Launch Chrome using Windows 'start' via cmd so it is handed off to the interactive desktop shell!
    launch_cmd = f'start "" "{chrome_exe}" --remote-debugging-port={port} --user-data-dir="{user_data}" --no-first-run --no-default-browser-check "{url}"'
    print("Launching via cmd /c start:", launch_cmd)
    subprocess.run(["cmd.exe", "/c", launch_cmd], shell=True)

    # Wait for CDP endpoint to respond
    cdp_url = f"http://127.0.0.1:{port}/json/version"
    connected = False
    for _ in range(10):
        time.sleep(1)
        try:
            with urllib.request.urlopen(cdp_url, timeout=2) as resp:
                print("CDP Response:", resp.read().decode("utf-8")[:100])
                connected = True
                break
        except Exception as e:
            print("Waiting for CDP...", e)

    if not connected:
        print("Failed to reach CDP port 9222")
        return

    # Now connect Playwright over CDP!
    print("Connecting Playwright over CDP...")
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    print("Connected! Contexts:", len(browser.contexts))
    context = browser.contexts[0]
    pages = context.pages
    print("Pages open:", len(pages))
    page = pages[0] if pages else context.new_page()
    print("Page URL:", page.url, "Title:", page.title())
    
    # Take screenshot
    shot = "scratch/cdp_test.png"
    page.screenshot(path=shot)
    print("Screenshot saved to:", shot)

if __name__ == "__main__":
    test_cdp()

