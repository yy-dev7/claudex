from __future__ import annotations

import uuid

import pytest

from tests.conftest import SandboxTestContext


class TestSandboxPreviewLinks:
    async def test_get_preview_links(
        self,
        sandbox_test_context: SandboxTestContext,
    ) -> None:
        ctx = sandbox_test_context
        response = await ctx.client.get(
            f"/api/v1/sandbox/{ctx.chat.sandbox_id}/preview-links",
            headers=ctx.auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "links" in data
        assert isinstance(data["links"], list)

    async def test_get_preview_links_unauthorized(
        self,
        sandbox_test_context: SandboxTestContext,
    ) -> None:
        ctx = sandbox_test_context
        response = await ctx.client.get(
            f"/api/v1/sandbox/{ctx.chat.sandbox_id}/preview-links",
        )

        assert response.status_code == 401


class TestSandboxFiles:
    async def test_get_files_metadata(
        self,
        sandbox_test_context: SandboxTestContext,
    ) -> None:
        ctx = sandbox_test_context
        response = await ctx.client.get(
            f"/api/v1/sandbox/{ctx.chat.sandbox_id}/files/metadata",
            headers=ctx.auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        assert isinstance(data["files"], list)

    async def test_write_file(
        self,
        sandbox_test_context: SandboxTestContext,
    ) -> None:
        ctx = sandbox_test_context
        test_path = f"/home/user/test_{ctx.provider}.txt"
        test_content = f"Integration test content ({ctx.provider})"

        write_response = await ctx.client.put(
            f"/api/v1/sandbox/{ctx.chat.sandbox_id}/files",
            json={"file_path": test_path, "content": test_content},
            headers=ctx.auth_headers,
        )

        assert write_response.status_code == 200
        assert write_response.json()["success"] is True

    async def test_get_file_content(
        self,
        sandbox_test_context: SandboxTestContext,
    ) -> None:
        ctx = sandbox_test_context
        test_filename = f"read_test_{ctx.provider}.txt"
        test_path = f"/home/user/{test_filename}"
        test_content = f"Read test content ({ctx.provider})"

        await ctx.client.put(
            f"/api/v1/sandbox/{ctx.chat.sandbox_id}/files",
            json={"file_path": test_path, "content": test_content},
            headers=ctx.auth_headers,
        )

        response = await ctx.client.get(
            f"/api/v1/sandbox/{ctx.chat.sandbox_id}/files/content/{test_filename}",
            headers=ctx.auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "content" in data
        assert "path" in data
        assert data["path"] == test_filename
        assert data["content"] == test_content

    async def test_get_file_not_found(
        self,
        sandbox_test_context: SandboxTestContext,
    ) -> None:
        ctx = sandbox_test_context
        response = await ctx.client.get(
            f"/api/v1/sandbox/{ctx.chat.sandbox_id}/files/content/nonexistent/file.txt",
            headers=ctx.auth_headers,
        )

        assert response.status_code == 404


class TestSandboxSecrets:
    async def test_get_secrets(
        self,
        sandbox_test_context: SandboxTestContext,
    ) -> None:
        ctx = sandbox_test_context
        response = await ctx.client.get(
            f"/api/v1/sandbox/{ctx.chat.sandbox_id}/secrets",
            headers=ctx.auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "secrets" in data
        assert isinstance(data["secrets"], list)

    async def test_add_and_delete_secret(
        self,
        sandbox_test_context: SandboxTestContext,
    ) -> None:
        ctx = sandbox_test_context
        secret_key = f"TEST_SECRET_{ctx.provider.upper()}"
        secret_value = f"test_secret_value_{ctx.provider}"

        add_response = await ctx.client.post(
            f"/api/v1/sandbox/{ctx.chat.sandbox_id}/secrets",
            json={"key": secret_key, "value": secret_value},
            headers=ctx.auth_headers,
        )

        assert add_response.status_code == 200
        assert secret_key in add_response.json()["message"]

        delete_response = await ctx.client.delete(
            f"/api/v1/sandbox/{ctx.chat.sandbox_id}/secrets/{secret_key}",
            headers=ctx.auth_headers,
        )

        assert delete_response.status_code == 200

    async def test_update_secret(
        self,
        sandbox_test_context: SandboxTestContext,
    ) -> None:
        ctx = sandbox_test_context
        secret_key = f"UPDATE_SECRET_{ctx.provider.upper()}"
        secret_value = f"initial_value_{ctx.provider}"
        updated_value = f"updated_value_{ctx.provider}"

        await ctx.client.post(
            f"/api/v1/sandbox/{ctx.chat.sandbox_id}/secrets",
            json={"key": secret_key, "value": secret_value},
            headers=ctx.auth_headers,
        )

        update_response = await ctx.client.put(
            f"/api/v1/sandbox/{ctx.chat.sandbox_id}/secrets/{secret_key}",
            json={"value": updated_value},
            headers=ctx.auth_headers,
        )

        assert update_response.status_code == 200
        assert secret_key in update_response.json()["message"]

        await ctx.client.delete(
            f"/api/v1/sandbox/{ctx.chat.sandbox_id}/secrets/{secret_key}",
            headers=ctx.auth_headers,
        )


class TestSandboxDownload:
    async def test_download_zip(
        self,
        sandbox_test_context: SandboxTestContext,
    ) -> None:
        ctx = sandbox_test_context
        response = await ctx.client.get(
            f"/api/v1/sandbox/{ctx.chat.sandbox_id}/download-zip",
            headers=ctx.auth_headers,
        )

        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/zip"
        assert len(response.content) > 0


class TestSandboxIdeTheme:
    async def test_set_ide_theme(
        self,
        sandbox_test_context: SandboxTestContext,
    ) -> None:
        ctx = sandbox_test_context
        response = await ctx.client.put(
            f"/api/v1/sandbox/{ctx.chat.sandbox_id}/ide-theme",
            json={"theme": "dark"},
            headers=ctx.auth_headers,
        )

        assert response.status_code == 200

    async def test_set_ide_theme_unauthorized(
        self,
        sandbox_test_context: SandboxTestContext,
    ) -> None:
        ctx = sandbox_test_context
        response = await ctx.client.put(
            f"/api/v1/sandbox/{ctx.chat.sandbox_id}/ide-theme",
            json={"theme": "dark"},
        )

        assert response.status_code == 401


class TestSandboxIdeUrl:
    async def test_get_ide_url(
        self,
        sandbox_test_context: SandboxTestContext,
    ) -> None:
        ctx = sandbox_test_context
        response = await ctx.client.get(
            f"/api/v1/sandbox/{ctx.chat.sandbox_id}/ide-url",
            headers=ctx.auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "url" in data
        if ctx.provider == "docker":
            assert data["url"] is not None
            assert "http" in data["url"]

    async def test_get_ide_url_unauthorized(
        self,
        sandbox_test_context: SandboxTestContext,
    ) -> None:
        ctx = sandbox_test_context
        response = await ctx.client.get(
            f"/api/v1/sandbox/{ctx.chat.sandbox_id}/ide-url",
        )

        assert response.status_code == 401


class TestSandboxUnauthorized:
    @pytest.mark.parametrize(
        "method,endpoint_suffix,json_body",
        [
            ("GET", "/preview-links", None),
            ("GET", "/files/metadata", None),
            ("PUT", "/files", {"file_path": "/test.txt", "content": "test"}),
            ("GET", "/files/content/test.txt", None),
            ("GET", "/secrets", None),
            ("POST", "/secrets", {"key": "TEST", "value": "test"}),
            ("PUT", "/secrets/TEST", {"value": "updated"}),
            ("DELETE", "/secrets/TEST", None),
            ("GET", "/download-zip", None),
            ("PUT", "/ide-theme", {"theme": "dark"}),
            ("GET", "/ide-url", None),
        ],
    )
    async def test_sandbox_endpoints_unauthorized(
        self,
        sandbox_test_context: SandboxTestContext,
        method: str,
        endpoint_suffix: str,
        json_body: dict | None,
    ) -> None:
        ctx = sandbox_test_context
        endpoint = f"/api/v1/sandbox/{ctx.chat.sandbox_id}{endpoint_suffix}"

        if method == "GET":
            response = await ctx.client.get(endpoint)
        elif method == "PUT":
            response = await ctx.client.put(endpoint, json=json_body)
        elif method == "POST":
            response = await ctx.client.post(endpoint, json=json_body)
        elif method == "DELETE":
            response = await ctx.client.delete(endpoint)
        else:
            response = await ctx.client.request(method, endpoint)

        assert response.status_code == 401


class TestSandboxNotFound:
    @pytest.mark.parametrize(
        "method,endpoint_suffix,json_body",
        [
            ("GET", "/preview-links", None),
            ("GET", "/files/metadata", None),
            ("PUT", "/files", {"file_path": "/test.txt", "content": "test"}),
            ("GET", "/files/content/test.txt", None),
            ("GET", "/secrets", None),
            ("POST", "/secrets", {"key": "TEST", "value": "test"}),
            ("PUT", "/secrets/TEST", {"value": "updated"}),
            ("DELETE", "/secrets/TEST", None),
            ("GET", "/download-zip", None),
            ("PUT", "/ide-theme", {"theme": "dark"}),
            ("GET", "/ide-url", None),
        ],
    )
    async def test_sandbox_endpoints_not_found(
        self,
        sandbox_test_context: SandboxTestContext,
        method: str,
        endpoint_suffix: str,
        json_body: dict | None,
    ) -> None:
        ctx = sandbox_test_context
        fake_sandbox_id = f"fake-sandbox-{uuid.uuid4().hex[:8]}"
        endpoint = f"/api/v1/sandbox/{fake_sandbox_id}{endpoint_suffix}"

        if method == "GET":
            response = await ctx.client.get(endpoint, headers=ctx.auth_headers)
        elif method == "PUT":
            response = await ctx.client.put(
                endpoint, json=json_body, headers=ctx.auth_headers
            )
        elif method == "POST":
            response = await ctx.client.post(
                endpoint, json=json_body, headers=ctx.auth_headers
            )
        else:
            response = await ctx.client.request(
                method, endpoint, headers=ctx.auth_headers
            )

        assert response.status_code == 404
