import subprocess
import os

def launch_chrome():
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    user_data_dir = r"C:\Users\samee\OneDrive\Desktop\javis\data\browser_profile"
    url = "https://www.linkedin.com/login"

    si = subprocess.STARTUPINFO()
    si.lpDesktop = r"WinSta0\Default"
    
    cmd = [
        chrome_path,
        f"--user-data-dir={user_data_dir}",
        "--remote-debugging-port=9222",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized",
        "--window-name=YoursBuddy AI Browser",
        url
    ]
    
    proc = subprocess.Popen(cmd, startupinfo=si)
    print("Launched Chrome with PID:", proc.pid)

if __name__ == "__main__":
    launch_chrome()

