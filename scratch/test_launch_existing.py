import urllib.request
import subprocess
import time

def test():
    print("Testing ensure_chrome_debug...")
    # Check if 9222 is open
    try:
        with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=1) as r:
            print("Port 9222 is ALREADY open!")
            return True
    except Exception:
        pass

    print("Port 9222 not open. Launching Chrome with --remote-debugging-port=9222...")
    cmd = (
        'powershell -Command "'
        'Get-Process chrome -ErrorAction SilentlyContinue | ForEach-Object { $_.CloseMainWindow() }; '
        'Start-Sleep -Seconds 1; '
        'Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue; '
        'Start-Sleep -Seconds 1; '
        'Start-Process \'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe\' -ArgumentList \'--remote-debugging-port=9222\', \'--restore-last-session\''
        '"'
    )
    subprocess.run(cmd, shell=True)

    for i in range(10):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=1) as r:
                print(f"Port 9222 opened successfully! (attempt {i+1})")
                return True
        except Exception:
            pass

    print("Failed to open port 9222.")
    return False

if __name__ == "__main__":
    test()

