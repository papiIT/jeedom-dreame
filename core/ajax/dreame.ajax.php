<?php
/* This file is part of the Jeedom "dreame" plugin (AGPL-3.0).
 * Appels AJAX de la page du plugin : synchronisation des robots, recréation des commandes. Réservé aux administrateurs.
 */
try {
	require_once __DIR__ . '/../../../../core/php/core.inc.php';
	include_file('core', 'authentification', 'php');
	if (!isConnect('admin')) {
		throw new Exception(__('401 - Accès non autorisé', __FILE__));
	}
	ajax::init();

	if (init('action') == 'discover') {
		dreame::sendToDaemon(array('action' => 'discover'));
		ajax::success();
	}

	if (init('action') == 'createCommands') {
		$eqLogic = dreame::byId(init('id'));
		if (!is_object($eqLogic)) {
			throw new Exception(__('Equipement introuvable', __FILE__));
		}
		$eqLogic->createCommands();
		ajax::success();
	}

	throw new Exception(__('Aucune méthode correspondante à', __FILE__) . ' : ' . init('action'));
} catch (Exception $e) {
	ajax::error(displayException($e), $e->getCode());
}
