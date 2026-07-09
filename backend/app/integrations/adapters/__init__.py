"""
Integration adapter registry.

Maps provider names to adapter classes. The polling engine and
integration management API use this to instantiate the right adapter
for each integration record.
"""

from app.integrations.adapters.danfoss_alsense import DanfossAlsenseAdapter
from app.integrations.adapters.emerson_oversight import EmersonOversightAdapter
from app.integrations.adapters.schneider_ecostruxure import SchneiderEcoStruxureAdapter
from app.integrations.adapters.jci_openblue import JCIOpenBlueAdapter, JCIMetasysAdapter
from app.integrations.adapters.honeywell_niagara import HoneywellNiagaraAdapter
from app.integrations.adapters.modbus_tcp import ModbusTCPAdapter
from app.integrations.adapters.bacnet_ip import BACnetIPAdapter
from app.integrations.adapters.dickson_dicksonone import DicksonDicksonOneAdapter

# Provider name → adapter class
ADAPTER_REGISTRY: dict[str, type] = {
    "danfoss_alsense": DanfossAlsenseAdapter,
    "emerson_oversight": EmersonOversightAdapter,
    "schneider_ecostruxure": SchneiderEcoStruxureAdapter,
    "jci_openblue": JCIOpenBlueAdapter,
    "jci_metasys": JCIMetasysAdapter,
    "honeywell_niagara": HoneywellNiagaraAdapter,
    "modbus_tcp": ModbusTCPAdapter,
    "bacnet_ip": BACnetIPAdapter,
    "dickson_dicksonone": DicksonDicksonOneAdapter,
}


def get_adapter_class(provider: str):
    """Get adapter class by provider name."""
    cls = ADAPTER_REGISTRY.get(provider)
    if not cls:
        raise ValueError(
            f"Unknown provider '{provider}'. "
            f"Available: {', '.join(ADAPTER_REGISTRY.keys())}"
        )
    return cls


def list_providers() -> list[dict]:
    """List all available providers with metadata."""
    return [
        {
            "provider": name,
            "integration_type": cls.integration_type,
            "supports_write": hasattr(cls, 'write') and cls.write is not None,
        }
        for name, cls in ADAPTER_REGISTRY.items()
    ]
