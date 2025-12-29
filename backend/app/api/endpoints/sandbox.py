from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.core.deps import (
    SandboxContext,
    get_sandbox_context,
    get_sandbox_service_for_context,
)
from app.models.schemas import (
    AddSecretRequest,
    FileContentResponse,
    FileMetadata,
    IDEUrlResponse,
    MessageResponse,
    PortPreviewLink,
    PreviewLinksResponse,
    SandboxFilesMetadataResponse,
    SecretResponse,
    SecretsListResponse,
    UpdateFileRequest,
    UpdateFileResponse,
    UpdateIDEThemeRequest,
    UpdateSecretRequest,
)
from app.services.exceptions import SandboxException
from app.services.sandbox import SandboxService


router = APIRouter()

P = ParamSpec("P")
T = TypeVar("T")


def handle_sandbox_errors(
    operation: str,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                raise
            except SandboxException as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e),
                ) from e
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to {operation}: {str(e)}",
                ) from e

        return wrapper

    return decorator


@router.get("/{sandbox_id}/preview-links", response_model=PreviewLinksResponse)
async def get_preview_links(
    context: SandboxContext = Depends(get_sandbox_context),
    sandbox_service: SandboxService = Depends(get_sandbox_service_for_context),
) -> PreviewLinksResponse:
    links = await sandbox_service.get_preview_links(context.sandbox_id)
    return PreviewLinksResponse(links=[PortPreviewLink(**link) for link in links])


@router.get("/{sandbox_id}/ide-url", response_model=IDEUrlResponse)
async def get_ide_url(
    context: SandboxContext = Depends(get_sandbox_context),
    sandbox_service: SandboxService = Depends(get_sandbox_service_for_context),
) -> IDEUrlResponse:
    url = await sandbox_service.get_ide_url(context.sandbox_id)
    return IDEUrlResponse(url=url)


@router.get(
    "/{sandbox_id}/files/metadata",
    response_model=SandboxFilesMetadataResponse,
)
async def get_files_metadata(
    context: SandboxContext = Depends(get_sandbox_context),
    sandbox_service: SandboxService = Depends(get_sandbox_service_for_context),
) -> SandboxFilesMetadataResponse:
    files = await sandbox_service.get_files_metadata(context.sandbox_id)
    return SandboxFilesMetadataResponse(files=[FileMetadata(**f) for f in files])


@router.get(
    "/{sandbox_id}/files/content/{file_path:path}", response_model=FileContentResponse
)
async def get_file_content(
    file_path: str,
    context: SandboxContext = Depends(get_sandbox_context),
    sandbox_service: SandboxService = Depends(get_sandbox_service_for_context),
) -> FileContentResponse:
    try:
        file_data = await sandbox_service.get_file_content(
            context.sandbox_id, file_path
        )
        return FileContentResponse(**file_data)
    except SandboxException as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get file content: {str(e)}",
        )


@router.put("/{sandbox_id}/files", response_model=UpdateFileResponse)
@handle_sandbox_errors("update file")
async def update_file_in_sandbox(
    request: UpdateFileRequest,
    context: SandboxContext = Depends(get_sandbox_context),
    sandbox_service: SandboxService = Depends(get_sandbox_service_for_context),
) -> UpdateFileResponse:
    await sandbox_service.write_file(
        context.sandbox_id, request.file_path, request.content
    )
    return UpdateFileResponse(
        success=True, message=f"File {request.file_path} updated successfully"
    )


@router.get("/{sandbox_id}/secrets", response_model=SecretsListResponse)
@handle_sandbox_errors("get secrets")
async def get_secrets(
    context: SandboxContext = Depends(get_sandbox_context),
    sandbox_service: SandboxService = Depends(get_sandbox_service_for_context),
) -> SecretsListResponse:
    secrets = await sandbox_service.get_secrets(context.sandbox_id)
    return SecretsListResponse(secrets=[SecretResponse(**s) for s in secrets])


@router.post("/{sandbox_id}/secrets", response_model=MessageResponse)
@handle_sandbox_errors("add secret")
async def add_secret(
    secret_data: AddSecretRequest,
    context: SandboxContext = Depends(get_sandbox_context),
    sandbox_service: SandboxService = Depends(get_sandbox_service_for_context),
) -> MessageResponse:
    await sandbox_service.add_secret(
        context.sandbox_id, secret_data.key, secret_data.value
    )
    return MessageResponse(message=f"Secret {secret_data.key} added successfully")


@router.put("/{sandbox_id}/secrets/{key}", response_model=MessageResponse)
@handle_sandbox_errors("update secret")
async def update_secret(
    key: str,
    secret_data: UpdateSecretRequest,
    context: SandboxContext = Depends(get_sandbox_context),
    sandbox_service: SandboxService = Depends(get_sandbox_service_for_context),
) -> MessageResponse:
    await sandbox_service.update_secret(context.sandbox_id, key, secret_data.value)
    return MessageResponse(message=f"Secret {key} updated successfully")


@router.delete("/{sandbox_id}/secrets/{key}", response_model=MessageResponse)
@handle_sandbox_errors("delete secret")
async def delete_secret(
    key: str,
    context: SandboxContext = Depends(get_sandbox_context),
    sandbox_service: SandboxService = Depends(get_sandbox_service_for_context),
) -> MessageResponse:
    await sandbox_service.delete_secret(context.sandbox_id, key)
    return MessageResponse(message=f"Secret {key} deleted successfully")


@router.put("/{sandbox_id}/ide-theme", response_model=MessageResponse)
@handle_sandbox_errors("update IDE theme")
async def update_ide_theme(
    request: UpdateIDEThemeRequest,
    context: SandboxContext = Depends(get_sandbox_context),
    sandbox_service: SandboxService = Depends(get_sandbox_service_for_context),
) -> MessageResponse:
    await sandbox_service.update_ide_theme(context.sandbox_id, request.theme)
    return MessageResponse(message=f"IDE theme updated to {request.theme}")


@router.get("/{sandbox_id}/download-zip")
@handle_sandbox_errors("generate zip file")
async def download_sandbox_files(
    context: SandboxContext = Depends(get_sandbox_context),
    sandbox_service: SandboxService = Depends(get_sandbox_service_for_context),
) -> Response:
    zip_bytes = await sandbox_service.generate_zip_download(context.sandbox_id)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="sandbox_{context.sandbox_id}.zip"'
        },
    )
