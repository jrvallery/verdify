---
title: "Verdify Launch Pack"
date: 2026-05-07
status: draft
---

# Verdify Launch Pack

This is the operator-facing launch plan for Jason. It is not linked from the public site.

## Launch Thesis

First-person framing:

> I built a 367 sq ft greenhouse in Longmont, Colorado where a local AI planner writes bounded climate tactics, an ESP32 enforces relay safety every 5 seconds, and the plans, telemetry, costs, failures, and lessons are public.

Non-negotiable claims:

- Local-first, not local-only.
- Solar-aligned, not off-grid solar powered.
- AI writes bounded tactics, not direct relay commands.
- Public proof is static first, Grafana second.
- It is a family/open-source personal project, not a revenue launch.
- James gets visible credit as part of the build story.

## Go/No-Go Checklist

- `data_health_status=ok`.
- `open_critical_high_alerts=0`.
- Current day has a visible full planner cycle.
- Planning Archive top day is coherent and does not contradict launch copy.
- Homepage static proof snapshot is fresh enough for crawlers.
- Grafana render cache warmer has a recent zero-failure run.
- Contact form delivers email to Jason.
- CSV links download directly.
- HN first comment is ready before posting.

## Recommended Timing

All times are Mountain time.

| Channel | Timing | Why |
|---|---|---|
| Hacker News | Tue-Thu, 8:15-9:15 AM | Hits the common 7-10 AM Pacific Show HN window while Jason can reply all day. |
| LinkedIn | Tue-Thu, 7:30-9:00 AM or 11:00 AM | Good for professional and local network discovery. |
| Reddit | After HN is live, staggered over 24-72h | Avoids duplicate-looking self-promotion and lets each community get a tailored angle. |
| Slashdot | Same morning as HN | Editorial review is not instant; submit a concise neutral story. |
| Facebook local groups | Evening, 6:00-8:00 PM | Better for local household/community readers. |
| X / Bluesky / Threads | Same day, 9:30 AM and follow-up later | Use as live thread/status, not the primary proof surface. |
| Instagram | Evening, 6:00-8:00 PM | Lead with greenhouse/solar/home-lab visuals. |
| Local media outreach | After HN/Reddit proof starts | A live discussion thread gives editors evidence that the story has traction. |

Research notes:

- Hacker News says Show HN is for something you made that people can try, inspect, or discuss, and asks submitters not to solicit votes: https://news.ycombinator.com/showhn.html
- HN general guidelines prefer original sources, non-promotional use, and non-editorialized titles: https://news.ycombinator.com/newsguidelines.html
- Slashdot submission guidance favors interesting, clear, neutral, well-linked, text-and-image friendly submissions: https://technology.slashdot.org/faq/submissions.shtml
- Sprout Social's 2026 timing data generally favors Tuesday/Wednesday and late morning through afternoon windows, but platform-native analytics and availability to reply matter more than generic timing: https://sproutsocial.com/insights/best-times-to-post-on-social-media/

## Primary Link Targets

Use these depending on audience:

- HN and technical Reddit: `https://verdify.ai/`
- Safety skeptics: `https://verdify.ai/reference/safety/`
- AI/control skeptics: `https://verdify.ai/reference/planning-loop/#ai-writable-tunables`
- Local/community: `https://verdify.ai/reference/about/`
- Data people: `https://verdify.ai/start/evidence/`
- Greenhouse/growers: `https://verdify.ai/greenhouse/`

## Hacker News

Title:

```text
Show HN: I built a local-AI greenhouse controller with public telemetry
```

First comment:

```text
Hi HN, I am Jason. This is a family project with my son James: a 367 sq ft greenhouse in Longmont, Colorado where an AI planner writes bounded climate tactics, and an ESP32 firmware controller owns the relay state machine every 5 seconds.

The part I think this crowd will care about is the trust boundary. Iris can write setpoints like VPD hysteresis, mist thresholds, fog escalation, heat/cool bias, dwell gates, and water budgets. It cannot directly flip relays. The firmware clamps and enforces the real-time state machine.

I also tried to make the claims falsifiable. The site publishes live telemetry, daily plans, scorecards, cost/water/energy data, known failures, generated lessons, and sample CSVs. The AI-writable tunables table is here:

https://verdify.ai/reference/planning-loop/#ai-writable-tunables

The safety split is here:

https://verdify.ai/reference/safety/

This is not a startup launch or paid product. It is an open-source-ish personal project that is still being scrubbed for credentials and household privacy. I am posting because I would like hard technical feedback before I polish it too much.
```

Comment response posture:

- Do not argue that it is "fully autonomous."
- Say "solar-aligned" instead of "solar powered."
- When challenged on LLM control, link the tunables table and ESP32 safety page.
- When challenged on noisy lessons, acknowledge the generated/curated split.
- When challenged on Grafana, link static evidence pages and CSVs.

## Reddit Targets

Post slowly and tailor each one.

| Community | Angle | Draft title |
|---|---|---|
| `r/Longmont` | Local family build, Boulder County climate, food/energy angle | I built a public AI-assisted greenhouse in Longmont |
| `r/boulder` | Local tech + climate + CU/Front Range angle | Longmont greenhouse project with public telemetry and local AI planning |
| `r/Colorado` | Front Range climate and gardening difficulty | Colorado greenhouse with public climate telemetry and AI planning |
| `r/greenhouse` | Practical greenhouse control, VPD, equipment | My 367 sq ft greenhouse publishes plans, VPD telemetry, costs, and failures |
| `r/gardening` | Growing at elevation and winter/spring stress | Trying to make a Colorado greenhouse more honest with public data |
| `r/esp32` | Firmware safety boundary | ESP32 greenhouse controller with AI-written setpoints, not AI relay control |
| `r/arduino` | Maker/control implementation | AI planner writes bounded tactics; microcontroller owns the relays |
| `r/homelab` | Local inference, Grafana, TimescaleDB | My homelab runs the planner and public proof layer for a greenhouse |
| `r/selfhosted` | Static site, Grafana, API, data publishing | Self-hosting the public evidence layer for a greenhouse controller |
| `r/LocalLLaMA` | Local Gemma/vLLM route | Local Gemma planner for real greenhouse setpoint decisions |
| `r/HomeAssistant` | HA/ESPHome/control bridge | Home Assistant telemetry plus ESP32 firmware for greenhouse control |

Always check current subreddit rules before posting. Disclose that you built it. Do not post identical text across communities.

General Reddit body:

```text
I built this in Longmont with my son James. It is a real 367 sq ft greenhouse, not a simulation: heaters, fans, misters, fog, vents, grow lights, RS485 probes, hydroponics, solar-aligned energy tracking, and an ESP32 state machine running every 5 seconds.

The AI layer is intentionally bounded. Iris writes setpoints and hypotheses; the ESP32 owns relay decisions and safety rails. I made the plans, telemetry, costs, failures, and lessons public so people can challenge the claims.

Main site: https://verdify.ai/
What the AI can set: https://verdify.ai/reference/planning-loop/#ai-writable-tunables
Safety split: https://verdify.ai/reference/safety/
Evidence: https://verdify.ai/start/evidence/

I am especially interested in critiques from people who have run real greenhouse, irrigation, ESPHome, or control systems.
```

## LinkedIn

Draft:

```text
I built Verdify with my son James: a 367 sq ft greenhouse in Longmont, Colorado where a local AI planner writes bounded climate tactics, an ESP32 firmware controller enforces relay safety every 5 seconds, and the plans, telemetry, costs, failures, and lessons are public.

The trust boundary is the whole point. Iris can tune VPD hysteresis, mist thresholds, fog escalation, heat/cool bias, dwell timing, and water budgets. It cannot directly flip relays. The firmware owns the real-time state machine.

This is a personal, open-source-oriented project, not a product launch. It combines a lot of things I care about: local inference, physical systems, public evidence, sustainable/solar-aligned operations, and building something real with family.

James deserves credit for keeping the project grounded in the physical greenhouse, not just the dashboard.

Site: https://verdify.ai/
AI-writable tunables: https://verdify.ai/reference/planning-loop/#ai-writable-tunables
Safety architecture: https://verdify.ai/reference/safety/
Evidence: https://verdify.ai/start/evidence/

I would love hard feedback from greenhouse growers, controls engineers, ESP32/ESPHome builders, local AI people, and anyone who has tried to make software survive contact with weather.
```

Tag Jason as `@Jason Vallery` and James only if his public LinkedIn profile is confirmed.

## X / Bluesky / Threads

Thread:

```text
I built a 367 sq ft greenhouse in Longmont, Colorado where a local AI planner writes bounded climate tactics, an ESP32 enforces relay safety every 5 seconds, and the plans/telemetry/costs/failures are public.

The key design choice: the AI does not flip relays. It writes tactical setpoints. Firmware owns the state machine.

What Iris can actually set: VPD hysteresis, mist thresholds, fog escalation, heat/cool bias, dwell timing, water budget, lighting posture, and a few bounded escape hatches.

The public proof layer includes live telemetry, daily plans, scorecards, economics, CSV samples, known limits, and lessons.

This is a family/personal project with my son James, not a product launch. I want technical critique before it gets too polished.

https://verdify.ai/
```

## Instagram

Caption:

```text
This is Verdify, the greenhouse James and I built in Longmont, Colorado.

It is now a public AI-assisted greenhouse control loop: local planning, ESP32 relay safety, rooftop-solar-aligned energy tracking, live telemetry, daily plans, costs, failures, and lessons.

The AI does not directly run the equipment. It writes bounded climate tactics; the controller enforces safety every 5 seconds.

verdify.ai
```

Image order:

1. Exterior greenhouse with solar/home visible.
2. Interior grow lights and hydroponics.
3. ESP32/controller photo.
4. Planning/archive screenshot.
5. Jason and James photo.

## Facebook / Local Groups

Draft:

```text
Longmont friends: James and I built a 367 sq ft greenhouse here in town, and I just made the control system public.

It uses sensors, an ESP32 controller, rooftop-solar-aligned energy tracking, and an AI planner that writes bounded climate tactics. The controller, not the AI, owns the relays and safety behavior.

I published the plans, telemetry, costs, failures, and lessons because I wanted the project to be inspectable instead of just a polished story.

https://verdify.ai/
```

## Slashdot

Submission:

```text
Jason Vallery built Verdify, a 367 sq ft greenhouse in Longmont, Colorado that publishes its AI-assisted control loop. A local Gemma/vLLM planner writes bounded climate tactics through OpenClaw, while an ESP32 firmware controller owns relay safety every 5 seconds. The site includes live telemetry, daily planning archives, scorecards, cost and water data, known limits, AI-writable tunables, and sample CSVs. It is a personal family project rather than a commercial launch, and the interesting question is whether the public evidence supports the control claims.

Main link: https://verdify.ai/
Safety boundary: https://verdify.ai/reference/safety/
Tunables: https://verdify.ai/reference/planning-loop/#ai-writable-tunables
Evidence: https://verdify.ai/start/evidence/
```

## Local Media Targets

Prioritize:

- Longmont Leader
- Longmont Times-Call
- Boulder Daily Camera
- Boulder Weekly
- Colorado Sun
- Colorado Public Radio
- 9News
- Denver7
- CBS Colorado
- BizWest
- CU Boulder engineering or alumni/community channels if James wants that affiliation public
- Greenhouse Grower
- Greenhouse Management
- Hackaday
- IEEE Spectrum tips

Pitch:

```text
Subject: Longmont family builds public AI-assisted greenhouse with live telemetry

Hi,

I am Jason Vallery in Longmont. My son James and I built Verdify, a 367 sq ft greenhouse that now publishes its AI-assisted control loop: live telemetry, daily plans, costs, failures, safety boundaries, lessons, and sample data.

The local angle is real: Front Range elevation, dry spring air, snow, solar gain, rooftop-solar-aligned energy, and year-round growing in Boulder County. The technical angle is that the AI planner does not directly control relays. It writes bounded climate tactics; an ESP32 firmware controller enforces safety every 5 seconds.

Public site: https://verdify.ai/
Safety boundary: https://verdify.ai/reference/safety/
Evidence: https://verdify.ai/start/evidence/

This is a personal family project, not a commercial product. I am happy to talk, and I would like James to take as many of the build-story questions as he is comfortable handling.

Jason Vallery
Longmont, Colorado
```

## James Interview Prep

Core answer:

> My dad and I built the greenhouse as a real place first. The software came later because we wanted to understand why the room behaved differently every day. The AI does not directly control equipment. It suggests bounded setpoints, and the ESP32 controller handles the relays and safety.

Questions and canned answers:

| Question | James answer |
|---|---|
| What did you build? | A real greenhouse in Longmont with sensors, fans, heaters, misters, fog, hydroponics, grow lights, and a controller that records what happens. |
| What is your role? | I helped with the physical build and the project story. I keep it grounded: it has to work as a greenhouse, not just as software. |
| Why AI? | The greenhouse changes by hour: sun, cold nights, dry air, and different crops. AI is useful for planning tradeoffs, but it should not directly flip relays. |
| Why local inference? | Local inference keeps routine planning cheap, fast, and close to the system. Cloud reasoning is still available for heavier reviews. |
| Is it safe? | The AI writes bounded tactics. The ESP32 firmware controls the relay state machine every 5 seconds and has hard safety rails. |
| What did the data show? | VPD is often the hard part in Colorado. Dry air can stress plants even when temperature looks fine. |
| Is it solar powered? | It is solar-aligned, not off-grid. The home has rooftop solar and batteries, but the greenhouse still uses grid power and gas heat when physics requires it. |
| What surprised you? | How physical the problem is. Shade, concrete, dry air, and equipment limits matter as much as code. |
| What would you improve next? | Shade cloth and cleaner public data are high on the list. Software cannot beat full solar gain by itself. |
| What should other students learn from it? | Build something real enough that mistakes have evidence. The best lesson is when the data proves your idea was incomplete. |

Do not say:

- "The AI runs the greenhouse."
- "It is fully autonomous."
- "It is off-grid solar powered."
- "The model learned everything by itself."

Use instead:

- "AI-assisted."
- "Bounded tactics."
- "ESP32-controlled relays."
- "Solar-aligned."
- "Public evidence."
