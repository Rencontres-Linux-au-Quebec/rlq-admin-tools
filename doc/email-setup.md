# Courriel des alertes — configuration et DNS

> Configuration **complète et sécurisée** (Postfix en envoi seulement, TLS obligatoire, SPF, DKIM, DMARC, TLS-RPT, MTA-STS) avec fichiers prêts à copier : voir `courriel-securise.md` et `courriel/`.

Les outils (`web-monitor.py`, `app-health-check.py`) envoient leurs alertes par **SMTP**. Ce guide explique comment
configurer l'envoi, quels enregistrements ajouter au DNS du domaine, et comment tout vérifier.

## 1. Choisir comment envoyer

| Solution | Pour qui | Délivrabilité |
|---|---|---|
| **Relais SMTP d'un fournisseur** (recommandé) : le fournisseur qui héberge déjà le courriel du domaine, ou un service d'envoi (Brevo, Mailjet, Amazon SES…) | tous les serveurs | excellente : le fournisseur gère la réputation et DKIM |
| **Compte Gmail / Google Workspace** avec un mot de passe d'application | dépannage | bonne, mais l'expéditeur doit être ce compte |
| **Postfix envoyant directement** (sans relais) | déconseillé | faible : port 25 souvent bloqué par l'hébergeur, adresse IP de serveur mal réputée, PTR à obtenir |

Recommandation : **un relais SMTP authentifié**, sur le port 587 (STARTTLS) ou 465 (SSL).

## 2. Configurer les outils

Dans `/etc/default/app-health-check.conf` (créé au premier lancement ou par `app-health-check.py --create-config`, droits 600 ;
un `~/.app-health-check.cfg` éventuel est lu ensuite et l'emporte, et le programme affiche toujours les fichiers lus) :

```
SMTP_HOST=smtp.fournisseur.exemple      # serveur du relais
SMTP_PORT=587                           # 587 (STARTTLS) ou 465 (SSL)
SMTP_SECURITY=                          # vide : déduit du port (starttls, ssl) ; none : relais local sans TLS
SMTP_USER=alertes@rencontres-linux.quebec
SMTP_PASSWORD=...                       # mot de passe d'application, jamais le mot de passe principal
NOTIFY_EMAIL_FROM=alertes@rencontres-linux.quebec   # adresse de VOTRE domaine, autorisée par le relais
NOTIFY_EMAIL_TO=info@rencontres-linux.quebec        # une ou plusieurs adresses, séparées par des virgules
DKIM_SELECTOR=                          # sélecteur DKIM indiqué par le relais (ex. « s1 », « mail »)
```

## 3. Enregistrements DNS à ajouter (chez le fournisseur du domaine)

Remplacer `rencontres-linux.quebec` par le domaine de `NOTIFY_EMAIL_FROM`.

| Enregistrement | Nom | Valeur | Rôle |
|---|---|---|---|
| **MX** | `rencontres-linux.quebec.` | `10 <serveur de réception de votre fournisseur>.` | le domaine peut recevoir (réponses, retours) ; beaucoup de serveurs refusent un expéditeur sans MX |
| **SPF** (TXT) | `rencontres-linux.quebec.` | `v=spf1 include:<domaine SPF du relais> -all` | liste les serveurs autorisés à envoyer pour le domaine. **Un seul** enregistrement SPF : fusionner les `include:` s'il en faut plusieurs |
| **DKIM** (TXT ou CNAME) | `<sélecteur>._domainkey.rencontres-linux.quebec.` | fourni par le relais | signature cryptographique de chaque courriel |
| **DMARC** (TXT) | `_dmarc.rencontres-linux.quebec.` | `v=DMARC1; p=none; rua=mailto:postmaster@rencontres-linux.quebec; fo=1` | politique en cas d'échec de SPF/DKIM, et rapports |

DMARC en trois temps : `p=none` (observer les rapports quelques semaines), puis `p=quarantine`, puis `p=reject`.

**PTR** (DNS inverse de l'adresse IP) : seulement si le serveur envoie **directement** sans relais ; il se demande à
l'hébergeur, et doit correspondre au nom du serveur.

## 4. Vérifier

```bash
app-health-check.py --check-email-dns    # relais joignable, MX, SPF, DMARC, DKIM — enregistrements manquants indiqués
app-health-check.py --test-email         # la même vérification, puis l'envoi réel d'un courriel de test
nginx-hardening.sh --check               # étape 13 : la même vérification, à chaque contrôle du serveur
```

Le courriel de test doit arriver **dans la boîte de réception**, pas dans les pourriels. Dans Gmail, « Afficher
l'original » doit indiquer `SPF: PASS`, `DKIM: PASS` et `DMARC: PASS`.

Les changements DNS peuvent prendre jusqu'à la durée de vie (TTL) des anciens enregistrements pour être visibles.

## 5. Variante : Postfix comme relais local

Utile pour que les courriels du système (cron, unattended-upgrades) partent aussi par le relais :

```bash
apt install postfix libsasl2-modules          # choisir « Satellite system », relais : [smtp.fournisseur.exemple]:587
postconf -e 'smtp_sasl_auth_enable = yes' 'smtp_sasl_password_maps = hash:/etc/postfix/sasl_passwd' \
            'smtp_sasl_security_options = noanonymous' 'smtp_tls_security_level = encrypt'
echo '[smtp.fournisseur.exemple]:587 utilisateur:motdepasse' > /etc/postfix/sasl_passwd
chmod 600 /etc/postfix/sasl_passwd && postmap /etc/postfix/sasl_passwd && systemctl restart postfix
```

Puis, dans la configuration des outils : `SMTP_HOST=127.0.0.1`, `SMTP_PORT=25`, `SMTP_SECURITY=none`, `SMTP_USER=`
vide (Postfix s'identifie lui-même auprès du relais).
