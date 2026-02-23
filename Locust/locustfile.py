import os
import json
from itertools import count

from locust import HttpUser, task, between


KEYCLOAK_HOST = os.getenv("KEYCLOAK_HOST", "keycloak")
KEYCLOAK_PORT = int(os.getenv("KEYCLOAK_PORT", "8080"))
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "master")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "admin-cli")

# Comptes de charge : loadtest_user_1, loadtest_user_2, ..., loadtest_user_N
USER_PREFIX = os.getenv("KEYCLOAK_LOAD_USER_PREFIX", "loadtest_user_")
USER_PASSWORD = os.getenv("KEYCLOAK_LOAD_PASSWORD", "testpass")
USER_COUNT = int(os.getenv("KEYCLOAK_USER_COUNT", "100"))

_user_counter = count(0)


class KeycloakPasswordGrantUser(HttpUser):
    """
    Utilisateur Locust qui exécute un flux password grant sur
    /realms/{realm}/protocol/openid-connect/token avec des comptes distincts.

    Chaque instance Locust utilise un login différent dérivé de USER_PREFIX.
    Exemple de comptes attendus dans Keycloak :
      loadtest_user_1, loadtest_user_2, ..., loadtest_user_N
    tous avec le même mot de passe USER_PASSWORD.
    """

    wait_time = between(1, 3)
    host = f"http://{KEYCLOAK_HOST}:{KEYCLOAK_PORT}"

    def on_start(self):
        # Assigne un index de compte unique (en modulo sur USER_COUNT)
        index = next(_user_counter) % USER_COUNT + 1
        self.username = f"{USER_PREFIX}{index}"
        self.password = USER_PASSWORD
        self._refresh_tokens = []  # tous les tokens à invalider en fin de test

    def on_stop(self):
        """En fin de test : logout pour chaque session créée (chaque login = une session Keycloak)."""
        tokens = getattr(self, "_refresh_tokens", None) or []
        for refresh_token in tokens:
            if not refresh_token:
                continue
            logout_data = {
                "client_id": KEYCLOAK_CLIENT_ID,
                "refresh_token": refresh_token,
            }
            self.client.post(
                f"/realms/{KEYCLOAK_REALM}/protocol/openid-connect/logout",
                data=logout_data,
                name="logout",
            )
        self._refresh_tokens = []

    @task
    def get_token_with_password_grant(self):
        """
        Demande un access_token via le grant_type=password
        avec un compte distinct par utilisateur Locust.
        """
        data = {
            "grant_type": "password",
            "client_id": KEYCLOAK_CLIENT_ID,
            "username": self.username,
            "password": self.password,
            "scope": "openid",
        }

        with self.client.post(
            f"/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token",
            data=data,
            name="password_grant_token",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                # On marque la requête en échec pour suivre les erreurs dans le dashboard
                resp.failure(
                    f"HTTP {resp.status_code} pour {self.username}: {resp.text[:200]}"
                )
                return

            try:
                payload = resp.json()
            except json.JSONDecodeError:
                resp.failure("Réponse non JSON")
                return

            if "access_token" not in payload:
                resp.failure("Pas de access_token dans la réponse")
                return

            # Chaque login crée une session Keycloak ; on garde le token pour tout fermer en on_stop
            rt = payload.get("refresh_token")
            if rt:
                self._refresh_tokens.append(rt)

            # Pas de logout ici : les sessions restent actives pendant le test pour que
            # les 10 comptes distincts s'affichent en temps réel dans Grafana.

