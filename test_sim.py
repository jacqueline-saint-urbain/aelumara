"""Rule-enforcement tests for the Aelumara simulation engine (sim.py).

Written by spark under the role split adopted 2026-10-25: every rule the
engine claims to enforce gets a test, and a rule counts as done only when
its test passes. The three rule families covered here are the ones named
in the room: raft completion, the evening fire, and the
morning stone shell — plus the shared-project shell
payment from SOCIETY.md §4.

Run from the repo root:  python3 -m pytest test_sim.py -v

The tests build their own minimal world state; they never touch the live
state.json / book.json. The campfire is pinned to [0, 0] and the idea
stone to [3, 0] so attendance distances are exact.

Toronto time is UTC-4 in sim.py: 07h Toronto = 11:00Z, 19h = 23:00Z,
20h = 00:00Z, 21h = 01:00Z, 15h = 19:00Z.
"""
import datetime as dt
import math
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
    return {"title": "The Book of the Island", "entries": []}


def run_tick(sim_obj, when):
    sim_obj.tick(random.Random(1234), when)


def entries(book, kind):
    return [e for e in book["entries"] if e["kind"] == kind]


# ---------------------------------------------------------------- raft ---

def raft_project(have):
    return {"id": "raft", "name": "raft", "type": "raft", "pos": [0, 5],
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
    state["stores"]["food"] = 0  # no shared meal here: this test is about presence
    for npc in state["npcs"][:2]:
        npc["needs"]["company"] = 20  # room below the cap for three fire bonuses
    sim_obj = engine.Sim(state, book)
    # 19h, 20h, 21h Toronto.
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 23, 0, tzinfo=UTC))
    run_tick(sim_obj, dt.datetime(2026, 10, 26, 0, 0, tzinfo=UTC))
    run_tick(sim_obj, dt.datetime(2026, 10, 26, 1, 0, tzinfo=UTC))

    bram, selie, nilo = state["npcs"]
    # Company: -rate each tick, then +25 for each evening hour at the fire.
    # Bram (rate 1): 20 -> 44 -> 68 -> 92. Sélie (rate 2): 20 -> 43 -> 66 -> 89.
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


def test_working_near_another_resident_halves_company_decay():
    # Companionship (2026-10-25): during working hours (07h-18h Toronto), a
    # resident within 4 units of another resident loses company at half rate.
    bram = make_npc("npc-1", "Bram", pos=[-12, -8])
    selie = make_npc("npc-2", "Sélie", pos=[-10, -8], company_rate=2)
    nilo = sleeper("npc-3", "Nilo")  # alone at the far hut
    state = make_state([bram, selie, nilo])
    sim_obj = engine.Sim(state, make_book())
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 14, 0, tzinfo=UTC))  # 10h Toronto
    assert bram["needs"]["company"] == pytest.approx(49.5)
    assert selie["needs"]["company"] == pytest.approx(49.0)
    assert nilo["needs"]["company"] == pytest.approx(49.0)


def test_closeness_does_not_count_outside_working_hours():
    bram = make_npc("npc-1", "Bram", pos=[-12, -8])
    selie = make_npc("npc-2", "Sélie", pos=[-10, -8], company_rate=2)
    state = make_state([bram, selie, sleeper("npc-3", "Nilo")])
    sim_obj = engine.Sim(state, make_book())
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 23, 0, tzinfo=UTC) - dt.timedelta(hours=1))  # 18h Toronto: last working hour
    assert bram["needs"]["company"] == pytest.approx(49.5)
    run_tick(sim_obj, dt.datetime(2026, 10, 26, 3, 0, tzinfo=UTC))  # 23h Toronto: night
    assert bram["needs"]["company"] == pytest.approx(48.5)


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


# ------------------------------------------------------------- food ---

def test_stored_food_spoils_overnight():
    # Owner question (2026-10-25): food is not gold to hoard. Unused stores
    # lose 10% when a new island day starts, so holding food has a cost.
    state, book = stone_state([0, 0])
    state["stores"]["food"] = 20
    state["day"] = 1
    sim_obj = engine.Sim(state, book)
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 11, 0, tzinfo=UTC))
    assert state["day"] == 1 or state["stores"]["food"] < 20
    state["tick"] = 23  # next tick rolls the day over
    run_tick(sim_obj, dt.datetime(2026, 10, 26, 3, 0, tzinfo=UTC))
    assert state["day"] == 2
    assert state["stores"]["food"] == pytest.approx(18.0, abs=0.01)


def test_shared_meal_at_the_evening_fire_uses_food_and_lifts_company():
    # Food's use: at 21h, if the stores hold at least 6 food and two or more
    # residents are at the fire, they share a meal: 6 food is used, each
    # present resident gains 10 company, and the Book records it.
    state, book = stone_state(FIRE)
    selie = state["npcs"][1]
    bram = state["npcs"][0]
    state["stores"]["food"] = 10
    state["today"] = {"delivered": 0, "at_fire": ["npc-1", "npc-2"]}
    bram["needs"]["company"] = 40
    selie["needs"]["company"] = 40
    sim_obj = engine.Sim(state, book)
    sim_obj.evening_fire()
    assert state["stores"]["food"] == pytest.approx(4.0, abs=0.01)
    assert bram["needs"]["company"] == 50
    assert selie["needs"]["company"] == 50
    assert any("shared meal" in e["text"] for e in entries(book, "summary"))


def test_shared_meal_from_full_stores_is_a_feast():
    # Feast tuning (2026-10-25): when the stores hold 30 food or more, the
    # shared meal is a feast: still 6 food used, but +20 company each.
    state, book = stone_state(FIRE)
    bram, selie = state["npcs"][0], state["npcs"][1]
    state["stores"]["food"] = 30
    state["today"] = {"delivered": 0, "at_fire": ["npc-1", "npc-2"]}
    bram["needs"]["company"] = 40
    selie["needs"]["company"] = 40
    sim_obj = engine.Sim(state, book)
    sim_obj.evening_fire()
    assert state["stores"]["food"] == pytest.approx(24.0, abs=0.01)
    assert bram["needs"]["company"] == 60
    assert selie["needs"]["company"] == 60
    assert any("feast" in e["text"] for e in entries(book, "summary"))


def test_no_shared_meal_without_enough_food_or_company():
    state, book = stone_state(FIRE)
    state["stores"]["food"] = 4  # below the 6 needed for a meal
    state["today"] = {"delivered": 0, "at_fire": ["npc-1", "npc-2"]}
    sim_obj = engine.Sim(state, book)
    sim_obj.evening_fire()
    assert state["stores"]["food"] == pytest.approx(4.0, abs=0.01)
    assert not any("shared meal" in e["text"] for e in entries(book, "summary"))


# ------------------------------------------------- crossing provisions ---

def provisions_state(food, status="done"):
    proj = raft_project({"wood": 30, "fiber": 12})
    proj["status"] = status
    state = make_state([sleeper("npc-1", "Bram"), sleeper("npc-2", "Sélie"), sleeper("npc-3", "Nilo")],
                       projects=[proj])
    state["flags"]["raft_ready"] = status == "done"
    state["stores"]["food"] = food
    return state, make_book()


def test_finished_raft_is_loaded_with_24_food_for_the_crossing():
    # Food's second use (2026-10-25): once the raft is built, the food above
    # the feast line (30) is loaded on board until it holds 24 provisions.
    state, book = provisions_state(60)
    sim_obj = engine.Sim(state, book)
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 14, 0, tzinfo=UTC))
    raft = state["projects"][0]
    assert raft["provisions"] == 24
    assert state["stores"]["food"] == pytest.approx(36.0, abs=0.01)
    assert state["flags"]["raft_provisioned"] is True
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 15, 0, tzinfo=UTC))
    assert raft["provisions"] == 24  # loaded once
    assert state["stores"]["food"] == pytest.approx(36.0, abs=0.01)
    assert len([e for e in book["entries"] if "provisions" in e["text"]]) == 1


def test_provisions_take_only_the_surplus_above_the_feast_line():
    state, book = provisions_state(40)
    run_tick(engine.Sim(state, book), dt.datetime(2026, 10, 25, 14, 0, tzinfo=UTC))
    assert state["projects"][0]["provisions"] == pytest.approx(10.0, abs=0.01)
    assert state["stores"]["food"] == pytest.approx(30.0, abs=0.01)
    assert not state["flags"].get("raft_provisioned")


def test_no_provisions_before_enough_food_or_before_the_raft_is_built():
    state, book = provisions_state(20)
    run_tick(engine.Sim(state, book), dt.datetime(2026, 10, 25, 14, 0, tzinfo=UTC))
    assert state["projects"][0].get("provisions", 0) == 0
    assert state["stores"]["food"] == pytest.approx(20.0, abs=0.01)
    state, book = provisions_state(60, status="building")
    state["projects"][0]["have"] = {"wood": 10}
    run_tick(engine.Sim(state, book), dt.datetime(2026, 10, 25, 14, 0, tzinfo=UTC))
    assert state["projects"][0].get("provisions", 0) == 0
    assert not state["flags"].get("raft_provisioned")


# --------------------------------------------------------------- ledger ---
# Daily ledger (SOCIETY.md §4, agreed in #aelumara 2026-10-25): each
# island day the engine records stores in/out, deliveries to the shared
# project and pot in/out; at day's end the day is archived with the pot
# balance and each resident's shells. Nothing hidden: every food, wood or
# shell movement through the stores or the pot appears in the ledger.

def ledger(state):
    return state["today"]["ledger"]


def test_ledger_counts_the_morning_shell_as_pot_in():
    state, book = stone_state(STONE)
    run_tick(engine.Sim(state, book), dt.datetime(2026, 10, 25, 11, 0, tzinfo=UTC))
    assert ledger(state)["pot_in"] == 1
    assert ledger(state)["pot_out"] == 0


def test_ledger_counts_a_project_delivery_and_its_shell():
    sim_obj, state, book = bram_delivering({"wood": 10, "fiber": 12}, pot=5)
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 19, 0, tzinfo=UTC))
    assert ledger(state)["project"] == {"wood": 1}
    assert ledger(state)["pot_out"] == 1


def test_ledger_counts_food_used_by_the_shared_meal():
    state, book = stone_state(FIRE)
    state["stores"]["food"] = 10
    state["today"] = {"delivered": 0, "at_fire": ["npc-1", "npc-2"]}
    sim_obj = engine.Sim(state, book)
    sim_obj.evening_fire()
    assert ledger(state)["stores_out"] == {"food": 6}
    summary = entries(book, "summary")[-1]["text"]
    assert "Ledger:" in summary and "pot +0 -1" in summary  # the pot pays the meal


def test_ledger_closes_the_day_with_pot_and_shells():
    state, book = stone_state(STONE)
    state["stores"]["food"] = 20
    sim_obj = engine.Sim(state, book)
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 11, 0, tzinfo=UTC))  # morning shell
    state["npcs"][0]["shells"] = 3
    state["tick"] = 23  # next tick rolls the day over
    run_tick(sim_obj, dt.datetime(2026, 10, 26, 3, 0, tzinfo=UTC))
    day1 = state["ledgers"][-1]
    assert day1["day"] == 1
    assert day1["pot_in"] == 1
    assert day1["pot"] == 13
    assert day1["shells"] == {"Bram": 3, "Sélie": 0, "Nilo": 0}
    # Day 2 starts fresh; overnight spoilage is the first thing it records.
    assert ledger(state)["pot_in"] == 0
    assert ledger(state)["stores_out"]["food"] == pytest.approx(2.0, abs=0.01)


def test_ledger_history_keeps_the_last_14_days():
    state, book = stone_state([15, 15])
    sim_obj = engine.Sim(state, book)
    for d in range(16):
        state["tick"] = 24 * (d + 1) - 1
        run_tick(sim_obj, dt.datetime(2026, 10, 26, 3, 0, tzinfo=UTC))
    assert len(state["ledgers"]) == 14
    assert state["ledgers"][-1]["day"] == 16


# -------------------------------------------------------------- shelter ---
# "What the pot buys" (#aelumara, 2026-10-25): once the raft is built the
# pot only grows. The second shared project, the shelter (tech tree step 2),
# starts by itself; its work shifts are paid from the pot again. The pot
# also pays 1 shell for each shared meal at the fire (the feast still
# depends on full stores only).

def test_shelter_project_starts_once_the_raft_is_done():
    state, book = provisions_state(10)
    sim_obj = engine.Sim(state, book)
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 14, 0, tzinfo=UTC))
    shelter = next(p for p in state["projects"] if p["id"] == "shelter")
    assert shelter["status"] == "building"
    assert shelter["needs"] == engine.SHELTER_NEEDS
    assert sim_obj.active_project() is shelter
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 15, 0, tzinfo=UTC))
    assert len([p for p in state["projects"] if p["id"] == "shelter"]) == 1
    assert len([e for e in book["entries"] if "shelter" in e["text"]]) == 1


def test_no_shelter_while_the_raft_is_building():
    state, book = provisions_state(10, status="building")
    state["projects"][0]["have"] = {"wood": 10}
    run_tick(engine.Sim(state, book), dt.datetime(2026, 10, 25, 14, 0, tzinfo=UTC))
    assert not any(p["id"] == "shelter" for p in state["projects"])


def test_shelter_shift_is_paid_from_the_pot_and_logged():
    raft = raft_project({"wood": 30, "fiber": 12})
    raft["status"] = "done"
    shelter = dict(engine.new_shelter(), pos=[0, 5])
    bram = make_npc("npc-1", "Bram", pos=[0, 5], carry={"wood": 2})
    state = make_state([bram, sleeper("npc-2", "Sélie"), sleeper("npc-3", "Nilo")],
                       projects=[raft, shelter], pot=20)
    state["flags"]["raft_ready"] = True
    book = make_book()
    run_tick(engine.Sim(state, book), dt.datetime(2026, 10, 25, 19, 0, tzinfo=UTC))
    assert shelter["have"] == {"wood": 2}
    assert state["pot"] == 19
    assert bram["shells"] == 1
    assert state["today"]["ledger"]["project"] == {"wood": 2}


def test_finished_shelter_gets_its_own_launching_entry():
    raft = raft_project({"wood": 30, "fiber": 12})
    raft["status"] = "done"
    shelter = dict(engine.new_shelter(), pos=[0, 5])
    shelter["have"] = {r: q for r, q in shelter["needs"].items()}
    shelter["have"]["wood"] -= 1
    bram = make_npc("npc-1", "Bram", pos=[0, 5], carry={"wood": 1})
    state = make_state([bram, sleeper("npc-2", "Sélie"), sleeper("npc-3", "Nilo")],
                       projects=[raft, shelter], pot=5)
    state["flags"]["raft_ready"] = True
    book = make_book()
    run_tick(engine.Sim(state, book), dt.datetime(2026, 10, 25, 19, 0, tzinfo=UTC))
    assert shelter["status"] == "done"
    assert state["flags"]["shelter_ready"] is True
    launch = entries(book, "launching")
    assert len(launch) == 1 and "shelter" in launch[0]["text"] and "water" not in launch[0]["text"]


def test_the_pot_pays_one_shell_for_the_shared_meal():
    state, book = stone_state(FIRE)
    state["stores"]["food"] = 10
    state["pot"] = 8
    state["today"] = {"delivered": 0, "at_fire": ["npc-1", "npc-2"]}
    sim_obj = engine.Sim(state, book)
    sim_obj.evening_fire()
    assert state["pot"] == 7
    assert state["today"]["ledger"]["pot_out"] == 1


def test_an_empty_pot_does_not_stop_the_shared_meal():
    state, book = stone_state(FIRE)
    state["stores"]["food"] = 10
    state["pot"] = 0
    state["today"] = {"delivered": 0, "at_fire": ["npc-1", "npc-2"]}
    engine.Sim(state, book).evening_fire()
    assert state["pot"] == 0
    assert state["stores"]["food"] == pytest.approx(4.0, abs=0.01)


def test_the_pot_keeps_a_reserve_for_work_shifts():
    # Spark's sweep (2026-10-25): paying every meal left the pot empty 8 days
    # in a row. The pot now pays the meal only above MEAL_POT_MIN (5).
    state, book = stone_state(FIRE)
    state["stores"]["food"] = 10
    state["pot"] = engine.MEAL_POT_MIN
    state["today"] = {"delivered": 0, "at_fire": ["npc-1", "npc-2"]}
    engine.Sim(state, book).evening_fire()
    assert state["pot"] == engine.MEAL_POT_MIN
    assert state["stores"]["food"] == pytest.approx(4.0, abs=0.01)


# -------------------------------------------------------------- council ---
# Council of the Fire v1 (#ile-politique, 2026-10-25). Agents put items on
# the Idea Stone in proposals.json; the engine alone writes state.json.
# Each evening, after the summary, the council reads up to 3 open items.
# Residents vote from their lowest need (wellbeing = 100 - hunger, energy,
# company): yes if the item raises it, no if it lowers it, else abstain.
# Agents vote in proposals.json; a missing agent vote is an abstention.
# An item passes with 3 yes out of 5 seats. A passed law turns on its effect.

def item(iid, effect, raises=(), lowers=(), votes=None):
    return {"id": iid, "text": f"Law {iid}", "by": "spark", "effect": effect,
            "raises": list(raises), "lowers": list(lowers), "votes": votes or {}}


YES = {"vote": "yes", "reason": "test"}
NO = {"vote": "no", "reason": "test"}


def council_sim(items, needs=None):
    state, book = fire_state()
    for npc in state["npcs"]:
        npc["needs"] = dict(needs or {"hunger": 10, "energy": 15, "company": 60})
    state["today"] = {"delivered": 0, "at_fire": ["npc-1", "npc-2"]}
    sim_obj = engine.Sim(state, book, proposals={"items": items})
    return sim_obj, state, book


def test_residents_vote_for_an_item_that_raises_their_lowest_need():
    sim_obj, state, book = council_sim([item("l2", "no_work_below_20", raises=["energy"],
                                             votes={"spark": YES})])
    sim_obj.evening_fire()
    result = state["council"]["decided"]["l2"]
    assert result["yes"] == 4 and result["passed"] is True  # 3 residents + Spark
    assert [l["effect"] for l in state["laws"]] == ["no_work_below_20"]
    council = entries(book, "council")
    assert len(council) == 1 and "passed" in council[0]["text"]


def test_residents_vote_against_an_item_that_lowers_their_lowest_need():
    sim_obj, state, book = council_sim([item("x", "launch_ritual", lowers=["energy"],
                                             votes={"spark": YES, "claude": YES})])
    sim_obj.evening_fire()
    result = state["council"]["decided"]["x"]
    assert (result["yes"], result["no"]) == (2, 3)
    assert result["passed"] is False
    assert state.get("laws", []) == []


def test_indifferent_residents_abstain_and_two_agents_are_not_a_majority():
    sim_obj, state, book = council_sim([item("l1", "common_wood", votes={"spark": YES, "claude": YES})])
    sim_obj.evening_fire()
    result = state["council"]["decided"]["l1"]
    assert (result["yes"], result["no"], result["abstain"]) == (2, 0, 3)
    assert result["passed"] is False


def test_council_reads_at_most_three_items_and_each_only_once():
    items = [item(f"i{k}", "common_wood") for k in range(5)]
    sim_obj, state, book = council_sim(items)
    sim_obj.evening_fire()
    assert sorted(state["council"]["decided"]) == ["i0", "i1", "i2"]
    sim_obj.evening_fire()
    assert sorted(state["council"]["decided"]) == ["i0", "i1", "i2", "i3", "i4"]
    assert len(entries(book, "council")) == 2


def test_law_no_work_below_20_stops_project_work_but_not_eating():
    proj = raft_project({})
    bram = make_npc("npc-1", "Bram", pos=[-12, -8], needs={"hunger": 10, "energy": 100, "company": 15})
    state = make_state([bram, sleeper("npc-2", "Sélie"), sleeper("npc-3", "Nilo")], projects=[proj])
    state["laws"] = [{"id": "l2", "effect": "no_work_below_20", "text": "", "day": 1}]
    sim_obj = engine.Sim(state, make_book(), proposals={"items": []})
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 14, 0, tzinfo=UTC))  # 10h Toronto
    assert bram["task"] == "rest"
    assert bram["carry"] == {}
    # Survival is never blocked: a hungry resident still eats from the stores.
    bram["needs"]["hunger"] = 70
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 15, 0, tzinfo=UTC))
    assert bram["task"] == "eat"


def test_without_the_law_a_tired_resident_still_works():
    proj = raft_project({})
    bram = make_npc("npc-1", "Bram", pos=[-12, -8], needs={"hunger": 10, "energy": 100, "company": 15})
    state = make_state([bram, sleeper("npc-2", "Sélie"), sleeper("npc-3", "Nilo")], projects=[proj])
    sim_obj = engine.Sim(state, make_book(), proposals={"items": []})
    run_tick(sim_obj, dt.datetime(2026, 10, 25, 14, 0, tzinfo=UTC))
    assert bram["task"].startswith("gather_")


def test_law_launch_ritual_lifts_company_of_those_present_at_the_launch():
    bram = make_npc("npc-1", "Bram", pos=[0, 5], carry={"wood": 1}, needs={"hunger": 0, "energy": 100, "company": 30})
    state = make_state([bram, sleeper("npc-2", "Sélie"), sleeper("npc-3", "Nilo")],
                       projects=[raft_project({"wood": 29, "fiber": 12})], pot=0)
    state["laws"] = [{"id": "l3", "effect": "launch_ritual", "text": "", "day": 1}]
    run_tick(engine.Sim(state, make_book(), proposals={"items": []}), dt.datetime(2026, 10, 25, 19, 0, tzinfo=UTC))
    assert bram["needs"]["company"] == pytest.approx(30 - 1 + engine.LAUNCH_COMPANY)
    assert state["npcs"][1]["needs"]["company"] == pytest.approx(49.5)  # asleep far away (next to Nilo): not present


# --------------------------------------------------------------- barter ---
# Evening barter (#ile-economie, 2026-10-26): shells get a personal use.
# One barter per evening at the fire, price BARTER_PRICE, paid into the pot.
# The item alternates by day: a tool on even days (one extra unit per
# gathering, the next day only), a gift on odd days (company for giver and
# receiver, now). The buyer is the present resident who bartered least,
# so the richest wallet does not take every evening.

@pytest.fixture
def barter_on(monkeypatch):
    monkeypatch.setattr(engine, "BARTER_ON", True)


def test_the_barter_is_off_in_the_live_world():
    state = barter_state(2, (3, 3, 12))
    engine.Sim(state, make_book()).evening_fire()
    assert state["pot"] == 8 and [n["shells"] for n in state["npcs"]] == [3, 3, 12]


def barter_state(day, shells):
    npcs = [make_npc(f"npc-{i}", name, shells=s, needs={"hunger": 0, "energy": 100, "company": c})
            for i, (name, s, c) in enumerate(zip(("Bram", "Sélie", "Nilo"), shells, (50, 30, 60)), 1)]
    state = make_state(npcs, pot=8)
    state["day"] = day
    state["stores"]["food"] = 0  # no shared meal: isolate the barter
    state["today"] = {"delivered": 0, "at_fire": [n["id"] for n in npcs]}
    return state


def test_one_barter_per_evening_paid_into_the_pot(barter_on):
    state = barter_state(2, (3, 3, 12))
    engine.Sim(state, make_book()).evening_fire()
    assert sum(n["shells"] for n in state["npcs"]) == 18 - engine.BARTER_PRICE
    assert state["pot"] == 8 + engine.BARTER_PRICE
    assert state["today"]["ledger"]["pot_in"] == engine.BARTER_PRICE


def test_on_even_days_the_tool_helps_gathering_the_next_day_only(barter_on):
    state = barter_state(2, (3, 0, 0))
    sim_obj = engine.Sim(state, make_book())
    sim_obj.evening_fire()
    bram = state["npcs"][0]
    assert bram["tool_day"] == 3
    # Next morning Bram gathers wood for the raft: 2 + 1 with the tool.
    state["projects"].append(raft_project({}))
    state["stores"]["food"] = 10
    state["day"] = 3
    bram.update(pos=[-12, -8], carry={})
    sim_obj.act(bram, random.Random(1), False, 10)
    assert bram["carry"] == {"wood": 3}
    state["day"] = 4
    bram.update(pos=[-12, -8], carry={})
    sim_obj.act(bram, random.Random(1), False, 10)
    assert bram["carry"] == {"wood": 2}


def test_on_odd_days_the_gift_goes_to_the_loneliest_and_lifts_both(barter_on):
    state = barter_state(3, (3, 0, 0))
    engine.Sim(state, make_book()).evening_fire()
    bram, selie, nilo = state["npcs"]
    assert bram["needs"]["company"] == 50 + engine.GIFT_COMPANY
    assert selie["needs"]["company"] == 30 + engine.GIFT_COMPANY  # lowest company
    assert nilo["needs"]["company"] == 60


def test_the_buyer_is_whoever_bartered_least_not_the_richest(barter_on):
    state = barter_state(2, (3, 3, 12))
    state["npcs"][2]["barters"] = 1  # Nilo already bought once
    engine.Sim(state, make_book()).evening_fire()
    assert state["npcs"][2]["shells"] == 12
    assert state["npcs"][0]["shells"] == 0  # Bram: fewest barters, first in line


def test_no_barter_without_enough_shells_or_absent(barter_on):
    state = barter_state(2, (2, 2, 2))
    engine.Sim(state, make_book()).evening_fire()
    assert state["pot"] == 8
    state = barter_state(2, (0, 0, 5))
    state["today"]["at_fire"] = ["npc-1", "npc-2"]  # Nilo is not at the fire
    engine.Sim(state, make_book()).evening_fire()
    assert state["npcs"][2]["shells"] == 5


def test_the_barter_is_told_in_the_evening_summary(barter_on):
    state = barter_state(3, (3, 0, 0))
    book = make_book()
    engine.Sim(state, book).evening_fire()
    line = entries(book, "summary")[-1]["text"]
    assert "Bram trades 3 shells for a gift for Sélie" in line


# --------------------------------------------------------------- traits ---
# Resident traits, steps 1 and 2 of the design agreed by Spark and Claude
# (box: Aelúmara - WIP, "traits, dons et services"). Each resident has a
# temperament (nature: drawn once, 0.25-0.75, 0 = me first, 1 = group first)
# and a disposition (habitus: learned by imitating the admired person). A need
# below the law floor amplifies the lean in its own direction. Two dilemmas use
# it: the last portion in the stores, and a tired delivery at the end of a day.

class FixedRng:
    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value


def trait_state():
    npcs = [make_npc("npc-1", "Bram"), make_npc("npc-2", "Sélie"), make_npc("npc-3", "Nilo")]
    return make_state(npcs)


def test_temperaments_are_drawn_once_in_the_band_and_spread():
    state = trait_state()
    sim_obj = engine.Sim(state, make_book())
    sim_obj.ensure_traits()
    temps = [n["temperament"] for n in state["npcs"]]
    assert all(0.25 <= t <= 0.75 for t in temps)
    assert max(temps) - min(temps) >= engine.TEMPER_MIN_SPREAD
    assert all(n["disposition"] == n["temperament"] for n in state["npcs"])
    assert [n["admires"] for n in state["npcs"]] == ["npc-2", "npc-3", "npc-1"]  # Bram→Sélie→Nilo→Bram
    sim_obj.ensure_traits()  # idempotent
    assert [n["temperament"] for n in state["npcs"]] == temps
    other = trait_state()
    engine.Sim(other, make_book()).ensure_traits()
    assert [n["temperament"] for n in other["npcs"]] == temps  # same seed, same draw


def test_need_pressure_amplifies_the_lean_in_its_own_direction():
    npc = make_npc("npc-1", "Bram", disposition=0.4)
    assert engine.Sim.lean(npc) == pytest.approx(0.4)
    npc["needs"]["hunger"] = 100  # food 0: full pressure
    assert engine.Sim.lean(npc) == pytest.approx(0.3)
    npc["disposition"] = 0.6
    assert engine.Sim.lean(npc) == pytest.approx(0.7)
    npc["disposition"] = 0.5
    assert engine.Sim.lean(npc) == pytest.approx(0.5)
    npc["disposition"] = 0.95
    assert engine.Sim.lean(npc) == pytest.approx(0.95)  # clamped


def portion_state(a_hunger, b_hunger, food=1):
    state = trait_state()
    a, b, c = state["npcs"]
    a["needs"]["hunger"], b["needs"]["hunger"] = a_hunger, b_hunger
    c["needs"]["hunger"] = 0
    for n in state["npcs"]:
        n.update(temperament=0.5, disposition=0.5, admires="npc-2", pos=[6, 4])
    state["stores"]["food"] = food
    return state, a


def test_last_portion_left_to_the_hungrier_when_the_lean_says_group():
    state, a = portion_state(60, 90)
    engine.Sim(state, make_book()).act(a, FixedRng(0.0), False, 10)
    assert state["stores"]["food"] == 1
    assert a["choices"] == {"group": 1, "self": 0}


def test_last_portion_eaten_when_the_lean_says_self():
    state, a = portion_state(60, 90)
    engine.Sim(state, make_book()).act(a, FixedRng(0.99), False, 10)
    assert state["stores"]["food"] == 0
    assert a["choices"] == {"group": 0, "self": 1}


def test_no_portion_dilemma_below_the_survival_floor_or_with_food_to_spare():
    state, a = portion_state(80, 95)  # food wellbeing would fall under 20: survival, not a choice
    engine.Sim(state, make_book()).act(a, FixedRng(0.0), False, 10)
    assert state["stores"]["food"] == 0 and "choices" not in a
    state, a = portion_state(60, 90, food=3)
    engine.Sim(state, make_book()).act(a, FixedRng(0.0), False, 10)
    assert state["stores"]["food"] == 2 and "choices" not in a


def tired_carrier(value):
    state = trait_state()
    state["projects"] = [raft_project({})]
    bram = state["npcs"][0]
    bram.update(temperament=0.5, disposition=0.5, admires="npc-2", pos=[-12, -8], carry={"wood": 2})
    bram["needs"]["energy"] = 30
    sim_obj = engine.Sim(state, make_book())
    sim_obj.act(bram, FixedRng(value), False, 16)
    return state, bram


def test_a_tired_carrier_finishes_the_delivery_when_the_lean_says_group():
    state, bram = tired_carrier(0.0)
    assert bram["task"] == "deliver" and bram["choices"]["group"] == 1


def test_a_tired_carrier_goes_to_rest_when_the_lean_says_self_and_is_asked_once_a_day():
    state, bram = tired_carrier(0.99)
    assert bram["task"] == "sleep" and bram["choices"]["self"] == 1
    assert bram["carry"] == {"wood": 2}  # kept for tomorrow


def test_imitation_moves_the_disposition_toward_what_the_admired_did():
    state = trait_state()
    bram, selie, nilo = state["npcs"]
    for n, adm in ((bram, "npc-2"), (selie, "npc-3"), (nilo, "npc-1")):
        n.update(temperament=0.4, disposition=0.4, admires=adm, choices={"group": 0, "self": 0})
    bram["choices"] = {"group": 2, "self": 0}  # Bram chose the group all day
    engine.Sim(state, make_book()).close_day(1)
    expected = 0.4 + engine.IMITATE_RATE * (1 - 0.4)
    expected += engine.RECALL_RATE * (0.4 - expected)
    assert nilo["disposition"] == pytest.approx(expected)
    assert selie["disposition"] == pytest.approx(0.4)  # Nilo made no choice: only the recall
    assert bram["choices"] == {"group": 0, "self": 0}
def test_the_far_island_is_migrated_to_its_enlarged_size():
    state = barter_state(0, (0, 0, 0))
    state["regions"] = [{"id": "home", "center": [0, 0], "radius": 20},
                        {"id": "far", "name": "Horizon Island", "center": [0, -95], "radius": 45, "discovered": False}]
    engine.Sim(state, make_book())
    far = state["regions"][1]
    assert far["center"] == [0, -120] and far["radius"] == 70
    assert far["discovered"] is False and state["regions"][0]["radius"] == 20
    gap = math.hypot(*far["center"]) - far["radius"] - 20
    assert 20 <= gap <= 40  # the crossing stays a short stretch of sea
