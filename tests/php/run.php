<?php
/*
 * Tests unitaires PHP du plugin Dreame (sans Jeedom installé).
 * Usage : php tests/php/run.php   (code retour 0 = succès)
 *
 * Le lanceur reconstitue l'arborescence d'un Jeedom dans un dossier temporaire :
 *   <tmp>/core/php/core.inc.php  -> faux cœur (stub_core.php)
 *   <tmp>/plugins/dreame         -> copie des dossiers core/ et plugin_info/ du dépôt
 * puis charge la vraie classe du plugin et vérifie son comportement.
 */

$repo = realpath(__DIR__ . '/../..');
$root = sys_get_temp_dir() . '/jeedom_dreame_tests_' . getmypid();
@mkdir($root . '/core/php', 0777, true);
@mkdir($root . '/plugins', 0777, true);
copy(__DIR__ . '/stub_core.php', $root . '/core/php/core.inc.php');
function copyTree($src, $dst) {
	@mkdir($dst, 0777, true);
	foreach (scandir($src) as $f) {
		if ($f == '.' || $f == '..') continue;
		is_dir("$src/$f") ? copyTree("$src/$f", "$dst/$f") : copy("$src/$f", "$dst/$f");
	}
}
foreach (array('core', 'plugin_info') as $d) copyTree("$repo/$d", "$root/plugins/dreame/$d");
require_once $root . '/plugins/dreame/core/class/dreame.class.php';

$failures = 0; $count = 0;
function check($cond, $label) {
	global $failures, $count;
	$count++;
	if (!$cond) { $failures++; echo "ÉCHEC : $label\n"; }
}

/* Faux démon : socket TCP local qui récupère les ordres envoyés par le plugin */
$server = stream_socket_server('tcp://127.0.0.1:0', $errno, $errstr);
$port = (int) substr(strrchr(stream_socket_get_name($server, false), ':'), 1);
config::save('socketport', $port, 'dreame');
config::save('username', 'user@example.com', 'dreame');
config::save('password', 'secret', 'dreame');
file_put_contents(jeedom::getTmpFolder('dreame') . '/deamon.pid', getmypid());   // démon « démarré »
function lastOrder() {
	global $server;
	$conn = stream_socket_accept($server, 2);
	$line = trim(fgets($conn));
	fclose($conn);
	return json_decode($line, true);
}

/* 1. Catalogue */
$defs = dreame::commandDefinitions();
check(count($defs) > 50, 'le catalogue est chargé');
check(isset($defs['start']) && $defs['start']['type'] == 'action', 'la commande start existe');

/* 2. Démon : informations et configuration */
$info = dreame::deamon_info();
check($info['launchable'] == 'ok' && $info['state'] == 'ok', 'démon lançable et démarré');
config::save('password', '', 'dreame');
check(dreame::deamon_info()['launchable'] == 'nok', 'démon non lançable sans mot de passe');
config::save('password', 'secret', 'dreame');

/* 3. Découverte : création d'un équipement avec les commandes de base */
dreame::handleDaemon(array('action' => 'devices', 'devices' => array(array('did' => '42', 'name' => 'Totor', 'model' => 'dreame.vacuum.r9419a', 'mac' => 'aa'))));
$eq = eqLogic::byLogicalId('42', 'dreame');
check(is_object($eq) && $eq->getName() == 'Totor', 'équipement créé à la découverte');
check(lastOrder()['action'] == 'reload', 'le démon est rechargé après création');
check(is_object($eq->getCmd(null, 'start')), 'commande Démarrer créée sans propriété requise');
check(!is_object($eq->getCmd(null, 'wash_mop')), 'pas de lavage tant que la station n\'est pas détectée');

/* 4. Propriétés supportées : création ciblée et liaisons action -> info */
dreame::handleDaemon(array('action' => 'supported', 'did' => '42', 'props' => array('state', 'battery', 'suction_level', 'self_wash_base_status')));
check(is_object($eq->getCmd(null, 'wash_mop')), 'lavage créé quand la station est détectée');
check(is_object($eq->getCmd(null, 'set_suction')), 'réglage d\'aspiration créé');
check(!is_object($eq->getCmd(null, 'set_volume')), 'pas de volume si non supporté');
check($eq->getCmd('action', 'set_suction')->getValue() == $eq->getCmd('info', 'suction_level')->getId(), 'action liée à son info');
check($eq->getCmd('action', 'set_suction')->getConfiguration('listValue') != '', 'liste de valeurs renseignée');

/* 5. Mises à jour envoyées par le démon */
dreame::handleDaemon(array('action' => 'update', 'did' => '42', 'values' => array('battery' => 87, 'state_label' => 'En charge')));
check($eq->getCmd('info', 'battery')->execCmd() == 87, 'valeur mise à jour');
dreame::handleDaemon(array('action' => 'token', 'token' => 'abc'));
check(config::byKey('refresh_token', 'dreame') == 'abc', 'jeton mémorisé');
$cfg = dreame::handleDaemon(array('action' => 'config'));
check($cfg['devices'][0]['did'] == '42' && $cfg['cycle'] >= 15, 'configuration transmise au démon');

/* 6. Exécution des commandes -> ordres au démon */
$eq->getCmd('action', 'start')->execute();
$o = lastOrder();
check($o == array('action' => 'cmd', 'did' => '42', 'cmd' => 'start', 'apikey' => 'TESTKEY'), 'Démarrer envoie l\'ordre cmd/start avec la clé API');
$eq->getCmd('action', 'set_suction')->execute(array('select' => '3'));
$o = lastOrder();
check($o['action'] == 'set' && $o['setting'] == 'suction_level' && $o['value'] == '3', 'liste de choix -> ordre set');
$eq->getCmd('action', 'refresh')->execute();
check(lastOrder()['action'] == 'refresh', 'Rafraîchir -> ordre refresh');

/* 7. Message d'erreur du démon */
dreame::handleDaemon(array('action' => 'message', 'level' => 'error', 'message' => 'test'));
check(end(log::$lines)[0] == 'error', 'message d\'erreur journalisé');
$thrown = false;
try { dreame::handleDaemon(array('action' => 'inconnu')); } catch (Exception $e) { $thrown = true; }
check($thrown, 'action inconnue refusée');

/* 8. Santé */
check(count(dreame::health()) >= 3, 'page santé renseignée');

exec('rm -rf ' . escapeshellarg($root));
echo "$count vérifications, $failures échec(s)\n";
exit($failures > 0 ? 1 : 0);
