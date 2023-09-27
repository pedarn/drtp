import argparse
import ipaddress
import os
import sys


def check_port(val: str) -> int:
    """
    Checks if the port is a valid port number between 1024 and 65535
    :param val: port number specified by user
    :return: port number as an integer
    """
    try:
        val = int(val)
    except ValueError:
        raise argparse.ArgumentTypeError("expected integer but got string")
    if val < 1024 or val > 65535:
        raise argparse.ArgumentTypeError("expected an integer between 1024 and 65535")
    return val


def check_ip(val: str):
    """
    Checks if the IP address is valid
    :param val: IP address specified by user
    :return: IP address as a string
    """
    try:
        ipaddress.ip_address(val)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a valid IP address, got {val}")
    return val


def check_file(val: str):
    """
    Checks if the file exists on the system
    :param val: filename specified by user
    :return: filename as a string
    """
    if not os.path.isfile(val):
        raise argparse.ArgumentTypeError(f"expected a valid file, got {val}")
    return val


def parse_args():
    """
    Parses the arguments given by the user, transforms and returns them.
    Throws an error if the arguments are invalid.
    :return: parsed arguments given by the user transformed into the correct type
    """
    parser = argparse.ArgumentParser(description="positional arguments", epilog="end of help",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("-s", "--server", action="store_true", help="Run in server mode")
    parser.add_argument("-c", "--client", action="store_true", help="Run in client mode")
    parser.add_argument("-i", "--ip", type=check_ip, default="127.0.0.1", help="The IP address to bind to")
    parser.add_argument("-p", "--port", type=check_port, default=8088, help="The port to listen on")
    parser.add_argument("-r", "--reliable_method", choices=("saw", "gbn", "sr"), default="saw",
                        help="The reliability functions to use, Stop And Wait, Go Back N or Selective Repeat")
    parser.add_argument("-f", "--file", type=check_file, help="The file to send")
    parser.add_argument("-t", "--test_case", choices=("skip_ack", "skip_seq"), help="The test case to run")
    parser.add_argument("-w", "--window_size", type=int, default=5, help="The window size to use")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose mode")

    # Runs the parser and places the extracted data
    args = parser.parse_args()

    # Check if the user has specified server or client mode
    # Equality means that the user har either specified both or neither, which is invalid
    if args.server == args.client:
        parser.error("You must run either in server or client mode")

    # Check if the arguments are valid for client mode
    if args.client:
        if not args.file:
            parser.error("You must specify a file to send in client mode")

        if args.test_case == "skip_ack":
            parser.error("You cannot run skip_ack in client mode")

    # Check if the arguments are valid for server mode
    if args.server:
        if args.test_case == "skip_seq":
            parser.error("You cannot run skip_seq in server mode")

        if args.file:
            parser.error("You cannot specify a file to send in server mode")

        if args.window_size != 5:
            parser.error("You cannot specify a window size in server mode")

    return args
