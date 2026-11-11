"""Sector mandate templates: ready-made, machine-readable perimeters.

A template is a named, versioned perimeter for one kind of agent in one sector, with a
catalog that says in plain words what each action type means, and the legal references
the principal should check. It does not change how mandates work: a template only fills
in the perimeter arguments of ``create_mandate`` and records which template (id, version
and digest) the mandate was built from, in the mandate's metadata.

Usage::

    from amr.templates import get_template

    template = get_template("agent-sante-rgpd")
    kwargs = template.create_mandate_kwargs()  # perimeter arguments and metadata
    await create_mandate(principal_id=..., agent_id=..., scope=template.summary,
                         legal_basis_regulation=..., legal_basis_article=...,
                         duration_hours=template.default_duration_hours, **kwargs)
"""

from amr.templates.agent_assurance_sante_vie import AGENT_ASSURANCE_SANTE_VIE
from amr.templates.agent_credit import AGENT_CREDIT
from amr.templates.agent_rh_recrutement import AGENT_RH_RECRUTEMENT
from amr.templates.agent_sante_rgpd import AGENT_SANTE_RGPD
from amr.templates.agent_support_client import AGENT_SUPPORT_CLIENT
from amr.templates.base import LegalReference, MandateTemplate, Stewardship

AGENT_ASSURANCE_SANTE_VIE_ID = AGENT_ASSURANCE_SANTE_VIE.template_id
AGENT_CREDIT_ID = AGENT_CREDIT.template_id
AGENT_RH_RECRUTEMENT_ID = AGENT_RH_RECRUTEMENT.template_id
AGENT_SANTE_RGPD_ID = AGENT_SANTE_RGPD.template_id
AGENT_SUPPORT_CLIENT_ID = AGENT_SUPPORT_CLIENT.template_id

_TEMPLATES: dict[str, MandateTemplate] = {
    AGENT_ASSURANCE_SANTE_VIE.template_id: AGENT_ASSURANCE_SANTE_VIE,
    AGENT_CREDIT.template_id: AGENT_CREDIT,
    AGENT_RH_RECRUTEMENT.template_id: AGENT_RH_RECRUTEMENT,
    AGENT_SANTE_RGPD.template_id: AGENT_SANTE_RGPD,
    AGENT_SUPPORT_CLIENT.template_id: AGENT_SUPPORT_CLIENT,
}


def list_templates() -> list[str]:
    """Return the ids of the available templates, sorted."""
    return sorted(_TEMPLATES)


def get_template(template_id: str) -> MandateTemplate:
    """Return the template with this id, or raise KeyError."""
    try:
        return _TEMPLATES[template_id]
    except KeyError:
        raise KeyError(
            f"unknown mandate template {template_id!r}; available: {list_templates()}"
        ) from None


__all__ = [
    "AGENT_ASSURANCE_SANTE_VIE_ID",
    "AGENT_CREDIT_ID",
    "AGENT_RH_RECRUTEMENT_ID",
    "AGENT_SANTE_RGPD_ID",
    "AGENT_SUPPORT_CLIENT_ID",
    "LegalReference",
    "MandateTemplate",
    "Stewardship",
    "get_template",
    "list_templates",
]
