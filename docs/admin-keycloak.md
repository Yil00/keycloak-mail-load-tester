# Configuration admin Keycloak

Cette page décrit les réglages à faire dans l’interface d’administration Keycloak pour les tests (envoi de mails, test de charge).

## Autoriser le grant « Direct access » pour admin-cli

Requis pour que le **test de charge** (logins via client `admin-cli`) fonctionne sans erreur 403.

1. Ouvre **http://localhost:8080** (ou l’URL de ton instance).
2. Connecte-toi avec l’admin : **admin** / **admin** (ou les identifiants définis dans `.env`).
3. Reste sur le realm **master**.
4. Menu **Clients** → clique sur **admin-cli**.
5. Onglet **Paramètres** (Settings).
6. Active **Direct access grants** (ou **Direct access grants enabled**).
7. Clique sur **Enregistrer**.

Sans cette option, les requêtes « Resource Owner Password » (login avec username/password) renverront **403 Forbidden**.

---

## Protection contre la force brute (optionnel pour le test)

Lors d’un **test de charge** avec beaucoup de requêtes de login, Keycloak peut bloquer des adresses IP à cause de la détection de force brute.

1. Realm **master** → **Sécurité** (ou **Security defenses**).
2. Section **Protection contre la force brute** (Brute force detection).

Pour les tests uniquement, tu peux :

- **Désactiver temporairement** la protection, ou  
- **Augmenter** le nombre de tentatives autorisées / le seuil de blocage.

Pense à réactiver ou à remettre des valeurs raisonnables en environnement partagé ou préprod.
