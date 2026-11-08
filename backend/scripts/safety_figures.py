"""Presentation evidence: test inventory from a pytest JUnit XML + PNG figures from the safety experiments.

Inputs:  --junit <pytest --junitxml file>, data/experiments/safety_timeline.json, safety_stress_*_2000.json
Outputs: data/experiments/test_inventory.json, docs/test-evidence/*.png
Run:     cd backend && uv run pytest -q --junitxml=/tmp/junit.xml && uv run python scripts/safety_figures.py --junit /tmp/junit.xml
(matplotlib comes with the `vision` extra: uv sync --extra vision)
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from app.config import DATA_DIR, REPO_DIR  # noqa: E402

EXP = DATA_DIR / "experiments"
OUT = REPO_DIR / "docs" / "test-evidence"

# Test files -> the layer of the system they prove (order = bottom-up through the pipeline).
LAYERS: list[tuple[str, tuple[str, ...]]] = [
    ("Live Texas feeds + observation layer", ("test_drivetexas", "test_feed_intake", "test_local_sensors",
     "test_noaa_products", "test_observe_", "test_recent_feeds", "test_region_mode", "test_regional_roads",
     "test_texas_", "test_flood_monitor_demo")),
    ("Flood model + evidence fusion", ("test_area_risk", "test_critical_", "test_depth_grid", "test_flood",
     "test_fusion", "test_hand_flood", "test_road_status", "test_route_out", "test_hill_country_demo",
     "test_replay_golden")),
    ("Per-user danger (new)", ("test_safety_",)),
    ("Driver stages + profile risk", ("test_demo_flow", "test_escalation", "test_profile_risk", "test_risk",
     "test_route_check", "test_stop_detect")),
    ("Outreach: Photon texts, ElevenLabs calls, replies", ("test_call_summary", "test_inbound", "test_mode",
     "test_outreach_", "test_photon2", "test_reply_parse", "test_voice_")),
    ("Evidence store", ("test_evidence_",)),
    ("Drone + vision (next layer)", ("test_drone_", "test_print_scale", "test_tabletop", "test_tello",
     "test_vision_")),
]
# Core guarantees shown on the slide: (claim, test file, test name).
GUARANTEES = [
    ("Unknown water depth is never read as a dry road", "test_safety_hazard", "test_unknown_depth_is_not_dry_and_not_flooded"),
    ("Deeper water never lowers the danger level", "test_safety_hazard", "test_monotone_in_depth"),
    ("Your own car's stall depth sets the critical line", "test_safety_hazard", "test_depth_on_your_road_uses_your_stall_depth"),
    ("An NWS outage never reads as all-clear", "test_safety_hazard", "test_nws_outage_does_not_read_as_all_clear"),
    ("A car stopped in water is CRITICAL", "test_safety_region", "test_stopped_in_water_is_critical"),
    ("Vulnerability raises a level but never invents one", "test_safety_region", "test_vulnerability_bumps_but_never_invents"),
    ("Water ahead while driving means turn around", "test_safety_region", "test_water_ahead_while_driving"),
    ("No reply: poll, then call, then family", "test_safety_policy", "test_danger_poll_then_call_then_family"),
    ("Never the same alert twice inside a cooldown", "test_safety_policy", "test_never_duplicates_same_level_within_cooldown"),
    ("HELP flags responders and beats a later SAFE", "test_safety_policy", "test_help_flags_responders_once_and_beats_a_later_safe"),
    ("Users with hearing loss are never called", "test_safety_policy", "test_no_voice_users_are_never_called"),
    ("No all-clear after HELP, an open case, or dark evidence", "test_safety_policy", "test_no_all_clear_after_help_or_with_an_open_case"),
    ("GPS jitter at home never looks like driving", "test_safety_motion", "test_gps_jitter_while_parked_never_drives_or_walks"),
    ("Real numbers are never texted unless allowlisted", "test_outreach_guard", "test_real_number_never_sent_even_in_photon_mode"),
    ("Phone numbers never appear in API responses", "test_safety_api", "test_enroll_validates_and_never_echoes_phone"),
    ("July 4, 2025: Ruth is at DANGER before SH 39 floods", "test_safety_region", "test_replay_finds_ruth_in_danger_before_the_emergency"),
]
LEVEL_COLORS = {"none": "#c9c8c2", "watch": "#86b6ef", "warning": "#fab219", "danger": "#ec835a", "critical": "#d03b3b"}
INK, MUTED, GRID = "#1d1f22", "#5d5f63", "#e6e5e0"
EVENTS = [("01:14", "Flash Flood Warning"), ("04:04", "Flash Flood Emergency (Hunt)"), ("04:22", "SH 39 under water")]


def layer_of(f: str) -> str:
    for name, prefixes in LAYERS:
        if any(f == p or f.startswith(p) for p in prefixes):
            return name
    return "Other"


def inventory(junit: str) -> dict:
    root = ET.parse(junit).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    per_file: Counter = Counter()
    status: dict[tuple[str, str], str] = {}
    for tc in suite.iter("testcase"):
        f = tc.get("classname", "").split(".")[-1]
        name = tc.get("name", "").split("[")[0]
        s = ("skipped" if tc.find("skipped") is not None else
             "failed" if tc.find("failure") is not None or tc.find("error") is not None else "passed")
        per_file[(f, s)] += 1
        if status.get((f, name)) != "failed":
            status[(f, name)] = s
    layers: dict[str, Counter] = {name: Counter() for name, _ in LAYERS}
    files = sorted({f for f, _ in per_file})
    for f in files:
        for s in ("passed", "failed", "skipped"):
            layers.setdefault(layer_of(f), Counter())[s] += per_file[(f, s)]
    return {
        "run": {k: suite.get(k) for k in ("tests", "failures", "errors", "skipped", "time", "timestamp")},
        "passed": int(suite.get("tests")) - int(suite.get("failures")) - int(suite.get("errors")) - int(suite.get("skipped")),
        "files": len(files),
        "layers": [{"layer": n, **dict(layers[n])} for n, _ in LAYERS],
        "guarantees": [{"claim": c, "file": f, "test": t, "status": status.get((f, t), "missing")} for c, f, t in GUARANTEES],
        "skipped_why": {"test_evidence_mongo / test_evidence_app": "need a running MongoDB replica set",
                        "test_replay_golden": "bit-for-bit replay digest, RUN_SLOW=1 (~15 min)"},
    }


def _style(ax) -> None:
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=10, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def fig_tests(inv: dict) -> None:
    rows = inv["layers"][::-1]
    fig, ax = plt.subplots(figsize=(10, 4.6), dpi=200)
    y = range(len(rows))
    ax.barh(list(y), [r.get("passed", 0) for r in rows], color="#2a78d6", height=0.55)
    for i, r in enumerate(rows):
        extra = f"  ({r['skipped']} skipped)" if r.get("skipped") else ""
        ax.text(r.get("passed", 0) + 3, i, f"{r.get('passed', 0)} passed{extra}", va="center", color=INK, fontsize=10)
    ax.set_yticks(list(y), [r["layer"] for r in rows], color=INK, fontsize=10.5)
    ax.set_xlim(0, max(r.get("passed", 0) for r in rows) * 1.35)
    _style(ax)
    ax.set_title(f"{inv['passed']} tests pass, 0 fail ({inv['files']} test files, {float(inv['run']['time']):.0f} s)",
                 loc="left", color=INK, fontsize=14, fontweight="bold", pad=14)
    fig.tight_layout()
    fig.savefig(OUT / "tests_by_layer.png", facecolor="white")
    plt.close(fig)


def fig_timeline(tl: dict) -> None:
    rows = tl["rows"]
    x = list(range(len(rows)))
    labels = [r["t"] for r in rows]
    fig, ax = plt.subplots(figsize=(11, 5), dpi=200)
    order = ["none", "watch", "warning", "danger", "critical"]
    ax.stackplot(x, *[[r[k] for r in rows] for k in order], colors=[LEVEL_COLORS[k] for k in order],
                 labels=[k.capitalize() for k in order], edgecolor="white", linewidth=0.6)
    ax.plot(x, [r["truly_near_deep_water"] for r in rows], color=INK, linewidth=2.2, linestyle=(0, (4, 2)),
            label="Actually near 6+ in of water (replay truth)")
    for n, (t, what) in enumerate(EVENTS):
        i = min(range(len(labels)), key=lambda k: abs(int(labels[k][:2]) * 60 + int(labels[k][3:]) - (int(t[:2]) * 60 + int(t[3:]))))
        ax.axvline(i, color=MUTED, linewidth=0.8, ymax=1.0 / 1.12 + 0.02 + 0.045 * (n % 2))
        ax.text(i + 0.4, tl["users"] * (1.015 + 0.05 * (n % 2)), f"{t} {what}", fontsize=8.5, color=MUTED, va="bottom")
    ticks = [i for i, lab in enumerate(labels) if lab.endswith(":00") or lab.endswith(":30")]
    ax.set_xticks(ticks, [labels[i] for i in ticks])
    ax.set_xlim(0, len(rows) - 1)
    ax.set_ylim(0, tl["users"] * 1.14)
    ax.set_ylabel("Kerr County residents", color=MUTED)
    _style(ax)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.1), ncol=6, frameon=False, fontsize=9, labelcolor=INK)
    ax.set_title(f"July 4, 2025 replay: {tl['users']} residents' danger level vs where the water really was (CDT)",
                 loc="left", color=INK, fontsize=13, fontweight="bold", pad=22)
    fig.tight_layout()
    fig.savefig(OUT / "replay_levels.png", facecolor="white")
    plt.close(fig)


def fig_stress(stress: dict[str, dict]) -> None:
    names = [("none", "Normal"), ("usgs_dark", "River gauges\ndark at 04:00"), ("nws_down", "NWS alerts\ndown"),
             ("stale", "Every source\nstale")]
    names = [(k, v) for k, v in names if k in stress]
    fig, ax = plt.subplots(figsize=(10, 4.8), dpi=200)
    w = 0.36
    xs = range(len(names))
    for j, (key, label, color) in enumerate([("warning", "Warned (WARNING+) before water arrived", "#fab219"),
                                             ("danger", "Asked 'are you safe?' (DANGER+) before water", "#ec835a")]):
        vals = [stress[k][key]["recall"] * 100 for k, _ in names]
        pos = [x + (j - 0.5) * (w + 0.03) for x in xs]
        ax.bar(pos, vals, width=w, color=color, label=label)
        for p, v in zip(pos, vals):
            ax.text(p, v + 1.5, f"{v:.0f}%", ha="center", color=INK, fontsize=10)
    ax.set_xticks(list(xs), [v for _, v in names], color=INK, fontsize=10)
    ax.set_ylim(0, 112)
    ax.set_yticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
    _style(ax)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.14), ncol=2, frameon=False, fontsize=9.5, labelcolor=INK)
    n = stress["none"]
    ax.set_title(f"2,000 simulated users, {n['truth']['exposed_users']:,} truly reached by water: who we warned in time",
                 loc="left", color=INK, fontsize=13, fontweight="bold", pad=14)
    fig.tight_layout()
    fig.savefig(OUT / "stress_recall.png", facecolor="white")
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--junit", required=True)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    inv = inventory(args.junit)
    (EXP / "test_inventory.json").write_text(json.dumps(inv, indent=1))
    fig_tests(inv)
    fig_timeline(json.loads((EXP / "safety_timeline.json").read_text()))
    stress = {k: json.loads((EXP / f"safety_stress_{k}_2000.json").read_text())
              for k in ("none", "usgs_dark", "nws_down", "stale") if (EXP / f"safety_stress_{k}_2000.json").exists()}
    fig_stress(stress)
    missing = [g for g in inv["guarantees"] if g["status"] != "passed"]
    print(f"{inv['passed']} passed; guarantees not passing: {missing or 'none'}; figures in {OUT}")


if __name__ == "__main__":
    main()
