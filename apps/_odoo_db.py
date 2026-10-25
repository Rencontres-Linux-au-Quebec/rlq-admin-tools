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
# _odoo_db.py - users of an Odoo database (login identifier, UID, name, internal or portal/public), read in
# READ-ONLY mode from PostgreSQL (runuser -u postgres -- psql). Used by web-monitor.py (--list-users --details: UID)
# and app-log-live.py (name of the person behind an IP address). Reads ONLY, never a password read - except remettre_en_attente
# (odoo-mail-retry.py, with confirmation): the only write, which changes only the state of e-mails that failed to send.
# 1.14: two other writes, always after confirmation and guarded in the SQL itself: set_user_active (web-monitor.py --ban-odoo-user /
# --unban-odoo-user: account archived or restored) and fix_registration_email (odoo-mail-retry.py: corrected address of a registration).
#
#
# Usage (normalement appele par les programmes de la suite) :
#   python3 apps/_odoo_db.py BASE         liste des utilisateurs de la base (UID, identifiant, nom, type)
#   python3 apps/_odoo_db.py --verbose BASE   ... en affichant la commande psql
#   python3 apps/_odoo_db.py --modules BASE  installed modules (name, state, version, modified UTC, author; tabs)
#   python3 apps/_odoo_db.py --version

import json
import os
import re
import subprocess
import sys

__version__ = "1.21.20261022.231529"
# 1.20: PostgreSQL commands run as the postgres user: runuser under root, "sudo -n" otherwise (the account needs no root)
POSTGRES_RUN = ["runuser", "-u", "postgres", "--"] if os.geteuid() == 0 else ["sudo", "-n", "-u", "postgres", "--"]

VERBOSE = False     # --verbose : la commande psql est affichee avant son execution
SEP = "\x1f"
REQUETE = ("SELECT u.id, u.login, replace(replace(COALESCE(p.name::text, ''), E'\n', ' '), E'\r', ' '), u.share "
           "FROM res_users u JOIN res_partner p ON p.id = u.partner_id ORDER BY u.id")


def utilisateurs(base, delai=20):
    """{login: {"uid", "nom", "type"}} de la base ; None si impossible (psql absent, base inaccessible, pas root)."""
    if not re.fullmatch(r"[\w.-]+", base or ""):
        return None
    if VERBOSE:
        print("+ runuser -u postgres -- psql -d " + base + " -tA -c \"SELECT … FROM res_users JOIN res_partner\" (lecture seule)", file=sys.stderr)
    try:
        r = subprocess.run(POSTGRES_RUN + ["psql", "-d", base, "-tA", "-F", SEP, "-c", REQUETE],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                           universal_newlines=True, errors="replace", timeout=delai)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    res = {}
    for ligne in r.stdout.splitlines():
        c = ligne.split(SEP)
        if len(c) == 4 and c[0].isdigit():
            res[c[1]] = {"uid": int(c[0]), "nom": c[2], "type": "portail/public" if c[3] in ("t", "true", "1") else "interne"}
    return res or None


def modules_installes(base, motifs, delai=20):
    """Noms des modules INSTALLÉS dont le nom correspond à un des motifs SQL (« %session% »…), triés ; None si impossible (psql absent,
    base inaccessible, pas root). Lecture seule ; les motifs viennent du programme (jamais d'une saisie)."""
    if not re.fullmatch(r"[\w.-]+", base or "") or not all(re.fullmatch(r"[%\w]+", m) for m in motifs):
        return None
    requete = ("SELECT name FROM ir_module_module WHERE state = 'installed' AND name ILIKE ANY (ARRAY["
               + ", ".join(f"'{m}'" for m in motifs) + "]) ORDER BY name")
    if VERBOSE:
        print("+ runuser -u postgres -- psql -d " + base + " -tA -c \"SELECT name FROM ir_module_module WHERE state = 'installed' …\" (lecture seule)", file=sys.stderr)
    try:
        r = subprocess.run(POSTGRES_RUN + ["psql", "-d", base, "-tA", "-c", requete], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, universal_newlines=True, errors="replace", timeout=delai)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return [l.strip() for l in r.stdout.splitlines() if l.strip()] if r.returncode == 0 else None


def _requete(base, sql, delai=20):
    """Lignes (listes de champs) du résultat d'une requête SELECT ; None si impossible (psql absent, base inaccessible, pas root). La
    transaction est forcée en LECTURE SEULE par PostgreSQL lui-même (default_transaction_read_only) : rien ne peut être modifié."""
    if not re.fullmatch(r"[\w.-]+", base or ""):
        return None
    if VERBOSE:
        print("+ runuser -u postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -d " + base + " -tA -c \"" + sql[:90] + " …\"", file=sys.stderr)
    try:
        r = subprocess.run(POSTGRES_RUN + ["env", "PGOPTIONS=-c default_transaction_read_only=on", "psql", "-d", base, "-tA", "-F", SEP,
                            "-c", sql], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, universal_newlines=True,
                           errors="replace", timeout=delai)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return [ligne.split(SEP) for ligne in r.stdout.splitlines() if ligne.strip()]


def modules_etat(base, delai=30):
    """[{nom, etat, version, auteur, maj, cree}] des modules d'une base qui ne sont ni désinstallés ni non installables (installés, à mettre à jour, à installer, à retirer) ;
    `version` est la version installée (latest_version, enregistrée à la dernière mise à jour) ; `maj` : date de la dernière écriture de l'enregistrement du module par Odoo (installation, mise à jour, désinstallation : Odoo ne garde pas d'autre date), `cree` : date et heure (UTC, comme `maj`) où Odoo a vu le module pour la première fois (liste des applications). None si impossible (psql absent, base inaccessible, pas root). Lecture seule."""
    lignes = _requete(base, "SELECT name, state, COALESCE(latest_version, ''), replace(COALESCE(author, ''), E'\n', ' '), "
                            "COALESCE(to_char(write_date, 'YYYY-MM-DD HH24:MI'), ''), COALESCE(to_char(create_date, 'YYYY-MM-DD HH24:MI'), '') FROM ir_module_module "
                            "WHERE state NOT IN ('uninstalled', 'uninstallable') ORDER BY name", delai)
    if lignes is None:
        return None
    return [{"nom": c[0], "etat": c[1], "version": c[2], "auteur": c[3], "maj": c[4], "cree": c[5]} for c in lignes if len(c) == 6]


def nom_traduit(valeur):
    """Nom Odoo lu en texte : un nom traduisible (JSON par langue dans Odoo récent) donne la valeur fr_CA, puis fr_FR, puis en_US, puis la première."""
    valeur = valeur or ""
    if valeur.startswith("{"):
        try:
            valeurs = json.loads(valeur)
            return valeurs.get("fr_CA") or valeurs.get("fr_FR") or valeurs.get("en_US") or next(iter(valeurs.values()), "")
        except ValueError:
            pass
    return valeur


def groupes_rlq(base, prefixe="RLQ", delai=20):
    """[{nom, membres, id, categorie}] des groupes Odoo dont le nom commence par PREFIXE (« RLQ-JPOL26-Visiteur »…), avec le nombre de comptes ACTIFS qui en font
    partie, triés par nom ; `id` (identifiant du groupe, res_groups.id) et `categorie` (nom de sa catégorie, ou « » s'il n'en a pas) distinguent deux groupes
    qui portent le même nom. None si impossible (psql absent, base inaccessible, pas root). LECTURE SEULE."""
    if not re.fullmatch(r"[\w-]{1,30}", prefixe or ""):
        return None
    lignes = _requete(base, "SELECT g.name::text, count(u.id), g.id, COALESCE(c.name::text, '') FROM res_groups g "
                            "LEFT JOIN res_groups_users_rel r ON r.gid = g.id LEFT JOIN res_users u ON u.id = r.uid AND u.active "
                            "LEFT JOIN ir_module_category c ON c.id = g.category_id "
                            f"WHERE g.name::text ILIKE '%{prefixe}%' GROUP BY g.id, g.name, c.name ORDER BY g.name::text, g.id", delai)
    if lignes is None:
        return None
    res = []
    for c in lignes:
        if len(c) < 2 or not c[1].isdigit():
            continue
        nom = nom_traduit(c[0])
        if nom.upper().startswith(prefixe.upper()):
            groupe = {"nom": nom, "membres": int(c[1])}
            if len(c) > 2 and c[2].isdigit():
                groupe["id"] = int(c[2])
            if len(c) > 3:
                groupe["categorie"] = nom_traduit(c[3])
            res.append(groupe)
    return sorted(res, key=lambda g: (g["nom"].lower(), g.get("id", 0)))


def parametres(base, prefixe="mail."):
    """{clé: valeur} des paramètres système (ir_config_parameter) dont la clé commence par PREFIXE, sans les clés qui évoquent un secret ; None si
    impossible. Les clés absentes sont celles qu'Odoo n'a jamais enregistrées : il utilise alors sa valeur par défaut."""
    if not re.fullmatch(r"[a-z_.]+", prefixe or ""):
        return None
    lignes = _requete(base, f"SELECT key, value FROM ir_config_parameter WHERE key LIKE '{prefixe}%' AND key !~* '(secret|password|passwd|token|apikey|private)' ORDER BY key")
    return None if lignes is None else {l[0]: l[1] if len(l) > 1 else "" for l in lignes}


def serveurs_courriel(base):
    """[{id, nom, hote, port, chiffrement, filtre, actif}] des serveurs de courrier sortant ENREGISTRÉS dans Odoo (jamais d'identifiant ni de mot de
    passe) ; [] s'il n'y en a aucun (Odoo utilise alors odoo.conf) ; None si impossible."""
    lignes = _requete(base, "SELECT id, name, smtp_host, smtp_port, smtp_encryption, COALESCE(from_filter, ''), active FROM ir_mail_server ORDER BY sequence, id")
    if lignes is None:
        return None
    res = []
    for l in lignes:
        if len(l) >= 7 and l[0].isdigit():
            res.append({"id": int(l[0]), "nom": l[1], "hote": l[2], "port": l[3], "chiffrement": l[4], "filtre": l[5], "actif": l[6] in ("t", "true", "1")})
    return res


def decalage_local_sql():
    """Seconds de décalage de l'heure LOCALE de cette machine par rapport à UTC (PostgreSQL d'Odoo enregistre en UTC), pour grouper par JOUR LOCAL."""
    import time
    return -(time.altzone if time.localtime().tm_isdst > 0 else time.timezone)


def courriels(base, jours=7):
    """État des courriels des JOURS derniers jours : {etats: {état: n}, echecs_par_jour: {jour: n}, sujets: [(sujet, n)], raisons: [(raison, n)]} ;
    None si impossible. États d'Odoo : outgoing (en attente), sent, exception (échec d'envoi), cancel, received. Jamais d'adresse de destinataire."""
    jours = int(jours)
    depuis = f"create_date > now() - interval '{jours} days'"
    etats = _requete(base, f"SELECT state, COUNT(*) FROM mail_mail WHERE {depuis} GROUP BY state ORDER BY 2 DESC")
    if etats is None:
        return None
    echecs = _requete(base, f"SELECT to_char(date(create_date + interval '{decalage_local_sql()} seconds'), 'YYYY-MM-DD'), COUNT(*) FROM mail_mail WHERE state = 'exception' AND {depuis} GROUP BY 1 ORDER BY 1") or []
    # The subject is NOT in mail_mail: mail.mail inherits from mail.message (_inherits), it is in mail_message.
    sujets = _requete(base, f"SELECT left(COALESCE(g.subject, ''), 80), COUNT(*) FROM mail_mail m JOIN mail_message g ON g.id = m.mail_message_id "
                            f"WHERE m.state = 'exception' AND m.{depuis} GROUP BY 1 ORDER BY 2 DESC LIMIT 5") or []
    raisons = _requete(base, f"SELECT left(split_part(COALESCE(failure_reason, ''), E'\\n', 1), 140), COUNT(*) FROM mail_mail WHERE state = 'exception' AND {depuis} GROUP BY 1 ORDER BY 2 DESC LIMIT 5") or []
    nombre = lambda lignes: [(l[0], int(l[1])) for l in lignes if len(l) >= 2 and l[1].isdigit()]
    return {"etats": dict(nombre(etats)), "echecs_par_jour": dict(nombre(echecs)), "sujets": nombre(sujets), "raisons": nombre(raisons)}


def _titre_sql(colonne):
    """Expression SQL du titre d'un enregistrement dont le nom est traduit (jsonb, Odoo 16+) : français canadien, français, anglais, puis le texte brut."""
    return f"COALESCE({colonne}->>'fr_CA', {colonne}->>'fr_FR', {colonne}->>'en_US', {colonne}::text)"


def _texte_sql(valeur):
    """Littéral SQL sûr : apostrophes doublées, aucun caractère de contrôle (le nom d'une étiquette vient de la ligne de commande ou du clavier)."""
    return "'" + re.sub(r"[\x00-\x1f]", "", valeur).replace("'", "''") + "'"


def _condition_etiquette(nom):
    """Condition SQL « l'étiquette de contact (alias c) porte ce nom » : dans n'importe quelle langue (nom traduit, jsonb) ou, sinon, nom simple."""
    v = _texte_sql(nom)
    return f"EXISTS (SELECT 1 FROM jsonb_each_text(c.name::jsonb) t WHERE t.value = {v})", f"c.name::text = {v}"


def groupe_existe(base, nom, delai=20):
    """Vrai/faux : l'étiquette de contact `nom` (res.partner.category, « groupe de contacts ») existe dans la base ; None si illisible (psql, table absente). LECTURE SEULE."""
    for condition in _condition_etiquette(nom):
        lignes = _requete(base, f"SELECT count(*) FROM res_partner_category c WHERE {condition}", delai)
        if lignes:
            return int(lignes[0][0]) > 0
    return None


def groupes_contacts(base, limite=30, delai=20):
    """Noms des étiquettes de contact existantes (pour aider à corriger une faute de frappe) ; None si illisible. LECTURE SEULE."""
    lignes = _requete(base, f"SELECT left({_titre_sql('c.name')}, 60) FROM res_partner_category c ORDER BY 1 LIMIT {int(limite)}", delai)
    return None if lignes is None else [c[0] for c in lignes if c and c[0]]


def membres_groupe(base, nom, delai=20):
    """Identifiants de connexion des utilisateurs dont le contact porte l'étiquette `nom` ; None si illisible. LECTURE SEULE. Ni nom, ni courriel d'autre contact."""
    for condition in _condition_etiquette(nom):
        lignes = _requete(base, "SELECT DISTINCT u.login FROM res_users u JOIN res_partner_res_partner_category_rel r ON r.partner_id = u.partner_id "
                                f"JOIN res_partner_category c ON c.id = r.category_id WHERE {condition}", delai)
        if lignes is not None:
            return [c[0] for c in lignes if c and c[0]]
    return None


def _inscriptions(base, sql, delai):
    lignes = _requete(base, sql, delai)
    if lignes is None:
        return None
    res = []
    for c in lignes:
        if len(c) >= 4 and re.fullmatch(r"\d+", c[0]):
            res.append({"quand": int(c[0]), "titre": c[1], "nom": c[2], "etat": c[3], "ticket": c[4] if len(c) >= 5 else ""})
    return res


def inscriptions_evenements(base, jours=30, limite=15, delai=20):
    """Dernières inscriptions à des événements (event_registration), les plus récentes d'abord : [{quand (epoch), titre, nom, etat, ticket}] ; None si impossible. LECTURE SEULE.
    Ni courriel ni téléphone : seulement le nom inscrit et le nom du billet (ticket) choisi (vide si l'événement n'en a pas)."""
    jours, limite = int(jours), int(limite)
    return _inscriptions(base, f"SELECT extract(epoch from r.create_date)::bigint, left({_titre_sql('e.name')}, 60), left(replace(COALESCE(r.name, ''), E'\n', ' '), 40), "
                               f"COALESCE(r.state, ''), left({_titre_sql('t.name')}, 40) FROM event_registration r JOIN event_event e ON e.id = r.event_id "
                               f"LEFT JOIN event_event_ticket t ON t.id = r.event_ticket_id WHERE r.create_date > now() - interval '{jours} days' ORDER BY r.create_date DESC LIMIT {limite}", delai)


def inscriptions_avec_sondage(base, jours=30, limite=15, motif="portes ouvertes", delai=30):
    """Comme inscriptions_evenements(), plus le SONDAGE de confirmation de la même personne pour les événements dont le titre contient MOTIF (« portes ouvertes ») :
    [{quand, titre, nom, etat, ticket, avec_sondage (bool : l'événement en demande un), sondage: None ou {quand, titre, nom, etat}}] ; None si impossible. LECTURE SEULE.
    La personne est reconnue par son contact (partner_id) ou, à défaut, par son courriel (comparaison seulement : jamais renvoyé) ; sondage = le plus avancé (terminé d'abord), puis le plus
    récent, parmi ceux dont le titre contient MOTIF, hors essais."""
    jours, limite = int(jours), int(limite)
    motif = re.sub(r"[^\w\s-]", "", motif or "").strip()
    if not motif:
        return inscriptions_evenements(base, jours, limite, delai)
    titre_e, titre_s = _titre_sql("e.name"), _titre_sql("s.title")
    sql = (f"SELECT extract(epoch from r.create_date)::bigint, left({titre_e}, 60), left(replace(COALESCE(r.name, ''), E'\\n', ' '), 40), COALESCE(r.state, ''), "
           f"left({_titre_sql('t.name')}, 40), CASE WHEN {titre_e} ILIKE '%{motif}%' THEN '1' ELSE '0' END, "
           f"COALESCE(extract(epoch from sv.create_date)::bigint::text, ''), left(COALESCE(sv.titre, ''), 60), left(replace(COALESCE(sv.nom, ''), E'\\n', ' '), 40), COALESCE(sv.state, '') "
           f"FROM event_registration r JOIN event_event e ON e.id = r.event_id LEFT JOIN event_event_ticket t ON t.id = r.event_ticket_id "
           f"LEFT JOIN LATERAL (SELECT i.create_date, {titre_s} AS titre, p.name AS nom, i.state FROM survey_user_input i JOIN survey_survey s ON s.id = i.survey_id "
           f"LEFT JOIN res_partner p ON p.id = i.partner_id WHERE NOT COALESCE(i.test_entry, false) AND {titre_s} ILIKE '%{motif}%' "
           f"AND ((r.partner_id IS NOT NULL AND i.partner_id = r.partner_id) OR (COALESCE(r.email, '') <> '' AND lower(i.email) = lower(r.email))) "
           f"ORDER BY (i.state = 'done') DESC, i.create_date DESC LIMIT 1) sv ON {titre_e} ILIKE '%{motif}%' "
           f"WHERE r.create_date > now() - interval '{jours} days' ORDER BY r.create_date DESC LIMIT {limite}")
    lignes = _requete(base, sql, delai)
    if lignes is None:
        return None
    res = []
    for c in lignes:
        if len(c) >= 10 and re.fullmatch(r"\d+", c[0]):
            sondage = {"quand": int(c[6]), "titre": c[7], "nom": c[8], "etat": c[9]} if re.fullmatch(r"\d+", c[6]) else None
            res.append({"quand": int(c[0]), "titre": c[1], "nom": c[2], "etat": c[3], "ticket": c[4], "avec_sondage": c[5] == "1", "sondage": sondage})
    return res


def registrations_by_ticket(base, days=30, limit=200, delai=30):
    """Registrations of the last DAYS days with THEIR survey (READ-ONLY): the survey expected for a registration is the one of its ticket (event_event_ticket.rlq_survey_id,
    module rlq_survey_report), otherwise the one of the event (event_event.survey_id, if that column exists). The person (contact, otherwise e-mail: compared, never
    returned) is looked up in THAT survey only: an answer to a survey of another event or ticket (last year's, a test, another ticket) is no longer taken for the
    confirmation; the person's most recent answer to ANY other survey is returned apart, as `other`, to be pointed out (only when the expected one is missing). Sorted by event (most recent start first), ticket, then registration (most recent first).
    [{id, when, event_id, event, event_start, ticket_id, ticket, state, name, survey_id, survey, answer: None or {when, name, state}, other: None or {when, title, name, state}}];
    None if impossible (PostgreSQL unreachable, or no survey column: module rlq_survey_report absent — see inscriptions_avec_sondage)."""
    days, limit = int(days), int(limit)
    ticket_col, event_col = _column_exists(base, "event_event_ticket", "rlq_survey_id"), _column_exists(base, "event_event", "survey_id")
    if not ticket_col and not event_col:
        return None
    expected = "COALESCE(" + ", ".join((["t.rlq_survey_id"] if ticket_col else []) + (["e.survey_id"] if event_col else []) + ["0"]) + ")"
    same_person = "((r.partner_id IS NOT NULL AND i.partner_id = r.partner_id) OR (COALESCE(r.email, '') <> '' AND lower(i.email) = lower(r.email)))"
    title_e, title_t, title_s = _titre_sql("e.name"), _titre_sql("t.name"), _titre_sql("s.title")
    sql = (f"SELECT r.id, extract(epoch from r.create_date)::bigint, e.id, left({title_e}, 60), COALESCE(extract(epoch from e.date_begin)::bigint::text, ''), "
           f"COALESCE(t.id, 0), left(COALESCE({title_t}, ''), 40), COALESCE(r.state, ''), left(replace(COALESCE(r.name, ''), E'\\n', ' '), 40), "
           f"COALESCE(s.id, 0), left(COALESCE({title_s}, ''), 80), "
           f"COALESCE(a.quand::text, ''), left(replace(COALESCE(a.nom, ''), E'\\n', ' '), 40), COALESCE(a.state, ''), "
           f"COALESCE(o.quand::text, ''), left(COALESCE(o.titre, ''), 80), left(replace(COALESCE(o.nom, ''), E'\\n', ' '), 40), COALESCE(o.state, '') "
           f"FROM event_registration r JOIN event_event e ON e.id = r.event_id LEFT JOIN event_event_ticket t ON t.id = r.event_ticket_id "
           f"LEFT JOIN survey_survey s ON s.id = {expected} "
           f"LEFT JOIN LATERAL (SELECT extract(epoch from i.create_date)::bigint AS quand, p.name AS nom, i.state FROM survey_user_input i LEFT JOIN res_partner p ON p.id = i.partner_id "
           f"WHERE i.survey_id = s.id AND NOT COALESCE(i.test_entry, false) AND {same_person} ORDER BY (i.state = 'done') DESC, i.create_date DESC LIMIT 1) a ON true "
           f"LEFT JOIN LATERAL (SELECT extract(epoch from i.create_date)::bigint AS quand, {_titre_sql('s2.title')} AS titre, p.name AS nom, i.state FROM survey_user_input i "
           f"JOIN survey_survey s2 ON s2.id = i.survey_id LEFT JOIN res_partner p ON p.id = i.partner_id "
           f"WHERE i.survey_id <> COALESCE(s.id, 0) AND NOT COALESCE(i.test_entry, false) AND {same_person} "
           f"ORDER BY i.create_date DESC LIMIT 1) o ON a.quand IS NULL AND s.id IS NOT NULL "
           f"WHERE r.create_date > now() - interval '{days} days' "
           f"ORDER BY e.date_begin DESC NULLS LAST, e.id, {title_t} NULLS LAST, r.create_date DESC LIMIT {limit}")
    rows = _requete(base, sql, delai)
    if rows is None:
        return None
    res = []
    for c in rows:
        if len(c) < 18 or not re.fullmatch(r"\d+", c[1]):
            continue
        res.append({"id": int(c[0]), "when": int(c[1]), "event_id": int(c[2]), "event": c[3], "event_start": int(c[4]) if c[4].isdigit() else 0,
                    "ticket_id": int(c[5] or 0), "ticket": c[6], "state": c[7], "name": c[8], "survey_id": int(c[9] or 0), "survey": c[10],
                    "answer": {"when": int(c[11]), "name": c[12], "state": c[13]} if c[11].isdigit() else None,
                    "other": {"when": int(c[14]), "title": c[15], "name": c[16], "state": c[17]} if c[14].isdigit() else None})
    return res


def mail_detail(base, mail_id, message_id="", delai=10, address=""):
    """Who an e-mail (mail.mail) was sent to and what it is, READ-ONLY: {subject, recipients: [names] (contacts, otherwise the e-mail_to addresses as written),
    record: name of the record it is about (« registration Ana Tremblay — Event title » for event.registration, otherwise the model)} ; {} if not found or if
    the Message-Id does not match (another database) ; None if PostgreSQL is unreachable. `address`: the recipient as Odoo logs it, masked (« b****ss@exemple.org »):
    picks the notified partner(s) whose e-mail matches it when the mail.mail is already deleted."""
    if not str(mail_id).isdigit():
        return {}
    check = f" AND g.message_id = {_sql_text(message_id)}" if message_id else ""
    rows = _requete(base,
        "SELECT left(replace(COALESCE(g.subject, ''), E'\\n', ' '), 160), "
        "COALESCE((SELECT string_agg(left(replace(p.name, E'\\n', ' '), 40), '; ' ORDER BY p.name) FROM mail_mail_res_partner_rel x JOIN res_partner p ON p.id = x.res_partner_id "
        "WHERE x.mail_mail_id = m.id), ''), left(COALESCE(m.email_to, ''), 200), COALESCE(g.model, ''), COALESCE(g.res_id, 0) "
        f"FROM mail_mail m JOIN mail_message g ON g.id = m.mail_message_id WHERE m.id = {int(mail_id)}{check}", delai)
    if rows is None:
        return None
    if (not rows or len(rows[0]) < 5) and message_id:
        # 1.19: Odoo deletes the mail.mail right after sending it (auto_delete: "deleted mail.mail records with IDs: [7624]", a few ms later): the
        # mail.message stays, with the same Message-Id; recipients = the partner notified by e-mail whose address matches the masked one, otherwise all the
        # partners notified by e-mail, otherwise the partners of the message
        pattern = re.sub(r"\*+", "%", re.sub(r"([%_\\])", r"\\\1", address)) if address and "*" in address and "@" in address else ""
        notified = ("(SELECT string_agg(DISTINCT left(replace(p.name, E'\\n', ' '), 40), '; ') FROM mail_notification n JOIN res_partner p ON p.id = n.res_partner_id "
                    "WHERE n.mail_message_id = g.id AND n.notification_type = 'email'{})")
        rows = _requete(base,
            "SELECT left(replace(COALESCE(g.subject, ''), E'\\n', ' '), 160), "
            "COALESCE(" + (notified.format(f" AND p.email ILIKE {_sql_text(pattern)}") + ", " if pattern else "") + notified.format("") + ", "
            "(SELECT string_agg(DISTINCT left(replace(p.name, E'\\n', ' '), 40), '; ') FROM mail_message_res_partner_rel x JOIN res_partner p ON p.id = x.res_partner_id "
            "WHERE x.mail_message_id = g.id), ''), '', COALESCE(g.model, ''), COALESCE(g.res_id, 0) "
            f"FROM mail_message g WHERE g.message_id = {_sql_text(message_id)} ORDER BY g.id DESC LIMIT 1", delai)
        if rows is None:
            return None
    if not rows or len(rows[0]) < 5:
        return {}
    subject, partners, email_to, model, res_id = rows[0][:5]
    recipients = [n for n in partners.split("; ") if n] or [re.sub(r"\s*<[^>]*>", "", a).strip().strip('"') or a.strip() for a in email_to.split(",") if a.strip()]
    record = model
    if model == "event.registration" and res_id.isdigit():
        r = _requete(base, f"SELECT left(replace(COALESCE(r.name, ''), E'\\n', ' '), 40), left({_titre_sql('e.name')}, 60) FROM event_registration r "
                           f"JOIN event_event e ON e.id = r.event_id WHERE r.id = {int(res_id)}", delai)
        if r and len(r[0]) >= 2:
            record = f"registration {r[0][0]} — {r[0][1]}"
            if not recipients and r[0][0]:
                recipients = [r[0][0]]
    return {"subject": subject, "recipients": recipients, "record": record}


def user_profiles(base, delai=60):
    """--list-users --table / --csv of web-monitor.py (1.16), READ-ONLY: {login: {email, phone, country (ISO code), country_name, city, groups: [custom groups:
    created in Odoo or by an rlq_* module], all_groups: [every group, for --group], tags: [contact tags], events: registrations not cancelled, surveys: surveys
    completed (tests excluded), created: creation of the account (epoch, 1.17)}}. Inner separators chr(2) / chr(3): Python splitlines() also cuts at chr(28) to chr(30). Tables of modules not installed (event, survey) count 0. None if PostgreSQL is unreachable."""
    regs = (_requete(base, "SELECT to_regclass('public.event_registration') IS NOT NULL, to_regclass('public.survey_user_input') IS NOT NULL, "
                           "to_regclass('public.res_partner_res_partner_category_rel') IS NOT NULL", delai) or [["", "", ""]])[0]
    has_event, has_survey, has_tags = (r in ("t", "true") for r in (regs + ["", "", ""])[:3])
    mobile = "NULLIF(p.mobile, ''), " if _column_exists(base, "res_partner", "mobile") else ""
    events = "(SELECT count(*) FROM event_registration e WHERE e.partner_id = p.id AND COALESCE(e.state, '') <> 'cancel')" if has_event else "0"
    surveys = ("(SELECT count(*) FROM survey_user_input i WHERE i.partner_id = p.id AND i.state = 'done' AND NOT COALESCE(i.test_entry, false))"
               if has_survey else "0")
    tags = (f"COALESCE((SELECT string_agg({_titre_sql('t.name')}, chr(3) ORDER BY 1) FROM res_partner_res_partner_category_rel x "
            f"JOIN res_partner_category t ON t.id = x.category_id WHERE x.partner_id = p.id), '')" if has_tags else "''")
    sql = ("SELECT u.login, COALESCE(p.email, ''), COALESCE(NULLIF(p.phone, ''), " + mobile + "''), COALESCE(c.code, ''), "
           f"COALESCE({_titre_sql('c.name')}, ''), replace(COALESCE(p.city, ''), E'\\n', ' '), "
           f"COALESCE((SELECT string_agg({_titre_sql('g.name')} || chr(2) || COALESCE(d.module, ''), chr(3) ORDER BY 1) FROM res_groups_users_rel r "
           "JOIN res_groups g ON g.id = r.gid LEFT JOIN ir_model_data d ON d.model = 'res.groups' AND d.res_id = g.id WHERE r.uid = u.id), ''), "
           f"{tags}, {events}, {surveys}, COALESCE(extract(epoch FROM u.create_date)::bigint::text, '') "      # 1.17: Odoo stores UTC: epoch read as UTC
           "FROM res_users u JOIN res_partner p ON p.id = u.partner_id LEFT JOIN res_country c ON c.id = p.country_id")
    rows = _requete(base, sql, delai)
    if rows is None:
        return None
    res = {}
    for c in rows:
        if len(c) < 10:
            continue
        groups = [g.split("\x02") for g in c[6].split("\x03") if g]
        custom = sorted({n for n, *m in groups if not (m and m[0]) or m[0].startswith("rlq") or m[0] in ("__export__", "__custom__")})
        res[c[0]] = {"email": c[1], "phone": c[2], "country": c[3], "country_name": c[4], "city": c[5], "groups": custom,
                     "all_groups": sorted({n for n, *_ in groups}), "tags": [t for t in c[7].split("\x03") if t],
                     "events": int(c[8]) if c[8].isdigit() else 0, "surveys": int(c[9]) if c[9].isdigit() else 0,
                     "created": int(c[10]) if len(c) > 10 and c[10].isdigit() else None}
    return res


def jetons_sondages(base, delai=20):
    """{jeton d'accès (minuscules): titre} des sondages (survey_survey), pour nommer les sondages vus dans les adresses /survey/<jeton> ; avec le nom du ou des billets (ticket) qui utilisent
    ce sondage (rlq_survey_id, module rlq_survey_report) quand il n'est pas déjà dans le titre ; None si impossible. LECTURE SEULE. Le jeton d'accès est public (il est dans le lien du sondage)."""
    titre = _titre_sql("s.title")
    avec_billets = (f"SELECT lower(s.access_token), left({titre}, 60), COALESCE(left(string_agg(DISTINCT {_titre_sql('t.name')}, ', '), 40), '') FROM survey_survey s "
                    f"LEFT JOIN event_event_ticket t ON t.rlq_survey_id = s.id WHERE s.access_token IS NOT NULL GROUP BY s.id")
    lignes = _requete(base, avec_billets, delai)
    if lignes is None:                       # module rlq_survey_report absent : pas de colonne rlq_survey_id
        lignes = _requete(base, f"SELECT lower(access_token), left({_titre_sql('title')}, 60), '' FROM survey_survey s WHERE access_token IS NOT NULL", delai)
    if lignes is None:
        return None
    res = {}
    for c in lignes:
        if len(c) >= 2 and c[0]:
            billets = c[2] if len(c) >= 3 else ""
            res[c[0]] = c[1] + (f" — billet {billets}" if billets and billets.lower() not in c[1].lower() else "")
    return res


def reponses_sondages(base, jours=30, limite=15, delai=20):
    """Dernières participations à des sondages (survey_user_input, hors essais), les plus récentes d'abord : [{quand (epoch), titre, nom, etat}] ; None si impossible. LECTURE SEULE.
    Le nom est celui du contact connecté (« anonyme » sinon) ; jamais de courriel ni de réponse."""
    jours, limite = int(jours), int(limite)
    return _inscriptions(base, f"SELECT extract(epoch from i.create_date)::bigint, left({_titre_sql('s.title')}, 60), left(replace(COALESCE(p.name, 'anonyme'), E'\n', ' '), 40), "
                               f"COALESCE(i.state, '') FROM survey_user_input i JOIN survey_survey s ON s.id = i.survey_id LEFT JOIN res_partner p ON p.id = i.partner_id "
                               f"WHERE i.create_date > now() - interval '{jours} days' AND NOT COALESCE(i.test_entry, false) ORDER BY i.create_date DESC LIMIT {limite}", delai)


def bases_odoo():
    """Bases PostgreSQL qui contiennent la table des courriels d'Odoo (mail_mail) ; None si PostgreSQL est inaccessible (psql absent, pas root)."""
    noms = _requete("postgres", "SELECT datname FROM pg_database WHERE NOT datistemplate AND datname <> 'postgres' ORDER BY 1")
    if noms is None:
        return None
    return [n[0] for n in noms if re.fullmatch(r"[\w.-]+", n[0]) and (_requete(n[0], "SELECT to_regclass('public.mail_mail') IS NOT NULL") or [[""]])[0][0] in ("t", "true")]


def courriels_en_echec(base, jours=30):
    """[{id, instant, sujet, destinataires, raison}] des courriels en ÉCHEC D'ENVOI (état « exception ») des JOURS derniers jours, du plus ancien au plus
    récent ; None si impossible. Le sujet vient de mail_message (mail.mail en hérite) ; destinataires : email_to, sinon les adresses des contacts."""
    jours = int(jours)
    lignes = _requete(base,
        "SELECT m.id, floor(extract(epoch FROM m.create_date)), left(COALESCE(g.subject, ''), 160), "
        "left(COALESCE(NULLIF(m.email_to, ''), (SELECT string_agg(p.email, ', ') FROM mail_mail_res_partner_rel r JOIN res_partner p ON p.id = r.res_partner_id "
        "WHERE r.mail_mail_id = m.id), ''), 300), "
        "left(replace(replace(COALESCE(m.failure_reason, ''), E'\\n', ' '), E'\\r', ' '), 500) "
        f"FROM mail_mail m JOIN mail_message g ON g.id = m.mail_message_id WHERE m.state = 'exception' AND m.create_date > now() - interval '{jours} days' "
        "ORDER BY m.create_date, m.id", delai=60)
    if lignes is None:
        return None
    res = []
    for l in lignes:
        if len(l) >= 5 and l[0].isdigit():
            res.append({"id": int(l[0]), "instant": float(l[1] or 0), "sujet": l[2], "destinataires": l[3], "raison": l[4]})
    return res


def courriels_envoyes(base, limite=10):
    """[{id, instant, sujet, destinataires}] des LIMITE derniers courriels ENVOYÉS (état « sent »), du plus récent au plus ancien ; None si impossible."""
    limite = max(1, int(limite))
    lignes = _requete(base,
        "SELECT m.id, floor(extract(epoch FROM m.create_date)), left(COALESCE(g.subject, ''), 160), "
        "left(COALESCE(NULLIF(m.email_to, ''), (SELECT string_agg(p.email, ', ') FROM mail_mail_res_partner_rel r JOIN res_partner p ON p.id = r.res_partner_id "
        "WHERE r.mail_mail_id = m.id), ''), 300) "
        f"FROM mail_mail m JOIN mail_message g ON g.id = m.mail_message_id WHERE m.state = 'sent' ORDER BY m.create_date DESC, m.id DESC LIMIT {limite}", delai=60)
    if lignes is None:
        return None
    return [{"id": int(l[0]), "instant": float(l[1] or 0), "sujet": l[2], "destinataires": l[3]} for l in lignes if len(l) >= 4 and l[0].isdigit()]


def remettre_en_attente(base, ids, delai=60):
    """UNIQUE ÉCRITURE de ce composant : remet des courriels en échec d'envoi à l'état « En attente » (outgoing), comme le bouton « Réessayer » d'Odoo ; la tâche
    planifiée d'Odoo les enverra à son prochain passage. Seuls les courriels encore en échec (state = 'exception') sont touchés. Retourne la liste des id remis en
    attente ; None si impossible. Aucune autre colonne n'est modifiée que l'état et la date de modification."""
    try:
        ids = sorted({int(i) for i in ids})
    except (TypeError, ValueError):
        return None
    if not ids or not re.fullmatch(r"[\w.-]+", base or ""):
        return None
    sql = ("UPDATE mail_mail SET state = 'outgoing', write_date = (now() AT TIME ZONE 'utc') "
           f"WHERE id IN ({', '.join(str(i) for i in ids)}) AND state = 'exception' RETURNING id")
    if VERBOSE:
        print("+ runuser -u postgres -- psql -d " + base + " -tA -c \"UPDATE mail_mail SET state = 'outgoing' WHERE id IN (" + ", ".join(map(str, ids[:5]))
              + (" …" if len(ids) > 5 else "") + ") AND state = 'exception'\" (ÉCRITURE)", file=sys.stderr)
    try:
        r = subprocess.run(POSTGRES_RUN + ["psql", "-d", base, "-v", "ON_ERROR_STOP=1", "-tA", "-c", sql], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, universal_newlines=True, errors="replace", timeout=delai)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return [int(l) for l in r.stdout.splitlines() if l.strip().isdigit()]


# ---------------------------------------------------------------------------------------------------------------------------------
# 1.14: Odoo accounts (investigation, ban) and e-mail addresses of registrations (correction). New code in English (migration by stages).
# ---------------------------------------------------------------------------------------------------------------------------------
def _sql_text(value):
    """SQL literal of a text that may come from Odoo data (an e-mail address typed by a visitor): doubled quotes, no NUL, no backslash escapes."""
    return "'" + str(value).replace("\x00", "").replace("'", "''") + "'"


def _column_exists(base, table, column):
    rows = _requete(base, f"SELECT 1 FROM information_schema.columns WHERE table_name = {_sql_text(table)} AND column_name = {_sql_text(column)}")
    return bool(rows)


def user_detail(base, login, delai=30):
    """Odoo account of a login, READ-ONLY: {uid, login, name, email, active, share, created (epoch), logins (res_users_log count), last_login (epoch or 0),
    registrations: [(epoch, event, state)], registration_count, messages_30d, survey_answers, oauth: provider name or ""} ; {} if the login does not exist ;
    None if PostgreSQL is unreachable (psql missing, root required)."""
    oauth = _column_exists(base, "res_users", "oauth_provider_id")
    rows = _requete(base,
        "SELECT u.id, u.login, replace(COALESCE(p.name::text, ''), E'\\n', ' '), COALESCE(p.email, ''), u.active, u.share, floor(extract(epoch FROM u.create_date)), "
        "(SELECT count(*) FROM res_users_log l WHERE l.create_uid = u.id), COALESCE((SELECT floor(extract(epoch FROM max(l.create_date))) FROM res_users_log l WHERE l.create_uid = u.id), 0), "
        "u.partner_id, " + ("COALESCE((SELECT COALESCE(to_jsonb(o.name)->>'en_US', o.name::text) FROM auth_oauth_provider o WHERE o.id = u.oauth_provider_id), '')" if oauth else "''") + " "
        f"FROM res_users u JOIN res_partner p ON p.id = u.partner_id WHERE u.login = {_sql_text(login)}", delai)
    if rows is None:
        return None
    if not rows or len(rows[0]) < 11:
        return {}
    c = rows[0]
    pid = int(c[9]) if c[9].isdigit() else 0
    res = {"uid": int(c[0]), "login": c[1], "name": c[2], "email": c[3], "active": c[4] in ("t", "true"), "share": c[5] in ("t", "true"),
           "created": float(c[6] or 0), "logins": int(c[7] or 0), "last_login": float(c[8] or 0), "partner_id": pid, "oauth": c[10],
           "registrations": [], "registration_count": 0, "messages_30d": None, "survey_answers": None}
    if pid:
        email = c[3]
        regs = _requete(base,
            f"SELECT floor(extract(epoch FROM r.create_date)), left({_titre_sql('e.name')}, 60), COALESCE(r.state, '') FROM event_registration r "
            f"JOIN event_event e ON e.id = r.event_id WHERE r.partner_id = {pid}" + (f" OR lower(r.email) = lower({_sql_text(email)})" if email else "")
            + " ORDER BY r.create_date DESC", delai) or []
        res["registration_count"] = len(regs)
        res["registrations"] = [(float(r[0] or 0), r[1], r[2]) for r in regs[:8] if len(r) >= 3]
        msg = _requete(base, f"SELECT count(*) FROM mail_message WHERE author_id = {pid} AND message_type = 'comment' AND create_date > now() - interval '30 days'", delai)
        res["messages_30d"] = int(msg[0][0]) if msg and msg[0][0].isdigit() else None
        if (_requete(base, "SELECT to_regclass('public.survey_user_input') IS NOT NULL") or [[""]])[0][0] in ("t", "true"):
            sv = _requete(base, f"SELECT count(*) FROM survey_user_input WHERE partner_id = {pid}", delai)
            res["survey_answers"] = int(sv[0][0]) if sv and sv[0][0].isdigit() else None
    return res


def set_user_active(base, uid, active, delai=30):
    """WRITE (web-monitor.py --ban-odoo-user / --unban-odoo-user, after confirmation): archives (active = false) or restores an Odoo account.
    Guards in the SQL itself: never the superuser, the admin or the public user (uid <= 2 and base.public_user), never an INTERNAL account when archiving
    (share = true required), and only an account in the opposite state. An archived account can no longer log in and its open sessions are
    invalidated by Odoo (the session token includes the « active » field). Returns True (changed), False (nothing to change: guard), None (impossible)."""
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        return None
    if uid <= 2 or not re.fullmatch(r"[\w.-]+", base or ""):
        return False
    guard = ("AND u.share AND u.active" if not active else "AND NOT u.active")
    sql = (f"UPDATE res_users u SET active = {'true' if active else 'false'}, write_date = (now() AT TIME ZONE 'utc') WHERE u.id = {uid} {guard} "
           "AND u.id NOT IN (SELECT res_id FROM ir_model_data WHERE module = 'base' AND name IN ('public_user', 'user_root', 'user_admin') AND model = 'res.users') "
           "RETURNING u.id")
    if VERBOSE:
        print("+ runuser -u postgres -- psql -d " + base + f" -tA -c \"UPDATE res_users SET active = {'true' if active else 'false'} WHERE id = {uid} …\" (ÉCRITURE)", file=sys.stderr)
    try:
        r = subprocess.run(POSTGRES_RUN + ["psql", "-d", base, "-v", "ON_ERROR_STOP=1", "-tA", "-c", sql], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, universal_newlines=True, errors="replace", timeout=delai)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return any(l.strip() == str(uid) for l in r.stdout.splitlines())


def registration_emails(base, days=90, limit=5000, delai=60):
    """[{id, when (epoch), event, name, email, state, partner_id, partner_email, login}] of the event registrations of the last DAYS days that have an
    e-mail address (most recent first), READ-ONLY: the caller checks the addresses (apps/_email_check.py). None if impossible."""
    days, limit = int(days), int(limit)
    rows = _requete(base,
        "SELECT r.id, floor(extract(epoch FROM r.create_date)), left(" + _titre_sql("e.name") + ", 60), left(replace(COALESCE(r.name, ''), E'\\n', ' '), 60), "
        "replace(COALESCE(r.email, ''), E'\\n', ' '), COALESCE(r.state, ''), COALESCE(r.partner_id, 0), replace(COALESCE(p.email, ''), E'\\n', ' '), "
        "COALESCE((SELECT u.login FROM res_users u WHERE u.partner_id = p.id ORDER BY u.id LIMIT 1), '') "
        "FROM event_registration r JOIN event_event e ON e.id = r.event_id LEFT JOIN res_partner p ON p.id = r.partner_id "
        f"WHERE COALESCE(r.email, '') <> '' AND r.create_date > now() - interval '{days} days' ORDER BY r.create_date DESC, r.id DESC LIMIT {limit}", delai)
    if rows is None:
        return None
    res = []
    for c in rows:
        if len(c) >= 9 and c[0].isdigit():
            res.append({"id": int(c[0]), "when": float(c[1] or 0), "event": c[2], "name": c[3], "email": c[4].strip(), "state": c[5],
                        "partner_id": int(c[6]) if c[6].isdigit() else 0, "partner_email": c[7].strip(), "login": c[8]})
    return res


def failed_mails_for(base, registration_id, email, delai=30):
    """Ids of the e-mails still in failure (state « exception ») linked to a registration (model event.registration) or addressed to `email` (email_to or a
    recipient contact with that address). READ-ONLY. None if impossible."""
    rid = int(registration_id)
    rows = _requete(base,
        "SELECT DISTINCT m.id FROM mail_mail m JOIN mail_message g ON g.id = m.mail_message_id WHERE m.state = 'exception' AND ("
        f"(g.model = 'event.registration' AND g.res_id = {rid}) OR position(lower({_sql_text(email)}) in lower(COALESCE(m.email_to, ''))) > 0 OR EXISTS ("
        "SELECT 1 FROM mail_mail_res_partner_rel x JOIN res_partner p ON p.id = x.res_partner_id "
        f"WHERE x.mail_mail_id = m.id AND lower(COALESCE(p.email, '')) = lower({_sql_text(email)}))) ORDER BY m.id", delai)
    if rows is None:
        return None
    return [int(r[0]) for r in rows if r and r[0].isdigit()]


def fix_registration_email(base, registration_id, partner_id, old, new, mail_ids=(), delai=60):
    """WRITE (odoo-mail-retry.py, after confirmation): replaces a wrong e-mail address by its correction, in ONE transaction:
      - the registration (event_registration.email), only if it still holds the old address;
      - its contact (res_partner.email, and email_normalized when the column exists), only if the contact still holds the old address;
      - the failed e-mails `mail_ids` (email_to), then puts them back in « Outgoing » (resend by Odoo's mail queue), only if still in failure.
    The login of an Odoo account is NEVER changed (the person may log in with it). Returns {"registration", "partner", "mails"} (counts) or None (impossible)."""
    try:
        rid, pid = int(registration_id), int(partner_id or 0)
        mids = sorted({int(i) for i in mail_ids})
    except (TypeError, ValueError):
        return None
    if not re.fullmatch(r"[\w.-]+", base or "") or not old or not new or "\t" in new or "\n" in new:
        return None
    normalized = _column_exists(base, "res_partner", "email_normalized")
    o, n = _sql_text(old), _sql_text(new)
    parts = [f"WITH x AS (UPDATE event_registration SET email = {n}, write_date = (now() AT TIME ZONE 'utc') WHERE id = {rid} AND email = {o} RETURNING 1) "
             "SELECT 'registration', count(*) FROM x;"]
    if pid:
        parts.append(f"WITH x AS (UPDATE res_partner SET email = {n}" + (f", email_normalized = lower({n})" if normalized else "")
                     + f", write_date = (now() AT TIME ZONE 'utc') WHERE id = {pid} AND email = {o} RETURNING 1) SELECT 'partner', count(*) FROM x;")
    if mids:
        ids = ", ".join(map(str, mids))
        parts.append(f"WITH x AS (UPDATE mail_mail SET email_to = replace(email_to, {o}, {n}) WHERE id IN ({ids}) AND state = 'exception' "
                     f"AND position({o} in COALESCE(email_to, '')) > 0 RETURNING 1) SELECT 'email_to', count(*) FROM x;")
        parts.append(f"WITH x AS (UPDATE mail_mail SET state = 'outgoing', write_date = (now() AT TIME ZONE 'utc') "
                     f"WHERE id IN ({ids}) AND state = 'exception' RETURNING 1) SELECT 'mails', count(*) FROM x;")
    if VERBOSE:
        print("+ runuser -u postgres -- psql -1 -d " + base + f" -tA -c \"UPDATE event_registration SET email = … WHERE id = {rid} …\" (ÉCRITURE, une transaction)", file=sys.stderr)
    commands = [x for p in parts for x in ("-c", p)]           # one -c per statement, all in ONE transaction (-1): everything or nothing
    try:
        r = subprocess.run(POSTGRES_RUN + ["psql", "-1", "-d", base, "-v", "ON_ERROR_STOP=1", "-tA", "-F", SEP] + commands,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, universal_newlines=True, errors="replace", timeout=delai)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    res = {"registration": 0, "partner": 0, "mails": 0}
    for line in r.stdout.splitlines():
        c = line.split(SEP)
        if len(c) == 2 and c[0] in res and c[1].isdigit():
            res[c[0]] = int(c[1])
    return res


def main():
    global VERBOSE
    arguments = sys.argv[1:]
    if "--version" in arguments:
        print(f"_odoo_db.py version {__version__}")
        return 0
    if "-v" in arguments or "--verbose" in arguments:
        VERBOSE = True
        arguments = [a for a in arguments if a not in ("-v", "--verbose")]
    if len(arguments) == 2 and arguments[0] == "--modules":          # installed modules: name, state, version, modification date (UTC), author - separated by tabs
        etat = modules_etat(arguments[1])
        if etat is None:
            print("modules illisibles (psql absent, base inaccessible, ou root requis)", file=sys.stderr)
            return 1
        for m in etat:
            print("\t".join((m["nom"], m["etat"], m["version"], m["maj"], m["auteur"].replace("\t", " "))))
        return 0
    if len(arguments) != 1 or arguments[0].startswith("-"):
        print("usage : _odoo_db.py [-v|--verbose] BASE   |   _odoo_db.py --modules BASE", file=sys.stderr)
        return 2
    u = utilisateurs(arguments[0])
    if u is None:
        print("utilisateurs illisibles (psql absent, base inaccessible, ou root requis)", file=sys.stderr)
        return 1
    for login, v in sorted(u.items(), key=lambda kv: kv[1]["uid"]):
        print(f"{v['uid']:6d}  {login}  {v['nom']}  ({v['type']})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        sys.exit(0)
