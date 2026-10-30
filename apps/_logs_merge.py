# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# _logs_merge.py - merges several log streams into ONE stream, in time order (app-log-live.py --logs-nginx).
#
# Usage:
#   python3 _logs_merge.py [--grep REGEX] [--grep-sensitive] [--lines N] [--nginx FILE [FILE ...]] [--no-follow]
#                          [--since EPOCH] [--until EPOCH] [--version] [--wait SECONDS] [-- COMMAND [ARGUMENT ...]]
#
# COMMAND (optional) is the application stream: "journalctl -o short-iso-precise ..." or the converter of the Odoo file
# journal (apps/_odoo_journal.py). Its lines already begin with a systemd journal prefix: they are printed as they are.
# Each nginx FILE is followed with "tail -n N" (and "-F" unless --no-follow). Its lines receive the SAME prefix, in local
# time, "2026-10-29T21:52:03.000000-0400 host nginx: ", so that app-log-live.py reads them like the application lines:
#   * access log: the "[29/Oct/2026:21:52:03 -0400]" of the request is removed (it is already in the prefix), as for the
#     werkzeug lines of Odoo: "1.2.3.4 - - "GET /web HTTP/1.1" 200 ...";
#   * error log: the date and time at the start of the line are removed (already in the prefix); the rest is kept.
# --grep, --since and --until apply to the nginx lines only (the application stream is already filtered by journalctl).
#
# Order: each stream is in time order, and the lines are merged by time (the oldest first). A stream that is silent is
# waited for at most --wait seconds, then it is "stalled": not waited for again until one of its lines arrives, so a quiet
# nginx does not hold back the lines of Odoo. A line without a time (Python traceback continuation) takes the time of the
# previous line of its stream.
#
# SIGTERM (sent by app-log-live.py when it stops) stops the commands started here. A closed output pipe ends the program
# without a message.
# ========================================================================================================================
import argparse
import collections
import datetime
import os
import queue
import re
import signal
import socket
import subprocess
import sys
import threading
import time

__version__ = "1.0.20261029.215532"

WAIT_DEFAULT = float(os.environ.get("APP_LOG_MERGE_WAIT", "2"))         # seconds a silent stream is waited for, then "stalled"
JOURNAL_PROGRAM = "nginx"                                              # program name of the nginx lines in the journal format

# Journal prefix of "journalctl -o short-iso-precise" and of apps/_odoo_journal.py: 2026-10-29T21:52:03.123456-0400 ...
JOURNAL_TIME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d+)([+-])(\d{2}):?(\d{2})")
# nginx access log ("combined" and "combined_host"): 1.2.3.4 - - [29/Oct/2026:21:52:03 -0400] "GET / HTTP/1.1" ...
NGINX_ACCESS_RE = re.compile(r"^(\S+) (\S+) (\S+) \[([^\]]+)\] (.*)$")
ACCESS_TIME_RE = re.compile(r"^(\d{2})/([A-Za-z]{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) ([+-])(\d{2})(\d{2})$")
# nginx error log: 2026/10/29 21:52:03 [error] 1234#0: *5 message (local time of the server, without offset)
NGINX_ERROR_RE = re.compile(r"^(\d{4})/(\d{2})/(\d{2}) (\d{2}):(\d{2}):(\d{2}) (\[.*)$")
MONTHS = {name: number for number, name in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def offset_zone(sign, hours, minutes):
    """Fixed time zone of a UTC offset written as in the logs (sign, hours, minutes)."""
    delta = datetime.timedelta(hours=int(hours), minutes=int(minutes))
    return datetime.timezone(-delta if sign == "-" else delta)


def journal_instant(raw):
    """Instant (seconds since the epoch) of the journal prefix of a line, or None if the line does not begin with one."""
    m = JOURNAL_TIME_RE.match(raw)
    if not m:
        return None
    year, month, day, hour, minute, second, fraction, sign, hours, minutes = m.groups()
    micro = int((fraction + "000000")[:6])
    moment = datetime.datetime(int(year), int(month), int(day), int(hour), int(minute), int(second), micro,
                               tzinfo=offset_zone(sign, hours, minutes))
    return moment.timestamp()


def access_instant(when):
    """Instant of an nginx access time such as "29/Oct/2026:21:52:03 -0400", or None."""
    m = ACCESS_TIME_RE.match(when)
    if not m or m.group(2) not in MONTHS:
        return None
    day, month, year, hour, minute, second, sign, hours, minutes = m.groups()
    moment = datetime.datetime(int(year), MONTHS[month], int(day), int(hour), int(minute), int(second),
                               tzinfo=offset_zone(sign, hours, minutes))
    return moment.timestamp()


def nginx_pair(raw):
    """(instant or None, message) of a line of an nginx log: the message has no time of its own (it is in the prefix).
    The instant is None when the time is not recognized: the message is then the line as it is."""
    m = NGINX_ACCESS_RE.match(raw)
    if m:
        ip, ident, user, when, rest = m.groups()
        instant = access_instant(when)
        if instant is not None:
            return instant, f"{ip} {ident} {user} {rest}"
    m = NGINX_ERROR_RE.match(raw)
    if m:
        year, month, day, hour, minute, second, rest = m.groups()
        try:
            instant = datetime.datetime(int(year), int(month), int(day), int(hour), int(minute), int(second)).astimezone().timestamp()
        except (ValueError, OverflowError, OSError):
            return None, raw
        return instant, rest
    return None, raw


def journal_line(instant, host, message):
    """Line in the format of a journal entry (local time with its offset, host, program), as app-log-live.py reads it."""
    local = datetime.datetime.fromtimestamp(instant, datetime.timezone.utc).astimezone()
    return f"{local:%Y-%m-%dT%H:%M:%S}.{local.microsecond:06d}{local:%z} {host} {JOURNAL_PROGRAM}: {message}"


class Filters:
    """--since, --until and --grep: applied to the nginx lines."""
    def __init__(self, since=None, until=None, grep=None, sensitive=False):
        self.since, self.until = since, until
        self.pattern = re.compile(grep, 0 if sensitive else re.IGNORECASE) if grep else None

    def keep(self, instant, message):
        if self.since is not None and instant < self.since:
            return False
        if self.until is not None and instant > self.until:
            return False
        return self.pattern is None or self.pattern.search(message) is not None


class Merger:
    """k-way merge of the streams. The shared queue receives (stream index, instant, message), and (index, None, None) at the
    end of a stream. The buffers hold the lines already read, in order, of each stream."""
    def __init__(self, count, wait):
        self.wait = wait
        self.shared = queue.Queue()
        self.buffers = [collections.deque() for _ in range(count)]
        self.finished = [False] * count
        self.stalled = [False] * count

    def pump(self, timeout):
        """Takes one item of the shared queue into the buffer of its stream; False if nothing arrived within timeout."""
        try:
            index, instant, message = self.shared.get(timeout=timeout) if timeout > 0 else self.shared.get_nowait()
        except queue.Empty:
            return False
        if message is None:
            self.finished[index] = True
        else:
            self.buffers[index].append((instant, message))
            self.stalled[index] = False
        return True

    def fill(self):
        """Makes sure every open stream has a waiting line, or is stalled."""
        while self.pump(0):
            pass
        for index in range(len(self.buffers)):
            if self.buffers[index] or self.finished[index] or self.stalled[index]:
                continue
            deadline = time.time() + self.wait
            while not self.buffers[index] and not self.finished[index]:
                remaining = deadline - time.time()
                if remaining <= 0 or not self.pump(remaining):
                    break
            self.stalled[index] = not self.buffers[index] and not self.finished[index]

    def next_message(self):
        """The oldest waiting line (ties: the lower stream index first), or None when every stream has ended."""
        while True:
            self.fill()
            waiting = [(buffer[0][0], index) for index, buffer in enumerate(self.buffers) if buffer]
            if waiting:
                _, index = min(waiting)
                return self.buffers[index].popleft()[1]
            if all(self.finished):
                return None
            self.pump(0.5)                                # every open stream is silent: wait for the next line


def read_stream(index, process, convert, host, shared):
    """Thread: reads the output of one command, converts each line and puts it into the shared queue.
    convert(raw) gives (instant or None, message or None); a message of None is dropped (filtered); host None: no prefix."""
    last = None
    try:
        for raw in process.stdout:
            instant, message = convert(raw.rstrip("\n"))
            if instant is None:
                instant = last if last is not None else time.time()
            else:
                last = instant
            if message is None:
                continue
            if host is not None:
                message = journal_line(instant, host, message)
            shared.put((index, instant, message))
    except (OSError, ValueError):
        pass
    finally:
        shared.put((index, None, None))


def start(command):
    """Process of a command whose standard output is read line by line, or None if it cannot be started."""
    try:
        return subprocess.Popen(command, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, universal_newlines=True,
                                errors="replace", bufsize=1)
    except OSError as e:
        sys.stderr.write(f"_logs_merge.py: cannot run {command[0]} ({e})\n")
        return None


def parse_arguments(argv):
    """Options (before "--") and the command (after it). The options are in alphabetical order, as in every program."""
    if "--" in argv:
        cut = argv.index("--")
        own, command = argv[:cut], argv[cut + 1:]
    else:
        own, command = argv, []
    parser = argparse.ArgumentParser(description="Merges log streams in time order (nginx lines in the journal format).")
    parser.add_argument("--grep", default=None, metavar="REGEX", help="nginx lines matching REGEX only")
    parser.add_argument("--grep-sensitive", action="store_true", help="--grep is case-sensitive")
    parser.add_argument("--lines", type=int, default=50, metavar="N", help="history lines of each nginx file (default: 50)")
    parser.add_argument("--nginx", nargs="+", default=[], metavar="FILE", help="nginx log files to merge")
    parser.add_argument("--no-follow", action="store_true", help="read the history of the files, then stop")
    parser.add_argument("--since", type=float, default=None, metavar="EPOCH", help="nginx lines from this instant on")
    parser.add_argument("--until", type=float, default=None, metavar="EPOCH", help="nginx lines up to this instant")
    parser.add_argument("--version", action="version", version=f"_logs_merge.py version {__version__}")
    parser.add_argument("--wait", type=float, default=WAIT_DEFAULT, metavar="SECONDS",
                        help=f"seconds a silent stream is waited for (default: {WAIT_DEFAULT:g})")
    return parser.parse_args(own), command


def main(argv=None):
    args, command = parse_arguments(sys.argv[1:] if argv is None else argv)
    host = socket.gethostname()
    filters = Filters(args.since, args.until, args.grep, args.grep_sensitive)

    def nginx_convert(raw):
        instant, message = nginx_pair(raw)
        if instant is not None and not filters.keep(instant, message):
            return instant, None
        return instant, message

    # Each source: (command, convert, host for the prefix or None). The application stream has its prefix already.
    sources = []
    if command:
        sources.append((command, lambda raw: (journal_instant(raw), raw), None))
    for path in args.nginx:
        tail = ["tail", "-n", str(args.lines)] + ([] if args.no_follow else ["-F"]) + [path]
        sources.append((tail, nginx_convert, host))
    if not sources:
        return 0
    merger = Merger(len(sources), args.wait)
    processes = []
    try:
        for index, (cmd, convert, prefix_host) in enumerate(sources):
            process = start(cmd)
            if process is None:
                merger.shared.put((index, None, None))
                continue
            processes.append(process)
            threading.Thread(target=read_stream, args=(index, process, convert, prefix_host, merger.shared), daemon=True).start()
        while True:
            message = merger.next_message()
            if message is None:
                break
            sys.stdout.write(message + "\n")
            sys.stdout.flush()
    except (KeyboardInterrupt, BrokenPipeError):
        pass                                              # interrupted, or the reader of the output has gone: stop quietly
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
    return 0


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    sys.exit(main())
