# Métriques Grafana et événements Keycloak

Ce document décrit les panneaux « Logins (événements) » du dashboard Grafana et les limites de ce que Keycloak expose.

---

## Panneaux « Logins (événements) » à 0

Si les graphiques **Logins (événements) — débit** et **Logins (événements) — total sur la période** restent à 0 alors que des tests de charge (ex. `make load-test-multi-ramp`) génèrent bien des connexions réussies, la cause est en général que les **event metrics** Keycloak ne sont pas exposées.

### Cause

En Keycloak 26.x, les métriques d’événements utilisateur (`keycloak_user_events_total`) dépendent de la **feature** `user-event-metrics`, qui doit être activée au **build**. Sans elle, l’endpoint `/metrics` (port 9000) ne contient pas ces compteurs.

### Configuration dans ce projet

Le projet utilise une **image Keycloak personnalisée** construite avec `Dockerfile.keycloak`, qui active la feature `user-event-metrics` au build. Le `docker-compose.yml` build cette image et lance Keycloak avec `start` (pas `start-dev`) pour réutiliser ce build.

- **Première fois** : lancer `docker compose build keycloak` puis `make up`, ou `docker compose up -d --build`.
- Si les panneaux restent à 0 : vérifier que l’image a bien été construite et que Keycloak a été redémarré après le build.

### Vérifier que les métriques sont exposées

Depuis la machine hôte (avec le port 9000 mappé) :

```bash
curl -s http://localhost:9000/metrics | grep keycloak_user_events_total
```

Vous devez voir des lignes du type :

```
keycloak_user_events_total{...,event="login",error="",...} ...
keycloak_user_events_total{...,event="logout",error="",...} ...
```

Si aucune ligne n’apparaît, la feature ou les options event-metrics ne sont pas actives (vérifier les variables d’environnement et redémarrer Keycloak).

---

## Nombre de comptes actifs en temps réel

**Keycloak n’expose pas** de métrique pour :

- le **nombre de comptes distincts connectés en même temps** (sessions actives, utilisateurs uniques) ;
- le **nombre de comptes distincts connectés sur les X dernières minutes**.

Les métriques **Logins (événements)** donnent le **nombre d’événements login** (connexions réussies) : chaque appel réussi au flux token (password, etc.) incrémente le compteur. Un même utilisateur qui se connecte 10 fois compte pour 10 événements, pas pour 1 « compte actif ».

Pour avoir une notion de « comptes actifs » ou « utilisateurs uniques sur une période », il faudrait soit :

- s’appuyer sur un autre système (logs, base de données, session store) et construire une métrique personnalisée ;
- ou utiliser une extension / un export personnalisé Keycloak (hors périmètre des métriques Prometheus fournies par défaut).

Le texte du dashboard Grafana rappelle cette limite dans le panneau « Informations métriques ».
