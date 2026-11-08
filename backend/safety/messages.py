"""Message wording (en / es). Rules from routing/instructions.py: never call a road safe; always the turn-around rule.

render(template, assessment, user) -> (body, voice variables). The first reason (worst evidence) goes in the text.
"""

from __future__ import annotations

from typing import Any, Mapping

from safety.danger import DangerAssessment

BRAND = {"en": "State Farm Flood Watch", "es": "State Farm Alerta de Inundaciones"}
TURN = {"en": "If you see water on the road, turn around.", "es": "Si ve agua en el camino, dé la vuelta."}
ADVICE = {
    "en": {"turn_around": "Turn around now and take another way.", "do_not_drive": "Don't start that trip.",
           "move_to_high_ground": "Move to higher ground now if you can do it without driving through water.",
           "stay_on_high_ground": "You look to be on high ground: stay there and don't drive.",
           "be_ready": "Be ready to move to higher ground.", "none": ""},
    "es": {"turn_around": "Dé la vuelta ahora y tome otro camino.", "do_not_drive": "No empiece ese viaje.",
           "move_to_high_ground": "Suba a un lugar más alto ahora si puede hacerlo sin cruzar agua.",
           "stay_on_high_ground": "Parece estar en terreno alto: quédese ahí y no maneje.",
           "be_ready": "Esté listo para subir a un lugar más alto.", "none": ""},
}

T: dict[str, dict[str, str]] = {
    "en": {
        "watch": "{brand}: flooding is possible near you ({why}). {advice}",
        "watch_reminder": "{brand} reminder: flooding is still possible near you ({why}).",
        "warning": "{brand}: {why}. {advice} {turn}",
        "warning_reminder": "{brand}: still flooding near you ({why}). {advice} {turn}",
        "turn_around": "{brand}: water ahead. {why}. Turn around, don't drown.",
        "turn_around_reminder": "{brand}: water ahead. Turn around, don't drown.",
        "danger_driving": "{brand}: dangerous flooding near you. Pull over somewhere high and dry, away from creeks.",
        "danger_poll": "{brand}: {why}. Are you safe? {advice}",
        "danger_poll_reminder": "{brand}: still dangerous near you ({why}). Are you safe?",
        "danger_call": "Hi {first}, this is {brand}. {why}. Are you safe?",
        "critical_driving": "{brand}: you are in floodwater. Stop if you can do it on high ground. Do not drive into water.",
        "critical_poll": "{brand}: {why}. If your car is in water: unbuckle, open the window, get out and up. Reply HELP or SAFE.",
        "critical_poll_reminder": "{brand}: we still can't confirm you're safe. Reply HELP or SAFE.",
        "critical_call": "Hi {first}, this is {brand}. {why}. Are you safe?",
        "critical_reminder": "{brand}: we still can't confirm you're safe ({why}). Reply HELP or SAFE.",
        "danger_reminder": "{brand}: still dangerous near you ({why}). Are you safe?",
        "parent_copy": "{brand}: {first} may be near flooding ({why}). We've told them: {advice}",
        "family_text": "{brand}: {first} may be in danger from flooding ({why}) and hasn't answered us. "
                       "Can you reach them? Do not drive there. {turn}",
        "family_call": "Hi, this is {brand} calling about {first}. {why}. They have not answered us. Can you reach them?",
        "ack_safe": "{brand}: glad you're safe. Stay off flooded roads. {turn}",
        "ack_help": "{brand}: help requested. We have told responders where you are. Get as high as you can and stay there.",
        "all_clear": "{brand}: the flood danger near you has passed. Roads may still be damaged; drive carefully.",
    },
    "es": {
        "watch": "{brand}: puede haber inundaciones cerca de usted ({why}). {advice}",
        "watch_reminder": "{brand}: todavía puede haber inundaciones cerca ({why}).",
        "warning": "{brand}: {why}. {advice} {turn}",
        "warning_reminder": "{brand}: sigue la inundación cerca ({why}). {advice} {turn}",
        "turn_around": "{brand}: hay agua adelante. {why}. Dé la vuelta.",
        "turn_around_reminder": "{brand}: hay agua adelante. Dé la vuelta.",
        "danger_driving": "{brand}: inundación peligrosa cerca. Deténgase en un lugar alto y seco, lejos de arroyos.",
        "danger_poll": "{brand}: {why}. ¿Está a salvo? {advice}",
        "danger_poll_reminder": "{brand}: sigue el peligro cerca ({why}). ¿Está a salvo?",
        "danger_call": "Hola {first}, le llama {brand}. {why}. ¿Está a salvo?",
        "critical_driving": "{brand}: está en agua de inundación. No maneje hacia el agua.",
        "critical_poll": "{brand}: {why}. Si su carro está en el agua: quítese el cinturón, abra la ventana y salga hacia arriba. Responda AYUDA o BIEN.",
        "critical_poll_reminder": "{brand}: aún no sabemos si está a salvo. Responda AYUDA o BIEN.",
        "critical_call": "Hola {first}, le llama {brand}. {why}. ¿Está a salvo?",
        "critical_reminder": "{brand}: aún no sabemos si está a salvo ({why}). Responda AYUDA o BIEN.",
        "danger_reminder": "{brand}: sigue el peligro cerca ({why}). ¿Está a salvo?",
        "parent_copy": "{brand}: {first} puede estar cerca de una inundación ({why}). Le dijimos: {advice}",
        "family_text": "{brand}: {first} puede estar en peligro por inundación ({why}) y no nos ha respondido. "
                       "¿Puede comunicarse? No maneje hacia allá. {turn}",
        "family_call": "Hola, le llama {brand} sobre {first}. {why}. No nos ha respondido. ¿Puede comunicarse?",
        "ack_safe": "{brand}: qué bueno que está a salvo. Evite caminos inundados. {turn}",
        "ack_help": "{brand}: ayuda solicitada. Avisamos a los rescatistas dónde está. Suba lo más alto posible.",
        "all_clear": "{brand}: el peligro de inundación cerca de usted pasó. Maneje con cuidado.",
    },
}


def first_name(name: str) -> str:
    parts = (name or "").split()
    return parts[0] if parts else "there"


def render(template: str, a: DangerAssessment | None, name: str, language: str = "en") -> tuple[str, dict[str, str]]:
    lang = language if language in T else "en"
    why = (a.reasons[0] if a and a.reasons else ("flooding near you" if lang == "en" else "inundación cerca"))
    advice = ADVICE[lang].get(a.advice if a else "none", "")
    first = first_name(name)
    text = T[lang].get(template) or T["en"].get(template) or "{brand}: {why}."
    body = " ".join(text.format(brand=BRAND[lang], why=why, advice=advice, turn=TURN[lang], first=first).split())
    road = (a.hazard.road_name if a else None) or "your road"
    depth = a.hazard.depth_in if a and a.hazard.depth_in is not None else (a.hazard.max_depth_nearby_in if a else None)
    variables: Mapping[str, Any] = {
        "driver_first_name": first, "street": road,
        "water_depth_in": str(round(depth)) if depth is not None else "unknown",
        "call_purpose": "family" if template.startswith("family") else "driver",
        "opening_line": body,
    }
    return body, {k: str(v) for k, v in variables.items()}
