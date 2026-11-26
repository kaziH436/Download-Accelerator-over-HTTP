# Usage: python downloader.py NumberOfThreads ObjectURI localFilename
# Example: python downloader.py 4 http://www.textfiles.com/art/cowz.txt out.txt
import sys
from socket import *
from threading import Thread

BUFFER_SIZE = 4096
MIN_THREADS = 1
MAX_THREADS = 16
HEADER_END = b"\r\n\r\n"


def parseUri(uri):
    """Split http://host[:port]/path into (host, port, path)."""
    if not uri.startswith("http://"):
        raise ValueError("ObjectURI must start with http://")

    rest = uri[len("http://"):]
    hostPart, slash, path = rest.partition("/")
    path = "/" + path

    host, colon, port = hostPart.partition(":")
    port = int(port) if colon else 80

    if not host:
        raise ValueError("ObjectURI has no host name")
    return host, port, path


def connectAndSend(server_addr, request):
    """Connect to the server, send the request and return the socket."""
    clientSock = socket(AF_INET, SOCK_STREAM)
    try:
        clientSock.connect(server_addr)
        clientSock.sendall(request.encode())
    except Exception:
        clientSock.close()
        raise
    return clientSock


def readHeaders(clientSock):
    """Read until the blank line that ends the headers.

    Returns (headers as text, any body bytes already received).
    """
    data = b""
    while HEADER_END not in data:
        chunk = clientSock.recv(BUFFER_SIZE)
        if not chunk:
            raise Exception("connection closed before the headers ended")
        data += chunk

    head, _, body = data.partition(HEADER_END)
    return head.decode(), body


def getStatusCode(head):
    # First line looks like: HTTP/1.1 206 Partial Content
    return int(head.split("\r\n")[0].split()[1])


def getContentLength(head):
    for line in head.split("\r\n"):
        if line.lower().startswith("content-length:"):
            return int(line.split(":", 1)[1].strip())
    raise Exception("no Content-Length header in the reply")


def getObjectSize(server_addr, host, path):
    # Send HEAD request
    request = (f"HEAD {path} HTTP/1.0\r\n"
               f"Host: {host}\r\n"
               f"Connection: close\r\n"
               f"\r\n")
    clientSock = connectAndSend(server_addr, request)
    try:
        head, _ = readHeaders(clientSock)
    finally:
        clientSock.close()

    if getStatusCode(head) != 200:
        raise Exception("HEAD request failed:\n" + head)
    return getContentLength(head)


def downloadRange(server_addr, host, path, start, end, filename, errors):
    """Thread function: download bytes start..end and write them to the file."""
    try:
        # Send GET request with a Range header
        request = (f"GET {path} HTTP/1.0\r\n"
                   f"Host: {host}\r\n"
                   f"Range: bytes={start}-{end}\r\n"
                   f"Connection: close\r\n"
                   f"\r\n")
        clientSock = connectAndSend(server_addr, request)

        try:
            head, data = readHeaders(clientSock)
            if getStatusCode(head) != 206:
                raise Exception("expected 206 Partial Content, got:\n" + head)

            # Each thread opens its own handle so the seek positions
            # of different threads do not interfere with each other
            received = 0
            with open(filename, "r+b") as f:
                f.seek(start)
                while data:
                    f.write(data)
                    received += len(data)
                    data = clientSock.recv(BUFFER_SIZE)
        finally:
            clientSock.close()

        expected = end - start + 1
        if received != expected:
            raise Exception(f"received {received} bytes, expected {expected}")

    except Exception as e:
        errors.append(f"bytes {start}-{end}: {e}")


def main():
    # Check the command line arguments
    if len(sys.argv) != 4:
        print("Usage: python downloader.py NumberOfThreads ObjectURI localFilename")
        sys.exit(1)

    try:
        numThreads = int(sys.argv[1])
    except ValueError:
        print("NumberOfThreads must be an integer")
        sys.exit(1)

    if numThreads < MIN_THREADS or numThreads > MAX_THREADS:
        print(f"NumberOfThreads must be between {MIN_THREADS} and {MAX_THREADS}")
        sys.exit(1)

    uri = sys.argv[2]
    filename = sys.argv[3]

    try:
        host, port, path = parseUri(uri)
    except ValueError as e:
        print("Bad ObjectURI:", e)
        sys.exit(1)

    server_addr = (host, port)

    # Issue a HEAD request to learn the size of the object
    try:
        size = getObjectSize(server_addr, host, path)
    except Exception as e:
        print("HEAD failed:", e)
        sys.exit(1)
    print(f"Object size: {size} bytes")

    # Allocate a local file with "size" bytes in it
    with open(filename, "wb") as f:
        f.truncate(size)

    # Each thread gets ceil(size / numThreads) bytes; the last one gets the rest
    chunk = (size + numThreads - 1) // numThreads
    errors = []
    threads = []

    for i in range(numThreads):
        start = i * chunk
        if start >= size:
            break  # more threads than bytes: nothing left to assign
        end = min(start + chunk - 1, size - 1)

        t = Thread(target=downloadRange,
                   args=(server_addr, host, path, start, end, filename, errors))
        t.start()
        threads.append(t)

    # Wait for all worker threads to finish
    for t in threads:
        t.join()

    if errors:
        for message in errors:
            print("Error:", message)
        print("Download failed.")
        sys.exit(1)

    print(f"Download complete: {filename}")


if __name__ == "__main__":
    main()