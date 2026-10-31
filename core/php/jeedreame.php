<?php
/* This file is part of the Jeedom "dreame" plugin (AGPL-3.0).
 * Point de rappel du démon : reçoit ses évènements (JSON) et les transmet à dreame::handleDaemon().
 * Accès protégé par la clé API du plugin.
 */
require_once __DIR__ . '/../../../../core/php/core.inc.php';

if (!jeedom::apiAccess(init('apikey'), 'dreame')) {
	http_response_code(401);
	echo json_encode(array('error' => 'unauthorized'));
	die();
}
header('Content-Type: application/json');
$payload = json_decode(file_get_contents('php://input'), true);
if (!is_array($payload) || !isset($payload['action'])) {
	http_response_code(400);
	echo json_encode(array('error' => 'bad request'));
	die();
}
try {
	echo json_encode(dreame::handleDaemon($payload));
} catch (Exception $e) {
	log::add('dreame', 'error', 'Callback ' . $payload['action'] . ' : ' . $e->getMessage());
	http_response_code(500);
	echo json_encode(array('error' => $e->getMessage()));
}
