<?php
/* This file is part of the Jeedom "dreame" plugin (AGPL-3.0). */
require_once __DIR__ . '/../../../core/php/core.inc.php';

/** Valeurs par défaut de la configuration */
function dreame_install() {
	if (config::byKey('socketport', 'dreame') == '') {
		config::save('socketport', 55090, 'dreame');
	}
	if (config::byKey('country', 'dreame') == '') {
		config::save('country', 'eu', 'dreame');
	}
	if (config::byKey('cycle', 'dreame') == '') {
		config::save('cycle', 60, 'dreame');
	}
}

/** Mise à jour : nouvelles commandes, nettoyage de l'ancien environnement Python (v1.0) */
function dreame_update() {
	dreame_install();
	$oldVenv = __DIR__ . '/../resources/venv';
	if (is_dir($oldVenv)) {
		shell_exec(system::getCmdSudo() . 'rm -rf ' . escapeshellarg($oldVenv) . ' 2>&1');
	}
	foreach (eqLogic::byType('dreame') as $eqLogic) {
		$eqLogic->createCommands();
	}
}

function dreame_remove() {
}
