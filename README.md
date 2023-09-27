## Data2410 Reliable Transport Protocol (DRTP)

## Table of contents:

<!-- TOC -->
  * [Data2410 Reliable Transport Protocol (DRTP)](#data2410-reliable-transport-protocol--drtp-)
  * [Table of contents:](#table-of-contents-)
  * [Description:](#description-)
  * [Limitations:](#limitations-)
  * [Usage:](#usage-)
  * [Options:](#options-)
    * [Server mode:](#server-mode-)
    * [Client mode:](#client-mode-)
  * [Examples:](#examples-)
    * [Server mode:](#server-mode--1)
    * [Client mode:](#client-mode--1)
<!-- TOC -->

## Description:

DRTP is a tool for reliable file transfer over UDP between a client and a server.

## Limitations:

The application is only tested using python 3.9.2 and above

The socket timeout is set to four times the RTT. When running the application on local host without added delay this
timeout might be too short. If the application times out, try increasing the timeout value in the code.

## Usage:

The application can be initialized in either server or client mode.

In server mode, the application listens on a port and waits for a client to start sending.

In client mode, the application connects to a server and sends a file to it.

- Initialize application in server mode with default settings `application.py -s`
- Initialize application in client mode with default settings `application.py -c -f filename.txt`

## Options:

Not all option combinations are valid. Both the client and server must use the same reliability method. The client must
specify a file to send. The client can specify a window size, but the server broadcasts a default receiver window size
of 64.

### Server mode:

| Option                                            | Description                                                                                   |
|---------------------------------------------------|-----------------------------------------------------------------------------------------------|
| `-h, --help`                                      | show help message and exit                                                                    |
| `-s, --server`                                    | Run in server mode (default: False)                                                           |
| `-c, --client`                                    | Run in client mode (default: False)                                                           |
| `-i IP, --ip IP`                                  | The IP address to bind to (default: 127.0.0.1)                                                |
| `-p PORT, --port PORT`                            | The port to listen on (default: 8088)                                                         |
| `-r {saw,gbn,sr}, --reliable_method {saw,gbn,sr}` | The reliability functions to use, Stop And Wait, Go Back N or Selective Repeat (default: saw) |
| `-t {skip_ack}, --test_case {skip_ack}`           | The test case to run (default: None)                                                          |
| `-v, --verbose`                                   | Enable verbose mode (default: False)                                                          |

### Client mode:

| Option                                            | Description                                                                                   |
|---------------------------------------------------|-----------------------------------------------------------------------------------------------|
| `-h, --help`                                      | show help message and exit                                                                    |
| `-c, --client`                                    | Run in client mode (default: False)                                                           |
| `-i IP, --ip IP`                                  | The IP address to bind to (default: 127.0.0.1)                                                |
| `-p PORT, --port PORT`                            | The port to listen on (default: 8088)                                                         |
| `-r {saw,gbn,sr}, --reliable_method {saw,gbn,sr}` | The reliability functions to use, Stop And Wait, Go Back N or Selective Repeat (default: saw) |
| `-f FILE, --file FILE`                            | The file to send (default: None)                                                              |
| `-t {skip_seq}, --test_case {skip_seq}`           | The test case to run (default: None)                                                          |
| `-w WINDOW_SIZE, --window_size WINDOW_SIZE`       | The window size to use (default: 5)                                                           |
| `-v, --verbose`                                   | Enable verbose mode (default: False)                                                          |

## Examples:

### Server mode:

- Run application in server mode and bind to ip 10.0.0.2 with port 8080 `application.py -s -i 10.0.0.2 -p 8080`
- Run application in server mode using default ip and port, using reliability method Go Back
  N `application.py -s -r gbn`

### Client mode:

- Run application in client mode and connect to server at 10.0.0.2 with port 8080,
  picture.jpg `application.py -c -i 10.0.0.2 -p 8080 -f picture.jpg`
- Run application in client mode using default ip and port, using reliability method Go Back N, sending
  file.txt `application.py -c -f file.txt -r gbn`
- Run application in client mode using default ip and port, sending picture.jpg printing verbose status
  messages `application.py -c -f picture.jpg -v`
