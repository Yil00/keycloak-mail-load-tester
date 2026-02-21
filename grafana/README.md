# Grafana — Monitoring Keycloak

Ce dossier contient la configuration **provisioning** de Grafana pour le projet Keycloak.

## Contenu

- **provisioning/dashboards/** : chargement automatique des dashboards au démarrage.
  - **default.yml** : provider qui charge les JSON du dossier `json/` dans le dossier Grafana **Keycloak**.
  - **json/** : 2 dashboards (Vue d’ensemble, Sessions et utilisateurs).
- **provisioning/datasources/** : datasource Prometheus préconfigurée (`http://prometheus:9090`).

## Dashboards

| Dashboard | Fichier | Panneaux |
|-----------|---------|----------|
| Keycloak — Vue d’ensemble | `json/keycloak-overview.json` | 11 |
| Keycloak — Sessions et utilisateurs | `json/keycloak-sessions-users.json` | 7 |

Accès : menu **Dashboards** → dossier **Keycloak**.

## Documentation

Voir **[docs/grafana-dashboards.md](../docs/grafana-dashboards.md)** pour :

- Nombre de dashboards et de graphiques
- Liste détaillée des panneaux avec explications et légendes
- Sources des données (Keycloak, keycloak-session-exporter)
- Structure des fichiers et personnalisation

Voir aussi **[docs/grafana-metrics.md](../docs/grafana-metrics.md)** pour les panneaux « Logins (événements) » et event metrics.
