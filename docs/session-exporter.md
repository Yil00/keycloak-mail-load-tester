# Exporter sessions Keycloak (Prometheus / Grafana)

Le script **`src/keycloak_session_exporter.py`** interroge l’**API Admin REST** Keycloak pour obtenir les **sessions actives**, les **comptes distincts connectés**, la **durée de session par utilisateur** et les **dernières connexions** (événements LOGIN). Il expose ces valeurs au format Prometheus sur un serveur HTTP (port 9091, endpoint `/metrics`).

---

## Métriques exposées

| Métrique | Type | Description |
|----------|------|-------------|
| `keycloak_sessions_total{client_id="..."}` | gauge | Nombre de sessions actives pour ce client (ex. `admin-cli`, `security-admin-console`). |
| `keycloak_distinct_users_connected` | gauge | Nombre d’utilisateurs (userId) distincts ayant au moins une session dans le realm. |
| `keycloak_session_duration_seconds{user_id="...", username="..."}` | gauge | Durée en secondes de la session (temps écoulé depuis le début). Limité aux 100 premières sessions. |
| `keycloak_last_login_timestamp_seconds{user_id="...", username="...", email="..."}` | gauge | Timestamp (epoch en secondes) des dernières connexions (événements LOGIN). Nécessite l’enregistrement des événements activé dans Keycloak. |
| `keycloak_session_exporter_up` | gauge | 1 si l’exporter a pu récupérer les données, 0 en cas d’erreur (auth, API, etc.). |

---

## Utilisation

### Avec Docker Compose (recommandé)

Le service **keycloak-session-exporter** est défini dans `docker-compose.yml`. Il est démarré avec les autres services :

```bash
make up
```

- **URL interne** (depuis Prometheus) : `http://keycloak-session-exporter:9091/metrics`
- **URL locale** (test) : http://localhost:9091/metrics

Prometheus scrape automatiquement cet exporter (voir `prometheus/prometheus.yml`, job `keycloak-session-exporter`). Deux dashboards Grafana utilisent ces métriques : **Keycloak — Vue d'ensemble** (comptes distincts, sessions par client, logins) et **Keycloak — Sessions et utilisateurs** (durée par user, dernières connexions id/username/email, évolution des comptes distincts).

### En local (sans Docker)

Variables d’environnement (ou `.env`) : `KEYCLOAK_URL`, `KEYCLOAK_REALM`, `KEYCLOAK_ADMIN_USER`, `KEYCLOAK_ADMIN_PASSWORD`. Optionnel : `EXPORTER_PORT` (défaut 9091).

```bash
pip install requests python-dotenv
python src/keycloak_session_exporter.py
```

Puis configurer Prometheus pour scraper `http://localhost:9091` (ou l’hôte adéquat en préprod).

---

## API Keycloak utilisée

- **Authentification** : token OAuth (client `admin-cli`, grant type « password » avec l’utilisateur admin).
- **Endpoints** :
  - `GET /admin/realms/{realm}/client-session-stats` → map clientId → nombre de sessions actives.
  - `GET /admin/realms/{realm}/clients` → liste des clients (id, clientId) pour résoudre les UUID.
  - `GET /admin/realms/{realm}/clients/{client-uuid}/user-sessions?first=0&max=500` → sessions (userId, username, start) pour comptes distincts et durée de session.
  - `GET /admin/realms/{realm}/events?type=LOGIN&max=25` → derniers événements LOGIN (time, userId).
  - `GET /admin/realms/{realm}/users/{userId}` → username, email pour enrichir les événements.

**Dernières connexions** : le panneau « Dernières connexions » du dashboard **Sessions et utilisateurs** nécessite que Keycloak enregistre les événements : **Realm** → **Events** → **Config** → **Save Events** et type **LOGIN**.

En cas d’échec (token, timeout, 4xx/5xx), les métriques sont mises à 0 et `keycloak_session_exporter_up` est à 0.
