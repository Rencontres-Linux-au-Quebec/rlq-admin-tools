#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# _vpn.py - what hides behind an address: VPN, Tor, relay (iCloud Private Relay, Cloudflare WARP) or hosting provider, guessed from the NAME of
# the owner of its block (RDAP organisation and network name, read by apps/_reseau.py), and whether it is a Tor exit (official list of the Tor
# project, cached one day). Shared by web-monitor.py (accounts) and nginx-log-audit.sh (--investigate). A guess, not a proof: a VPN on a network
# of unknown name is not seen; a data center is the exit of most VPNs, but also of servers rented directly.
#
# Command line (used by nginx-log-audit.sh):
#   _vpn.py IP [--org ORGANISATION] [--net NETWORK] [--no-tor] [--verbose]
#   prints one line: KIND, NAME, TOR (1 or 0), TOR_LIST_DATE (YYYY-MM-DD HH:MM or empty), LABEL - separated by ASCII 31 (\x1f)
#   KIND: VPN, Tor, Relay, Hosting or empty; LABEL: the owner's name to show (the network name when the organisation says nothing, e.g. "Admin").

import argparse
import os
import re
import shutil
import subprocess
import sys
import time

__version__ = "1.1.20261102.230844"

SEP = "\x1f"
# Owner of the block (RDAP organisation and network name) -> (kind, short name; empty: the owner's first word). The first match wins.
# Kinds: VPN, Tor, Relay (iCloud Private Relay, Cloudflare WARP: the user's real address is hidden too), Hosting (data center: the exit of most VPNs
# and proxies - a person does not browse from a data center, a VPN does). Moved from web-monitor.py 2.85 (unchanged).
VPN_OWNERS = (
    (r"nordvpn|tefincom", "VPN", "NordVPN"), (r"surfshark", "VPN", "Surfshark"), (r"expressvpn|express vpn", "VPN", "ExpressVPN"),
    (r"proton ?(ag|vpn|technologies)", "VPN", "Proton"), (r"mullvad|31173 services", "VPN", "Mullvad"), (r"private internet access", "VPN", "PIA"),
    (r"cyberghost", "VPN", "CyberGhost"), (r"ipvanish", "VPN", "IPVanish"), (r"windscribe", "VPN", "Windscribe"), (r"hide\.?me\b|eventure", "VPN", "hide.me"),
    (r"purevpn|gz systems", "VPN", "PureVPN"), (r"torguard|vpnetworks", "VPN", "TorGuard"), (r"vyprvpn|golden frog", "VPN", "VyprVPN"),
    (r"hotspot shield|\bpango\b", "VPN", "HotspotShield"), (r"tunnelbear", "VPN", "TunnelBear"), (r"astrill", "VPN", "Astrill"), (r"airvpn", "VPN", "AirVPN"),
    (r"\bivpn\b|privatus", "VPN", "IVPN"), (r"perfect privacy", "VPN", "PerfectPrivacy"), (r"\bovpn\b", "VPN", "OVPN"), (r"privado", "VPN", "Privado"),
    (r"strongvpn", "VPN", "StrongVPN"), (r"vpn", "VPN", ""),
    (r"torservers|tor[-_ ]?exit|emerald onion|applied privacy|calyx institute|tor project", "Tor", ""),
    (r"private[-_ ]?relay", "Relay", "iCloud"), (r"cloudflare", "Relay", "Cloudflare"), (r"fastly", "Relay", "Fastly"),
    (r"m247", "Hosting", "M247"), (r"datacamp|cdn77", "Hosting", "DataCamp"), (r"packethub", "Hosting", "PacketHub"), (r"clouvider", "Hosting", "Clouvider"),
    (r"zenlayer", "Hosting", "Zenlayer"), (r"leaseweb", "Hosting", "Leaseweb"), (r"\bovh", "Hosting", "OVH"), (r"hetzner", "Hosting", "Hetzner"),
    (r"digitalocean|digital ocean", "Hosting", "DigitalOcean"), (r"amazon|\baws\b", "Hosting", "Amazon"), (r"google (llc|cloud)|google-cloud|googlecloud", "Hosting", "Google"),
    (r"microsoft|azure", "Hosting", "Microsoft"), (r"linode|akamai", "Hosting", "Akamai"), (r"vultr|choopa|constant company", "Hosting", "Vultr"),
    (r"contabo", "Hosting", "Contabo"), (r"scaleway|online s\.?a\.?s", "Hosting", "Scaleway"), (r"hostinger", "Hosting", "Hostinger"), (r"psychz", "Hosting", "Psychz"),
    (r"xtom", "Hosting", "xTom"), (r"tzulo", "Hosting", "Tzulo"), (r"performive", "Hosting", "Performive"), (r"gsl networks", "Hosting", "GSL"),
    (r"datapacket", "Hosting", "DataPacket"), (r"quadranet", "Hosting", "QuadraNet"), (r"colocrossing", "Hosting", "ColoCrossing"), (r"worldstream", "Hosting", "WorldStream"),
    (r"frantech|buyvm|ponynet", "Hosting", "BuyVM"), (r"g-?core", "Hosting", "G-Core"), (r"stark industries", "Hosting", "Stark"), (r"\baeza\b", "Hosting", "Aeza"),
    (r"alibaba|aliyun", "Hosting", "Alibaba"), (r"tencent", "Hosting", "Tencent"), (r"oracle", "Hosting", "Oracle"), (r"ionos|1&1", "Hosting", "IONOS"),
    (r"netcup", "Hosting", "netcup"), (r"hivelocity", "Hosting", "Hivelocity"),
    (r"hosting|hoster|data ?cent(er|re)|datacent|\bvps\b|colocation|server", "Hosting", ""))
VPN_OWNERS_RE = [(re.compile(pattern), kind, name) for pattern, kind, name in VPN_OWNERS]
VPN_PRIORITY = {"VPN": 4, "Tor": 4, "Relay": 2, "Hosting": 1}

# RDAP organisation names that say nothing about the owner (45.138.12.41: organisation "Admin", network TC-DATACENTER-LIMITED).
GENERIC_ORG_RE = re.compile(r"^\W*(admin(istrator)?|abuse|noc|hostmaster|network( operations?)?|support|technical( contact)?|tech|n/?a|none|private|"
                            r"unknown|not disclosed|redacted( for privacy)?|data protected|-+)\W*$", re.I)

TOR_LIST_URL = "https://check.torproject.org/torbulkexitlist"     # official list of the Tor exits (one address per line)
TOR_MAX_AGE_S = 86400                                             # refreshed at most once a day
VERBOSE = False


def owner_label(organisation, network):
    """Name of the owner to show: the organisation, unless it says nothing (GENERIC_ORG_RE, empty), then the network name."""
    organisation, network = (organisation or "").strip(), (network or "").strip()
    if organisation and not GENERIC_ORG_RE.match(organisation):
        return organisation
    return network or organisation


def first_word(organisation, network):
    """Short name of a block owner: first word of the name shown (owner_label), 12 characters at most."""
    words = (owner_label(organisation, network) or "?").replace(",", " ").split()
    return (words[0] if words else "?")[:12]


def kind_of(organisation, network, short=True, abuse=""):
    """(kind, name) of the owner of an address block - VPN, Tor, Relay, Hosting (see VPN_OWNERS) - or None: an access provider (home,
    mobile), a company, a school... A guess from the NAME of the owner, not a proof. Name: the provider's name when known, otherwise the first
    word of the owner (short=True, for a table column) or its whole name (short=False). 1.1: `abuse`, the abuse mailbox of the block, is read too
    (132.196.59.85: organisation "Divya Quamara", network "cloud", abuse@microsoft.com)."""
    text = " ".join(x or "" for x in (organisation, network, abuse)).lower()
    if not text.strip():
        return None
    for pattern, kind, name in VPN_OWNERS_RE:
        if pattern.search(text):
            return kind, name or (first_word(organisation, network) if short else owner_label(organisation, network))
    return None


def tor_cache_path():
    """NGINX_TOOLS_TOR_CACHE, otherwise /var/cache/nginx-tools/tor-exits.txt when writable (root), otherwise ~/.cache/nginx-tools/tor-exits.txt."""
    explicit = os.environ.get("NGINX_TOOLS_TOR_CACHE")
    if explicit:
        return explicit
    system = "/var/cache/nginx-tools"
    try:
        os.makedirs(system, exist_ok=True)
        if os.access(system, os.W_OK):
            return os.path.join(system, "tor-exits.txt")
    except OSError:
        pass
    return os.path.join(os.path.expanduser("~"), ".cache", "nginx-tools", "tor-exits.txt")


def _download(timeout=10):
    """Text of the official list, or "" (curl, otherwise wget; never an exception)."""
    if shutil.which("curl"):
        cmd = ["curl", "-fsSL", "--max-time", str(timeout), TOR_LIST_URL]
    elif shutil.which("wget"):
        cmd = ["wget", "-qO-", "--timeout=%d" % timeout, TOR_LIST_URL]
    else:
        return ""
    if VERBOSE:
        print("+ " + " ".join(cmd), file=sys.stderr)
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=timeout + 2,
                           universal_newlines=True, errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return r.stdout if r.returncode == 0 else ""


def tor_exits(path=None, max_age=TOR_MAX_AGE_S, now=None):
    """(set of Tor exit addresses, date of the list "YYYY-MM-DD HH:MM" or ""). Refreshed when the cache is older than `max_age`; a failed
    download keeps the previous list (an empty set when there is none). Lines that are not addresses are ignored."""
    path = path or tor_cache_path()
    now = time.time() if now is None else now
    try:
        age = now - os.path.getmtime(path)
    except OSError:
        age = None
    if age is None or age > max_age:
        text = _download()
        addresses = [l.strip() for l in text.splitlines() if re.fullmatch(r"[0-9a-fA-F:.]{3,45}", l.strip() or "-")]
        if len(addresses) >= 10:                                   # a real list has hundreds of lines: never replace the cache with an error page
            try:
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                tmp = path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write("\n".join(addresses) + "\n")
                os.replace(tmp, path)
            except OSError:
                pass
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            exits = {l.strip() for l in f if l.strip()}
        date = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
    except OSError:
        return set(), ""
    return exits, date


def main():
    global VERBOSE
    p = argparse.ArgumentParser(prog="_vpn.py", description="VPN, Tor, relay or hosting provider behind an address (guess from the block owner, official Tor list).")
    p.add_argument("ip")
    p.add_argument("--abuse", default="", help="abuse mailbox of the block (RDAP)")
    p.add_argument("--net", default="", help="network name of the block (RDAP)")
    p.add_argument("--no-tor", action="store_true", help="do not read the Tor exit list")
    p.add_argument("--org", default="", help="organisation owning the block (RDAP)")
    p.add_argument("--verbose", action="store_true", help="show the download command")
    p.add_argument("--version", action="version", version="%(prog)s " + __version__)
    a = p.parse_args()
    VERBOSE = a.verbose
    kind = kind_of(a.org, a.net, short=False, abuse=a.abuse)
    tor, date = 0, ""
    if not a.no_tor:
        exits, date = tor_exits()
        tor = 1 if a.ip in exits else 0
    if tor:
        kind = ("Tor", "Tor")
    print(SEP.join((kind[0] if kind else "", kind[1] if kind else "", str(tor), date, owner_label(a.org, a.net))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
