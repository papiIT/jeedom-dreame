<?php
/* This file is part of the Jeedom "dreame" plugin.
 *
 * This program is free software: you can redistribute it and/or modify it under the terms of the
 * GNU Affero General Public License as published by the Free Software Foundation, either version 3
 * of the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
 * without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
 * See the GNU Affero General Public License for more details.
 */

require_once __DIR__ . '/../../../../core/php/core.inc.php';

/**
 * Plugin Dreame : pilotage des robots aspirateurs Dreame via le cloud Dreamehome.
 *
 * Architecture
 *  - Un démon Python (resources/dreamed/dreamed.py) maintient les sessions cloud et l'écoute
 *    des changements poussés par les robots.
 *  - Jeedom -> démon : ordres JSON sur un socket TCP local (sendToDaemon).
 *  - Démon -> Jeedom : appels HTTP sur core/php/jeedreame.php, traités par handleDaemon().
 *  - Les commandes sont décrites dans core/config/commands.json et créées uniquement si le
 *    robot expose la propriété correspondante (détection automatique au premier contact).
 */
class dreame extends eqLogic {

	/** Clés de configuration chiffrées en base par le cœur Jeedom */
	public static $_encryptConfigKey = array('password', 'refresh_token');

	/** Port TCP local par défaut du démon */
	const DEFAULT_PORT = 55090;

	/* ================================================================ catalogue de commandes */

	/**
	 * Retourne le catalogue des commandes, indexé par logicalId.
	 * @return array<string, array>
	 */
	public static function commandDefinitions() {
		static $defs = null;
		if ($defs === null) {
			$json = json_decode(file_get_contents(__DIR__ . '/../config/commands.json'), true);
			$defs = array();
			foreach ($json['commands'] as $def) {
				$defs[$def['logicalId']] = $def;
			}
		}
		return $defs;
	}

	/* ================================================================ dépendances
	 * Gérées par le cœur Jeedom à partir de plugin_info/packages.json (environnement Python
	 * isolé dans resources/python_venv sous Debian 12). On ajoute seulement un contrôle des
	 * imports pour détecter une installation incomplète.
	 */

	/** Commande Python à utiliser (environnement du plugin géré par le cœur) */
	public static function python() {
		return trim(system::getCmdPython3(__CLASS__));
	}

	public static function additionnalDependancyCheck() {
		exec(self::python() . ' -c "import requests, paho.mqtt, Crypto, cryptography" 2>&1', $out, $rc);
		return array('state' => ($rc == 0) ? 'ok' : 'nok');
	}

	/* ================================================================ démon */

	public static function deamon_info() {
		$return = array('log' => __CLASS__, 'launchable' => 'ok', 'state' => 'nok');
		$pid_file = jeedom::getTmpFolder(__CLASS__) . '/deamon.pid';
		if (file_exists($pid_file)) {
			if (@posix_getsid(trim(file_get_contents($pid_file)))) {
				$return['state'] = 'ok';
			} else {
				shell_exec(system::getCmdSudo() . 'rm -rf ' . $pid_file . ' 2>&1 > /dev/null');
			}
		}
		if (trim(config::byKey('username', __CLASS__)) == '' || config::byKey('password', __CLASS__) == '') {
			$return['launchable'] = 'nok';
			$return['launchable_message'] = __('Identifiants Dreamehome non renseignés', __FILE__);
		}
		return $return;
	}

	public static function deamon_start() {
		self::deamon_stop();
		$info = self::deamon_info();
		if ($info['launchable'] != 'ok') {
			throw new Exception(__('Veuillez vérifier la configuration', __FILE__));
		}
		$cmd = self::python() . ' ' . realpath(__DIR__ . '/../../resources/dreamed') . '/dreamed.py';
		$cmd .= ' --loglevel ' . log::convertLogLevel(log::getLogLevel(__CLASS__));
		$cmd .= ' --socketport ' . intval(config::byKey('socketport', __CLASS__, self::DEFAULT_PORT));
		$cmd .= ' --callback ' . network::getNetworkAccess('internal', 'proto:127.0.0.1:port:comp') . '/plugins/dreame/core/php/jeedreame.php';
		$cmd .= ' --apikey ' . jeedom::getApiKey(__CLASS__);
		$cmd .= ' --pid ' . jeedom::getTmpFolder(__CLASS__) . '/deamon.pid';
		log::add(__CLASS__, 'info', __('Lancement du démon', __FILE__));
		exec($cmd . ' >> ' . log::getPathToLog(__CLASS__ . '_daemon') . ' 2>&1 &');
		for ($i = 0; $i < 20; $i++) {
			if (self::deamon_info()['state'] == 'ok') {
				message::removeAll(__CLASS__, 'unableStartDeamon');
				return true;
			}
			sleep(1);
		}
		log::add(__CLASS__, 'error', __('Impossible de lancer le démon, consultez le log dreame_daemon', __FILE__), 'unableStartDeamon');
		return false;
	}

	public static function deamon_stop() {
		$pid_file = jeedom::getTmpFolder(__CLASS__) . '/deamon.pid';
		if (file_exists($pid_file)) {
			system::kill(intval(trim(file_get_contents($pid_file))));
		}
		system::kill('dreamed.py');
		sleep(1);
	}

	/** Exclut l'environnement Python des sauvegardes Jeedom (il est réinstallable) */
	public static function backupExclude() {
		return array('resources/python_venv', 'resources/venv');
	}

	/**
	 * Envoie un ordre au démon.
	 * @param array $params ordre ('action' => discover|reload|cmd|set|refresh, ...)
	 * @throws Exception si le démon est arrêté ou injoignable
	 */
	public static function sendToDaemon($params) {
		if (self::deamon_info()['state'] != 'ok') {
			throw new Exception(__('Le démon Dreame n\'est pas démarré', __FILE__));
		}
		$params['apikey'] = jeedom::getApiKey(__CLASS__);
		$socket = @fsockopen('127.0.0.1', intval(config::byKey('socketport', __CLASS__, self::DEFAULT_PORT)), $errno, $errstr, 5);
		if (!$socket) {
			throw new Exception(__('Impossible de joindre le démon Dreame : ', __FILE__) . $errstr);
		}
		fwrite($socket, json_encode($params) . "\n");
		fclose($socket);
	}

	/** Page Santé du plugin (Analyse > Santé) */
	public static function health() {
		$return = array();
		$deps = plugin::byId(__CLASS__)->dependancy_info();
		$return[] = array('test' => __('Dépendances', __FILE__), 'result' => $deps['state'] == 'ok' ? __('OK', __FILE__) : __('NOK', __FILE__),
			'advice' => $deps['state'] == 'ok' ? '' : __('Relancez l\'installation des dépendances', __FILE__), 'state' => $deps['state'] == 'ok');
		$daemon = self::deamon_info();
		$return[] = array('test' => __('Démon', __FILE__), 'result' => $daemon['state'] == 'ok' ? __('OK', __FILE__) : __('Arrêté', __FILE__),
			'advice' => $daemon['state'] == 'ok' ? '' : (isset($daemon['launchable_message']) ? $daemon['launchable_message'] : ''), 'state' => $daemon['state'] == 'ok');
		foreach (eqLogic::byType(__CLASS__, true) as $eqLogic) {
			$online = $eqLogic->getCmd('info', 'online');
			$ok = is_object($online) && $online->execCmd() == 1;
			$return[] = array('test' => $eqLogic->getName(), 'result' => $ok ? __('En ligne', __FILE__) : __('Hors ligne', __FILE__),
				'advice' => $ok ? '' : __('Vérifiez la connexion Wi-Fi du robot et le log dreame_daemon', __FILE__), 'state' => $ok);
		}
		return $return;
	}

	/* ================================================================ rappels du démon */

	/** Configuration transmise au démon (identifiants, région, robots) */
	public static function daemonConfig() {
		$devices = array();
		foreach (eqLogic::byType(__CLASS__) as $eqLogic) {
			$devices[] = array('did' => $eqLogic->getLogicalId(), 'name' => $eqLogic->getName(), 'enabled' => (bool) $eqLogic->getIsEnable());
		}
		return array(
			'username' => trim(config::byKey('username', __CLASS__)),
			'password' => config::byKey('password', __CLASS__),
			'country' => config::byKey('country', __CLASS__, 'eu'),
			'refresh_token' => config::byKey('refresh_token', __CLASS__),
			'cycle' => max(15, intval(config::byKey('cycle', __CLASS__, 60))),
			'devices' => $devices,
		);
	}

	/**
	 * Traite un évènement envoyé par le démon.
	 * @param array $payload ('action' => config|token|devices|supported|update|message, ...)
	 * @return array réponse renvoyée au démon
	 */
	public static function handleDaemon($payload) {
		switch ($payload['action']) {
			case 'config':
				return self::daemonConfig();

			case 'token':
				config::save('refresh_token', $payload['token'], __CLASS__);
				return array('ok' => true);

			case 'devices':
				$created = 0;
				foreach ($payload['devices'] as $device) {
					$eqLogic = eqLogic::byLogicalId($device['did'], __CLASS__);
					if (!is_object($eqLogic)) {
						$eqLogic = new dreame();
						$eqLogic->setEqType_name(__CLASS__);
						$eqLogic->setLogicalId($device['did']);
						$eqLogic->setName($device['name']);
						$eqLogic->setIsEnable(1);
						$eqLogic->setIsVisible(1);
						$created++;
					}
					$eqLogic->setConfiguration('model', $device['model']);
					$eqLogic->setConfiguration('mac', $device['mac']);
					$eqLogic->save();
				}
				event::add('jeedom::alert', array(
					'level' => 'success',
					'page' => __CLASS__,
					'message' => sprintf(__('%d robot(s) trouvé(s), %d nouveau(x)', __FILE__), count($payload['devices']), $created),
				));
				if ($created > 0) {
					self::sendToDaemon(array('action' => 'reload'));
				}
				return array('ok' => true);

			case 'supported':
				$eqLogic = eqLogic::byLogicalId($payload['did'], __CLASS__);
				if (is_object($eqLogic)) {
					$eqLogic->setConfiguration('supported', $payload['props']);
					$eqLogic->save(true);
					$eqLogic->createCommands();
				}
				return array('ok' => true);

			case 'update':
				$eqLogic = eqLogic::byLogicalId($payload['did'], __CLASS__);
				if (is_object($eqLogic)) {
					foreach ($payload['values'] as $logicalId => $value) {
						$eqLogic->checkAndUpdateCmd($logicalId, $value);
					}
				}
				return array('ok' => true);

			case 'message':
				$level = $payload['level'] == 'error' ? 'error' : 'warning';
				log::add(__CLASS__, $level, $payload['message']);
				event::add('jeedom::alert', array('level' => $level == 'error' ? 'danger' : 'warning', 'page' => __CLASS__, 'message' => $payload['message']));
				return array('ok' => true);
		}
		throw new Exception('Unknown action ' . $payload['action']);
	}

	/* ================================================================ équipement */

	public function getImage() {
		return 'plugins/dreame/plugin_info/dreame_icon.png';
	}

	public function postSave() {
		if ($this->getLogicalId() != '') {
			$this->createCommands();
		}
	}

	/** Après une sauvegarde depuis l'interface : le démon recharge la liste des robots */
	public function postAjax() {
		try {
			self::sendToDaemon(array('action' => 'reload'));
		} catch (Exception $e) {
		}
	}

	public function postRemove() {
		try {
			self::sendToDaemon(array('action' => 'reload'));
		} catch (Exception $e) {
		}
	}

	/**
	 * Crée les commandes manquantes supportées par ce robot. Ne modifie jamais une commande
	 * existante (l'utilisateur a pu la renommer ou la personnaliser).
	 */
	public function createCommands() {
		$supported = $this->getConfiguration('supported', array());
		if (!is_array($supported)) {
			$supported = array();
		}
		$order = 0;
		$links = array();
		foreach (self::commandDefinitions() as $logicalId => $def) {
			$order++;
			if ($def['prop'] !== null && !in_array($def['prop'], $supported)) {
				continue;
			}
			$cmd = $this->getCmd(null, $logicalId);
			if (!is_object($cmd)) {
				$cmd = new dreameCmd();
				$cmd->setEqLogic_id($this->getId());
				$cmd->setLogicalId($logicalId);
				$cmd->setName(__($def['name'], __FILE__));
				$cmd->setType($def['type']);
				$cmd->setSubType($def['subType']);
				$cmd->setOrder($order);
				$cmd->setIsVisible(isset($def['isVisible']) ? $def['isVisible'] : 1);
				if (isset($def['unite'])) $cmd->setUnite($def['unite']);
				if (isset($def['generic_type'])) $cmd->setGeneric_type($def['generic_type']);
				if (isset($def['isHistorized'])) $cmd->setIsHistorized($def['isHistorized']);
				if (isset($def['icon'])) $cmd->setDisplay('icon', '<i class="' . $def['icon'] . '"></i>');
				if (isset($def['listValue'])) $cmd->setConfiguration('listValue', $def['listValue']);
				if (isset($def['minValue'])) $cmd->setConfiguration('minValue', $def['minValue']);
				if (isset($def['maxValue'])) $cmd->setConfiguration('maxValue', $def['maxValue']);
				$cmd->save();
			}
			if (isset($def['value'])) {
				$links[$logicalId] = $def['value'];
			}
		}
		// liaison action -> info (affiche l'état courant sur le widget de l'action)
		foreach ($links as $actionId => $infoId) {
			$action = $this->getCmd('action', $actionId);
			$info = $this->getCmd('info', $infoId);
			if (is_object($action) && is_object($info) && $action->getValue() != $info->getId()) {
				$action->setValue($info->getId());
				$action->save();
			}
		}
	}
}

class dreameCmd extends cmd {

	/** Les commandes sont gérées par le plugin : pas de suppression automatique */
	public function dontRemoveCmd() {
		return true;
	}

	/**
	 * Exécution d'une commande action : transmise au démon.
	 *  - refresh : relecture immédiate
	 *  - réglage (select/slider/On/Off) : ordre « set » avec la valeur
	 *  - autre : ordre « cmd » (démarrer, pause, station, consommables...)
	 */
	public function execute($_options = array()) {
		if ($this->getType() != 'action') {
			return;
		}
		$eqLogic = $this->getEqLogic();
		$did = $eqLogic->getLogicalId();
		if ($this->getLogicalId() == 'refresh') {
			dreame::sendToDaemon(array('action' => 'refresh', 'did' => $did));
			return;
		}
		$defs = dreame::commandDefinitions();
		$def = isset($defs[$this->getLogicalId()]) ? $defs[$this->getLogicalId()] : null;
		if ($def === null || !isset($def['daemon'])) {
			throw new Exception(__('Commande inconnue : ', __FILE__) . $this->getLogicalId());
		}
		$isSetting = $this->getSubType() == 'select' || $this->getSubType() == 'slider' || isset($def['setValue']);
		if ($isSetting) {
			if ($this->getSubType() == 'select') {
				$value = $_options['select'];
			} elseif ($this->getSubType() == 'slider') {
				$value = $_options['slider'];
			} else {
				$value = $def['setValue'];
			}
			dreame::sendToDaemon(array('action' => 'set', 'did' => $did, 'setting' => $def['daemon'], 'value' => $value));
			return;
		}
		dreame::sendToDaemon(array('action' => 'cmd', 'did' => $did, 'cmd' => $def['daemon']));
	}
}
