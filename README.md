# STV SPORT V3 — Barça · Real Madrid · El Clásico

Application web locale (FastAPI + SQLite + page web responsive) centrée sur le **FC Barcelone** et le **Real Madrid**, 100 % gratuite, sans données simulées.

## Lancer sur Windows
1. Installer Python 3.11 ou 3.12 (cocher « Add Python to PATH »).
2. Extraire le ZIP dans un dossier, puis double-cliquer sur `start_windows.bat`.
3. Le site s'ouvre sur http://127.0.0.1:8000

Au premier lancement, le compte **admin** est créé avec un mot de passe aléatoire écrit dans `ADMIN_MOT_DE_PASSE.txt`. Connecte-toi, puis clique sur « Mot de passe » pour le changer.

## Ce que contient le site
- **Pages Barça, Real Madrid et El Clásico** : directs officiels, prochains matchs, derniers résultats avec bouton « Résumé », vidéos de buts.
- **Logos des clubs et drapeaux des pays** à côté de chaque équipe (initiales si logo introuvable).
- **Scores en direct tous sports** (SportsAPI, optionnel), actualisés toutes les 60 s.
- **Matchs, replays, chaînes** ajoutables par l'administrateur, recherche par équipe, favoris, historique.

## Sources gratuites
| Besoin | Source | Clé |
|---|---|---|
| Résumés et buts | ScoreBat (flux libre) | aucune |
| Calendrier et résultats | TheSportsDB (clé de test publique) | aucune |
| Directs officiels | YouTube Data API v3 | `YOUTUBE_API_KEY` (gratuite, optionnelle) |
| Scores tous sports | SportsAPI | `SPORTSAPI_KEY` (optionnelle) |

Sans clé YouTube, tout fonctionne sauf la recherche automatique de directs. Les recherches YouTube sont mises en cache 15 minutes (une recherche coûte 100 des 10 000 unités gratuites par jour).

## Limites à connaître
- Aucune API gratuite ne donne tous les matchs complets de Liga ou de Ligue des champions. STV SPORT affiche les résumés et les directs officiels réellement disponibles, et le dit sinon.
- Pour diffuser un match complet, ajoute dans l'administration un flux **dont tu as les droits** (`https://…m3u8`, `.mp4` ou lien d'intégration officiel).
- Les services gratuits (TheSportsDB clé de test, ScoreBat) peuvent changer ou limiter leur accès.
- Les logos des clubs appartiennent à leurs propriétaires : ils sont chargés depuis TheSportsDB, pas inclus dans le projet.

## API (documentation : /docs)
`/api/clubs/{barcelona|real-madrid}/videos|live|matches|badge|info`, `/api/clubs/clasico/videos`, `/api/clubs/status`, `/api/matches`, `/api/videos`, `/api/channels`, `/api/sportsapi/*`, `/api/team-logo/{nom}`, `/api/auth/*`, `/api/me/password`.

## Sécurité (déjà en place)
Clé secrète générée automatiquement (`secret.key`), mot de passe admin aléatoire, CORS limité à localhost, lecteur limité aux URL https, flux admin validés, clé API uniquement côté serveur.
Pour un déploiement public : mets l'application derrière HTTPS et sauvegarde `stv_sport.db`.
