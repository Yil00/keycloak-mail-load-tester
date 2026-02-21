# Test de charge : explication (tokens vs comptes réels)

Ce document décrit comment fonctionne le test de charge (`src/keycloak_load_test.py`) et en quoi il diffère d’une simulation avec plusieurs comptes utilisateurs réels sur Keycloak.

---

## Comment fonctionne le test actuel

Le script appelle le **endpoint d’émission de tokens** Keycloak :

- **URL** : `{KEYCLOAK_URL}/realms/{realm}/protocol/openid-connect/token`
- **Méthode** : `POST`
- **Grant type** : **Resource Owner Password Credentials** (`grant_type=password`)
- **Client** : `admin-cli` (nécessite « Direct access grants » activé, voir [admin-keycloak.md](admin-keycloak.md))

À chaque requête, le script envoie les **mêmes identifiants** (par défaut : `admin` / mot de passe admin). Keycloak :

1. Vérifie le couple username / password
2. Émet un token (access_token, etc.)
3. Renvoie la réponse JSON

Le test lance **N threads** (mode constant) ou **X utilisateurs virtuels** avec montée/descente (mode ramp). Chaque thread enchaîne des appels au endpoint token avec **le même compte**, sans réutiliser le token (chaque appel = un nouveau login).

---

## Ce que le test mesure

| Métrique | Signification |
|----------|----------------|
| **Débit (req/s)** | Nombre d’obtentions de token par seconde que Keycloak peut traiter. |
| **Latence** | Temps de réponse du endpoint token (min, moyenne, p50, p95, p99). |
| **Taux de succès** | Part des requêtes qui renvoient un token (HTTP 200). |

On mesure donc la **capacité du endpoint token** et du flux « password » avec **un seul utilisateur répété**.

---

## Un seul compte (token) vs plusieurs comptes réels

Ce n’est **pas** la même chose qu’une charge avec des comptes utilisateurs réels distincts.

### Test actuel : un seul compte (ex. admin)

- Tous les threads utilisent le **même** username/password.
- Keycloak refait à chaque fois la même vérification, souvent très bien servie par le **cache** (même user, même realm).
- On sollicite surtout : **réseau, sérialisation, émission de token**, et peu la base (lookup user répété pour le même user).

**Intérêt** : mesurer le **débit maximal** du endpoint token et la latence dans un cas très favorable (cache chaud, un seul user).

### Charge avec plusieurs comptes réels (users Keycloak distincts)

- Chaque requête (ou chaque utilisateur virtuel) utilise un **compte différent** (user1, user2, …, userN).
- Keycloak doit à chaque fois : **rechercher l’utilisateur** en base (ou cache), vérifier le mot de passe, puis émettre le token.
- On sollicite davantage : **base de données, caches par user, éventuellement détection brute force**, et le cœur métier Keycloak (user lookup, validation).

**Intérêt** : scénario plus **réaliste** (plusieurs utilisateurs qui se connectent en même temps), utile pour dimensionner en préprod.

### Résumé

| Aspect | Un seul user (token répété) | Plusieurs users réels |
|--------|-----------------------------|------------------------|
| Endpoint | Même : `/token` | Même : `/token` |
| Comptes utilisés | 1 (ex. admin) | N (user1, user2, …) |
| Cache / DB | Très favorable (même user) | Plus de lookups, moins de cache |
| Réalisme | Bon pour « débit max » du token | Plus proche de vrais utilisateurs |

---

## En pratique

- Pour **tester la capacité brute du token endpoint** (combien de req/s, quelle latence) : utilisez **`src/keycloak_load_test.py`** (un seul compte, ex. admin). Commandes : `make load-test`, `make load-test-ramp`.
- Pour **simuler une charge proche de la production** avec beaucoup d’utilisateurs différents : utilisez **`src/keycloak_load_test_multi_user.py`** :
  - **Création automatique** : le script crée N utilisateurs dans le realm (mot de passe commun), lance le test de charge (chaque thread utilise des comptes différents), puis supprime les users (sauf avec `--no-cleanup`).
  - **Fichier de comptes** : option `--accounts-file path` avec une ligne `username:password` par compte.
  - Commandes Make : `make load-test-multi`, `make load-test-multi-ramp` (variables : `CREATE_USERS`, `MULTI_USER_PASSWORD`, `CONCURRENT`, `DURATION`, etc.).
