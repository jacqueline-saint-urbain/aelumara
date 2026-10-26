# Aelúmara

Aelúmara is a small simulated world: an archipelago, a first island, three residents, a raft under construction and a Book that tells everything.

The name blends two words from an invented language: *Aelumë*, "the light that shelters", and *Velúmara*, "where the sea slows down". It is pronounced a-eh-loo-MA-ra.

## Watching the world

The page `index.html` shows the island in 3D, the residents' dashboard and the Book of the Island. The simulation engine (`sim.py`) moves the world's time forward, one tick at a time, and writes the result to `state.json` and `book.json`. A GitHub Actions robot runs it every hour and records each tick.

- `world.json`: the geography and objects of the island.
- `state.json`: the living state of the world (residents, resources, projects).
- `book.json`: the Book of the Island, the chronicle of events.
- `SOCIETY.md`: the residents, rituals, economy and proposed laws.
- `WORLD.md`: the world protocol.
