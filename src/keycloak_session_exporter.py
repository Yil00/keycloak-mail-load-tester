#!/usr/bin/env python3
"""
Exporteur Prometheus pour les sessions Keycloak (API Admin REST).

Expose :
  - keycloak_sessions_total{client_id="..."} : nombre de sessions actives par client
  - keycloak_distinct_users_connected : nombre de comptes (userId) distincts ayant au moins une session
  - keycloak_session_duration_seconds{user_id="...", username="..."} : durée en secondes de la session (utilisateurs connectés)
  - keycloak_last_login_timestamp_seconds{user_id="...", username="...", email="..."} : timestamp (epoch s) des dernières connexions (événements LOGIN)

À lancer en service HTTP sur le port 9091 ; Prometheus scrape /metrics.
Variables d'environnement : KEYCLOAK_URL, KEYCLOAK_REALM, KEYCLOAK_ADMIN_USER, KEYCLOAK_ADMIN_PASSWORD.
"""

import os
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import List, Optional
from urllib.parse import urlparse

try:
    from dotenv import load_dotenv
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_root, ".env"))
    load_dotenv()
except ImportError:
    pass

import requests

_DEFAULT_PORT = os.environ.get("KEYCLOAK_PORT", "8080")
DEFAULT_URL = os.environ.get("KEYCLOAK_URL", f"http://localhost:{_DEFAULT_PORT}").rstrip("/")
DEFAULT_REALM = os.environ.get("KEYCLOAK_REALM", "master")
DEFAULT_ADMIN = os.environ.get("KEYCLOAK_ADMIN_USER", "admin")
DEFAULT_ADMIN_PASS = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin")
EXPORTER_PORT = int(os.environ.get("EXPORTER_PORT", "9091"))
USER_SESSIONS_PAGE_SIZE = 500
MAX_SESSION_DURATION_SERIES = 100  # limite cardinalité
MAX_LAST_LOGIN_EVENTS = 25


def get_admin_token(base_url: str, admin_user: str, admin_pass: str) -> Optional[str]:
    try:
        r = requests.post(
            f"{base_url}/realms/master/protocol/openid-connect/token",
            data={
                "client_id": "admin-cli",
                "username": admin_user,
                "password": admin_pass,
                "grant_type": "password",
            },
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["access_token"]
    except Exception as e:
        err = getattr(e, "response", None)
        if err is not None:
            print(f"keycloak_session_exporter: get_admin_token {err.status_code} {err.text[:200]}", file=sys.stderr)
        else:
            print(f"keycloak_session_exporter: get_admin_token error: {e}", file=sys.stderr)
        return None


def fetch_client_session_stats(base_url: str, realm: str, token: str):
    """Retourne soit un dict {client_id: count} (format Keycloak récent), soit une list de {id, clientId, active} (ancien)."""
    try:
        r = requests.get(
            f"{base_url}/admin/realms/{realm}/client-session-stats",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        return data
    except Exception as e:
        err = getattr(e, "response", None)
        if err is not None:
            print(f"keycloak_session_exporter: fetch_client_session_stats {err.status_code} {err.text[:200]}", file=sys.stderr)
        else:
            print(f"keycloak_session_exporter: fetch_client_session_stats error: {e}", file=sys.stderr)
        return None


def fetch_clients(base_url: str, realm: str, token: str) -> Optional[List[dict]]:
    """Liste des clients du realm (id, clientId) pour résoudre clientId -> UUID."""
    try:
        r = requests.get(
            f"{base_url}/admin/realms/{realm}/clients",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def fetch_user_sessions_page(
    base_url: str, realm: str, client_uuid: str, token: str, first: int, max_count: int
) -> Optional[List[dict]]:
    try:
        r = requests.get(
            f"{base_url}/admin/realms/{realm}/clients/{client_uuid}/user-sessions",
            params={"first": first, "max": max_count},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def fetch_events(
    base_url: str, realm: str, token: str, event_type: str = "LOGIN", max_events: int = 20
) -> Optional[List[dict]]:
    """Derniers événements (ex. LOGIN). Tri décroissant par time."""
    try:
        r = requests.get(
            f"{base_url}/admin/realms/{realm}/events",
            params={"type": event_type, "max": max_events, "orderBy": "time", "sortOrder": "desc"},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def fetch_user(base_url: str, realm: str, token: str, user_id: str) -> Optional[dict]:
    """Détails d'un utilisateur (username, email)."""
    try:
        r = requests.get(
            f"{base_url}/admin/realms/{realm}/users/{user_id}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=5,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def collect_distinct_user_ids(
    base_url: str,
    realm: str,
    token: str,
    client_id_to_uuid: dict,
    client_id_to_count: dict,
) -> set:
    """client_id_to_count: {clientId: count}. client_id_to_uuid: {clientId: uuid}."""
    user_ids = set()
    for client_id, count in client_id_to_count.items():
        if (count or 0) <= 0:
            continue
        client_uuid = client_id_to_uuid.get(client_id)
        if not client_uuid:
            continue
        first = 0
        while True:
            page = fetch_user_sessions_page(
                base_url, realm, client_uuid, token, first, USER_SESSIONS_PAGE_SIZE
            )
            if not page:
                break
            for sess in page:
                uid = sess.get("userId")
                if uid:
                    user_ids.add(uid)
            if len(page) < USER_SESSIONS_PAGE_SIZE:
                break
            first += USER_SESSIONS_PAGE_SIZE
    return user_ids


def collect_sessions_with_duration(
    base_url: str,
    realm: str,
    token: str,
    client_id_to_uuid: dict,
    client_id_to_count: dict,
) -> List[tuple]:
    """Retourne au plus MAX_SESSION_DURATION_SERIES (user_id, username, start_ms). start en ms depuis epoch."""
    result = []
    seen = set()
    for client_id, count in client_id_to_count.items():
        if (count or 0) <= 0 or len(result) >= MAX_SESSION_DURATION_SERIES:
            continue
        client_uuid = client_id_to_uuid.get(client_id)
        if not client_uuid:
            continue
        first = 0
        while len(result) < MAX_SESSION_DURATION_SERIES:
            page = fetch_user_sessions_page(
                base_url, realm, client_uuid, token, first, USER_SESSIONS_PAGE_SIZE
            )
            if not page:
                break
            for sess in page:
                if len(result) >= MAX_SESSION_DURATION_SERIES:
                    break
                uid = sess.get("userId")
                start_ms = sess.get("start")
                if not uid or start_ms is None:
                    continue
                key = (uid, start_ms)
                if key in seen:
                    continue
                seen.add(key)
                username = (sess.get("username") or "").strip() or uid[:8]
                result.append((uid, _sanitize_label(username), int(start_ms)))
            if len(page) < USER_SESSIONS_PAGE_SIZE:
                break
            first += USER_SESSIONS_PAGE_SIZE
    return result


def _sanitize_label(s: str, max_len: int = 80) -> str:
    """Pour labels Prometheus : pas de guillemets, backslash, newline."""
    if not s:
        return "unknown"
    s = str(s).replace("\\", "_").replace('"', "'").replace("\n", " ").replace("\r", " ").strip()
    return s[:max_len] if len(s) > max_len else s


def _normalize_session_stats(stats, clients_list: Optional[List[dict]]):
    """
    Retourne (client_id_to_count: dict, client_id_to_uuid: dict).
    stats peut être un dict {clientId: count} (Keycloak récent) ou une list [{id, clientId, active}].
    """
    client_id_to_count = {}
    client_id_to_uuid = {}
    if clients_list:
        for c in clients_list:
            cid = c.get("clientId")
            uid = c.get("id")
            if cid is not None and uid:
                client_id_to_uuid[cid] = uid

    if isinstance(stats, dict):
        for client_id, count in stats.items():
            if client_id is not None:
                client_id_to_count[client_id] = int(count) if count is not None else 0
    elif isinstance(stats, list):
        for entry in stats:
            client_id = entry.get("clientId")
            active = int(entry.get("active") or 0)
            uuid_val = entry.get("id")
            if client_id is not None:
                client_id_to_count[client_id] = active
                if uuid_val:
                    client_id_to_uuid[client_id] = uuid_val
    return client_id_to_count, client_id_to_uuid


def escape_prometheus_label(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _fallback_metrics() -> str:
    """Métriques de secours en cas d'erreur (pour que Prometheus reçoive toujours des séries)."""
    return (
        "keycloak_session_exporter_up 0\n"
        "keycloak_sessions_total{client_id=\"unknown\"} 0\n"
        "keycloak_distinct_users_connected 0\n"
    )


def render_metrics(
    base_url: str,
    realm: str,
    admin_user: str,
    admin_pass: str,
) -> str:
    """Retourne le texte Prometheus (toujours valide)."""
    try:
        token = get_admin_token(base_url, admin_user, admin_pass)
        if not token:
            return _fallback_metrics()

        stats = fetch_client_session_stats(base_url, realm, token)
        if stats is None:
            return _fallback_metrics()

        clients_list = fetch_clients(base_url, realm, token)
        client_id_to_count, client_id_to_uuid = _normalize_session_stats(stats, clients_list)

        lines = ["keycloak_session_exporter_up 1"]
        if not client_id_to_count:
            lines.append('keycloak_sessions_total{client_id="none"} 0')
        for client_id, count in client_id_to_count.items():
            label = escape_prometheus_label(client_id)
            lines.append(f'keycloak_sessions_total{{client_id="{label}"}} {count}')

        distinct = collect_distinct_user_ids(
            base_url, realm, token, client_id_to_uuid, client_id_to_count
        )
        lines.append(f"keycloak_distinct_users_connected {len(distinct)}")

        # Durée de session par utilisateur (connectés)
        now_ms = int(time.time() * 1000)
        sessions_with_start = collect_sessions_with_duration(
            base_url, realm, token, client_id_to_uuid, client_id_to_count
        )
        for user_id, username, start_ms in sessions_with_start:
            duration_sec = max(0, (now_ms - start_ms) / 1000.0)
            uid_label = escape_prometheus_label(_sanitize_label(user_id, 36))
            un_label = escape_prometheus_label(username)
            lines.append(
                f'keycloak_session_duration_seconds{{user_id="{uid_label}",username="{un_label}"}} {duration_sec:.1f}'
            )

        # Dernières connexions (événements LOGIN) avec enrichissement user (username, email)
        events = fetch_events(base_url, realm, token, "LOGIN", MAX_LAST_LOGIN_EVENTS)
        if events:
            for evt in events:
                evt_time = evt.get("time")
                user_id = evt.get("userId")
                if evt_time is None or not user_id:
                    continue
                ts_sec = int(evt_time) / 1000
                user = fetch_user(base_url, realm, token, user_id)
                username = "unknown"
                email = ""
                if user:
                    username = _sanitize_label(user.get("username") or user_id[:8])
                    email = _sanitize_label(user.get("email") or "", 60)
                uid_label = escape_prometheus_label(_sanitize_label(user_id, 36))
                un_label = escape_prometheus_label(username)
                em_label = escape_prometheus_label(email)
                lines.append(
                    f'keycloak_last_login_timestamp_seconds{{user_id="{uid_label}",username="{un_label}",email="{em_label}"}} {ts_sec}'
                )

        return "\n".join(lines) + "\n"
    except Exception as e:
        print(f"keycloak_session_exporter: error: {e}", file=sys.stderr)
        return _fallback_metrics()


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/metrics":
            base = os.environ.get("KEYCLOAK_URL", DEFAULT_URL).rstrip("/")
            realm = os.environ.get("KEYCLOAK_REALM", DEFAULT_REALM)
            admin_user = os.environ.get("KEYCLOAK_ADMIN_USER", DEFAULT_ADMIN)
            admin_pass = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", DEFAULT_ADMIN_PASS)
            body = render_metrics(base, realm, admin_user, admin_pass)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
        elif parsed.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def main():
    port = int(os.environ.get("EXPORTER_PORT", str(EXPORTER_PORT)))
    server = HTTPServer(("0.0.0.0", port), MetricsHandler)
    print(f"Keycloak session exporter listening on 0.0.0.0:{port}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
