# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# _logs_merge.py - merges several log streams into ONE stream, in time order (app-log-live.py --log-nginx).
#
# Usage:
#   python3 _logs_merge.py [--grep REGEX] [--grep-sensitive] [--lines N] [--nginx FILE [FILE ...]] [--no-follow]
#                          [--since EPOCH] [--until EPOCH] [--version] [--wait SECONDS] [-- COMMAND [ARGUMENT ...]]
#
# COMMAND (optional) is the application stream: "journalctl -o short-iso-precise ..." or the converter of the Odoo file
# journal (apps/_odoo_journal.py). Its lines already begin with a systemd journal prefix: they are printed as they are.
# Each nginx FILE is followed with "tail -n N" (and "-F" unless --no-follow). Its lines receive the SAME prefix, in local
# time, "2026-10-29T21:52:03.000000-0400 host http: ", so that app-log-live.py reads them like the application lines:
#   * access log: the "[29/Oct/2026:21:52:03 -0400]" of the request is removed (it is already in the prefix), as for the
#     werkzeug lines of Odoo: "1.2.3.4 - - "GET /web HTTP/1.1" 200 ...";
#   * error log: the date and time at the start of the line are removed (already in the prefix); the rest is kept.
# --grep, --since and --until apply to the nginx lines only (the application stream is already filtered by journalctl).
#
# Order (1.2): the lines are merged by log time, the oldest first. A line is held for --wait seconds (APP_LOG_MERGE_WAIT,
# 1.5 by default) before it is released, so that a line a stream delivers late, within that time, still comes in its place.
# No stream is waited for: a silent stream never holds back the others. A line without a time (Python traceback continuation)
# takes the time of the previous line of its stream. Lines of the same second (nginx has no finer time) keep their arrival order.
#
# SIGTERM (sent by app-log-live.py when it stops) stops the commands started here. A closed output pipe ends the program
# without a message.
# ========================================================================================================================
import argparse
import datetime
import heapq
import itertools
import os
import queue
import re
import signal
import socket
import subprocess
import sys
import threading
import time

__version__ = "1.2.20261102.080324"

WAIT_DEFAULT = float(os.environ.get("APP_LOG_MERGE_WAIT", "1.5"))       # seconds a line is held to be placed in time order (1.2)
JOURNAL_PROGRAM = "http"                                               # program name of the nginx lines in the journal format (4 characters, like "odoo")

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
    """Time-ordered merge of the streams (1.2). The lines wait in a heap, sorted by log time, and a line is released only when
    its log time is at least `wait` seconds in the past (wall clock): a line that a stream delivers late, within that window,
    is still placed in time order. No stream is waited for: a silent stream never holds back the others. At the start, nothing
    is released before every stream has delivered a line or ended (or `wait` seconds have passed), so that the history of
    several files is merged too. When every stream has ended, what remains is released in order at once.
    `late` counts the lines that arrived after a later line had been released (they are printed in place, not dropped)."""
    def __init__(self, count, wait):
        self.wait = wait
        self.shared = queue.Queue()
        self.heap = []
        self.sequence = itertools.count()
        self.finished = [False] * count
        self.seen = [False] * count
        self.started = time.time()
        self.last_released = None
        self.late = 0

    def pump(self, timeout):
        """Takes one item of the shared queue into the heap; False if nothing arrived within timeout."""
        try:
            index, instant, message = self.shared.get(timeout=timeout) if timeout > 0 else self.shared.get_nowait()
        except queue.Empty:
            return False
        if message is None:
            self.finished[index] = True
        else:
            self.seen[index] = True
            heapq.heappush(self.heap, (instant, next(self.sequence), index, message))
        return True

    def releasable(self, now):
        """True when the oldest waiting line may be released (see the class documentation)."""
        if not self.heap:
            return False
        if all(self.finished):
            return True
        if not all(seen or done for seen, done in zip(self.seen, self.finished)) and now - self.started < self.wait:
            return False                                    # start: the history of every stream is awaited, for `wait` seconds at most
        return self.heap[0][0] + self.wait <= now

    def next_message(self):
        """The oldest line that may be released, or None when every stream has ended and nothing waits."""
        while True:
            while self.pump(0):
                pass
            now = time.time()
            if self.releasable(now):
                instant, _, _, message = heapq.heappop(self.heap)
                if self.last_released is not None and instant < self.last_released:
                    self.late += 1
                self.last_released = instant if self.last_released is None else max(self.last_released, instant)
                return message
            if not self.heap and all(self.finished):
                return None
            timeout = 0.2                                   # a new line is taken as it comes; the oldest one is re-checked at its due time
            if self.heap:
                timeout = min(timeout, max(0.01, self.heap[0][0] + self.wait - now))
            self.pump(timeout)


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
