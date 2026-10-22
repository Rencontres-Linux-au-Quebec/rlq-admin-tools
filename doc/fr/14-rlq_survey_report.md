# rlq_survey_report - module Odoo 18

Module Odoo 18 Community (dépend de `survey`, `mail`, `event`) pour les sondages mensuels des Rencontres Linux au Québec. La documentation complète pour les utilisateurs est le *Guide utilisateur* livré dans `doc/Guide-utilisateur-rlq_survey_report.html` et servi dans Odoo à l'adresse `/rlq_survey_report/aide`. Cette page est la vue de l'administrateur.

## Fonctions

* **Rapports** à partir des données natives `survey.user_input` : synthèse toutes rencontres, détail par rencontre, fiche par participant, section « À surveiller » ; exports HTML, PDF, Excel protégés par mot de passe (conformité à la loi sur la vie privée), anonymisation facultative des participants ; historique des fichiers générés.
* **Sondage par type de billet** : chaque type de billet d'événement peut pointer vers un sondage différent ; un champ de l'inscription contient le bon lien pour les modèles de courriel.
* **Actions de suivi** et commentaires internes par sondage.
* **Réponses envoyées par courriel au participant** à la fin d'un sondage (activé sondage par sondage).
* **Avertissements d'inscriptions** : courriel quand un événement atteint N inscriptions, répété tous les N (`rlq_alerte_repeter`), et à chaque sondage complété.
* **Groupes et étiquettes des inscrits** : un groupe Odoo par billet (`RLQ-<PRÉFIXE>-<billet>`), groupes liés aux réponses d'un sondage, reflétés en étiquettes de contact ; synchronisation périodique par sondage et par événement (toutes les N minutes, minimum 5, l'événement s'arrête seul un jour après sa fin) ; un assistant « Vérifier les groupes et étiquettes » montre un aperçu avant d'appliquer.
* **Adresses courriel invalides des inscriptions** (1.109) : chaque inscription est marquée *invalide* (ne peut pas recevoir de courriel, ex. `marieb.essai@gmail'com`), *faute de frappe probable* (`gmial.com`) ou *jetable*, avec la correction suggérée. Une erreur de ponctuation qui ne change aucune lettre est corrigée dès l'inscription (avant le départ du courriel de confirmation). Menu *Événements > Courriels invalides* : la liste, le bouton **Corriger et renvoyer** (inscription et contact corrigés, courriels en échec réadressés et remis en file, confirmation renvoyée) et les courriels sortants en échec (administrateurs).

## Paramètres système

| Clé | Rôle |
|---|---|
| `rlq_survey_report.mot_de_passe_defaut` | mot de passe par défaut pré-rempli dans le formulaire d'export - **à définir après l'installation** |
| `rlq_survey_report.courriel_inscriptions` | adresse(s) des avertissements d'inscriptions quand l'événement n'en a pas |
| `rlq_survey_report.url_aide` | cible du bouton « Aide » |
| `rlq_survey_report.synchro_minutes_defaut` | intervalle proposé (minutes, minimum 5, défaut `15`) pour une nouvelle synchronisation périodique |
| `rlq_survey_report.etiquettes_groupes` | `1` (défaut) étiquettes de contact pour les groupes ; `0` désactive |
| `rlq_survey_report.registration_email_autofix` | `syntax` (défaut : ponctuation et espaces seulement), `off`, ou `typos` (aussi un domaine courant mal écrit) |

## Tâches planifiées

Purge quotidienne des copies non anonymisées de plus de 3 jours ; synchronisation quotidienne des étiquettes ; toutes les 5 minutes, synchronisation périodique des sondages et événements cochés (tâche **désactivée tant qu'aucune case n'est cochée** ; les groupes sont de toute façon mis à jour tout de suite à chaque inscription, sondage terminé ou création de compte). Le menu « Synchronisation : sommaire » résume l'état.

## Procédure de mise à jour

Utiliser `odoo-update-module.sh --backup --zip rlq_survey_report.18.0.1.N.0.zip`. **Essayer d'abord sur une base de développement** : ce module a été écrit sans instance Odoo sous la main ; `doc/NOTES_VALIDATION.md` liste, version par version, ce qu'il faut confirmer sur une vraie instance, et des tests Odoo (`tests/`) sont fournis mais n'ont pas été exécutés par l'outillage de l'auteur. Pour les lancer :

```bash
odoo-bin -d BASE_DE_TEST -i rlq_survey_report --test-enable --test-tags rlq_survey_report --stop-after-init
```

Le `run-all.sh` du module enchaîne ruff, la vérification de syntaxe, les tests autonomes (sans Odoo) et, si PostgreSQL et Odoo existent, une base jetable avec les tests Odoo.
