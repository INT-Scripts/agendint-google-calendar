# Agendint ↔ Google Calendar Sync

Un outil Python permettant de synchroniser automatiquement l'emploi du temps de votre école (récupéré via la librairie [Agendint](https://github.com/INT-Scripts/int-libraries)) directement avec votre Google Calendar.

Cet outil utilise l'API officielle Google Calendar et intègre un système de "Diff" intelligent : il ne modifie que ce qui est strictement nécessaire (ajouts, suppressions, modifications de salles ou d'intervenants) pour économiser vos quotas d'API. De plus, il historise l'ensemble des données extraites sous forme de logs JSON pour garder une trace.

## 🚀 Fonctionnalités

- **Synchronisation OAuth2** : Fonctionne de manière 100% autonome après la première connexion.
- **Diff intelligent** : Ne fait des requêtes d'insertion/mise à jour à Google que lorsque le cours a été modifié ou ajouté.
- **Historisation (Logs)** : Chaque synchronisation sauvegarde l'état brut de l'emploi du temps dans le dossier `scrape_history/`.
- **Mode Démon (Automatique)** : Le script peut tourner en boucle infinie (ex: une fois par jour) pour gérer l'actualisation sans intervention.
- **Hydratation paramétrable** : Possibilité de récupérer les détails complets (salles, intervenants) ou de s'en passer pour une exécution ultra-rapide.

---

## 🛠️ Installation et Préparation

### 1. Prérequis
Vous aurez besoin de **Python 3.10+** et de **[uv](https://github.com/astral-sh/uv)** (le gestionnaire de paquets ultra-rapide).

Clonez ce dépôt et installez les dépendances :
```bash
git clone https://github.com/votre-pseudo/agendint-google-calendar.git
cd agendint-google-calendar
uv sync
# Ou uv install via : uv add "git+https://github.com/INT-Scripts/int-libraries.git#subdirectory=packages/agendint" google-api-python-client google-auth-httplib2 google-auth-oauthlib python-dotenv
```

### 2. Variables d'Environnement
Copiez le modèle `.env.example` en `.env` :
```bash
cp .env.example .env
```
Ouvrez le `.env` et ajoutez vos identifiants d'école ainsi que l'ID du Google Calendar cible (laissez vide pour utiliser votre calendrier principal).

### 3. Obtenir l'accès à Google API (`credentials.json`)
Pour que le script puisse modifier votre Google Calendar :
1. Allez sur la [Google Cloud Console](https://console.cloud.google.com/).
2. Créez un projet et activez la **Google Calendar API**.
3. Dans **Écran de consentement OAuth**, mettez l'application "En production" (cela vous évite le bug des utilisateurs de test) ou ajoutez votre adresse email en tant que "Test User".
4. Dans **Identifiants**, créez un "ID client OAuth" (Type: *Application de bureau*).
5. Téléchargez le fichier JSON, renommez-le en `credentials.json` et placez-le à la racine de ce dossier.

---

## 💻 Utilisation

### Premier lancement (Validation Google)
Pour la toute première exécution, lancez le mode "Dry Run" (simulation). Il ne modifiera rien sur Google Calendar mais il ouvrira une fenêtre dans votre navigateur pour associer votre compte Google.

```bash
uv run main.py --dry-run
```
Acceptez les autorisations. Un fichier `token.json` va être généré, permettant au script d'être 100% autonome par la suite !

### Utilisation Classique
Pour lancer une synchronisation unique sur l'année complète (avec hydratation des salles et profs) :
```bash
uv run main.py
```

### Sans Hydratation (Très Rapide)
Pour désactiver les requêtes supplémentaires (si le site de l'école est lent) :
```bash
uv run main.py --no-hydrate
```

### 🔁 Mode Automatique (Démon)
Le script peut tourner en tâche de fond. S'il réussit, il attendra 24h. S'il y a un problème réseau, il réessaiera 1h plus tard :
```bash
uv run main.py --daemon
```

### Paramètres Avancés
Vous pouvez modifier les délais du démon avec les arguments suivants :
- `--interval 24` : Nombre d'heures entre deux synchronisations réussies (Mode Démon).
- `--retry-delay 1` : Nombre d'heures avant une nouvelle tentative en cas d'erreur (Mode Démon).

## 📂 Structure du Projet

- `main.py` : Point d'entrée, gestion du mode démon, des arguments et des logs d'historique JSON.
- `scraper.py` : Interface avec la librairie `agendint`.
- `gcal_sync.py` : Connexion à l'API Google, création des événements et algorithme intelligent de "Diff".
- `scrape_history/` : Généré automatiquement, stocke vos logs d'emploi du temps en JSON.
