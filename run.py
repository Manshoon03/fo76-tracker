import threading
import sys
import os
import socket

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app

PORT = int(os.getenv('FO76_PORT', 5000))
HOST = os.getenv('FO76_HOST', '0.0.0.0')

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
    # Only attempt on machines with a display (skip on headless Pi)
    if os.getenv('DISPLAY') or sys.platform == 'win32' or sys.platform == 'darwin':
        import webbrowser
        webbrowser.open(f'http://127.0.0.1:{PORT}')

if __name__ == '__main__':
    local_ip = get_local_ip()
    print("=" * 50)
    print("  FO76 TRACKER - Starting server...")
    print(f"  This PC:    http://127.0.0.1:{PORT}")
    print(f"  Network:    http://{local_ip}:{PORT}")
    print("  Press Ctrl+C to stop")
    print("=" * 50)

    threading.Timer(1.2, open_browser).start()

    try:
        from waitress import serve
        print("  Server:     waitress (production)")
        print("=" * 50)
        serve(app, host=HOST, port=PORT, threads=4)
    except ImportError:
        print("  Server:     werkzeug dev (install waitress for production)")
        print("=" * 50)
        app.run(debug=False, host=HOST, port=PORT, threaded=True)
