"""Vérifie que le catalogue core/config/commands.json est cohérent avec le démon.

Le PHP crée les commandes à partir de ce fichier et le démon les alimente : une incohérence
(propriété inconnue, action absente, réglage mal typé) donnerait des commandes muettes.
"""
import json
import os
import re

import pytest

import dreamed

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CATALOG = json.load(open(os.path.join(ROOT, "core", "config", "commands.json"), encoding="utf-8"))["commands"]
BY_ID = {c["logicalId"]: c for c in CATALOG}
# commandes info alimentées par le démon sans être des propriétés brutes
DERIVED = {"online", "last_update", "state_label", "cleaning", "docked", "error_label", "charging_label",
           "self_wash_label", "auto_empty_label", "clean_water_label", "dirty_water_label", "dust_bag_label",
           "suction_label", "water_label", "cleaning_mode_label"}


def test_logical_ids_are_unique():
    ids = [c["logicalId"] for c in CATALOG]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("cmd", CATALOG, ids=lambda c: c["logicalId"])
def test_required_fields(cmd):
    assert cmd["type"] in ("info", "action")
    assert cmd["subType"] in ("binary", "numeric", "string", "other", "select", "slider")
    assert cmd["name"].strip()
    assert "prop" in cmd


@pytest.mark.parametrize("cmd", CATALOG, ids=lambda c: c["logicalId"])
def test_prop_exists_in_daemon(cmd):
    if cmd["prop"] is not None:
        assert cmd["prop"] in dreamed.PROPS, f"propriété inconnue du démon : {cmd['prop']}"


@pytest.mark.parametrize("cmd", [c for c in CATALOG if c["type"] == "info"], ids=lambda c: c["logicalId"])
def test_info_is_fed_by_daemon(cmd):
    lid = cmd["logicalId"]
    assert lid in dreamed.PROPS or lid in DERIVED, f"aucune source pour {lid}"


@pytest.mark.parametrize("cmd", [c for c in CATALOG if c["type"] == "action" and c["logicalId"] != "refresh"], ids=lambda c: c["logicalId"])
def test_action_is_known_by_daemon(cmd):
    target = cmd.get("daemon")
    assert target, "une action doit indiquer sa cible démon"
    is_setting = cmd["subType"] in ("select", "slider") or "setValue" in cmd
    if is_setting:
        assert target in dreamed.SETTINGS
    else:
        assert target in dreamed.ACTIONS


@pytest.mark.parametrize("cmd", [c for c in CATALOG if c["subType"] == "select"], ids=lambda c: c["logicalId"])
def test_select_values_are_accepted_by_daemon(cmd):
    allowed, _ = dreamed.SETTINGS[cmd["daemon"]]
    values = [int(v.split("|")[0]) for v in cmd["listValue"].split(";")]
    assert set(values) <= set(allowed)
    assert re.fullmatch(r"(\d+\|[^;|]+;)*\d+\|[^;|]+", cmd["listValue"])


@pytest.mark.parametrize("cmd", [c for c in CATALOG if "value" in c], ids=lambda c: c["logicalId"])
def test_action_value_links_to_existing_info(cmd):
    target = BY_ID.get(cmd["value"])
    assert target and target["type"] == "info"


def test_every_daemon_action_is_exposed():
    exposed = {c.get("daemon") for c in CATALOG}
    assert set(dreamed.ACTIONS) <= exposed
    assert set(dreamed.SETTINGS) <= exposed
