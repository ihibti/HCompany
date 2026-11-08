from enum import Enum


class Task(str, Enum):
    REFUSE_COOKIES = "refuse_cookies"
    ACCEPT_COOKIES = "accept_cookies"
    CANCEL_SUBSCRIPTION = "cancel_subscription"
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"


ENTER_COUNTERPART: dict[Task, Task] = {
    Task.REFUSE_COOKIES: Task.ACCEPT_COOKIES,
    Task.CANCEL_SUBSCRIPTION: Task.SUBSCRIBE,
}

LEAVE_TASKS = {Task.REFUSE_COOKIES, Task.CANCEL_SUBSCRIPTION, Task.UNSUBSCRIBE}

COMMON_RULES = """Rules:
- Work only on the website given. Do not log in with any account unless credentials are provided below. Never enter payment details.
- Behave like a regular visitor using the screen: do not use web search, do not fetch page source code or files, do not visit other websites (including code repositories), and do not type URLs you have not seen as links on the site, except the starting URL. The user is measuring the path the site offers, so shortcuts make the audit worthless.
- Count every click, key press and form submission you make; the user is measuring how much effort this site demands.
- Read the screen carefully. Sites may use misleading button colors, swapped button positions, double negatives, fake close buttons and pre-checked boxes. Do what the goal says, not what the design nudges you toward.
- If you get stuck in a loop or the goal is impossible on this site, stop and report it honestly instead of guessing.
- If the site itself refuses to load for you (an "Access Denied" page, a bot-protection or CAPTCHA challenge, an error page, a region block), set access_blocked to true and stop: that is not a dark pattern and the goal must not be reported as impossible.
- When you are done, answer with the structured report."""

TASK_PROMPTS: dict[Task, str] = {
    Task.REFUSE_COOKIES: """Go to {url}.
Goal: refuse all non-essential cookies (tracking, advertising, analytics, personalisation) with the fewest possible interactions.
- Never click a button that accepts cookies, even partially ("Accept", "Agree", "OK", "Continue with cookies", "Accepter").
- If there is no direct refuse button, look for options such as "Customize", "Settings", "Parameters", "Learn more", a small "Continue without accepting" link or a close cross, then switch every optional purpose and vendor off and save.
- If refusing requires paying or subscribing (a "cookie wall"), do not pay; report the outcome as impossible.
- If no cookie banner ever appears, report that.
{rules}""",
    Task.ACCEPT_COOKIES: """Go to {url}.
Goal: accept all cookies with the fewest possible interactions, then stop.
- If no cookie banner ever appears, report that.
{rules}""",
    Task.CANCEL_SUBSCRIPTION: """Go to {url}.
Goal: fully cancel the paid subscription of the account so that it will not be billed again.
{credentials}
- Cancelling means a final, confirmed cancellation. Pausing, downgrading, switching plans, accepting a discount or a free month, or "talking to an advisor later" is NOT cancelling. Decline every retention offer.
- If a chat or form asks why you are leaving, give a short neutral answer such as "I no longer need the service" and insist on cancelling.
- Before the final irreversible click that actually cancels, call the request_confirmation tool describing the exact button you are about to click, and only proceed if it returns "approved". If it returns anything else, stop and report.
- You are done only when the site clearly states the subscription is cancelled.
{rules}""",
    Task.SUBSCRIBE: """Go to {url}.
Goal: start the subscription or free trial with the fewest possible interactions and stop at the first screen that confirms you are subscribed.
{credentials}
- Do not enter real payment details. If a payment form is required, stop there and report the number of interactions it took to reach it.
{rules}""",
    Task.UNSUBSCRIBE: """Go to {url}.
Goal: unsubscribe this email address from all marketing emails with the fewest possible interactions.
{credentials}
- Choose "unsubscribe from all" rather than reducing frequency or picking topics.
- You are done only when the site confirms the unsubscription.
{rules}""",
}


def build_task_prompt(task: Task, url: str, credentials: str | None = None) -> str:
    creds = f"Account details you may use: {credentials}" if credentials else "No account credentials are provided."
    return TASK_PROMPTS[task].format(url=url, credentials=creds, rules=COMMON_RULES)


PATTERN_DEFINITIONS: dict[str, str] = {
    "asymmetric_choice": "The option the user is likely to want (refuse, cancel) is visually weaker than the one the business wants: smaller, grey, a text link instead of a button, or placed out of the way.",
    "hidden_option": "The option exists but is hidden behind extra layers, collapsed sections, scrolling, footers or vague labels.",
    "forced_action": "The user cannot continue without doing something they did not ask for (accepting, subscribing, paying, creating an account).",
    "confirmshaming": "Wording that guilts or shames the user for declining, such as 'No thanks, I like paying full price'.",
    "nagging": "The same request or offer is shown again after the user already declined.",
    "obstruction": "Extra steps that add effort without serving the user: mandatory surveys, re-entering passwords, chats, phone calls, long multi-page flows.",
    "misdirection": "Design that draws attention away from the user's goal: swapped button positions, primary styling on the business option, fake close buttons, distracting offers.",
    "preselection": "Options that favour the business are pre-ticked or pre-enabled by default.",
    "false_urgency": "Countdowns, 'last chance' banners or scarcity claims meant to pressure the decision.",
    "sneaking": "The outcome is quietly different from what the user chose, such as a pause or downgrade presented as if it were the cancellation.",
    "trick_question": "Confusing wording such as double negatives that makes the user pick the opposite of what they intend.",
}

CLASSIFIER_SYSTEM_PROMPT = """You are an expert auditor of deceptive design ("dark patterns") in user interfaces, working for a consumer-protection compliance team.
You receive one screenshot taken while an agent was trying to complete a goal on a website. Report only dark patterns that are visible in this screenshot and that hinder the stated goal. Do not speculate about anything not visible. If the screen is neutral, return an empty list.

Pattern taxonomy (use these exact ids):
{definitions}

Severity scale: 1 = mild nudge, 2 = clear manipulation that costs the user effort, 3 = blocks or reverses the user's choice.
For every finding, quote the exact visible text or describe the exact visual element as evidence."""


def build_classifier_system_prompt() -> str:
    definitions = "\n".join(f"- {key}: {text}" for key, text in PATTERN_DEFINITIONS.items())
    return CLASSIFIER_SYSTEM_PROMPT.format(definitions=definitions)


def build_classifier_user_prompt(task: Task, url: str | None, step_note: str | None) -> str:
    goal = {
        Task.REFUSE_COOKIES: "refuse all non-essential cookies",
        Task.ACCEPT_COOKIES: "accept cookies",
        Task.CANCEL_SUBSCRIPTION: "cancel a paid subscription",
        Task.SUBSCRIBE: "subscribe",
        Task.UNSUBSCRIBE: "unsubscribe from marketing emails",
    }[task]
    lines = [f"User goal: {goal}."]
    if url:
        lines.append(f"Page URL: {url}")
    if step_note:
        lines.append(f"What the agent was doing: {step_note}")
    lines.append("List the dark patterns visible in this screenshot that work against the user goal.")
    return "\n".join(lines)
