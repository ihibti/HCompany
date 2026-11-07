from dataclasses import dataclass

from escapehatch.prompts import Task


@dataclass(frozen=True)
class LegalRef:
    code: str
    jurisdiction: str
    title: str
    summary: str
    url: str


GDPR_7_3 = LegalRef(
    code="GDPR Art. 7(3)",
    jurisdiction="EU",
    title="Withdrawing consent must be as easy as giving it",
    summary="Regulation (EU) 2016/679 requires that it be as easy to withdraw consent as to give it.",
    url="https://eur-lex.europa.eu/eli/reg/2016/679/oj",
)
EPRIVACY_5_3 = LegalRef(
    code="ePrivacy Directive Art. 5(3)",
    jurisdiction="EU",
    title="Consent required for non-essential cookies",
    summary="Directive 2002/58/EC requires prior consent before storing or reading non-essential trackers on a user's device (transposed in France by Art. 82 of the Loi Informatique et Libertés).",
    url="https://eur-lex.europa.eu/eli/dir/2002/58/oj",
)
CNIL_GUIDELINES = LegalRef(
    code="CNIL Délibérations 2020-091 / 2020-092",
    jurisdiction="FR",
    title="Refusing cookies must be as easy as accepting them",
    summary="The CNIL guidelines and recommendation on cookies require that refusing be as simple as accepting. In January 2022 the CNIL fined Google €150M and Facebook €60M because refusing took more clicks than accepting.",
    url="https://www.cnil.fr/fr/cookies-et-autres-traceurs/regles/cookies/lignes-directrices-modificatives-et-recommandation",
)
DSA_25 = LegalRef(
    code="DSA Art. 25",
    jurisdiction="EU",
    title="Ban on deceptive interface design by online platforms",
    summary="Regulation (EU) 2022/2065 forbids online platforms from designing interfaces that deceive or manipulate users, including giving more prominence to certain choices, repeatedly requesting a choice already made, and making termination harder than subscribing.",
    url="https://eur-lex.europa.eu/eli/reg/2022/2065/oj",
)
UCPD = LegalRef(
    code="Directive 2005/29/EC",
    jurisdiction="EU",
    title="Unfair Commercial Practices Directive",
    summary="Prohibits misleading and aggressive commercial practices, including non-contractual barriers to terminating a contract.",
    url="https://eur-lex.europa.eu/eli/dir/2005/29/oj",
)
FR_L215_1_1 = LegalRef(
    code="Code de la consommation L215-1-1",
    jurisdiction="FR",
    title="Résiliation en trois clics",
    summary="Since 1 June 2023 (loi n° 2022-1158), a contract that can be concluded online must be cancellable online through a free, easily accessible feature.",
    url="https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000046190107",
)
US_ROSCA = LegalRef(
    code="ROSCA, 15 U.S.C. § 8403",
    jurisdiction="US",
    title="Simple mechanism to stop recurring charges",
    summary="The Restore Online Shoppers' Confidence Act requires online negative-option sellers to provide simple mechanisms to stop recurring charges. (The FTC's 2024 click-to-cancel rule was vacated in July 2025; ROSCA still applies.)",
    url="https://www.law.cornell.edu/uscode/text/15/8403",
)
CA_ARL = LegalRef(
    code="Cal. Bus. & Prof. Code § 17602",
    jurisdiction="US-CA",
    title="California Automatic Renewal Law",
    summary="Consumers who sign up online must be able to cancel online, without obstruction.",
    url="https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=BPC&sectionNum=17602",
)
FR_L34_5 = LegalRef(
    code="CPCE L34-5",
    jurisdiction="FR",
    title="Free and simple opt-out from marketing emails",
    summary="Every marketing email must offer a simple, free way to object to further messages.",
    url="https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000042155961",
)
US_CAN_SPAM = LegalRef(
    code="CAN-SPAM, 15 U.S.C. § 7704",
    jurisdiction="US",
    title="Working opt-out in commercial email",
    summary="Commercial emails must include a working opt-out mechanism, and opt-out requests must be honored within 10 business days.",
    url="https://www.law.cornell.edu/uscode/text/15/7704",
)

TASK_BASELINE: dict[Task, tuple[LegalRef, ...]] = {
    Task.REFUSE_COOKIES: (EPRIVACY_5_3, CNIL_GUIDELINES, GDPR_7_3),
    Task.CANCEL_SUBSCRIPTION: (FR_L215_1_1, US_ROSCA, CA_ARL),
    Task.UNSUBSCRIBE: (FR_L34_5, US_CAN_SPAM),
}

PATTERN_REFS: dict[str, tuple[LegalRef, ...]] = {
    "asymmetric_choice": (DSA_25,),
    "hidden_option": (DSA_25,),
    "forced_action": (UCPD,),
    "confirmshaming": (DSA_25, UCPD),
    "nagging": (DSA_25,),
    "obstruction": (DSA_25, UCPD),
    "misdirection": (DSA_25, UCPD),
    "preselection": (GDPR_7_3,),
    "false_urgency": (UCPD,),
    "sneaking": (UCPD,),
    "trick_question": (DSA_25, UCPD),
}


def applicable_refs(task: Task, pattern_ids: list[str]) -> list[LegalRef]:
    refs: list[LegalRef] = []
    for ref in TASK_BASELINE.get(task, ()):
        if ref not in refs:
            refs.append(ref)
    for pattern_id in pattern_ids:
        for ref in PATTERN_REFS.get(pattern_id, ()):
            if ref not in refs:
                refs.append(ref)
    return refs
