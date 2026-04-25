import socket
import threading
import os
import datetime
import email.utils
import mimetypes
from urllib.parse import unquote_plus

# ====================== CONFIGURATION ======================
HOST = '127.0.0.1'
PORT = 8080

# Project root (WEB-SERVER/) is one level above the src/ directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # WEB-SERVER/
ROOT_DIR = os.path.join(BASE_DIR, 'test_files')
LOG_FILE = os.path.join(BASE_DIR, 'server.log')
# ===========================================================

log_lock = threading.Lock()

def log_request(client_ip: str, requested_file: str, status_code: int, status_msg: str):
    """Append one line to the log file for each request"""
    with log_lock:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"{client_ip} {timestamp} {requested_file} {status_code} {status_msg}\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
        print(f"[LOG] {entry.strip()}")

def get_content_type(file_path: str) -> str:
    mime, _ = mimetypes.guess_type(file_path)
    return mime or "application/octet-stream"

def get_last_modified(file_path: str) -> str:
    mtime = os.path.getmtime(file_path)
    return email.utils.formatdate(mtime, usegmt=True)

def parse_if_modified_since(date_str: str):
    try:
        return email.utils.parsedate_to_datetime(date_str).timestamp()
    except:
        return None

def send_response(conn, status_code: int, status_msg: str, headers=None, body=b"",
                  client_ip="", requested_file=""):
    """Construct and send an HTTP response, then log it."""
    if headers is None:
        headers = {}

    # Build status line
    response_line = f"HTTP/1.1 {status_code} {status_msg}\r\n"
    # Default headers
    headers.setdefault("Date", email.utils.formatdate(usegmt=True))
    headers.setdefault("Server", "Comp2322-MultiThread-WebServer/1.0")
    # Connection header is set by the caller, NOT defaulted here

    header_lines = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    full_response = response_line + header_lines + "\r\n"

    conn.sendall(full_response.encode("utf-8"))
    if body:
        conn.sendall(body)

    log_request(client_ip, requested_file, status_code, status_msg)

def handle_client(conn, addr):
    client_ip = addr[0]
    print(f"[INFO] Connected from {client_ip}")

    try:
        while True:
            # Simple read – assumes request fits in 4096 bytes (OK for this project)
            data = conn.recv(4096)
            if not data:
                break

            request_str = data.decode("utf-8", errors="ignore")
            lines = request_str.split("\r\n")
            if not lines:
                break

            request_line = lines[0].strip()
            parts = request_line.split(maxsplit=2)

            # 400 Bad Request – malformed request line
            if len(parts) < 3:
                send_response(conn, 400, "Bad Request",
                              {"Content-Type": "text/html", "Connection": "close"},
                              b"<html><body><h1>400 Bad Request</h1></body></html>",
                              client_ip, "N/A")
                break

            method, url, version = parts
            method = method.upper()

            # Only GET and HEAD are allowed → 400 otherwise
            if method not in ("GET", "HEAD"):
                send_response(conn, 400, "Bad Request",
                              {"Content-Type": "text/html", "Connection": "close"},
                              b"<html><body><h1>400 Bad Request</h1></body></html>",
                              client_ip, url.split("?")[0])
                break

            if version not in ("HTTP/1.0", "HTTP/1.1"):
                send_response(conn, 400, "Bad Request",
                              {"Content-Type": "text/html", "Connection": "close"},
                              b"<html><body><h1>400 Bad Request</h1></body></html>",
                              client_ip, url.split("?")[0])
                break

            # Parse headers
            headers = {}
            for line in lines[1:]:
                if not line.strip():
                    break
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip().lower()] = v.strip()

            # Clean the file path (remove query string and URL-decode)
            file_path = unquote_plus(url.split("?")[0])
            if file_path in ("/", ""):
                file_path = "/index.html"
            requested_file = file_path.lstrip("/")

            # Security: resolve the absolute path and prevent traversal
            abs_root = os.path.abspath(ROOT_DIR)
            full_path = os.path.normpath(os.path.join(abs_root, requested_file))

            # 403 Forbidden – any attempt to break out of ROOT_DIR
            if (not full_path.startswith(abs_root) or
                ".." in requested_file or
                requested_file.startswith('..')):
                send_response(conn, 403, "Forbidden",
                              {"Content-Type": "text/html", "Connection": "close"},
                              b"<html><body><h1>403 Forbidden</h1><p>Access denied.</p></body></html>",
                              client_ip, requested_file)
                break   # always close after a 403

            # 404 Not Found
            if not os.path.exists(full_path) or not os.path.isfile(full_path):
                send_response(conn, 404, "File Not Found",
                              {"Content-Type": "text/html",
                               "Connection": _get_connection_header(version, headers)},
                              b"<html><body><h1>404 File Not Found</h1></body></html>",
                              client_ip, requested_file)
                if _should_close(version, headers):
                    break
                continue

            # File metadata
            last_modified_str = get_last_modified(full_path)
            content_type = get_content_type(full_path)
            file_size = os.path.getsize(full_path)

            # 304 Not Modified (conditional GET / HEAD)
            if "if-modified-since" in headers and method in ("GET", "HEAD"):
                if_ts = parse_if_modified_since(headers["if-modified-since"])
                if if_ts is not None and os.path.getmtime(full_path) <= if_ts + 1:  # 1 sec tolerance
                    resp_headers = {
                        "Last-Modified": last_modified_str,
                        "Content-Type": content_type,
                        "Content-Length": "0",
                        "Connection": _get_connection_header(version, headers)
                    }
                    send_response(conn, 304, "Not Modified", resp_headers, b"",
                                  client_ip, requested_file)
                    if _should_close(version, headers):
                        break
                    continue

            # Prepare body (only for GET)
            body = b""
            if method == "GET":
                with open(full_path, "rb") as f:
                    body = f.read()

            # Build response headers
            resp_headers = {
                "Last-Modified": last_modified_str,
                "Content-Type": content_type,
                "Content-Length": str(file_size),   # actual size, even for HEAD
                "Connection": _get_connection_header(version, headers)
            }

            send_response(conn, 200, "OK", resp_headers, body, client_ip, requested_file)

            # Decide whether to keep the connection alive
            if _should_close(version, headers):
                break

    except Exception as e:
        print(f"[ERROR] {client_ip}: {e}")
    finally:
        conn.close()
        print(f"[INFO] Connection closed for {client_ip}")

def _should_close(version: str, headers: dict) -> bool:
    """Return True if the connection should be closed after this response."""
    conn_header = headers.get("connection", "").lower()
    if version == "HTTP/1.0":
        return conn_header != "keep-alive"
    else:  # HTTP/1.1
        return conn_header == "close"

def _get_connection_header(version: str, headers: dict) -> str:
    """Return the value for the Connection response header."""
    return "close" if _should_close(version, headers) else "keep-alive"

def main():
    if not os.path.exists(ROOT_DIR):
        print(f"[ERROR] test_files folder not found at:\n   {ROOT_DIR}")
        return

    # Ensure log file exists
    if not os.path.exists(LOG_FILE):
        open(LOG_FILE, "a").close()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(10)

    print(f"\n Multi-threaded Web Server running at http://{HOST}:{PORT}")
    print(f" Serving files from: {ROOT_DIR}")
    print(" Press Ctrl+C to stop\n")

    try:
        while True:
            conn, addr = server.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("\n Shutting down server...")
    finally:
        server.close()

if __name__ == "__main__":
    main()