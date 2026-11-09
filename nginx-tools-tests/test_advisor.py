"""apps/_advisor.py et touche z d'app-log-live.py (1.163) : analyse des problèmes soulevés, détails lus dans les journaux (trace d'Odoo, référents de nginx),
recommandations, historique des analyses (nouveau, récurrent, réglé) ; catalogue lang/_advisor.fr.po ; dictionnaire de faits construit depuis Stats."""
import ast
import importlib.util
import json
import os
import re
import stat
import tempfile
import time
import unittest
from collections import Counter

from helpers import SCRIPTS_DIR

ENVIRONNEMENT = "commun"
PROGRAMME = "app-log-live.py"                               # nom du programme (lu par stats_runner)
os.environ.setdefault("APP_LOG_LIVE_SITEMAP", "off")


def charger(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ADV = charger("_advisor_t", os.path.join(SCRIPTS_DIR, "apps", "_advisor.py"))

TRACE = """2026-11-04 12:21:15,001 1234 INFO prod werkzeug: 1.2.3.4 - - "GET / HTTP/1.1" 200 - 10 0.01 0.02
2026-11-04 12:21:16,123 1234 ERROR prod odoo.http: Exception during request handling.
Traceback (most recent call last):
  File "/usr/lib/python3/dist-packages/odoo/http.py", line 2367, in __call__
    response = request._serve_db()
  File "/opt/odoo/rlq-addons/rlq_event_extra/controllers/main.py", line 88, in track_page
    tags = json.loads(kw['tags'])[0]
KeyError: 'tags'
2026-11-04 12:21:17,000 1234 INFO prod werkzeug: done
""".splitlines()

ACCESS = """1.1.1.1 - - [04/Nov/2026:09:10:00 -0500] "GET /en_CA/shop/tasse HTTP/1.1" 404 1234 "https://site.example/en_CA/shop" "Mozilla/5.0" host=site.example
1.1.1.2 - - [04/Nov/2026:09:11:00 -0500] "GET /en_CA/shop/tasse?x=1 HTTP/1.1" 404 1234 "https://www.google.com/" "Mozilla/5.0" host=site.example
1.1.1.3 - - [04/Nov/2026:09:12:00 -0500] "GET /sitemap.xml HTTP/1.1" 403 12 "-" "SemrushBot" host=site.example
1.1.1.4 - - [01/Nov/2026:09:13:00 -0500] "GET /en_CA/shop/tasse HTTP/1.1" 404 12 "https://old.example/" "Mozilla/5.0" host=site.example
"""


def faits(**k):
    base = {"start": time.time() - 3600, "requests": 100, "lines": 120, "errors5": {}, "codes_by_url": {}, "plain_4xx": {}, "gone_404": {}, "sitemap_paths": None,
            "odoo_errors": [], "conflicts": 0, "conflict_codes": {}, "final_failures": 0, "failure_codes": {}, "mails": 0, "slow": [], "to_ban": [], "not_proposed": [],
            "account_ips": {}, "who": {}, "latency_n": None}
    base.update(k)
    return base


def erreur(level, logger, message, n=1):
    return {"level": level, "logger": logger, "message": message, "n": n, "first": time.time(), "last": time.time(), "when": "07:21:16"}


def par_id(findings):
    return {f["id"]: f for f in findings}


class Details(unittest.TestCase):
    """Lecture des détails : trace d'Odoo, en-têtes de nginx."""

    def test_trace_trouvee_et_analysee(self):
        trace = ADV.odoo_trace(TRACE, "odoo.http", "Exception during request handling.")
        self.assertEqual(len(trace), 7)
        self.assertTrue(trace[-1].startswith("KeyError"))
        p = ADV.parse_traceback(trace)
        self.assertEqual(p["exception"], "KeyError")
        self.assertEqual(p["message"], "'tags'")
        self.assertEqual(p["module"], "rlq_event_extra")                   # dossier rlq-addons/ reconnu
        self.assertEqual(p["frame"], "main.py:88 in track_page")

    def test_message_avec_nombres_normalises(self):
        lignes = ["2026-11-04 12:00:00,1 9 ERROR prod odoo.addons.mail: Mail Delivery Failed pour 12 destinataires", "suite"]
        self.assertEqual(len(ADV.odoo_trace(lignes, "odoo.addons.mail", "Mail Delivery Failed pour N destinataires")), 2)
        self.assertEqual(ADV.odoo_trace(lignes, "odoo.http", "Mail Delivery Failed pour N destinataires"), [])
        self.assertEqual(ADV.parse_traceback(["une ligne"]), {})

    def test_nginx_referents_codes_et_fenetre(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "site-access.log")
            with open(chemin, "w") as f:
                f.write(ACCESS)
            debut = ADV.calendar.timegm((2026, 11, 2, 0, 0, 0, 0, 0, 0))
            r = ADV.nginx_details([chemin, os.path.join(d, "absent.log")], ["/en_CA/shop/tasse?y=2", "/sitemap.xml"], since=debut)
        tasse = r["/en_CA/shop/tasse"]
        self.assertEqual(tasse["codes"], Counter({"404": 2}))                   # la ligne du 1er novembre est avant la fenêtre
        self.assertEqual(ADV.internal_referers(tasse), Counter({"https://site.example/en_CA/shop": 1}))
        self.assertIn("https://www.google.com/", tasse["referers"])
        self.assertEqual(r["/sitemap.xml"]["codes"], Counter({"403": 1}))

    def test_journal_compresse_gz(self):
        import gzip
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "site-access.log.2.gz")
            with gzip.open(chemin, "wt") as f:
                f.write(ACCESS)
            r = ADV.nginx_details([chemin], ["/en_CA/shop/tasse"])
            self.assertEqual(r["/en_CA/shop/tasse"]["codes"], Counter({"404": 3}))
            with open(os.path.join(d, "abime.gz"), "wb") as f:
                f.write(b"pas du gzip")
            self.assertEqual(ADV.read_tail(os.path.join(d, "abime.gz")), [])

    def test_fin_de_fichier_seulement(self):
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "x.log")
            with open(chemin, "w") as f:
                f.write("A" * 50 + "\npremiere\nderniere\n")
            self.assertEqual(ADV.read_tail(chemin, 20), ["premiere", "derniere"])     # la ligne coupée au début est retirée
            self.assertEqual(ADV.read_tail(os.path.join(d, "absent")), [])


class Regles(unittest.TestCase):
    def test_slash_ev_fausse_alerte(self):
        f = par_id(ADV.analyze(faits(gone_404={"/ev": 1}, sitemap_paths=frozenset({"/", "/event"}))))
        self.assertEqual(f["sitemap-404-false:/ev"]["severity"], ADV.INFO)
        self.assertIn("not a language code", " ".join(f["sitemap-404-false:/ev"]["evidence"]))
        self.assertIn("all-clear", f)

    def test_lien_tronque_et_vraie_page_disparue(self):
        f = par_id(ADV.analyze(faits(gone_404={"/even": 2, "/vieille-page": 3}, sitemap_paths=frozenset({"/", "/event", "/event/jpo"}))))
        self.assertEqual(f["sitemap-404-truncated:/even"]["severity"], ADV.LOOK)
        self.assertIn("/event", f["sitemap-404-truncated:/even"]["evidence"][0])
        self.assertEqual(f["sitemap-404:/vieille-page"]["severity"], ADV.LOOK)
        self.assertNotIn("all-clear", f)

    def test_lien_mort_du_site_et_produit(self):
        details = {"nginx": {"/a": {"codes": Counter({"404": 4}), "referers": Counter({"https://s.example/page": 4}), "hosts": Counter({"s.example": 4}), "agents": Counter()},
                             "/shop/tasse": {"codes": Counter({"404": 6}), "referers": Counter(), "hosts": Counter(), "agents": Counter()},
                             "/bots": {"codes": Counter({"403": 9}), "referers": Counter(), "hosts": Counter(), "agents": Counter()}}}
        f = par_id(ADV.analyze(faits(plain_4xx={"/a": 4, "/shop/tasse": 6, "/bots": 9, "/rare": 2}), details))
        self.assertEqual(f["dead-link:/a"]["severity"], ADV.LOOK)
        self.assertIn("a link of the site itself", f["dead-link:/a"]["cause"])
        self.assertEqual(f["dead-link:/shop/tasse"]["severity"], ADV.LOOK)
        self.assertNotIn("dead-link:/bots", f)                                  # 403 : robots refusés, pas une page morte
        self.assertNotIn("dead-link:/rare", f)                                  # moins de 3

    def test_nginx_details_qui_a_demande_et_qui_a_repondu(self):
        """1.5: robots / browsers, repeated addresses and the size of the 404 are read in the access log by the program itself."""
        ligne = ('{ip} - - [20/Oct/2026:14:49:04 -0400] "GET /en_CA/event/x-129/registration/success?registration_ids={i} HTTP/1.1" 404 {b} "{ref}" "{ua}" host="s.example"')
        ua_nav = "Mozilla/5.0 (iPhone; CPU iPhone OS 26_6_1 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"
        ua_bot = "Mozilla/5.0 (Linux; Android 10; K) Chrome/138.0.0.0 Mobile Safari/537.36 (compatible; Google-Read-Aloud; +https://support.google.com)"
        lignes = [ligne.format(ip="24.1.1.1", i=1913, b=6910, ref="https://s.example/register", ua=ua_nav),
                  ligne.format(ip="24.1.1.2", i=1913, b=6911, ref="https://s.example/register", ua=ua_nav),
                  ligne.format(ip="66.249.1.1", i=1986, b=7578, ref="-", ua=ua_bot)]
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "access.log")
            with open(chemin, "w", encoding="utf-8") as f:
                f.write("\n".join(lignes) + "\n")
            res = ADV.nginx_details([chemin], ["/en_CA/event/x-129/registration/success"])
        detail = res["/en_CA/event/x-129/registration/success"]
        self.assertEqual(detail["browser_hits"], 2)
        self.assertEqual(detail["browser_ips"], {"24.1.1.1", "24.1.1.2"})
        self.assertEqual(sum(detail["robots"].values()), 1)
        self.assertEqual(detail["browser_queries"]["registration_ids=1913"], 2)
        self.assertEqual(sorted(detail["bytes_4xx"]), [6910, 6911, 7578])
        f = par_id(ADV.analyze(faits(plain_4xx={"/en_CA/event/x-129/registration/success": 3},
                                     codes_by_url={"/en_CA/event/x-129/registration/success": {"404": 3}}),
                               {"nginx": res, "registrations": {"asked": 2, "found": 2, "no_visitor": 1, "duplicates": 1}}))
        trouve = f["registration-404:/en_CA/event/x-129/registration/success"]
        self.assertEqual(trouve["severity"], ADV.LOOK)
        texte = " ".join(trouve["evidence"])
        self.assertIn("page is the one of Odoo (6.7 KB)", texte)
        self.assertIn("1 robots, link previews or tools", texte)
        self.assertIn("2 browsers from 2 addresses", texte)
        self.assertIn("?registration_ids=1913 ×2", texte)
        self.assertIn("2 found of 2, 1 with no visitor recorded", texte)
        self.assertIn("1 people registered several times", texte)

    def test_page_404_de_nginx_et_confirmation_ouverte_par_des_robots(self):
        d = {"codes": Counter({"404": 3}), "referers": Counter(), "hosts": Counter(), "agents": Counter(), "bytes_4xx": [146, 146, 146],
             "robots": Counter({"WhatsApp/2.23": 3}), "browser_hits": 0, "browser_ips": set(), "browser_queries": Counter()}
        chemin = "/event/x-119/registration/success"
        f = par_id(ADV.analyze(faits(plain_4xx={chemin: 3}, codes_by_url={chemin: {"404": 3}}), {"nginx": {chemin: d}}))
        self.assertEqual(f["registration-404:" + chemin]["severity"], ADV.INFO)
        self.assertIn("the one of nginx (146 bytes)", " ".join(f["registration-404:" + chemin]["evidence"]))
        autre = "/shop/tasse"
        d2 = dict(d, bytes_4xx=[146] * 6, codes=Counter({"404": 6}))
        f = par_id(ADV.analyze(faits(plain_4xx={autre: 6}, codes_by_url={autre: {"404": 6}}), {"nginx": {autre: d2}}))
        self.assertIn("a rule or a location of nginx refuses", " ".join(f["dead-link:" + autre]["evidence"]))

    def test_5xx_faits_par_ce_serveur_sont_une_information(self):
        """1.6: the 500 made by the tests of the administrator (curl, probes) are not a problem, and the same exception of Odoo is not either."""
        chemin = "/en_CA/event/x-125/registration/success"
        trace = ["2026-11-06 13:30:51,000 1 ERROR db odoo.http: Exception during request handling.", "Traceback (most recent call last):",
                 "  File \"/opt/odoo/odoo/odoo/http.py\", line 754, in route_wrapper", "    result = endpoint(self, *args, **params_ok)",
                 "TypeError: WebsiteEventController.event_registration_success() missing 1 required positional argument: 'registration_ids'"]
        f = faits(errors5={chemin: 3}, http_errors5=[(time.time(), 500, chemin, "127.0.0.1")] * 2 + [(time.time(), 500, chemin, "51.1.2.3")],
                  server_ips=["51.1.2.3"], who={"127.0.0.1": "app-health-check.py", "51.1.2.3": "this server"},
                  odoo_errors=[{"level": "ERROR", "logger": "odoo.http", "message": "Exception during request handling.", "n": 3, "last": time.time(), "when": "x"}])
        res = par_id(ADV.analyze(f, {"traces_5xx": {chemin: trace}, "tracebacks": {("ERROR", "odoo.http", "Exception during request handling."): trace}}))
        self.assertEqual(res["http-5xx:" + chemin]["severity"], ADV.INFO)
        self.assertIn("made by this server itself", res["http-5xx:" + chemin]["cause"])
        texte = " ".join(res["http-5xx:" + chemin]["evidence"])
        self.assertIn("this server [127.0.0.1] ×2", texte)                       # not « app-health-check.py »: it was the tests of the administrator
        self.assertNotIn("app-health-check.py", texte)
        erreur = next(v for k, v in res.items() if k.startswith("odoo:"))
        self.assertEqual(erreur["severity"], ADV.INFO)
        self.assertIn("same exception", erreur["cause"])
        # a visitor causing the same page to fail keeps the problem
        f2 = faits(errors5={chemin: 3}, http_errors5=[(time.time(), 500, chemin, "11.2.3.4")] * 3, server_ips=["51.1.2.3"])
        self.assertEqual(par_id(ADV.analyze(f2, {"traces_5xx": {chemin: trace}}))["http-5xx:" + chemin]["severity"], ADV.PROBLEM)

    def test_noms_de_robots_et_404_de_nginx_avec_lien_du_site(self):
        self.assertEqual(ADV.ROBOT_NAME_RE.search("Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (compatible; Google-Read-Aloud; +https://support.google.com)").group(0), "Google-Read-Aloud")
        self.assertEqual(ADV.ROBOT_NAME_RE.search("WhatsApp/2.23.20.0").group(0), "WhatsApp/2.23.20.0")
        chemin = "/event/page/2"
        d = {"codes": Counter({"404": 5}), "referers": Counter({"https://s.example/event?date=all": 5}), "hosts": Counter({"s.example": 5}), "agents": Counter(),
             "bytes_4xx": [146] * 5, "robots": Counter(), "browser_hits": 5, "browser_ips": {"1.1.1.1"}, "browser_queries": Counter()}
        f = par_id(ADV.analyze(faits(plain_4xx={chemin: 5}, codes_by_url={chemin: {"404": 5}}, site_hosts=["s.example"]), {"nginx": {chemin: d}}))
        trouve = f["dead-link:" + chemin]
        self.assertIn("nginx refuses an address that the site itself offers", trouve["cause"])
        self.assertTrue(any("nginx-hardening.sh --update" in a for a in trouve["advice"]))
        self.assertFalse(any("correct the link" in a for a in trouve["advice"]))

    def test_formulaires_de_compte_de_personnes_connues(self):
        ips = {"65.93.168.160": 9, "142.116.31.94": 8, "67.69.76.24": 6, "9.9.9.9": 3}
        who = {"65.93.168.160": "Qinghe Sun [65.93.168.160]", "142.116.31.94": "cecchino [142.116.31.94]", "67.69.76.24": "Fernando [67.69.76.24]", "9.9.9.9": "9.9.9.9"}
        # 1.7: "known" = an address where a person signed in (known_ips), no longer any address that has a name
        f = par_id(ADV.analyze(faits(account_ips=ips, who=who, account_urls=["/web/reset_password"], known_ips=["65.93.168.160", "142.116.31.94", "67.69.76.24"]),
                               {"nginx": {"/web/reset_password": {"methods": Counter({"GET": 20, "POST": 6})}}}))
        self.assertEqual(f["account-forms"]["severity"], ADV.INFO)
        self.assertIn("mostly from people already known", f["account-forms"]["title"])
        inconnus = {"1.1.1.%d" % i: 3 for i in range(10)}
        f = par_id(ADV.analyze(faits(account_ips=inconnus, who={}, account_urls=["/web/signup"]), {"nginx": {"/web/signup": {"methods": Counter({"POST": 30})}}}))
        self.assertEqual(f["account-forms"]["severity"], ADV.LOOK)

    def test_sitemap_xml_403_avec_des_200_reste_une_information(self):
        """1.4: the 200 answers of the visitors and of the program itself do not turn the 403 of the refused robots into a point to look at."""
        details = {"nginx": {"/sitemap.xml": {"codes": Counter({"403": 5, "200": 20}), "referers": Counter(), "hosts": Counter(),
                                              "agents": Counter({"ClaudeBot/1.0": 4, "app-log-live (sitemap check)": 15})}}}
        f = par_id(ADV.analyze(faits(plain_4xx={"/sitemap.xml": 5}, codes_by_url={"/sitemap.xml": {"403": 5, "200": 20}}), details))
        self.assertEqual(f["sitemap-xml-403"]["severity"], ADV.INFO)
        self.assertNotIn("sitemap-xml-4xx", f)

    def test_websocket_jamais_lent_et_limite_depassee(self):
        """1.4: a websocket open for hours is not a slow request; a real request beyond limit_time_real is not described as « close to » it."""
        ws = [{"total": 4911.0, "url": "/websocket", "ip": "x", "t_sql": 0.0, "t_py": 4911.0, "t": time.time()} for _ in range(10)]
        self.assertNotIn("slow-requests", par_id(ADV.analyze(faits(slow=ws))))
        _ev, conseils, _cause = ADV.odoo_settings_advice({"workers": "13", "limit_time_real": "600"}, 6, 16000, slowest=4911)
        lent = [{"total": 4911.0, "url": "/shop", "ip": "x", "t_sql": 0.0, "t_py": 4911.0, "t": time.time()}]
        conf = {"odoo_conf": {"path": "/etc/odoo/odoo.conf", "values": {"workers": "13", "limit_time_real": "600"}, "cpus": 6, "mem_mb": 16000}}
        texte = " ".join(par_id(ADV.analyze(faits(slow=lent), conf))["slow-requests"]["advice"])
        self.assertIn("more than limit_time_real=600", texte)
        self.assertNotIn("close to limit_time_real", texte)

    def test_sitemap_xml_403_et_404(self):
        f = par_id(ADV.analyze(faits(plain_4xx={"/sitemap.xml": 12}, codes_by_url={"/sitemap.xml": {"403": 12}})))
        self.assertEqual(f["sitemap-xml-403"]["severity"], ADV.INFO)
        f = par_id(ADV.analyze(faits(plain_4xx={"/sitemap.xml": 5}, codes_by_url={"/sitemap.xml": {"404": 5}})))
        self.assertEqual(f["sitemap-xml-4xx"]["severity"], ADV.LOOK)

    def test_5xx_passerelle_ou_erreur_interne(self):
        f = par_id(ADV.analyze(faits(errors5={"/a": 6, "/b": 1}, codes_by_url={"/a": {"502": 6}, "/b": {"500": 1}})))
        self.assertEqual(f["http-5xx:/a"]["severity"], ADV.PROBLEM)
        self.assertIn("nginx got no answer", f["http-5xx:/a"]["cause"])
        self.assertEqual(f["http-5xx:/b"]["severity"], ADV.LOOK)
        self.assertIn("internal error", f["http-5xx:/b"]["cause"])

    def test_erreurs_odoo_connues_et_trace(self):
        e = [erreur("ERROR", "odoo.addons.web.controllers.binary", ".map should have been generated through debug assets"),
             erreur("ERROR", "odoo.http", "Exception during request handling."),
             erreur("WARNING", "odoo.http", "<function x> called ignoring args {'token'}"),
             erreur("WARNING", "odoo.models", "un avertissement inconnu"),
             erreur("CRITICAL", "odoo.service", "inconnu")]
        trace = ADV.odoo_trace(TRACE, "odoo.http", "Exception during request handling.")
        f = par_id(ADV.analyze(faits(odoo_errors=e), {"tracebacks": {("ERROR", "odoo.http", "Exception during request handling."): trace}}))
        carte = next(v for k, v in f.items() if k.startswith("odoo:odoo.addons.web"))
        self.assertEqual(carte["severity"], ADV.INFO)
        exc = f["odoo:odoo.http:KeyError"]
        self.assertEqual(exc["severity"], ADV.LOOK)
        self.assertIn("programming error", exc["cause"])
        self.assertTrue(any("rlq_event_extra" in x for x in exc["evidence"]))
        self.assertFalse(any(k.startswith("odoo:odoo.models") for k in f))        # avertissement inconnu : pas de conseil
        crit = f["odoo:odoo.service:inconnu"]
        self.assertEqual(crit["severity"], ADV.PROBLEM)
        self.assertTrue(any("key E" in a for a in crit["advice"]))               # trace introuvable : touche E

    def test_conflits_courriels_lenteurs_bannissements_formulaires_latence(self):
        slow_sql = [{"total": 6, "url": "/shop", "ip": "x", "t_sql": 5.0, "t_py": 1.0} for _ in range(5)]
        f = par_id(ADV.analyze(faits(final_failures=3, failure_codes={"40001": 3}, conflicts=60, mails=1,
                                     odoo_errors=[erreur("ERROR", "odoo.addons.base.models.ir_mail_server", "550 5.1.1 user unknown")],
                                     slow=slow_sql, to_ban=[("1.2.3.4", "x [1.2.3.4]", "27 suspicious requests")], not_proposed=[("5.6.7.8", "cdn", "relay")],
                                     account_ips={"a": 6, "b": 1, "c": 1, "d": 1, "e": 1}, requests=20000, latency_n=30)))
        self.assertEqual(f["final-conflicts"]["severity"], ADV.PROBLEM)
        self.assertEqual(f["many-retries"]["severity"], ADV.INFO)
        self.assertTrue(any("recipient address does not exist" in x for x in f["mail-failures"]["evidence"]))      # 1.7: hints by pattern
        self.assertIn("database", f["slow-requests"]["cause"])
        self.assertEqual(f["slow-requests"]["severity"], ADV.PROBLEM)
        self.assertTrue(any("white list" in a for a in f["ban-pending"]["advice"]))
        self.assertEqual(f["ban-held"]["severity"], ADV.INFO)
        self.assertEqual(f["account-forms"]["severity"], ADV.LOOK)
        self.assertEqual(f["latency-sample"]["severity"], ADV.INFO)

    def test_cache_froid(self):
        cold = [{"total": 6, "url": "/web/assets/1/web.assets.js", "ip": "x", "t_sql": 0.1, "t_py": 5.0}] * 3
        self.assertIn("cold cache", par_id(ADV.analyze(faits(slow=cold)))["slow-requests"]["cause"])

    def test_une_regle_en_erreur_n_arrete_pas_les_autres(self):
        f = par_id(ADV.analyze(faits(errors5=None, to_ban=[("1", "x", "y")], gone_404=5)))
        self.assertTrue(any(k.startswith("advisor-rule-failed:") for k in f))
        self.assertIn("ban-pending", f)

    def test_ordre_par_gravite(self):
        f = ADV.analyze(faits(errors5={"/a": 6}, gone_404={"/ev": 1}, to_ban=[("1", "x", "y")]))
        self.assertEqual([x["severity"] for x in f], sorted([x["severity"] for x in f], reverse=True))


class Historique(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.path = os.path.join(self.d, "advisor-history.json")

    def tour(self, findings, session, t):
        h = ADV.History(self.path)
        trend = h.record(findings, session, t)
        self.assertTrue(h.save())
        return trend

    def f(self, *items):
        return [{"id": i, "severity": ADV.LOOK, "title": "T " + i, "count": c, "evidence": [], "cause": "", "advice": []} for i, c in items]

    def test_nouveau_recurrent_calme_regle_priorites(self):
        t0 = time.time()
        r = self.tour(self.f(("a", 2), ("b", 1)), "s1", t0)
        self.assertIsNone(r["previous"])
        self.assertEqual(r["tags"], {"a": ("new", 0), "b": ("new", 0)})
        r = self.tour(self.f(("a", 2), ("b", 3)), "s1", t0 + 60)                   # même session : a n'a pas bougé, b a grandi
        self.assertEqual(r["tags"]["a"], ("quiet", 0))
        self.assertEqual(r["tags"]["b"], ("streak", 2))
        r = self.tour(self.f(("b", 1), ("c", 1)), "s2", t0 + 120)                  # autre session : a a disparu
        self.assertEqual(r["tags"]["c"], ("new", 0))
        self.assertEqual(r["tags"]["b"], ("streak", 3))
        self.assertEqual(r["resolved"], [])                                         # a n'avait rien de nouveau au tour précédent
        r = self.tour(self.f(("c", 1)), "s3", t0 + 180)
        self.assertEqual(r["resolved"], ["T b"])
        self.assertEqual(r["top"][0], ("T b", 3))
        self.assertEqual(r["runs"], 4)
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

    def test_revenu_apres_une_absence(self):
        t0 = time.time()
        self.tour(self.f(("a", 1)), "s1", t0)
        self.tour(self.f(("z", 1)), "s2", t0 + 1)
        r = self.tour(self.f(("a", 1)), "s3", t0 + 2)
        self.assertEqual(r["tags"]["a"], ("back", 2))

    def test_fichier_illisible_vieux_et_limite(self):
        with open(self.path, "w") as f:
            f.write("{pas du json")
        h = ADV.History(self.path)
        self.assertIsNotNone(h.error)
        self.assertEqual(h.data["runs"], [])
        vieux = time.time() - (ADV.HISTORY_MAX_DAYS + 1) * 86400
        with open(self.path, "w") as f:
            json.dump({"runs": [{"t": vieux, "session": "x", "counts": {"a": 1}, "new": {"a": 1}}] + [{"t": time.time() - 10, "session": str(i), "new": {}} for i in range(ADV.HISTORY_MAX_RUNS + 5)]}, f)
        h = ADV.History(self.path)
        r = h.record(self.f(("a", 1)), "neuve")
        self.assertEqual(r["tags"]["a"], ("new", 0))                                # l'analyse trop vieille est oubliée
        self.assertEqual(len(h.data["runs"]), ADV.HISTORY_MAX_RUNS)
        self.assertFalse(ADV.History(None).save())

    def test_affichage(self):
        findings = ADV.analyze(faits(gone_404={"/ev": 1}, to_ban=[("1", "x [1]", "27 suspicious requests")]))
        h = ADV.History(self.path)
        lignes = ADV.render(findings, h.record(findings, "s"), history_path=self.path)
        texte = "\n".join(lignes)
        self.assertIn("Summary: 0 problems, 1 to look at", texte)
        self.assertIn("First analysis kept", texte)
        self.assertIn("[new]", texte)
        self.assertIn("→ key b", texte)
        self.assertIn(self.path, texte)
        self.assertIn("History not kept: lecture seule", "\n".join(ADV.render(findings, {}, history_error="lecture seule")))


class Catalogue(unittest.TestCase):
    """lang/_advisor.fr.po : chaque texte passé à tr() a sa traduction, chaque entrée existe dans le code, les {variables} sont conservées."""

    def test_catalogue_complet_et_a_jour(self):
        source = open(os.path.join(SCRIPTS_DIR, "apps", "_advisor.py"), encoding="utf-8").read()
        arbre = ast.parse(source)
        textes = set()
        for n in ast.walk(arbre):
            if isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str) \
                    and (getattr(n.func, "id", None) == "tr" or getattr(n.func, "attr", None) == "tr"):
                textes.add(n.args[0].value)
        for n in arbre.body:
            if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in ("KNOWN_MESSAGES", "TRACEBACK_HINTS", "SMTP_HINTS"):
                for t in n.value.elts:
                    textes.update(e.value for e in t.elts[1:] if isinstance(e, ast.Constant) and isinstance(e.value, str))
        i18n = charger("_i18n_adv", os.path.join(SCRIPTS_DIR, "apps", "_i18n.py"))
        po = os.path.join(SCRIPTS_DIR, "lang", "_advisor.fr.po")
        entrees = dict(i18n.lire_po(po))
        self.assertIn('"Source-Language: en\\n"', open(po, encoding="utf-8").read())
        self.assertEqual(sorted(t for t in textes if not entrees.get(t)), [], "textes sans traduction dans lang/_advisor.fr.po")
        self.assertEqual(sorted(k for k in entrees if k and k not in source), [], "entrées absentes du code")
        for en, fr in entrees.items():
            with self.subTest(msgid=en[:50]):
                self.assertEqual(sorted(re.findall(r"\{\w+\}", en)), sorted(re.findall(r"\{\w+\}", fr)))
                self.assertNotRegex(fr, "—")                                   # pas de tiret cadratin

    def test_traduction_francaise_par_app_log_live(self):
        live = charger("live_adv_tr", os.path.join(SCRIPTS_DIR, "app-log-live.py"))
        self.assertEqual(live.TR("Summary: {p} problems, {l} to look at, {i} for information"), "Sommaire : {p} problèmes, {l} à regarder, {i} pour information")


class FaitsEtTouche(unittest.TestCase):
    """app-log-live.py : touche z, dictionnaire de faits pour le module."""

    @classmethod
    def setUpClass(cls):
        cls.d = tempfile.mkdtemp()
        os.environ["WEB_MONITOR_STATE_DIR"] = cls.d               # jamais la vraie recommandation de web-monitor.py du serveur de test
        cls.m = charger("live_adv", os.path.join(SCRIPTS_DIR, "app-log-live.py"))

    def test_touche_z(self):
        self.assertEqual(self.m.MENU_KEYS.get(b"z"), "advise")
        self.assertIsNotNone(self.m.load_module("_advisor"))

    def test_faits(self):
        s = self.m.Stats(5.0)
        s.errors[5]["/boum"] = 2
        s.errors[4].update({"/.env": 3, "/shop/tasse": 7})
        s.http_errors = [(time.time(), 500, "/boum", "11.1.1.1"), (time.time(), 404, "/shop/tasse", "11.1.1.2")]
        s.odoo_errors[("ERROR", "odoo.http", "Exception during request handling.")] = 1
        s.odoo_errors_time[("ERROR", "odoo.http", "Exception during request handling.")] = [time.time(), time.time()]
        s.slow_requests, s.slow_info = [(6.0, "/lente", "11.1.1.3")], [(10, 1.0, 5.0, 100, time.time())]
        s.suspect_ips["11.1.1.4"] = 27
        s.account_ips["11.1.1.5"] = 2
        f = self.m.advisor_facts(s)
        self.assertEqual(f["errors5"], {"/boum": 2})
        self.assertEqual(f["plain_4xx"], {"/shop/tasse": 7})                  # requête suspecte retirée
        self.assertEqual(f["codes_by_url"]["/boum"], Counter({"500": 1}))
        self.assertEqual(f["odoo_errors"][0]["logger"], "odoo.http")
        self.assertEqual(f["slow"][0]["t_py"], 5.0)
        self.assertEqual([ip for ip, _w, _r in f["to_ban"]], ["11.1.1.4"])
        self.assertIn("suspicious requests", f["to_ban"][0][2])
        ADV.analyze(f)                                                         # le module accepte le dictionnaire tel quel

    def test_dossier_d_etat(self):
        with tempfile.TemporaryDirectory() as d:
            os.environ["APP_LOG_LIVE_STATE_DIR"] = d
            try:
                self.assertEqual(self.m.advisor_history_file(), os.path.join(d, "advisor-history.json"))
            finally:
                os.environ.pop("APP_LOG_LIVE_STATE_DIR", None)


if __name__ == "__main__":
    unittest.main()


class Version167(unittest.TestCase):
    """1.3 (app-log-live.py 1.167) : sortie vérifiée sur la vraie analyse de 14 jours du serveur — référents de son propre site, 404 comptés par nginx,
    5xx groupés par page avec la trace, balayage de vulnérabilités, nginx sans Odoo, VAPID, courriels confirmés par la base, réglages d'odoo.conf."""

    def test_referents_du_site_avec_host_entre_guillemets_et_sans_www(self):
        ligne = ('1.1.1.1 - - [04/Nov/2026:09:10:00 -0500] "GET /en_CA/appel HTTP/1.1" 404 12 "https://rencontres-linux.quebec/a-propos/x" "Mozilla/5.0" '
                 'host="www.rencontres-linux.quebec" rl=500')
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "a-access.log")
            with open(chemin, "w") as f:
                f.write(ligne + "\n" + ligne.replace('"GET', '"POST') + "\n")
            r = ADV.nginx_details([chemin], ["/en_CA/appel"])["/en_CA/appel"]
        self.assertEqual(r["hosts"], Counter({"www.rencontres-linux.quebec": 2}))       # without the quotes
        self.assertEqual(r["methods"], Counter({"GET": 1, "POST": 1}))
        self.assertEqual(ADV.internal_referers(r), Counter({"https://rencontres-linux.quebec/a-propos/x": 2}))   # same site, without www
        self.assertEqual(ADV.internal_referers({"referers": Counter({"https://autre.example/": 1}), "hosts": Counter()}, ["www.site.example"]), Counter())

    def test_404_compte_par_nginx_et_redirections_a_part(self):
        details = {"nginx": {"/en_CA/appel": {"codes": Counter({"404": 25, "403": 3, "301": 7}), "referers": Counter(), "hosts": Counter(), "agents": Counter(), "methods": Counter()}}}
        f = par_id(ADV.analyze(faits(plain_4xx={"/en_CA/appel": 20, "/en_CA/appel?x=1": 5}), details))
        lien = f["dead-link:/en_CA/appel"]
        self.assertEqual(lien["count"], 25)                                              # the 404 of nginx, the query strings grouped
        self.assertIn("404 ×25, 403 ×3", lien["evidence"][0])
        self.assertIn("7 redirections 3xx", lien["evidence"][0])

    def test_404_repond_200_maintenant_et_evenement_non_publie(self):
        details = {"now": {"/event/rencontre-119": 200, "/event/rencontre-58": 404},
                   "records": {"/event/rencontre-58": {"kind": "event", "id": 58, "name": "Rencontre", "published": False, "active": True, "end": "2026-11-03"}}}
        f = par_id(ADV.analyze(faits(gone_404={"/event/rencontre-119": 4}, plain_4xx={"/event/rencontre-58": 16}, sitemap_paths=frozenset({"/event/rencontre-119"})), details))
        self.assertEqual(f["sitemap-404-now-ok:/event/rencontre-119"]["severity"], ADV.INFO)
        mort = f["dead-link:/event/rencontre-58"]
        self.assertIn("not published", mort["cause"])
        self.assertTrue(any("event n° 58" in e and "NOT published" in e and "ended on 2026-11-03" in e for e in mort["evidence"]))

    def test_plan_du_site_wordpress(self):
        f = par_id(ADV.analyze(faits(plain_4xx={"/sitemap_index.xml": 24})))
        self.assertEqual(f["wp-sitemap:/sitemap_index.xml"]["severity"], ADV.INFO)
        self.assertNotIn("sitemap-xml-4xx", f)

    def test_5xx_groupes_par_page_balayage_et_formulaire(self):
        maintenant = time.time()
        fuzz = '/en_CA/event?search=zqzz"()((,)\').&tags=stfD'
        trace = TRACE[1:8]
        f = par_id(ADV.analyze(faits(errors5={"/en_CA/event?search=zqzz&tags=stfD": 5, fuzz: 1, "/event/125/track_proposal/post": 5},
                                     http_errors5=[(maintenant, 500, "/en_CA/event?search=zqzz&tags=stfD", "6.6.6.6")] * 5 + [(maintenant, 500, fuzz, "6.6.6.6")]
                                     + [(maintenant, 500, "/event/125/track_proposal/post", "1.2.3.4")] * 5, who={"6.6.6.6": "scan.example [6.6.6.6]"}),
                               {"traces_5xx": {"/event/125/track_proposal/post": trace}}))
        balayage = f["http-5xx:/en_CA/event"]
        self.assertEqual(balayage["count"], 6)                                           # the two URLs of the same page together
        self.assertEqual(balayage["severity"], ADV.LOOK)
        self.assertIn("vulnerability scanner", balayage["cause"])
        self.assertTrue(any("scan.example [6.6.6.6] ×6" in e for e in balayage["evidence"]))
        formulaire = f["http-5xx:/event/125/track_proposal/post"]
        self.assertEqual(formulaire["severity"], ADV.PROBLEM)
        self.assertIn("a form of the site fails", formulaire["advice"][0])
        self.assertTrue(any("KeyError" in e for e in formulaire["evidence"]))
        self.assertTrue(any("rlq_event_extra" in e for e in formulaire["evidence"]))

    def test_nginx_sans_odoo_relie_au_redemarrage(self):
        t = time.time() - 3600
        erreurs = [{"level": "ERROR", "message": f"[error] N#N: *N connect() failed (N: Connection refused) while connecting to upstream, client: N.N.N.N, request: \"GET /{x} HTTP/N.N\"",
                    "n": 10, "first": t, "last": t + 11} for x in ("a", "b")] + [{"level": "ERROR", "message": "[error] N#N: *N open() \"/x\" failed", "n": 25, "first": t, "last": t}]
        details = {"service": {"events": [(t - 9, "Stopping erplibre.service - Odoo..."), (t + 11, "Started erplibre.service - Odoo.")], "state": "active (running)"}}
        f = par_id(ADV.analyze(faits(nginx_errors=erreurs, odoo_errors=[erreur("ERROR", "error", erreurs[0]["message"], 10)]), details))
        amont = next(v for k, v in f.items() if k.startswith("nginx-upstream:"))
        self.assertEqual(amont["count"], 20)                                            # the requests of every client grouped
        self.assertEqual(amont["severity"], ADV.LOOK)
        self.assertIn("restarting", amont["cause"])
        self.assertTrue(any("Started erplibre.service" in e for e in amont["evidence"]))
        self.assertIn("nginx-errors", f)
        self.assertFalse(any(k.startswith("odoo:error") for k in f))                    # never an "Odoo error"
        sans = par_id(ADV.analyze(faits(nginx_errors=erreurs[:1])))
        self.assertEqual(next(v for k, v in sans.items() if k.startswith("nginx-upstream:"))["severity"], ADV.PROBLEM)

    def test_vapid_et_exceptions_de_toutes_les_occurrences(self):
        lignes = []
        for exc in ["odoo.addons.mail.tools.jwt.InvalidVapidError: Invalid VAPID public key"] * 3 + ["KeyError: 'tags'"]:
            lignes += ["2026-11-04 12:21:16,123 1 ERROR prod odoo.http: Exception during request handling.", "Traceback (most recent call last):", exc]
        self.assertEqual(ADV.exception_counts(lignes, "odoo.http", "Exception during request handling."),
                         Counter({"InvalidVapidError: Invalid VAPID public key": 3, "KeyError: 'tags'": 1}))
        vapid = ["2026-11-04 12:21:16,123 1 ERROR prod odoo.http: Exception during request handling.", "Traceback (most recent call last):",
                 '  File "/opt/odoo/odoo/addons/mail/models/mail_push_device.py", line 49, in register_devices', "odoo.addons.mail.tools.jwt.InvalidVapidError: Invalid VAPID public key"]
        cle = ("ERROR", "odoo.http", "Exception during request handling.")
        f = par_id(ADV.analyze(faits(odoo_errors=[erreur(*cle, n=20)]), {"tracebacks": {cle: vapid}, "exceptions": {cle: Counter({"InvalidVapidError: Invalid VAPID public key": 20})},
                                                                         "vapid": "2026-10-27 04:31 UTC"}))
        e = f["odoo:odoo.http:odoo.addons.mail.tools.jwt.InvalidVapidError"]
        self.assertEqual(e["severity"], ADV.INFO)
        self.assertIn("VAPID public key", e["cause"])
        self.assertTrue(any("2026-10-27 04:31 UTC" in x for x in e["evidence"]))
        melange = par_id(ADV.analyze(faits(odoo_errors=[erreur(*cle, n=20)]), {"tracebacks": {cle: vapid}, "exceptions": {cle: Counter({"KeyError: 'x'": 15, "InvalidVapidError: y": 5})}}))
        m = next(v for k, v in melange.items() if k.startswith("odoo:odoo.http"))
        self.assertNotIn("VAPID public key", m["cause"])                                 # the last occurrence is not the usual one: no cause drawn from it
        self.assertTrue(any("KeyError: 'x' ×15" in x for x in m["evidence"]))

    def test_trace_pres_d_une_heure(self):
        t = ADV.calendar.timegm((2026, 11, 4, 12, 21, 16, 0, 0, 0))
        self.assertTrue(ADV.trace_near(TRACE, t + 2, 3)[-1].startswith("KeyError"))
        self.assertEqual(ADV.trace_near(TRACE, t + 60, 3), [])

    def test_courriels_confirmes_ou_non_par_la_base(self):
        base = {"days": 14, "exception": 0, "outgoing": 0, "sent": 120, "reasons": [], "servers": ["smtp.example:587 (starttls)"]}
        f = par_id(ADV.analyze(faits(mails=40), {"mail_db": base}))
        self.assertNotIn("mail-failures", f)
        self.assertEqual(f["mail-failures-not-confirmed"]["severity"], ADV.INFO)
        f = par_id(ADV.analyze(faits(mails=0), {"mail_db": dict(base, exception=3, reasons=[("550 5.1.1 user unknown", 3)])}))
        echec = f["mail-failures"]
        self.assertEqual(echec["count"], 3)
        self.assertEqual(echec["fix"], ("mail", 14))
        self.assertTrue(any("recipient address does not exist" in x for x in echec["advice"]))       # 1.7: solution tracks in the recommendations
        f = par_id(ADV.analyze(faits(), {"mail_db": dict(base, outgoing=30)}))
        self.assertEqual(f["mail-queue"]["severity"], ADV.LOOK)

    def test_reglages_d_odoo_workers_et_limites(self):
        _ev, conseils, cause = ADV.odoo_settings_advice({"workers": "0"}, 4, 8000)
        self.assertEqual(cause, "workers=0")
        self.assertEqual(conseils[0][:2], ("workers0", 9))
        _ev, conseils, cause = ADV.odoo_settings_advice({"workers": "20", "limit_time_real": "120"}, 2, 16000, slowest=110)
        self.assertEqual(cause, "too-many")
        self.assertIn(("too-many", 5, 20), conseils)
        self.assertIn(("limit-real", 110, 120), conseils)
        ev, conseils, _c = ADV.odoo_settings_advice({"workers": "4", "limit_memory_soft": "2147483648"}, 4, 1500)
        self.assertIn("limit_memory_soft=2048 MB", ev[0])
        self.assertTrue(any(c[0] == "memory" for c in conseils))
        lent = [{"total": 6, "url": "/web/login", "ip": "x", "t_sql": 0.1, "t_py": 5.9, "t": time.time()}] * 6
        f = par_id(ADV.analyze(faits(slow=lent), {"odoo_conf": {"path": "/etc/odoo/odoo.conf", "values": {"workers": "0"}, "cpus": 2, "mem_mb": 4000}}))
        s = f["slow-requests"]
        self.assertTrue(any("/etc/odoo/odoo.conf" in e and "workers=0" in e for e in s["evidence"]))
        self.assertTrue(any("workers=0: Odoo runs in ONE process" in a for a in s["advice"]))
        self.assertTrue(any("Busiest hours" in e for e in s["evidence"]))
        self.assertIsNone(s["fix"])

    def test_lenteurs_apres_un_demarrage_prechauffage(self):
        t = time.time() - 3000
        lent = [{"total": 7, "url": "/", "ip": "x", "t_sql": 0.1, "t_py": 6.9, "t": t + 60}] * 4
        f = par_id(ADV.analyze(faits(slow=lent), {"service": {"events": [(t, "Started erplibre.service - Odoo.")]}}))
        self.assertIn("cold cache", f["slow-requests"]["cause"])
        self.assertEqual(f["slow-requests"]["fix"], ("warmup", None))

    def test_formulaires_consultes_seulement(self):
        details = {"nginx": {"/web/signup": {"methods": Counter({"GET": 150}), "codes": Counter(), "referers": Counter(), "hosts": Counter(), "agents": Counter()}},
                   "signup": {"scope": "b2c", "new_users": 0}}
        f = par_id(ADV.analyze(faits(account_ips={"a": 150, "b": 7}, account_urls=["/web/signup"]), details))
        self.assertEqual(f["account-forms"]["severity"], ADV.INFO)
        self.assertIn("no account attempts", f["account-forms"]["cause"])
        self.assertTrue(any("free (anyone can create an account)" in e for e in f["account-forms"]["evidence"]))

    def test_correction_proposee_affichee(self):
        findings = ADV.analyze(faits(to_ban=[("1.2.3.4", "x [1.2.3.4]", "3 suspicious requests")]))
        ban = par_id(findings)["ban-pending"]
        self.assertEqual(ban["fix"][0], "ban")
        self.assertEqual(ban["fix"][1][0][0], "1.2.3.4")
        texte = "\n".join(ADV.render(findings, {}, apply_hint="correction offered by --apply"))
        self.assertIn("⚙ correction offered by --apply", texte)



class Version17(unittest.TestCase):
    """apps/_advisor.py 1.7 (app-log-live.py 1.178): review of the night report of 2026-11-09. Push duplicates apart, interruption over, reason of a stop,
    memory risk, one address asking one page in a loop, failed e-mails one by one with solution tracks, simultaneous slow requests, accounts that never
    signed in, timeline, confirmed causes. Invented data only (documentation addresses, example.org)."""

    def test_doublon_d_abonnement_push_n_est_pas_un_conflit(self):
        known = next(k for k in ADV.KNOWN_MESSAGES if re.search(k[0], "odoo.sql_db: bad query: INSERT INTO \"mail_push_device\" (\"endpoint\") VALUES (...)", re.I))
        self.assertIn("push notifications", known[2])
        self.assertNotIn("retried", known[2])
        autre = next(k for k in ADV.KNOWN_MESSAGES if re.search(k[0], "odoo.sql_db: bad query: UPDATE res_partner SET x = 1", re.I))
        self.assertEqual(autre[1], ADV.LOOK)                                    # a bad query of another kind is no longer "harmless" by default
        f = par_id(ADV.analyze(faits(push_duplicates=5, push_duplicate_warnings=5, push_times=[time.time() - 600, time.time()])))
        p = f["push-duplicates"]
        self.assertEqual(p["severity"], ADV.INFO)
        self.assertTrue(p["confirmed"])
        self.assertTrue(any("unique violation" in e for e in p["evidence"]))
        self.assertIn("Cause (confirmed): ", "\n".join(ADV.render([p], {})))

    def test_exemple_brut_d_une_erreur_regroupee(self):
        e = dict(erreur("ERROR", "odoo.addons.web.controllers.binary", ".map should have been generated through debug assets, (version Nfe most likely outdated)"),
                 raw=".map should have been generated through debug assets, (version 5fe3a1 most likely outdated)")
        f = next(v for k, v in par_id(ADV.analyze(faits(odoo_errors=[e]))).items() if k.startswith("odoo:"))
        self.assertTrue(any("version 5fe3a1" in x for x in f["evidence"]))

    def test_interruption_terminee_et_raison_de_l_arret(self):
        now = time.time()
        first, last = now - 2 * 86400, now - 2 * 86400 + 8 * 3600
        nginx = [{"level": "ERROR", "message": "[error] N#N: *N connect() failed (N: Connection refused) while connecting to upstream, client: 192.0.2.1", "n": 33,
                  "first": first, "last": last}]
        service = {"events": [(last - 9, "Started erplibre.service - Odoo.")], "state": "active (running), started on Sat"}
        f = par_id(ADV.analyze(faits(nginx_errors=nginx, end=now, requests_start=last + 3600), {"service": service}))
        u = next(v for k, v in f.items() if k.startswith("nginx-upstream:"))
        self.assertEqual(u["severity"], ADV.INFO)
        self.assertIn("(over)", u["title"])
        self.assertTrue(any("8 h 00 min" in e for e in u["evidence"]))
        self.assertTrue(any("Before the first request read" in e for e in u["evidence"]))
        tue = {"events": [(last - 30, "erplibre.service: Main process exited, code=killed, status=9/KILL"), (last - 29, "erplibre.service: Failed with result 'oom-kill'."),
                          (last - 9, "Started erplibre.service - Odoo.")], "state": "active (running)"}
        u = next(v for k, v in par_id(ADV.analyze(faits(nginx_errors=nginx, end=now), {"service": tue})).items() if k.startswith("nginx-upstream:"))
        self.assertEqual(u["severity"], ADV.LOOK)                             # over, but killed by the system: still to look at (not history)
        self.assertTrue(u["confirmed"])
        self.assertTrue(any("oom-kill" in e for e in u["evidence"]))

    def test_risque_de_memoire(self):
        conf = {"path": "/etc/odoo/odoo.conf", "values": {"workers": "13", "max_cron_threads": "2", "limit_memory_hard": str(1196 * 1048576),
                                                         "limit_memory_soft": str(1016 * 1048576)}, "cpus": 6, "mem_mb": 16384}
        f = par_id(ADV.analyze(faits(), {"odoo_conf": conf, "memory": {"limit_mb": None, "oom_kills": None, "kernel": []}}))
        m = f["memory-risk"]
        self.assertEqual(m["severity"], ADV.LOOK)
        self.assertTrue(any("17940 MB" in e and "16384 MB" in e for e in m["evidence"]))
        self.assertTrue(any("limit_memory_hard to about 768 MB" in a and "13 workers + 2 cron + 1 gevent" in a for a in m["advice"]))      # 1.8: as nginx-hardening.sh 2.82
        dev = dict(conf, values=dict(conf["values"], workers="3", limit_memory_hard=str(5197 * 1048576)))
        m = par_id(ADV.analyze(faits(), {"odoo_conf": dev, "memory": {"other_mb": 453}}))["memory-risk"]
        self.assertTrue(any("limit_memory_hard to about 2048 MB" in a for a in m["advice"]))
        self.assertTrue(any("453 MB" in e and "2457 MB" in e for e in m["evidence"]))
        f = par_id(ADV.analyze(faits(), {"odoo_conf": conf, "memory": {"limit_mb": 16384, "oom_kills": 2, "kernel": [(time.time(), "Out of memory: Killed process 1234 (python3)")]}}))
        self.assertEqual(f["memory-risk"]["severity"], ADV.PROBLEM)
        self.assertTrue(f["memory-risk"]["confirmed"])
        petit = dict(conf, values=dict(conf["values"], workers="4"))
        self.assertNotIn("memory-risk", par_id(ADV.analyze(faits(), {"odoo_conf": petit, "memory": {}})))

    def test_meme_page_en_boucle(self):
        who = {"203.0.113.44": "host-44.example.net [203.0.113.44] CD (République démocratique du Congo)"}
        hot = [{"ip": "203.0.113.44", "url": "/web/dataset/call_kw/ir.config_parameter/get_web_dialog_size_config", "n": 1606, "ip_total": 1613,
                "codes": {"200": 1606}, "known": False}]
        f = par_id(ADV.analyze(faits(hot_pairs=hot, who=who)))
        h = next(v for k, v in f.items() if k.startswith("hot-pair:"))
        self.assertEqual(h["severity"], ADV.LOOK)
        self.assertIn("République démocratique du Congo", h["title"])
        self.assertIn("valid Odoo session", h["cause"])
        refuse = [dict(hot[0], codes={"303": 1606})]
        h = next(v for k, v in par_id(ADV.analyze(faits(hot_pairs=refuse, who=who))).items() if k.startswith("hot-pair:"))
        self.assertEqual(h["severity"], ADV.INFO)
        connu = [dict(hot[0], known=True)]
        h = next(v for k, v in par_id(ADV.analyze(faits(hot_pairs=connu, who=who))).items() if k.startswith("hot-pair:"))
        self.assertIn("known person", h["cause"])

    def test_courriels_en_echec_un_par_un_avec_pistes(self):
        t = time.mktime((2026, 11, 8, 14, 32, 0, 0, 0, -1))
        base = {"days": 2, "exception": 2, "outgoing": 0, "sent": 63, "reasons": [("Échec d'envoi de l'e-mail", 2)], "servers": ["mail.example.org:587 (starttls)"] * 2}
        failed = [{"id": 9, "instant": t, "sujet": "Inscription confirmée", "destinataires": "ana@example.org", "raison": "Échec d'envoi de l'e-mail", "base": "prod"},
                  {"id": 8, "instant": t - 60, "sujet": "Rappel", "destinataires": "bob@example.org", "raison": "Échec d'envoi de l'e-mail", "base": "prod"}]
        servers = [{"id": 1, "nom": "Principal", "hote": "mail.example.org", "port": "587", "chiffrement": "starttls", "filtre": "", "actif": True},
                   {"id": 3, "nom": "Copie", "hote": "mail.example.org", "port": "587", "chiffrement": "starttls", "filtre": "", "actif": True}]
        m = par_id(ADV.analyze(faits(), {"mail_db": base, "mail_failed": failed, "mail_servers": servers}))["mail-failures"]
        self.assertTrue(any("2026-11-08 14:32" in e and "Inscription confirmée" in e and "ana@example.org" in e for e in m["evidence"]))
        self.assertFalse(any(e.startswith("Cause: ") for e in m["evidence"]))      # the full list replaces the generic count
        self.assertTrue(any("generic message" in a for a in m["advice"]))
        self.assertTrue(any("2 outgoing servers for mail.example.org:587" in a for a in m["advice"]))
        self.assertTrue(m["confirmed"])
        auth = [dict(failed[0], raison="Échec d'envoi de l'e-mail SMTPAuthenticationError: (535, b'5.7.8 Username and Password not accepted')")]
        m = par_id(ADV.analyze(faits(), {"mail_db": base, "mail_failed": auth, "mail_servers": servers[:1]}))["mail-failures"]
        self.assertTrue(any("user name or the password" in a for a in m["advice"]))
        self.assertFalse(any("generic message" in a for a in m["advice"]))

    def test_lenteurs_simultanees_et_actions_planifiees(self):
        t = time.time() - 4000
        lent = [{"total": 21.9, "url": "/blog/presentations-3/tag/ia-17", "ip": "198.51.100.201", "t_sql": 21.7, "t_py": 0.2, "sql_n": 36, "t": t},
                {"total": 10.6, "url": "/event/rencontre-103/register", "ip": "198.51.100.182", "t_sql": 10.4, "t_py": 0.2, "sql_n": 33, "t": t + 14}]
        f = par_id(ADV.analyze(faits(slow=lent), {"crons": [(t - 30, "Mail: Email Queue Manager")]}))
        s = f["slow-requests"]
        self.assertIn("same moment", s["cause"])
        self.assertTrue(any("within 14 s" in e for e in s["evidence"]))
        self.assertTrue(any("Email Queue Manager" in e for e in s["evidence"]))
        self.assertTrue(any("21.9 s" in e and "SQL 21.7 s (36 queries)" in e for e in s["evidence"]))
        bouton = [{"total": 8.0, "url": "/web/dataset/call_button/rlq.survey.report.wizard/action_generate", "ip": "x", "t_sql": 7.0, "t_py": 1.0, "t": t}]
        s = par_id(ADV.analyze(faits(slow=bouton)))["slow-requests"]
        self.assertTrue(any("action action_generate of the model rlq.survey.report.wizard" in e for e in s["evidence"]))

    def test_comptes_jamais_connectes(self):
        comptes = [{"t": time.time() - i * 600, "domain": "example.org", "logins": 0} for i in range(4)] + [{"t": time.time(), "domain": "example.net", "logins": 2}]
        details = {"nginx": {"/web/signup": {"methods": Counter({"GET": 8})}}, "signup": {"scope": "b2c", "new_users": 5, "accounts": comptes}}
        f = par_id(ADV.analyze(faits(account_ips={"192.0.2.%d" % i: 2 for i in range(9)}, account_urls=["/web/signup"]), details))
        a = f["account-forms"]
        self.assertEqual(a["severity"], ADV.LOOK)
        self.assertIn("never signed in: 4", a["title"])
        self.assertTrue(any("not found in the access logs read: 10" in e for e in a["evidence"]))
        self.assertTrue(any("@example.net" in e and "signed in 2 times since" in e for e in a["evidence"]))

    def test_bannies_pendant_la_periode_et_chronologie(self):
        t = time.time() - 1800
        facts = faits(banned_during=[("192.0.2.77", t, ["nginx-badrequests"])], who={"192.0.2.77": "scanner.example.net [192.0.2.77]"},
                      slow=[{"total": 6.0, "url": "/shop", "ip": "x", "t_sql": 5.0, "t_py": 1.0, "t": t - 60}], push_times=[t - 120, t - 10])
        f = par_id(ADV.analyze(facts))
        self.assertEqual(f["banned-during"]["severity"], ADV.INFO)
        events = ADV.timeline(facts, {"service": {"events": [(t - 300, "Started erplibre.service")]}})
        texts = [x for _t, x in events]
        self.assertEqual([round(x) for x, _ in events], sorted(round(x) for x, _ in events))
        self.assertTrue(texts[0].startswith("service: "))
        self.assertTrue(any("ban of scanner.example.net" in x for x in texts))
        self.assertTrue(any(x.startswith("slow request: 6.0 s") for x in texts))


class Pays(unittest.TestCase):
    """apps/_countries.py (app-log-live.py 1.178): full names of the countries, French and English."""

    def test_noms_complets(self):
        c = charger("_countries_t", os.path.join(SCRIPTS_DIR, "apps", "_countries.py"))
        self.assertEqual(c.label("CD"), "CD (République démocratique du Congo)")
        self.assertEqual(c.label("cd", "en"), "CD (Democratic Republic of the Congo)")
        self.assertEqual(c.label("US"), "US (États-Unis)")
        self.assertEqual(c.label("ZZ"), "ZZ")
        self.assertEqual(c.label(""), "")
        self.assertGreaterEqual(len(c.NAMES), 249)
        self.assertFalse([k for k, (fr, en) in c.NAMES.items() if not fr or not en or "—" in fr + en])


class Version18(unittest.TestCase):
    """apps/_advisor.py 1.8 (app-log-live.py 1.179): verification of the exports of DEV and PROD of 2026-11-09. Invented data only."""

    def test_evenement_a_venir_se_termine(self):
        futur = time.strftime("%Y-%m-%d", time.localtime(time.time() + 20 * 86400))
        lignes, _etat = ADV.Analyzer().site_lines("/event/x-1", {"records": {"/event/x-1": {"kind": "event", "id": 1, "name": "Dîner", "published": False, "active": True, "end": futur}}})
        self.assertTrue(any("ends on " + futur in l for l in lignes))
        lignes, _etat = ADV.Analyzer().site_lines("/event/x-1", {"records": {"/event/x-1": {"kind": "event", "id": 1, "name": "Dîner", "published": False, "active": True, "end": "2020-01-01"}}})
        self.assertTrue(any("ended on 2020-01-01" in l for l in lignes))

    def test_messages_connus_csrf_et_dbfilter(self):
        for texte in ("odoo.http: No CSRF validation token provided for path '/'", "odoo.http: Logged into database 'x', but dbfilter rejects it; logging session out."):
            self.assertEqual(next(k for k in ADV.KNOWN_MESSAGES if re.search(k[0], texte, re.I))[1], ADV.INFO)

    def test_limite_de_messages_par_session_smtp(self):
        base = {"days": 2, "exception": 2, "outgoing": 0, "sent": 62, "reasons": []}
        motif = "Échec d'envoi de l'e-mail SMTPDataError: (452, b'4.4.5 Maximum number of messages per session exceeded.')"
        echecs = [{"id": 1, "instant": time.time() - 3 * 86400, "sujet": "Test", "destinataires": ", ".join(f"p{i}@example.org" for i in range(12)), "raison": motif, "base": "prod"}]
        m = par_id(ADV.analyze(faits(start=time.time() - 86400), {"mail_db": base, "mail_failed": echecs}))["mail-failures"]
        self.assertTrue(m["advice"][0].startswith("the mail server accepts only a few e-mails per SMTP connection"))
        self.assertTrue(any("(12 recipients)" in e and "before the window, still not resent" in e for e in m["evidence"]))

    def test_doublons_push_apres_un_conflit(self):
        p = par_id(ADV.analyze(faits(push_duplicates=15, push_duplicate_warnings=15, push_after_conflict=15)))["push-duplicates"]
        self.assertTrue(any(e.startswith("15 of them came less than 5 s after a retried conflict") for e in p["evidence"]))

    def test_chronologie_lignes_d_odoo_du_journal(self):
        t = time.time() - 600
        events = ADV.timeline(faits(), {"service": {"events": [], "odoo_events": [(t, "odoo.addons.auto_backup.models.db_backup: Starting backup")]}})
        self.assertEqual(events[0][1], "Odoo (journal): odoo.addons.auto_backup.models.db_backup: Starting backup")


class Version19(unittest.TestCase):
    """apps/_advisor.py 1.9 (app-log-live.py 1.180): findings checked by an administrator, Odoo device log (res.device.log). Invented data only."""

    HOT = [{"ip": "203.0.113.44", "url": "/web/dataset/call_kw/ir.config_parameter/get_web_dialog_size_config", "n": 3198, "ip_total": 3226, "codes": {"200": 3198}, "known": False}]
    DEVICES = {"203.0.113.44": [{"login": "benevole@example.org", "name": "Bénévole Exemple", "share": False, "platform": "android", "browser": "chrome",
                                 "last": time.time() - 600, "revoked": False}]}

    def test_session_d_un_utilisateur_du_site(self):
        h = next(v for k, v in par_id(ADV.analyze(faits(hot_pairs=self.HOT), {"devices": self.DEVICES})).items() if k.startswith("hot-pair:"))
        self.assertEqual(h["severity"], ADV.INFO)
        self.assertTrue(h["confirmed"])
        self.assertIn("Bénévole Exemple", h["cause"])
        self.assertTrue(any("benevole@example.org" in e and "android chrome" in e for e in h["evidence"]))
        self.assertTrue(any("--ack " + ADV.ack_code(h["id"]) in a for a in h["advice"]))

    def test_pas_de_bannissement_d_une_adresse_avec_session(self):
        f = par_id(ADV.analyze(faits(to_ban=[("203.0.113.44", "x [203.0.113.44]", "3 suspicious requests"), ("192.0.2.9", "y [192.0.2.9]", "5 suspicious requests")]),
                               {"devices": self.DEVICES}))
        self.assertEqual([ip for ip, _w, _r in f["ban-pending"]["fix"][1]], ["192.0.2.9"])
        self.assertEqual(f["ban-held-session"]["severity"], ADV.LOOK)

    def test_constats_verifies(self):
        d = tempfile.mkdtemp()
        acks = ADV.Acknowledgements(os.path.join(d, ADV.ACK_FILE))
        findings = ADV.analyze(faits(hot_pairs=self.HOT))
        hot = next(f for f in findings if f["id"].startswith("hot-pair:"))
        code = ADV.ack_code(hot["id"])
        self.assertRegex(code, r"^[0-9a-f]{6}$")
        acks.add(code, hot["id"], hot["title"], "un bénévole, boucle du client web", "martial", 30, count=3198)
        self.assertTrue(acks.save())
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(d, ADV.ACK_FILE)).st_mode), 0o600)
        active = ADV.Acknowledgements(os.path.join(d, ADV.ACK_FILE)).active()
        shown, checked = ADV.split_acknowledged(findings, active)
        self.assertNotIn(hot["id"], [f["id"] for f in shown])
        texte = "\n".join(ADV.render(shown, {}, acknowledged=checked))
        self.assertIn("Checked by an administrator, left out of the summary: 1", texte)
        self.assertIn("un bénévole, boucle du client web", texte)
        self.assertIn(f"[{code}]", texte)
        plus = [dict(f, count=7000) if f["id"] == hot["id"] else f for f in findings]          # more than twice the count of the check: back
        shown, checked = ADV.split_acknowledged(plus, active)
        retour = next(f for f in shown if f["id"] == hot["id"])
        self.assertIn("to look at again", "\n".join(ADV.render([retour], {})))
        self.assertEqual(ADV.split_acknowledged(findings, ADV.Acknowledgements(os.path.join(d, ADV.ACK_FILE)).active(time.time() + 31 * 86400))[1], [])


class OdooRuntime110(unittest.TestCase):
    """1.10 : constats odoo-conf-not-applied, odoo-conf-command-line et odoo-processes (règle rule_odoo_runtime)."""

    def test_constats(self):
        rt = {"start": 1000.0, "file_mtime": 2000.0, "known": True, "after_start": True, "changed": [("limit_memory_hard", "5197", "2048")],
              "overrides": [("workers", "3", "2")], "processes": 5, "expected": 7}
        f = par_id(ADV.analyze(faits(), {"odoo_runtime": rt, "service": {"name": "odoo.service"}}))
        self.assertEqual(f["odoo-conf-not-applied"]["severity"], ADV.LOOK)
        self.assertIn("limit_memory_hard: in effect 5197, in the file 2048", " ".join(f["odoo-conf-not-applied"]["evidence"]))
        self.assertIn("systemctl restart odoo.service", " ".join(f["odoo-conf-not-applied"]["advice"]))
        self.assertEqual(f["odoo-conf-command-line"]["severity"], ADV.INFO)
        self.assertEqual(f["odoo-processes"]["severity"], ADV.INFO)

    def test_inconnu_et_rien(self):
        f = par_id(ADV.analyze(faits(), {"odoo_runtime": {"start": 1000.0, "file_mtime": 2000.0, "known": False, "after_start": True, "changed": []}}))
        self.assertEqual(f["odoo-conf-not-applied"]["severity"], ADV.INFO)
        f = par_id(ADV.analyze(faits(), {"odoo_runtime": {"start": 1000.0, "file_mtime": 900.0, "known": True, "changed": [], "processes": 7, "expected": 7}}))
        self.assertNotIn("odoo-conf-not-applied", f)
        self.assertNotIn("odoo-processes", f)
