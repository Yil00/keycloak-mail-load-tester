# Notes de release

## Résumé des changements

- **Stack** : Keycloak 26 + Postgres 16 + MailHog + Prometheus + Grafana (docker-compose). Keycloak est construit via `Dockerfile.keycloak` (feature user-event-metrics pour les métriques logins).
- **Scripts** : déplacés dans `src/` :
  - `src/test_keycloak.py` : test d'envoi de mails en masse (création users → envoi vérification → suppression), stratégies full / batch-pause / rate.
  - `src/keycloak_load_test.py` : test de charge (mode constant ou ramp : montée/descente progressive).
  - `src/keycloak_load_test_multi_user.py` : test de charge multi-comptes (création de N users, test, suppression) pour une simulation proche production.
  - `src/keycloak_session_exporter.py` : exporteur Prometheus (API Admin Keycloak) — sessions par client, comptes distincts connectés, durée de session, dernières connexions (id, username, email).
- **Monitoring** : Prometheus scrape Keycloak (port 9000) et keycloak-session-exporter (port 9091). Config : `prometheus/prometheus.yml` ; doc : `docs/prometheus.md`. Grafana : 2 dashboards (dossier Keycloak) — « Vue d'ensemble » (débit, latence, 2xx/4xx/5xx, comptes distincts, sessions par client, logins, connexions total) et « Sessions et utilisateurs » (durée session par user, dernières connexions, évolution comptes distincts) ; doc : `docs/grafana-dashboards.md`.
- **Documentation** : `docs/admin-keycloak.md`, `docs/load-test-tokens.md`, `docs/session-exporter.md`, `docs/grafana-metrics.md`, `docs/grafana-dashboards.md`, `docs/prometheus.md`. `grafana/README.md` et `prometheus/README.md`. `env.dist` documente `EXPORTER_PORT` pour l'exporter.

Les commandes `make` (test, load-test, load-test-multi, etc.) pointent vers `src/`. Le fichier `.env` à la racine est lu par docker-compose et par les scripts.
