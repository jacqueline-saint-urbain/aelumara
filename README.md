# Aelumara

Aelumara est un petit monde simulé : un archipel, une première île, trois résidents, un radeau en construction et un Livre qui raconte tout.

Le nom fond deux mots d'une langue inventée : *Aelumë*, « la lumière qui abrite », et *Velúmara*, « là où la mer ralentit ». Il se prononce a-é-lou-MA-ra.

## Regarder le monde

La page `index.html` affiche l'île en 3D, le tableau de bord des résidents et le Livre de l'île. Le moteur de simulation (`sim.py`) fait avancer le temps du monde, un tour à la fois, et écrit le résultat dans `state.json` et `book.json` — un robot GitHub Actions le lance chaque heure et enregistre chaque tour.

- `world.json` : la géographie et les objets de l'île.
- `state.json` : l'état vivant du monde (résidents, ressources, projets).
- `book.json` : le Livre de l'île, la chronique des événements.
- `SOCIETY.md` : les résidents, les rituels, l'économie et les lois proposées.
- `WORLD.md` : le protocole du monde.
