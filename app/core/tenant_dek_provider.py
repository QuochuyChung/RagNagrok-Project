"""
Tenant DEK provider.

Resolves a plaintext AES-256 DEK for a given Tenant object or encrypted_dek
blob by delegating to AWS KMS (or local KEK fallback via app.core.encryption).

Design decisions:
    - NO in-process caching in this module.  The FastAPI dependency or service
      layer is responsible for passing the DEK around within a single request.
      This keeps this module stateless and easily testable.
    - Accepts either a ``Tenants`` ORM model or raw ``encrypted_dek`` bytes so
      callers don't have to import the ORM model just to unwrap a key.

Usage (inside a service / dependency):
    from app.core.tenant_dek_provider import get_plaintext_dek

    plaintext_dek = await get_plaintext_dek(tenant)          # from ORM model
    plaintext_dek = await get_plaintext_dek_from_blob(blob, tenant_name)
"""

from __future__ import annotations

from app.core.encryption import unwrap_tenant_dek
from app.core.logging import get_logger

logger = get_logger(__name__)


async def get_plaintext_dek(tenant) -> bytes:
    """
    Unwrap the tenant's DEK given a ``Tenants`` ORM object.

    Args:
        tenant: A ``Tenants`` SQLAlchemy model instance. Must have
                ``encrypted_dek`` (bytes) and ``tenant_name`` (str) attributes.

    Returns:
        32-byte plaintext AES-256 DEK.

    Raises:
        RuntimeError: If KMS has a network/timeout error and no fallback is possible.
        ValueError: If the wrapped blob is corrupt or the wrong key is used.
    """
    if not tenant.encrypted_dek:
        raise ValueError(
            f"Tenant '{tenant.tenant_name}' has no encrypted_dek stored. "
            "Re-create the tenant or run a migration to generate a DEK."
        )
    return await unwrap_tenant_dek(tenant.encrypted_dek, tenant.tenant_name)


async def get_plaintext_dek_from_blob(encrypted_dek: bytes, tenant_name: str) -> bytes:
    """
    Unwrap a raw encrypted DEK blob without needing the full ORM model.

    Args:
        encrypted_dek: Raw bytes from the ``tenants.encrypted_dek`` column.
        tenant_name:   The tenant's name (used as KMS EncryptionContext / AAD).

    Returns:
        32-byte plaintext AES-256 DEK.
    """
    return await unwrap_tenant_dek(encrypted_dek, tenant_name)
