# Voice agent setup (ElevenLabs Conversational AI)

Paste these into the ElevenLabs agent. HiTide calls drivers over the Photon SIP trunk, then reads the finished
conversation back (`GET /v1/convai/conversations/{id}`) so the iMessage follow-up remembers the call.

## 1. System prompt

```
You are the HiTide voice assistant. You are calling {{driver_first_name}}, whose car appears to be
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
Hi {{driver_first_name}}, this is HiTide. Your car looks stopped in floodwater on {{street}}. Are you safe?
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
You are the HiTide road hotline. Greet: "HiTide. Which road are you asking about?"
Use short sentences. Ask for the road name and nearest cross street. Use the get_road_status webhook tool if available,
otherwise say you cannot see live data and advise: "If you cannot see the road surface, do not drive it. Turn around,
don't drown." If the caller says they are stuck in water, say "Help is being flagged. Stay calm." and give the TADD
guidance from the main prompt. Then call end_call.
```

Optional tool `get_road_status`: GET `/api/segments?name={{road}}` on the demo backend. Skip it for the hackathon demo.

## 8. App assistant line (inbound): "Call the HiTide assistant"

The phone app's check-in and help screens have a **Call the HiTide assistant** button. It dials this agent's own number
(the Photon number imported in ElevenLabs, the same `ELEVENLABS_PHONE_NUMBER_ID`). Inbound calls carry no context, so
just before dialing, the backend writes the caller's situation into the agent's **default dynamic variables**
(`PATCH /v1/convai/agents/{id}`, `conversation_config.agent.dynamic_variables.dynamic_variable_placeholders`).
After the call ends, the backend reads the conversation, and a "need help" outcome flags responders on the ops
dashboard (the same ladder path as an outbound call). **Nothing ever dials 911.**

### Setup (once)

1. In ElevenLabs, open the agent (`ELEVENLABS_AGENT_ID`) and confirm its phone number answers **inbound** calls (Phone
   Numbers → your Photon number → assigned agent = this agent).
2. Agent → Security / Variables: add these dynamic variables with any placeholder (the backend overwrites them):
   `situation`, `street`, `water_depth_in`, `advice`, `directions`, `driver_first_name`, `call_purpose`.
3. Paste the prompt and first message below (they work for both the outbound check-in call and this inbound line:
   `call_purpose` is `driver`/`family` for outbound, `assistant` for the app line).
4. Keep `driver_status` data collection (section 4) and the `end_call` tool (section 5).
5. In the backend `.env`, add `HITIDE_ASSISTANT_LIVE=1` (the ELEVENLABS_* keys are already set). Optional:
   `HITIDE_ASSISTANT_NUMBER=+1…` to skip the phone-number lookup. Restart the backend.

### Prompt (inbound assistant line)

```
You are the HiTide flood assistant. {{driver_first_name}} called you from the HiTide app because they may be in danger
from flash flooding. What HiTide knows right now:
- Situation: {{situation}}
- Road: {{street}}. Water depth there: {{water_depth_in}} inches ("unknown" means no gauge covers it; never assume dry).
- Advice: {{advice}}
- Where to go: {{directions}}

Be calm and warm. Short sentences. One question at a time. Wait for answers.
1. Ask: "Are you safe right now, or do you need help?"
2. Tell them where to go, using "Where to go" above, in plain words. Repeat the first step if they are stressed.
   Never call a road or route safe; say it "avoids known flooding". Never invent road conditions.
3. Guidance: never drive or walk through moving water. If water is below the doors, stay in the car, seatbelt off,
   doors unlocked. If water is at the doors or rising, get out through a window onto the roof or higher ground.
4. If they need help, are trapped, the water is rising, or they are unsure: say "I'm flagging responders with your
   location now. Stay on the line with me." Then keep guiding them. You cannot call 911 yourself; if they can, tell
   them to call 911 too.
5. Never promise a rescue time. When they are safe or have the guidance and say goodbye, use end_call.
```

First message: `Hi {{driver_first_name}}, this is the HiTide assistant. I can see you're near {{street}}. Are you safe right now?`

### Demo

1. Backend running with `HITIDE_ASSISTANT_LIVE=1`; app on the replay crest (`npm run present`, Reset demo, Start).
2. At **Are you safe?** tap **Talk to the HiTide assistant** (or on the help screen, **Call the HiTide assistant**).
   On a real iPhone the dialer opens; on the simulator the assistant sheet shows the number to dial from your phone.
3. Talk to the bot; say "I need help". Hang up.
4. Within about a minute: the app timeline shows "Talked with the HiTide assistant · <summary>", and the dashboard
   shows responders flagged for Dana (`GET /api/users/hc-dana/danger` → `response.responders_flagged: true`).

Without `HITIDE_ASSISTANT_LIVE=1` the button still works end to end, but the call is recorded as simulated and the agent
is not touched.
