"""Port probe helper for start.bat — no dependencies outside stdlib."""
import socket
import sys


def check_port(host: str, port: int) -> bool:
    """Return True if something is already listening on host:port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        s.close()
        return False


def find_free_port(host: str, start: int, end: int) -> int:
    """Return the first free port in [start, end], or 0 if none."""
    for port in range(start, end + 1):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((host, port))
            s.close()
            return port
        except OSError:
            try:
                s.close()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "check":
        host = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
        port = int(sys.argv[3]) if len(sys.argv) > 3 else 8080
        sys.exit(0 if check_port(host, port) else 1)
    elif cmd == "find":
        host = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
        start = int(sys.argv[3]) if len(sys.argv) > 3 else 8501
        end = int(sys.argv[4]) if len(sys.argv) > 4 else 8599
        port = find_free_port(host, start, end)
        if port:
            print(port)
            sys.exit(0)
        sys.exit(1)
    else:
        print(f"Usage: {sys.argv[0]} check|find [host] [port]", file=sys.stderr)
        sys.exit(2)
