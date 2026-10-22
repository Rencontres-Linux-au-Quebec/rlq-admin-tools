#!/usr/bin/env python3
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux
# Copyright (C) 2026 Rencontres Linux au Québec contributors
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Full text: https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
"""Chaque clé que les programmes lisent dans leur fichier de configuration (ou dans le fichier commun app-default.conf) doit être
écrite, en commentaire, dans le modèle doc/en/ et doc/fr/ (ce modèle sert à créer /etc/default/PROGRAMME.conf au premier lancement)."""
import glob
import os
import re
import unittest

from helpers import SCRIPTS_DIR, script_path

ENVIRONNEMENT = "commun"   # tous les serveurs (Odoo et BigBlueButton)

# Lecteurs écrits à la main (sans SCHEMA_CONFIG) : clés lues par odoo-warmup.py et odoo-mail-retry.py.
LECTEURS_MANUELS = {
    "odoo-warmup": ["REPEAT", "WAIT", "LINKS", "LATEST", "URL", "DB", "LOGIN", "KEY_FILE", "PAGES", "PAGES_FILE", "LANGS", "MODELS", "SERVICE", "LANGUAGE"],
    "odoo-mail-retry": ["BATCH", "DAYS", "DB", "DETAILS", "NO_PROMPT", "LANGUAGE"],
}
COMMUNES = ["LANGUAGE", "VERBOSE", "DEBUG_LEVEL", "LOG_KEEP_DAYS", "ANONYMIZE"]


def cles_schema(texte):
    m = re.search(r"^SCHEMA_CONFIG\s*=\s*(\{.*?\})\s*$", texte, re.M | re.S)
    return re.findall(r'"([A-Z][A-Z0-9_]+)"\s*:\s*\(', m.group(1)) if m else []


def cles_bash(texte):
    return sorted(set(re.findall(r"config_defaut\s+[A-Z_0-9]+\s+([A-Z][A-Z0-9_]+)\s", texte)))


def cles_modele(chemin):
    with open(chemin, encoding="utf-8") as f:
        return set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", f.read(), re.M))


class ClesDansLesModeles(unittest.TestCase):
    def modele(self, langue, programme):
        return os.path.join(SCRIPTS_DIR, "doc", langue, f"{programme}.conf.example")

    def verifier(self, programme, cles):
        for langue in ("en", "fr"):
            with self.subTest(programme=programme, langue=langue):
                chemin = self.modele(langue, programme)
                self.assertTrue(os.path.isfile(chemin), f"modèle absent : {chemin}")
                absentes = sorted(set(cles) - cles_modele(chemin))
                self.assertEqual(absentes, [], f"{programme} ({langue}) : clés absentes du modèle")

    def test_programmes_python_avec_schema(self):
        for chemin in sorted(glob.glob(os.path.join(SCRIPTS_DIR, "*.py"))):
            with open(chemin, encoding="utf-8") as f:
                cles = cles_schema(f.read())
            if cles:
                with self.subTest(programme=os.path.basename(chemin)):
                    self.verifier(os.path.basename(chemin)[:-3], cles)

    def test_programmes_bash(self):
        for chemin in sorted(glob.glob(os.path.join(SCRIPTS_DIR, "*.sh"))):
            with open(chemin, encoding="utf-8") as f:
                cles = cles_bash(f.read())
            if cles:
                with self.subTest(programme=os.path.basename(chemin)):
                    self.verifier(os.path.basename(chemin)[:-3], cles)

    def test_lecteurs_manuels(self):
        for programme, cles in LECTEURS_MANUELS.items():
            with self.subTest(programme=programme):
                self.verifier(programme, cles)

    def test_fichier_commun(self):
        """app-default.conf : les cinq clés communes (apps/_config.py CLES_COMMUNES) doivent être dans le modèle commun."""
        for langue in ("en", "fr"):
            with self.subTest(langue=langue):
                chemin = os.path.join(SCRIPTS_DIR, "doc", langue, "app-default.conf.example")
                absentes = sorted(set(COMMUNES) - cles_modele(chemin))
                self.assertEqual(absentes, [], f"app-default ({langue}) : clés absentes du modèle commun")

    def test_commune_declaree_dans_le_module_partage(self):
        with open(script_path("apps/_config.py"), encoding="utf-8") as f:
            texte = f.read()
        m = re.search(r'^CLES_COMMUNES\s*=\s*\((.*?)\)', texte, re.M)
        self.assertIsNotNone(m, "CLES_COMMUNES introuvable dans apps/_config.py")
        self.assertEqual(sorted(re.findall(r'"([A-Z_]+)"', m.group(1))), sorted(COMMUNES))


if __name__ == "__main__":
    unittest.main()
