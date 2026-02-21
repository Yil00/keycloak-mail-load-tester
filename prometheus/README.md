# Prometheus — Collecte des métriques Keycloak

Ce dossier contient la configuration Prometheus utilisée par le projet Keycloak.

## Fichier de configuration

- **prometheus.yml** : jobs de scrape pour Keycloak (port 9000) et keycloak-session-exporter (port 9091), avec labels `namespace: keycloak`.

## Jobs

| Job | Cible | Métriques |
|-----|--------|-----------|
| keycloak | `keycloak:9000` | HTTP, event metrics (logins, etc.) |
| keycloak-session-exporter | `keycloak-session-exporter:9091` | Sessions, comptes distincts, durée, dernières connexions |

## Documentation

Voir **[docs/prometheus.md](../docs/prometheus.md)** pour :

- Explication du rôle de Prometheus
- Détail de la configuration (scrape_interval, labels)
- Tutoriel de requêtes PromQL
- Dépannage (targets DOWN, No data)
