"""Rule-enforcement tests for the Aelumara simulation engine (sim.py).

Written by spark under the role split adopted 2026-10-25: every rule the
engine claims to enforce gets a test, and a rule counts as done only when
its test passes. The three rule families covered here are the ones named
in the room: raft completion, the evening fire (le feu du soir), and the
morning stone shell (la pierre du matin) — plus the shared-project shell
payment from SOCIETY.md §4.

Run from the repo root:  python3 -m pytest test_sim.py -v

The tests build their own minimal world state; they never touch the live
state.json / book.json. The campfire is pinned to [0, 0] and the idea
stone to [3, 0] so attendance distances are exact.

Toronto time is UTC-4 in sim.py: 07h Toronto = 11:00Z, 19h = 23:00Z,
20h = 00:00Z, 21h = 01:00Z, 15h = 19:00Z.
"""
import datetime as dt
import random

import pytest

import sim as engine

UTC = dt.timezone.utc
FIRE = [0, 0]
STONE = [3, 0]


@pytest.fixture(autouse=True)
def fixed_spots(monkeypatch):
    monkeypatch.setattr(engine, "load_world_spots", lambda: {"fire": FIRE, "stone": STONE})


def make_npc(nid, name, **kw):
    npc = {
        "id": nid,
        "name": name,
        "home": "fire",
        "pos": [0, 0],
        "needs": {"hunger": 0, "energy": 100, "company": 50},
        "task": "idle",
        "carry": {},
        "delivered": 0,
        "shells": 0,
    }
    npc.update(kw)
    return npc


def sleeper(nid, name):
    """A resident asleep at the far hut: present in the world, inert."""
    return make_npc(nid, name, home="hut-a", pos=[15, 15], task="sleep",
                    needs={"hunger": 0, "energy": 50, "company": 50})


def make_state(npcs, projects=None, pot=12):
    return {
        "v": 2,
        "seed": 2026,
        "tick": 0,
        "day": 1,
        "time": "2026-10-25T00:00:00Z",
        "flags": {"raft_ready": False},
        "stores": {"wood": 0, "fiber": 0, "food": 8},
        "nodes": [
            {"id": "stores", "type": "storehouse", "pos": [6, 4]},
            {"id": "hut-a", "type": "hut", "pos": [15, 15]},
            {"id": "wood-1", "type": "palm", "resource": "wood", "stock": 10, "pos": [-12, -8]},
            {"id": "fiber-1", "type": "reeds", "resource": "fiber", "stock": 10, "pos": [-16, 6]},
        ],
        "projects": projects if projects is not None else [],
        "npcs": npcs,
        "pot": pot,
        "today": {"delivered": 0, "at_fire": []},
        "fires": 0,
    }


def make_book():
    return {"title": "Le Livre de l'île", "entries": []}


def run_tick(sim_obj, when):
    sim_obj.tick(random.Random(1234), when)


def entries(book, kind):
    return [e for e in book["entries"] if e["kind"] == kind]


# ---------------------------------------------------------------- raft ---

def raft_project(have):
    return {"id": "raft", "name": "radeau", "type": "raft", "pos": [0, 5],
            "status": "building", "needs": {"wood": 30, "fiber": 12}, "have": have}


def bram_delivering(have, pot):
    bram = make_npc("npc-1", "Bram", pos=[0, 5], carry={"wood": 1})
    state = make_state([bram, sleeper("npc-2", "Sélie"), sleeper("npc-3", "Nilo")],
                       projects=[raft_project(have)], pot=pot)
    book = make_book()
    return engine.Sim(state, book), state, book


def test_raft_completes_when_last_resource_is_delivered():
    sim_obj, state, book = bram_delivering({"wood": 29, "fiber": 12}, pot=0)
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 19, 0, tzinfo=UTC))  # 15h Toronto
    proj = state["projects"][0]
    assert proj["status"] == "done"
    assert proj["done_tick"] == state["tick"]
    assert state["flags"]["raft_ready"] is True
    launching = entries(book, "launching")
    assert len(launching) == 1
    assert "First step" in launching[0]["text"]


def test_raft_does_not_complete_early():
    sim_obj, state, book = bram_delivering({"wood": 28, "fiber": 12}, pot=0)
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 19, 0, tzinfo=UTC))
    proj = state["projects"][0]
    assert proj["have"]["wood"] == 29
    assert proj["status"] == "building"
    assert state["flags"]["raft_ready"] is False
    assert entries(book, "launching") == []


def test_raft_completion_is_chronicled_exactly_once():
    sim_obj, state, book = bram_delivering({"wood": 29, "fiber": 12}, pot=0)
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 19, 0, tzinfo=UTC))
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 20, 0, tzinfo=UTC))  # one more hour
    assert len(entries(book, "launching")) == 1
    assert state["projects"][0]["status"] == "done"


def test_delivery_to_shared_project_pays_one_shell_from_the_pot():
    # SOCIETY.md §4: finishing a work shift on a shared project earns
    # 1 shell, paid out of the common pot (which starts at 12).
    sim_obj, state, book = bram_delivering({"wood": 10, "fiber": 12}, pot=5)
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 19, 0, tzinfo=UTC))
    bram = state["npcs"][0]
    assert state["projects"][0]["have"]["wood"] == 11
    assert state["pot"] == 4
    assert bram["shells"] == 1


# --------------------------------------------------------- evening fire ---

def fire_state():
    bram = make_npc("npc-1", "Bram", pos=[0, 0])
    selie = make_npc("npc-2", "Sélie", pos=[0.5, 0], company_rate=2)
    nilo = sleeper("npc-3", "Nilo")  # asleep at the far hut: he misses the fire
    state = make_state([bram, selie, nilo], projects=[raft_project({})])
    return state, make_book()


def test_evening_fire_rewards_presence_and_names_the_absent():
    state, book = fire_state()
    sim_obj = engine.Sim(state, book)
    # 19h, 20h, 21h Toronto.
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 23, 0, tzinfo=UTC))
    run_tick(sim_obj, dt.datetime(2026, 10, 26, 0, 0, tzinfo=UTC))
    run_tick(sim_obj, dt.datetime(2026, 10, 26, 1, 0, tzinfo=UTC))

    bram, selie, nilo = state["npcs"]
    # Company: -rate each tick, then +15 on arrival at the fire.
    # Bram (rate 1): 50 -> 64 -> 78 -> 92. Sélie (rate 2): 50 -> 63 -> 76 -> 89.
    assert bram["needs"]["company"] == 92
    assert selie["needs"]["company"] == 89
    # Nilo slept through it: decay only, no fire bonus.
    assert nilo["needs"]["company"] == 47
    # Presence registered once per resident.
    assert state["today"]["at_fire"] == ["npc-1", "npc-2"]
    # The 21h summary names who came and who was absent, exactly once.
    summaries = entries(book, "summary")
    assert len(summaries) == 1
    assert "Bram" in summaries[0]["text"] and "Sélie" in summaries[0]["text"]
    assert "Absent: Nilo" in summaries[0]["text"]
    assert state["fires"] == 1


# -------------------------------------------------------- morning stone ---

def stone_state(selie_pos):
    selie = make_npc("npc-2", "Sélie", home="hut-a", pos=selie_pos, ritual="stone")
    state = make_state([sleeper("npc-1", "Bram"), selie, sleeper("npc-3", "Nilo")])
    return state, make_book()


def test_morning_stone_adds_one_shell_once_per_day():
    state, book = stone_state(STONE)  # Sélie starts the day at the stone
    sim_obj = engine.Sim(state, book)
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 11, 0, tzinfo=UTC))  # 07h Toronto
    selie = state["npcs"][1]
    assert state["pot"] == 13
    assert selie["stone_day"] == state["day"]
    assert selie["say"] == "A shell on the stone."
    # A second tick on the same morning adds nothing more.
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 11, 0, tzinfo=UTC))
    assert state["pot"] == 13


def test_morning_stone_needs_arrival():
    state, book = stone_state([15, 15])  # far from the stone: she walks, no shell
    sim_obj = engine.Sim(state, book)
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 11, 0, tzinfo=UTC))
    selie = state["npcs"][1]
    assert selie["task"] == "stone"
    assert state["pot"] == 12
    assert selie.get("stone_day") is None


def test_morning_stone_walk_arrives_from_far_away_and_pays_once():
    # Owner decision A (2026-10-25): the walk to the stone starts at 06h and
    # continues each tick until she arrives. Her hut is 15.5 units away, so
    # three ticks (06h, 07h, 08h) are needed; she pays once, then stops.
    state, book = stone_state([18.5, 0])  # 15.5 units from the stone at [3, 0]
    sim_obj = engine.Sim(state, book)
    selie = state["npcs"][1]
    for utc_hour in (10, 11, 12):  # 06h, 07h, 08h Toronto
        run_tick(sim_obj, dt.datetime(2026, 10, 25, utc_hour, 0, tzinfo=UTC))
    assert selie["pos"] == pytest.approx(STONE, abs=0.01)
    assert state["pot"] == 13
    assert selie["stone_day"] == state["day"]
    # Later the same morning, nothing more is paid.
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 13, 0, tzinfo=UTC))  # 09h
    assert state["pot"] == 13
