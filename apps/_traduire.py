#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
# _traduire.py - translates the output of a bash program (shared module, apps/): runs the command and passes its lines through the catalogue lang/PROGRAM.XX.po.
#
"""Usage : _traduire.py PROGRAMME VARIABLE_LANGUE -- COMMANDE [ARGUMENTS…]

Appelé par apps/_i18n.sh (fonction i18n_relancer) tout au début d'un programme bash. La langue se choisit comme pour les programmes Python (apps/_i18n.py) :
--lang, la variable du programme, LANGUAGE du fichier de configuration, LC_ALL / LC_MESSAGES / LANG. En français (langue du code) : la commande REMPLACE ce processus
(exec : rien ne change, ni processus ni sortie). Dans une autre langue : la commande tourne en sous-processus ; sa sortie standard et son erreur standard passent par le
traducteur, ligne par ligne ; une invite sans fin de ligne (« Continuer ? [o/N] ») est traduite après 50 ms de silence. Si la sortie est un terminal, la commande reçoit
un pseudo-terminal de même taille (couleurs, largeur) ; sinon un tube. L'entrée standard n'est pas touchée. Code de retour : celui de la commande.
Variable NGINX_TOOLS_LANG : langue imposée à tous les outils (ex. « fr » quand un programme analyse la sortie d'un autre)."""
import codecs
import fcntl
import importlib.util
import os
import selectors
import signal
import struct
import subprocess
import sys
import termios

__version__ = "1.6.20261022.231529"
DOSSIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUPPLEMENTAIRES = ("_listes", "_profile", "_rapport", "_bbb", "_reseau", "_cache_ip", "_odoo_db")
# Programs whose output contains that of another program (displayed as is): their catalogue is completed with the other's.
AUTRES_CATALOGUES = {"nginx-log-audit": ("sync-crowdsec-blocklist",), "nginx-hardening": ("app-health-check",), "run-all": ("app-health-check",)}
SILENCE = 0.05            # secondes sans rien recevoir avant de traduire une invite sans fin de ligne


def _i18n():
    spec = importlib.util.spec_from_file_location("_i18n", os.path.join(DOSSIER, "apps", "_i18n.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _anonymiser():
    spec = importlib.util.spec_from_file_location("_anonymiser", os.path.join(DOSSIER, "apps", "_anonymiser.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _taille(source, cible):
    """Copie la taille du terminal `source` (descripteur) sur le pseudo-terminal `cible`."""
    try:
        fcntl.ioctl(cible, termios.TIOCSWINSZ, fcntl.ioctl(source, termios.TIOCGWINSZ, struct.pack("HHHH", 0, 0, 0, 0)))
    except OSError:
        pass


class Flux:
    """Une sortie du programme : octets reçus -> lignes traduites écrites sur `destination` (descripteur)."""
    def __init__(self, lecture, destination, tr):
        self.lecture, self.destination, self.tr = lecture, destination, tr
        self.decodeur = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.reste = ""
        self.ouvert = True

    def _ecrire(self, texte):
        donnees = texte.encode("utf-8", "replace")
        while donnees:
            try:
                n = os.write(self.destination, donnees)
            except InterruptedError:
                continue
            donnees = donnees[n:]

    def lire(self):
        try:
            octets = os.read(self.lecture, 65536)
        except OSError:                      # pseudo-terminal : EIO quand le programme a fini
            octets = b""
        if not octets:
            self.ouvert = False
            self.vider()
            return
        self.reste += self.decodeur.decode(octets)
        if "\n" in self.reste:
            complet, _, self.reste = self.reste.rpartition("\n")
            for ligne in complet.split("\n"):
                self._ecrire(self.tr(ligne) + "\n")

    def vider(self):
        """Fin de flux ou silence : traduit et écrit ce qui reste (une invite sans fin de ligne)."""
        if self.reste:
            self._ecrire(self.tr(self.reste))
            self.reste = ""


def lancer(commande, tr, langue, anonymiser=False):
    """Exécute la commande avec sa sortie filtrée ; code de retour de la commande. anonymiser : la commande (et tout ce qu'elle lance) reçoit NGINX_TOOLS_ANON_ACTIF."""
    sorties, enfants, fermer = [], [], []
    try:
        identiques = os.fstat(1).st_ino == os.fstat(2).st_ino and os.fstat(1).st_dev == os.fstat(2).st_dev      # "2>&1": a single pipe, the order of the lines is kept
    except OSError:
        identiques = False
    for numero in ((1,) if identiques else (1, 2)):
        if os.isatty(numero):
            maitre, esclave = os.openpty()
            attr = termios.tcgetattr(esclave)
            attr[1] &= ~termios.OPOST                      # no \n -> \r\n: the real terminal takes care of it
            termios.tcsetattr(esclave, termios.TCSANOW, attr)
            _taille(numero, esclave)
            sorties.append((maitre, numero, True))
            enfants.append(esclave)
        else:
            lecture, ecriture = os.pipe()
            sorties.append((lecture, numero, False))
            enfants.append(ecriture)
        fermer.append(enfants[-1])
    if identiques:
        enfants.append(enfants[0])
    signal.signal(signal.SIGINT, lambda *_: None)          # Ctrl-C also goes to the command (same group): it is the command that decides. A HANDLER (and not SIG_IGN, inherited at exec): the command keeps the normal Ctrl-C behavior
    proc = subprocess.Popen(commande, stdout=enfants[0], stderr=enfants[1], close_fds=True, env=dict(os.environ, NGINX_TOOLS_I18N="1", NGINX_TOOLS_I18N_LANGUE=langue, **({"NGINX_TOOLS_ANON_ACTIF": "1"} if anonymiser else {})))
    for fd in fermer:
        os.close(fd)

    def redimensionner(*_):
        for (maitre, numero, terminal) in sorties:
            if terminal:
                _taille(numero, maitre)
        try:
            proc.send_signal(signal.SIGWINCH)              # the pseudo-terminal is not the control terminal of the command: it would not be warned otherwise
        except OSError:
            pass
    signal.signal(signal.SIGWINCH, redimensionner)
    signal.signal(signal.SIGTERM, lambda *_: proc.send_signal(signal.SIGTERM))
    flux = {lecture: Flux(lecture, numero, tr) for (lecture, numero, _t) in sorties}
    sel = selectors.DefaultSelector()
    for lecture in flux:
        sel.register(lecture, selectors.EVENT_READ)
    fin = None
    while any(f.ouvert for f in flux.values()):
        evenements = sel.select(SILENCE if fin is None else 0.2)
        if not evenements:
            for f in flux.values():
                f.vider()
            if proc.poll() is not None:                    # command finished, but a process launched by it keeps the output open: we do not wait
                if fin is None:
                    fin = True
                    continue
                break
            continue
        for cle, _m in evenements:
            f = flux[cle.fd]
            f.lire()
            if not f.ouvert:
                sel.unregister(cle.fd)
    for f in flux.values():
        f.vider()
    code = proc.wait()
    return code if code >= 0 else 128 - code


def main(argv):
    """Deux modes : « PROGRAMME VARIABLE -- COMMANDE… » (programmes bash : traduction et/ou anonymisation) ; « --anonymiser-seul -- COMMANDE… » (programmes Python, qui se
    traduisent eux-mêmes : seule l'anonymisation de leur sortie est faite ici)."""
    if len(argv) >= 4 and argv[1] == "--anonymiser-seul" and argv[2] == "--":
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        return lancer(argv[3:], _anonymiser().Anonymiseur(), "fr", anonymiser=True)
    if len(argv) < 5 or argv[3] != "--":
        print(__doc__, file=sys.stderr)
        return 2
    programme, variable, commande = argv[1], argv[2], argv[4:]
    try:
        module = _i18n()
        # command = [interpreter, script, arguments...]: the language depends on the script's arguments
        contexte = module.demarrer(DOSSIER, programme, variable, SUPPLEMENTAIRES + AUTRES_CATALOGUES.get(programme, ()), argv=commande[2:], confirmer_ctrl_c=False)
        langue, tr = contexte.langue, contexte.tr
        os.environ["NGINX_TOOLS_I18N_ORIGINE"] = getattr(contexte, "origine_langue", "")       # 1.4: shown by config_afficher ("--lang fr (LANG=fr_CA.UTF-8)")
        config = contexte.config
    except Exception:
        langue, tr, config = "fr", None, {}
    anonymiseur = None
    try:
        outil = _anonymiser()
        if outil.demande(commande[2:], config, terminal=os.isatty(1)):
            anonymiseur = outil.Anonymiseur()
        commande = commande[:2] + outil.sans_option(commande[2:])         # the bash programs do not know --anonymize: the filter is set here
    except Exception:
        if any(a.startswith("--anon") and "--anonymize".startswith(a) for a in commande[2:]):
            print("ERREUR : anonymisation demandée mais apps/_anonymiser.py est illisible : rien n'est affiché.", file=sys.stderr)
            return 2
    traduit = not (langue == "fr" or tr is None or not tr)
    if not traduit and anonymiseur is None:
        os.environ["NGINX_TOOLS_I18N"] = "1"
        os.environ["NGINX_TOOLS_I18N_LANGUE"] = "fr"
        os.execvp(commande[0], commande)
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    if anonymiseur is None:
        return lancer(commande, tr, langue)
    return lancer(commande, (lambda ligne: anonymiseur(tr(ligne) if traduit else ligne)), langue, anonymiser=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
