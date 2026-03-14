import socket
import subprocess
import json
import argparse
import re

DANGEROUS_PATTERNS = [
    r"\brm\s+-rf\s+/\b",
    r"\bmkfs\b",
    r"\bdd\s+.*of=/dev/",
    r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;:",  # fork bomb
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bhalt\b",
    r"\binit\s+0\b",
]

COMMAND_TIMEOUT = 600  # 10 minute default timeout


def validate_command(command: str) -> bool:
    """Return True if command passes basic safety checks."""
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            return False
    return True


parser = argparse.ArgumentParser()
parser.add_argument("--workplace", type=str, default="/workplace")
parser.add_argument("--port", type=int, default=8000)
parser.add_argument("--timeout", type=int, default=COMMAND_TIMEOUT)
args = parser.parse_args()

if __name__ == "__main__":
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("0.0.0.0", args.port))
    server.listen(1)

    print(f"[INFO] Listening on port {args.port}...")

    def receive_all(conn, buffer_size=4096):
        data = b""
        while True:
            part = conn.recv(buffer_size)
            data += part
            if len(part) < buffer_size:
                break
        return data.decode()

    while True:
        conn, addr = server.accept()
        print(f"[INFO] Connection from {addr}")
        while True:
            command = receive_all(conn)
            if not command:
                break

            # Validate command before execution
            if not validate_command(command):
                error_response = {
                    "type": "final",
                    "status": -1,
                    "result": f"Command rejected by safety filter: {command[:100]}",
                }
                conn.send(json.dumps(error_response).encode() + b"\n")
                continue

            # Execute the command with timeout
            try:
                modified_command = ["/bin/bash", "-c", command]
                process = subprocess.Popen(
                    modified_command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=args.workplace,
                )
                output = ""
                try:
                    while True:
                        line = process.stdout.readline()
                        if not line and process.poll() is not None:
                            break
                        output += line
                        chunk_response = {"type": "chunk", "data": line}
                        conn.send(
                            json.dumps(chunk_response).encode() + b"\n"
                        )

                    process.wait(timeout=args.timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    output += "\n[TIMEOUT] Command exceeded time limit.\n"

                final_response = {
                    "type": "final",
                    "status": process.poll(),
                    "result": output,
                }
                conn.send(json.dumps(final_response).encode() + b"\n")
            except Exception as e:
                error_response = {
                    "type": "final",
                    "status": -1,
                    "result": f"Error running command: {str(e)}",
                }
                conn.send(json.dumps(error_response).encode() + b"\n")
        conn.close()
