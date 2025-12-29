from app.core.config import get_settings
from app.services.exceptions import SandboxException
from app.services.sandbox_providers.base import SandboxProvider
from app.services.sandbox_providers.types import DockerConfig, SandboxProviderType

settings = get_settings()


def create_docker_config() -> DockerConfig:
    return DockerConfig(
        image=settings.DOCKER_IMAGE,
        network=settings.DOCKER_NETWORK,
        host=settings.DOCKER_HOST,
        preview_base_url=settings.DOCKER_PREVIEW_BASE_URL,
        sandbox_domain=settings.DOCKER_SANDBOX_DOMAIN,
        traefik_network=settings.DOCKER_TRAEFIK_NETWORK,
    )


def create_sandbox_provider(
    provider_type: SandboxProviderType | str,
    api_key: str | None = None,
    docker_config: DockerConfig | None = None,
) -> SandboxProvider:
    if isinstance(provider_type, str):
        provider_type = SandboxProviderType(provider_type)

    if provider_type == SandboxProviderType.E2B:
        from app.services.sandbox_providers.e2b_provider import E2BSandboxProvider

        if not api_key:
            raise SandboxException("E2B API key is required")
        return E2BSandboxProvider(api_key=api_key)

    if provider_type == SandboxProviderType.DOCKER:
        from app.services.sandbox_providers.docker_provider import (
            LocalDockerProvider,
        )

        config = docker_config or create_docker_config()
        return LocalDockerProvider(config=config)

    raise ValueError(f"Unknown provider type: {provider_type}")
