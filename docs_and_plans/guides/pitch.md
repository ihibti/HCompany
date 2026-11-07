# Escape Hatch: pitch (3 minutes)

## 0:00 Hook (20s)
"How many clicks does it take to subscribe to a streaming service? One. How many to cancel? Last night our agent counted twelve, plus a password, a chatbot that 'paused' instead of cancelling, and a link in 9-pixel grey text."

## 0:20 Problem (25s)
- Exit flows are the one part of the web that companies *want* to break: cookie walls, retention mazes, confirmshaming.
- Regulators already fine for it: CNIL fined Google €150M and Facebook €60M in 2022 because refusing cookies took more clicks than accepting. France has required online cancellation since June 2023. The EU DSA bans deceptive interfaces.
- Nobody can audit this at scale. Exit flows have no API, they are built to confuse, and they change constantly. A scraper cannot judge whether "Reject" is harder to find than "Accept". You need something that *sees the screen and clicks*.

## 0:45 Live demo (90s)
1. Home → "French media" preset → three agents race in parallel on lemonde.fr, lefigaro.fr and allocine.fr, refusing cookies. Watch the click markers and the live effort counter.
2. Report cards land: **3 of 6 major French sites we audited make refusing cookies impossible without paying.** Each verdict comes with screenshot evidence (e.g. Le Figaro's "continue without accepting" redirects to the subscription page) and the law it touches.
3. Consumer mode: "Cancel my Netflux, Level 5". The agent re-enters the password, insists three times with the retention chatbot, refuses the fake "pause", and *asks you before the irreversible click*. Approve → cancelled.

## 2:15 Reliability and tech (25s)
- Built on H's Agents API (Holo, cloud browser, structured answers, custom tools for human approval) and the Models API (Holo vision classifying every key screenshot into an 11-pattern dark-pattern taxonomy with strict JSON schema).
- Netflux gauntlet benchmark: 5 levels of escalating dark patterns with ground truth. 5/5 cancelled; effort within a few actions of the human minimum; pattern precision/recall measured against the ground truth.
- Every run is stored and replayable; the pure scoring core is unit-tested.

## 2:40 Business (20s)
- B2B: continuous compliance audits for brands, agencies and consumer associations: "your exit flow, graded every week, with evidence".
- B2C: "cancel it for me", which works on any site because it uses the UI, not an integration.
- One audit costs a few cents of agent time.

## Close (5s)
"Signing up takes one click. Escape Hatch makes sure leaving does too."

## Backup answers
- *Why not scrape the DOM?* Dark patterns are visual: size, color, position, contrast, fake close buttons. And chatbot retention flows need an agent that converses.
- *Legality of the audits?* We only act as a regular visitor, on public pages or with the user's own account; there is no load beyond one human session.
- *False positives?* The ground-truth benchmark measures precision; every finding is quoted from the screenshot and kept as evidence for human review.
