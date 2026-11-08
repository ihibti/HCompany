# Social posts (Best LinkedIn post / Best X post, €500 each)

Attach `docs/assets/french-media-race.gif` (X) or `docs/assets/netflux-l5.gif` (LinkedIn). Tag @hcompany_ai, @42AI and @cognition (Devin).

## LinkedIn
Signing up takes 1 click. Leaving takes… we decided to measure it.

This weekend at the H Company × 42AI Computer Use Agents Hackathon I built **Escape Hatch**: an AI agent that tries to *leave* websites, by refusing cookies, cancelling subscriptions or unsubscribing, and grades how hard each site makes it.

It sees the screen and clicks like a person, because exit flows have no API and are designed to confuse. Every key screenshot is then reviewed by a vision model for dark patterns: confirmshaming, hidden options, fake close buttons, "pause" disguised as "cancel". The report links each finding to the law it touches (CNIL guidance, France's online-cancellation rule, EU DSA Art. 25).

What it found on 19 popular French sites: **6 make refusing cookies impossible unless you pay.**

To test reliability, I built "Netflux", a fictional streaming service with 5 levels of increasingly evil cancellation flows. The final level has a password re-entry, a retention chatbot and a fake "we paused your account 🎉". Before the irreversible click, the agent stops and asks you for permission.

Built on H Company's Agents API (Holo) and Models API.

#ComputerUse #AIagents #DarkPatterns #GDPR #Hackathon

## X (thread)
1/ Signing up: 1 click.
Leaving: we sent an AI agent to find out.

Escape Hatch: a computer-use agent that refuses cookies and cancels subscriptions for you, and grades every dark pattern in the way. Built at the @hcompany_ai × @42AI hackathon 🧵

2/ 19 popular French sites audited. 6 make refusing cookies impossible without paying. The agent screenshots the proof and cites the law (CNIL, DSA Art. 25).

3/ Reliability test: "Netflux", a fake streaming service with 5 levels of evil cancellation flows. The final level has a retention chatbot and a fake "pause" link. The agent asks you before the irreversible click.

4/ Holo agents click, Holo vision flags the dark patterns, and a pure scoring core turns it all into a grade from A to F. Exit flows have no API, so this is a job for computer use.
