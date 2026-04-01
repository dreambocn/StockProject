from app.core.settings import Settings
from app.integrations.policy_provider import PolicyProvider
from app.integrations.policy_providers.csrc_provider import CsrcPolicyProvider
from app.integrations.policy_providers.gov_cn_provider import GovCnPolicyProvider
from app.integrations.policy_providers.miit_provider import MiitPolicyProvider
from app.integrations.policy_providers.ndrc_provider import NdrcPolicyProvider
from app.integrations.policy_providers.npc_provider import NpcPolicyProvider
from app.integrations.policy_providers.pbc_provider import PbcPolicyProvider


def build_policy_provider_registry(settings: Settings) -> list[PolicyProvider]:
    providers: list[PolicyProvider] = []
    if settings.policy_provider_gov_cn_enabled:
        providers.append(GovCnPolicyProvider())
    if settings.policy_provider_npc_enabled:
        providers.append(NpcPolicyProvider())
    if settings.policy_provider_pbc_enabled:
        providers.append(PbcPolicyProvider())
    if settings.policy_provider_csrc_enabled:
        providers.append(CsrcPolicyProvider())
    if settings.policy_provider_ndrc_enabled:
        providers.append(NdrcPolicyProvider())
    if settings.policy_provider_miit_enabled:
        providers.append(MiitPolicyProvider())
    return providers
