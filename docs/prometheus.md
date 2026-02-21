# Prometheus — Configuration et tutoriel

Ce document explique le rôle de Prometheus dans le projet Keycloak, la configuration utilisée, et un tutoriel pour interroger les métriques.

---

## Rôle de Prometheus

**Prometheus** récupère (scrape) périodiquement les métriques exposées par :

1. **Keycloak** (port 9000) : métriques HTTP et event metrics (logins, etc.) si l’image est construite avec la feature dédiée.
2. **keycloak-session-exporter** (port 9091) : métriques dérivées de l’API Admin (sessions par client, comptes distincts connectés, durée de session, dernières connexions).

Prometheus stocke ces séries temporelles et les expose pour les requêtes (PromQL). **Grafana** se connecte à Prometheus comme datasource et affiche les graphiques à partir de ces données.

---

## Configuration

### Fichier principal : `prometheus/prometheus.yml`

```yaml
global:
  scrape_interval: 5s      # Récupération des métriques toutes les 5 secondes
  evaluation_interval: 5s  # Évaluation des règles toutes les 5 secondes

scrape_configs:
  - job_name: keycloak
    static_configs:
      - targets: ["keycloak:9000"]
        labels:
          namespace: keycloak
          container: keycloak
    metrics_path: /metrics

  - job_name: keycloak-session-exporter
    static_configs:
      - targets: ["keycloak-session-exporter:9091"]
        labels:
          namespace: keycloak
          container: keycloak-session-exporter
    metrics_path: /metrics
```

- **scrape_interval** : fréquence à laquelle Prometheus interroge chaque cible. 5 s donne des courbes assez fines.
- **targets** : adresses des services dans le réseau Docker (noms de conteneurs).
- **labels** : étiquettes ajoutées à toutes les métriques scrapées depuis cette cible (ex. `namespace="keycloak"`). Utilisées dans Grafana pour filtrer (`namespace="keycloak"`).

### Jobs configurés

| Job | Cible | Rôle |
|-----|--------|------|
| **keycloak** | `keycloak:9000` | Métriques natives Keycloak (HTTP, event metrics). |
| **keycloak-session-exporter** | `keycloak-session-exporter:9091` | Métriques sessions / utilisateurs (API Admin). |

---

## Accès à l’interface Prometheus

- **URL** : http://localhost:9090 (ou `http://localhost:${PROMETHEUS_PORT}`).
- Aucune authentification par défaut.

Onglets utiles :

- **Graph** : exécuter une requête PromQL et afficher la courbe ou le tableau.
- **Status → Targets** : état des cibles (UP / DOWN). Indispensable si Grafana affiche « No data ».

---

## Tutoriel : premières requêtes

### 1. Vérifier que les cibles sont UP

1. Aller dans **Status** → **Targets**.
2. Vérifier que **keycloak** et **keycloak-session-exporter** sont **UP**. Si **DOWN**, vérifier que les conteneurs tournent (`docker compose ps`) et que le port est joignable depuis Prometheus.

### 2. Afficher le nombre de comptes distincts connectés

Dans **Graph**, saisir :

```promql
keycloak_distinct_users_connected
```

Puis **Execute**. Vous devriez voir une ou plusieurs séries (avec le label `namespace="keycloak"` si appliqué). Onglet **Table** pour la valeur instantanée, **Graph** pour l’évolution dans le temps.

### 3. Afficher les sessions par client

```promql
keycloak_sessions_total
```

Chaque ligne correspond à un `client_id` (ex. `admin-cli`, `security-admin-console`). La **Value** est le nombre de sessions actives pour ce client.

### 4. Débit de requêtes Keycloak (requêtes par seconde)

```promql
sum(rate(http_server_requests_seconds_count{namespace="keycloak"}[1m]))
```

`rate(...[1m])` calcule le taux sur la dernière minute ; `sum` agrège toutes les séries. Unité : requêtes par seconde.

### 5. Total des connexions réussies sur la période affichée

En Prometheus on utilise souvent `increase` sur un compteur. Exemple sur 1 h :

```promql
sum(increase(keycloak_user_events_total{event="login",error=""}[1h]))
```

Dans Grafana, la plage est variable : `$__range` est utilisé dans les panneaux pour s’adapter à la plage temporelle du dashboard.

---

## Notions PromQL utiles

| Élément | Exemple | Signification |
|--------|---------|----------------|
| **Sélecteur** | `keycloak_sessions_total{client_id="admin-cli"}` | Filtre les séries par label. |
| **rate()** | `rate(metric[5m])` | Taux de variation par seconde sur la fenêtre (pour compteurs). |
| **increase()** | `increase(metric[1h])` | Augmentation sur la fenêtre (pour compteurs). |
| **sum()** | `sum(metric)` | Somme sur toutes les séries. |
| **or vector(0)** | `metric or vector(0)` | Évite « no data » : affiche 0 si la métrique n’existe pas. |

---

## Dépannage

### Grafana affiche « No data » sur certains panneaux

1. **Status → Targets** : les deux jobs doivent être **UP**. Si **keycloak-session-exporter** est DOWN, l’exporter met peut-être du temps à démarrer (pip install) ; attendre 1–2 min ou vérifier les logs : `docker logs keycloak_session_exporter`.
2. **Vérifier que la métrique existe** : dans Prometheus, onglet **Graph**, taper le nom de la métrique (ex. `keycloak_distinct_users_connected`) et exécuter. Si aucun résultat, la métrique n’est pas encore scrapée ou l’exporter est en échec.
3. **Panneaux « Logins (événements) » à 0** : voir [grafana-metrics.md](grafana-metrics.md) (image Keycloak avec event metrics).

### Prometheus ne scrape pas l’exporter

- Vérifier que `keycloak-session-exporter` et `prometheus` sont sur le même réseau Docker (comme défini dans `docker-compose.yml`).
- Tester depuis le conteneur Prometheus : `docker exec prometheus wget -qO- http://keycloak-session-exporter:9091/metrics | head -5`.

### Recharger la configuration Prometheus

Si vous modifiez `prometheus.yml` :

```bash
curl -X POST http://localhost:9090/-/reload
```

(Le conteneur doit avoir été lancé avec `--web.enable-lifecycle` ; c’est le cas dans le `command` du `docker-compose`.)

---

## Fichiers et variables

| Fichier / répertoire | Rôle |
|----------------------|------|
| `prometheus/prometheus.yml` | Configuration des jobs de scrape et des labels. |
| Variable d’environnement `PROMETHEUS_PORT` | Port exposé sur l’hôte (défaut 9090). Voir `env.dist` / `.env`. |

Les métriques sont stockées dans le conteneur (volume interne Prometheus). En cas de recréation du conteneur, l’historique est perdu sauf si un volume persistant est ajouté.

---

## Voir aussi

- [grafana-dashboards.md](grafana-dashboards.md) — Liste des dashboards et des graphiques.
- [session-exporter.md](session-exporter.md) — Métriques exposées par l’exporter.
- [grafana-metrics.md](grafana-metrics.md) — Event metrics Keycloak et panneaux Logins.
