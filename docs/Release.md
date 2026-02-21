# Notes de release

## Résumé des changements

- **Stack** : Keycloak 26 + Postgres 16 + MailHog + Prometheus + Grafana (docker-compose).
- **Scripts** : déplacés dans `src/` :
  - `src/test_keycloak.py` : test d’envoi de mails en masse (création users → envoi vérification → suppression), stratégies full / batch-pause / rate.
  - `src/keycloak_load_test.py` : test de charge (mode constant ou ramp : montée/descente progressive).
- **Monitoring** : Prometheus scrape les métriques Keycloak (port 9000), Grafana dashboard « Keycloak — Vue d’ensemble » (débit, latence, requêtes actives estimées, 2xx/4xx/5xx).
- **Documentation** : `docs/admin-keycloak.md` (Direct access grants, protection brute force), `env.dist` et README à jour.

Les commandes `make` (test, test-nb, test-rate, test-batch, load-test, load-test-ramp) pointent vers `src/`. Le fichier `.env` à la racine est lu par docker-compose et par les scripts.
