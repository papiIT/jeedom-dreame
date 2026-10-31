# Plugin Jeedom Dreame

Pilotage des robots aspirateurs laveurs **Dreame** depuis [Jeedom](https://www.jeedom.com) via le cloud Dreamehome.

- Documentation : https://papiit.github.io/jeedom-dreame/fr_FR/
- Historique : https://papiit.github.io/jeedom-dreame/fr_FR/changelog

## Architecture

```
plugin_info/            info.json (fiche Market), packages.json (dépendances), installation, configuration
core/class/             dreame.class.php : équipements, commandes, démon, santé
core/config/            commands.json : catalogue unique des commandes (créées selon les capacités du robot)
core/php/jeedreame.php  point de rappel HTTP du démon (clé API obligatoire)
core/ajax/              actions de la page du plugin (synchronisation, recréation des commandes)
core/i18n/              traductions
desktop/                page de gestion des robots
resources/dreamed/      démon Python (dreamed.py) + protocole cloud embarqué (dreame/, licence MIT)
tests/python/           tests unitaires du démon et cohérence du catalogue (pytest)
tests/php/              tests unitaires de la classe PHP avec un faux cœur Jeedom
docs/                   documentation fr_FR / en_US
```

Échanges :

```
Jeedom (PHP) --ordre JSON sur socket local 127.0.0.1:55090 (clé API)--> démon Python --HTTPS/MQTT--> cloud Dreame
Jeedom (PHP) <--POST JSON sur core/php/jeedreame.php (clé API)-------- démon Python
```

## Tests

```bash
pip install pytest requests
python -m pytest tests/python      # démon et catalogue, sans dépendance cloud
php tests/php/run.php              # classe PHP, sans Jeedom installé
```

Les mêmes tests tournent à chaque envoi sur GitHub (`.github/workflows/tests.yml`).

## Publication sur le Market

1. Créer le dépôt GitHub, pousser le code sur les branches `beta` puis `master`.
2. Activer GitHub Pages sur le dossier `/docs` et ajuster les liens de `plugin_info/info.json`.
3. Présenter le plugin sur le forum (Salon des développeurs › Présentation Plugin).
4. Ajouter le plugin sur le Market (identifiant `dreame`) en indiquant le dépôt.

## Licence

AGPL-3.0 (voir `LICENSE`). Composants tiers : voir `THIRD_PARTY.md`.
