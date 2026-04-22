import webbrowser
import threading
import sys
import os
import socket

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

def open_browser():
    webbrowser.open('http://127.0.0.1:5000')

if __name__ == '__main__':
    local_ip = get_local_ip()
    print("=" * 50)
    print("  FO76 TRACKER - Starting server...")
    print(f"  This PC:    http://127.0.0.1:5000")
    print(f"  Network:    http://{local_ip}:5000")
    print("  Press Ctrl+C to stop")
    print("=" * 50)
    threading.Timer(1.2, open_browser).start()
    app.run(debug=False, host='0.0.0.0', port=5000)
