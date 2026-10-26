#!/usr/bin/env python3
"""Playtest sweep for the Aelúmara engine (task 2 of the Spark/Claude split).

Runs the REAL engine (sim.py from the aelumara repository, imported as-is) for
30 island days (720 ticks) from a fresh fixture built right here.
The repository's live state is never touched: everything happens in memory.

For each engine rule, the script counts how many times it fires.
At the end, it lists the rules that NEVER fired.

Fresh fixture (start):
- tick 0, day 1, clock 2026-10-26T03:00:00Z (first tick = midnight, Toronto time according to the engine's fixed -4 offset)
- shared pot: 12 shells; stores: wood 0, fiber 0, food 6
- resource nodes full (stock at the maximum set by the engine)
- raft: 0/30 wood, 0/12 fiber, status "building"
- residents: needs hunger 50, energy 80, company 50; nothing carried, 0 deliveries, 0 shells
- starting positions: each at home (Bram hut 1, Sélie hut 2, Nilo at the fire)
- Empty book, fire counter at 0

The tick loop reproduces exactly the one in sim.py main():
generator seed = seed * 100003 + tick + 1, one tick = one island hour.
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

TICKS = 720  # 30 island days
SIM_BLOB = sys.argv[1] if len(sys.argv) > 1 else "repository version"
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
    home_pos = {"npc-1": [9, 8], "npc-2": [12, 3], "npc-3": None}  # Nilo: the fire (spots)
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
    book = {"title": "The Book of the Island", "entries": []}
    return s, book


def main():
    state, book = fresh_fixture()
    sim = sim_mod.Sim(state, book)
    # Nilo sleeps at the fire: his starting position is the fire's in world.json.
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
        # --- snapshot before ---
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

        # --- comparisons after ---
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
        ("Raft completion (status done + raft_ready flag)", 1 if stats["raft_done_tick"] else 0),
        ("\"launching\" entry in the Book", stats["book_by_kind"].get("launching", 0)),
        ("Progress milestones 25/50/75% in the Book", stats["book_by_kind"].get("progress", 0)),
        ("Deliveries to the project (total quantity)", stats["deliveries_to_project_qty"]),
        ("One-shell payments per delivery to the project", stats["shell_payments"]),
        ("Deliveries to stores (outside the project)", stats["deliveries_to_stores_qty"]),
        ("Morning stone: Sélie arrives at 07:00 (+1 shell to the pot)", stats["stone_arrivals"]),
        ("Evening fire: evening summary in the Book", stats["book_by_kind"].get("summary", 0)),
        ("Evening fire: at least one resident present", stats["evenings_with_someone"]),
        ("Evening fire: all three residents present", stats["evenings_all_present"]),
        ("Meals taken from stores (eat task)", stats["eat_count"]),
        ("Berry gathering when stores are empty (forage task)", stats["forage_count"]),
        ("Sleep with energy regain (sleep task)", stats["sleep_ticks"]),
        ("Rest for lack of a resource to gather (rest task)", stats["rest_count"]),
        ("Resident signature line (8% probability per tick)", stats["signature_line_fired"]),
        ("Hunger at the ceiling (100)", stats["hunger_hit_100"]),
        ("Energy at zero", stats["energy_hit_0"]),
        ("Company at zero", stats["company_hit_0"]),
        ("Resource node depleted (stock < 1, so ignored by residents)", len(stats["node_ever_below_1"])),
        ("Food stores at zero at the start of a tick", stats["stores_food_zero_ticks"]),
        ("After the raft: wood or fiber gathering", stats["post_raft_gather_wood_fiber"]),
        ("After the raft: one-shell payment", stats["post_raft_shell_payments"]),
    ]

    out = []
    out.append(f"PLAYTEST SWEEP — Aelúmara, sim.py engine (aelumara repository, engine blob {SIM_BLOB})")
    if RUN_LABEL:
        out.append(f"Context: {RUN_LABEL}")
    out.append(f"Run: {stats['ticks']} ticks = 30 island days, fresh fixture (see the header of playtest_sweep.py), live state never touched.")
    out.append("")
    out.append("RULE FIRINGS")
    for name, count in rules:
        out.append(f"- {name}: {count}")
    out.append("")
    out.append("RULES THAT NEVER FIRED")
    never = [name for name, count in rules if count == 0]
    if never:
        for name in never:
            out.append(f"- {name}")
    else:
        out.append("- (none)")
    out.append("")
    out.append("HIGHLIGHTS")
    out.append(f"- Raft completed: tick {stats['raft_done_tick']}, day {stats['raft_done_day']} (raft_ready flag = {state['flags'].get('raft_ready')}).")
    out.append(f"- Book: {len(book['entries'])} entries, by kind: {json.dumps(stats['book_by_kind'], ensure_ascii=False, sort_keys=True)}.")
    out.append(f"- Fire counter (state.fires) at the end: {stats['fires_counter_end']}; evenings with at least one resident present: {stats['evenings_with_someone']}; empty evenings: {stats['evenings_empty']}; full evenings: {stats['evenings_all_present']}.")
    out.append(f"- Fire attendance by resident (over 30 evenings): {json.dumps(stats['at_fire_by_npc'], ensure_ascii=False, sort_keys=True)}.")
    out.append(f"- Morning stone: {stats['stone_arrivals']} arrivals, over {len(stats['stone_days'])} distinct days.")
    out.append(f"- Shared pot: min {stats['pot_min']}, max {stats['pot_max']}, end {state['pot']}; shells earned by residents: {stats['shell_payments']}; after the raft, the pot gained another {stats['post_raft_pot_gain']} (morning stone) with no possible expense.")
    out.append(f"- Final stores: {json.dumps(state['stores'], ensure_ascii=False)}; lowest food: {stats['stores_food_min']}.")
    out.append(f"- Needs observed (min/max): hunger {stats['needs_min']['hunger']}/{stats['needs_max']['hunger']}, energy {stats['needs_min']['energy']}/{stats['needs_max']['energy']}, company {stats['needs_min']['company']}/{stats['needs_max']['company']}.")
    out.append(f"- Tasks observed: {json.dumps(stats['task_counts'], ensure_ascii=False, sort_keys=True)}.")
    out.append(f"- Lowest node stocks: {json.dumps(stats['node_min_stock'], ensure_ascii=False, sort_keys=True)}.")
    out.append(f"- Final state: tick {state['tick']}, day {state['day']}, island time {state['time']}.")
    report = "\n".join(out) + "\n"
    with open(os.path.join(HERE, "playtest_sweep.log"), "w", encoding="utf-8") as f:
        f.write(report)
    print(report)


if __name__ == "__main__":
    main()
