import os
import sys
import time
from random import randint
from socket import *
from struct import *
from typing import NamedTuple, Union, Tuple, Generator, BinaryIO, List, Dict, Optional

from arg_parser import parse_args

""" CONSTANTS """

# I integer (unsigned long) = 4bytes and H (unsigned short integer 2 bytes)
HEADER_FORMAT = '!IIHH'
HEADER_SIZE = 12
DATA_SIZE = 1460
PACKAGE_SIZE = HEADER_SIZE + DATA_SIZE
SEP = "<SEPARATOR>"
METHOD_NAMES = {"saw": "stop and wait", "gbn": "go back N", "sr": "selective repeat"}

# Types
Flags = NamedTuple('Flags', syn=bool, ack=bool, fin=bool)
Header = NamedTuple('Header', seq=int, ack=int, flags=int, win=int)

""" SERVER """


class Server:
    last_valid_seq: int

    def __init__(self):
        """
        Initialize server using arguments
        """
        # Connection
        self.server_socket = socket(AF_INET, SOCK_DGRAM)
        self.client_address = None

        # File information
        self.file_name = None
        self.file_buffer = b""

        # Sequence number
        self._current_seq = None

        # Test case
        self.test_can_run = False
        self.skip_ack_generator = yield_true_once()

        # Bind to address
        try:
            if args.verbose:
                print(f'Binding to {args.ip}:{args.port}')
            self.server_socket.bind((args.ip, args.port))
        except OSError as e:
            sys.exit(f'Failed to bind to {args.ip}:{args.port}, {repr(e)}')

    def get_next_seq(self) -> int:
        """
        Get next sequence number by incrementing the current sequence number
        :return: next sequence number
        """
        if self._current_seq is None:
            self._current_seq = 0
            return self._current_seq
        else:
            self._current_seq += 1
            return self._current_seq

    def start_server(self) -> None:
        """
        Perform handshake and start receiving data from the client using the specified method.
        After receiving the file, write it to disk.
        """
        try:
            # Handshake
            self.handshake()

            # Receive file name and method
            try:
                package, _ = self.server_socket.recvfrom(PACKAGE_SIZE)
                seq, ack, flags, win = parse_header(package[:12])
                self.last_valid_seq = seq
                self.send_ack(seq)
            except Exception:
                self.server_socket.close()
                sys.exit("Did not receive file name and method")

            # Set file name and method
            data = package[12:].decode()
            file_name, client_method = data.split(SEP)
            self.file_name = file_name

            # Check method
            method = args.reliable_method
            if client_method != method:
                raise Exception("Client and server must use the same method")

            print_in_block(f"Receiving file {file_name} using {METHOD_NAMES.get(method)} method")

            self.test_can_run = True
            start_time = time.time()
            # Receive file
            if method == "saw":
                # Using stop and wait
                self.stop_and_wait()
            elif method == "gbn":
                # Using go back N
                self.go_back_n()
            elif method == "sr":
                # Using selective repeat
                self.selective_repeat()
            end_time = time.time()

            print_in_block("Finished receiving file")

            # Inject "recv" in file name
            name_recv_type = ".".join(self.file_name.split(".")[:-1]) + "-recv." + self.file_name.split(".")[-1]

            # Write file
            with open(name_recv_type, "wb") as file:
                if args.verbose:
                    print_in_block("Writing file")
                file.write(self.file_buffer)

            # Calculate time
            time_taken = end_time - start_time
            # Calculate throughput im mbps
            throughput = (os.path.getsize(name_recv_type) * 8) / (time_taken * 1000_000)
            print_in_block(f"Time taken receiving: {time_taken:.2f} seconds", f"Throughput: {throughput:.2f} mbps")

            # Close socket
            self.server_socket.close()
            sys.exit(0)
        except Exception as e:
            self.server_socket.close()
            sys.exit(f"Error occurred while receiving data {repr(e)}")

    def handshake(self) -> None:
        """
        Wait for client to initiate handshake and then perform handshake with client
        :raises Exception: if handshake fails
        """
        try:
            # Receive syn
            package, address = self.server_socket.recvfrom(PACKAGE_SIZE)
            # Save client address for later use
            self.client_address = address
            header = parse_header(package[:12])
            flags = parse_flags(header.flags)

            # Update last valid sequence number
            self.last_valid_seq = header.seq

            # Check syn
            if not flags.syn:
                Exception("Did not receive syn")

            # Send syn-ack
            packet = create_packet(1, 0, set_flags(syn=True, ack=True), 64, None)
            self.server_socket.sendto(packet, self.client_address)

            # Receive ack

            # Set timeout for receiving ack
            self.server_socket.settimeout(0.5)

            # Receive ack
            package, _ = self.server_socket.recvfrom(PACKAGE_SIZE)
            header = parse_header(package[:12])
            flags = parse_flags(header.flags)

            # Remove timeout after receiving ack
            self.server_socket.settimeout(None)

            # Update last valid sequence number
            self.last_valid_seq = header.seq

            # Check ack
            if not flags.ack:
                Exception("Did not receive ack")

            # Handshake successful
            if args.verbose:
                print("Handshake successful")
        except Exception as e:
            self.server_socket.close()
            sys.exit(f"Handshake failed, {repr(e)}")

    def stop_and_wait(self) -> None:
        """
        Receive file using stop and wait method.
        Receive data from client in a loop and send ack for each package that is received in order.
        If a package is received out of order or is a duplicate, send a duplicate ack.
        Every valid package received is written to the file buffer.
        Function exits when a package with the fin flag is received.
        """
        # Receive file
        while True:
            header, data = self.receive_package()
            flags = parse_flags(header.flags)

            if header.seq != self.last_valid_seq + 1:
                # Duplicate or out of order package, send dupack
                self.send_ack(self.last_valid_seq)
            else:
                if data:
                    # Write data to file buffer
                    self.file_buffer += data
                self.send_ack(header.seq)
                self.last_valid_seq = header.seq

                if flags.fin:
                    break

    def go_back_n(self) -> None:
        """
        Receive file using go back N method. Receives data from client in a loop and sends ack for each package that is
        received in order. If a package is received out of order or is a duplicate, send a duplicate ack. Every valid
        package received is written to the file buffer. Function exits when a package with the fin flag is received.

        This method is very similar to stop and wait, but the client side implementation is different.
        """
        while True:
            # Receive packet
            header, data = self.receive_package()
            flags = parse_flags(header.flags)

            # Check if packet is duplicate
            if header.seq == self.last_valid_seq:
                # Send ack for duplicate packet
                self.send_ack(header.seq)
                continue

            # Check if packet is out of order
            if header.seq != self.last_valid_seq + 1:
                # Let client go to timeout
                continue

            # Packet is in order

            # Check if packet is fin
            if flags.fin:
                self.send_ack(header.seq)
                break

            # Save data to buffer
            self.file_buffer += data

            # Update last valid seq
            self.last_valid_seq = header.seq

            # Send ack
            self.send_ack(header.seq)

    def selective_repeat(self) -> None:
        """
        Receive file using selective repeat method. Receives data from client in a loop and acknowledges each package
        that is received in order. If a package is received out of order it is added to a buffer, and the sequence
        numbers that were skipped are added to a list. When a package is received the list of missing packages is
        checked and if the package is in the list it is added to the buffer. When a sequence of packages is received
        without any missing packages, the buffer is written to the file buffer and the list of missing packages is
        cleared. Function exits when a package with the fin flag is received.
        """
        missing_packages: list[int] = []  # List of missing packages
        package_buffer: dict[int, Optional[bytes]] = {}  # Buffer to store out-of-order packages
        received_fin = False

        while True:
            header, data = self.receive_package()
            flags = parse_flags(header.flags)

            # Check if in list of missing packages
            if header.seq in missing_packages:
                package_buffer[header.seq] = data
                missing_packages.remove(header.seq)

                if args.verbose:
                    print("Received missing package", header.seq)

            # Out of order
            if header.seq > self.last_valid_seq + 1:
                # Add skipped packages to missing packages list
                for i in range(self.last_valid_seq + 1, header.seq):
                    missing_packages.append(i)

                if args.verbose:
                    print("Received package out of order", header.seq)

            # Add package to buffer
            if data:
                package_buffer[header.seq] = data

            if flags.fin:
                received_fin = True
                self.send_ack(header.seq)
            else:
                if not self.skip_ack():
                    self.send_ack(header.seq)
                else:
                    print_in_block(f"Skipped ack {header.seq}")

            if header.seq > self.last_valid_seq:
                self.last_valid_seq = header.seq

            # Check if buffer has missing packages
            if not missing_packages and package_buffer:
                # Write to file buffer
                for i in sorted(package_buffer.keys()):
                    self.file_buffer += package_buffer[i]
                package_buffer.clear()

            # Check if all packages have been received
            if args.verbose and missing_packages:
                print("List of missing packages", missing_packages)

            if not missing_packages and received_fin:
                break

    def receive_package(self) -> Tuple[Header, Union[bytes, None]]:
        """
        Receive package from client and parse header.
        :return: Header and data
        """
        # Receive package
        package, _ = self.server_socket.recvfrom(PACKAGE_SIZE)
        # Parse header
        header = parse_header(package[:12])

        if args.verbose:
            # Parse flags
            flags = parse_flags(header.flags)

            if flags.fin:
                package_type = "fin"
            elif flags.ack:
                package_type = "ack"
            elif flags.syn:
                package_type = "syn"
            else:
                package_type = "data"

            print_in_columns(f"Received {package_type}", f"seq: {header.seq}")

        if len(package) > 12:
            data = package[12:]
        else:
            data = None

        return header, data

    def send_ack(self, ack) -> None:
        """
        Send ack to client.
        If the test case is skip_ack, the ack is skipped if the function self.skip_ack() returns true.
        :param ack: the ack number to send
        """
        # Skip ack if test case is skip_ack and generator returns true (chance)
        if self.skip_ack():
            print_in_block(f"Skipping ack {ack}")
            return

        if args.verbose:
            print_in_columns("Sending ack", f"ack: {ack}")

        # Send ack
        package = create_packet(self.get_next_seq(), ack, set_flags(ack=True), 64, None)
        self.server_socket.sendto(package, self.client_address)

    def skip_ack(self) -> bool:
        """
        Check if ack should be skipped.
        This method can only return True when the test case is skip_ack.
        Utilizes a generator to return True with a certain chance.
        :return: True if ack should be skipped, False otherwise
        """
        if args.test_case == "skip_ack":
            skipping = next(self.skip_ack_generator)
            if skipping:
                return True
            return skipping
        return False


""" CLIENT """


class Client:
    def __init__(self):
        self.client_socket = socket(AF_INET, SOCK_DGRAM)
        self.client_socket.connect((args.ip, args.port))

        # Set blocking to true (necessary on windows)
        self.client_socket.setblocking(True)

        # Default timeout is 0.5 seconds. This is updated during handshake
        self.client_socket.settimeout(0.5)
        # Multiplier for timeout (timeout = rtt * multiplier)
        self.rtt_multiplier = 4

        # File information
        self.filepath = args.file
        self.filename = os.path.basename(self.filepath)
        self.filesize = os.path.getsize(self.filepath)

        # Maximum number of retries
        self.max_retries = 10

        # Test
        self.test_can_run = False
        self.skip_seq_generator = yield_true_once()

        # Count number of timeouts
        self.number_of_timeouts = 0

        # Sequence number
        self._current_seq = 0

    def current_seq(self) -> int:
        """
        Get current sequence number.
        :return: current sequence number
        """
        return self._current_seq

    def next_seq(self) -> int:
        """
        Get next sequence number without incrementing.
        :return: next sequence number
        """
        return self._current_seq + 1

    def advance_seq(self) -> int:
        """
        Increment sequence number by one and return new value.
        :return: new sequence number
        """
        self._current_seq += 1
        return self._current_seq

    def start_client(self) -> None:
        """
        Perform handshake and start sending file to server.
        Uses the method specified in args.reliable_method.
        """
        try:
            # Handshake
            self.handshake()

            # Check method
            method = args.reliable_method

            # Send file information
            if args.verbose:
                print("Sending file information", f"name:{self.filename} method:{method}")
            data = f"{self.filename}{SEP}{method}"
            packet = create_packet(self.current_seq(), 0, set_flags(), 0, data.encode())
            # Send filename using stop and wait
            self.stop_and_wait(self.current_seq(), packet)

            print_in_block(f"Sending file {self.filename} using {METHOD_NAMES.get(method)} method")

            # Send file
            self.test_can_run = True
            start_time = time.time()
            with open(self.filepath, "rb") as file:
                # Stop and wait
                if method == "saw":
                    if args.verbose:
                        print_in_block("Stop and wait START")

                    while True:
                        data = file.read(DATA_SIZE)
                        if not data:
                            break
                        # Send packet using stop and wait
                        packet = create_packet(self.advance_seq(), 0, set_flags(), 0, data)
                        self.stop_and_wait(self.current_seq(), packet)

                    # Send fin
                    self.send_fin()
                    if args.verbose:
                        print_in_block("Stop and wait END")

                # Go back N
                elif method == "gbn":
                    self.go_back_n(file)

                # Selective repeat
                elif method == "sr":
                    self.selective_repeat(file)
            end_time = time.time()

            # Calculate time
            time_taken = end_time - start_time
            # Calculate throughput im mbps
            throughput = (os.path.getsize(self.filepath) * 8) / (time_taken * 1000_000)
            print_in_block(f"Time taken sending: {time_taken:.2f} seconds", f"Throughput: {throughput:.2f} mbps",
                           f"Number of timeouts: {self.number_of_timeouts}")

            print_in_block("Finished sending file")
        except Exception as e:
            raise Exception("Error occurred while sending data", repr(e))
        finally:
            # Close connection
            self.client_socket.close()
            sys.exit(1)

    def handshake(self) -> None:
        """
        Perform handshake with server.
        During the handshake the timeout value is set to the RTT * rtt_multiplier.
        :raises Exception: if handshake fails
        """
        if args.verbose:
            print("Performing handshake")

        try:
            # Send syn
            packet = create_packet(self.current_seq(), 0, set_flags(syn=True), 0, None)
            send_time = time.time()
            self.send_packet(packet)

            # Wait for syn ack
            ack = self.receive_ack()
            receive_time = time.time()

            # Calculate and set RTT
            rtt = receive_time - send_time
            timeout_value = rtt * self.rtt_multiplier
            self.client_socket.settimeout(timeout_value)
            if args.verbose:
                print("Using timeout value:", timeout_value)

            # Check if ack is correct
            if ack is None or ack != self.current_seq():
                print(ack, self.current_seq())
                raise Exception("Did not receive syn:ack")

            # Send ack
            package = create_packet(self.current_seq(), 0, set_flags(ack=True), 0, None)
            self.send_packet(package)

        except Exception as e:
            self.client_socket.close()
            sys.exit(f"Handshake failed {repr(e)}")

        if args.verbose:
            print("Handshake successful")

    def stop_and_wait(self, seq: int, packet: bytes) -> None:
        """
        Send packet to server and wait for ack.
        Repeat until ack is received.
        :param seq: sequence number
        :param packet: packet to send
        """
        retry_limiter = retry_counter(self.max_retries)

        # Wait for ack
        while True:
            # Check if we should try sending
            next(retry_limiter)

            # Send package
            self.send_packet(packet)

            # Receive ack
            ack = self.receive_ack()
            if ack == seq:
                break

    def go_back_n(self, file: BinaryIO) -> None:
        """
        Send file to server using go back N method.
        Fill sender window with packets and sends them.
        Then expects acknowledgments for all packets in the window.
        If ack is not received in time, all unacknowledged packets in the window are resent.
        Because the server only accepts packets in order, the ack received is cumulative.
        :param file:
        """
        if args.verbose:
            print_in_block("Go back N START")

        window_size = args.window_size
        sender_window: list[tuple[int, bytes]] = [] 
        done_reading = False
        retry_limiter = retry_counter(self.max_retries)

        while True:
            if not sender_window and done_reading:
                break

            # Fill sender window
            if len(sender_window) < window_size and not done_reading:
                # Read data from file
                data = file.read(DATA_SIZE)

                if data:
                    # Add data packet to sender window
                    packet = create_packet(self.advance_seq(), 0, set_flags(), window_size, data)
                else:
                    # If we reached the end of the file create fin packet
                    packet = create_packet(self.advance_seq(), 0, set_flags(fin=True), window_size, None)
                    done_reading = True

                # Add packet to sender window and send packet
                sender_window.append((self.current_seq(), packet))
            else:
                # Sender window is full or we are done reading

                # Send all packets in sender window
                for seq, packet in sender_window:
                    self.send_packet(packet)

                while sender_window:
                    ack = self.receive_ack()
                    if ack is not None:
                        # Ack is cumulative, so remove all packets with seq number less than or equal to ack
                        while sender_window and sender_window[0][0] <= ack:
                            # Remove acked packages from sender window
                            sender_window.pop(0)
                    else:
                        next(retry_limiter)
                        break
        if args.verbose:
            print_in_block("Go back N END")

    def selective_repeat(self, file: BinaryIO) -> None:
        """
        Send file to server using selective repeat method.
        Fills sender window with packets and sends them.
        Waits for ack for each packet in the window.
        If ack is not received in time, only the unacknowledged packet is resent.
        :param file:
        """
        if args.verbose:
            print_in_block("Selective repeat START")

        window_size = args.window_size
        sender_window: dict[int, bytes] = {}
        done_reading = False

        while True:
            # Return if we are done reading and sender window is empty
            if not sender_window and done_reading:
                break

            # Fill sender window
            while len(sender_window) < window_size and not done_reading:

                # Read data from file
                data = file.read(DATA_SIZE)

                if not data:
                    # Create fin packet if we reached the end of the file
                    packet = create_packet(self.advance_seq(), 0, set_flags(fin=True), window_size, None)
                    done_reading = True
                else:
                    # Create data packet
                    packet = create_packet(self.advance_seq(), 0, set_flags(), window_size, data)

                # Add packet to sender window
                sender_window[self.current_seq()] = packet

            # Send all packets in sender window
            for seq, packet in sender_window.items():
                self.send_packet(packet)

            # Receive ack and remove acked packages from sender window
            while sender_window:
                ack = self.receive_ack()
                if ack is not None:
                    if ack in sender_window:
                        del sender_window[ack]
                    else:
                        continue
                else:
                    break

        if args.verbose:
            print_in_block("Selective repeat END")

    def send_fin(self) -> None:
        """
        Send fin packet to server using stop and wait method.
        """
        # Send fin
        packet = create_packet(self.advance_seq(), 0, set_flags(fin=True), 0, None)
        self.stop_and_wait(self.current_seq(), packet)

    def send_packet(self, packet: bytes) -> None:
        """
        Send packet to server.
        Uses skip_seq to skip sending a packet is the skip_seq test case is active.
        :param packet: packet to send
        """
        # Test case to skip seq
        if self.skip_seq():
            header = parse_header(packet[:12])
            # Create corrupted packet with next sequence number
            if args.verbose:
                print_in_block(f"Skipping packet with seq {header.seq}")
            return

        # Send packet
        self.client_socket.sendall(packet)

        if args.verbose:
            header = parse_header(packet[:12])
            flags = parse_flags(header.flags)

            if flags.fin:
                package_type = "fin"
            elif flags.ack:
                package_type = "ack"
            elif flags.syn:
                package_type = "syn"
            else:
                package_type = "data"

            print_in_columns(f"Sending {package_type}", f"seq: {header.seq}")

    def receive_ack(self) -> Union[int, None]:
        """
        Receive ack from server.
        If the socket times out, the timeout counter is increased.
        :return: the ack number or None if no ack was received
        :raises Exception: if received package does not have ack flag
        """
        try:
            # Receive package from server
            package = self.client_socket.recv(PACKAGE_SIZE)
            seq, ack, flags, win = parse_header(package[:12])
            flags = parse_flags(flags)

            if flags.ack:
                if args.verbose:
                    if flags.syn:
                        print_in_columns(f"Received syn:ack", f"ack: {ack}")
                    elif flags.fin:
                        print_in_columns(f"Received fin:ack", f"ack: {ack}")
                    else:
                        print_in_columns(f"Received ack", f"ack: {ack}")

                return ack
            raise Exception("Received package without ack flag")
        except Exception as e:
            if isinstance(e, OSError):
                print("Timeout while receiving package")
                self.number_of_timeouts += 1
            else:
                raise Exception("Error while receiving package", repr(e))
            return None

    def skip_seq(self) -> bool:
        """
        Test case to skip sending a packet.
        Uses the skip_seq_generator to determine if a packet should be skipped.
        :return: True if packet should be skipped, False otherwise
        """
        if not self.test_can_run:
            return False

        if args.test_case == "skip_seq":
            skipping = next(self.skip_seq_generator)
            if skipping:
                return True
            return skipping
        return False


""" UTILITY FUNCTIONS """


def print_in_block(*args):
    """
    Prints data in a block.
    :param args: printable data
    """
    min_len = max(len(arg) for arg in args)
    base_len = 30
    print_len = max(min_len, base_len)
    print_len = print_len + 4
    top = "─" * print_len
    bottom = "─" * print_len

    print(top)
    for arg in args:
        print(arg.center(print_len))
    print(bottom)


def print_in_columns(*args: object) -> None:
    """
    Prints data in columns of length 20.
    :param args: printable data
    """
    columns = (" {: <20} " * len(args)).strip()
    print(columns.format(*args))


def retry_counter(limit: int) -> Generator[int, None, None]:
    """
    Yields a counter starting at 0 and ending at limit.
    Raises an exception when limit is reached.
    :param limit: limit of the counter
    :raises Exception: when limit is reached
    """
    counter = 0
    while True:
        yield counter
        counter += 1
        if counter == limit:
            raise Exception("Retries limit reached")


def yield_true_once() -> Generator[bool, None, None]:
    """
    Yields True once and then False forever.
    The probability of yielding True starts at 1/10.
    The probability of yielding True increases by 1/10 for every False.
    """
    done = False
    tries = 0

    while True:
        if not done:
            if randint(0, 10 - tries) == 0:
                yield True
                done = True
            else:
                tries += 1
        yield False


def parse_header(header: bytes) -> Header:
    """
    Takes a header of 12 bytes as an argument,
    unpacks the value based on the constant HEADER_FORMAT
    and returns a named tuple with the values
    :param header: 12 bytes header
    :return: parsed header as a named tuple Header
    """
    seq, ack, flags, win = unpack(HEADER_FORMAT, header)
    return Header(seq, ack, flags, win)


def parse_flags(flags: int) -> Flags:
    """
    Takes a 4 bit integer as an argument,
    bit shifts the integer to get the value of each flag
    and returns a named tuple with the values.
    Only the first 3 fields are parsed because we're not
    using reset flag in our implementation.
    :param flags: four bit integer
    :return: parsed flags as a named tuple Flags(ack, syn, fin) containing boolean values
    """
    # We only parse the first 3 fields because we're not
    # using reset flag in our implementation

    syn = flags & (1 << 3)  # 1 << 3 = 1000
    ack = flags & (1 << 2)  # 1 << 2 = 0100
    fin = flags & (1 << 1)  # 1 << 1 = 0010
    # rst = flags & 1       # 1 << 0 = 0001

    # Return flags as a named tuple Flags
    return Flags(bool(syn), bool(ack), bool(fin))


def create_packet(seq: int, ack: int, flags: int, win: int, data: bytes = None) -> bytes:
    """
    Creates a packet with header information and application data
    and returns a bytes object containing the header values
    # packed according to the header_format !IIHH
    :param seq: sequence number of the packet (4 bytes)
    :param ack: acknowledgment number of the packet (4 bytes)
    :param flags: flags of the packet (2 bytes)
    :param win: receiver window of the packet (2 bytes)
    :param data: application data of the packet (1460 bytes)
    :return: packet with header and application data (1472 bytes)
    """
    header = pack(HEADER_FORMAT, seq, ack, flags, win)

    packet = header  # 12 bytes

    if data:
        packet += data  # 1460 bytes

    return packet  # 1472 bytes


def set_flags(syn: bool = False, ack: bool = False, fin: bool = False) -> int:
    """
    Set flags for a packet header
    :param syn: bool indicating if syn flag should be set
    :param ack: bool indicating if ack flag should be set
    :param fin: bool indicating if fin flag should be set
    :return: int representing the flags in the header
    """
    flag = 0
    if syn:
        flag |= 1 << 3  # 1 << 3 = 1000
    if ack:
        flag |= 1 << 2  # 1 << 2 = 0100
    if fin:
        flag |= 1 << 1  # 1 << 1 = 0010
    # if rst:
    #     flag |= 1       # 1 << 0 = 0001

    return flag


""" MAIN """

if __name__ == '__main__':
    args = parse_args()

    if args.server:
        print_in_block("Running in server mode")
        server = Server()
        server.start_server()

    if args.client:
        print_in_block("Running in client mode")
        client = Client()
        client.start_client()
