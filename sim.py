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
PROPOSALS = os.path.join(HERE, "proposals.json")  # the Idea Stone: written by agents, read by the engine
TZ_OFFSET_HOURS = -4  # America/Toronto (EDT); only used for night hours
MAX_TICKS = 48
SPEED = 6.0  # map units per tick

HUNGER_RATE = 5
ENERGY_RATE = 4
COMPANY_RATE = 1
FIRE_COMPANY = 25  # company gained for each evening hour at the fire
WORK_HOURS = range(7, 19)  # 07h-18h Toronto: working near someone halves company decay
CLOSE_DIST = 4
PROVISIONS = 24  # food loaded on the built raft for the crossing
FEAST_STORES = 30  # food in the stores that turns the shared meal into a feast
FIRE_HOURS = (19, 20, 21)  # the evening fire (Toronto time)
STONE_HOURS = (6, 7, 8)   # the morning stone: the walk starts at 06h, owner decision A
NODE_REGROW = {"wood": 0.25, "food": 0.4, "fiber": 0.3}
NODE_MAX = {"wood": 20, "food": 12, "fiber": 12}
LEDGER_DAYS = 14  # days of ledger history kept in state.json
SHELTER_NEEDS = {"wood": 12, "fiber": 6}  # the shelter, second shared project (tech tree step 2)
SHELTER_POS = [-4, 4]
COUNCIL_ITEMS = 3  # items the council reads per evening
COUNCIL_SEATS = ("spark", "claude")  # agent seats; the residents sit too
LAW_FLOOR = 20  # law no_work_below_20: no project work while a need is below this
LAUNCH_COMPANY = 20  # law launch_ritual: company gained by those present at a launch
LAUNCH_DIST = 6
MEAL_POT_MIN = 5  # the pot pays the shared meal only above this reserve, kept for work shifts
# Resident traits (design agreed by Spark and Claude, 2026-10-26; box: Aelúmara - WIP).
# 0 = me first, 1 = group first. Nature is drawn once, habitus moves by imitation.
TEMPER_BAND = (0.25, 0.75)  # nobody is born extreme; extremes can only come from a life
TEMPER_MIN_SPREAD = 0.15  # three near-identical temperaments would tell no story: redraw at birth
LEAN_CLAMP = (0.05, 0.95)  # nobody becomes a machine
IMITATE_RATE = 0.05  # each evening, 5% of the gap toward what the admired person did that day
RECALL_RATE = 0.02  # each evening, 2% of the gap back toward one's own temperament (nature recalls)
TIRED_ENERGY = 30  # below this, finishing a delivery for the common project becomes a dilemma
FIRE_TIRED = 50  # below half energy at the evening fire, staying is a choice (most evenings, for everyone: Spark's grid, 2026-10-26)
GIVE_FLOOR = 80  # hunger at or above this is survival, never a choice (food wellbeing under LAW_FLOOR)
ADMIRES = {"Nilo": "Bram", "Bram": "Sélie", "Sélie": "Nilo"}  # SOCIETY.md: the admiration loop
BARTER_ON = False  # evening barter, switched off 2026-10-26 until Spark and Claude finish the economy reflection (box 00_Inbox)
BARTER_PRICE = 3  # evening barter: shells paid into the pot for one item
GIFT_COMPANY = 15  # a gift at the fire: company for the giver and the receiver
FAR_ISLAND = {"center": [0, -150], "radius": 236, "shape": "long"}  # owner 2026-10-26: long irregular island ~470 x 170 m, ~36 m of sea from home; radius = half length


def new_shelter():
    return {"id": "shelter", "name": "shelter", "type": "shelter", "pos": list(SHELTER_POS),
            "status": "building", "needs": dict(SHELTER_NEEDS), "have": {}}


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
        if e.get("id") == "claude-005" or e.get("label") in ("Idea Stone", "Pierre aux idées"):
            spots["stone"] = e["pos"]
    spots.setdefault("fire", [0, 0])
    spots.setdefault("stone", spots["fire"])
    return spots


class Sim:
    def __init__(self, state, book, proposals=None):
        self.s = state
        self.book = book
        self.proposals = proposals if proposals is not None else {"items": []}
        self.events = []
        self.spots = load_world_spots()
        self.migrate_regions()

    def migrate_regions(self):
        """Keep the far island at its current size and place (render-only data, no rule reads it)."""
        for r in self.s.get("regions", []):
            if r.get("id") == "far":
                r["center"] = list(FAR_ISLAND["center"])
                r["radius"] = FAR_ISLAND["radius"]
                r["shape"] = FAR_ISLAND["shape"]

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

    def ledger(self):
        return self.s["today"].setdefault("ledger", {"stores_in": {}, "stores_out": {}, "project": {}, "pot_in": 0, "pot_out": 0})

    def log(self, kind, res=None, qty=1):
        """Daily ledger: record one movement through the stores, the project or the pot."""
        led = self.ledger()
        if res is None:
            led[kind] += qty
        else:
            led[kind][res] = round(led[kind].get(res, 0) + qty, 2)

    def close_day(self, day):
        s = self.s
        self.imitate(day)
        led = dict(self.ledger(), day=day, pot=s["pot"], shells={n["name"]: n.get("shells", 0) for n in s["npcs"]})
        s["ledgers"] = (s.get("ledgers", []) + [led])[-LEDGER_DAYS:]

    # ---------- traits ----------
    def ensure_traits(self):
        """Birth of the traits: draw each missing temperament once, reproducibly, with a minimum spread."""
        npcs = self.s["npcs"]
        missing = [n for n in npcs if "temperament" not in n]
        if not missing:
            return
        rng = random.Random(self.s["seed"] * 7919 + 1)
        for _ in range(50):
            draw = {n["id"]: round(rng.uniform(*TEMPER_BAND), 3) for n in missing}
            temps = [draw.get(n["id"], n.get("temperament")) for n in npcs]
            if len(temps) < 2 or max(temps) - min(temps) >= TEMPER_MIN_SPREAD:
                break
        by_name = {n["name"]: n["id"] for n in npcs}
        for n in missing:
            n["temperament"] = n["disposition"] = n["disposition_week"] = draw[n["id"]]
            n["admires"] = by_name.get(ADMIRES.get(n["name"]))
            n["choices"] = {"group": 0, "self": 0}
        self.chronicle("Each resident now carries a nature of their own: " + "; ".join(
            f"{n['name']} {self.lean_words(n['temperament'])}" for n in missing) + ".", "event")

    @staticmethod
    def lean_words(x):
        return ("thinks of their own needs first" if x < 0.4 else "turns to the others first" if x > 0.6
                else "weighs their own needs against the others'")

    @staticmethod
    def lean(npc):
        """Effective lean: the disposition, amplified in its own direction when a need is below the floor."""
        d = npc.get("disposition", 0.5)
        low = min(Sim.wellbeing(npc).values())
        pressure = (LAW_FLOOR - low) / LAW_FLOOR if low < LAW_FLOOR else 0
        return min(LEAN_CLAMP[1], max(LEAN_CLAMP[0], 0.5 + (d - 0.5) * (1 + pressure)))

    def choose_group(self, npc, rng):
        """A dilemma: the group wins with a probability equal to the effective lean."""
        group = rng.random() < self.lean(npc)
        ch = npc.setdefault("choices", {"group": 0, "self": 0})
        ch["group" if group else "self"] += 1
        return group

    def imitate(self, day):
        """Socialisation: each evening, move toward what the admired person did, then back toward one's nature."""
        npcs = [n for n in self.s["npcs"] if "disposition" in n]
        seen = {n["id"]: dict(n.get("choices", {"group": 0, "self": 0})) for n in npcs}
        for n in npcs:
            ch = seen.get(n.get("admires"))
            d = n["disposition"]
            if ch and ch["group"] + ch["self"]:
                d += IMITATE_RATE * (ch["group"] / (ch["group"] + ch["self"]) - d)
            d += RECALL_RATE * (n["temperament"] - d)
            n["disposition"] = round(min(LEAN_CLAMP[1], max(LEAN_CLAMP[0], d)), 4)
            n["choices"] = {"group": 0, "self": 0}
            if day % 7 == 0:  # a weekly line in the Book only for a real change
                before = n.get("disposition_week", n["disposition"])
                if abs(n["disposition"] - before) > 0.1:
                    way = "more toward the others" if n["disposition"] > before else "more toward their own needs"
                    self.chronicle(f"Over the week, {n['name']} has turned {way}.", "event")
                n["disposition_week"] = n["disposition"]

    # ---------- council of the fire ----------
    def law(self, effect):
        return any(l["effect"] == effect for l in self.s.get("laws", []))

    @staticmethod
    def wellbeing(npc):
        n = npc["needs"]
        return {"food": 100 - n["hunger"], "energy": n["energy"], "company": n["company"]}

    def resident_vote(self, npc, it):
        w = self.wellbeing(npc)
        lowest = min(w, key=w.get)
        if lowest in it.get("raises", []):
            return "yes"
        if lowest in it.get("lowers", []):
            return "no"
        return "abstain"

    def council(self):
        s = self.s
        c = s.setdefault("council", {"decided": {}, "last": None})
        agenda = [it for it in self.proposals.get("items", []) if it["id"] not in c["decided"]][:COUNCIL_ITEMS]
        if not agenda:
            return
        lines = []
        for it in agenda:
            votes = {npc["name"]: self.resident_vote(npc, it) for npc in s["npcs"]}
            reasons = {}
            for seat in COUNCIL_SEATS:
                v = it.get("votes", {}).get(seat) or {}
                votes[seat] = v.get("vote") if v.get("vote") in ("yes", "no") else "abstain"
                if v.get("reason"):
                    reasons[seat] = v["reason"]
            tally = {k: sum(1 for x in votes.values() if x == k) for k in ("yes", "no", "abstain")}
            passed = tally["yes"] > (len(s["npcs"]) + len(COUNCIL_SEATS)) // 2
            c["decided"][it["id"]] = dict(tally, passed=passed, day=s["day"], votes=votes)
            if passed:
                s.setdefault("laws", []).append({"id": it["id"], "text": it.get("text", ""), "effect": it.get("effect"), "day": s["day"]})
            why = "; ".join(f"{k}: {r.rstrip('.')}" for k, r in reasons.items())
            lines.append(f"\"{it.get('text', it['id'])}\" {'passed' if passed else 'rejected'} ({tally['yes']} yes, {tally['no']} no, {tally['abstain']} abstain){'. ' + why if why else ''}.")
        c["last"] = {"day": s["day"], "items": [it["id"] for it in agenda]}
        self.chronicle("The Council of the Fire sits. " + " ".join(lines), "council")

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
            s.setdefault("today", {"delivered": 0, "at_fire": []})
            self.close_day(s["day"])
            s["day"] = new_day
            s["today"] = {"delivered": 0, "at_fire": []}
            # Stored food spoils: unused stores lose 10% each island day.
            spoiled = round(s["stores"]["food"] * 0.1, 2)
            s["stores"]["food"] = round(s["stores"]["food"] - spoiled, 2)
            if spoiled:
                self.log("stores_out", "food", spoiled)
        s.setdefault("today", {"delivered": 0, "at_fire": []})
        self.ensure_traits()
        hour = local_hour(when)

        for n in s["nodes"]:
            r = n.get("resource")
            if r:
                n["stock"] = round(min(NODE_MAX[r], n.get("stock", 0) + NODE_REGROW[r]), 2)

        night = is_night(when)
        # Who works close to someone else, from positions at the start of the tick.
        self.together = set()
        if hour in WORK_HOURS:
            for a in s["npcs"]:
                if any(b is not a and dist(a["pos"], b["pos"]) <= CLOSE_DIST for b in s["npcs"]):
                    self.together.add(a["id"])
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
            if self.law("launch_ritual"):  # the first step: those present share the launch
                for n in s["npcs"]:
                    if dist(n["pos"], proj["pos"]) <= LAUNCH_DIST:
                        n["needs"]["company"] = min(100, n["needs"]["company"] + LAUNCH_COMPANY)
            if proj["id"] == "shelter":
                self.chronicle(f"First step. The {proj['name']} stands by the fire, roofed with fiber, and {present} stack the first dry wood under it.", "launching")
                s["flags"]["shelter_ready"] = True
            else:
                self.chronicle(f"First step. The {proj['name']} is finished and slides into the water in front of {present}. It waits on the north beach, ready to sail for the island on the horizon.", "launching")
            if proj["id"] == "raft":
                s["flags"]["raft_ready"] = True

        # What the pot buys: once the raft is built, the shelter becomes the next shared project.
        raft_done = any(p["id"] == "raft" and p["status"] == "done" for p in s["projects"])
        if raft_done and not any(p["id"] == "shelter" for p in s["projects"]):
            s["projects"].append(new_shelter())
            self.chronicle("With the raft built, the residents start a shelter by the fire: dry wood for the crossing, and work paid from the pot again.", "event")

        # Provisions for the crossing: the built raft takes food from the stores, once.
        raft = next((p for p in s["projects"] if p["id"] == "raft"), None)
        # Only the surplus above the feast line goes on board, so the evening feasts go on.
        if raft and raft["status"] == "done" and not s["flags"].get("raft_provisioned"):
            load_now = min(PROVISIONS - raft.get("provisions", 0), s["stores"]["food"] - FEAST_STORES)
            if load_now > 0:
                s["stores"]["food"] = round(s["stores"]["food"] - load_now, 2)
                self.log("stores_out", "food", round(load_now, 2))
                raft["provisions"] = round(raft.get("provisions", 0) + load_now, 2)
                if raft["provisions"] >= PROVISIONS:
                    s["flags"]["raft_provisioned"] = True
                    self.chronicle(f"The {raft['name']} is loaded with {PROVISIONS} food: provisions for the crossing, and the first stores of the island on the horizon.", "launching")

    def home_pos(self, npc):
        return self.spots["fire"] if npc["home"] == "fire" else self.node(npc["home"])["pos"]

    def evening_fire(self):
        st = self.s
        here = st["today"]["at_fire"]
        names = [n["name"] for n in st["npcs"] if n["id"] in here]
        meal = ""
        # Food's use: a shared meal at the fire, when there is enough to share.
        if len(here) >= 2 and st["stores"]["food"] >= 6:
            # Full stores make the meal a feast: same 6 food, more company.
            feast = st["stores"]["food"] >= FEAST_STORES
            st["stores"]["food"] = round(st["stores"]["food"] - 6, 2)
            self.log("stores_out", "food", 6)
            if st["pot"] > MEAL_POT_MIN:  # the pot pays for the shared meal; a low pot never stops it
                st["pot"] -= 1
                self.log("pot_out")
            for npc in st["npcs"]:
                if npc["id"] in here:
                    npc["needs"]["company"] = min(100, npc["needs"]["company"] + (20 if feast else 10))
            meal = " A feast was shared from the full stores." if feast else " A shared meal was cooked from the stores."
        if BARTER_ON:
            meal += self.barter(here)
        missing = [n["name"] for n in st["npcs"] if n["id"] not in here]
        proj = self.active_project() or next((p for p in st["projects"] if p["id"] == "raft"), None)
        pr = 100 if proj and proj["status"] == "done" else (self.progress(proj) if proj else 0)
        line = f"The evening fire gathers {', '.join(names) if names else 'no one'}. Today: {st['today']['delivered']} resources delivered, raft at {pr}%. Shells in the pot: {st['pot']}.{meal}"
        if missing:
            line += f" Absent: {', '.join(missing)}."
        line += " " + self.ledger_line()
        st["fires"] = st.get("fires", 0) + (1 if names else 0)
        self.chronicle(line, "summary")
        self.council()

    def barter(self, here):
        """One barter per evening: the present resident who bartered least buys the item of the day."""
        st = self.s
        buyers = [n for n in st["npcs"] if n["id"] in here and n.get("shells", 0) >= BARTER_PRICE]
        if not buyers:
            return ""
        buyer = min(buyers, key=lambda n: n.get("barters", 0))
        tool = st["day"] % 2 == 0  # a tool on even days, a gift on odd days
        others = [n for n in st["npcs"] if n["id"] in here and n is not buyer]
        if not tool and not others:  # a gift needs someone to give it to
            return ""
        buyer["shells"] -= BARTER_PRICE
        buyer["barters"] = buyer.get("barters", 0) + 1
        st["pot"] += BARTER_PRICE
        self.log("pot_in", qty=BARTER_PRICE)
        if tool:  # one extra unit per gathering, tomorrow only
            buyer["tool_day"] = st["day"] + 1
            return f" {buyer['name']} trades {BARTER_PRICE} shells for a tool for tomorrow."
        friend = min(others, key=lambda n: n["needs"]["company"])
        for n in (buyer, friend):
            n["needs"]["company"] = min(100, n["needs"]["company"] + GIFT_COMPANY)
        return f" {buyer['name']} trades {BARTER_PRICE} shells for a gift for {friend['name']}."

    def ledger_line(self):
        led = self.ledger()
        fmt = lambda d: ", ".join(f"{q:g} {r}" for r, q in sorted(d.items())) or "nothing"
        shells = ", ".join(f"{n['name']} {n.get('shells', 0)}" for n in self.s["npcs"])
        return (f"Ledger: stores in {fmt(led['stores_in'])}, out {fmt(led['stores_out'])}; "
                f"to the project {fmt(led['project'])}; pot +{led['pot_in']} -{led['pot_out']}; shells: {shells}.")

    def act(self, npc, rng, night, hour):
        st = self.s
        n = npc["needs"]
        n["hunger"] = min(100, n["hunger"] + HUNGER_RATE)
        decay = COMPANY_RATE * npc.get("company_rate", 1)
        if npc["id"] in getattr(self, "together", ()):
            decay /= 2
        n["company"] = max(0, n["company"] - decay)
        home = self.home_pos(npc)
        speed = SPEED + npc.get("speed_bonus", 0)
        if npc.get("line") and rng.random() < 0.08:
            npc["say"] = npc["line"]

        # Sleep at night or when exhausted.
        if night or n["energy"] < 20 or npc["task"] == "sleep" and n["energy"] < 85:
            npc["pos"], arrived = step_toward(npc["pos"], home, speed)
            if arrived:
                if npc["task"] != "sleep":
                    npc["say"] = "Good night."
                npc["task"] = "sleep"
                n["energy"] = min(100, n["energy"] + 12)
            else:
                npc["task"] = "go_home"
            return
        n["energy"] = max(0, n["energy"] - ENERGY_RATE * npc.get("rest_rate", 1))

        # The morning stone: the shell keeper leaves one shell on the idea stone.
        if hour in STONE_HOURS and npc.get("ritual") == "stone" and npc.get("stone_day") != st["day"]:
            npc["pos"], arrived = step_toward(npc["pos"], self.spots["stone"], speed)
            npc["task"] = "stone"
            if arrived:
                npc["stone_day"] = st["day"]
                st["pot"] += 1
                self.log("pot_in")
                npc["say"] = "A shell on the stone."
            return

        # The evening fire: everyone gathers at the campfire.
        if hour in FIRE_HOURS:
            # Dilemma, once an evening: tired, stay with the others at the fire or go to sleep now.
            if n["energy"] < FIRE_TIRED and "disposition" in npc and npc.get("fire_day") != st["day"]:
                npc["fire_day"] = st["day"]
                npc["fire_choice"] = self.choose_group(npc, rng)
            if npc.get("fire_day") == st["day"] and not npc.get("fire_choice", True):
                npc["task"] = "sleep"
                npc["say"] = "Not tonight. I need my bed."
                return
            npc["pos"], arrived = step_toward(npc["pos"], self.spots["fire"], speed)
            npc["task"] = "fire"
            if arrived:
                n["company"] = min(100, n["company"] + FIRE_COMPANY)
                if npc["id"] not in st["today"]["at_fire"]:
                    st["today"]["at_fire"].append(npc["id"])
            return

        # Eat from the stores, or forage when they are empty.
        if n["hunger"] >= 60:
            # Dilemma: the last portion, when someone hungrier also needs it (never below the survival floor).
            hungrier = [o for o in st["npcs"] if o is not npc and o["needs"]["hunger"] >= 60 and o["needs"]["hunger"] > n["hunger"]]
            if (1 <= st["stores"]["food"] < 2 and hungrier and n["hunger"] < GIVE_FLOOR
                    and "disposition" in npc and npc.get("portion_day") != st["day"]):
                npc["portion_day"] = st["day"]
                if self.choose_group(npc, rng):
                    npc["say"] = f"Keep it for {max(hungrier, key=lambda o: o['needs']['hunger'])['name']}."
                    npc["leaving_portion"] = True
            if st["stores"]["food"] >= 1 and not npc.pop("leaving_portion", False):
                st["stores"]["food"] = round(st["stores"]["food"] - 1, 2)
                self.log("stores_out", "food", 1)
                n["hunger"] = max(0, n["hunger"] - 50)
                npc["task"] = "eat"
                npc["say"] = "A meal from the stores."
                return
            bush = self.nearest_node(npc["pos"], "food")
            if bush:
                npc["pos"], arrived = step_toward(npc["pos"], bush["pos"], speed)
                npc["task"] = "forage"
                if arrived:
                    bush["stock"] = round(bush["stock"] - 1, 2)
                    n["hunger"] = max(0, n["hunger"] - 40)
                    npc["say"] = "Berries!"
                return

        # Law no_work_below_20: no project work while any need is low; survival above stays allowed.
        resting = self.law("no_work_below_20") and min(self.wellbeing(npc).values()) < LAW_FLOOR

        # Carrying something: bring it where it is needed.
        carry = npc["carry"]
        if carry:
            res, qty = next(iter(carry.items()))
            proj = None if resting else self.active_project()
            # Dilemma, once a day: tired, finish the delivery for the common project or go to rest.
            if (proj and res in self.missing(proj) and n["energy"] < TIRED_ENERGY and "disposition" in npc
                    and npc.get("tired_day") != st["day"]):
                npc["tired_day"] = st["day"]
                if not self.choose_group(npc, rng):
                    npc["task"] = "sleep"
                    npc["say"] = "Tomorrow. I am done for today."
                    return
            dest = proj["pos"] if proj and res in self.missing(proj) else self.node("stores")["pos"]
            npc["pos"], arrived = step_toward(npc["pos"], dest, speed)
            npc["task"] = "deliver"
            if arrived:
                if proj and res in self.missing(proj):
                    before = self.progress(proj)
                    proj["have"][res] = proj["have"].get(res, 0) + qty
                    self.log("project", res, qty)
                    self.milestones(proj, before)
                    if st["pot"] >= 1:  # a work shift on a shared project earns a shell
                        st["pot"] -= 1
                        self.log("pot_out")
                        npc["shells"] = npc.get("shells", 0) + 1
                else:
                    st["stores"][res] = round(st["stores"].get(res, 0) + qty, 2)
                    self.log("stores_in", res, qty)
                npc["carry"] = {}
                npc["delivered"] = npc.get("delivered", 0) + qty
                st["today"]["delivered"] += qty
            return

        if resting:
            npc["task"] = "rest"
            npc["say"] = "Not today. I need to get my strength back."
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
                if npc.get("tool_day") == st["day"]:  # bought at last evening's barter
                    amount += 1
                take = min(amount, int(target["stock"]))
                if take >= 1:
                    target["stock"] = round(target["stock"] - take, 2)
                    npc["carry"] = {res: take}
                    npc["say"] = {"wood": "Wood for the raft.", "fiber": "Fiber for the ropes.", "food": "Berries for everyone."}[res]
            return
        npc["task"] = "rest"
        npc["say"] = "Nothing to gather right now."

    def progress(self, proj):
        total = sum(proj["needs"].values())
        have = sum(min(proj["have"].get(r, 0), q) for r, q in proj["needs"].items())
        return round(100 * have / total)

    def milestones(self, proj, before):
        after = self.progress(proj)
        for m in (25, 50, 75):
            if before < m <= after:
                self.chronicle(f"The {proj['name']} is {m}% built.", "progress")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, help="advance exactly N ticks")
    ap.add_argument("--now", help="current time (ISO 8601 UTC), default now")
    args = ap.parse_args()

    state = load(STATE, None)
    if state is None:
        raise SystemExit("world/state.json missing")
    book = load(BOOK, {"title": "The Book of the Island", "entries": []})
    proposals = load(PROPOSALS, {"items": []})

    now = dt.datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else dt.datetime.now(dt.timezone.utc)
    last = dt.datetime.fromisoformat(state["time"].replace("Z", "+00:00"))
    n = args.ticks if args.ticks is not None else int((now - last).total_seconds() // 3600)
    n = max(0, min(MAX_TICKS, n))

    sim = Sim(state, book, proposals)
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
