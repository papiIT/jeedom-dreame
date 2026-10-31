"""Préparation des tests : on remplace la bibliothèque de protocole cloud par un faux module.

Ainsi les tests n'ont besoin ni des dépendances cryptographiques ni d'un compte Dreame :
ils vérifient la logique du démon (libellés, lots de requêtes, réglages, ordres, sécurité).
"""
import os
import sys
import types

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DAEMON_DIR = os.path.join(ROOT, "resources", "dreamed")


class FakeCloud:
    """Simule la partie « compte » du protocole (connexion, liste des appareils)."""

    def __init__(self, *args, login_ok=True, devices=None, **kwargs):
        self.args = args
        self.login_ok = login_ok
        self.devices = devices or {}
        self._secondary_key = "refresh-token-123"
        self.disconnected = False

    def login(self):
        return self.login_ok

    def get_devices(self):
        return self.devices

    def disconnect(self):
        self.disconnected = True


class FakeProtocol:
    """Simule la session d'un robot : propriétés en mémoire, actions et écritures enregistrées."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.cloud = FakeCloud()
        self.store = {}            # (siid, piid) -> valeur
        self.actions = []          # [(siid, aiid, params)]
        self.writes = []           # [(siid, piid, value)]
        self.requests = []         # tailles des lots de get_properties
        self.action_result = {"code": 0}
        self.write_code = 0
        self.connected_with = None

    def connect(self, message_callback=None, connected_callback=None):
        self.connected_with = message_callback
        return {"model": "dreame.vacuum.test"}

    def disconnect(self):
        pass

    def get_properties(self, req):
        self.requests.append(len(req))
        out = []
        for item in req:
            key = (item["siid"], item["piid"])
            if key in self.store:
                out.append({"did": item["did"], "siid": key[0], "piid": key[1], "code": 0, "value": self.store[key]})
            else:
                out.append({"did": item["did"], "siid": key[0], "piid": key[1], "code": -4001})
        return out

    def action(self, siid, aiid, params=None):
        self.actions.append((siid, aiid, params))
        return self.action_result

    def set_property(self, siid, piid, value):
        self.writes.append((siid, piid, value))
        if self.write_code == 0:
            self.store[(siid, piid)] = value
        return [{"did": "x", "siid": siid, "piid": piid, "code": self.write_code}]


# Faux paquet « dreame.protocol » injecté avant l'import du démon
_pkg = types.ModuleType("dreame")
_pkg.__path__ = []
_proto = types.ModuleType("dreame.protocol")
_proto.DreameVacuumProtocol = FakeProtocol
_proto.DreameVacuumDreameHomeCloudProtocol = FakeCloud
sys.modules["dreame"] = _pkg
sys.modules["dreame.protocol"] = _proto
sys.path.insert(0, DAEMON_DIR)

import dreamed  # noqa: E402


class RecordingJeedom:
    """Remplace le lien HTTP vers Jeedom : enregistre les évènements envoyés."""

    def __init__(self, config=None):
        self.sent = []
        self.config = config

    def send(self, payload, timeout=15):
        self.sent.append(payload)
        if payload.get("action") == "config":
            return self.config
        return {"ok": True}

    def of(self, action):
        return [p for p in self.sent if p.get("action") == action]


@pytest.fixture
def jeedom():
    return RecordingJeedom(config={
        "username": "user@example.com", "password": "secret", "country": "eu", "refresh_token": "",
        "cycle": 60, "devices": [{"did": "123", "name": "Totor", "enabled": True},
                                 {"did": "456", "name": "Off", "enabled": False}],
    })


@pytest.fixture
def daemon(jeedom):
    args = types.SimpleNamespace(apikey="KEY", callback="http://x", socketport=0, pid="/tmp/x", loglevel="error")
    d = dreamed.Daemon(args, jeedom=jeedom, robot_factory=lambda dm, did, name: dreamed.Robot(dm, did, name, protocol_factory=FakeProtocol),
                       cloud_factory=FakeCloud)
    d.config = jeedom.config
    return d


@pytest.fixture
def robot(daemon):
    r = dreamed.Robot(daemon, "123", "Totor", protocol_factory=FakeProtocol)
    r.proto = FakeProtocol()
    return r
