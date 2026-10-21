#!/usr/bin/env bash
# ========================================================================================================================
# Copyright (C) 2026 Services-Conseils Linux
# Copyright (C) 2026 Rencontres Linux au Québec contributors
#
# Ce fichier fait partie de la configuration nginx de Rencontres Linux Quebec. Logiciel libre : vous pouvez le
# redistribuer et/ou le modifier selon les termes de la GNU Affero General Public License publiee par la Free
# Software Foundation, soit la version 3 de la licence, soit (a votre choix) toute version ulterieure.
# Texte complet : https://www.gnu.org/licenses/agpl-3.0.html
# ========================================================================================================================
#
# run-all.sh — lanceur unique de la validation, a executer AVANT chaque deploiement. Une seule commande, un seul verdict :
#   0) presence des programmes et du dossier apps/ (installation incomplete signalee, avec la commande a lancer) ;
#   1) syntaxe de tous les programmes (bash -n, python3 -m py_compile) ;
#   2) ShellCheck sur tous les scripts Bash (0 signalement attendu : les exceptions voulues sont documentees par des
#      directives dans le code) ;
#   3) ruff sur le Python, s'il est installe (equivalent de ShellCheck pour Python) ;
#   4) la suite de tests (unittest, inclus dans Python), UNE FOIS PAR AWK DISPONIBLE (mawk, gawk, BusyBox) — gawk et
#      mawk n'interpretent pas les programmes awk de la meme facon (bug « awk -v » de nginx-log-audit.sh 1.24, invisible
#      sous mawk) ;
#   5) configuration deployee (/etc/nginx, /etc/fail2ban) comparee a la version testee (nginx-tools-tests/nginx-odoo/), pour
#      information : les differences sont signalees sans entrer dans le verdict (serveurs Odoo seulement) ;
#   6) controles du serveur REEL, en lecture seule, propres a son environnement (BigBlueButton : apps/_bbb.py ; Odoo :
#      app-health-check.py --target local), pour information : ils n'entrent pas dans le verdict.
# L'ENVIRONNEMENT (Odoo ou BigBlueButton) est detecte au depart (apps/_profile.py, ou --app NOM) : chaque module de test porte
# une etiquette « ENVIRONNEMENT = "commun" | "odoo" | "bbb" » et seuls les modules communs et ceux de CET environnement
# tournent. Serveur non reconnu (poste de developpement) ou --all-environments : tous les modules.
# Outils cherches dans le PATH, puis dans nginx-tools-tests/tools/ (executables statiques deposes la, ex. shellcheck, gawk, ruff).
# Ce qui n'a PAS pu etre verifie (outil absent, tests exigeant root ou un terminal) est dit explicitement dans le verdict.
# A la fin, STATISTIQUES (stats_runner.py) : duree totale et par passe, CPU, memoire, disque, programmes lances, et par programme le nombre de tests
# unitaires, fonctionnels, interactifs et de conformite (nature MESUREE pendant chaque test), desactives et en echec, et les tests les plus lents.
#
# HISTORIQUE DE VERSION (resume — voir run-all.changelog.txt pour le detail complet) :
#   1.192.20261020.222909 — test_docs: the legal company name is allowed as author of the Odoo module (author key of __manifest__.py only).
#   1.191.20261020.211944 — Personal configuration file ~/.run-all.conf (not .cfg); a legacy one with .cfg is renamed automatically.
#   1.190.20261020.175756 — Runs WITHOUT root (simulated root in the test copies only); tests never write the real /etc or /var (system defaults redirected, checked at the end); no more stop on « Broken pipe » (nginx-tools 1.137).
#   1.189.20261020.163255 — tools/ (static gawk 5.3.2 and ruff 0.16.9) now in the Git repository, with tools/LISEZMOI.md (versions, licences, sources, SHA-256).
#   1.188.20261020.112434 — Statistics at the end (duration, CPU, memory, disk, tests per program: unit / functional / interactive / conformity); personal data removed from the tests; FR/EN sample data and alignment tests; nginx-odoo/ read from NGINX_ODOO_DIR (not in git) (nginx-tools 1.134).
#   1.187.20261017.214019 — Tests of web-monitor 2.69 (IP seen, sorted title, configuration keys) (nginx-tools 1.128).
#   1.186.20261017.200717 — Residual files of the programs folder only reported (never deleted, the tests go on); test of a second Ctrl+C; web-monitor 2.68, app-log-live 1.85.
#   1.185.20261017.105442 — Tests of web-monitor 2.67 (compact table, profile fields, --group, --csv, --stats), language from the environment (nginx-tools 1.126).
#   1.184.20261016.173838 — Ctrl+C: timeout --foreground for each test module; tests of the registrations per ticket, sent e-mails, odoo-update-module 1.11, web-monitor columns, Ctrl+C (nginx-tools 1.125).
#   1.183.20261016.160728 — Tests: app-log-live --truncate, SSH accounts, RLQ* groups in columns, French screen without English (app-log-live 1.83, nginx-tools 1.124).
#   1.182.20261016.151148 — Residual lang/*.en.po of English-source programs detected (offered for deletion); docs page count computed; host-perf-audit cores (nginx-tools 1.123).
#   1.181.20261016.114848 — Tests: suspicious Odoo accounts, ban / watch, e-mail checks, host-perf-audit, app-log-live latency, invalid registration e-mails (web-monitor 2.65, app-log-live 1.82, odoo-mail-retry 1.10, nginx-log-audit 2.37, nginx-tools 1.122).
#   1.180.20261016.085519 — Tests: web-monitor --table systems/browsers/pages columns, app-log-live SSH port, grouped recommendations (app-log-live 1.81, web-monitor 2.64, nginx-tools 1.121).
#   1.179.20261016.065618 — Tests aligned with app-log-live 1.80 (code in English) and nginx-tools 1.120.
#   1.178.20261015.231203 — Tests aligned with web-monitor 2.63 (code in English), apps/_i18n.py 1.14 and nginx-tools 1.119.
#   1.177.20261015.220452 — Tests aligned with app-log-check 2.20 and odoo-mail-retry 1.9 (code in English), apps/_i18n.py 1.13 and nginx-tools 1.118.
#   1.176.20261015.212130 — Tests aligned with app-health-check 2.22 (code in English) and nginx-tools 1.117.
#   1.175.20261015.201400 — Tests aligned with odoo-mail-retry 1.8, odoo-chat-post 1.4 and odoo-docs 1.1 (code in English) and nginx-tools 1.116.
#   1.174.20261015.195053 — Tests adaptés à zip-versions 1.12 (code en anglais, catalogue fr.po).
#   1.173.20261015.191427 — Tests : nouveau test i18n (programme écrit en anglais).
#   1.172.20261015.183524 — Tests : test_odoo_docs (faux Odoo), odoo-docs dans les listes de conventions, test zip-versions.
#   1.171.20261015.175527 — Tests : documentation FR/EN (test_docs : parité, aide réelle, XML valide, aucune donnée personnelle).
#   1.170.20261015.172851 — Tests : membres des groupes RLQ* ; ShellCheck 0.11.0 propre.
#   1.169.20261015.170611 — Tests : modules rlq* toujours affichés au démarrage (test_app_log_live).
#   1.168.20261015.143436 — Tests : --anonymize (test_anonymiser, 15 tests).
#   1.167.20261015.105354 — Tests : odoo-chat-post, clé API du robot (6 tests).
#   1.166.20261015.103039 — Tests : odoo-chat-post --create-bot, 3 tests.
#   1.165.20261015.095427 — Tests : odoo-chat-post accès restreint (--members), 5 tests.
#   1.164.20261015.092124 — Tests : aide testée en français (--lang en), couleur zip-versions, pare-feu, tri des customs.
#   1.163.20261015.090500 — Tests : odoo-chat-post.py 1.0 (test_odoo_chat_post.py, faux serveur XML-RPC d'Odoo).
#   1.162.20261015.083721 — Tests : réglages sauvegardés, bannis déjà bloqués, customs au démarrage, connectés, 429 (test_reglages_bannis_limites).
#   1.161.20261015.080630 — Tests : root au début, LOG_KEEP_DAYS, modules rlq* toujours affichés.
#   1.160.20261015.073057 — Tests : colonnes, date des fichiers de config, relance sudo.
#   1.159.20261015.065821 — Tests : IP à débannir, connexions, anglais, fichier commun.
#   1.158.20261014.214019 — Tests : modules customs d'abord, version du .zip.
#   1.157.20261014.203136 — Tests : détection du service d'Odoo, --lines 50.
#   1.156.20261014.190654 — Tests : archive .zip, versions avant / après, derniers modules.
#   1.155.20261014.182101 — Tests : warm-up (pages, langues, sondages optionnels).
#   1.154.20261014.175821 — Tests : fichier commun app-default.conf, sauvegarde des réglages.
#   1.153.20261014.174013 — Tests : préchauffage, heure locale des modules.
#   1.152.20261014.170802 — Tests : surlignage +mot / -mot.
#   1.151.20261014.164721 — Tests : bloc de démarrage d'app-log-live condensé.
#   1.150.20261014.161550 — Tests : sortie lisible de odoo-update-module.sh.
#   1.149.20261014.154520 — Tests : Ctrl+C pendant une question (Python et bash).
#   1.148.20261014.151232 — Tests : tableau des modules et chiffres en couleurs.
#   1.147.20261014.114859 — Tests : chien de garde silencieux pendant une question.
#   1.146.20261014.110643 — Tests : odoo-update-module.sh ; étiquette des personnes sans doublon.
#   1.145.20261014.103454 — Tests : derniers modules installés avec leur date.
#   1.144.20261013.231736 — Tests : alerte du service arrêté.
#   1.143.20261013.224353 — Tests : chien de garde du direct.
#   1.142.20261013.220907 — Tests : l'IP externe ne retient pas l'affichage.
#   1.141.20261013.215347 — Tests : surlignage des mots (--highlight).
#   1.140.20261013.214058 — Tests : masquage des secrets en temps linéaire.
#   1.139.20261013.205851 — Tests : amonts d'Odoo 17 (nginx-hardening, app-log-live) ; nginx-odoo/ synchronisé.
#   1.138.20261013.203700 — Tests : websocket sur la configuration livrée (variable proxy_pass).
#   1.137.20261013.201708 — Tests : secrets masqués (app-log-live).
#   1.136.20261013.195358 — Tests : websocket d'Odoo dans nginx-hardening.sh.
#   1.135.20261013.191845 — Tests : conflits réessayés et échecs définitifs (app-log-live).
#   1.134.20261013.163324 — Tests : versions du jour (zip-versions), étape 0a, détails des erreurs, modules d'Odoo.
#   1.133.20261013.161254 — Test : ancien nom trouvé dans nginx (étape 0e).
#   1.132.20261013.155822 — Test : couleurs du sommaire.
#   1.131.20261013.155051 — Test : adresse non répétée avec la touche b.
#   1.130.20261013.153600 — Tests : odoo-warmup.py ; question oui/non du courriel (étape 0d).
#   1.129.20261013.160500 — Test : requêtes lentes d'assets et de vues (cache à froid).
#   1.128.20261013.153500 — Test : journal quotidien d'un lancement filtré.
#   1.127.20261013.150500 — Test : questions du courriel avec sortie redirigée.
#   1.126.20261013.143500 — Test : attente disque et type de disques.
#   1.125.20261013.141500 — Tests : --watch pages et sondages, requête lente en Python.
#   1.124.20261013.123500 — Tests : étape 0e (changement de nom DNS).
#   1.123.20261013.121500 — Test : diagnostic du certificat SSL.
#   1.122.20261013.112000 — Test : URL avec guillemets alignée.
#   1.121.20261013.105200 — Tests : relance de web-monitor.py par la touche b, recommandations gardées 48 h.
#   1.120.20261013.103000 — --install-missing (ShellCheck, ruff) ; apps/_courriel.py ; tests du courriel.
#   1.119.20261013.100000 — Tests : amonts nginx, IP externe, alignement websocket.
#   1.118.20261013.091500 — Tests : diagnostic du site, serveur BBB, Ctrl-C répété.
#   1.117.20261013.084000 — Tests : CMS WordPress, log_format, base64, chemins dans la traduction.
#   1.116.20261013.081500 — Tests : sondes /wp, balayage de 404, touche b, --sent.
#   1.115.20261012.231200 — Tests : --not-found, espace disque, site lab, iptables-persistent, page de maintenance.
#   1.114.20261012.220800 — Tests : alignement des messages d'Odoo, période des statistiques, fuseau horaire, cache nginx, rotation du journal.
#   1.113.20261012.213000 — Tests : service d'après db_user, installation des programmes manquants.
#   1.112.20261012.195500 — Tests : détection de la configuration d'Odoo (test_odoo_conf.py), ports, logfile.
#   1.111.20261012.183000 — Tests : démarrage en anglais sans français, couleurs et traduction, causes des requêtes lentes ; test_saisie déclare son environnement.
#   1.111.20261012.183000 — Saisies avec édition (read -e) ; nouveau test_saisie.py ; tests adaptés à la coupure par défaut des noms.
#   1.109.20261012.103600 — Fichier de configuration créé au premier démarrage ; tests test_config_defaut.py (création, modèles complets).
#   1.108.20261012.094953 — Tests : état de web-monitor isolé (WEB_MONITOR_STATE_DIR), alignement du sommaire, colonnes après traduction.
#   1.107.20261012.084701 — Tests de app-log-live.py 1.29 (diagnostic des recommandations de web-monitor.py).
#   1.106.20261011.231758 — Tests de app-log-live.py 1.28 (niveaux 1 à 9 du tableau de bord, --level, touches 1 à 9).
#   1.105.20261011.211500 — Tests de app-log-live.py 1.27 (espace avant HTTP, tableau de bord traduit).
#   1.104.20261011.180500 — ShellCheck récent : SC2317 (corps de run_all_nettoyer, appelée indirectement) ignoré.
#   1.103.20261011.183500 — Tests des réseaux partagés (nginx-hardening.sh 2.30, nginx-odoo-config 1.9).
#   1.102.20261011.172500 — Test de la section [11] adapté (réseaux partagés sans alerte) ; nginx-odoo-config 1.8.
#   1.101.20261011.170500 — Tests de la section [11] de nginx-log-audit.sh 2.29 et de la limite par cookie (nginx-odoo-config 1.7).
#   1.100.20261011.144500 — Ctrl+C : confirmation (apps/_i18n.sh) ; passe de tests isolée (setsid) ; test_ctrl_c ; correction SC2002 de nginx-hardening.sh 2.29.
#   1.99.20261011.133251 — Nouveau test de l'étape 12 de nginx-hardening.sh (rechargement de nginx) ; env-dev.conf ouvert (nginx-odoo-config 1.6).
#   1.98.20261011.093635 — Ctrl+C arrête toute la suite (code 130), en français comme en anglais.
#   1.97.20261010.225415 — Les tests n'héritent plus des variables du traducteur (NGINX_TOOLS_I18N, NGINX_TOOLS_I18N_LANGUE, NGINX_TOOLS_LANG) quand run-all.sh est lancé en anglais.
#   1.96.20261010.215000 — Affichage francais ou anglais (--lang) ; fichier de configuration (LANGUAGE, ALL_ENVIRONMENTS, APP, VERBOSE) et -c/--config ; test_i18n.py reecrit pour les catalogues PO.
#   1.95.20261010.200936 — Tests : web-monitor.py 2.47 (affichage fr/en, catalogues lang/, test_i18n.py).
#   1.94.20261010.173057 — Tests : web-monitor.py 2.46 (minutes, largeur des colonnes).
#   1.93.20261010.164501 — Tests : app-log-live.py 1.24 (adresses recommandees par web-monitor) ; WEB_MONITOR_STATE_DIR isole.
#   1.92.20261010.143016 — Tests : web-monitor.py 2.45 (--table, --sort).
#   1.91.20261009.230224 — Tests : app-log-live.py 1.23 (sondage de confirmation).
#   1.90.20261009.170830 — Tests : nginx-hardening.sh 2.26 (verification odoo-auth).
#   1.89.20261009.153721 — Tests : app-log-live.py 1.22 (images base64).
#   1.88.20261009.150500 — Tests : app-log-live.py 1.21 (billet, courriels a renvoyer) et nginx-hardening.sh 2.25 (etape 16).
#   1.87.20261009.142644 — Tests : app-log-live.py 1.20 (User-Agent, --watch) et nginx-odoo-config 1.5.
#   1.86.20261009.114822 — Tests : app-log-live.py 1.19 (proposition de bannissement) et nginx-log-audit.sh 2.26 (--evidence).
#   1.85.20261009.112443 — Tests : app-log-live.py 1.18 et app-log-check.py 2.14 ; run_pty repond aux questions de fin de Ctrl-C.
#   1.84.20261009.105804 — Tests : app-log-live.py 1.17 (robots et vrais visiteurs).
#   1.83.20261009.104326 — Fichiers residuels : propose de les effacer (o/N), sinon arret ; test de l'etape 15 du setup.
#   1.82.20261009.085618 — Tests : app-log-live.py 1.16 (sondes locales, URL raccourcies).
#   1.81.20261008.235744 — Tests : app-log-live.py 1.15 (la touche b n'inclut jamais le serveur).
#   1.80.20261008.191922 — Tests : app-log-live.py 1.14 (statistiques des visites du site).
#   1.79.20261008.173412 — Tests : app-log-live.py 1.13 (--exclude-ip, --accentuate-group, --chime, --time-report).
#   1.78.20261008.124728 — Tests : app-log-live.py 1.12 (menu des touches, presence triee, comptes resumes) ; nginx-odoo-config 1.4 (inclusions par nom exact).
#   1.77.20261008.120306 — Test : couleurs conservees avec --report-err (nginx-hardening.sh 2.23, _rapport 1.9).
#   1.76.20261008.112757 — Tests : nginx-hardening.sh 2.22 (team-ips-*.conf existent toujours ; joker sans fichier = nginx -t en echec).
#   1.75.20261008.113500 — Tests : nginx-hardening.sh 2.21 (message de nginx -t, configuration deja invalide).
#   1.74.20261008.103818 — Tests : app-log-live.py 1.11 (tableau de bord, touches, sante, journal quotidien, largeurs).
#   1.73.20261008.084031 — Tests : isolation des vrais /etc/default (listes), fichiers residuels signales ; app-log-live.py 1.10.
#   1.72.20261007.232518 — Tests : couleurs explicites de app-log-live.py ; regle apple-touch-icon de la configuration nginx.
#   1.71.20261007.231352 — Tests : presentation compacte de app-log-live.py.
#   1.70.20261007.223004 — Tests : [banni], requetes lentes, filtres et resume de app-log-live.py.
#   1.69.20261007.221217 — Tests : alignement, requetes suspectes et video inverse de app-log-live.py.
#   1.68.20261007.200504 — Tests : destinataire dans le menu de odoo-mail-retry.py.
#   1.67.20261007.175327 — Tests : odoo-mail-retry.py ; non-regression du sujet des courriels.
#   1.66.20261007.171721 — Tests : cache des adresses, sommaire et diagnostics de courriel, 5 jours les plus actifs ; sentinelle sur le cache.
#   1.65.20261007.093208 — Listes d'adresses hors des archives : sentinelle sur /etc/default/nginx-tools-*.conf, tests des listes et des lieux.
#   1.64.20261002.214327 — Premiere ligne de TOUTE execution (meme --help) : nom et version. Tests : preuves de bannissement, geoip-bin, en-tetes, rapport par heure.
#   1.63.20261002.201545 — Tests : rapport par heure et par jour (app-log-check.py --by-hour).
#   1.62.20261002.165312 — Tests : retour arriere, adresses du sommaire, lecture --details, app-log-live 1.2 (pays, voie rapide, rappel, serveur local, conflit SQL).
#   1.61.20261002.120134 — Tests : regle wp-admin (configuration), regle manquante (web-monitor), app-log-live 1.1, version de la configuration.
#   1.60.20261002.073514 — Tests par environnement (Odoo ou BBB, detectes ; --app, --all-environments, --list) ; etape 6 : controles du serveur reel ; /proc isole.
#   1.59.20261002.064915 — Tests : fournisseur d'acces, refus ACL, version dans le nom des archives.
#   1.58.20261001.202502 — Tests de zip-versions.py 1.2 (archives d'autres programmes, coherence).
#   1.57.20261001.143624 — apps/_bbb.py attendu ; tests test_bbb.py.
#   1.56.20261001.094048 — Suite renommee nginx-tools-tests (archive et dossier) ; ancienne copie dans tests/ signalee.
#   1.55.20261001.092458 — Nouveau programme zip-versions.py : attendu, conventions, tests (test_zip_versions.py).
#   1.54.20261001.090925 — Tests : redirection de nginx rejetee ; blocs de redirection apres les regles de securite (configuration).
#   1.53.20260930.225745 — Tests : diagnostics et corrections faits par web-monitor.py (--apply), numerotation du rapport.
#   1.52.20260930.163902 — Option --report-err ; composant commun apps/_rapport.* ajoute a la liste des fichiers attendus ; tests du rapport.
#   1.51.20260930.132809 — Sentinelle des fichiers de configuration reels ; tests des heures multiples, de --times, de la retention et de ./ ignore.
#   1.50.20260930.123230 — Tests : configuration en couches (odoo-backup.sh, app-health-check.py), renommage avant le timer, timers vers un fichier absent.
#   1.49.20260930.093133 — Tests : configuration de odoo-backup.sh dans /etc/default (ordre, ancien emplacement, creation, timer) ; regroupement.
#   1.48.20260930.090527 — Tests : Googlebot sur BBB et Odoo, pages demandees, 403 de navigateurs (une adresse domine).
#   1.47.20260930.084200 — Tests : en-tetes de courriel lus par un analyseur (plus de dependance au PID), filtre BBB identique, [7], Ctrl-C, HSTS.
#   1.46.20260930.081347 — Tests : motif « A && B || C » (independant de la version de ShellCheck), refus 403 de navigateurs.
#   1.45.20260930.072401 — Tests : connexions structurees et en couleur, recommandations BBB.
#   1.44.20260929.235632 — Tests : HSTS avec redirection vers le meme nom (avertissement, echec et conseil HAProxy).
#   1.43.20260929.195459 — Aide : options par ordre alphabetique ; test AideTriee (huit programmes).
#   1.42.20260929.193615 — Tests : --days, configuration creee a la premiere execution ; vocabulaire des tests.
#   1.41.20260929.192148 — Tests : colonnes J-1 et J-2, options d'Odoo du processus en cours et du script de demarrage.
#   1.40.20260929.185720 — Tests : --check-email-dns sans --target, etape 13 sans resultat, fail2ban arrete.
#   1.39.20260929.182259 — Tests : app-health-check.py complet sans SMTP, relais injoignable, couleurs.
#   1.38.20260929.180340 — Tests de odoo-backup.sh 1.1 : format d'Odoo (.zip, .tar.xz), restauration, retention par format.
#   1.37.20260929.151644 — Tests : odoo-backup.sh, durcissement BBB, surveillance de la sauvegarde.
#   1.36.20260929.145745 — Tests : courriel (DNS, envoi reel, modes TLS), etape 13, utilisateurs connus hors equipe.
#   1.35.20260929.144332 — Tests : sonde legere /web/health, ligne geante tronquee.
#   1.34.20260929.134422 — Tests des verrous et de la source unique des adresses de l'equipe (test_locks, etape 12).
#   1.33.20260929.130357 — Tests : --details, adresses partagees, limit_memory_hard=0.
#   1.32.20260929.123856 — Tests de la liste unique de l'equipe (quatre outils) ; garde : tout apps/*.conf est un profil.
#   1.31.20260929.084225 — Tests en echec relances seuls : echec confirme (bloquant) ou [INSTABLE] (last-instable.log).
#   1.30.20260929.083206 — Tests : jail nginx-blocked-probes, ignoreip de fail2ban, refus journalises, sommaire.
#   1.29.20260929.080620 — Tests du format combined_host (configuration, lecture awk) ; noms dans la recommandation.
#   1.28.20260928.231233 — Tests : part du trafic des utilisateurs connectes et details par compte.
#   1.27.20260928.224616 — Tests : --list-users, recommandation reformulee ; configuration testee a jour (equipe, Tailscale).
#   1.26.20260928.220753 — Tests des plages d'adresses (equipe, liste blanche nginx, sommaire) ; configuration testee a jour.
#   1.25.20260928.215040 — Tests : IP connectee a Odoo jamais proposee au bannissement ; section des connexions du sommaire.
#   1.24.20260928.212833 — Tests : directive su (logrotate), variables non initialisees sur BBB, nom de l'utilisateur Odoo.
#   1.23.20260928.211633 — Tests isoles de la machine : PATH sans commandes systeme sensibles, detection par fichiers isolee.
#   1.22.20260928.141712 — Tests : certificat TLS (vrai serveur local), recommandations, compatibilite Python 3.8.
#   1.21.20260928.103708 — Tests : espace des journaux, nos programmes exclus, workers d'Odoo, --unban-check, retention N mois, appareils (--stats).
#   1.20.20260928.094028 — Tests des appareils des visiteurs et des 404 de nginx (web-monitor.py 2.9).
#   1.19.20260928.091309 — Tests : echecs de synchronisation (diagnostic, suivi, cron), PATH sous cron, alerte web-monitor.
#   1.18.20260928.083340 — Tests des preuves avant bannissement (nginx-log-audit.sh 2.5) et de web-monitor.py 2.7.
#   1.17.20260927.224845 — Tests de la classification du sommaire sur les cas reels (web-monitor.py 2.6).
#   1.16.20260927.220922 — Tests du bannissement en fin de passage et de --ban-recommended (web-monitor.py 2.5).
#   1.15.20260927.215447 — Tests de --export-bans / --import-bans et du nouveau --status.
#   1.14.20260927.212124 — Etape 0 : programmes presents (archive extraite sans copie reconnue) ; plus de plantage si apps/ manque.
#   1.13.20260927.202645 — Changelogs dans doc/ ; tests --version/--changelog sans application et repli du changelog.
#   1.12.20260927.200712 — Noms en anglais : tests/README.md, tests/helpers.py, tests/tools/ ; test des noms de fichiers.
#   1.11.20260927.192332 — Tests de la phase 2 (raisonnement --ban, sortie aeree, magenta, entonnoir, pare-feu, less).
#   1.10.20260927.145909 — Programmes renommes ; bibliotheques apps/ validees (ShellCheck, ruff) ; tests multi-application.
#   1.9.20260927.101228 — Test des noms d'options en anglais (tous les programmes) ; tests de --summary enrichis.
#   1.8.20260927.094449 — Tests de web-monitor.py --bilan (valeurs exactes, periode partielle).
#   1.7.20260927.093411 — Tests de --unban-check (verdicts ; levee avec un fichier non executable).
#   1.6.20260927.092739 — Tests : robot inoffensif jamais propose (faux positif reel), vrai scanner toujours propose.
#   1.5.20260926.230736 — Test du setup adapte au message de verification fail2ban-regex explique (setup 1.21).
#   1.4.20260926.225500 — Test de synchronisation de la copie de configuration : reussit (au lieu d'etre
#                          « non verifie ») sur un serveur, ou seule la copie de la suite existe.
#   1.3.20260926.223504 — Configuration nginx fournie dans tests/nginx-odoo/ (tests de configuration, plus de tests
#                          desactives faute de modeles) ; nouvelle etape 5 : configuration deployee comparee a la testee.
#   1.2.20260926.211237 — Raison reelle des tests desactives ; repertoires temporaires oublies supprimes (filet) ;
#                          fonction grep_q devenue inutile retiree ; executables gawk et ruff fournis dans tests/tools/.
#   1.1.20260926.165635 — Echec signale par un code de sortie 1 SANS faux « ARRET INATTENDU » (le test final
#                          declenchait le piege ERR) ; sortie de ruff compacte (une ligne par defaut).
#   1.0.20260926.132022 — Version initiale.
#
# Usage : nginx-tools-tests/run-all.sh [-v|--verbose] [--version] [--changelog]
#   Code de sortie : 0 = tout ce qui a ete execute a reussi ; 1 = au moins un echec.

set -euo pipefail

# shellcheck disable=SC2154  # « ec » est affectee DANS le texte du trap (ec=$?), a l'execution (faux positif).
trap 'ec=$?; echo "*** ARRÊT INATTENDU DE run-all.sh (code $ec) À LA LIGNE $LINENO : $BASH_COMMAND" >&2' ERR
# Ctrl+C : apps/_i18n.sh demande confirmation (« Interrompre le programme ? [o/N] ») ; si oui, run_all_nettoyer arrête la passe de tests (son propre groupe de processus) avant la sortie.
JOB_PID=""
# shellcheck disable=SC2317,SC2329  # appelée indirectement : CTRL_C_NETTOYAGE (apps/_i18n.sh) et le piège TERM
run_all_nettoyer() {
    if [[ -n "$JOB_PID" ]]; then kill -TERM -- "-$JOB_PID" 2>/dev/null || true; fi
    echo >&2; echo "Interrompu (Ctrl+C) : arrêt de run-all.sh." >&2
}
# shellcheck disable=SC2034  # lue par apps/_i18n.sh
CTRL_C_NETTOYAGE=run_all_nettoyer
trap 'run_all_nettoyer; exit 143' TERM

readonly SCRIPT_VERSION="1.192.20261020.222909"
RUN_ALL_DEBUT=$(date +%s)
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; readonly TESTS_DIR
PROG_DIR="${TEST_SCRIPTS_DIR:-$(dirname "$TESTS_DIR")}"; readonly PROG_DIR
# Changelog dans le sous-repertoire doc/ ; repli sur l'ancien emplacement (a cote du programme) tant que
# l'installation n'a pas ete reorganisee.
CHANGELOG_FILE="$TESTS_DIR/doc/run-all.changelog.txt"
if [[ ! -r "$CHANGELOG_FILE" && -r "$TESTS_DIR/run-all.changelog.txt" ]]; then CHANGELOG_FILE="$TESTS_DIR/run-all.changelog.txt"; fi
readonly CHANGELOG_FILE
VERBOSE=0; APP_FORCE=""; TOUS_ENVIRONNEMENTS=0; LISTE_SEULE=0; INSTALLER_MANQUANTS=0

# Langue d'affichage (en ou fr) : --lang, RUN_ALL_LANG, LANGUAGE du fichier de configuration, LC_ALL / LANG — apps/_i18n.sh traduit la sortie (rien ne change en français).
if [[ -r "$PROG_DIR/apps/_i18n.sh" ]]; then
    # shellcheck source=/dev/null  # bibliothèque livrée avec les programmes
    . "$PROG_DIR/apps/_i18n.sh"
    i18n_relancer run-all RUN_ALL_LANG "$0" "$@"
    # Les programmes lancés par la suite (et dont la sortie est analysée) restent en français : seule la sortie de run-all.sh est traduite.
    [[ -n "${NGINX_TOOLS_I18N:-}" ]] && export NGINX_TOOLS_LANG=fr
    # Fichier de configuration (/etc/default/run-all.conf PUIS ~/.run-all.conf ; -c/--config FICHIER : ce fichier seul) : valeurs par défaut des options.
    # shellcheck disable=SC2034  # lue par apps/_i18n.sh (config_creer_defaut)
    CFG_DOSSIER_DOC="$TESTS_DIR/doc"; config_lire run-all "$@"        # premier démarrage : crée le fichier de configuration (modèle : doc/run-all.conf.example)
    export NGINX_TOOLS_CONFIG_CREER=0                                  # les programmes testés, eux, ne créent jamais de fichier dans le vrai /etc/default
    config_defaut TOUS_ENVIRONNEMENTS ALL_ENVIRONMENTS --all-environments booleen
    config_defaut APP_FORCE APP --app texte
    config_defaut INSTALLER_MANQUANTS INSTALL_MISSING --install-missing booleen
    config_defaut VERBOSE VERBOSE --verbose booleen
fi

# --report-err : rapport d'erreurs à copier-coller en fin d'exécution (programme, version, serveur, échecs…) — apps/_rapport.sh
if [[ -r "$PROG_DIR/apps/_rapport.sh" ]]; then
    # shellcheck source=/dev/null  # bibliothèque livrée à côté du programme
    . "$PROG_DIR/apps/_rapport.sh"
    rapport_si_demande "$TESTS_DIR/run-all.sh" "$SCRIPT_VERSION" "$PROG_DIR" "$@"
fi
# Première ligne de TOUTE exécution, même avec --help : le nom et la version du programme (--version l'affiche lui-même).
case " $* " in *" --version "*) ;; *) echo "run-all.sh v$SCRIPT_VERSION" ;; esac
if declare -F config_afficher >/dev/null; then
    case " $* " in *" --version "*|*" --changelog "*) ;; *) config_afficher ;; esac
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        -v|--verbose) VERBOSE=1; shift ;;
        --all-environments) TOUS_ENVIRONNEMENTS=1; shift ;;
        --app) APP_FORCE="${2:-}"; [[ -n "$APP_FORCE" ]] || { echo "--app attend un nom (odoo, bbb…)" >&2; exit 1; }; shift 2 ;;
        -c|--config) shift 2 ;;                # lus avant (apps/_i18n.sh : config_lire)
        --config=*|--lang=*) shift ;;
        --lang) shift 2 ;;
        --install-missing) INSTALLER_MANQUANTS=1; shift ;;
        --list) LISTE_SEULE=1; shift ;;
        --version) echo "run-all.sh version $SCRIPT_VERSION"; exit 0 ;;
        --changelog)
            if [[ ! -r "$CHANGELOG_FILE" ]]; then echo "Changelog introuvable : $CHANGELOG_FILE" >&2; exit 1; fi
            if [[ -t 1 ]]; then
                sed -E $'s/([0-9]+\\.[0-9]+\\.[0-9]{8}\\.[0-9]{6})/\\x1b[1;36m\\1\\x1b[0m/' "$CHANGELOG_FILE" || true  # lecteur ferme plus tot : SIGPIPE attendu
            else
                cat "$CHANGELOG_FILE" || true  # lecteur ferme plus tot (| head) : SIGPIPE attendu, pas une erreur
            fi
            exit 0 ;;
        -h|--help)
            cat <<'AIDE'
Usage : nginx-tools-tests/run-all.sh [OPTION]...
Suite de validation : présence des programmes, syntaxe, ShellCheck, ruff, tests (un passage par awk), configuration.

Options (par ordre alphabétique) :
  --all-environments           exécuter les tests de TOUS les environnements (Odoo et BigBlueButton), quel que soit le serveur
  --app NAME                   environnement à tester : odoo, bbb… (profil apps/NAME.conf ; défaut : détecté sur ce serveur)
  --changelog                  affiche le journal des modifications
  -c, --config FILE            fichier de configuration à lire SEUL (défaut : /etc/default/run-all.conf puis ~/.run-all.conf)
  -h, --help                   affiche cette aide et quitte
  --install-missing            installer les logiciels de validation absents (ShellCheck par apt-get, ruff par apt-get ou pip) ; il faut être root
  --lang LANG                  langue d'affichage : en ou fr (défaut : selon LC_ALL / LC_MESSAGES / LANG)
  --list                       affiche l'environnement détecté et les modules de test retenus, sans rien exécuter
  --report-err                 afficher à la fin un rapport d'erreurs à copier-coller (programme, version, serveur,
                               échecs, avertissements) ; désactive couleurs et questions interactives
  -v, --verbose                détail de chaque vérification
  --version                    affiche la version et quitte
AIDE
            exit 0
            ;;
        --report-err) shift ;;                 # traité avant (apps/_rapport.sh) ; accepté ici avec --help, --version…
        *) echo "Argument inconnu : $1" >&2; exit 1 ;;
    esac
done

if [[ -t 1 ]]; then
    C_RED=$'\x1b[1;31m'; C_YELLOW=$'\x1b[1;33m'; C_GREEN=$'\x1b[1;32m'; C_CYAN=$'\x1b[1;36m'; C_RESET=$'\x1b[0m'
else
    C_RED=""; C_YELLOW=""; C_GREEN=""; C_CYAN=""; C_RESET=""
fi
[[ -d "$TESTS_DIR/tools" ]] && export PATH="$TESTS_DIR/tools:$PATH"

# --install-missing : ShellCheck et ruff absents sont installés (apt-get, sinon pip pour ruff) ; sans cette option, les étapes 2 et 3 sont seulement ignorées.
installer_manquants() {
    local cmd="$1" paquet="$2" pip_paquet="${3:-}"
    command -v "$cmd" >/dev/null 2>&1 && return 0
    if (( EUID != 0 )); then echo "  $cmd absent : --install-missing demande les droits root (sudo)." >&2; return 0; fi
    if command -v apt-get >/dev/null 2>&1 && DEBIAN_FRONTEND=noninteractive apt-get install -y "$paquet" >/dev/null 2>&1 && command -v "$cmd" >/dev/null 2>&1; then
        echo "  $cmd installé (paquet $paquet)."
    elif [[ -n "$pip_paquet" ]] && command -v pip3 >/dev/null 2>&1 && pip3 install --break-system-packages "$pip_paquet" >/dev/null 2>&1; then
        echo "  $cmd installé (pip $pip_paquet)."
    else
        echo "  Installation de $cmd en échec : apt-get install $paquet${pip_paquet:+ (ou pip3 install $pip_paquet)} et lire l'erreur." >&2
    fi
    return 0
}
if (( INSTALLER_MANQUANTS )); then
    installer_manquants shellcheck shellcheck
    installer_manquants ruff ruff ruff
fi

ECHECS=0
NON_VERIFIE=()
ok()   { echo "  ${C_GREEN}[OK]${C_RESET}    $1"; }
ko()   { echo "  ${C_RED}[ÉCHEC]${C_RESET} $1"; ECHECS=$((ECHECS + 1)); }
skip() { echo "  ${C_YELLOW}[IGNORÉ]${C_RESET} $1"; NON_VERIFIE+=("$1"); }
titre() { echo; echo "${C_CYAN}=== $1 ===${C_RESET}"; }
detail() { if [[ "$VERBOSE" == "1" ]]; then sed 's/^/      /'; else cat >/dev/null; fi; }

cd "$PROG_DIR"

# --- Environnement de CE serveur : Odoo ou BigBlueButton (profil apps/<nom>.conf, detecte ou force par --app) -------------
# ENV_APP vide = serveur non reconnu (poste de developpement, aucune ou plusieurs applications) : tous les modules tournent.
ENV_APP=""; ENV_LABEL=""; ENV_ORIGINE=""
if [[ -n "$APP_FORCE" ]]; then
    ENV_APP="$APP_FORCE"; ENV_LABEL="$APP_FORCE"; ENV_ORIGINE="forcé (--app)"
    if [[ ! -f "$PROG_DIR/apps/$APP_FORCE.conf" ]]; then
        profils=()
        for f in "$PROG_DIR"/apps/*.conf; do [[ -f "$f" ]] && profils+=("$(basename "$f" .conf)"); done
        echo "ERREUR : profil d'application inconnu : $APP_FORCE (profils : ${profils[*]:-aucun})" >&2
        exit 1
    fi
    ENV_LABEL=$(sed -n 's/^APP_LABEL="\(.*\)"/\1/p' "$PROG_DIR/apps/$APP_FORCE.conf" | head -1)
elif [[ -r "$PROG_DIR/apps/_profile.py" ]] && command -v python3 >/dev/null 2>&1; then
    detecte=$(cd "$PROG_DIR/apps" && python3 -c "import _profile; p = _profile.charger_profil_app('.', None); print(p['APP_NAME'] + '|' + p['APP_LABEL'])" 2>/dev/null) || detecte=""
    if [[ -n "$detecte" ]]; then ENV_APP=${detecte%%|*}; ENV_LABEL=${detecte#*|}; ENV_ORIGINE="détecté automatiquement"; fi
fi
if (( TOUS_ENVIRONNEMENTS )); then ENV_ORIGINE="${ENV_ORIGINE:+$ENV_ORIGINE ; }tous les environnements demandés (--all-environments)"; fi

# Modules de test : l'etiquette « ENVIRONNEMENT = "…" » de chacun (commun, odoo, bbb) decide s'il tourne sur ce serveur.
MODULES=(); MODULES_ECARTES=(); ECARTES_ENV=""
for f in "$TESTS_DIR"/test_*.py; do
    m=$(basename "$f" .py)
    etiquette=$(sed -n 's/^ENVIRONNEMENT = "\([a-z0-9_-]*\)".*/\1/p' "$f" | head -1)
    etiquette=${etiquette:-commun}
    if [[ "$etiquette" == "commun" || -z "$ENV_APP" || "$etiquette" == "$ENV_APP" ]] || (( TOUS_ENVIRONNEMENTS )); then
        MODULES+=("$m")
    else
        MODULES_ECARTES+=("$m"); ECARTES_ENV="$etiquette"
    fi
done
if (( LISTE_SEULE )); then
    echo "Environnement : ${ENV_LABEL:-non reconnu (tous les modules sont retenus)}${ENV_APP:+ ($ENV_APP)}${ENV_ORIGINE:+ — $ENV_ORIGINE}"
    echo "Modules retenus (${#MODULES[@]}) : ${MODULES[*]}"
    echo "Modules écartés (${#MODULES_ECARTES[@]}) : ${MODULES_ECARTES[*]:-aucun}"
    exit 0
fi
mapfile -t BASH_PROGS < <(ls ./*.sh ./apps/*.sh 2>/dev/null; echo "$TESTS_DIR/run-all.sh")
mapfile -t PY_PROGS < <(ls ./*.py ./apps/*.py 2>/dev/null)
echo "Programmes : $PROG_DIR"
echo "Environnement : ${ENV_LABEL:-non reconnu}${ENV_APP:+ ($ENV_APP)}${ENV_ORIGINE:+ — $ENV_ORIGINE}"
if (( ${#MODULES_ECARTES[@]} > 0 )); then
    echo "  Tests propres à un autre environnement (${ECARTES_ENV}) non exécutés ici : ${MODULES_ECARTES[*]} — --all-environments pour tout exécuter"
fi

titre "0) Programmes présents dans $PROG_DIR"
# Installation incomplete (programmes absents) : le dire clairement ici, plutot que des sections vides et des dizaines
# de tests desactives un par un. Cas typique : nginx-tools.zip extrait (dossier nginx-tools/) sans l'etape de copie.
MANQUANTS=0
for attendu in nginx-hardening.sh nginx-log-audit.sh sync-crowdsec-blocklist.sh odoo-backup.sh odoo-update-module.sh app-health-check.py app-log-check.py \
               web-monitor.py zip-versions.py app-log-live.py odoo-mail-retry.py odoo-chat-post.py odoo-warmup.py host-perf-audit.py apps/_profile.sh apps/_profile.py apps/_rapport.sh apps/_rapport.py apps/_bbb.py \
               apps/_reseau.py apps/_odoo_db.py apps/_listes.py apps/_listes.sh apps/_cache_ip.py apps/_courriel.py apps/_email_check.py apps/_odoo_users.py apps/_sysperf.py apps/_i18n.py apps/_i18n.sh apps/_config.py apps/_traduire.py apps/config-entete.txt apps/odoo.conf apps/bbb.conf; do
    if [[ -f "$attendu" ]]; then
        [[ "$VERBOSE" == "1" ]] && ok "$attendu"
    else
        ko "$attendu absent"; MANQUANTS=$((MANQUANTS + 1))
    fi
done
if (( MANQUANTS == 0 )); then
    ok "tous les programmes et le dossier apps/ sont présents"
else
    if [[ -f nginx-tools/nginx-log-audit.sh ]]; then
        echo "      ${C_YELLOW}L'archive a été extraite dans $PROG_DIR/nginx-tools/ sans être copiée à sa place :${C_RESET}"
        echo "      cd $PROG_DIR && cp -r nginx-tools/* . && rm -rf nginx-tools"
    else
        echo "      ${C_YELLOW}Déployer l'archive : cd $PROG_DIR && unzip -o nginx-tools.<version>.zip && cp -r nginx-tools/* . && rm -rf nginx-tools${C_RESET}"
    fi
fi
# Ancienne copie de CETTE suite dans tests/ (avant la 1.56 : nom partagé avec les tests d'autres programmes, qui
# s'écrasaient mutuellement) : signalée avec la liste de nos fichiers qui s'y trouvent, jamais supprimée ici — le dossier
# peut contenir les tests d'autres programmes, parfois sous les mêmes noms (README.md, helpers.py…).
if [[ "$(basename "$TESTS_DIR")" != "tests" && -f tests/test_web_monitor.py && -f tests/run-all.sh ]]; then
    ancienne=$(sed -n 's/^readonly SCRIPT_VERSION="\(.*\)"/\1/p' tests/run-all.sh | head -1)
    communs=()
    for f in "$TESTS_DIR"/*; do
        if [[ "$(basename "$f")" != __pycache__ && -e "tests/$(basename "$f")" ]]; then communs+=("$(basename "$f")"); fi
    done
    echo "  ${C_YELLOW}[ATTN]${C_RESET}  ancienne copie de cette suite dans $PROG_DIR/tests/ (run-all.sh ${ancienne:-?}) : la suite est"
    echo "          maintenant dans $(basename "$TESTS_DIR")/ — à retirer de tests/ (${#communs[@]} nom(s) en commun : ${communs[*]:0:8}…)"
fi

# Fichiers RÉSIDUELS d'anciennes versions : une archive extraite par-dessus un ancien dossier n'en retire rien. Ces fichiers (listes d'adresses
# personnelles, générées sur chaque serveur) ne sont plus livrés ; leur présence fait échouer des tests (test_locks, test_multi_app, test_listes)
# pour une raison qui n'est pas un défaut du code. Signalé avec la commande exacte, jamais supprimé ici.
RESIDUELS=()
for f in "$PROG_DIR/apps/team-ips.list" "$TESTS_DIR/nginx-odoo/snippets/team-ips-geo.conf" "$TESTS_DIR/nginx-odoo/snippets/team-ips-allow.conf" \
         "$PROG_DIR/nginx-odoo/snippets/team-ips-geo.conf" "$PROG_DIR/nginx-odoo/snippets/team-ips-allow.conf"; do
    [[ -f "$f" ]] && RESIDUELS+=("$f")
done
# 1.182 : ancien catalogue lang/PROGRAMME.en.po d'un programme passé au code anglais (son lang/PROGRAMME.fr.po déclare Source-Language en) : cp -r ne
# l'efface pas, et il fausse les traductions (texte français dans l'affichage anglais) et test_i18n.
# Règle générale : un catalogue dans la langue SOURCE du programme (déclarée par l'en-tête Source-Language de son catalogue français) est résiduel.
for f in "$PROG_DIR"/lang/*.po; do
    lg=${f%.po}; lg=${lg##*.}; base=${f%."$lg".po}
    [[ -f "$f" && "$lg" != fr && -f "$base.fr.po" ]] && grep -q "^\"Source-Language: $lg" "$base.fr.po" && RESIDUELS+=("$f")
done
# 1.186 : la suite de tests ne modifie JAMAIS le dossier des programmes (elle ne faisait que proposer, mais c'était hors de son dossier) : les fichiers
# résiduels sont signalés, avec la commande pour les retirer, et les tests continuent (les anciens lang/PROG.en.po ne sont plus lus : apps/_i18n.py 1.15).
if (( ${#RESIDUELS[@]} > 0 )); then
    echo "  ${C_YELLOW}[ATTN]${C_RESET}  fichier(s) résiduel(s) d'une ancienne version (plus livrés, lus par aucun programme) :"
    printf '          %s\n' "${RESIDUELS[@]}"
    echo "          Ils peuvent être retirés sans risque : rm -f ${RESIDUELS[*]}"
    echo "          (un lang/PROG.en.po date de l'époque où PROG était écrit en français ; PROG est écrit en anglais et lit lang/PROG.fr.po ; aucun autre programme ne le lit)"
fi

titre "1) Syntaxe"
for f in "${BASH_PROGS[@]}"; do
    if out=$(bash -n "$f" 2>&1); then ok "bash -n $(basename "$f")"; else ko "bash -n $(basename "$f") : $out"; fi
done
for f in "${PY_PROGS[@]}"; do
    if out=$(python3 -m py_compile "$f" 2>&1); then ok "py_compile $(basename "$f")"; else ko "py_compile $(basename "$f") : $out"; fi
done

titre "2) ShellCheck"
if command -v shellcheck >/dev/null 2>&1; then
    for f in "${BASH_PROGS[@]}"; do
        out=$(shellcheck -f gcc "$f" 2>&1) || true
        if [[ -z "$out" ]]; then ok "shellcheck $(basename "$f") : 0 signalement"
        else ko "shellcheck $(basename "$f") : $(printf '%s\n' "$out" | grep -c .) signalement(s)"; printf '%s\n' "$out" | sed 's/^/      /'; fi
    done
else
    skip "ShellCheck non installé (relancer avec --install-missing, ou apt install shellcheck, ou exécutable statique dans nginx-tools-tests/tools/)"
fi

titre "3) ruff (analyse du Python)"
if command -v ruff >/dev/null 2>&1; then
    # E9/F : erreurs de syntaxe et defauts reels (noms indefinis, imports ou variables inutilises...) — pas le style.
    if out=$(ruff check --select E9,F --target-version py38 --no-cache --output-format concise "${PY_PROGS[@]}" "$TESTS_DIR"/*.py 2>&1); then ok "ruff : aucun défaut"
    else ko "ruff : défauts trouvés"; printf '%s\n' "$out" | sed 's/^/      /'; fi
else
    skip "ruff non installé (relancer avec --install-missing, ou pipx install ruff, ou exécutable statique dans nginx-tools-tests/tools/)"
fi

titre "4) Suite de tests (une fois par awk disponible) — ${#MODULES[@]} module(s) : commun${ENV_APP:+ + $ENV_APP}"
TMP_AVANT=$(find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'test-rlq-*' 2>/dev/null | sort) || true
# Sentinelle : la suite ne doit JAMAIS créer ni modifier un fichier de configuration RÉEL (/etc/default, ~). Empreinte avant/après :
# sur un serveur ces fichiers existent légitimement — seul un changement PENDANT la suite est une faute.
# Legacy personal names (rule before 1.191: personal files ended with .cfg; the programs rename them .conf): a test must never rename a real one.
ANCIENS_NOMS=("${HOME:-/root}/.app-health-check.cfg" "${HOME:-/root}/.odoo-backup.cfg" "${HOME:-/root}/.app-default.cfg")    # legacy names
empreinte_configs() {
    local f
    for f in /etc/default/app-health-check.conf /etc/default/odoo-backup.conf /etc/default/nginx-hardening.conf \
             /etc/default/sanity-check-odoo.conf "${HOME:-/root}/.app-health-check.conf" "${HOME:-/root}/.odoo-backup.conf" \
             ${ANCIENS_NOMS[@]+"${ANCIENS_NOMS[@]}"} \
             /var/lib/nginx-tools/bbb-state.json /var/lib/nginx-tools/bbb-state.json.before \
             /etc/default/nginx-tools-mail.conf /etc/default/nginx-tools-mail.pass /etc/msmtprc \
             /etc/default/nginx-tools-white-list.conf /etc/default/nginx-tools-ip-location.conf /var/lib/nginx-tools/ip-cache.sqlite \
             /var/lib/nginx-tools/odoo-users.tsv; do
        # 1.190 : fichier illisible sans root (droits 600) : taille et date de modification (stat), qui changent aussi si un test l'écrit
        if [[ -r "$f" ]]; then sha256sum "$f"; elif [[ -e "$f" ]]; then echo "illisible $(stat -c '%s %Y' "$f" 2>/dev/null)  $f"; else echo "absent  $f"; fi
    done
}
CONFIGS_AVANT=$(empreinte_configs)
MARQUE_SYSTEME=$(mktemp)                                         # 1.190 : tout fichier de /etc ou /var/backups modifié APRÈS ce point est examiné à la fin
AWKS=()
for a in mawk gawk original-awk; do command -v "$a" >/dev/null 2>&1 && AWKS+=("$(command -v "$a")"); done
BB_WRAP=""
if command -v busybox >/dev/null 2>&1 && busybox awk 'BEGIN{}' 2>/dev/null; then
    BB_WRAP="$(mktemp -d)/awk-busybox"; printf '#!/bin/sh\nexec busybox awk "$@"\n' > "$BB_WRAP"; chmod +x "$BB_WRAP"; AWKS+=("$BB_WRAP")
fi
[[ ${#AWKS[@]} -eq 0 ]] && AWKS+=("$(command -v awk)")
STATS_DIR=$(mktemp -d); STATS_FICHIERS=()                    # 1.188 : statistiques de chaque passe (stats_runner.py), affichées à la fin
LANCEUR=(python3 -W ignore -m unittest)                         # repli sans stats_runner.py (ancienne suite) : mêmes tests, sans statistiques
for a in "${AWKS[@]}"; do
    rc=0
    nom=$(basename "$a"); nom=${nom#awk-}
    if [[ -r "$TESTS_DIR/stats_runner.py" ]]; then
        STATS_FICHIERS+=("$STATS_DIR/passe-${#STATS_FICHIERS[@]}-$nom.json")
        LANCEUR=(python3 -W ignore "$TESTS_DIR/stats_runner.py" --run "${STATS_FICHIERS[-1]}")
    fi
    # La passe tourne dans SA PROPRE session (setsid) : le Ctrl+C du terminal ne l'atteint pas, la confirmation de run-all décide (non -> la passe continue, sans test faussé).
    sortie_passe=$(mktemp)
    (cd "$TESTS_DIR" && TEST_AWK="$a" TEST_SCRIPTS_DIR="$PROG_DIR" exec setsid "${LANCEUR[@]}" "${MODULES[@]}" -v >"$sortie_passe" 2>&1) &
    JOB_PID=$!
    while :; do
        wait "$JOB_PID" && rc=0 || rc=$?
        kill -0 "$JOB_PID" 2>/dev/null || break              # « wait » interrompu par la question de Ctrl+C : la passe tourne encore, on l'attend de nouveau
    done
    JOB_PID=""
    res=$(cat "$sortie_passe"); rm -f "$sortie_passe"
    bilan=$(printf '%s\n' "$res" | grep -E '^(Ran|OK|FAILED)' | tr '\n' ' ')
    if [[ $rc -eq 0 ]]; then ok "tests sous $nom : $bilan"; printf '%s\n' "$res" | detail
    else
        # Chaque test en échec est relancé SEUL : échec confirmé (bloquant), ou test INSTABLE — il ne réussit que seul
        # (dépendance à l'ordre ou au moment) : signalé, avec son message complet conservé dans last-instable.log.
        confirmes=(); instables=()
        while IFS= read -r id; do
            [[ -z "$id" ]] && continue
            if (cd "$TESTS_DIR" && TEST_AWK="$a" TEST_SCRIPTS_DIR="$PROG_DIR" python3 -W ignore -m unittest "$id" >/dev/null 2>&1); then
                instables+=("$id")
            else
                confirmes+=("$id")
            fi
        done < <(printf '%s\n' "$res" | sed -nE 's/^(FAIL|ERROR): ([A-Za-z0-9_]+) \(([A-Za-z0-9_.]+)\).*/\2 \3/p' \
                 | awk '{ id = $2; if (id !~ ("\\." $1 "$")) id = id "." $1; print id }' | sort -u)
        if (( ${#confirmes[@]} > 0 || ${#instables[@]} == 0 )); then
            ko "tests sous $nom : $bilan"
            # 1.190 : sed lit TOUTE l'entrée (pas de « head ») : sinon grep reçoit SIGPIPE et « set -o pipefail » + le piège ERR arrêtaient run-all.sh
            printf '%s\n' "$res" | grep -E '^(FAIL|ERROR):|AssertionError|Error:' | sed -n '1,40s/^/      /p'
        else
            ok "tests sous $nom : tous réussis une fois relancés seuls"
        fi
        if (( ${#instables[@]} > 0 )); then
            {
                echo "=== $(date '+%Y-%m-%d %H:%M:%S') — run-all.sh v$SCRIPT_VERSION — awk : $nom — $(hostname)"
                for id in "${instables[@]}"; do
                    printf '%s\n' "$res" | awk -v t="${id##*.}" '/^(FAIL|ERROR): / { garde = index($0, t) > 0 } /^-{10,}$/ && garde && vu++ { garde = 0 } garde'
                done
            } >> "$TESTS_DIR/last-instable.log"
            for id in "${instables[@]}"; do
                echo "  ${C_YELLOW}[INSTABLE]${C_RESET} $id : a échoué dans la suite, réussi seul — détail : $TESTS_DIR/last-instable.log"
            done
        fi
    fi
    # Tests desactives : la RAISON reelle, donnee par chaque test (-v : « ... skipped 'raison' »), une fois par raison.
    if [[ "$a" == "${AWKS[0]}" ]]; then
        while IFS= read -r ligne; do
            [[ -z "$ligne" ]] && continue
            skip "$ligne"
        done < <(printf '%s\n' "$res" | grep -oE "skipped '[^']*'" | sed -E "s/^skipped '(.*)'$/\1/" | sort | uniq -c \
                 | sed -E 's/^ *([0-9]+) (.*)$/\1 test(s) désactivé(s) : \2/')
    fi
done
[[ -n "$BB_WRAP" ]] && rm -rf "$(dirname "$BB_WRAP")"
# Filet de securite : repertoires temporaires des tests restes dans /tmp (test interrompu, processus tue...). Seuls
# ceux CREES PENDANT CE PASSAGE sont supprimes — jamais ceux d'un autre passage en cours ou d'un autre utilisateur.
TMP_APRES=$(find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'test-rlq-*' 2>/dev/null | sort) || true
RESTES=$(comm -13 <(printf '%s\n' "$TMP_AVANT") <(printf '%s\n' "$TMP_APRES") | grep . || true)
CONFIGS_APRES=$(empreinte_configs)
# 1.190 : fichiers SYSTÈME modifiés pendant la suite. Un test ne doit JAMAIS écrire hors de son dossier : un fichier qui nomme un dossier de test
# (/tmp/test-rlq-…) vient d'un test = échec ; les autres (un service de la machine a pu écrire pendant ce temps) = pour information.
ECRITS_PAR_TESTS=(); ECRITS_AUTRES=()
while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    if grep -qs 'test-rlq-' "$f"; then ECRITS_PAR_TESTS+=("$f"); else ECRITS_AUTRES+=("$f"); fi
done < <(find /etc /var/backups -xdev -type f -newer "$MARQUE_SYSTEME" 2>/dev/null | sort)
rm -f "$MARQUE_SYSTEME"
if (( ${#ECRITS_PAR_TESTS[@]} > 0 )); then
    ko "la suite de tests a ÉCRIT ${#ECRITS_PAR_TESTS[@]} fichier(s) du système (ils nomment un dossier de test) — à supprimer :"
    printf '      %s\n' "${ECRITS_PAR_TESTS[@]}"
fi
if (( ${#ECRITS_AUTRES[@]} > 0 )); then
    echo "  [INFO]  ${#ECRITS_AUTRES[@]} fichier(s) de /etc ou /var/backups modifié(s) pendant la suite, sans lien avec un test (un service de la machine) : ${ECRITS_AUTRES[*]:0:5}"
fi
if [[ "$CONFIGS_AVANT" != "$CONFIGS_APRES" ]]; then
    ko "la suite de tests a MODIFIÉ un fichier de configuration réel (elle doit tout rediriger vers un dossier temporaire) :"
    diff <(printf '%s\n' "$CONFIGS_AVANT") <(printf '%s\n' "$CONFIGS_APRES") | grep '^[<>]' | sed 's/^/      /' || true
    echo "      Cause la plus probable : un programme réel (ex. nginx-hardening.sh --update) lancé PENDANT la suite, dans un autre terminal. Aucun test n'écrit ces fichiers (vérifié avec strace) : relancer la suite sans rien d'autre."
fi
if [[ -n "$RESTES" ]]; then
    n_restes=$(printf '%s\n' "$RESTES" | grep -c .)
    while IFS= read -r r; do rm -rf "${r:?}"; done <<< "$RESTES"
    echo "  ${C_YELLOW}[NETTOYÉ]${C_RESET} $n_restes répertoire(s) temporaire(s) de test laissé(s) dans /tmp — supprimé(s)"
fi
for requis in mawk gawk; do
    command -v "$requis" >/dev/null 2>&1 || skip "$requis absent : les différences d'interprétation awk ne sont pas couvertes (apt install $requis)"
done

titre "5) Configuration déployée comparée à la version testée (nginx-tools-tests/nginx-odoo/)"
# Derive de deploiement : fichiers de /etc/nginx et /etc/fail2ban differents de la configuration testee. Signale
# seulement (une difference peut etre voulue, ex. liste d'IP de l'equipe) : n'entre pas dans le verdict.
REF="${NGINX_ODOO_DIR:-$TESTS_DIR/nginx-odoo}"                   # 1.188 : configuration privée, hors du dépôt Git (copie locale)
if [[ -n "$ENV_APP" && "$ENV_APP" != "odoo" ]]; then
    echo "  [INFO]  sans objet pour $ENV_LABEL : cette configuration nginx est celle des serveurs Odoo"
elif [[ ! -d /etc/nginx ]]; then
    echo "  [INFO]  pas de /etc/nginx sur cette machine — comparaison sans objet"
elif [[ ! -d "$REF" ]]; then
    echo "  [INFO]  $REF absent — comparaison impossible"
else
    n_id=0; n_abs=0; n_diff=0
    while IFS='|' read -r src dst; do
        [[ -f "$src" ]] || continue
        if [[ ! -e "$dst" ]]; then n_abs=$((n_abs + 1)); continue; fi
        if cmp -s "$src" "$dst"; then n_id=$((n_id + 1))
        else n_diff=$((n_diff + 1)); echo "  ${C_YELLOW}[ATTN]${C_RESET}  différent de la version testée : $dst"; fi
    done < <(
        cd "$REF" && find conf.d snippets sites-available -type f -name '*.conf' 2>/dev/null | sed "s#.*#$REF/&|/etc/nginx/&#"
        for f in "$REF"/fail2ban/*.filter.conf; do [[ -f "$f" ]] && echo "$f|/etc/fail2ban/filter.d/$(basename "$f" .filter.conf).conf"; done
        [[ -f "$REF/fail2ban/nginx-catchall.jail.conf" ]] && echo "$REF/fail2ban/nginx-catchall.jail.conf|/etc/fail2ban/jail.d/nginx-catchall.conf"
        [[ -f "$REF/maintenance/index.html" ]] && echo "$REF/maintenance/index.html|/var/www/maintenance/index.html"
    )
    echo "  [INFO]  $n_id fichier(s) identique(s), $n_diff différent(s), $n_abs absent(s) de ce serveur (normal pour ceux d'un autre environnement)"
    (( n_diff > 0 )) && echo "          Voir une différence : diff <fichier testé> <fichier déployé> ; déployer : voir nginx-tools-tests/nginx-odoo/README.md"
fi

titre "6) Contrôles du serveur réel, en lecture seule (${ENV_LABEL:-environnement non reconnu})"
# Contrôles PROPRES à l'environnement, faits sur CE serveur (les étapes 1 à 4 testent le code avec des commandes simulées).
# Pour information : l'état d'un serveur n'est pas un défaut du code, donc rien ici n'entre dans le verdict.
controle_reel() {          # controle_reel LIBELLÉ COMMANDE… : lignes [OK]/[ATTN]/[FAIL] de la sortie, en un résumé
    local libelle="$1" sortie n_fail n_attn; shift
    sortie=$(timeout --foreground 300 "$@" 2>&1) || true
    n_fail=$(printf '%s\n' "$sortie" | grep -cE '^\s*(\x1b\[[0-9;]*m)?\[(FAIL|ÉCHEC)\]' || true)
    n_attn=$(printf '%s\n' "$sortie" | grep -cE '^\s*(\x1b\[[0-9;]*m)?\[ATTN\]' || true)
    echo "  [INFO]  $libelle : $n_fail échec(s), $n_attn avertissement(s) sur ce serveur"
    printf '%s\n' "$sortie" | grep -E '^\s*(\x1b\[[0-9;]*m)?\[(FAIL|ÉCHEC|ATTN)\]' | sed -n '1,8s/^/          /p'
}
case "$ENV_APP" in
    bbb)
        if [[ -r apps/_bbb.py ]]; then
            controle_reel "BigBlueButton : versions, nos règles chargées, API, client HTML5, HSTS (apps/_bbb.py --summary)" \
                python3 apps/_bbb.py --summary
        else
            echo "  [INFO]  apps/_bbb.py absent : contrôles de BigBlueButton impossibles"
        fi ;;
    odoo)
        if [[ -r app-health-check.py ]]; then
            controle_reel "Odoo : nginx et application (app-health-check.py --target local)" \
                python3 app-health-check.py --target local --app odoo
        else
            echo "  [INFO]  app-health-check.py absent : contrôles d'Odoo impossibles"
        fi ;;
    *) echo "  [INFO]  environnement non reconnu : aucun contrôle de serveur réel (--app NOM pour en choisir un)" ;;
esac

# 1.188 : statistiques (durée, ressources, nombre de tests par programme et par nature) — le tableau est écrit DANS la langue d'affichage par
# stats_runner.py (largeurs calculées après traduction : colonnes alignées en français comme en anglais)
if (( ${#STATS_FICHIERS[@]} > 0 )); then
    python3 "$TESTS_DIR/stats_runner.py" --total "$(( $(date +%s) - RUN_ALL_DEBUT ))" --report "${STATS_FICHIERS[@]}" || true
fi
[[ -n "${STATS_DIR:-}" ]] && rm -rf "$STATS_DIR"
echo
echo "=============================================================="
if (( ECHECS > 0 )); then
    echo "${C_RED} VERDICT : $ECHECS ÉCHEC(S) — ne pas déployer.${C_RESET}"
elif (( ${#NON_VERIFIE[@]} > 0 )); then
    echo "${C_YELLOW} VERDICT : tout ce qui a été exécuté réussit — mais ${#NON_VERIFIE[@]} point(s) NON vérifié(s) (voir [IGNORÉ]).${C_RESET}"
else
    echo "${C_GREEN} VERDICT : TOUT PASSE — validation complète.${C_RESET}"
fi
echo "=============================================================="
# « exit » explicite : un « (( ECHECS == 0 )) » final faux declenchait le piege ERR (faux « ARRET INATTENDU »).
if (( ECHECS > 0 )); then exit 1; fi
exit 0
