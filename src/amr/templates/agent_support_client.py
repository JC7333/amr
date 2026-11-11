"""Template ``agent-support-client``: an AI agent answering customers for a business.

What the agent may do: read the customer's account and history, answer a ticket while
saying that the answer comes from an AI, route a ticket, propose a commercial gesture,
and grant a commercial gesture under a ceiling (50 EUR per gesture by default; the
principal may lower it, never raise it). What it may never do: refuse a refund or a
complaint, terminate a contract, close an account, change payment details, export the
customer's data, or create a sub-agent (delegation is off, and ``agent.create`` is
forbidden).

Every decision that goes against the customer (refusing a refund or a complaint,
terminating, closing) is a forbidden action type: AMR enforces it on the action types,
it does not read what an answer says. Granting a gesture is the only allowed action type
meant to commit money: it must carry ``amount`` and ``currency``, at or below the ceiling.
The template sets no risk class; a mandate may add one, for example to shorten the
tokens of ``commercial_gesture.grant`` (``create_mandate_kwargs(risk_classes=...)``).

This template is a provisional sector baseline (``stewardship``): published by the AMR
registry until a body of the customer support sector takes it over, with no practitioner
review recorded yet.

The legal references are pointers for the principal, all marked ``to_verify``: they are
not legal advice and have not been reviewed by counsel.
"""

from amr.models.perimeter import Perimeter
from amr.templates.base import LegalReference, MandateTemplate, Stewardship

AGENT_SUPPORT_CLIENT = MandateTemplate(
    template_id="agent-support-client",
    version="1.0.0",
    title="Customer support agent (human decides against the customer)",
    sector="customer-support",
    summary=(
        "Answer customers for a business: read the customer's account and history, answer "
        "a ticket while saying the answer comes from an AI, route a ticket, propose a "
        "commercial gesture, grant a commercial gesture under a ceiling. Never refuse a "
        "refund or a complaint, terminate a contract, close an account, change payment "
        "details, export the customer's data, or create a sub-agent."
    ),
    perimeter=Perimeter(
        allowed_actions=(
            "customer_account.read",
            "ticket.answer",
            "ticket.route",
            "commercial_gesture.propose",
            "commercial_gesture.grant",
        ),
        forbidden_actions=(
            "refund.refuse",
            "complaint.refuse",
            "contract.terminate",
            "account.close",
            "payment_details.change",
            "customer_data.export",
            "agent.create",
        ),
        delegation_allowed=False,
        max_amount="50",
        currency="EUR",
        amount_actions=("commercial_gesture.grant",),
    ),
    actions={
        "customer_account.read": "Read the customer's account and the history of their "
        "tickets.",
        "ticket.answer": "Answer a ticket, saying that the answer comes from an AI.",
        "ticket.route": "Route a ticket to a human team or another queue.",
        "commercial_gesture.propose": "Propose a commercial gesture to a human, who "
        "decides.",
        "commercial_gesture.grant": "Grant a commercial gesture, with an amount at or "
        "below the mandate's ceiling.",
        "refund.refuse": "Forbidden: refuse a refund; a human decides.",
        "complaint.refuse": "Forbidden: reject a complaint; a human decides.",
        "contract.terminate": "Forbidden: terminate the customer's contract.",
        "account.close": "Forbidden: close the customer's account.",
        "payment_details.change": "Forbidden: change the customer's payment details.",
        "customer_data.export": "Forbidden: export or transfer the customer's data.",
        "agent.create": "Forbidden: create a sub-agent (delegation is off as well).",
    },
    default_duration_hours=720,
    legal_references=(
        LegalReference(
            reference="Regulation (EU) 2024/1689 (AI Act), Art. 50(1)",
            topic="Providers design AI systems that interact directly with natural persons "
            "so that those persons are informed they are interacting with an AI system, "
            "unless obvious. Applies from 2 August 2026.",
        ),
        LegalReference(
            reference="Regulation (EU) 2016/679 (GDPR), Art. 22",
            topic="Decisions based solely on automated processing, including profiling.",
        ),
        LegalReference(
            reference="Code de la consommation (FR), Art. L612-1",
            topic="Consumer's right to use a consumer mediator free of charge; the trader "
            "guarantees access to a mediation scheme.",
        ),
        LegalReference(
            reference="Code de la consommation (FR), Art. L616-1",
            topic="The trader gives the consumer the contact details of the competent "
            "mediator, including when a complaint made to its services has not settled "
            "the dispute.",
        ),
    ),
    notes=(
        "Legal references are pointers to check, not legal advice.",
        "Every decision that goes against the customer (refusing a refund or a "
        "complaint, terminating a contract, closing an account) stays with a human.",
        "AMR does not read answers or routings: an answer must not carry a refusal or a "
        "promise of money, and routing must not close a ticket; the system that receives "
        "the token checks that.",
        "The template does not say that the business must answer with an AI or that an "
        "AI answer meets the information duty of Art. 50(1): saying it is an AI is part "
        "of the action type ticket.answer, and AMR does not read the answer.",
        "The ceiling of a commercial gesture is 50 EUR per gesture by default; a mandate "
        "may lower it (create_mandate_kwargs(max_amount=...)), never raise it. There is no "
        "cumulative ceiling per period in this template: several gestures can add up, so "
        "a principal who needs a total cap adds period_max_amount and period_days to the "
        "create_mandate arguments.",
        "Any action that states an amount is checked against the ceiling: a proposal of a "
        "larger gesture is refused if its token states the amount, and is made without "
        "it.",
        "The agent names the action type it asks a token for: the system that receives "
        "the token must map each real operation to the right type (a refund refused in "
        "the ticketing system is refund.refuse; a gesture actually credited is "
        "commercial_gesture.grant).",
        "The template sets no risk class; a mandate may add one, for example to shorten "
        "the tokens of commercial_gesture.grant.",
        "Delegation is off for mandates under this one. The agent must not have access to "
        "create_mandate itself, or it could register a new root mandate for a sub-agent.",
        "When a body authorized the agent, record its decision (organ_decision) with the "
        "persons or roles it designates. AMR records what the principal declares: it does "
        "not check that the decision exists or that the people named are who they say.",
    ),
    organ_decision="optional",
    stewardship=Stewardship(
        status="provisional",
        held_by="AMR registry (mandatia.eu)",
        handover=(
            "Provisional baseline published by the registry until a body of the customer "
            "support sector takes it over; that body then holds the template and its "
            "versions."
        ),
        reviewers=(),
    ),
)
