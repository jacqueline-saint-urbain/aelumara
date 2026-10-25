#!/usr/bin/env python3
"""Trio Island simulation engine (world/2).

Advances world/state.json by one tick per real hour elapsed since the last
run (capped at 48), so island time follows real time. Deterministic: the
random generator is seeded from the tick number, so a given state always
produces the same next state.

State written: world/state.json. Chronicle appended: world/book.json.
Agents' hand-placed pieces stay in world/world.json and are never touched.

Usage: python3 world/sim.py [--ticks N] [--now ISO8601]
"""
import argparse
import datetime as dt
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")
BOOK = os.path.join(HERE, "book.json")
TZ_OFFSET_HOURS = -4  # America/Toronto (EDT); only used for night hours
MAX_TICKS = 48
SPEED = 6.0  # map units per tick

HUNGER_RATE = 5
ENERGY_RATE = 4
COMPANY_RATE = 1
FIRE_HOURS = (19, 20, 21)  # le feu du soir (Toronto time)
STONE_HOUR = 7            # la pierre du matin
NODE_REGROW = {"wood": 0.25, "food": 0.4, "fiber": 0.3}
NODE_MAX = {"wood": 20, "food": 12, "fiber": 12}


def load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def step_toward(pos, target, speed=SPEED):
    d = dist(pos, target)
    if d <= speed:
        return [round(target[0], 2), round(target[1], 2)], True
    f = speed / d
    return [round(pos[0] + (target[0] - pos[0]) * f, 2), round(pos[1] + (target[1] - pos[1]) * f, 2)], False


def local_hour(tick_time):
    return (tick_time + dt.timedelta(hours=TZ_OFFSET_HOURS)).hour


def is_night(tick_time):
    h = local_hour(tick_time)
    return h >= 22 or h < 6


def load_world_spots():
    """Read-only: positions of the agents' campfire and idea stone in world.json."""
    w = load(os.path.join(HERE, "world.json"), {"entities": []})
    spots = {}
    for e in w.get("entities", []):
        if e.get("type") == "campfire" and "fire" not in spots:
            spots["fire"] = e["pos"]
        if e.get("id") == "claude-005" or e.get("label") == "Pierre aux idées":
            spots["stone"] = e["pos"]
    spots.setdefault("fire", [0, 0])
    spots.setdefault("stone", spots["fire"])
    return spots


class Sim:
    def __init__(self, state, book):
        self.s = state
        self.book = book
        self.events = []
        self.spots = load_world_spots()

    # ---------- chronicle ----------
    def chronicle(self, text, kind="event"):
        entry = {"tick": self.s["tick"], "day": self.s["day"], "at": self.s["time"], "by": "sim", "kind": kind, "text": text}
        self.book["entries"].append(entry)
        self.events.append(text)

    # ---------- helpers ----------
    def node(self, nid):
        return next(n for n in self.s["nodes"] if n["id"] == nid)

    def nearest_node(self, pos, resource):
        candidates = [n for n in self.s["nodes"] if n.get("resource") == resource and n.get("stock", 0) >= 1]
        if not candidates:
            return None
        return min(candidates, key=lambda n: dist(pos, n["pos"]))

    def active_project(self):
        return next((p for p in self.s["projects"] if p["status"] == "building"), None)

    def missing(self, project):
        return {r: q - project["have"].get(r, 0) for r, q in project["needs"].items() if project["have"].get(r, 0) < q}

    # ---------- one tick ----------
    def tick(self, rng, when):
        s = self.s
        s["tick"] += 1
        s["time"] = when.strftime("%Y-%m-%dT%H:%M:%SZ")
        new_day = s["tick"] // 24 + 1
        if new_day != s["day"]:
            s["day"] = new_day
            s["today"] = {"delivered": 0, "at_fire": []}
        s.setdefault("today", {"delivered": 0, "at_fire": []})
        hour = local_hour(when)

        for n in s["nodes"]:
            r = n.get("resource")
            if r:
                n["stock"] = round(min(NODE_MAX[r], n.get("stock", 0) + NODE_REGROW[r]), 2)

        night = is_night(when)
        for npc in s["npcs"]:
            self.act(npc, rng, night, hour)
            # Whoever is at the fire during the evening counts as present, asleep or not.
            if hour in FIRE_HOURS and dist(npc["pos"], self.spots["fire"]) < 1 and npc["id"] not in s["today"]["at_fire"]:
                s["today"]["at_fire"].append(npc["id"])
        if hour == FIRE_HOURS[-1]:
            self.evening_fire()

        proj = self.active_project()
        if proj and not self.missing(proj):
            proj["status"] = "done"
            proj["done_tick"] = s["tick"]
            present = ", ".join(n["name"] for n in s["npcs"])
            self.chronicle(f"Le premier pas. Le {proj['name']} est terminé et glisse jusqu'à l'eau sous les yeux de {present}. Il attend sur la plage nord, prêt à prendre la mer vers l'île de l'horizon.", "launching")
            if proj["id"] == "raft":
                s["flags"]["raft_ready"] = True

    def home_pos(self, npc):
        return self.spots["fire"] if npc["home"] == "fire" else self.node(npc["home"])["pos"]

    def evening_fire(self):
        st = self.s
        here = st["today"]["at_fire"]
        names = [n["name"] for n in st["npcs"] if n["id"] in here]
        missing = [n["name"] for n in st["npcs"] if n["id"] not in here]
        proj = self.active_project() or next((p for p in st["projects"] if p["id"] == "raft"), None)
        pr = 100 if proj and proj["status"] == "done" else (self.progress(proj) if proj else 0)
        line = f"Le feu du soir réunit {', '.join(names) if names else 'personne'}. Aujourd'hui : {st['today']['delivered']} ressources livrées, radeau à {pr} %. Coquillages au pot : {st['pot']}."
        if missing:
            line += f" Absents : {', '.join(missing)}."
        st["fires"] = st.get("fires", 0) + (1 if names else 0)
        self.chronicle(line, "summary")

    def act(self, npc, rng, night, hour):
        st = self.s
        n = npc["needs"]
        n["hunger"] = min(100, n["hunger"] + HUNGER_RATE)
        n["company"] = max(0, n["company"] - COMPANY_RATE * npc.get("company_rate", 1))
        home = self.home_pos(npc)
        speed = SPEED + npc.get("speed_bonus", 0)
        if npc.get("line") and rng.random() < 0.08:
            npc["say"] = npc["line"]

        # Sleep at night or when exhausted.
        if night or n["energy"] < 20 or npc["task"] == "sleep" and n["energy"] < 85:
            npc["pos"], arrived = step_toward(npc["pos"], home, speed)
            if arrived:
                if npc["task"] != "sleep":
                    npc["say"] = "Bonne nuit."
                npc["task"] = "sleep"
                n["energy"] = min(100, n["energy"] + 12)
            else:
                npc["task"] = "go_home"
            return
        n["energy"] = max(0, n["energy"] - ENERGY_RATE * npc.get("rest_rate", 1))

        # La pierre du matin: the shell keeper leaves one shell on the idea stone.
        if hour == STONE_HOUR and npc.get("ritual") == "stone" and npc.get("stone_day") != st["day"]:
            npc["pos"], arrived = step_toward(npc["pos"], self.spots["stone"], speed)
            npc["task"] = "stone"
            if arrived:
                npc["stone_day"] = st["day"]
                st["pot"] += 1
                npc["say"] = "Un coquillage sur la pierre."
            return

        # Le feu du soir: everyone gathers at the campfire.
        if hour in FIRE_HOURS:
            npc["pos"], arrived = step_toward(npc["pos"], self.spots["fire"], speed)
            npc["task"] = "fire"
            if arrived:
                n["company"] = min(100, n["company"] + 15)
                if npc["id"] not in st["today"]["at_fire"]:
                    st["today"]["at_fire"].append(npc["id"])
            return

        # Eat from the stores, or forage when they are empty.
        if n["hunger"] >= 60:
            if st["stores"]["food"] >= 1:
                st["stores"]["food"] = round(st["stores"]["food"] - 1, 2)
                n["hunger"] = max(0, n["hunger"] - 50)
                npc["task"] = "eat"
                npc["say"] = "Un repas aux réserves."
                return
            bush = self.nearest_node(npc["pos"], "food")
            if bush:
                npc["pos"], arrived = step_toward(npc["pos"], bush["pos"], speed)
                npc["task"] = "forage"
                if arrived:
                    bush["stock"] = round(bush["stock"] - 1, 2)
                    n["hunger"] = max(0, n["hunger"] - 40)
                    npc["say"] = "Des baies !"
                return

        # Carrying something: bring it where it is needed.
        carry = npc["carry"]
        if carry:
            res, qty = next(iter(carry.items()))
            proj = self.active_project()
            dest = proj["pos"] if proj and res in self.missing(proj) else self.node("stores")["pos"]
            npc["pos"], arrived = step_toward(npc["pos"], dest, speed)
            npc["task"] = "deliver"
            if arrived:
                if proj and res in self.missing(proj):
                    before = self.progress(proj)
                    proj["have"][res] = proj["have"].get(res, 0) + qty
                    self.milestones(proj, before)
                    if st["pot"] >= 1:  # a work shift on a shared project earns a shell
                        st["pot"] -= 1
                        npc["shells"] = npc.get("shells", 0) + 1
                else:
                    st["stores"][res] = round(st["stores"].get(res, 0) + qty, 2)
                npc["carry"] = {}
                npc["delivered"] = npc.get("delivered", 0) + qty
                st["today"]["delivered"] += qty
            return

        # Choose work: what the project lacks, else food for the stores.
        proj = self.active_project()
        wants = []
        if proj:
            wants = sorted(self.missing(proj), key=lambda r: -self.missing(proj)[r])
        if st["stores"]["food"] < 6:
            wants.insert(0, "food")
        if not wants:
            wants = ["food"]
        pref = npc.get("likes")
        if pref in wants and rng.random() < 0.6:
            wants.remove(pref)
            wants.insert(0, pref)
        for res in wants:
            target = self.nearest_node(npc["pos"], res)
            if not target:
                continue
            npc["pos"], arrived = step_toward(npc["pos"], target["pos"], speed)
            npc["task"] = "gather_" + res
            if arrived:
                amount = 3 if npc.get("talent") == res else 2
                take = min(amount, int(target["stock"]))
                if take >= 1:
                    target["stock"] = round(target["stock"] - take, 2)
                    npc["carry"] = {res: take}
                    npc["say"] = {"wood": "Du bois pour le radeau.", "fiber": "Des fibres pour les cordes.", "food": "Des baies pour tout le monde."}[res]
            return
        npc["task"] = "rest"
        npc["say"] = "Rien à ramasser pour l'instant."

    def progress(self, proj):
        total = sum(proj["needs"].values())
        have = sum(min(proj["have"].get(r, 0), q) for r, q in proj["needs"].items())
        return round(100 * have / total)

    def milestones(self, proj, before):
        after = self.progress(proj)
        for m in (25, 50, 75):
            if before < m <= after:
                self.chronicle(f"Le {proj['name']} est construit à {m} %.", "progress")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, help="advance exactly N ticks")
    ap.add_argument("--now", help="current time (ISO 8601 UTC), default now")
    args = ap.parse_args()

    state = load(STATE, None)
    if state is None:
        raise SystemExit("world/state.json missing")
    book = load(BOOK, {"title": "Le Livre de l'île", "entries": []})

    now = dt.datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else dt.datetime.now(dt.timezone.utc)
    last = dt.datetime.fromisoformat(state["time"].replace("Z", "+00:00"))
    n = args.ticks if args.ticks is not None else int((now - last).total_seconds() // 3600)
    n = max(0, min(MAX_TICKS, n))

    sim = Sim(state, book)
    for i in range(n):
        when = last + dt.timedelta(hours=i + 1)
        rng = random.Random(state["seed"] * 100003 + state["tick"] + 1)
        sim.tick(rng, when)

    save(STATE, state)
    save(BOOK, book)
    print(f"advanced {n} tick(s) -> tick {state['tick']}, day {state['day']}; events: {len(sim.events)}")
    for e in sim.events:
        print(" -", e)


if __name__ == "__main__":
    main()
