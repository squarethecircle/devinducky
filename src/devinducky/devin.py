"""Thin client for the Devin v3 API (only the calls devinducky needs)."""

import httpx

BASE_URL = "https://api.devin.ai"


class DevinError(Exception):
    def __init__(self, status, message):
        super().__init__(f"{status}: {message}")
        self.status = status


class Devin:
    def __init__(self, api_key, base_url=BASE_URL, timeout=15):
        self.http = httpx.Client(base_url=base_url, timeout=timeout,
                                 headers={"Authorization": f"Bearer {api_key}"})
        self.org_id = None
        self.user_id = None

    def _req(self, method, path, **kw):
        try:
            r = self.http.request(method, path, **kw)
        except httpx.HTTPError as e:
            raise DevinError(0, str(e)) from e
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail", r.text)
            except ValueError:
                detail = r.text
            raise DevinError(r.status_code, str(detail)[:300])
        return r.json() if r.content else None

    def _org(self, path):
        return f"/v3/organizations/{self.org_id}{path}"

    def whoami(self):
        me = self._req("GET", "/v3/self")
        self.org_id = me.get("org_id") or me.get("devin_sessions_org_id")
        self.user_id = me.get("user_id")
        return me

    def get_session(self, devin_id):
        return self._req("GET", self._org(f"/sessions/{devin_id}"))

    def list_sessions(self, session_ids):
        """Sessions by ID (one request for up to 200)."""
        if not session_ids:
            return []
        params = [("session_ids", sid) for sid in session_ids] + [("first", 200)]
        return self._req("GET", self._org("/sessions"), params=params).get("items", [])

    def create_session(self, preset):
        body = {k: preset[k] for k in
                ("prompt", "playbook_id", "repos", "title", "devin_mode", "max_acu_limit")
                if preset.get(k) is not None}
        body["tags"] = sorted(set(preset.get("tags", [])) | {"devinducky"})
        return self._req("POST", self._org("/sessions"), json=body)

    def list_playbooks(self):
        res = self._req("GET", self._org("/playbooks"))
        return res.get("items", res) if isinstance(res, dict) else res
