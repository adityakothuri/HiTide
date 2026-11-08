"""Per-user flood danger: where is the user, what is the water doing there, how vulnerable are they, who do we contact.

hazard.py        location -> LocationHazard (live or replayed evidence from the Hill Country loop)
vulnerability.py profile  -> Vulnerability (one model, each concept counted once)
danger.py        hazard x vulnerability x motion -> DangerAssessment (level + human reasons)
motion.py        location pings -> parked | driving | stopped (+ stopped-in-water)
policy.py        danger level over time -> outreach actions (ladder, cooldowns, replies)
monitor.py       ties it together on every loop step and every location ping
"""
