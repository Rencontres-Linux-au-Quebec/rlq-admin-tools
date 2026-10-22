# odoo-chat-post.py - canaux d'alerte Discuss et robot restreint

Crée, par l'API externe d'Odoo (XML-RPC avec une clé d'API - aucun accès à PostgreSQL), les **canaux et fils** d'alertes de l'équipe dans Discuss, chacun avec un premier message qui explique son rôle, et y publie des alertes. Le catalogue est un fichier JSON (`doc/odoo-chat-post.catalogue.json`) : sécurité, courriels, sauvegardes, mises à jour, jour d'événement, plus un jeu de fils par événement (`--event JPOL26` -> `JPOL26-Inscriptions`, `JPOL26-Sondages`).

```bash
odoo-chat-post.py --list                                         # catalogue : présent ou absent
odoo-chat-post.py --create --dry-run --suggested                 # aperçu
odoo-chat-post.py --create --members vous@example.org,tux-bot    # RESTREINT : seuls ces comptes voient/sont membres
odoo-chat-post.py --post "Odoo-Erreurs/HTTP 5xx" --message "Rafale de 5xx à 14 h 02"
echo "texte" | odoo-chat-post.py --post "Odoo-Erreurs/HTTP 5xx" --message -
```

* `--create` ne crée que ce qui manque ; il ne modifie jamais un canal existant.
* Accès : par défaut le groupe `base.group_user` (tous les utilisateurs internes) ; `--members` le restreint aux identifiants listés et **crée un groupe restreint** « Alertes équipe (odoo-chat-post) ».

## Le compte robot

`--create-bot` crée un utilisateur interne **sans aucun droit autre que d'écrire dans ces canaux**. Au premier lancement il crée aussi sa clé d'API (un an si Odoo le permet, sinon 7 jours) et écrit `LOGIN` / `API_KEY` dans `/etc/default/odoo-chat-post.conf` (droits 600, version précédente sauvegardée ; répéter `--bot-config` pour les fichiers d'autres programmes). `--renew-key` émet une nouvelle clé (l'ancienne reste valide jusqu'à son expiration). Odoo ne permet pas de créer une clé d'API par l'API externe : le programme ouvre donc une session web et rejoue l'assistant « Clé d'API » - si votre version d'Odoo diffère, créez la clé à la main dans *Préférences -> Sécurité du compte* et placez-la dans le fichier.

## Options
{{HELP}}
