# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# Odoo journal written to a FILE (logfile of its configuration): each line receives the prefix of a systemd journal,
# "2026-10-02T10:07:18.326000-0400 host odoo[PID]: " (Odoo's time, in UTC, is converted to local time). The programs that read
# "journalctl -o short-iso-precise" then work without change. Lines without a time (Python traceback) take the previous prefix.
# Usage: python3 _odoo_journal.py FILE NUMBER_OF_LINES FOLLOW   (NUMBER_OF_LINES: "+1" = whole file; FOLLOW: 1 = tail -F)
import datetime
import re
import socket
import subprocess
import sys

MOTIF = re.compile(r"^(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d),(\d{3}) (\d+) ")


def main(fichier, nombre, suivre):
    hote, prefixe = socket.gethostname(), None
    commande = ["tail", "-n", nombre] + (["-F"] if suivre else []) + [fichier]
    flux = subprocess.Popen(commande, stdout=subprocess.PIPE, text=True, errors="replace", bufsize=1).stdout
    for ligne in flux:
        ligne = ligne.rstrip("\n")
        m = MOTIF.match(ligne)
        if m:
            local = datetime.datetime.strptime(m.group(1) + " " + m.group(2), "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.timezone.utc).astimezone()
            prefixe = f"{local:%Y-%m-%dT%H:%M:%S}.{m.group(3)}000{local:%z} {hote} odoo[{m.group(4)}]: "
        if prefixe is not None:
            print(prefixe + ligne, flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] == "1")
