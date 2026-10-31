<?php
/* This file is part of the Jeedom "dreame" plugin (AGPL-3.0).
 * Page de configuration du plugin : compte Dreamehome, région, fréquence de rafraîchissement, port du démon.
 */
require_once __DIR__ . '/../../../core/php/core.inc.php';
include_file('core', 'authentification', 'php');
if (!isConnect()) {
	include_file('desktop', '404', 'php');
	die();
}
?>
<form class="form-horizontal">
	<fieldset>
		<legend><i class="fas fa-user"></i> {{Compte Dreamehome}}</legend>
		<div class="form-group">
			<label class="col-md-4 control-label">{{Identifiant (e-mail)}}</label>
			<div class="col-md-4">
				<input class="configKey form-control" data-l1key="username" autocomplete="off" />
			</div>
		</div>
		<div class="form-group">
			<label class="col-md-4 control-label">{{Mot de passe}}</label>
			<div class="col-md-4">
				<input type="password" class="configKey form-control" data-l1key="password" autocomplete="new-password" />
			</div>
		</div>
		<div class="form-group">
			<label class="col-md-4 control-label">{{Région du compte}}
				<sup><i class="fas fa-question-circle tooltips" title="{{Région choisie dans l'application Dreamehome (Europe pour la France)}}"></i></sup>
			</label>
			<div class="col-md-4">
				<select class="configKey form-control" data-l1key="country">
					<option value="eu">{{Europe}}</option>
					<option value="us">{{Amérique du Nord}}</option>
					<option value="cn">{{Chine}}</option>
					<option value="ru">{{Russie}}</option>
					<option value="sg">{{Asie (Singapour)}}</option>
					<option value="kr">{{Corée}}</option>
				</select>
			</div>
		</div>
		<legend><i class="fas fa-university"></i> {{Démon}}</legend>
		<div class="form-group">
			<label class="col-md-4 control-label">{{Fréquence de rafraîchissement au repos (s)}}
				<sup><i class="fas fa-question-circle tooltips" title="{{Les changements sont aussi reçus en temps réel ; pendant un nettoyage la fréquence passe à 15 s}}"></i></sup>
			</label>
			<div class="col-md-2">
				<input class="configKey form-control" data-l1key="cycle" placeholder="60" />
			</div>
		</div>
		<div class="form-group">
			<label class="col-md-4 control-label">{{Port socket interne}}</label>
			<div class="col-md-2">
				<input class="configKey form-control" data-l1key="socketport" placeholder="55090" />
			</div>
		</div>
	</fieldset>
</form>
