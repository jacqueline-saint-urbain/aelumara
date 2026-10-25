#!/usr/bin/env python3
"""Passe de jeu (playtest sweep) pour le moteur d'Aelúmara (tâche 2 de la répartition Spark/Claude).

Fait tourner le moteur RÉEL (sim.py du dépôt aelumara, importé tel quel) pendant
30 jours d'île (720 ticks) à partir d'une fixture fraîche construite ici même.
L'état vivant du dépôt n'est jamais touché : tout se passe en mémoire.

Pour chaque règle du moteur, le script compte combien de fois elle se déclenche.
À la fin, il liste les règles qui ne se sont JAMAIS déclenchées.

Fixture fraîche (départ) :
- tick 0, jour 1, horloge 2026-10-26T03:00:00Z (premier tick = minuit, heure de Toronto selon le décalage fixe -4 du moteur)
- pot commun : 12 coquillages ; réserves : bois 0, fibre 0, nourriture 6
- nœuds de ressources pleins (stock au maximum prévu par le moteur)
- radeau : 0/30 bois, 0/12 fibre, statut « building »
- résidents : besoins faim 50, énergie 80, compagnie 50 ; aucun porté, 0 livraison, 0 coquillage
- positions de départ : chacun chez soi (Bram hutte 1, Sélie hutte 2, Nilo au feu)
- Livre vide, compteur de feux à 0

La boucle de ticks reproduit exactement celle de sim.py main() :
graine du générateur = seed * 100003 + tick + 1, un tick = une heure d'île.
"""
import copy
import datetime as dt
import importlib.util
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("aelumara_sim", os.path.join(HERE, "sim.py"))
sim_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim_mod)

TICKS = 720  # 30 jours d'île
SIM_BLOB = sys.argv[1] if len(sys.argv) > 1 else "version du dépôt"
RUN_LABEL = sys.argv[2] if len(sys.argv) > 2 else ""


def fresh_fixture():
    with open(os.path.join(HERE, "state.json"), encoding="utf-8") as f:
        s = json.load(f)
    s["tick"] = 0
    s["day"] = 1
    s["time"] = "2026-10-26T03:00:00Z"
    s["flags"] = {"raft_ready": False}
    s["pot"] = 12
    s["fires"] = 0
    s["today"] = {"delivered": 0, "at_fire": []}
    s["stores"] = {"wood": 0, "fiber": 0, "food": 6}
    for n in s["nodes"]:
        r = n.get("resource")
        if r:
            n["stock"] = float(sim_mod.NODE_MAX[r])
    for p in s["projects"]:
        p["status"] = "building"
        p["have"] = {}
        p.pop("done_tick", None)
    home_pos = {"npc-1": [9, 8], "npc-2": [12, 3], "npc-3": None}  # Nilo : le feu (spots)
    for npc in s["npcs"]:
        npc["needs"] = {"hunger": 50, "energy": 80, "company": 50}
        npc["carry"] = {}
        npc["delivered"] = 0
        npc["shells"] = 0
        npc["task"] = "idle"
        npc["say"] = ""
        npc.pop("stone_day", None)
        if home_pos[npc["id"]] is not None:
            npc["pos"] = list(home_pos[npc["id"]])
    book = {"title": "Le Livre de l'île", "entries": []}
    return s, book


def main():
    state, book = fresh_fixture()
    sim = sim_mod.Sim(state, book)
    # Nilo dort au feu : sa position de départ est celle du feu dans world.json.
    for npc in state["npcs"]:
        if npc["id"] == "npc-3":
            npc["pos"] = list(sim.spots["fire"])

    stats = {
        "ticks": 0,
        "deliveries_to_project_qty": 0,
        "deliveries_to_stores_qty": 0,
        "shell_payments": 0,
        "stone_arrivals": 0,
        "stone_days": set(),
        "book_by_kind": {},
        "fires_counter_end": None,
        "evenings_with_someone": 0,
        "evenings_empty": 0,
        "evenings_all_present": 0,
        "at_fire_by_npc": {},
        "task_counts": {},
        "eat_count": 0,
        "forage_count": 0,
        "sleep_ticks": 0,
        "rest_count": 0,
        "signature_line_fired": 0,
        "hunger_hit_100": 0,
        "energy_hit_0": 0,
        "company_hit_0": 0,
        "needs_min": {"hunger": 101, "energy": 101, "company": 101},
        "needs_max": {"hunger": -1, "energy": -1, "company": -1},
        "node_ever_below_1": set(),
        "node_min_stock": {},
        "pot_min": None,
        "pot_max": None,
        "stores_food_min": None,
        "stores_food_zero_ticks": 0,
        "raft_done_tick": None,
        "raft_done_day": None,
        "post_raft_gather_wood_fiber": 0,
        "post_raft_shell_payments": 0,
        "post_raft_pot_gain": 0,
    }

    last = dt.datetime.fromisoformat(state["time"].replace("Z", "+00:00"))
    prev_book_len = 0
    for i in range(TICKS):
        when = last + dt.timedelta(hours=i + 1)
        hour = sim_mod.local_hour(when)
        # --- instantané avant ---
        pot_b = state["pot"]
        shells_b = {n["id"]: n.get("shells", 0) for n in state["npcs"]}
        deliv_b = {n["id"]: n.get("delivered", 0) for n in state["npcs"]}
        stone_b = {n["id"]: n.get("stone_day") for n in state["npcs"]}
        have_b = sum(state["projects"][0]["have"].values())
        status_b = state["projects"][0]["status"]
        say_b = {n["id"]: n.get("say", "") for n in state["npcs"]}
        food_b = state["stores"]["food"]
        if food_b == 0:
            stats["stores_food_zero_ticks"] += 1

        rng = random.Random(state["seed"] * 100003 + state["tick"] + 1)
        sim.tick(rng, when)
        stats["ticks"] += 1

        # --- comparaisons après ---
        proj = state["projects"][0]
        have_a = sum(proj["have"].values())
        deliv_delta = sum(state["npcs"][k].get("delivered", 0) - deliv_b[state["npcs"][k]["id"]] for k in range(len(state["npcs"])))
        proj_delta = have_a - have_b
        stats["deliveries_to_project_qty"] += proj_delta
        stats["deliveries_to_stores_qty"] += max(0, deliv_delta - proj_delta)
        shell_delta = sum(n.get("shells", 0) - shells_b[n["id"]] for n in state["npcs"])
        stats["shell_payments"] += shell_delta
        for n in state["npcs"]:
            if n.get("stone_day") is not None and n.get("stone_day") != stone_b[n["id"]]:
                stats["stone_arrivals"] += 1
                stats["stone_days"].add(n["stone_day"])
        if status_b != "done" and proj["status"] == "done":
            stats["raft_done_tick"] = state["tick"]
            stats["raft_done_day"] = state["day"]
        raft_done = proj["status"] == "done"
        if raft_done:
            stats["post_raft_shell_payments"] += shell_delta
            if state["pot"] > pot_b:
                stats["post_raft_pot_gain"] += state["pot"] - pot_b

        for e in book["entries"][prev_book_len:]:
            stats["book_by_kind"][e["kind"]] = stats["book_by_kind"].get(e["kind"], 0) + 1
        prev_book_len = len(book["entries"])

        if hour == sim_mod.FIRE_HOURS[-1]:
            present = list(state["today"]["at_fire"])
            if present:
                stats["evenings_with_someone"] += 1
            else:
                stats["evenings_empty"] += 1
            if len(present) == len(state["npcs"]):
                stats["evenings_all_present"] += 1
            for pid in present:
                stats["at_fire_by_npc"][pid] = stats["at_fire_by_npc"].get(pid, 0) + 1

        for n in state["npcs"]:
            t = n.get("task", "?")
            stats["task_counts"][t] = stats["task_counts"].get(t, 0) + 1
            if t == "eat":
                stats["eat_count"] += 1
            elif t == "forage":
                stats["forage_count"] += 1
            elif t == "sleep":
                stats["sleep_ticks"] += 1
            elif t == "rest":
                stats["rest_count"] += 1
            if raft_done and t in ("gather_wood", "gather_fiber"):
                stats["post_raft_gather_wood_fiber"] += 1
            if n.get("line") and n.get("say") == n["line"] and say_b[n["id"]] != n["line"]:
                stats["signature_line_fired"] += 1
            nd = n["needs"]
            for k in ("hunger", "energy", "company"):
                stats["needs_min"][k] = min(stats["needs_min"][k], nd[k])
                stats["needs_max"][k] = max(stats["needs_max"][k], nd[k])
            if nd["hunger"] >= 100:
                stats["hunger_hit_100"] += 1
            if nd["energy"] <= 0:
                stats["energy_hit_0"] += 1
            if nd["company"] <= 0:
                stats["company_hit_0"] += 1

        for nd_ in state["nodes"]:
            r = nd_.get("resource")
            if r:
                cur = nd_["stock"]
                key = nd_["id"]
                if key not in stats["node_min_stock"] or cur < stats["node_min_stock"][key]:
                    stats["node_min_stock"][key] = cur
                if cur < 1:
                    stats["node_ever_below_1"].add(key)

        stats["pot_min"] = state["pot"] if stats["pot_min"] is None else min(stats["pot_min"], state["pot"])
        stats["pot_max"] = state["pot"] if stats["pot_max"] is None else max(stats["pot_max"], state["pot"])
        stats["stores_food_min"] = state["stores"]["food"] if stats["stores_food_min"] is None else min(stats["stores_food_min"], state["stores"]["food"])

    stats["fires_counter_end"] = state.get("fires", 0)
    stats["stone_days"] = sorted(stats["stone_days"])
    stats["node_ever_below_1"] = sorted(stats["node_ever_below_1"])

    rules = [
        ("Achèvement du radeau (statut done + drapeau raft_ready)", 1 if stats["raft_done_tick"] else 0),
        ("Entrée « launching » dans le Livre", stats["book_by_kind"].get("launching", 0)),
        ("Jalons de progression 25/50/75 % dans le Livre", stats["book_by_kind"].get("progress", 0)),
        ("Livraisons au projet (quantité totale)", stats["deliveries_to_project_qty"]),
        ("Paiements d'un coquillage par livraison au projet", stats["shell_payments"]),
        ("Livraisons aux réserves (hors projet)", stats["deliveries_to_stores_qty"]),
        ("Pierre du matin : arrivée de Sélie à 07 h (+1 coquillage au pot)", stats["stone_arrivals"]),
        ("Feu du soir : résumé du soir dans le Livre", stats["book_by_kind"].get("summary", 0)),
        ("Feu du soir : au moins un résident présent", stats["evenings_with_someone"]),
        ("Feu du soir : les trois résidents présents", stats["evenings_all_present"]),
        ("Repas pris aux réserves (tâche eat)", stats["eat_count"]),
        ("Cueillette de baies quand les réserves sont vides (tâche forage)", stats["forage_count"]),
        ("Sommeil avec regain d'énergie (tâche sleep)", stats["sleep_ticks"]),
        ("Repos faute de ressource à ramasser (tâche rest)", stats["rest_count"]),
        ("Phrase signature d'un résident (probabilité 8 % par tick)", stats["signature_line_fired"]),
        ("Faim au plafond (100)", stats["hunger_hit_100"]),
        ("Énergie à zéro", stats["energy_hit_0"]),
        ("Compagnie à zéro", stats["company_hit_0"]),
        ("Nœud de ressource épuisé (stock < 1, donc ignoré par les résidents)", len(stats["node_ever_below_1"])),
        ("Réserves de nourriture à zéro au début d'un tick", stats["stores_food_zero_ticks"]),
        ("Après le radeau : récolte de bois ou de fibre", stats["post_raft_gather_wood_fiber"]),
        ("Après le radeau : paiement d'un coquillage", stats["post_raft_shell_payments"]),
    ]

    out = []
    out.append(f"PASSE DE JEU — Aelúmara, moteur sim.py (dépôt aelumara, blob du moteur {SIM_BLOB})")
    if RUN_LABEL:
        out.append(f"Contexte : {RUN_LABEL}")
    out.append(f"Course : {stats['ticks']} ticks = 30 jours d'île, fixture fraîche (voir en-tête de playtest_sweep.py), état vivant jamais touché.")
    out.append("")
    out.append("DÉCLENCHEMENTS PAR RÈGLE")
    for name, count in rules:
        out.append(f"- {name} : {count}")
    out.append("")
    out.append("RÈGLES JAMAIS DÉCLENCHÉES")
    never = [name for name, count in rules if count == 0]
    if never:
        for name in never:
            out.append(f"- {name}")
    else:
        out.append("- (aucune)")
    out.append("")
    out.append("FAITS SAILLANTS")
    out.append(f"- Radeau terminé : tick {stats['raft_done_tick']}, jour {stats['raft_done_day']} (drapeau raft_ready = {state['flags'].get('raft_ready')}).")
    out.append(f"- Livre : {len(book['entries'])} entrées, par genre : {json.dumps(stats['book_by_kind'], ensure_ascii=False, sort_keys=True)}.")
    out.append(f"- Compteur de feux (state.fires) à la fin : {stats['fires_counter_end']} ; soirs avec au moins un présent : {stats['evenings_with_someone']} ; soirs vides : {stats['evenings_empty']} ; soirs au complet : {stats['evenings_all_present']}.")
    out.append(f"- Présences au feu par résident (sur 30 soirs) : {json.dumps(stats['at_fire_by_npc'], ensure_ascii=False, sort_keys=True)}.")
    out.append(f"- Pierre du matin : {stats['stone_arrivals']} arrivées, sur {len(stats['stone_days'])} jours distincts.")
    out.append(f"- Pot commun : min {stats['pot_min']}, max {stats['pot_max']}, fin {state['pot']} ; coquillages gagnés par les résidents : {stats['shell_payments']} ; après le radeau, le pot a encore gagné {stats['post_raft_pot_gain']} (pierre du matin) sans aucune dépense possible.")
    out.append(f"- Réserves à la fin : {json.dumps(state['stores'], ensure_ascii=False)} ; nourriture au plus bas : {stats['stores_food_min']}.")
    out.append(f"- Besoins observés (min/max) : faim {stats['needs_min']['hunger']}/{stats['needs_max']['hunger']}, énergie {stats['needs_min']['energy']}/{stats['needs_max']['energy']}, compagnie {stats['needs_min']['company']}/{stats['needs_max']['company']}.")
    out.append(f"- Tâches observées : {json.dumps(stats['task_counts'], ensure_ascii=False, sort_keys=True)}.")
    out.append(f"- Stocks de nœuds au plus bas : {json.dumps(stats['node_min_stock'], ensure_ascii=False, sort_keys=True)}.")
    out.append(f"- État final : tick {state['tick']}, jour {state['day']}, heure d'île {state['time']}.")
    report = "\n".join(out) + "\n"
    with open(os.path.join(HERE, "playtest_sweep.log"), "w", encoding="utf-8") as f:
        f.write(report)
    print(report)


if __name__ == "__main__":
    main()
