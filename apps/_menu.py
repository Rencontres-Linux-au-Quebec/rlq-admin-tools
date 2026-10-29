# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux Inc.
# Copyright (C) 2026 Rencontres Linux au Quebec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
"""_menu.py - menu --menu commun aux programmes Python (apps/, chargé par importlib) : dialog si disponible, sinon texte.

Usage, dans un programme, après parse_args() :
    menu = charger_menu(SCRIPT_DIR)
    if args.menu:
        menu.menu(os.path.abspath(__file__), sys.argv[1:], ENTREES, configuration=programme, nom=NOM)
ENTREES : liste de (options à relancer, libellé français, libellé anglais, confirmer). Les options sont relancées avec celles
de la ligne de commande (sauf --menu). Le menu ajoute la configuration lue, --changelog et Quitter.
"""
import os
import subprocess
import sys
import tempfile

DIALOG_BIN = os.environ.get("NGINX_TOOLS_DIALOG", "dialog")


_LANGUE = None      # langue d'affichage du programme (paramètre `langue` de menu) ; à défaut, NGINX_TOOLS_I18N_LANGUE


def _en():
    if _LANGUE:
        return _LANGUE.startswith("en")
    return os.environ.get("NGINX_TOOLS_I18N_LANGUE", "fr").startswith("en")


def _t(fr, en):
    return en if _en() else fr


def _libelle(fr, en, traduire=None):
    """Libellé d'une entrée : pour un programme écrit en anglais, `traduire` (son traducteur, lang/PROG.fr.po) traduit le texte anglais ; sinon fr/en."""
    return traduire(en) if traduire else _t(fr, en)


def _terminal_ok():
    try:
        with open("/dev/tty", "rb"):
            return True
    except OSError:
        return False


def _dialog_disponible():
    from shutil import which
    return which(DIALOG_BIN) is not None and _terminal_ok()


def _dialog(args):
    """(code retour, réponse) : la réponse de dialog est lue dans un fichier (--output-fd), le terminal reste l'écran."""
    with tempfile.TemporaryFile("w+") as f:
        rc = subprocess.run([DIALOG_BIN, "--output-fd", str(f.fileno())] + args, pass_fds=(f.fileno(),)).returncode
        f.seek(0)
        return rc, f.read().strip()


def _confirmer(question):
    if _dialog_disponible() and _UI["mode"] == "dialog":
        rc, _ = _dialog(["--title", _UI["titre"], "--yesno", question, "8", "72"])
        return rc == 0
    try:
        rep = input(question + " [o/N] ")
    except EOFError:
        return False
    return rep.strip().lower() in ("o", "oui", "y", "yes")


def _relancer(programme, argv, options):
    """Relance le programme avec les options reçues (sans --menu) et OPTIONS, puis affiche le code de retour."""
    args = [a for a in argv if a != "--menu"] + list(options)
    print()
    rc = subprocess.run([sys.executable, programme] + args).returncode
    print()
    if rc == 0:
        print(_t("Terminé (code 0).", "Done (code 0)."))
    else:
        print(_t(f"Code de retour : {rc}", f"Return code: {rc}"))


def _configuration(configuration):
    """Texte : fichiers de configuration lus et options qu'ils donnent (apps/_config.py : lire)."""
    lignes = []
    try:
        cfg, fichiers = configuration()
    except Exception as exc:  # une configuration illisible ne doit pas casser le menu
        return [_t("Configuration illisible : ", "Unreadable configuration: ") + str(exc)]
    lignes.append(_t("Fichiers de configuration lus (le dernier l'emporte) :", "Configuration files read (the last one wins):"))
    lignes += [f"  {f}" for f in fichiers] or [_t("  aucun (valeurs par défaut du programme)", "  none (program default values)")]
    lignes.append("")
    lignes.append(_t("Options par défaut lues dans ces fichiers (la ligne de commande les remplace) :",
                     "Default options read from these files (the command line overrides them):"))
    lignes += [f"  {k} = {v}" for k, v in cfg.items()] or [_t("  aucune", "  none")]
    return lignes


_UI = {"mode": "texte", "titre": ""}


def menu(programme, argv, entrees, configuration=None, nom="", traduire=None, langue=None):
    """Boucle du menu. `configuration` : fonction () -> (cfg, fichiers) pour la vue de configuration. Quitte le programme.
    `traduire` et `langue` : traducteur et langue d'affichage du programme (programmes écrits en anglais) ; sinon NGINX_TOOLS_I18N_LANGUE."""
    global _LANGUE
    _LANGUE = langue or None
    if not (sys.stdin.isatty() and sys.stderr.isatty()):
        print("ERREUR: --menu demande un terminal (entrée et sortie interactives).", file=sys.stderr)
        sys.exit(1)
    _UI["titre"] = nom or os.path.basename(programme)
    if _dialog_disponible():
        _UI["mode"] = "dialog"
    else:
        _UI["mode"] = "texte"
        if not _dialog_disponible():
            print(_t("[ATTN] commande dialog absente : menu texte (sudo apt install dialog pour le menu graphique).",
                     "[ATTN] dialog command missing: text menu (sudo apt install dialog for the graphical menu)."), file=sys.stderr)
    while True:
        if _UI["mode"] == "dialog":
            items = []
            for i, (opts, fr, en, conf) in enumerate(entrees):
                items += [str(i), _libelle(fr, en, traduire)]
            items += ["config", _t("Voir la configuration lue", "Show the configuration read")]
            items += ["changelog", _t("Journal des modifications (--changelog)", "Change log (--changelog)")]
            items += ["q", _t("Quitter", "Quit")]
            rc, choix = _dialog(["--title", _UI["titre"], "--menu", _t("Choisissez une opération :", "Choose an operation:"),
                                 "22", "76", "14"] + items)
            if rc != 0 or choix in ("", "q"):
                break
        else:
            print()
            print("=" * 62)
            print(" " + _UI["titre"])
            print("=" * 62)
            for i, (opts, fr, en, conf) in enumerate(entrees):
                print(f"  {i:2d}  {_libelle(fr, en, traduire)}")
            print(f"  c   {_t('Voir la configuration lue', 'Show the configuration read')}")
            print(f"  l   {_t('Journal des modifications (--changelog)', 'Change log (--changelog)')}")
            print(f"  q   {_t('Quitter', 'Quit')}")
            print()
            try:
                choix = input(_t("Votre choix : ", "Your choice: ")).strip().lower()
            except EOFError:
                print()
                break
            if choix in ("q", ""):
                break
        if choix == "config":
            if configuration is None:
                print(_t("Aucune configuration à montrer.", "No configuration to show."))
            else:
                print("\n".join(_configuration(configuration)))
        elif choix in ("l", "changelog"):
            _relancer(programme, argv, ["--changelog"])
        elif choix.isdigit() and int(choix) < len(entrees):
            opts, fr, en, conf = entrees[int(choix)]
            libelle = _libelle(fr, en, traduire)
            if conf and not _confirmer(_t(f"{libelle} : confirmer ?", f"{libelle}: confirm?")):
                print(_t("Annulé : rien n'est modifié.", "Cancelled: nothing changed."))
            else:
                _relancer(programme, argv, opts)
        else:
            print(_t(f"Choix inconnu : « {choix} ».", f"Unknown choice: « {choix} »."))
        try:
            input(_t("Entrée pour revenir au menu...", "Enter to return to the menu..."))
        except EOFError:
            break
    sys.exit(0)


def _config_explicite(argv):
    for i, a in enumerate(argv):
        if a.startswith("--config="):
            return a.split("=", 1)[1]
        if a in ("-c", "--config") and i + 1 < len(argv):
            return argv[i + 1]
    return None


def configuration_de(dossier, nom, argv):
    """Fonction () -> (cfg, fichiers) : la configuration lue par apps/_config.py (même règle que le programme)."""
    def lire():
        import importlib.util
        spec = importlib.util.spec_from_file_location("_config", os.path.join(dossier, "apps", "_config.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.lire(nom, explicite=_config_explicite(argv))
    return lire


def charger_menu(dossier):
    """Charge apps/_menu.py (pas d'import de paquet : comme les autres modules du dépôt)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_menu", os.path.join(dossier, "apps", "_menu.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
