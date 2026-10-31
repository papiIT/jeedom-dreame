<?php
/*
 * Faux cœur Jeedom minimal pour tester la classe du plugin sans installation Jeedom.
 * Seules les méthodes utilisées par dreame.class.php sont simulées, en mémoire.
 */

function __($txt, $file = '') { return $txt; }

class config {
	public static $values = array();
	public static function byKey($key, $plugin = 'core', $default = '') {
		return isset(self::$values[$plugin][$key]) ? self::$values[$plugin][$key] : $default;
	}
	public static function save($key, $value, $plugin = 'core') { self::$values[$plugin][$key] = $value; }
}

class log {
	public static $lines = array();
	public static function add($plugin, $level, $msg, $id = '') { self::$lines[] = array($level, $msg); }
	public static function getPathToLog($name) { return sys_get_temp_dir() . '/' . $name; }
	public static function convertLogLevel($l) { return 'error'; }
	public static function getLogLevel($p) { return 400; }
}

class event { public static $events = array(); public static function add($n, $o) { self::$events[] = array($n, $o); } }
class message { public static function removeAll($p, $id = '') {} }
class network { public static function getNetworkAccess($a, $b) { return 'http://127.0.0.1'; } }
class system {
	public static function getCmdPython3($p) { return 'python3 '; }
	public static function getCmdSudo() { return ''; }
	public static function kill($x) {}
}
class jeedom {
	public static function getApiKey($p) { return 'TESTKEY'; }
	public static function getTmpFolder($p) { $d = sys_get_temp_dir() . '/jeedom_test_' . $p; @mkdir($d); return $d; }
}
class plugin {
	public static function byId($id) { return new plugin(); }
	public function dependancy_info() { return array('state' => 'ok'); }
}

/** Équipements et commandes stockés en mémoire */
class eqLogic {
	public static $store = array();
	protected $id; protected $name; protected $logicalId; protected $eqType_name; protected $isEnable = 1; protected $isVisible = 1;
	protected $configuration = array(); public $cmds = array();
	public function getId() { return $this->id; }
	public function getName() { return $this->name; } public function setName($v) { $this->name = $v; }
	public function getLogicalId() { return $this->logicalId; } public function setLogicalId($v) { $this->logicalId = $v; }
	public function setEqType_name($v) { $this->eqType_name = $v; }
	public function getIsEnable() { return $this->isEnable; } public function setIsEnable($v) { $this->isEnable = $v; }
	public function setIsVisible($v) { $this->isVisible = $v; }
	public function getConfiguration($k, $d = '') { return isset($this->configuration[$k]) ? $this->configuration[$k] : $d; }
	public function setConfiguration($k, $v) { $this->configuration[$k] = $v; }
	public function save($direct = false) {
		if ($this->id === null) { $this->id = count(self::$store) + 1; self::$store[$this->id] = $this; }
		if (!$direct && method_exists($this, 'postSave')) $this->postSave();
	}
	public function getCmd($type = null, $logicalId = null) {
		if ($logicalId !== null) {
			foreach ($this->cmds as $c) if ($c->getLogicalId() == $logicalId && ($type === null || $c->getType() == $type)) return $c;
			return null;
		}
		return $this->cmds;
	}
	public function checkAndUpdateCmd($logicalId, $value) { $c = $this->getCmd('info', $logicalId); if ($c) $c->value = $value; }
	public static function byType($type, $onlyEnable = false) { return array_values(self::$store); }
	public static function byLogicalId($lid, $type) { foreach (self::$store as $e) if ($e->getLogicalId() == $lid) return $e; return null; }
}

class cmd {
	protected static $nextId = 1000;
	protected $id; protected $eqLogic; protected $logicalId; protected $name; protected $type; protected $subType;
	protected $configuration = array(); protected $display = array(); protected $valueLink; public $value; public $isVisible = 1;
	public function getId() { return $this->id; }
	public function setEqLogic_id($id) { $this->eqLogic = eqLogic::$store[$id]; }
	public function getEqLogic() { return $this->eqLogic; }
	public function getLogicalId() { return $this->logicalId; } public function setLogicalId($v) { $this->logicalId = $v; }
	public function getName() { return $this->name; } public function setName($v) { $this->name = $v; }
	public function getType() { return $this->type; } public function setType($v) { $this->type = $v; }
	public function getSubType() { return $this->subType; } public function setSubType($v) { $this->subType = $v; }
	public function setOrder($v) {} public function setIsVisible($v) { $this->isVisible = $v; }
	public function setUnite($v) {} public function setGeneric_type($v) {} public function setIsHistorized($v) {}
	public function setDisplay($k, $v) { $this->display[$k] = $v; }
	public function getConfiguration($k, $d = '') { return isset($this->configuration[$k]) ? $this->configuration[$k] : $d; }
	public function setConfiguration($k, $v) { $this->configuration[$k] = $v; }
	public function getValue() { return $this->valueLink; } public function setValue($v) { $this->valueLink = $v; }
	public function execCmd() { return $this->value; }
	public function save() {
		if ($this->id === null) { $this->id = self::$nextId++; $this->eqLogic->cmds[] = $this; }
	}
}
