"""Download accelerator over HTTP.

Usage:
    python downloader.py NumberOfThreads ObjectURI localFilename
    python downloader.py 4 http://www.textfiles.com/art/cowz.txt out.txt

Flow:
    1. Send a HEAD request to learn the object's size (Content-Length).
    2. Pre-allocate a local file of that size.
    3. Split the object into byte ranges, one per thread.
    4. Each thread sends a GET with a Range header and writes the
       response body directly to its own position in the file.
"""

import math
import socket
import sys
import threading
from urllib.parse import urlparse

MIN_THREADS = 1
MAX_THREADS = 16
RECV_SIZE = 4096
TIMEOUT_SECONDS = 30
HEADER_END = b"\r\n\r\n"


# ---------------------------------------------------------------------------
# Small HTTP helpers
# ---------------------------------------------------------------------------

def parse_uri(uri):
    """Split a URI into (host, port, path). Path includes any query string."""
    parsed = urlparse(uri)
    if parsed.scheme != "http" or not parsed.hostname:
        raise ValueError("ObjectURI must look like http://host/path")

    port = parsed.port or 80
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    return parsed.hostname, port, path


def build_request(method, host, path, byte_range=None):
    """Build a raw HTTP/1.0 request. byte_range is an optional (start, end)."""
    lines = [f"{method} {path} HTTP/1.0", f"Host: {host}"]
    if byte_range is not None:
        start, end = byte_range
        lines.append(f"Range: bytes={start}-{end}")
    lines.append("Connection: close")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")


def parse_response_head(raw_head):
    """Return (status_code, headers) from the raw bytes before the blank line.

    Header names are lowercased so lookups are case-insensitive.
    """
    lines = raw_head.decode("iso-8859-1").split("\r\n")
    status_code = int(lines[0].split()[1])

    headers = {}
    for line in lines[1:]:
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()
    return status_code, headers


def open_connection(host, port, request):
    """Connect to the server, send the request, and return the socket."""
    sock = socket.create_connection((host, port), timeout=TIMEOUT_SECONDS)
    sock.sendall(request)
    return sock


def read_response_head(sock):
    """Read from sock until the end of the headers.

    Returns (raw_head, leftover), where leftover is any body bytes that
    arrived in the same recv() as the end of the headers.
    """
    buffer = b""
    while HEADER_END not in buffer:
        chunk = sock.recv(RECV_SIZE)
        if not chunk:
            raise ConnectionError("Connection closed before headers finished")
        buffer += chunk

    raw_head, _, leftover = buffer.partition(HEADER_END)
    return raw_head, leftover


# ---------------------------------------------------------------------------
# Download logic
# ---------------------------------------------------------------------------

def get_object_size(host, port, path):
    """Issue a HEAD request and return the object's Content-Length."""
    request = build_request("HEAD", host, path)
    with open_connection(host, port, request) as sock:
        raw_head, _ = read_response_head(sock)

    status, headers = parse_response_head(raw_head)
    if status != 200:
        raise RuntimeError(f"HEAD request failed with status {status}")
    if "content-length" not in headers:
        raise RuntimeError("Server did not send a Content-Length header")
    return int(headers["content-length"])


def split_into_ranges(size, num_threads):
    """Divide [0, size) into inclusive (start, end) byte ranges.

    Each range is ceil(size / num_threads) bytes, except the last one,
    which gets whatever remains. Empty ranges are dropped.
    """
    chunk = math.ceil(size / num_threads)
    ranges = []
    for i in range(num_threads):
        start = i * chunk
        if start >= size:
            break
        end = min(start + chunk - 1, size - 1)
        ranges.append((start, end))
    return ranges


def download_range(host, port, path, byte_range, local_filename, errors):
    """Worker: download one byte range and write it into the local file.

    Any failure is appended to `errors` so the main thread can report it.
    """
    start, end = byte_range
    expected_bytes = end - start + 1

    try:
        request = build_request("GET", host, path, byte_range)
        with open_connection(host, port, request) as sock:
            raw_head, body_start = read_response_head(sock)
            status, _ = parse_response_head(raw_head)
            if status != 206:
                raise RuntimeError(f"expected 206 Partial Content, got {status}")

            # Each thread uses its own file handle, so seeks don't collide.
            with open(local_filename, "r+b") as out_file:
                out_file.seek(start)
                written = 0

                data = body_start
                while data:
                    out_file.write(data)
                    written += len(data)
                    data = sock.recv(RECV_SIZE)

        if written != expected_bytes:
            raise RuntimeError(f"got {written} bytes, expected {expected_bytes}")

    except (OSError, RuntimeError, ConnectionError) as error:
        errors.append(f"bytes {start}-{end}: {error}")


def preallocate_file(filename, size):
    """Create (or overwrite) a file that is exactly `size` bytes long."""
    with open(filename, "wb") as out_file:
        out_file.truncate(size)


def download(num_threads, uri, local_filename):
    """Run the full download. Returns True on success."""
    host, port, path = parse_uri(uri)

    size = get_object_size(host, port, path)
    print(f"Object size: {size} bytes")

    preallocate_file(local_filename, size)
    if size == 0:
        return True

    ranges = split_into_ranges(size, num_threads)
    errors = []
    threads = []

    for byte_range in ranges:
        thread = threading.Thread(
            target=download_range,
            args=(host, port, path, byte_range, local_filename, errors),
        )
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

    for message in errors:
        print(f"Error: {message}", file=sys.stderr)
    return not errors


# ---------------------------------------------------------------------------
# Command-line entry point
# ---------------------------------------------------------------------------

def parse_arguments(argv):
    """Validate command-line arguments and return (num_threads, uri, filename)."""
    if len(argv) != 4:
        sys.exit("Usage: python downloader.py NumberOfThreads ObjectURI localFilename")

    try:
        num_threads = int(argv[1])
    except ValueError:
        sys.exit("NumberOfThreads must be an integer")

    if not MIN_THREADS <= num_threads <= MAX_THREADS:
        sys.exit(f"NumberOfThreads must be between {MIN_THREADS} and {MAX_THREADS}")

    return num_threads, argv[2], argv[3]


def main():
    num_threads, uri, local_filename = parse_arguments(sys.argv)

    try:
        success = download(num_threads, uri, local_filename)
    except (ValueError, RuntimeError, OSError) as error:
        sys.exit(f"Error: {error}")

    if not success:
        sys.exit("Download failed")
    print(f"Saved to {local_filename}")


if __name__ == "__main__":
    main()
