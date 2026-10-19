# odoo-mail-retry.py — lister et renvoyer les courriels en échec

Lit PostgreSQL (root) et liste les courriels d'Odoo à l'état **exception** (« Échec d'envoi ») : sujet, date, destinataires (masqués sauf avec `--details`) et une cause classée *transitoire* ou *PERMANENTE*. Un menu propose ensuite : `t` tous, `l` un lot des N plus anciens (`--batch`), `c` choisir, `N` aucun.

```bash
odoo-mail-retry.py --db mabase --days 30
odoo-mail-retry.py --resend --yes --batch 10     # sans interaction, les 10 plus anciens
odoo-mail-retry.py --sent 20                     # les 20 derniers courriels ENVOYÉS
```

* « Renvoyer » remet seulement l'état à *Sortant* (comme le bouton « Réessayer ») ; l'action planifiée d'Odoo les envoie.
* C'est le **seul programme de la suite qui écrit dans la base d'Odoo**, protégé par `state = 'exception'`, avec confirmation, et chaque action est consignée dans `/var/lib/nginx-tools/mail-retry.log`. Une écriture directe en SQL ne vide pas le cache des paramètres d'Odoo : ne pas s'en servir pour changer des réglages.
* Note de schéma : `mail.mail` hérite de `mail.message` (`_inherits`), donc le **sujet** est dans `mail_message.subject`.
* Ne renvoie jamais sans terminal, sauf `--resend --yes`.

## Adresses invalides des inscriptions

Avant les courriels en échec, le programme liste les inscriptions aux événements dont l'adresse courriel est invalide ou mal écrite, avec la correction suggérée (`marie@hotmail'com` → `marie@hotmail.com`, `hotmial.com` → `hotmail.com`). Le menu les corrige toutes (`a`) ou une par une (`c` : Entrée accepte la suggestion, ou saisir une autre adresse, `s` passe) ; `--invalid-emails` ne montre qu'elles, `--fix --yes` applique les suggestions sans question. Une correction modifie, en une transaction, l'inscription, son contact (seulement s'il a la même adresse erronée) et les courriels en échec de cette inscription, qui repassent « En attente ». L'identifiant d'un compte Odoo n'est jamais modifié. Un courriel en échec adressé à une adresse invalide est affiché avec cette cause : renvoyé tel quel, il échouerait de nouveau.

## Options
{{HELP}}
