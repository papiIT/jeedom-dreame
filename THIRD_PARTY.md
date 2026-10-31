# Composants tiers

## Tasshack/dreame-vacuum (licence MIT)

Le dossier `resources/dreamed/dreame/` contient le module de protocole cloud du projet
[Tasshack/dreame-vacuum](https://github.com/Tasshack/dreame-vacuum), copyright (c) 2022 Tasshack,
distribué sous licence MIT (texte complet dans `resources/dreamed/dreame/LICENSE`).

- `protocol.py` et `exceptions.py` : copiés sans modification ;
- `types.py` : extrait limité à la classe `RestartableTimer` utilisée par `protocol.py` ;
- `resources/dreamed/miio/` : module de remplacement minimal (le protocole local Mi Home n'est pas utilisé).

Pour mettre à jour le protocole, recopier `protocol.py` et `exceptions.py` depuis le projet amont
puis relancer les tests (`pytest tests/python`).
