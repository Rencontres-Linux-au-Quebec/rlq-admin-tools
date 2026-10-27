# Configuration nginx generique (dossier nginx/)

Fichiers generiques pour un serveur nginx qui sert Odoo ou BigBlueButton. Ils ne contiennent aucun nom de domaine,
aucune adresse IP de l'organisation : ce qui est propre a un site vit dans un fichier separe, fourni par l'administrateur.

- conf.d/bot_blocker.conf : User-Agent de robots, scanners et clients indesirables (map $is_bad_bot).
- conf.d/odoo-global.conf : zones de limitation de debit (limit_req), limite de connexions, carte des instances non publiques.
- snippets/securite-commune.conf : regles de refus communes (bots, methodes, fichiers sensibles, curl en rafale).
- snippets/odoo/_odoo-common.conf : blocs location d'Odoo (proxy, limites, icone d'accueil, robots.txt).
- snippets/odoo/hsts.conf : en-tete HSTS.
- fail2ban/ : filtres et jails (nginx-catchall, nginx-blocked-probes, odoo-auth).

Ces fichiers sont installes par nginx-hardening.sh --update. Un fichier modifie a la main sur le serveur est sauvegarde
avant d'etre remplace, et l'installation demande confirmation. Un fichier absent est cree apres confirmation.
Version : voir le fichier VERSION de ce dossier.

Fichiers propres au site (domaines, vhosts, environnements) : voir le zip de configuration du site (rlq-nginx-config.NN.zip).
