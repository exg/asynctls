#!/usr/bin/env python

import argparse
import os
import socket
import subprocess
import sys
import time


def wait_for_server(pid_file, timeout):
    timeout *= 10
    while timeout > 0:
        time.sleep(0.1)
        if os.path.exists(pid_file):
            return True
        timeout -= 1
    return False


# This script expects to be executed so that pwd is the root of the repo


def main():
    args = parse_arguments()

    certificate_folder = os.path.join("stage", args.arch, "build", "test")
    pem_file_path = os.path.join(certificate_folder, "test.pem")
    key_file_path = os.path.join(certificate_folder, "test.key")
    pid_file_path = os.path.join(certificate_folder, "pid")

    print(repr(args.certificate_subdomain))

    try:
        generate_certificate(
            args.certificate_subdomain, pem_file_path, key_file_path
        )
    except subprocess.CalledProcessError:
        print("Failed to create certificates")
        return False

    hostname = args.subhostname + ".localhost"
    port = 12345

    if os.path.exists(pid_file_path):
        os.unlink(pid_file_path)
    server = start_server(args.arch, pem_file_path, key_file_path, pid_file_path)
    if not wait_for_server(pid_file_path, 5):
        server.kill()
        server.wait()
        return False
    if args.client == "tcp":
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1)
            client_returncode = 0
        except Exception:
            client_returncode = 1
        client_output = ""
    else:
        if args.client == "openssl":
            client = start_openssl_client(pem_file_path, hostname, port)
        else:
            client = start_client(args.arch, pem_file_path, hostname, port)
        time_for_client_to_finish = 5
        verify_process_finishes(client, time_for_client_to_finish)
        client_output, _ = client.communicate()
        client_returncode = args.client_returncode

    time_for_server_to_finish = 1
    verify_process_finishes(server, time_for_server_to_finish)
    server_output, _ = server.communicate()

    print("Server output:")
    print(server_output)
    print("")
    print("Client output:")
    print(client_output)
    print("")

    server_successful = server.returncode == args.server_returncode
    client_successful = client_returncode == args.client_returncode

    return server_successful and client_successful


def verify_process_finishes(p, initial_wait_time):
    def wait_for_process_to_end(seconds):
        current_time = time.time()
        end_time = current_time + seconds
        while time.time() < end_time and p.poll() is None:
            time.sleep(0.1)

        return p.poll() is not None

    if wait_for_process_to_end(initial_wait_time):
        return
    p.kill()
    p.wait()


def start_server(arch, pem_file, key_file, pid_file):
    return subprocess.Popen(
        [
            os.path.join("stage", arch, "build", "test", "tlstestserver"),
            pem_file,
            key_file,
            pid_file,
        ],
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
    )


def start_client(arch, pem_file, hostname, port):
    return subprocess.Popen(
        [
            "stage/{}/build/test/tlstest".format(arch),
            "--file",
            pem_file,
            "127.0.0.1",
            str(port),
            hostname,
        ],
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
    )


def start_openssl_client(pem_file, hostname, port):
    return subprocess.Popen(
        [
            "openssl",
            "s_client",
            "-quiet",
            "-connect",
            "127.0.0.1:{}".format(port),
            "-CAfile",
            pem_file,
            "-verify_hostname",
            hostname,
            "-verify_return_error",
        ],
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
    )


def parse_arguments():
    parser = argparse.ArgumentParser(description="Run communication test")
    parser.add_argument(
        "--client", choices=("tcp", "openssl", "tlstest"), default="tlstest"
    ),
    parser.add_argument("arch")
    parser.add_argument(
        "subhostname", help="subdomain under .localhost to test against"
    )
    parser.add_argument(
        "certificate_subdomain",
        help="subdomain under .localhost used for certificate."
        + " Can contain wildcards.",
    )
    parser.add_argument(
        "client_returncode",
        type=int,
        default=0,
        help="Expected client return code",
    )
    parser.add_argument(
        "server_returncode",
        type=int,
        default=0,
        help="Expected server return code",
    )

    args = parser.parse_args()

    return args


def generate_certificate(certificate_subdomain, pem_file, key_file):
    domain_name = "/CN=" + certificate_subdomain + ".localhost"
    subprocess.check_call(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:4096",
            "-sha256",
            "-nodes",
            "-keyout",
            key_file,
            "-out",
            pem_file,
            "-subj",
            domain_name,
            "-days",
            str(3650),
        ]
    )


if __name__ == "__main__":
    test_passed = main()
    print("Test " + ("passed" if test_passed else "failed"))
    return_code = 0 if test_passed else 1
    sys.exit(return_code)
