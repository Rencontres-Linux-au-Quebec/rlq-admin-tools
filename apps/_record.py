#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Québec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# _record.py — test RECORDING for app-log-live.py (R key, --record-test-log): everything needed to analyze one test of the site,
# gathered over the recording window and packed into one .tar.xz (shared module, apps/).
#
"""One recording = one window of time [start, stop] and one archive `app-log-live-record-HOST-YYYYMMDD-HHMMSS[-label].tar.xz`:

  README.txt          what the archive holds (French and English): times (local and UTC), server, versions, label, filters, counts, missing sources
  records.log         the lines of app-log-live.py WITHOUT the noise (robots, static files, websockets, local probes): what the test did
  stream-all.log      every line of the window, each with its category ([kept] [robot] [static] [websocket] [local])
  steps.txt           the steps marked with the N key (start, end, duration, description); bilingual header
  raw/                complete extracts of the window, unfiltered: each log file given by the program (nginx access / error, blocked-probes, fail2ban, Odoo logfile,
                      BigBlueButton…), read from the size it had at the start (rotation followed), and the systemd journal of the service (journalctl --since/--until)
  network/            every SAMPLE_S seconds: TCP connections of the web and Odoo ports (ss), and a one-line count per port
  db/                 every SAMPLE_S seconds: pg_stat_activity (state, transaction age, query with its literals removed) and the locks held on ir_cron (scheduled
                      action running); at the start and at the end: counters and dates only (surveys, registrations, scheduled e-mails, e-mail queue, leads, wiki,
                      website views, scheduled actions), and the columns of these tables (Odoo version check)
  context/            service settings (systemctl show), Odoo configuration WITHOUT secrets (whitelisted keys), installed modules of interest, log files watched

PRIVACY (the archive is meant to be sent for analysis): every text is masked BEFORE it is written — IP addresses, e-mails, names known to the program
(stable pseudonyms of apps/_anonymiser.py, the same in every file of the archive), tokens (survey and ticket tokens, *hash*= / *token*= parameters, UUIDs,
long hexadecimal strings: « tok-xxxxxx »), SQL literals ('?'). No personal data is read from the database: counts, dates, identifiers, states.
Without apps/_anonymiser.py, a built-in fallback still replaces the addresses and e-mails (pseudonyms valid for this archive only).
Nothing here modifies anything: PostgreSQL is read in read-only transactions (the `query` function of apps/_odoo_db.py), the logs are only read."""
import datetime
import hashlib
import hmac
import ipaddress
import os
import platform
import pwd
import re
import secrets
import shutil
import socket
import subprocess
import tarfile
import tempfile
import threading
import time

__version__ = "1.2.20261022.133552"

SAMPLE_S = 10                               # seconds between two network / PostgreSQL samples
RAW_MAX_BYTES = 50 * 1024 * 1024            # at most this much read from ONE log file (the beginning of the window is kept, the rest is noted as cut)
STREAM_MAX_BYTES = 200 * 1024 * 1024        # records.log + stream-all.log: the recording stops by itself beyond this size
MAX_SECONDS_DEFAULT = 30 * 60               # RECORD_MAX of app-log-live.py: the recording stops by itself after 30 minutes
DISK_MIN_BYTES = 500 * 1024 * 1024          # free space needed in the folder of the archives to start
ARCHIVE_PREFIX = "app-log-live-record"
CATEGORIES = ("kept", "robot", "static", "websocket", "local")

UUID_RE = re.compile(r"(?<![0-9A-Za-z])[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?![0-9A-Za-z])")
LONG_HEX_RE = re.compile(r"(?<![0-9A-Za-z])[0-9a-fA-F]{20,}(?![0-9A-Za-z])")
TOKEN_PARAM_RE = re.compile(r"(?i)([?&;][\w.-]*(?:hash|token|key|sig|secret)[\w.-]*=)([^&\s\"'#]+)")
SURVEY_PATH_RE = re.compile(r"(/survey/[\w-]+/)([\w-]{12,})(?:/([\w-]{12,}))?")      # /survey/start/<survey token>, /survey/submit/<survey token>/<answer token>…
SQL_LITERAL_RE = re.compile(r"'(?:[^']|'')*'")
FALLBACK_IPV4_RE = re.compile(r"(?<![\w.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?!\w|\.\d)")
FALLBACK_IPV6_RE = re.compile(r"(?<![\w:.])(?:[0-9A-Fa-f]{1,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:.])")
FALLBACK_MAIL_RE = re.compile(r"[A-Za-z0-9._+*-]+(?:@|%40)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
ODOO_CONF_KEYS = ("workers", "max_cron_threads", "http_port", "xmlrpc_port", "gevent_port", "longpolling_port", "limit_time_real", "limit_time_cpu",
                  "limit_time_real_cron", "limit_request", "limit_memory_soft", "limit_memory_hard", "db_maxconn", "proxy_mode", "log_level", "logfile",
                  "server_wide_modules", "list_db", "unaccent")
MODULES_OF_INTEREST = ("base", "web", "website", "web_editor", "html_editor", "website_form", "survey", "website_survey", "event", "website_event",
                       "website_event_track", "event_sms", "crm", "website_crm", "document_page", "mail", "bus", "website_livechat", "im_livechat")
TABLES = ("survey_user_input", "survey_user_input_line", "survey_survey", "event_registration", "event_event", "event_mail", "event_track", "mail_mail",
          "mail_message", "mail_template", "crm_lead", "document_page", "document_page_history", "ir_ui_view", "website_page", "ir_attachment", "ir_cron",
          "website_visitor", "website_track", "bus_presence", "mail_presence", "res_users_log", "ir_module_module")
NOW_UTC = "(now() AT TIME ZONE 'UTC')"     # Odoo stores its dates in UTC, without time zone


def _run(cmd, timeout=20):
    """(code, stdout + stderr) of a command; (127, '') if it cannot run. Never an exception."""
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, universal_newlines=True,
                           errors="replace", timeout=timeout)
        return r.returncode, r.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return 127, ""


def slug(text, limit=40):
    """Label typed by the user -> part of a file name: letters, digits and dashes only (accents removed), at most `limit` characters."""
    import unicodedata
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:limit].strip("-")


def default_folder(journal_folder=None, env=None, euid=None):
    """Folder of the archives: APP_LOG_LIVE_RECORD_DIR; otherwise, under sudo, ~USER/app-log-live-records of the person who ran sudo (they can copy the archive
    without root); otherwise JOURNAL_FOLDER/records (the folder of the daily logs); otherwise ~/.local/state/app-log-live/records."""
    env = os.environ if env is None else env
    euid = os.geteuid() if euid is None else euid
    if env.get("APP_LOG_LIVE_RECORD_DIR"):
        return os.path.abspath(os.path.expanduser(env["APP_LOG_LIVE_RECORD_DIR"]))
    if euid == 0 and env.get("SUDO_USER") and env.get("SUDO_USER") != "root":
        try:
            return os.path.join(pwd.getpwnam(env["SUDO_USER"]).pw_dir, "app-log-live-records")
        except KeyError:
            pass
    if journal_folder:
        return os.path.join(journal_folder, "records")
    return os.path.join(os.path.expanduser("~"), ".local", "state", "app-log-live", "records")


TOOL_VERSIONS = (("psql", ["psql", "--version"]), ("runuser", ["runuser", "--version"]), ("sudo", ["sudo", "-V"]), ("journalctl", ["journalctl", "--version"]),
                  ("systemctl", ["systemctl", "--version"]), ("ss", ["ss", "-V"]), ("nginx", ["nginx", "-v"]), ("fail2ban-client", ["fail2ban-client", "-V"]),
                  ("ipset", ["ipset", "-V"]))     # 1.2: versions written in context/system.txt (stdout and stderr)


def privileged(cmd):
    """1.2: root commands (journalctl of a protected service…) run through « sudo -n » when this account is not root (see app-log-live.py)."""
    if os.geteuid() == 0 or shutil.which("sudo") is None:
        return cmd
    return ["sudo", "-n"] + cmd


def _tool_code(cmd):
    try:
        return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=10).returncode
    except (OSError, subprocess.TimeoutExpired):
        return 127


def _tool_first_line(cmd):
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=10, universal_newlines=True, errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = (r.stdout or "").strip().splitlines()
    return lines[0] if lines else f"(no output, code {r.returncode})"


def sudo_owner(env=None):
    """(uid, gid) of the person who ran sudo, or None: the archive is given to them."""
    env = os.environ if env is None else env
    try:
        uid, gid = int(env.get("SUDO_UID", "")), int(env.get("SUDO_GID", ""))
    except ValueError:
        return None
    return (uid, gid) if uid > 0 else None


class FallbackMask:
    """Masking without apps/_anonymiser.py: addresses and e-mails replaced by pseudonyms keyed by a random salt (valid for this archive only)."""

    def __init__(self):
        self.salt = secrets.token_bytes(16)

    def pseudonyme(self, kind, value):
        return hmac.new(self.salt, f"{kind}:{value.lower()}".encode("utf-8", "replace"), hashlib.sha256).hexdigest()[:6]

    def _ip(self, m):
        text = m.group(0)
        try:
            address = ipaddress.ip_address(text)
        except ValueError:
            return text
        if address.is_loopback or address.is_unspecified or text.startswith("255."):
            return text
        return "IP-" + self.pseudonyme("ip", str(address))

    def __call__(self, text):
        text = FALLBACK_MAIL_RE.sub(lambda m: "usager-" + self.pseudonyme("mail", m.group(0).replace("%40", "@")) + "@anonyme.invalid", text)
        text = FALLBACK_IPV4_RE.sub(self._ip, text)
        return FALLBACK_IPV6_RE.sub(self._ip, text)


class Recorder:
    """Recording of one test. start() then add(line, category) for each line of the stream, stop() at the end (in the background: `done(result)` is called
    with the result; wait=True: in the calling thread, for Ctrl-C). `query(base, sql)` -> rows or None (apps/_odoo_db.py _requete: read-only);
    `databases()` -> names of the Odoo databases; `log_files`: files read from their size at the start; `service` / `namespace`: systemd journal of the window.
    `mask`: callable text -> text (the Anonymiseur of app-log-live.py); None: FallbackMask."""

    def __init__(self, folder, label="", mask=None, query=None, databases=None, service=None, namespace=None, log_files=(), odoo_conf=None,
                 max_seconds=MAX_SECONDS_DEFAULT, max_bytes=STREAM_MAX_BYTES, sample_s=SAMPLE_S, program="app-log-live.py", version="",
                 versions=None, run=None, owner=None, ports=None, app="odoo", filters=""):
        self.folder, self.label, self.slug = folder, (label or "").strip(), slug(label)
        self.mask_names = mask or FallbackMask()
        self.query, self.databases = query, databases
        self.service, self.namespace, self.odoo_conf = service, namespace, odoo_conf
        self.log_files = [f for f in dict.fromkeys(log_files or ()) if f]
        self.max_seconds, self.max_bytes, self.sample_s = max_seconds, max_bytes, max(1.0, float(sample_s))
        self.program, self.version, self.versions = program, version, dict(versions or {})
        self.run = run or _run
        self.owner = owner if owner is not None else sudo_owner()
        self.ports = ports or {}
        self.app, self.filters = app, filters
        self.token_salt = secrets.token_bytes(16)
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.counts = {c: 0 for c in CATEGORIES}
        self.bytes = 0
        self.notes = []                       # sources missing or cut, said in README.txt
        self.steps = []                       # 1.1: steps of the test (N key): dicts n, description, start, end
        self.open_step = None                 # 1.1: the step being recorded, if any
        self.t0 = self.t1 = None
        self.work = self.base_name = None
        self.files = {}
        self.offsets = []
        self.sampler = self.finisher = None
        self._counters = {}                                # 1.2: last PostgreSQL write counters per base (db/writes-BASE.log)
        self.result = None
        self.stopping = False

    # --- masking --------------------------------------------------------------------------------------------------------------------------------
    def _token(self, value):
        return "tok-" + hmac.new(self.token_salt, value.encode("utf-8", "replace"), hashlib.sha256).hexdigest()[:6]

    def mask(self, text):
        """Text as written in the archive: tokens first (a token may look like an address part), then addresses, e-mails and names."""
        if not text:
            return text
        try:
            text = SURVEY_PATH_RE.sub(lambda m: m.group(1) + self._token(m.group(2)) + ("/" + self._token(m.group(3)) if m.group(3) else ""), text)
            text = TOKEN_PARAM_RE.sub(lambda m: m.group(1) + self._token(m.group(2)), text)
            text = UUID_RE.sub(lambda m: self._token(m.group(0)), text)
            text = LONG_HEX_RE.sub(lambda m: self._token(m.group(0)), text)
            return self.mask_names(text)
        except Exception:                                    # noqa: BLE001 — a masking error must never leave a real value: the line is dropped
            return "(line not written: masking failed)"

    def mask_sql(self, text):
        return self.mask(SQL_LITERAL_RE.sub("'?'", text or ""))

    # --- files of the work folder ---------------------------------------------------------------------------------------------------------------
    def _open(self, relative):
        path = os.path.join(self.work, relative)
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0), 0o600)
        return os.fdopen(fd, "a", encoding="utf-8", errors="replace")

    def _write(self, relative, text):
        with self.lock:
            f = self.files.get(relative)
            if f is None:
                f = self.files[relative] = self._open(relative)
            f.write(text)

    def _prepare_folder(self):
        """Folder of the archives (0700); refuses a symbolic link (a folder in another person's home, written by root)."""
        if os.path.islink(self.folder):
            raise OSError(f"{self.folder} is a symbolic link")
        os.makedirs(self.folder, mode=0o700, exist_ok=True)
        if self.owner and os.geteuid() == 0:
            parent = os.path.dirname(self.folder.rstrip("/"))
            try:
                if os.stat(parent).st_uid == self.owner[0] and os.stat(self.folder).st_uid == 0:
                    os.chown(self.folder, *self.owner)        # ~USER/app-log-live-records created by root: given to USER
            except OSError:
                pass

    # --- start ------------------------------------------------------------------------------------------------------------------------------------
    def start(self):
        """Creates the work folder, notes the size of each log file and starts the samples (in the background). OSError: nothing started."""
        self._prepare_folder()
        free = shutil.disk_usage(self.folder).free
        if free < DISK_MIN_BYTES:
            raise OSError(f"only {free // (1024 * 1024)} MB free in {self.folder}")
        # 1.2: PostgreSQL samples are MANDATORY: without them the archive cannot show the writes and the locks (the recording is refused)
        if self.query is None:
            raise OSError("the recording needs the Odoo database (PostgreSQL samples): no access to it")
        if shutil.which("psql") is None:
            raise OSError("the recording needs psql (PostgreSQL client): install postgresql-client")
        bases = self._bases()
        if not bases:
            raise OSError("the recording needs an Odoo database to sample: none found")
        if self.query(bases[0], "SELECT 1") is None:
            raise OSError("PostgreSQL unreachable: « sudo -n -u postgres psql » failed (check the sudoers rules of this account)")
        self.t0 = time.time()
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(self.t0))
        host = slug(socket.gethostname().split(".")[0], 30) or "server"
        self.base_name = f"{ARCHIVE_PREFIX}-{host}-{stamp}" + (f"-{self.slug}" if self.slug else "")
        self.work = tempfile.mkdtemp(prefix=".work-" + self.base_name + "-", dir=self.folder)
        for path in self.log_files:
            try:
                st = os.stat(path)
                self.offsets.append((path, st.st_ino, st.st_size))
            except OSError:
                self.offsets.append((path, None, 0))
        self._write("records.log", f"# {self.program} v{self.version} — recording started {self._local(self.t0)} ({self._utc(self.t0)})"
                                   + (f" — label: {self.label}" if self.label else "") + "\n")
        self.sampler = threading.Thread(target=self._sample_loop, daemon=True, name="record-sampler")
        self.sampler.start()
        return self

    @staticmethod
    def _local(t):
        return time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(t))

    @staticmethod
    def _utc(t):
        return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    def elapsed(self):
        return (self.t1 or time.time()) - self.t0 if self.t0 else 0.0

    def limit_reason(self):
        """'duration' / 'size' when a limit is reached (the program then stops the recording), otherwise None."""
        if self.t0 is None or self.stopping:
            return None
        if self.max_seconds and self.elapsed() >= self.max_seconds:
            return "duration"
        if self.max_bytes and self.bytes >= self.max_bytes:
            return "size"
        return None

    def add(self, line, category="kept"):
        """One line of the stream (without colors). Category: kept (records.log and stream-all.log) or a noise category (stream-all.log only)."""
        if self.t0 is None or self.stopping or self.bytes >= self.max_bytes:
            return
        category = category if category in CATEGORIES else "kept"
        text = self.mask(line.rstrip("\n"))
        stamp = time.strftime("%H:%M:%S", time.localtime())
        with self.lock:
            self.counts[category] += 1
        self._write("stream-all.log", f"{stamp} [{category}] {text}\n")
        size = len(text) + 20
        if category == "kept":
            self._write("records.log", text + "\n")
            size += len(text) + 1
        with self.lock:
            self.bytes += size

    # --- 1.1: steps of the test (N key): a description marks the start and the end of one action of the test ------------------------------------
    @staticmethod
    def _hms(t):
        return time.strftime("%H:%M:%S", time.localtime(t))

    def step_start(self, description):
        """Opens step N with a description (an open step is closed first). Returns N; None when no recording is running."""
        if self.t0 is None or self.stopping:
            return None
        if self.open_step is not None:
            self.step_end()
        text = " ".join((description or "").split())[:200] or "(no description)"
        with self.lock:
            step = {"n": len(self.steps) + 1, "description": self.mask(text), "start": time.time(), "end": None}
            self.steps.append(step)
            self.open_step = step
        self._step_line("START", step)
        return step["n"]

    def step_end(self, reason="key"):
        """Closes the open step. Returns its number; None when no step is open."""
        with self.lock:
            step, self.open_step = self.open_step, None
            if step is None:
                return None
            step["end"] = time.time()
        self._step_line("END", step, reason)
        return step["n"]

    def _step_line(self, kind, step, reason="key"):
        now = time.time()
        if kind == "START":
            text = f"STEP {step['n']} START {self._hms(now)} — {step['description']}"
        else:
            text = f"STEP {step['n']} END {self._hms(now)} — {now - step['start']:.0f} s — {step['description']}"
            if reason != "key":
                text += f" ({reason})"
        self._write("stream-all.log", f"{self._hms(now)} [step] {text}\n")
        self._write("records.log", f"# {text}\n")

    def _steps_text(self):
        out = ["# Étapes du test (touche N) / Steps of the test (N key)",
               "# n  début / start    fin / end        durée / duration   description"]
        for s in self.steps:
            end = self._hms(s["end"]) if s["end"] else "(ouverte / open)"
            duration = (s["end"] or time.time()) - s["start"]
            out.append(f"{s['n']:>3}  {self._hms(s['start'])}       {end:<19}{duration:>8.0f} s          {s['description']}")
        if not self.steps:
            out.append("# (aucune étape / no step)")
        return "\n".join(out) + "\n"

    # --- samples (network, PostgreSQL) --------------------------------------------------------------------------------------------------------------
    def _sample_loop(self):
        try:
            self._write_context()
            self._snapshot("start")
        except Exception as e:                               # noqa: BLE001 — a failed source is noted, never fatal
            self.notes.append(f"start snapshot failed: {e}")
        while not self.stop_event.is_set():
            started = time.time()
            try:
                self._sample()
            except Exception as e:                           # noqa: BLE001
                self.notes.append(f"sample failed: {e}")
            self.stop_event.wait(max(0.5, self.sample_s - (time.time() - started)))

    def _web_ports(self):
        ports = {"80", "443"}
        for key in ("http_port", "gevent_port"):
            if self.ports.get(key):
                ports.add(str(self.ports[key]))
        return ports

    def _sample(self):
        stamp = time.strftime("%H:%M:%S")
        code, out = self.run(["ss", "-Htanp"], 10)
        if code == 0:
            ports, rows, per_port = self._web_ports(), [], {}
            for line in out.splitlines():
                cols = line.split()
                if len(cols) < 5:
                    continue
                local_port, peer_port = cols[3].rsplit(":", 1)[-1], cols[4].rsplit(":", 1)[-1]
                if local_port in ports or peer_port == "5432" or local_port == "5432":
                    rows.append(line)
                    if cols[0] == "ESTAB":
                        key = local_port if local_port in ports or local_port == "5432" else "5432"
                        per_port[key] = per_port.get(key, 0) + 1
            self._write("network/ss.log", f"=== {stamp} ({len(rows)} connection(s))\n" + "".join(self.mask(r) + "\n" for r in rows))
            self._write("network/summary.tsv", stamp + "\t" + "\t".join(f"{p}={n}" for p, n in sorted(per_port.items())) + "\n")
        elif "ss" not in " ".join(self.notes):
            self.notes.append("network samples: ss unavailable")
        if self.query is None:
            return
        for base in self._bases():
            rows = self.query(base, "SELECT pid, COALESCE(application_name, ''), COALESCE(state, ''), COALESCE(wait_event_type, ''), "
                                    "COALESCE(round(extract(epoch FROM now() - xact_start))::text, ''), COALESCE(round(extract(epoch FROM now() - query_start))::text, ''), "
                                    "left(replace(replace(query, E'\\n', ' '), E'\\r', ' '), 400) "
                                    "FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid() ORDER BY xact_start NULLS LAST")
            if rows is None:
                if "PostgreSQL" not in " ".join(self.notes):
                    self.notes.append("PostgreSQL samples: unreachable (psql missing or not root)")
                return
            self._write(f"db/activity-{base}.log", f"=== {stamp} ({len(rows)} connection(s)) pid · application · state · wait · transaction age s · query age s · query\n"
                        + "".join(" · ".join(r[:6]) + " · " + self.mask_sql(r[6] if len(r) > 6 else "")[:200] + "\n" for r in rows))
            locks = self.query(base, "SELECT l.pid, l.mode, l.granted FROM pg_locks l JOIN pg_class c ON c.oid = l.relation WHERE c.relname = 'ir_cron'")
            if locks:
                self._write(f"db/cron-locks-{base}.log", f"=== {stamp} " + " ; ".join("pid " + " ".join(r) for r in locks) + "\n")
            counters = self.query(base, "SELECT relname, n_tup_ins + n_tup_upd + n_tup_del FROM pg_stat_user_tables WHERE relname IN (" + ", ".join(f"'{t}'" for t in TABLES) + ")")
            if counters is not None:                         # 1.2: writes per table since the previous sample (cumulative counters of PostgreSQL)
                now_values = {r[0]: int(r[1] or 0) for r in counters}
                before = self._counters.get(base)
                self._counters[base] = now_values
                if before is not None:
                    moved = [f"{t} +{now_values[t] - before.get(t, 0)}" for t in sorted(now_values) if now_values[t] != before.get(t, now_values[t])]
                    self._write(f"db/writes-{base}.log", f"=== {stamp} " + (" · ".join(moved) if moved else "no write") + "\n")

    def _bases(self):
        try:
            names = list(self.databases() if callable(self.databases) else (self.databases or []))
        except Exception:                                    # noqa: BLE001
            names = []
        return [b for b in names if re.fullmatch(r"[\w.-]+", b or "")]

    # --- context and database snapshots ------------------------------------------------------------------------------------------------------------
    def _write_context(self):
        lines = [f"program: {self.program} v{self.version}", f"server: {socket.gethostname()}", f"system: {self._os_name()}",
                 f"python: {platform.python_version()}", f"application profile: {self.app}", f"display filters at start: {self.filters or 'none'}",
                 f"recording started: {self._local(self.t0)} / {self._utc(self.t0)}"]
        lines += [f"component {k}: {v}" for k, v in sorted(self.versions.items())]
        self._write("context/program.txt", "\n".join(lines) + "\n")
        self._write("context/system.txt", self._system_text())
        if self.service:
            code, out = self.run(["systemctl", "show", self.service, "--no-pager", "-p",
                                  "ActiveState,SubState,TimeoutStopUSec,TimeoutStartUSec,KillMode,KillSignal,Restart,User,MainPID,ActiveEnterTimestamp"], 10)
            self._write("context/service.txt", f"systemctl show {self.service}\n" + (out if code == 0 else "(unavailable)\n"))
        if self.odoo_conf:
            self._write("context/odoo-conf.txt", self._odoo_conf_text())
        watched = []
        for path, inode, size in self.offsets:
            watched.append(f"{path}\t{'missing or unreadable' if inode is None else f'{size} bytes at start'}")
        self._write("context/log-files.txt", "\n".join(watched) + "\n" if watched else "(no log file given)\n")
        if self.query is None:
            return
        for base in self._bases():
            rows = self.query(base, "SELECT name, state, COALESCE(latest_version, '') FROM ir_module_module WHERE name IN ("
                                    + ", ".join(f"'{m}'" for m in MODULES_OF_INTEREST) + ") OR name LIKE 'rlq%' ORDER BY name")
            if rows is not None:
                self._write(f"context/modules-{base}.txt", "name · state · version\n" + "".join(" · ".join(r) + "\n" for r in rows))

    def _system_text(self):
        """1.2: who runs the recording and with which tools: root or not, sudo, OS, kernel, Python, PostgreSQL client and the other tools (no user name)."""
        uid = os.geteuid()
        lines = [f"uid: {uid} ({'root' if uid == 0 else 'not root'})"]
        if uid != 0:
            if shutil.which("sudo") is None:
                lines.append("sudo: not installed")
            else:
                lines.append("sudo -n: " + ("usable without password" if _tool_code(["sudo", "-n", "true"]) == 0 else "refused without password (check sudoers)"))
        lines.append(f"os: {self._os_name()}")
        uname = os.uname()
        lines.append(f"kernel: {uname.sysname} {uname.release} {uname.machine}")
        lines.append(f"python: {platform.python_version()}")
        for name, cmd in TOOL_VERSIONS:
            first = _tool_first_line(cmd) if shutil.which(cmd[0]) else None
            lines.append(f"{name}: {first or 'not installed'}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _os_name():
        try:
            with open("/etc/os-release", encoding="utf-8", errors="replace") as f:
                m = re.search(r'^PRETTY_NAME="?([^"\n]*)', f.read(), re.M)
            return m.group(1) if m else platform.platform()
        except OSError:
            return platform.platform()

    def _odoo_conf_text(self):
        """Whitelisted keys only (no password, no secret, no database host): `ODOO_CONF_KEYS`."""
        values = {}
        try:
            with open(self.odoo_conf, encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = re.match(r"^\s*([\w.]+)\s*=\s*(.*?)\s*$", line)
                    if m and m.group(1) in ODOO_CONF_KEYS:
                        values[m.group(1)] = m.group(2).split("#", 1)[0].strip()
        except OSError as e:
            return f"{self.odoo_conf}: unreadable ({e.strerror})\n"
        return f"{self.odoo_conf} (keys kept: {', '.join(ODOO_CONF_KEYS)})\n" + "".join(f"{k} = {v}\n" for k, v in sorted(values.items()))

    def _columns(self, base, table):
        rows = self.query(base, f"SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = '{table}' ORDER BY ordinal_position")
        return [r[0] for r in rows or []]

    def _select(self, base, table, candidates, tail, columns):
        """SELECT of the candidate columns that exist in `table` (Odoo versions differ): (rows, columns used); (None, []) when none exists."""
        present = [c for c in candidates if c in columns]
        if not present:
            return None, []
        rows = self.query(base, f"SELECT {', '.join(present)} FROM {table} {tail}")
        return rows, present

    def _snapshot(self, phase):
        """db/PHASE-BASE.txt: counters, dates, identifiers and states — never a name, an e-mail or a text typed by a visitor."""
        if self.query is None:
            return
        for base in self._bases():
            exists = self.query(base, "SELECT " + ", ".join(f"to_regclass('public.{t}') IS NOT NULL" for t in TABLES))
            if not exists:
                self.notes.append(f"database {base}: unreadable for the {phase} snapshot")
                continue
            present = {t for t, v in zip(TABLES, exists[0]) if v in ("t", "true")}
            columns = {t: self._columns(base, t) for t in sorted(present)}
            out = [f"# {phase} snapshot of {base} — {self._local(time.time())} ({self._utc(time.time())}); Odoo dates are in UTC", ""]

            def expression(table, column, sql):
                """`sql` (an expression on `column`) offered as a candidate only when the column exists."""
                return [sql] if column in columns.get(table, []) else []

            def section(title, rows, header=None):
                out.append(f"## {title}")
                if rows is None:
                    out.append("(unavailable)")
                elif not rows:
                    out.append("(none)")
                else:
                    if header:
                        out.append(" · ".join(header))
                    out.extend(self.mask(" · ".join(r)) for r in rows)
                out.append("")

            q = self.query
            if "survey_user_input" in present:
                section("survey_user_input per state: state · count · last write (UTC) · written in the last 30 min",
                        q(base, f"SELECT state, count(*), COALESCE(max(write_date)::text, ''), count(*) FILTER (WHERE write_date > {NOW_UTC} - interval '30 minutes') "
                                "FROM survey_user_input GROUP BY state ORDER BY state"))
                rows, cols = self._select(base, "survey_user_input i", [c for c in ("id", "survey_id", "state", "create_date", "write_date", "start_datetime",
                                                                                    "end_datetime", "last_displayed_page_id", "deadline")
                                                                        if c in columns["survey_user_input"]],
                                          f"WHERE write_date > {NOW_UTC} - interval '2 hours' ORDER BY write_date DESC LIMIT 50", columns["survey_user_input"])
                section("survey answers written in the last 2 hours", rows, cols)
            if "survey_survey" in present:
                rows, cols = self._select(base, "survey_survey", ("id", "active", "questions_layout", "is_time_limited", "time_limit", "access_mode",
                                                                  "users_login_required", "is_attempts_limited")
                                          + tuple(expression("survey_survey", "title", "left(title::text, 80)")),
                                          "ORDER BY id DESC LIMIT 30", columns["survey_survey"] + expression("survey_survey", "title", "left(title::text, 80)"))
                section("surveys (layout: one page per question / section / all on one page)", rows, cols)
            if "event_registration" in present:
                section("event_registration: last id · count · created in the last 2 hours · last creation (UTC)",
                        q(base, f"SELECT COALESCE(max(id)::text, ''), count(*), count(*) FILTER (WHERE create_date > {NOW_UTC} - interval '2 hours'), "
                                "COALESCE(max(create_date)::text, '') FROM event_registration"))
                rows, cols = self._select(base, "event_registration", ("id", "event_id", "event_ticket_id", "state", "create_date", "write_date"),
                                          "ORDER BY id DESC LIMIT 20", columns["event_registration"])
                section("last 20 registrations", rows, cols)
            if "event_mail" in present:
                rows, cols = self._select(base, "event_mail", ("id", "event_id", "interval_nbr", "interval_unit", "interval_type", "notification_type",
                                                               "template_ref", "scheduled_date", "mail_done", "mail_state", "mail_count_done", "error_datetime", "write_date"),
                                          f"WHERE scheduled_date IS NULL OR scheduled_date > {NOW_UTC} - interval '30 days' ORDER BY scheduled_date DESC NULLS LAST LIMIT 40",
                                          columns["event_mail"])
                section("event_mail (scheduled communications of the events, 30 days)", rows, cols)
                ids = sorted({int(m.group(1)) for r in rows or [] for v in r for m in [re.fullmatch(r"mail\.template,(\d+)", v)] if m})
                if ids and "mail_template" in present:
                    section("templates of these communications: id · contains a /survey/ link · name",
                            q(base, "SELECT id, (body_html::text ILIKE '%/survey/%'), left(name::text, 80) FROM mail_template WHERE id IN ("
                                    + ", ".join(str(i) for i in ids) + ") ORDER BY id"))
            if "mail_mail" in present:
                joined = "mail_message" in present and "mail_message_id" in columns["mail_mail"]
                join = "LEFT JOIN mail_message g ON g.id = m.mail_message_id" if joined else ""
                model = "COALESCE(g.model, '')" if joined else "''"
                section("mail_mail (e-mail queue): state · model · count · last write (UTC)",
                        q(base, f"SELECT m.state, {model}, count(*), COALESCE(max(m.write_date)::text, '') FROM mail_mail m {join} GROUP BY 1, 2 ORDER BY 1, 2"))
            if "crm_lead" in present:
                section("crm_lead: last id · count · created in the last 2 hours · last creation (UTC)",
                        q(base, f"SELECT COALESCE(max(id)::text, ''), count(*), count(*) FILTER (WHERE create_date > {NOW_UTC} - interval '2 hours'), "
                                "COALESCE(max(create_date)::text, '') FROM crm_lead"))
            if "event_track" in present:
                rows, cols = self._select(base, "event_track", ("id", "event_id", "stage_id", "create_date", "write_date"), "ORDER BY id DESC LIMIT 10", columns["event_track"])
                section("last 10 event_track (talk proposals)", rows, cols)
            if "document_page" in present:
                rows, cols = self._select(base, "document_page", ("id", "type", "write_date", "write_uid") + tuple(expression("document_page", "name", "left(name::text, 60)")),
                                          "ORDER BY write_date DESC NULLS LAST LIMIT 10", columns["document_page"] + expression("document_page", "name", "left(name::text, 60)"))
                section("wiki: last 10 pages written", rows, cols)
            if "document_page_history" in present:
                rows, cols = self._select(base, "document_page_history", ("id", "page_id", "create_date", "create_uid"), "ORDER BY id DESC LIMIT 10",
                                          columns["document_page_history"])
                section("wiki: last 10 history entries", rows, cols)
            if "ir_ui_view" in present and "website_id" in columns["ir_ui_view"]:
                rows, cols = self._select(base, "ir_ui_view", ("id", "key", "website_id", "write_date", "write_uid"),
                                          "WHERE website_id IS NOT NULL ORDER BY write_date DESC NULLS LAST LIMIT 10", columns["ir_ui_view"])
                section("website views (website_id set): last 10 written", rows, cols)
            if "website_page" in present:
                rows, cols = self._select(base, "website_page", ("id", "url", "write_date", "write_uid"), "ORDER BY write_date DESC NULLS LAST LIMIT 10", columns["website_page"])
                section("website pages: last 10 written", rows, cols)
            if "ir_attachment" in present:
                section("attachments created in the last 2 hours: model · count · last creation (UTC)",
                        q(base, f"SELECT COALESCE(res_model, ''), count(*), COALESCE(max(create_date)::text, '') FROM ir_attachment "
                                f"WHERE create_date > {NOW_UTC} - interval '2 hours' GROUP BY 1 ORDER BY 2 DESC LIMIT 20"))
            if "website_visitor" in present and "last_connection_datetime" in columns["website_visitor"]:
                section("website visitors: seen in the last 30 min · last visit (UTC)",
                        q(base, f"SELECT count(*) FILTER (WHERE last_connection_datetime > {NOW_UTC} - interval '30 minutes'), "
                                "COALESCE(max(last_connection_datetime)::text, '') FROM website_visitor"))
            if "website_track" in present:
                rows, cols = self._select(base, "website_track", ("visit_datetime", "page_id") + tuple(expression("website_track", "url", "left(url, 160)")),
                                          f"WHERE visit_datetime > {NOW_UTC} - interval '30 minutes' ORDER BY visit_datetime DESC LIMIT 30",
                                          columns["website_track"] + expression("website_track", "url", "left(url, 160)"))
                section("pages tracked in the last 30 min", rows, cols)
            for presence_table in ("mail_presence", "bus_presence"):
                if presence_table in present and "status" in columns[presence_table]:
                    section(f"{presence_table}: status · count", q(base, f"SELECT status, count(*) FROM {presence_table} GROUP BY 1 ORDER BY 1"))
            if "res_users_log" in present:
                section("sign-ins in the last 2 hours (res_users_log)", q(base, f"SELECT count(*) FROM res_users_log WHERE create_date > {NOW_UTC} - interval '2 hours'"))
            if "ir_cron" in present:
                rows, cols = self._select(base, "ir_cron", ("id", "cron_name", "active", "interval_number", "interval_type", "nextcall", "lastcall", "priority",
                                                            "failure_count", "first_failure_date"),
                                          "WHERE active ORDER BY nextcall", columns["ir_cron"])
                section("active scheduled actions (ir_cron), next call first", rows, cols)
            self._write(f"db/{phase}-{base}.txt", "\n".join(out) + "\n")
            if phase == "start":
                self._write(f"db/schema-{base}.txt", "".join(f"{t}: {', '.join(c)}\n" for t, c in columns.items()))

    # --- stop -------------------------------------------------------------------------------------------------------------------------------------
    def stop(self, reason="key", done=None, wait=False):
        """Ends the recording: last samples, raw extracts, journal, README.txt, archive. In the background (done(result) at the end), or right here (wait=True).
        result: {'path', 'size', 'seconds', 'counts', 'reason', 'notes', 'error'}."""
        if self.t0 is None or self.stopping:
            return self.result
        self.stopping = True
        self.t1 = time.time()
        self.stop_event.set()

        def finish():
            try:
                self.result = self._finish(reason)
            except Exception as e:                           # noqa: BLE001
                self.result = {"path": None, "size": 0, "seconds": self.elapsed(), "counts": dict(self.counts), "reason": reason,
                               "notes": list(self.notes), "error": str(e) or e.__class__.__name__}
                shutil.rmtree(self.work, ignore_errors=True)
            if done is not None:
                done(self.result)
        if wait:
            finish()
            return self.result
        self.finisher = threading.Thread(target=finish, daemon=True, name="record-finish")
        self.finisher.start()
        return None

    def join(self, timeout=None):
        if self.finisher is not None:
            self.finisher.join(timeout)
        return self.result

    def _finish(self, reason):
        if self.open_step is not None:
            self.step_end("recording stopped")
        if self.sampler is not None:
            self.sampler.join(30)
        try:
            self._snapshot("end")
        except Exception as e:                               # noqa: BLE001
            self.notes.append(f"end snapshot failed: {e}")
        self._raw_extracts()
        self._journal_extract()
        self._write("records.log", f"# recording stopped {self._local(self.t1)} ({self._utc(self.t1)}) — {self.elapsed():.0f} s — reason: {reason}\n")
        self._write("steps.txt", self._steps_text())
        self._write("README.txt", self._readme(reason))
        with self.lock:
            for f in self.files.values():
                f.close()
            self.files.clear()
        final = os.path.join(self.folder, self.base_name + ".tar.xz")
        temporary = final + ".part"
        with tarfile.open(temporary, "w:xz", preset=6) as tar:
            for name in ("README.txt", "records.log", "stream-all.log", "steps.txt", "raw", "network", "db", "context"):
                path = os.path.join(self.work, name)
                if os.path.exists(path):
                    tar.add(path, arcname=os.path.join(self.base_name, name))
        os.chmod(temporary, 0o600)
        os.replace(temporary, final)
        if self.owner and os.geteuid() == 0:
            try:
                os.chown(final, *self.owner)
            except OSError:
                pass
        shutil.rmtree(self.work, ignore_errors=True)
        return {"path": final, "size": os.path.getsize(final), "seconds": self.elapsed(), "counts": dict(self.counts), "reason": reason,
                "notes": list(self.notes), "error": None}

    def _read_window(self, path, inode, offset):
        """New content of a log file since the start. Rotated during the recording (other inode): the end of the old file (path.1) then the new file whole."""
        chunks = []
        try:
            st = os.stat(path)
        except OSError:
            return None, "missing at the end"
        note = ""
        if inode is not None and st.st_ino != inode:
            old = path + ".1"
            try:
                if os.stat(old).st_ino == inode:
                    chunks.append((old, offset))
                    note = "rotated during the recording (end of .1, then the new file)"
                else:
                    note = "rotated during the recording (old part not found)"
            except OSError:
                note = "rotated during the recording (old part not found)"
            chunks.append((path, 0))
        else:
            chunks.append((path, offset if inode is not None and st.st_size >= offset else 0))
        data, cut = [], False
        left = RAW_MAX_BYTES
        for name, start in chunks:
            try:
                with open(name, "rb") as f:
                    f.seek(start)
                    block = f.read(left + 1)
            except OSError as e:
                return None, f"unreadable ({e.strerror})"
            if len(block) > left:
                block, cut = block[:left], True
            data.append(block)
            left -= len(block)
            if left <= 0:
                break
        if cut:
            note = (note + "; " if note else "") + f"cut at {RAW_MAX_BYTES // (1024 * 1024)} MB"
        return b"".join(data).decode("utf-8", "replace"), note

    def _raw_extracts(self):
        used = set()
        for path, inode, offset in self.offsets:
            text, note = self._read_window(path, inode, offset)
            name = os.path.basename(path)
            while name in used:
                name = "_" + name
            used.add(name)
            if text is None:
                self.notes.append(f"{path}: {note}")
                continue
            if note:
                self.notes.append(f"{path}: {note}")
            self._write(f"raw/{name}", "".join(self.mask(line) + "\n" for line in text.splitlines()))

    def _journal_extract(self):
        if not self.service:
            return
        cmd = privileged(["journalctl", "-u", self.service, "--no-pager", "-q", "-o", "short-iso-precise", "--since", f"@{int(self.t0)}", "--until", f"@{int(self.t1) + 1}"])
        if self.namespace:
            cmd += ["--namespace", self.namespace]
        code, out = self.run(cmd, 120)
        if code != 0 and not out:
            self.notes.append("systemd journal of the window: unavailable (journalctl)")
            return
        lines = out.splitlines()
        size, kept = 0, []
        for line in lines:
            size += len(line) + 1
            if size > RAW_MAX_BYTES:
                self.notes.append(f"systemd journal: cut at {RAW_MAX_BYTES // (1024 * 1024)} MB")
                break
            kept.append(self.mask(line) + "\n")
        self._write(f"raw/journal-{slug(self.service, 60) or 'service'}.log", "".join(kept))

    def _readme(self, reason):
        counts = self.counts
        noise = sum(v for k, v in counts.items() if k != "kept")
        reasons_fr = {"key": "touche R", "duration": "durée maximale atteinte", "size": "taille maximale atteinte", "end": "fin du programme",
                      "interrupt": "Ctrl+C", "test-log": "fin de --record-test-log"}
        reasons_en = {"key": "R key", "duration": "maximum duration reached", "size": "maximum size reached", "end": "end of the program",
                      "interrupt": "Ctrl+C", "test-log": "end of --record-test-log"}
        notes = self.notes or []
        fr = [
            "ENREGISTREMENT D'UN TEST — app-log-live.py",
            "=" * 60,
            f"Étiquette        : {self.label or '(aucune)'}",
            f"Début            : {self._local(self.t0)}  ({self._utc(self.t0)})",
            f"Fin              : {self._local(self.t1)}  ({self._utc(self.t1)})",
            f"Durée            : {self.elapsed():.0f} s — arrêt : {reasons_fr.get(reason, reason)}",
            f"Étapes           : {len(self.steps)} (steps.txt)",
            f"Serveur          : {socket.gethostname()} — {self._os_name()}",
            f"Programme        : {self.program} v{self.version} (composant _record.py v{__version__})",
            f"Lignes           : {counts['kept']} gardées (records.log) ; {noise} de bruit retirées (robots {counts['robot']}, fichiers statiques {counts['static']}, "
            f"websockets {counts['websocket']}, sondes locales {counts['local']}) — toutes dans stream-all.log",
            "Confidentialité  : adresses IP, courriels, noms connus et jetons remplacés par des pseudonymes stables (les mêmes dans tous les fichiers) ;",
            "                   littéraux SQL remplacés par '?' ; aucune donnée personnelle lue dans la base (compteurs, dates, identifiants, états).",
            "",
            "Contenu :",
            "  records.log     les lignes du test, sans le bruit",
            "  steps.txt       les étapes marquées avec la touche N (début, fin, durée, description)",
            "  stream-all.log  toutes les lignes, avec leur catégorie",
            "  raw/            extraits complets des journaux pendant la fenêtre (nginx, fail2ban, Odoo, journal systemd du service)",
            "  network/        connexions TCP des ports web et d'Odoo toutes les " + f"{self.sample_s:g} s (ss), et leur compte par port",
            "  db/             activité PostgreSQL et verrous sur ir_cron toutes les " + f"{self.sample_s:g} s ; instantanés de début et de fin ; colonnes des tables",
            "  context/        réglages du service, configuration d'Odoo (sans secret), modules, journaux surveillés",
            "Sources absentes ou coupées : " + ("; ".join(notes) if notes else "aucune"),
        ]
        en = [
            "TEST RECORDING — app-log-live.py",
            "=" * 60,
            f"Label            : {self.label or '(none)'}",
            f"Start            : {self._local(self.t0)}  ({self._utc(self.t0)})",
            f"End              : {self._local(self.t1)}  ({self._utc(self.t1)})",
            f"Duration         : {self.elapsed():.0f} s — stopped by: {reasons_en.get(reason, reason)}",
            f"Steps            : {len(self.steps)} (steps.txt)",
            f"Server           : {socket.gethostname()} — {self._os_name()}",
            f"Program          : {self.program} v{self.version} (component _record.py v{__version__})",
            f"Lines            : {counts['kept']} kept (records.log); {noise} noise lines removed (robots {counts['robot']}, static files {counts['static']}, "
            f"websockets {counts['websocket']}, local probes {counts['local']}) — all of them in stream-all.log",
            "Privacy          : IP addresses, e-mails, known names and tokens replaced by stable pseudonyms (the same in every file);",
            "                   SQL literals replaced by '?'; no personal data read from the database (counts, dates, identifiers, states).",
            "",
            "Content:",
            "  records.log     the lines of the test, without the noise",
            "  steps.txt       the steps marked with the N key (start, end, duration, description)",
            "  stream-all.log  every line, with its category",
            "  raw/            complete log extracts of the window (nginx, fail2ban, Odoo, systemd journal of the service)",
            "  network/        TCP connections of the web and Odoo ports every " + f"{self.sample_s:g} s (ss), and their count per port",
            "  db/             PostgreSQL activity and ir_cron locks every " + f"{self.sample_s:g} s; start and end snapshots; columns of the tables",
            "  context/        service settings, Odoo configuration (no secret), modules, watched logs",
            "Missing or cut sources: " + ("; ".join(notes) if notes else "none"),
        ]
        return "\n".join(fr) + "\n\n" + "\n".join(en) + "\n"
