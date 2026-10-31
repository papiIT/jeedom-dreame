# Plugin Dreame

Le plugin **Dreame** permet de piloter les robots aspirateurs et laveurs **Dreame** depuis Jeedom, via le cloud **Dreamehome** (le même service que l'application mobile Dreamehome).

Fonctionnalités :

- démarrer, mettre en pause, arrêter un nettoyage, renvoyer le robot à sa base, le localiser ;
- régler la puissance d'aspiration, le débit d'eau et le mode de nettoyage (aspiration, lavage ou les deux) ;
- piloter la station : vidage du bac, lavage et séchage des serpillières ;
- suivre l'état du robot (état, erreur, batterie, charge, durée et surface du dernier nettoyage) ;
- suivre la station (réservoirs d'eau propre et sale, sac à poussière) ;
- suivre l'usure des consommables (brosses, filtre, capteurs, serpillières…) et les remettre à zéro ;
- régler le volume, le verrouillage enfant, le boost tapis et le mode « ne pas déranger ».

Les changements d'état sont reçus **en temps réel** (le cloud pousse les modifications) ; une interrogation de secours a lieu toutes les 60 secondes au repos et toutes les 15 secondes pendant un nettoyage.

Les commandes sont créées **automatiquement selon les capacités de votre modèle** : un robot sans station de lavage n'aura pas les commandes de lavage, par exemple.

## Modèles compatibles

Tous les robots aspirateurs Dreame associés à un compte **Dreamehome** devraient fonctionner. Le plugin a été validé sur un **Dreame L40 Ultra**. Les robots associés uniquement à l'application **Xiaomi Mi Home** ne sont pas pris en charge.

Le réglage du mode de nettoyage tient compte de l'encodage particulier des modèles avec station de lavage et serpillières relevables (L10s, L20, L40, X30, X40…). Si un réglage ne donne pas le résultat attendu sur votre modèle, signalez-le sur le forum avec le log du démon en mode debug.

## Prérequis

- Jeedom 4.4 ou supérieur, Debian 11 ou 12 ;
- un compte **Dreamehome** sur lequel le robot est associé (e-mail et mot de passe) ;
- un accès Internet pour Jeedom (le pilotage passe par le cloud Dreame).

> **Conseil**
>
> Vous pouvez créer un second compte Dreamehome, partager le robot avec lui depuis l'application et l'utiliser dans Jeedom. Vous gardez ainsi votre compte principal pour l'application.

## Installation

1. Installez le plugin depuis le Market, puis activez-le.
2. Lancez l'installation des **dépendances** (environnement Python dédié, quelques minutes sur un Raspberry Pi).
3. Renseignez la configuration (voir ci-dessous) : le **démon** démarre automatiquement.

## Configuration du plugin

| Paramètre | Description |
|---|---|
| Identifiant (e-mail) | E-mail du compte Dreamehome. |
| Mot de passe | Mot de passe du compte (stocké chiffré dans Jeedom). |
| Région du compte | Région choisie dans l'application Dreamehome : **Europe** pour la France. |
| Fréquence de rafraîchissement au repos | Intervalle d'interrogation de secours en secondes (60 par défaut, minimum 15). |
| Port socket interne | Port local utilisé entre Jeedom et le démon (55090 par défaut). À changer seulement en cas de conflit. |

Après la première connexion, le plugin mémorise un jeton de session : le mot de passe n'est plus renvoyé au cloud à chaque redémarrage.

## Ajout des robots

Dans **Plugins → Objets connectés → Dreame**, cliquez sur **Synchroniser** : les robots du compte sont créés automatiquement (le nom est celui donné dans l'application). Ouvrez ensuite chaque robot pour choisir son **objet parent** (pièce).

Les commandes apparaissent au premier contact avec le robot ; si vous en supprimez une par erreur, le bouton **Recréer les commandes manquantes** la recrée.

## Commandes

### États

| Commande | Description |
|---|---|
| En ligne | 1 si le robot répond via le cloud. |
| Etat | État en clair (Aspiration, En charge, Lavage des serpillières…). |
| En nettoyage | 1 pendant un nettoyage (pratique dans les scénarios). |
| Sur la base | 1 quand le robot est sur sa base. |
| Erreur | Erreur ou alerte en clair (« Aucune » si tout va bien). |
| Batterie | Niveau de batterie en %. |
| Durée du nettoyage / Surface nettoyée | Valeurs du dernier nettoyage. |
| Puissance d'aspiration, Débit d'eau, Mode de nettoyage | Réglages actuels en clair. |
| Station, Vidage automatique, Réservoirs, Sac à poussière | État de la station. |
| Brosses, Filtre, Capteurs, Serpillières… | Durée de vie restante en % et en heures (masquées par défaut). |

Les commandes « (code) » contiennent les valeurs brutes ; elles sont masquées et servent aux scénarios avancés.

### Actions

| Commande | Description |
|---|---|
| Démarrer / Pause / Arrêter / Retour à la base | Pilotage du nettoyage. |
| Localiser | Le robot émet un son. |
| Régler l'aspiration / le débit d'eau / le mode de nettoyage | Listes de choix. |
| Vider le bac | Vidage dans la station (modèles avec vidage automatique). |
| Laver les serpillières / Démarrer ou arrêter le séchage | Modèles avec station de lavage. |
| Boost tapis, Verrouillage enfant, Ne pas déranger (On/Off), Régler le volume | Réglages (masqués par défaut). |
| Réinitialiser … | Remise à zéro d'un consommable après remplacement (masquées par défaut). |

## Exemples de scénarios

- **Nettoyage quand tout le monde est parti** : déclencheur sur la présence, action `#[Cuisine][Totor][Démarrer]#`.
- **Prévenir quand le bac est plein** : déclencheur `#[Cuisine][Totor][Sac à poussière]#` différent de « OK », action de notification.
- **Lavage des serpillières après chaque nettoyage** : déclencheur `#[Cuisine][Totor][En nettoyage]# == 0`, action « Laver les serpillières ».

## Santé et dépannage

La page **Analyse → Santé** indique l'état des dépendances, du démon et de chaque robot.

| Problème | Solution |
|---|---|
| Le démon ne démarre pas | Vérifiez l'e-mail et le mot de passe, puis le log `dreame_daemon`. |
| « Connexion au compte Dreamehome impossible » | Mauvais identifiants ou mauvaise **région**. Testez-les dans l'application Dreamehome. |
| Aucun robot trouvé | Le robot est-il bien associé à ce compte Dreamehome (et non à Xiaomi Mi Home) ? |
| Robot « hors ligne » | Vérifiez sa connexion Wi-Fi dans l'application Dreamehome ; le plugin se reconnecte seul avec un délai croissant (jusqu'à 10 minutes). |
| Une commande ne fait rien | Passez le log du plugin en **Debug**, relancez le démon et consultez `dreame_daemon`. |

## Confidentialité et fonctionnement

Le plugin dialogue avec les serveurs Dreame comme le fait l'application officielle. Les identifiants restent dans Jeedom (mot de passe et jeton chiffrés) ; le démon n'écoute que sur l'interface locale du Jeedom et chaque échange avec Jeedom est protégé par la clé API du plugin.

Ce plugin n'est ni développé ni soutenu par Dreame. Le protocole cloud provient du projet open source [Tasshack/dreame-vacuum](https://github.com/Tasshack/dreame-vacuum) (licence MIT), intégré au plugin.
