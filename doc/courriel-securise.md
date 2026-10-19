# Envoyer des courriels de façon sécuritaire (Postfix, SPF, DKIM, DMARC, TLS)

Ce guide complète `email-setup.md` (relais SMTP, vérifications des outils). Il fournit des **fichiers de configuration prêts à
copier** dans `doc/courriel/` pour un serveur Linux (Debian / Ubuntu) qui envoie du courriel : Odoo, cron, `web-monitor.py`,
`app-health-check.py`. Exemples avec le domaine `rencontres-linux.quebec` et le serveur `mail.rencontres-linux.quebec` : à remplacer.

## 1. Choisir le mode

| Mode | Principe | Quand |
|---|---|---|
| **A. Relais authentifié** (recommandé) | Postfix local → relais SMTP du fournisseur (587, TLS, mot de passe) | le plus simple, bonne délivrabilité, le relais gère la réputation et souvent le DKIM |
| **B. Envoi direct** | Postfix local → serveurs des destinataires, signature DKIM par OpenDKIM | port 25 sortant ouvert, adresse IP « propre », PTR obtenu de l'hébergeur ; plus d'entretien |

Dans les deux modes Postfix **n'écoute que sur 127.0.0.1** (`inet_interfaces = loopback-only`) : aucun port 25 exposé, aucun
relais ouvert possible. Odoo et les outils envoient à `127.0.0.1:25`, sans mot de passe (accès local seulement).

## 2. Installer et configurer Postfix

```bash
apt install postfix libsasl2-modules mailutils      # « Site Internet » ou « Satellite system » ; le nom du système : mail.rencontres-linux.quebec
hostnamectl set-hostname mail.rencontres-linux.quebec    # le nom doit être celui du PTR (mode B)
cp /etc/postfix/main.cf /etc/postfix/main.cf.origine
cp doc/courriel/main.cf.relais /etc/postfix/main.cf       # mode A   (mode B : doc/courriel/main.cf.direct)
```

**Mode A** — identifiants du relais (droits stricts) :

```bash
install -m 600 /dev/null /etc/postfix/sasl_passwd
echo '[smtp.fournisseur.exemple]:587 utilisateur:mot-de-passe-d-application' > /etc/postfix/sasl_passwd
postmap /etc/postfix/sasl_passwd && chmod 600 /etc/postfix/sasl_passwd /etc/postfix/sasl_passwd.db
postfix check && systemctl restart postfix
```

**Mode B** — certificat (facultatif pour l'envoi, utile si un correspondant l'exige) et OpenDKIM :

```bash
apt install opendkim opendkim-tools
install -d -o opendkim -g opendkim -m 750 /etc/opendkim/keys/rencontres-linux.quebec
opendkim-genkey -b 2048 -d rencontres-linux.quebec -s 2026a -D /etc/opendkim/keys/rencontres-linux.quebec
chown opendkim:opendkim /etc/opendkim/keys/rencontres-linux.quebec/2026a.private && chmod 600 /etc/opendkim/keys/rencontres-linux.quebec/2026a.private
cp doc/courriel/opendkim.conf /etc/opendkim.conf
cat /etc/opendkim/keys/rencontres-linux.quebec/2026a.txt        # la valeur à publier au DNS (section 3)
systemctl enable --now opendkim && postfix check && systemctl restart postfix
```

## 3. DNS (chez le fournisseur du domaine) — modèle : `doc/courriel/dns-zone.txt`

| Enregistrement | Nom | Rôle |
|---|---|---|
| **SPF** (TXT) | `rencontres-linux.quebec.` | serveurs autorisés à envoyer ; **un seul** par nom, terminé par `-all` |
| **DKIM** (TXT) | `2026a._domainkey.rencontres-linux.quebec.` | clé publique qui vérifie la signature (mode B : `2026a.txt`) |
| **DMARC** (TXT) | `_dmarc.rencontres-linux.quebec.` | politique si SPF et DKIM échouent + rapports agrégés (`rua`) |
| **TLS-RPT** (TXT) | `_smtp._tls.rencontres-linux.quebec.` | rapports d'échecs de TLS |
| **PTR** | adresse IP du serveur | mode B : à demander à l'**hébergeur** ; doit donner `mail.rencontres-linux.quebec`, qui doit retourner la même IP |
| **CAA** | `rencontres-linux.quebec.` | seule l'autorité voulue peut émettre des certificats |
| **MTA-STS** | `_mta-sts` + page HTTPS | seulement si le domaine **reçoit** du courrier (section 6) |

**Déploiement progressif de DMARC** : `p=none` (observer les rapports 2 à 4 semaines, corriger les expéditeurs oubliés : Odoo, formulaires,
infolettres) → `p=quarantine` → `p=reject`. `adkim=s; aspf=s` (alignement strict) convient quand tous les envois utilisent
exactement `@rencontres-linux.quebec` ; passer à `r` (relaxé) si un service tiers envoie avec un sous-domaine.
La boîte `dmarc@` (rua) doit exister ; les rapports sont des fichiers XML compressés envoyés par Google, Microsoft, etc.

**Rotation DKIM** (tous les 6 à 12 mois) : générer `2026b`, publier `2026b._domainkey`, attendre la propagation, changer `Selector` et
`KeyFile` dans `opendkim.conf`, redémarrer, puis retirer `2026a` après 2 semaines.

## 4. Odoo et les outils

- **Odoo** (Paramètres ▸ Technique ▸ Serveurs de courriel sortant) : serveur `127.0.0.1`, port `25`, sécurité **Aucune** (boucle locale),
  « Filtre De » = `rencontres-linux.quebec`. Paramètres système : `mail.catchall.domain` = `rencontres-linux.quebec`, `mail.default.from` =
  `notifications` (adresse expéditrice du domaine, jamais celle d'un utilisateur : SPF et DMARC doivent s'aligner). `mail.session.batch.size`
  à 10 évite l'erreur 452 des relais qui limitent les messages par connexion.
- **Outils** (`/etc/default/app-health-check.conf`) : `SMTP_HOST=127.0.0.1`, `SMTP_PORT=25`, `SMTP_SECURITY=none`, `SMTP_USER=` vide,
  `NOTIFY_EMAIL_FROM=alertes@rencontres-linux.quebec`, `DKIM_SELECTOR=2026a` (ou celui du relais).

## 5. Vérifier

```bash
postfix check && postconf -n | grep -E 'inet_interfaces|relayhost|smtp_tls|milter'     # écoute locale, TLS, relais
ss -ltnp | grep ':25 '                                       # doit montrer 127.0.0.1:25 SEULEMENT
opendkim-testkey -d rencontres-linux.quebec -s 2026a -vvv    # mode B : « key OK »
dig +short TXT rencontres-linux.quebec _dmarc.rencontres-linux.quebec 2026a._domainkey.rencontres-linux.quebec
dig +short -x 203.0.113.10                                   # PTR (mode B)
echo "essai" | mail -s "essai $(date +%H:%M)" -r alertes@rencontres-linux.quebec vous@exemple.org
journalctl -u postfix -n 30 --no-pager                       # « status=sent », « TLS connection established »
app-health-check.py --check-email-dns                        # MX, SPF, DMARC, DKIM, relais (outils de ce projet)
```

Dans Gmail, « Afficher l'original » doit indiquer `SPF: PASS`, `DKIM: PASS`, `DMARC: PASS` ; la ligne « Received » doit montrer
« using TLS » (`TLSv1.3`). Un test plus complet : envoyer à l'adresse fournie par mail-tester.com ou à `check-auth@verifier.port25.com`.

## 6. Pour aller plus loin

- **MTA-STS** (domaine qui reçoit du courrier) : TXT `_mta-sts` = `v=STSv1; id=AAAAMMJJ…` (changer l'`id` à chaque modification de la
  politique) et le fichier `https://mta-sts.rencontres-linux.quebec/.well-known/mta-sts.txt` :
  ```
  version: STSv1
  mode: testing
  mx: mx1.fournisseur.exemple
  max_age: 86400
  ```
  Passer à `mode: enforce` et `max_age: 604800` après quelques semaines sans rapport TLS-RPT d'échec.
- **DANE** (DNSSEC requis) : un résolveur local (`unbound`) et `smtp_tls_security_level = dane` (lignes commentées de `main.cf.direct`).
- **Pare-feu** : aucun port entrant pour le courrier ; sortant : 587 (mode A) ou 25 (mode B). `ufw` : `ufw allow out 587/tcp`.
- **Surveillance** : `postqueue -p` (file d'attente), `mailq | tail -1`, et `app-log-check.py` pour les échecs d'envoi d'Odoo
  (`odoo-mail-retry.py` les liste et les renvoie ; `--sent 10` montre les derniers envoyés).
- **Réputation** : s'inscrire à Google Postmaster Tools et Microsoft SNDS avec le domaine ; vérifier que l'adresse IP n'est pas sur une liste
  de blocage (mxtoolbox.com/blacklists.aspx) ; ne jamais envoyer en masse depuis le mode B sans désabonnement (en-tête `List-Unsubscribe`).

## Configuration automatique par le programme de setup (nginx-hardening.sh 2.38)

`nginx-hardening.sh --update` (étape 0d) installe `msmtp`, `msmtp-mta` (commande `sendmail`) et `bsd-mailx` (commande `mail`), puis demande **une seule fois** dans un terminal :
serveur SMTP, port (587), chiffrement (STARTTLS), nom d'utilisateur, adresse d'expéditeur, adresse de destination et mot de passe (sans écho).

- Les réponses non secrètes vont dans `/etc/default/nginx-tools-mail.conf` (modèle : `doc/nginx-tools-mail.conf.example`).
- Le **mot de passe** va dans `/etc/default/nginx-tools-mail.pass`, mode 0600, propriétaire root. Il n'est jamais dans le fichier de configuration, ni affiché, ni journalisé, ni dans un rapport (`--report-err`), ni dans les archives livrées.
- `/etc/msmtprc` est écrit pour les programmes Bash (`sendmail`, `mail`) ; le mot de passe y est lu dans le fichier à part (`passwordeval`). Un `/etc/msmtprc` créé par quelqu'un d'autre n'est jamais écrasé.
- Les programmes Python utilisent `apps/_courriel.py` (`python3 apps/_courriel.py --test`, `--send SUJET`, `--show-config`) ; `app-health-check.py` s'en sert quand ses propres clés `SMTP_*` sont vides.
- Une pièce jointe de plus de 100 Mo (`MAIL_ATTACH_MAX_MB`) est remplacée par un lien (voir `doc/nginx-tools-mail.conf.example`).
- Pour redemander les réponses : `nginx-hardening.sh --update --mail-setup`. Sans terminal : `--mail-host`, `--mail-user`… et la variable d'environnement `NGINX_TOOLS_MAIL_PASSWORD`.

### Entrées DNS à créer (valeurs exactes affichées par `app-health-check.py --check-email-dns`, étape 13 du setup)

Pour le domaine D de l'adresse d'expéditeur :

| Type | Nom | Valeur |
|------|-----|--------|
| TXT (SPF) | `D.` | `v=spf1 include:DOMAINE_DU_RELAIS ~all` si le domaine du relais publie un SPF, sinon `v=spf1 a:HOTE_DU_RELAIS ~all` |
| TXT (DMARC) | `_dmarc.D.` | `v=DMARC1; p=none; rua=mailto:postmaster@D; fo=1` (puis `quarantine`, puis `reject` après quelques semaines de rapports propres) |
| TXT (DKIM) | `SELECTEUR._domainkey.D.` | `v=DKIM1; k=rsa; p=CLÉ_PUBLIQUE` — clé et sélecteur fournis par le relais ; notez le sélecteur dans `DKIM_SELECTOR` |
| MX | `D.` | seulement si D doit aussi recevoir du courrier (chez votre fournisseur) |

Le SPF, le DKIM et le DMARC doivent concerner le domaine de l'adresse **expéditeur** (`MAIL_FROM`), pas celui du serveur SMTP.
