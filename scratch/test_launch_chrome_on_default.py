import ctypes
import os
import time

user32 = ctypes.windll.user32

def test_launch():
    # 1. Switch calling thread to the real interactive user desktop
    h_default = user32.OpenDesktopW("Default", 0, False, 0x01FF)
    print("OpenDesktop handle:", h_default)
    if h_default:
        res = user32.SetThreadDesktop(h_default)
        print("SetThreadDesktop result:", res)

    # 2. Launch Chrome via Playwright
    import sys
    sys.path.insert(0, "backend")
    from app.services.browser_controller import BrowserController
    bc = BrowserController()
    info = bc._start_sync(headless=False)
    print("Browser started:", info)
    
    # 3. Open LinkedIn
    res = bc._open_url_sync("https://www.linkedin.com/login")
    print("Navigated:", res.url, res.title)

    # 4. Check if a window with LinkedIn or Chrome now appears on Default desktop
    chrome_found = False
    def cb(hwnd, extra):
        nonlocal chrome_found
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if "linkedin" in title.lower() or "yoursbuddy" in title.lower():
            print("FOUND WINDOW ON DEFAULT DESKTOP:", title, "HWND:", hwnd)
            chrome_found = True
        return True

    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(CB(cb), 0)
    print("Chrome found on Default desktop:", chrome_found)
    
    time.sleep(3)
    bc._stop_sync()

if __name__ == "__main__":
    test_launch()

