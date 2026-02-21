# Grafana — Dashboards et graphiques

Ce document décrit les dashboards Grafana fournis pour le monitoring Keycloak : nombre de dashboards, liste des graphiques, explications et légendes.

---

## Vue d’ensemble

| Élément | Valeur |
|--------|--------|
| **Nombre de dashboards** | 2 |
| **Nombre total de panneaux** | 18 (dont 2 textes informatifs) |
| **Source des données** | Prometheus (datasource `prometheus`, URL `http://prometheus:9090`) |
| **Dossier de provisioning** | `grafana/provisioning/dashboards/` |
| **Fichiers JSON** | `json/keycloak-overview.json`, `json/keycloak-sessions-users.json` |

Les dashboards sont chargés automatiquement au démarrage de Grafana (provisioning). Ils apparaissent dans le menu **Dashboards** → dossier **Keycloak**.

---

## Accès et utilisation

- **URL** : http://localhost:3000 (ou `http://localhost:${GRAFANA_PORT}` si modifié).
- **Identifiants par défaut** : admin / admin (variables `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`).
- **Plage temporelle** : en haut à droite (ex. « Dernière 1 heure », « Dernières 24 heures »). Certains panneaux utilisent cette plage (ex. « Total sur la période »).
- **Rafraîchissement** : optionnel, configurable (ex. 5s, 30s, 1m) ou manuel (bouton refresh).
- **Légende / description** : chaque panneau dispose d’une **description** (icône **ℹ️** à côté du titre) expliquant la métrique et sa signification.

---

## Dashboard 1 : Keycloak — Vue d’ensemble

- **UID** : `keycloak-overview`
- **Nombre de panneaux** : 11 (dont 1 texte)
- **Objectif** : vue globale sur le serveur Keycloak (débit, latence, erreurs, logins, sessions).

### Liste des panneaux (graphiques et explications)

| # | Type | Titre | Explication / légende |
|---|------|--------|------------------------|
| 1 | **Timeseries** | Débit (requêtes / s) | Nombre total de requêtes HTTP traitées par seconde par Keycloak (tous endpoints). Reflète l’activité globale (logins, API admin, etc.). *Source : `http_server_requests_seconds_count` (Keycloak port 9000).* |
| 2 | **Timeseries** | Latence moyenne (s) | Temps de réponse moyen des requêtes HTTP (fenêtre 1 min). Une hausse peut indiquer une saturation ou une charge base de données. *Source : ratio `_sum` / `_count` des requêtes HTTP.* |
| 3 | **Gauge** | Requêtes actives (estim.) | Estimation du nombre de requêtes en cours (formule de Little : débit × latence). Keycloak n’expose pas de jauge native ; à 0 quand il n’y a plus de trafic. *Seuils : vert &lt; 50, jaune &lt; 100, rouge ≥ 100.* |
| 4 | **Timeseries** | Taux d’erreur (%) | Part des requêtes en 4xx et 5xx par rapport au total (fenêtre 1 min). Utile pour détecter rejets (403, 429) ou erreurs serveur. |
| 5 | **Timeseries** | Taux de succès 2xx (%) | Part des requêtes 2xx par rapport au total. Complément du taux d’erreur ; proche de 100 % en conditions normales. |
| 6 | **Text** | Informations métriques | Rappel de ce qui est affiché (débit, latence, 2xx/4xx/5xx, logins, sessions) et de la source « session exporter » pour comptes distincts et sessions par client. |
| 7 | **Gauge** | Comptes distincts connectés (temps réel) | Nombre d’utilisateurs (userId) ayant au moins une session active dans le realm. *Source : keycloak-session-exporter, métrique `keycloak_distinct_users_connected`.* |
| 8 | **Timeseries** | Sessions actives par client | Nombre de sessions actives par client OAuth (admin-cli, security-admin-console, etc.). *Source : keycloak-session-exporter, `keycloak_sessions_total{client_id="..."}`.* |
| 9 | **Timeseries** | Logins (événements) — débit | Nombre d’événements login par seconde (event metrics Keycloak). Chaque succès d’authentification = 1 événement ; ce n’est pas le nombre de comptes distincts. *Nécessite image Keycloak avec feature user-event-metrics.* |
| 10 | **Stat** | Connexions réussies (total sur la période) | Nombre total de connexions réussies sur la plage temporelle du dashboard (ex. 49 K = 49 000). Pas le nombre de personnes uniques. *Suffixe affiché : « connexions ».* |
| 11 | **Timeseries** | Requêtes par statut HTTP | Débit par type de réponse : 2xx (succès), 4xx (client), 5xx (serveur). Permet de voir la répartition des succès et des erreurs dans le temps. |

---

## Dashboard 2 : Keycloak — Sessions et utilisateurs

- **UID** : `keycloak-sessions-users`
- **Nombre de panneaux** : 7 (dont 1 texte)
- **Objectif** : focus sur les sessions actives, la durée par utilisateur et les dernières connexions (id, username, email).

### Liste des panneaux (graphiques et explications)

| # | Type | Titre | Explication / légende |
|---|------|--------|------------------------|
| 1 | **Stat** | Comptes distincts connectés | Même indicateur que sur le dashboard Vue d’ensemble : nombre d’utilisateurs uniques avec au moins une session. *Seuils : vert, jaune (50), rouge (200).* |
| 2 | **Timeseries** | Sessions actives par client | Évolution du nombre de sessions actives par client OAuth. Utile pour voir les pics pendant les tests de charge ou l’usage de la console. |
| 3 | **Bar gauge** | Durée de session par utilisateur (connectés) | Temps écoulé (en secondes) depuis le début de chaque session active. Un utilisateur avec plusieurs sessions peut apparaître plusieurs fois. Limité aux 100 premières sessions. *Source : `keycloak_session_duration_seconds`.* |
| 4 | **Table** | Durée de session — détail (tableau) | Liste des utilisateurs actuellement connectés avec la durée de leur session (colonnes : user_id, username, durée en s). Utile pour export ou tri précis. |
| 5 | **Table** | Dernières connexions (id, username, email) | Liste des derniers événements LOGIN : date/heure, user_id, username, email. *Nécessite l’enregistrement des événements activé dans Keycloak (Realm → Events → Config → Save Events, type LOGIN).* |
| 6 | **Timeseries** | Évolution des comptes distincts connectés | Courbe du nombre de comptes distincts connectés dans le temps. Permet de voir les phases de montée ou descente de charge. |
| 7 | **Text** | À propos de ce dashboard | Rappel : source des données (keycloak-session-exporter), délai après `make up`, et condition pour le panneau « Dernières connexions » (events activés). |

---

## Légendes et sources de données

- **Keycloak natif (port 9000)** : métriques HTTP (`http_server_requests_seconds_*`) et event metrics (`keycloak_user_events_total`) si l’image est construite avec `Dockerfile.keycloak`.
- **keycloak-session-exporter (port 9091)** : métriques dérivées de l’API Admin Keycloak : `keycloak_sessions_total`, `keycloak_distinct_users_connected`, `keycloak_session_duration_seconds`, `keycloak_last_login_timestamp_seconds`.

Toutes les requêtes Prometheus utilisent le label `namespace="keycloak"` lorsqu’il est appliqué par la configuration Prometheus (voir [prometheus.md](prometheus.md)).

---

## Fichiers et structure

```
grafana/
├── provisioning/
│   ├── dashboards/
│   │   ├── default.yml          # Provider : dossier Keycloak, path json
│   │   └── json/
│   │       ├── keycloak-overview.json
│   │       └── keycloak-sessions-users.json
│   └── datasources/
│       └── datasource.yml       # Prometheus, url: http://prometheus:9090
```

- **Modifier un dashboard** : éditer le JSON correspondant puis recharger Grafana (ou redémarrer le conteneur). Les dashboards sont en `editable: true`.
- **Ajouter un dashboard** : ajouter un fichier `.json` dans `json/` en respectant le schéma Grafana (title, uid, panels, etc.) ; le provider les charge automatiquement.

---

## Voir aussi

- [grafana-metrics.md](grafana-metrics.md) — Panneaux « Logins (événements) » à 0, event metrics Keycloak.
- [session-exporter.md](session-exporter.md) — Métriques exposées par l’exporter (sessions, comptes distincts, durée, dernières connexions).
- [prometheus.md](prometheus.md) — Configuration Prometheus et tutoriel de requêtes.
