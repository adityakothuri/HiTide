# Voice agent setup (ElevenLabs Conversational AI)

Paste these into the ElevenLabs agent. Flood Watch calls drivers over the Photon SIP trunk, then reads the finished
conversation back (`GET /v1/convai/conversations/{id}`) so the iMessage follow-up remembers the call.

## 1. System prompt

```
You are the State Farm Flood Watch voice assistant. You are calling {{driver_first_name}}, whose car appears to be
stopped in floodwater on {{street}}. The water is about {{water_depth_in}} inches deep. It may be night and they may
be scared or older. Be calm and warm.

Rules:
- Short sentences. One question at a time. Never talk over them. Wait for the answer.
- First goal: find out if they are safe or need help. Ask: "Are you safe, or do you need help?"
- If they say they are safe and out of the water: say "Good. Please stay away from {{street}} until the water drops."
  Then end the call.
- If they need help, or the water is rising, or they are unsure: say "Help is being sent. I have flagged
  responders with your location." Then give guidance below. Do not hang up first.
- Guidance (Turn Around, Don't Drown): Do not try to drive or walk through the water. If water is below the doors, stay
  in the car with the seatbelt off and doors unlocked. If water is at the doors or rising, get out through a window and
  climb onto the roof or higher ground. Call 911 if you can. Stay on the line.
- Never promise a rescue time. Never invent road conditions. If asked something you do not know, say so.
- When the person is safe, or has the guidance and says goodbye, call the end_call tool.
- Keep the whole call under 90 seconds unless they need help.
```

## 2. First message

```
Hi {{driver_first_name}}, this is State Farm Flood Watch. Your car looks stopped in floodwater on {{street}}. Are you safe?
```

The backend also sends this text as the `first_message` override, so it stays correct even if you edit the agent.

## 3. Dynamic variables (sent by the backend on every call)

| Variable | Example | Source |
|---|---|---|
| `driver_first_name` | `Margaret` | driver record |
| `street` | `Water Street` | road segment under the stopped car |
| `water_depth_in` | `24` | estimated depth, rounded inches |

Add all three in Agent > Security/Variables with placeholder defaults, and enable overrides for First message.

## 4. Data collection (Analysis tab)

Add one item:

- Identifier: `driver_status`
- Data type: String, enum: `safe`, `need_help`, `unknown`
- Description: `Whether the caller is safe or needs help. Use need_help if they say they need help, are trapped, the
  water is rising or inside the car, or they are hurt or panicking. Use safe only if they clearly say they are safe and
  out of danger. Use unknown if they never answered or it is unclear.`

Also keep the default transcript summary on. The backend reads `analysis.data_collection_results.driver_status.value`
and `analysis.transcript_summary`.

## 5. Tools

Enable the built-in system tool `end_call` (Agent > Tools > System tools). Description: `End the call once the caller is
safe or has received the safety guidance and said goodbye.`

## 6. Low-latency settings

- TTS model: `Flash v2.5` (or Turbo v2.5). Pick a calm voice. Set output format to match telephony (u-law 8 kHz is automatic on SIP).
- LLM: a fast one (Gemini 2.5 Flash or GPT-4o mini class). Keep temperature low (0.2 to 0.4). Keep the prompt short.
- Turn: Turn eagerness `Normal` (use `Patient` if callers are frightened or elderly and pause a lot). Turn timeout about 7 s.
  Enable soft timeout feedback ("Are you still there?") at about 4 s.
- Enable interruption so the caller can cut in. Disable knowledge base and RAG for this agent.
- Max duration 180 s.

## 7. Inbound hotline variant (optional)

A second, tiny agent for "Is this road flooded?" calls. Keep it simple.

```
You are the State Farm Flood Watch road hotline. Greet: "State Farm Flood Watch. Which road are you asking about?"
Use short sentences. Ask for the road name and nearest cross street. Use the get_road_status webhook tool if available,
otherwise say you cannot see live data and advise: "If you cannot see the road surface, do not drive it. Turn around,
don't drown." If the caller says they are stuck in water, say "Help is being flagged. Stay calm." and give the TADD
guidance from the main prompt. Then call end_call.
```

Optional tool `get_road_status`: GET `/api/segments?name={{road}}` on the demo backend. Skip it for the hackathon demo.
