"""Tests unitaires du démon Dreame (resources/dreamed/dreamed.py)."""
import json
import socket
import threading
import time

import pytest

import dreamed


# ------------------------------------------------------------------ libellés et conversions
class TestLabels:
    def test_state_and_cleaning_flag(self):
        out = dreamed.labels_for({"state": 1})
        assert out == {"state_label": "Aspiration", "cleaning": 1}
        assert dreamed.labels_for({"state": 6})["cleaning"] == 0

    def test_unknown_values_are_still_readable(self):
        assert dreamed.labels_for({"state": 999})["state_label"] == "État 999"
        assert dreamed.labels_for({"error": 4242})["error_label"] == "Erreur 4242"

    def test_charging_sets_docked(self):
        assert dreamed.labels_for({"charging_status": 1})["docked"] == 1
        assert dreamed.labels_for({"charging_status": 3})["docked"] == 1
        assert dreamed.labels_for({"charging_status": 2})["docked"] == 0

    def test_only_present_keys_are_computed(self):
        assert dreamed.labels_for({"battery": 80}) == {}

    def test_station_and_settings_labels(self):
        out = dreamed.labels_for({"dust_bag_status": 0, "suction_level": 3, "water_volume": 1, "cleaning_mode": 2})
        assert out["dust_bag_label"] == "OK"
        assert out["suction_label"] == "Max"
        assert out["water_label"] == "Faible"
        assert out["cleaning_mode_label"] == "Aspiration et lavage"

    def test_none_values_are_ignored(self):
        assert "suction_label" not in dreamed.labels_for({"suction_level": None})

    def test_to_number(self):
        assert dreamed.to_number(True) == 1
        assert dreamed.to_number(False) == 0
        assert dreamed.to_number(42) == 42


class TestCleaningMode:
    """Valeurs relevées sur un L40 Ultra réel : 5120 = aspiration + lavage."""

    def test_decode_grouped_value(self):
        assert dreamed.decode_cleaning_mode(5120) == 2      # bits bas 0 -> aspiration + lavage
        assert dreamed.decode_cleaning_mode(5122) == 0      # bits bas 2 -> aspiration seule
        assert dreamed.decode_cleaning_mode(5121) == 1      # bits bas 1 -> lavage

    def test_decode_simple_models(self):
        assert dreamed.decode_cleaning_mode(0) == 0
        assert dreamed.decode_cleaning_mode(2) == 2
        assert dreamed.decode_cleaning_mode(None) is None

    @pytest.mark.parametrize("mode", [0, 1, 2])
    def test_encode_keeps_other_bits(self, mode):
        raw = dreamed.encode_cleaning_mode(5120, mode)
        assert raw & ~0x03 == 5120 & ~0x03                  # réglages annexes conservés
        assert dreamed.decode_cleaning_mode(raw) == mode    # aller-retour cohérent

    def test_encode_simple_models(self):
        assert dreamed.encode_cleaning_mode(1, 2) == 2
        assert dreamed.encode_cleaning_mode(None, 1) == 1


# ------------------------------------------------------------------ cohérence des tables
def test_every_prop_has_unique_siid_piid():
    assert len(set(dreamed.PROPS.values())) == len(dreamed.PROPS)


def test_every_setting_is_a_readable_property():
    for name in dreamed.SETTINGS:
        assert name in dreamed.PROPS


def test_active_states_include_cleaning_states():
    assert dreamed.CLEANING_STATES <= dreamed.ACTIVE_STATES


# ------------------------------------------------------------------ robot
class TestRobot:
    def test_get_is_split_in_batches(self, robot):
        for key, sp in dreamed.PROPS.items():
            robot.proto.store[sp] = 1
        values = robot._get(dreamed.PROPS.keys())
        assert len(values) == len(dreamed.PROPS)
        assert max(robot.proto.requests) <= dreamed.Robot.BATCH
        assert sum(robot.proto.requests) == len(dreamed.PROPS)

    def test_probe_reports_only_supported_props(self, robot, jeedom):
        robot.proto.store[dreamed.PROPS["battery"]] = 90
        robot.proto.store[dreamed.PROPS["state"]] = 6
        robot.probe()
        assert robot.supported == ["battery", "state"]
        assert jeedom.of("supported")[-1]["props"] == ["battery", "state"]
        update = jeedom.of("update")[-1]["values"]
        assert update["battery"] == 90 and update["state_label"] == "En charge"
        assert "last_update" in update

    def test_publish_normalises_values(self, robot, jeedom):
        robot.publish({"dnd": True, "cleaning_mode": 5120})
        values = jeedom.of("update")[-1]["values"]
        assert values["dnd"] == 1
        assert values["cleaning_mode"] == 2
        assert values["cleaning_mode_label"] == "Aspiration et lavage"
        assert robot.values["cleaning_mode"] == 5120          # la valeur brute est gardée pour l'écriture

    def test_publish_nothing_when_empty(self, robot, jeedom):
        robot.publish({})
        assert jeedom.of("update") == []

    def test_pushed_message(self, robot, jeedom):
        robot.on_message({"method": "properties_changed", "params": [
            {"siid": 3, "piid": 1, "value": 55}, {"siid": 99, "piid": 9, "value": 1}]})
        values = jeedom.of("update")[-1]["values"]
        assert values["battery"] == 55
        assert "99" not in json.dumps(values)

    def test_pushed_message_other_method_ignored(self, robot, jeedom):
        robot.on_message({"method": "_otc.info", "params": {}})
        robot.on_message({"garbage": True})
        assert jeedom.of("update") == []

    def test_action_success_schedules_quick_poll(self, robot):
        robot.action("wash_mop")
        assert robot.proto.actions == [(4, 4, [{"piid": 10, "value": "2,1"}])]
        assert robot.next_poll > time.time()

    def test_action_refused(self, robot):
        robot.proto.action_result = {"code": -1}
        with pytest.raises(RuntimeError):
            robot.action("start")

    def test_unknown_action(self, robot):
        with pytest.raises(ValueError):
            robot.action("self_destruct")

    def test_set_setting_select(self, robot):
        robot.set_setting("suction_level", "3")
        assert robot.proto.writes == [(4, 4, 3)]

    def test_set_setting_bool_cast(self, robot):
        robot.set_setting("dnd", 1)
        assert robot.proto.writes == [(5, 1, True)]

    def test_set_cleaning_mode_uses_current_raw_value(self, robot):
        robot.values["cleaning_mode"] = 5120
        robot.set_setting("cleaning_mode", 0)
        siid, piid, raw = robot.proto.writes[-1]
        assert (siid, piid) == (4, 23)
        assert raw == 5122

    @pytest.mark.parametrize("name,value", [("suction_level", 9), ("water_volume", 0), ("volume", 101), ("volume", -1), ("suction_level", "abc"), ("nope", 1)])
    def test_set_setting_rejects_invalid(self, robot, name, value):
        with pytest.raises(ValueError):
            robot.set_setting(name, value)
        assert robot.proto.writes == []

    def test_set_setting_refused_by_robot(self, robot):
        robot.proto.write_code = -1
        with pytest.raises(RuntimeError):
            robot.set_setting("volume", 50)

    def test_online_only_sent_on_change(self, robot, jeedom):
        robot.set_online(True)
        robot.set_online(True)
        robot.set_online(False)
        assert [p["values"]["online"] for p in jeedom.of("update")] == [1, 0]

    def test_active_property(self, robot):
        robot.values["state"] = 1
        assert robot.active
        robot.values["state"] = 6
        assert not robot.active


# ------------------------------------------------------------------ démon
class TestDaemon:
    def test_load_config_keeps_only_enabled_robots(self, daemon):
        daemon.load_config()
        assert list(daemon.robots) == ["123"]

    def test_save_token_only_when_changed(self, daemon, jeedom):
        daemon.save_token("abc")
        daemon.save_token("abc")
        daemon.save_token(None)
        assert [p["token"] for p in jeedom.of("token")] == ["abc"]

    def test_cycle_connects_and_polls(self, daemon, jeedom):
        daemon.load_config()
        daemon.cycle()
        robot = daemon.robots["123"]
        assert robot.proto is not None
        assert jeedom.of("update")[0]["values"] == {"online": 1}
        assert robot.next_poll > time.time()

    def test_cycle_backs_off_on_failure(self, daemon, jeedom):
        daemon.load_config()
        robot = daemon.robots["123"]

        def boom():
            raise RuntimeError("cloud down")
        robot.connect = boom
        daemon.cycle()
        assert robot.fail_count == 1
        assert robot.proto is None
        assert jeedom.of("update")[-1]["values"] == {"online": 0}
        assert robot.next_poll >= time.time() + 25

    def test_discover_filters_non_vacuum(self, daemon, jeedom):
        daemon.cloud_factory = lambda *a: type("C", (), {
            "_secondary_key": "tok", "login": lambda self: True, "disconnect": lambda self: None,
            "get_devices": lambda self: {"page": {"records": [
                {"did": 1, "model": "dreame.vacuum.r2416", "customName": "Totor", "mac": "aa"},
                {"did": 2, "model": "dreame.hold.w2422", "customName": "Balai"},
                {"did": 3, "model": "dreame.vacuum.p2009", "customName": "", "deviceInfo": {"displayName": "D9"}},
            ]}}})()
        daemon.discover()
        devices = jeedom.of("devices")[-1]["devices"]
        assert [d["name"] for d in devices] == ["Totor", "D9"]
        assert jeedom.of("token")[-1]["token"] == "tok"

    def test_discover_without_credentials(self, daemon, jeedom):
        daemon.config = {"username": "", "password": ""}
        daemon.discover()
        assert jeedom.of("message")[-1]["level"] == "error"

    def test_discover_login_failure(self, daemon, jeedom):
        daemon.cloud_factory = lambda *a: type("C", (), {"login": lambda self: False})()
        daemon.discover()
        assert "impossible" in jeedom.of("message")[-1]["message"]

    def test_handle_routes_orders(self, daemon, robot):
        daemon.robots = {"123": robot}
        daemon.handle({"action": "cmd", "did": "123", "cmd": "dock"})
        daemon.handle({"action": "set", "did": "123", "setting": "volume", "value": 40})
        robot.next_poll = 999999999999
        daemon.handle({"action": "refresh", "did": "123"})
        daemon.handle({"action": "reload"})
        assert robot.proto.actions == [(3, 1, None)]
        assert robot.proto.writes == [(7, 1, 40)]
        assert robot.next_poll == 0
        assert daemon.reload_event.is_set()

    def test_handle_unknown_robot(self, daemon, jeedom):
        daemon.handle({"action": "cmd", "did": "nope", "cmd": "start"})
        assert jeedom.of("message")[-1]["level"] == "warning"


# ------------------------------------------------------------------ socket (sécurité)
def test_socket_requires_apikey(daemon):
    received = []
    daemon.handle = received.append
    server = dreamed.Server(("127.0.0.1", 0), dreamed.SocketHandler)
    server.daemon = daemon
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        for payload in (b"not json\n", b'{"action":"reload","apikey":"WRONG"}\n', b'{"action":"reload","apikey":"KEY"}\n'):
            with socket.create_connection(("127.0.0.1", port)) as s:
                s.sendall(payload)
        for _ in range(50):
            if received:
                break
            time.sleep(0.05)
        assert received == [{"action": "reload", "apikey": "KEY"}]
    finally:
        server.shutdown()
        server.server_close()


def test_safe_handle_reports_errors(daemon, jeedom):
    def fail(msg):
        raise RuntimeError("boom")
    daemon.handle = fail
    dreamed.SocketHandler.safe_handle(daemon, {"action": "set", "setting": "volume"})
    assert jeedom.of("message")[-1]["message"] == "Commande volume : boom"


def test_jeedom_send_never_raises():
    class BrokenSession:
        def post(self, *a, **k):
            raise ConnectionError("down")
    assert dreamed.Jeedom("http://x", "k", session=BrokenSession()).send({"action": "config"}) is None
