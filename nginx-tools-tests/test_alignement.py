"""Alignement des colonnes en français ET en anglais, avec les données d'exemple (donnees_exemples.py : accents, accent combinant NFD, chinois,
apostrophes) : remplissage en COLONNES d'écran dans bash (apps/_i18n.sh pad_cols : printf de bash compte des octets), en-tête de
sync-crowdsec-blocklist.sh --stats, champs de odoo-update-module.sh, groupes RLQ* et inscriptions par billet de app-log-live.py, tableau des
statistiques de run-all.sh (stats_runner.py). Les tableaux complets de web-monitor.py et le flux de app-log-live.py sont vérifiés dans
test_odoo_users.py et test_app_log_live.py (même données)."""
# Environnement de ces tests, lu par run-all.sh : commun (tous les serveurs), odoo ou bbb.
ENVIRONNEMENT = "commun"   # fonctions d'affichage communes, aucun service réel
import contextlib
import importlib.util
import io
import json
import os
import re
import sys
import unittest

import donnees_exemples as ex
from helpers import EnvTest, script_path

ANSI = re.compile(r"\x1b\[[0-9;]*m|[-]")


def charger(nom, chemin, argv=None):
    """Module d'un programme, chargé avec ces arguments (la langue d'affichage est lue au chargement : --lang fr / en)."""
    ancien = sys.argv
    sys.argv = ["x"] + list(argv or [])
    try:
        spec = importlib.util.spec_from_file_location(nom, script_path(chemin))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.argv = ancien
    return module


class PadColsBash(EnvTest):
    """apps/_i18n.sh 1.15 : pad_cols complète en colonnes, quelle que soit la locale de l'appelant."""

    def pad(self, texte, n, locale="C"):
        rc, out, err = self.run_cmd(["bash", "-c", f'. "{script_path("apps/_i18n.sh")}"; pad_cols "$1" {n}; printf "|"', "x", texte], {"LC_ALL": locale, "LANG": locale})
        self.assertEqual(rc, 0, err)
        return out

    def test_accents_comptes_une_colonne_meme_sous_lang_c(self):
        for texte in ex.PERSONNES_FR + ex.PERSONNES_EN + ["PREMIÈRE DÉTECTION", ""]:
            with self.subTest(texte=texte):
                self.assertEqual(ex.largeur(self.pad(texte, 30)), 31)              # 30 colonnes + « | »
        self.assertEqual(self.pad("trop long pour la colonne", 4), "trop long pour la colonne|")     # jamais coupé, jamais négatif

    def test_printf_de_bash_compte_des_octets(self):
        """Le défaut corrigé : sans pad_cols, « Première » (9 octets) recevait 1 espace de moins que « Premiere »."""
        rc, out, _ = self.run_cmd(["bash", "-c", 'printf "%-12s|\\n" "Première" "Premiere"'], {"LC_ALL": "C", "LANG": "C"})
        a, b = out.splitlines()
        self.assertNotEqual(ex.largeur(a), ex.largeur(b))


class EnTetesBash(EnvTest):
    def test_sync_crowdsec_en_tete_de_stats_au_dessus_des_colonnes(self):
        """sync-crowdsec-blocklist.sh 1.25 : « PREMIÈRE DÉTECTION » (2 lettres accentuées) était 2 colonnes trop court : « DERNIÈRE DÉTECTION » ne
        tombait plus au-dessus des dates."""
        texte = open(script_path("sync-crowdsec-blocklist.sh"), encoding="utf-8").read()
        self.assertIn('"$(pad_cols "PREMIÈRE DÉTECTION" 38)"', texte)
        rc, out, err = self.run_cmd(["bash", "-c", f'. "{script_path("apps/_i18n.sh")}"; '
                                     'printf "%-40s %10s %12s  %s %s\\n" IP PAQUETS OCTETS "$(pad_cols "PREMIÈRE DÉTECTION" 38)" "DERNIÈRE DÉTECTION"; '
                                     'printf "%-40s %10s %12s  %-38s %s\\n" 203.0.113.30 12 3400 "2026-10-01 08:00" "2026-10-20 09:05"'], {"LC_ALL": "C"})
        tete, ligne = out.splitlines()
        self.assertEqual(ex.largeur(tete[:tete.index("DERNIÈRE")]), ex.largeur(ligne[:ligne.index("2026-10-20")]), out)

    def test_odoo_update_module_champs_alignes(self):
        """odoo-update-module.sh 1.13 : champ() complète l'étiquette en colonnes (« Modèle : » accentué ne décale plus sa valeur)."""
        texte = open(script_path("odoo-update-module.sh"), encoding="utf-8").read()
        champ = re.search(r"^champ\(\) \{.*$", texte, re.M).group(0)
        rc, out, err = self.run_cmd(["bash", "-c", f'. "{script_path("apps/_i18n.sh")}"; C_DIM=""; C_RESET=""; {champ}\n'
                                     'champ "Base :" b; champ "Modèle :" m; champ "Dépôt « é » :" d'], {"LC_ALL": "C"})
        self.assertEqual({ex.largeur(l) for l in out.splitlines()}, {2 + 13 + 2}, out)


class AppLogLiveFonctions(unittest.TestCase):
    """Fonctions d'affichage de app-log-live.py, dans les deux langues (le texte passe par translate_protected, comme à l'écran)."""

    def test_groupes_rlq_en_colonnes_avec_noms_accentues_et_chinois(self):
        for langue in ("fr", "en"):
            live = charger(f"live_g_{langue}", "app-log-live.py", ["--lang", langue])
            live.COLOR = False
            groupes = [{"nom": n, "membres": i * 7} for i, n in enumerate(["RLQ26-Bénévole", "RLQ26-Visiteur", "RLQ26-Comité organisateur", "RLQ26-张三李四",
                                                                        "RLQ26-Conférencier·ère", "RLQ26-Commanditaire", "RLQ26-Équipe technique"])]
            with self.subTest(langue=langue):
                lignes = [live.translate_protected(l) for l in live.rlq_group_columns(groupes, columns=200)]
                debuts = [ex.debuts_de_colonnes(l) for l in lignes]
                for d in debuts:
                    self.assertEqual(d, debuts[0][:len(d)], "\n".join(lignes))

    def test_inscriptions_par_billet_noms_alignes(self):
        """I key: the « (state) » column after the name starts at the same screen column for accented, NFD, Chinese and English names."""
        for langue in ("fr", "en"):
            live = charger(f"live_t_{langue}", "app-log-live.py", ["--lang", langue])
            live.COLOR = False
            rows = [{"event_id": 1, "event": ex.EVENEMENTS_FR[0], "event_start": 1790000000, "ticket_id": 1, "ticket": "Bénévole", "survey_id": 0, "survey": "",
                     "name": n, "state": "open", "when": 1790000000 + i, "answer": None, "other": None} for i, n in enumerate(ex.PERSONNES)]
            with self.subTest(langue=langue):
                lignes = [live.translate_protected(l) for l in live.ticket_report(rows) if "(open)" in l]
                self.assertEqual(len(lignes), len(ex.PERSONNES))
                self.assertEqual(len({ex.largeur(l[:l.index("(open)")]) for l in lignes}), 1, "\n".join(lignes))


class StatistiquesDeRunAll(unittest.TestCase):
    """run-all.sh 1.188 : tableau des statistiques (stats_runner.py) — mêmes colonnes en français et en anglais."""

    def setUp(self):
        spec = importlib.util.spec_from_file_location("stats_runner", os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats_runner.py"))
        self.sr = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.sr)

    def donnees(self, d):
        tests = []
        for i, (prog, kind) in enumerate([("app-log-live.py", "functional"), ("app-log-live.py", "unit"), ("web-monitor.py", "interactive"),
                                          ("apps/_i18n.sh", "unit"), (None, "conformity"), ("nginx-log-audit.sh", "functional")]):
            tests.append({"id": f"test_x.Classe.test_{i}_é", "module": "test_x", "program": prog, "kind": kind, "seconds": 0.5 + i * 12.3,
                          "result": ["ok", "skipped", "failed"][i % 3]})
        chemin = os.path.join(d, "stats.json")
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump({"awk": "mawk", "seconds": 4321.0, "cpu_user": 1234.5, "cpu_system": 321.0, "max_rss_kb": 204800, "processes": 9876,
                       "read_bytes": 10 ** 9, "write_bytes": 3 * 10 ** 8, "tests": tests}, f)
        return chemin

    def test_tableau_aligne_dans_les_deux_langues(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="test-rlq-") as d:
            chemin = self.donnees(d)
            for langue in ("fr", "en"):
                with self.subTest(langue=langue):
                    sortie = io.StringIO()
                    with contextlib.redirect_stdout(sortie):
                        self.sr.report([chemin], lang=langue, color=False)
                    lignes = sortie.getvalue().splitlines()
                    entete = next(i for i, l in enumerate(lignes) if re.match(r"\s+Program(me)?\s{2,}tests", l))
                    tableau = lignes[entete:entete + 6]                     # en-tête, 4 programmes + transversal, total
                    self.assertEqual(len({ex.largeur(l) for l in tableau}), 1, "\n".join(tableau))
                    self.assertIn("TOTAL", lignes[entete + 6])
                    self.assertEqual(ex.largeur(lignes[entete + 6]), ex.largeur(tableau[0]))
                    etiquettes = [l for l in lignes if " : " in l and l.startswith("  ") and not l.startswith("   ")][:5]
                    self.assertEqual(len({ex.largeur(l[:l.index(" : ")]) for l in etiquettes}), 1, "\n".join(etiquettes))
                    self.assertIn("unitaires" if langue == "fr" else "unit", tableau[0])

    def test_nature_des_tests_mesuree(self):
        """Nature mesurée pendant le test : un programme lancé = fonctionnel ; un pseudo-terminal = interactif ; rien = unitaire."""
        import pty
        import subprocess

        class Mini(unittest.TestCase):
            def test_a_unitaire(self):
                self.assertEqual(1 + 1, 2)

            def test_b_fonctionnel(self):
                subprocess.run(["true"], check=True)

            def test_c_interactif(self):
                pid, fd = pty.fork()
                if pid == 0:
                    os._exit(0)
                os.waitpid(pid, 0)
                os.close(fd)
        probe = self.sr.Probe()
        try:
            self.sr.StatsResult.probe, self.sr.StatsResult.records = probe, []
            unittest.TextTestRunner(stream=io.StringIO(), resultclass=self.sr.StatsResult).run(unittest.defaultTestLoader.loadTestsFromTestCase(Mini))
        finally:
            probe.uninstall()
        self.assertEqual([r["kind"] for r in self.sr.StatsResult.records], ["unit", "functional", "interactive"])

    def test_echec_d_un_sous_test_compte(self):
        """Un subTest() en échec compte le test comme « échec » dans le tableau (unittest passe par addSubTest, pas addFailure)."""
        class Mini(unittest.TestCase):
            def test_sous_tests(self):
                for i in (1, 2):
                    with self.subTest(i=i):
                        self.assertEqual(i, 1)
        probe = self.sr.Probe()
        try:
            self.sr.StatsResult.probe, self.sr.StatsResult.records = probe, []
            unittest.TextTestRunner(stream=io.StringIO(), resultclass=self.sr.StatsResult).run(unittest.defaultTestLoader.loadTestsFromTestCase(Mini))
        finally:
            probe.uninstall()
        self.assertEqual([r["result"] for r in self.sr.StatsResult.records], ["failed"])
        self.assertEqual(self.sr.program_of("test_app_log_live"), "app-log-live.py")
        self.assertEqual(self.sr.program_of("test_cache_ip"), os.path.join("apps", "_cache_ip.py"))
        self.assertIsNone(self.sr.program_of("test_conventions"))
        self.assertEqual(self.sr.pad("Durée", 9), "Durée    ")
        self.assertEqual(self.sr.width(ex.PERSONNE_NFD), 11)
        self.assertEqual(self.sr.width(ex.PERSONNE_CJK), 8)


if __name__ == "__main__":
    unittest.main()
