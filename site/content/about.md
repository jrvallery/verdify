---
title: "About Verdify"
tags: [verdify, vision, story]
date: 2026-04-07
aliases:
  - verdify
  - story
---

# About Verdify

![The Verdify greenhouse alongside the family home, showing the full structure in its Colorado residential setting](/static/photos/exterior-daytime-house-solar.jpg)

I built a greenhouse with my son James in Longmont, Colorado. Polycarbonate panels, concrete slab, peaked roof, 367 square feet. It was a project to do together, and a way to grow food year-round at 5,090 feet.

Then I put sensors in it. And then I couldn't stop.

## The Obsession

Six RS485 climate probes, three soil moisture sensors, a hydro water quality monitor, energy meters, weather feeds, two cameras. 172 entities on an ESP32. I could see every zone's temperature, every VPD spike, every fan cycle. I could see that the south zone hits 100F at noon while the east stays 91F because of a tree shadow. I could see that March has more VPD stress hours than August (Colorado spring: 14% humidity and strong solar. Monsoon moisture actually saves August).

And I could see that static automation rules were never going to work. The right setpoint at 6 AM is wrong by 1 PM. A dry day needs different misting than a humid day. Growing lettuce and growing peppers need opposite strategies in the same room.

So I built something that could think about it.

## What Emerged

Verdify is what the greenhouse became once I let AI into the loop. The control system has three layers. First, the crop target band: smooth diurnal profiles for five active crops (lettuce, pepper, strawberry, basil, vanda orchid) that define what conditions the plants need at each hour. Second, the AI planner: Gemini 3.1 Pro reads 14 sections of context (sensor data, 72-hour forecast, the crop band, validated lessons, previous plan scores) and writes tactical plans that decide how aggressively the controller should chase those targets. Third, the ESP32 state machine: 42 climate states evaluated every 5 seconds, enforcing the band with fans, heaters, misters, and fog.

The crops set the targets. The AI tunes the tactics. The controller enforces it. The telemetry proves what happened. And the system scores itself, extracts lessons, and gets better.

It took seven sprints to build: 44 database tables, 54 views, 54 Grafana dashboards, and a [public website](/) where the system publishes every plan, every lesson, and every dashboard. If the planner claims it reduced VPD stress by 2 hours, you can pull up the chart and check. The entire stack runs on a single VM — no cloud infrastructure, just a Gemini API key for the planner.

## Where This Goes

The architecture already has `greenhouse_id` on every table. Every API routes through `/greenhouses/{id}/`. The Vallery greenhouse is technically "just another tenant." The next step is multi-tenant: per-greenhouse dashboards, device provisioning. Then maybe a physics engine (GreenLight) for plan scoring. Then maybe other greenhouses.

But that's future. Right now, the greenhouse is the thing. The plants need VPD under 2.0, the fans can't cool below ambient, and the next 72-hour plan publishes at 6 PM.

## Emily

Emily is the hands-on grower. She plants, prunes, waters, and observes. She talks to the greenhouse through Slack, and the system (eventually) will track everything she reports. Her perspective keeps the project honest. The AI can optimize setpoints all day, but if the lettuce bolted because nobody noticed the south zone hitting 90F for a week, that's a system failure.

## The Father-Son Part

James and I built the greenhouse structure together. He's the reason it exists. The software grew out of wanting to understand the room we built, and then wanting to run it well.

That matters to me, but I don't think it's why you're reading this. You're probably here because an ESP32 running 42 climate states with Gemini planning 72 hours ahead is an interesting system. So go look at the [planning loop](/intelligence/planning/), or the [live dashboards](/evidence/operations/), or the [lessons the greenhouse has taught us](/intelligence/lessons/).
