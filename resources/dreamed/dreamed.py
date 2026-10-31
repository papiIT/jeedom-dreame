#!/usr/bin/env python3
# This file is part of the Jeedom "dreame" plugin.
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU Affero General Public License as published by the Free Software Foundation, either version 3
# of the License, or (at your option) any later version.
"""Démon Jeedom pour les robots aspirateurs Dreame (cloud Dreamehome).

Fonctionnement général
----------------------
* Au démarrage, le démon demande sa configuration à Jeedom (compte, région, robots activés)
  via l'URL de rappel ``core/php/jeedreame.php``.
* Pour chaque robot il ouvre une session cloud (protocole fourni par le projet open source
  Tasshack/dreame-vacuum, embarqué dans ``dreame/``), reçoit les changements poussés en temps
  réel (MQTT du cloud) et interroge le robot périodiquement en secours.
* Jeedom lui envoie des ordres sur un socket TCP local (un objet JSON par ligne, protégé par la
  clé API du plugin) : découverte, rechargement, commande, réglage, rafraîchissement.
* Toutes les valeurs remontées sont renvoyées à Jeedom avec leurs libellés en français.

Le module est importable sans effet de bord (pour les tests unitaires) : rien ne démarre tant
que ``main()`` n'est pas appelé.
"""
import argparse
import json
import logging
import os
import signal
import socketserver
import sys
import threading
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dreame.protocol import DreameVacuumDreameHomeCloudProtocol, DreameVacuumProtocol  # noqa: E402

LOG = logging.getLogger("dreamed")

# --------------------------------------------------------------------------------------------
# Correspondance MIoT : propriété -> (siid, piid)
# Les numéros viennent de la spécification MIoT des robots Dreame (cf. projet Tasshack).
# --------------------------------------------------------------------------------------------
PROPS = {
    "state": (2, 1),
    "error": (2, 2),
    "battery": (3, 1),
    "charging_status": (3, 2),
    "status": (4, 1),
    "cleaning_time": (4, 2),
    "cleaned_area": (4, 3),
    "suction_level": (4, 4),
    "water_volume": (4, 5),
    "task_status": (4, 7),
    "carpet_boost": (4, 12),
    "cleaning_mode": (4, 23),
    "self_wash_base_status": (4, 25),
    "child_lock": (4, 27),
    "dnd": (5, 1),
    "volume": (7, 1),
    "main_brush_time_left": (9, 1),
    "main_brush_left": (9, 2),
    "side_brush_time_left": (10, 1),
    "side_brush_left": (10, 2),
    "filter_left": (11, 1),
    "filter_time_left": (11, 2),
    "dust_collection": (15, 3),
    "auto_empty_status": (15, 5),
    "sensor_dirty_left": (16, 1),
    "sensor_dirty_time_left": (16, 2),
    "mop_pad_left": (18, 1),
    "mop_pad_time_left": (18, 2),
    "silver_ion_time_left": (19, 1),
    "silver_ion_left": (19, 2),
    "detergent_left": (20, 1),
    "detergent_time_left": (20, 2),
    "squeegee_time_left": (24, 1),
    "squeegee_left": (24, 2),
    "clean_water_tank_status": (27, 1),
    "dirty_water_tank_status": (27, 2),
    "dust_bag_status": (27, 3),
}
BY_SIID_PIID = {v: k for k, v in PROPS.items()}

# Actions MIoT : nom -> (siid, aiid, paramètres "in")
ACTIONS = {
    "start": (2, 1, None),
    "pause": (2, 2, None),
    "stop": (4, 2, None),
    "dock": (3, 1, None),
    "locate": (7, 1, None),
    "auto_empty": (15, 1, None),
    # Station de lavage : action 4.4 avec la propriété 4.10 "type,état"
    # (2,1 = lavage, 3,1 = séchage marche, 3,0 = séchage arrêt).
    "wash_mop": (4, 4, [{"piid": 10, "value": "2,1"}]),
    "dry_start": (4, 4, [{"piid": 10, "value": "3,1"}]),
    "dry_stop": (4, 4, [{"piid": 10, "value": "3,0"}]),
    "reset_main_brush": (9, 1, None),
    "reset_side_brush": (10, 1, None),
    "reset_filter": (11, 1, None),
    "reset_sensor": (16, 1, None),
    "reset_mop_pad": (18, 1, None),
    "reset_silver_ion": (19, 1, None),
    "reset_detergent": (20, 1, None),
    "reset_squeegee": (24, 1, None),
}

# Réglages modifiables : nom -> (valeurs autorisées ou (min, max), type de la valeur à écrire)
SETTINGS = {
    "suction_level": ((0, 1, 2, 3), int),
    "water_volume": ((1, 2, 3), int),
    "cleaning_mode": ((0, 1, 2), int),
    "carpet_boost": ((0, 1), int),
    "child_lock": ((0, 1), int),
    "dnd": ((0, 1), bool),
    "volume": ((0, 100), int),        # plage min/max
}
RANGE_SETTINGS = {"volume"}

# --------------------------------------------------------------------------------------------
# Libellés (français)
# --------------------------------------------------------------------------------------------
STATE_LABELS = {
    1: "Aspiration", 2: "Inactif", 3: "En pause", 4: "Erreur", 5: "Retour à la base",
    6: "En charge", 7: "Lavage du sol", 8: "Séchage des serpillières", 9: "Lavage des serpillières",
    10: "Retour pour lavage", 11: "Cartographie", 12: "Aspiration et lavage", 13: "Charge terminée",
    14: "Mise à jour", 15: "Nettoyage à la demande", 16: "Réinitialisation station",
    17: "Retour pour installer serpillières", 18: "Retour pour retirer serpillières",
    19: "Vérification de l'eau", 20: "Ajout d'eau", 21: "Lavage en pause", 22: "Vidage automatique",
    23: "Télécommande", 24: "Charge intelligente", 25: "Second passage", 26: "Suivi de personne",
    27: "Nettoyage localisé", 28: "Retour pour vidage", 29: "En attente de tâche",
    30: "Nettoyage de la station", 31: "Retour pour vidange", 32: "Vidange", 33: "Vidange automatique",
    34: "Vidage", 35: "Séchage du sac", 36: "Séchage du sac en pause", 37: "Vers nettoyage supplémentaire",
    38: "Nettoyage supplémentaire", 97: "Raccourci", 98: "Surveillance", 99: "Surveillance en pause",
    101: "Nettoyage approfondi initial", 102: "Nettoyage approfondi en pause", 103: "Désinfection",
    104: "Désinfection et séchage", 105: "Changement de serpillières", 106: "Changement de serpillières en pause",
    107: "Entretien du sol", 108: "Entretien du sol en pause", 116: "Installation serpillières",
    117: "Retrait serpillières", 118: "Recharge intelligente", 120: "Nettoyage assisté",
    121: "Entrée dans la base", 122: "Sortie de la base",
}
# États considérés comme "en nettoyage" (commande binaire « En nettoyage »)
CLEANING_STATES = {1, 7, 11, 12, 15, 25, 27, 37, 38, 101, 107}
# États où le robot bouge : on interroge alors plus souvent
ACTIVE_STATES = CLEANING_STATES | {5, 9, 10, 22, 28}
CHARGING_LABELS = {1: "En charge", 2: "Pas en charge", 3: "Charge terminée", 5: "Retour à la base"}
SELF_WASH_LABELS = {
    0: "Inactive", 1: "Lavage", 2: "Séchage", 3: "Retour à la base", 4: "En pause",
    5: "Ajout d'eau (nettoyage)", 6: "Ajout d'eau", 7: "Retour pour séchage",
}
AUTO_EMPTY_LABELS = {0: "Inactif", 1: "Vidage en cours", 2: "Non effectué"}
CLEAN_WATER_LABELS = {0: "OK", 1: "Absent", 2: "Niveau bas", 3: "Vérification"}
DIRTY_WATER_LABELS = {0: "OK", 1: "Absent ou plein"}
DUST_BAG_LABELS = {0: "OK", 1: "Absent", 2: "À vérifier"}
SUCTION_LABELS = {0: "Silencieux", 1: "Standard", 2: "Turbo", 3: "Max"}
WATER_LABELS = {1: "Faible", 2: "Moyen", 3: "Élevé"}
CLEANING_MODE_LABELS = {0: "Aspiration", 1: "Lavage", 2: "Aspiration et lavage", 3: "Lavage après aspiration"}
ERROR_LABELS = {
    0: "Aucune", 1: "Roue suspendue", 2: "Capteur de vide", 3: "Pare-chocs bloqué", 8: "Bac à poussière absent",
    9: "Réservoir absent", 10: "Réservoir d'eau vide", 11: "Bac à poussière plein", 12: "Brosse principale bloquée",
    13: "Brosse latérale bloquée", 14: "Filtre / ventilateur", 15: "Roue gauche", 16: "Roue droite",
    17: "Robot coincé", 18: "Robot coincé", 19: "Base introuvable", 20: "Batterie faible", 21: "Erreur de charge",
    24: "Caméra obstruée", 47: "Robot bloqué", 48: "Erreur du laser (LDS)", 51: "Filtre bloqué",
    59: "Zone interdite", 61: "Itinéraire impossible", 68: "Retirer les serpillières",
    69: "Serpillières retirées", 75: "Batterie faible, arrêt", 76: "Réservoir d'eau sale absent",
    80: "Robot coincé", 82: "Sol glissant", 85: "Vérifier l'installation des serpillières",
    86: "Réservoir d'eau sale plein", 101: "Bac plein", 102: "Bac ouvert", 105: "Réservoir d'eau propre",
    106: "Réservoir d'eau sale", 107: "Réservoir d'eau propre vide", 108: "Réservoir d'eau sale",
    109: "Réservoir d'eau sale bouché", 110: "Pompe d'eau sale", 111: "Serpillière", 114: "Nettoyer les serpillières",
    116: "Niveau d'eau propre bas", 117: "Station déconnectée", 118: "Niveau d'eau sale", 119: "Plateau de lavage",
    120: "Pas de serpillières dans la station", 121: "Sac à poussière plein", 125: "Vidange échouée",
    126: "Serpillière non détectée", 128: "Erreur de la station", 129: "Lavage échoué",
    213: "Réservoir embarqué vide", 214: "Réservoir d'eau sale embarqué plein", 215: "Serpillière non installée",
    226: "Bloqué par un obstacle", 1000: "Retour à la base impossible",
}


# --------------------------------------------------------------------------------------------
# Mode de nettoyage : encodage composite des modèles récents
# --------------------------------------------------------------------------------------------
def decode_cleaning_mode(raw):
    """Convertit la valeur brute de la propriété 4.23 en mode (0 aspiration, 1 lavage, 2 les deux).

    Les modèles avec station de lavage et serpillières relevables (L10s, L20, L40...) regroupent
    plusieurs réglages dans un entier : seuls les 2 bits de poids faible portent le mode, avec
    0 et 2 inversés par rapport à la numérotation logique. Les modèles simples renvoient
    directement 0, 1 ou 2.
    """
    if raw is None:
        return None
    raw = int(raw)
    if raw > 3:                       # encodage groupé
        low = raw & 0x03
        return {0: 2, 2: 0}.get(low, low)
    return raw


def encode_cleaning_mode(current_raw, mode):
    """Calcule la valeur brute à écrire pour obtenir ``mode`` sans écraser les autres réglages."""
    mode = int(mode)
    if current_raw is not None and int(current_raw) > 3:
        low = {2: 0, 0: 2}.get(mode, mode)
        return (int(current_raw) & ~0x03) | low
    return mode


def to_number(value):
    """Normalise les booléens renvoyés par le cloud (True/False) en 1/0 pour Jeedom."""
    if isinstance(value, bool):
        return 1 if value else 0
    return value


def labels_for(values):
    """Calcule les commandes « lisibles » (libellés, binaires) à partir des valeurs brutes reçues.

    Seules les clés présentes dans ``values`` sont traitées, ce qui permet de l'utiliser aussi bien
    sur un rafraîchissement complet que sur un changement poussé partiel.
    """
    out = {}
    if "state" in values:
        s = values["state"]
        out["state_label"] = STATE_LABELS.get(s, f"État {s}")
        out["cleaning"] = 1 if s in CLEANING_STATES else 0
    if "error" in values:
        e = values["error"]
        out["error_label"] = ERROR_LABELS.get(e, f"Erreur {e}")
    if "charging_status" in values:
        c = values["charging_status"]
        out["charging_label"] = CHARGING_LABELS.get(c, str(c))
        out["docked"] = 1 if c in (1, 3) else 0
    for key, table, name in (
        ("self_wash_base_status", SELF_WASH_LABELS, "self_wash_label"),
        ("auto_empty_status", AUTO_EMPTY_LABELS, "auto_empty_label"),
        ("clean_water_tank_status", CLEAN_WATER_LABELS, "clean_water_label"),
        ("dirty_water_tank_status", DIRTY_WATER_LABELS, "dirty_water_label"),
        ("dust_bag_status", DUST_BAG_LABELS, "dust_bag_label"),
        ("suction_level", SUCTION_LABELS, "suction_label"),
        ("water_volume", WATER_LABELS, "water_label"),
        ("cleaning_mode", CLEANING_MODE_LABELS, "cleaning_mode_label"),
    ):
        if key in values and values[key] is not None:
            out[name] = table.get(values[key], str(values[key]))
    return out


# --------------------------------------------------------------------------------------------
# Lien avec Jeedom
# --------------------------------------------------------------------------------------------
class Jeedom:
    """Envoie les évènements du démon à Jeedom (POST JSON sur l'URL de rappel)."""

    def __init__(self, callback, apikey, session=None):
        self.callback = callback
        self.apikey = apikey
        self.session = session or requests

    def send(self, payload, timeout=15):
        """Retourne la réponse JSON de Jeedom, ou None en cas d'échec (jamais d'exception)."""
        try:
            r = self.session.post(self.callback, params={"apikey": self.apikey}, json=payload, timeout=timeout)
            r.raise_for_status()
            return r.json() if r.content else None
        except Exception as ex:  # réseau, HTTP, JSON : on journalise et on continue
            LOG.error("Callback to Jeedom failed (%s): %s", payload.get("action"), ex)
            return None


# --------------------------------------------------------------------------------------------
# Un robot
# --------------------------------------------------------------------------------------------
class Robot:
    """Session cloud d'un robot : connexion, lecture, actions, réglages, messages poussés."""

    BATCH = 15  # le cloud Dreame accepte au plus ~15 propriétés par requête

    def __init__(self, daemon, did, name, protocol_factory=DreameVacuumProtocol):
        self.daemon = daemon
        self.did = str(did)
        self.name = name
        self.protocol_factory = protocol_factory
        self.proto = None
        self.lock = threading.RLock()     # le protocole n'est pas prévu pour des appels concurrents
        self.supported = None             # propriétés réellement exposées par ce modèle
        self.values = {}                  # dernières valeurs brutes connues
        self.online = None
        self.next_poll = 0
        self.fail_count = 0

    # -- connexion ---------------------------------------------------------------------------
    def connect(self):
        cfg = self.daemon.config
        LOG.info("[%s] Connecting to Dreame cloud (%s)", self.name, cfg["country"])
        proto = self.protocol_factory(
            username=cfg["username"],
            password=cfg["password"],
            country=cfg["country"],
            account_type="dreame",
            device_id=self.did,
            auth_key=cfg.get("refresh_token") or None,
        )
        if not proto.cloud.login():
            raise RuntimeError("login failed (check account / password / region)")
        # le jeton de rafraîchissement évite de renvoyer le mot de passe à chaque redémarrage
        self.daemon.save_token(proto.cloud._secondary_key)
        info = proto.connect(self.on_message, lambda *a: None)
        if not info:
            raise RuntimeError("robot not found on this account")
        self.proto = proto
        LOG.info("[%s] Connected (model %s)", self.name, info.get("model"))
        if self.supported is None:
            self.probe()

    def disconnect(self):
        if self.proto:
            try:
                self.proto.disconnect()
            except Exception:
                pass
        self.proto = None

    def set_online(self, online):
        """Met à jour la commande « En ligne » seulement quand l'état change."""
        if online != self.online:
            self.online = online
            self.daemon.jeedom.send({"action": "update", "did": self.did, "values": {"online": 1 if online else 0}})

    # -- lecture des propriétés --------------------------------------------------------------
    def _get(self, keys):
        """Lit les propriétés demandées par lots ; ignore celles que le robot ne connaît pas."""
        result = {}
        keys = list(keys)
        for i in range(0, len(keys), self.BATCH):
            batch = keys[i:i + self.BATCH]
            req = [{"did": k, "siid": PROPS[k][0], "piid": PROPS[k][1]} for k in batch]
            with self.lock:
                resp = self.proto.get_properties(req)
            for item in resp or []:
                if item.get("code") == 0 and item.get("did") in PROPS and "value" in item:
                    result[item["did"]] = item["value"]
        return result

    def probe(self):
        """Première lecture complète : détermine les propriétés supportées par le modèle."""
        values = self._get(PROPS.keys())
        self.supported = sorted(values.keys())
        LOG.info("[%s] Supported properties: %s", self.name, ", ".join(self.supported))
        self.daemon.jeedom.send({"action": "supported", "did": self.did, "props": self.supported})
        self.publish(values)

    def poll(self):
        keys = self.supported or list(PROPS.keys())
        self.publish(self._get(keys))

    def publish(self, values):
        """Envoie à Jeedom les valeurs reçues (normalisées) et leurs libellés."""
        if not values:
            return
        self.values.update(values)
        payload = {k: to_number(v) for k, v in values.items()}
        if "cleaning_mode" in payload:
            payload["cleaning_mode"] = decode_cleaning_mode(payload["cleaning_mode"])
        payload.update(labels_for(payload))
        payload["last_update"] = time.strftime("%Y-%m-%d %H:%M:%S")
        LOG.debug("[%s] Update %s", self.name, payload)
        self.daemon.jeedom.send({"action": "update", "did": self.did, "values": payload})

    def on_message(self, message):
        """Message poussé par le cloud : ``{"method": "properties_changed", "params": [...]}``."""
        try:
            if message.get("method") != "properties_changed":
                return
            values = {}
            for p in message.get("params", []):
                key = BY_SIID_PIID.get((p.get("siid"), p.get("piid")))
                if key and "value" in p:
                    values[key] = p["value"]
            if values:
                LOG.debug("[%s] Pushed %s", self.name, values)
                self.publish(values)
        except Exception:
            LOG.exception("[%s] Error while handling pushed message", self.name)

    # -- actions et réglages -----------------------------------------------------------------
    def action(self, name):
        if name not in ACTIONS:
            raise ValueError(f"unknown command {name}")
        siid, aiid, params = ACTIONS[name]
        LOG.info("[%s] Action %s (%s.%s %s)", self.name, name, siid, aiid, params or "")
        with self.lock:
            resp = self.proto.action(siid, aiid, params)
        if not resp or resp.get("code") != 0:
            raise RuntimeError(f"robot refused {name}: {resp}")
        self.next_poll = time.time() + 3   # relecture rapide pour refléter le nouvel état

    def set_setting(self, name, value):
        """Écrit un réglage après validation de la valeur."""
        if name not in SETTINGS:
            raise ValueError(f"unknown setting {name}")
        allowed, cast = SETTINGS[name]
        try:
            value = int(float(value))
        except (TypeError, ValueError):
            raise ValueError(f"invalid value {value!r} for {name}")
        if name in RANGE_SETTINGS:
            if not allowed[0] <= value <= allowed[1]:
                raise ValueError(f"{name} must be between {allowed[0]} and {allowed[1]}")
        elif value not in allowed:
            raise ValueError(f"{name} must be one of {allowed}")
        raw = value
        if name == "cleaning_mode":
            raw = encode_cleaning_mode(self.values.get("cleaning_mode"), value)
        siid, piid = PROPS[name]
        LOG.info("[%s] Set %s = %s (raw %s)", self.name, name, value, raw)
        with self.lock:
            resp = self.proto.set_property(siid, piid, cast(raw))
        ok = isinstance(resp, list) and resp and resp[0].get("code") == 0
        if not ok:
            raise RuntimeError(f"robot refused {name}={value}: {resp}")
        self.next_poll = time.time() + 2

    @property
    def active(self):
        return self.values.get("state") in ACTIVE_STATES


# --------------------------------------------------------------------------------------------
# Le démon
# --------------------------------------------------------------------------------------------
class Daemon:
    """Orchestration : configuration, découverte, boucle d'interrogation, ordres reçus."""

    def __init__(self, args, jeedom=None, robot_factory=Robot, cloud_factory=DreameVacuumDreameHomeCloudProtocol):
        self.args = args
        self.jeedom = jeedom or Jeedom(args.callback, args.apikey)
        self.robot_factory = robot_factory
        self.cloud_factory = cloud_factory
        self.config = {}
        self.robots = {}
        self.stop_event = threading.Event()
        self.reload_event = threading.Event()

    def save_token(self, token):
        """Mémorise (dans Jeedom, chiffré) le jeton de rafraîchissement s'il a changé."""
        if token and token != self.config.get("refresh_token"):
            self.config["refresh_token"] = token
            self.jeedom.send({"action": "token", "token": token})

    def load_config(self, retry_delay=10):
        """Récupère la configuration auprès de Jeedom (réessaie tant que Jeedom ne répond pas)."""
        cfg = None
        while cfg is None and not self.stop_event.is_set():
            cfg = self.jeedom.send({"action": "config"})
            if cfg is None:
                self.stop_event.wait(retry_delay)
        if cfg is None:
            return
        self.config = cfg
        for r in self.robots.values():
            r.disconnect()
        self.robots = {
            str(d["did"]): self.robot_factory(self, d["did"], d.get("name") or d["did"])
            for d in cfg.get("devices", []) if d.get("enabled")
        }
        LOG.info("Configuration loaded: %d robot(s)", len(self.robots))

    def discover(self):
        """Liste les robots du compte et les envoie à Jeedom (qui crée les équipements)."""
        cfg = self.config
        if not cfg.get("username") or not cfg.get("password"):
            self.jeedom.send({"action": "message", "level": "error", "message": "Identifiants Dreamehome non configurés"})
            return
        cloud = self.cloud_factory(cfg["username"], cfg["password"], "dreame", cfg["country"], cfg.get("refresh_token") or None)
        if not cloud.login():
            self.jeedom.send({"action": "message", "level": "error",
                              "message": "Connexion au compte Dreamehome impossible (identifiants ou région ?)"})
            return
        self.save_token(cloud._secondary_key)
        data = cloud.get_devices() or {}
        devices = []
        for d in data.get("page", {}).get("records", []):
            model = d.get("model", "")
            if ".vacuum." not in model:      # on ignore les autres appareils du compte
                continue
            name = d.get("customName") or (d.get("deviceInfo") or {}).get("displayName") or model
            devices.append({"did": str(d.get("did")), "name": name, "model": model, "mac": d.get("mac"),
                            "online": d.get("online")})
        LOG.info("Discovered %d robot(s): %s", len(devices), [x["name"] for x in devices])
        self.jeedom.send({"action": "devices", "devices": devices})
        try:
            cloud.disconnect()
        except Exception:
            pass

    def handle(self, msg):
        """Traite un ordre reçu de Jeedom."""
        action = msg.get("action")
        if action == "discover":
            self.discover()
        elif action == "reload":
            self.reload_event.set()
        elif action in ("cmd", "refresh", "set"):
            robot = self.robots.get(str(msg.get("did")))
            if robot is None or robot.proto is None:
                self.jeedom.send({"action": "message", "level": "warning", "message": "Robot non connecté, commande ignorée"})
                return
            if action == "refresh":
                robot.next_poll = 0
            elif action == "set":
                robot.set_setting(msg["setting"], msg.get("value"))
            else:
                robot.action(msg["cmd"])
        else:
            LOG.warning("Unknown order %s", action)

    def cycle(self):
        """Un tour de boucle : (re)connecte et interroge les robots dont c'est le tour."""
        now = time.time()
        for robot in list(self.robots.values()):
            if robot.next_poll > now:
                continue
            try:
                if robot.proto is None:
                    robot.connect()
                robot.poll()
                robot.fail_count = 0
                robot.set_online(True)
                interval = 15 if robot.active else int(self.config.get("cycle") or 60)
                robot.next_poll = time.time() + interval
            except Exception as ex:
                # échec : on coupe la session et on réessaie avec un délai croissant (max 10 min)
                robot.fail_count += 1
                delay = min(30 * robot.fail_count, 600)
                LOG.warning("[%s] %s (retry in %ss)", robot.name, ex, delay)
                robot.set_online(False)
                robot.disconnect()
                robot.next_poll = time.time() + delay

    def loop(self):
        self.load_config()
        while not self.stop_event.is_set():
            if self.reload_event.is_set():
                self.reload_event.clear()
                self.load_config()
            self.cycle()
            self.stop_event.wait(1)
        for r in self.robots.values():
            r.disconnect()


class SocketHandler(socketserver.StreamRequestHandler):
    """Réception des ordres de Jeedom : une ligne JSON par ordre, clé API obligatoire."""

    def handle(self):
        daemon = self.server.daemon
        for raw in self.rfile:
            try:
                msg = json.loads(raw.decode("utf-8"))
            except ValueError:
                LOG.error("Invalid message on socket")
                continue
            if msg.get("apikey") != daemon.args.apikey:
                LOG.error("Invalid apikey on socket")
                return
            LOG.debug("Order received: %s", {k: v for k, v in msg.items() if k != "apikey"})
            # chaque ordre dans son fil : une commande lente ne bloque pas les suivantes
            threading.Thread(target=self.safe_handle, args=(daemon, msg), daemon=True).start()

    @staticmethod
    def safe_handle(daemon, msg):
        try:
            daemon.handle(msg)
        except Exception as ex:
            LOG.exception("Order %s failed", msg.get("action"))
            what = msg.get("cmd") or msg.get("setting") or msg.get("action")
            daemon.jeedom.send({"action": "message", "level": "error", "message": f"Commande {what} : {ex}"})


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Démon Jeedom Dreame")
    p.add_argument("--loglevel", default="error")
    p.add_argument("--socketport", type=int, default=55090)
    p.add_argument("--callback", required=True)
    p.add_argument("--apikey", required=True)
    p.add_argument("--pid", required=True)
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    level = {"debug": logging.DEBUG, "info": logging.INFO, "notice": logging.INFO, "warning": logging.WARNING}.get(args.loglevel, logging.ERROR)
    logging.basicConfig(level=level, format="[%(asctime)s][%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    if level > logging.DEBUG:
        # la bibliothèque de protocole est bavarde : on ne garde que ses avertissements
        logging.getLogger("dreame").setLevel(max(level, logging.WARNING))

    with open(args.pid, "w") as f:
        f.write(str(os.getpid()))

    daemon = Daemon(args)
    server = Server(("127.0.0.1", args.socketport), SocketHandler)   # écoute locale uniquement
    server.daemon = daemon
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def shutdown(*_):
        LOG.info("Stopping daemon")
        daemon.stop_event.set()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    LOG.info("Daemon started on port %s", args.socketport)
    try:
        daemon.loop()
    finally:
        server.shutdown()
        try:
            os.remove(args.pid)
        except OSError:
            pass


if __name__ == "__main__":
    main()
