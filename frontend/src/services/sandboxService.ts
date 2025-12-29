import { apiClient } from '@/lib/api';
import { ensureResponse, NotFoundError, serviceCall, ValidationError } from '@/services/base';
import type {
  FileContent,
  FileMetadata,
  PortInfo,
  PreviewLinksResponse,
  Secret,
  UpdateFileResult,
} from '@/types';
import { logger } from '@/utils/logger';
import { validateRequired } from '@/utils/validation';

async function getPreviewLinks(sandboxId: string): Promise<PortInfo[]> {
  validateRequired(sandboxId, 'Sandbox ID');

  try {
    return await serviceCall(async () => {
      const response = await apiClient.get<PreviewLinksResponse>(
        `/sandbox/${sandboxId}/preview-links`,
      );
      if (!response || !response.links) {
        return [];
      }

      return response.links.map((link) => ({
        port: link.port,
        previewUrl: link.preview_url,
      }));
    });
  } catch (error) {
    logger.error('Preview links fetch failed', 'sandboxService', error);
    return [];
  }
}

async function getSandboxFilesMetadata(sandboxId: string): Promise<FileMetadata[]> {
  validateRequired(sandboxId, 'Sandbox ID');

  return serviceCall(async () => {
    const url = `/sandbox/${sandboxId}/files/metadata`;
    const response = await apiClient.get<{ files: FileMetadata[] }>(url);

    if (!response || !response.files) {
      return [];
    }

    return response.files;
  });
}

async function getFileContent(sandboxId: string, filePath: string): Promise<FileContent> {
  validateRequired(sandboxId, 'Sandbox ID');
  validateRequired(filePath, 'File path');

  return serviceCall(async () => {
    const url = `/sandbox/${sandboxId}/files/content/${filePath}`;
    const response = await apiClient.get<FileContent>(url);

    if (!response) {
      throw new NotFoundError('File not found');
    }

    return response;
  });
}

async function updateFile(
  sandboxId: string,
  filePath: string,
  content: string,
): Promise<UpdateFileResult> {
  validateRequired(sandboxId, 'Sandbox ID');
  validateRequired(filePath, 'File path');
  if (content === null || content === undefined) {
    throw new ValidationError('Content is required');
  }

  return serviceCall(async () => {
    const response = await apiClient.put<UpdateFileResult>(`/sandbox/${sandboxId}/files`, {
      file_path: filePath,
      content,
    });

    return ensureResponse(response, 'Update file operation returned no response');
  });
}

async function getSecrets(sandboxId: string): Promise<Secret[]> {
  validateRequired(sandboxId, 'Sandbox ID');

  return serviceCall(async () => {
    const response = await apiClient.get<{ secrets: Secret[] }>(`/sandbox/${sandboxId}/secrets`);

    if (!response || !response.secrets) {
      return [];
    }

    return response.secrets;
  });
}

async function addSecret(sandboxId: string, key: string, value: string): Promise<void> {
  validateRequired(sandboxId, 'Sandbox ID');
  validateRequired(key, 'Secret key');
  validateRequired(value, 'Secret value');

  await serviceCall(async () => {
    await apiClient.post(`/sandbox/${sandboxId}/secrets`, { key, value });
  });
}

async function updateSecret(sandboxId: string, key: string, value: string): Promise<void> {
  validateRequired(sandboxId, 'Sandbox ID');
  validateRequired(key, 'Secret key');
  validateRequired(value, 'Secret value');

  await serviceCall(async () => {
    await apiClient.put(`/sandbox/${sandboxId}/secrets/${key}`, { value });
  });
}

async function deleteSecret(sandboxId: string, key: string): Promise<void> {
  validateRequired(sandboxId, 'Sandbox ID');
  validateRequired(key, 'Secret key');

  await serviceCall(async () => {
    await apiClient.delete(`/sandbox/${sandboxId}/secrets/${key}`);
  });
}

async function downloadZip(sandboxId: string): Promise<Blob> {
  validateRequired(sandboxId, 'Sandbox ID');

  return serviceCall(async () => {
    const response = await apiClient.getBlob(`/sandbox/${sandboxId}/download-zip`);
    return ensureResponse(response, 'Download failed: No response received');
  });
}

async function updateIDETheme(sandboxId: string, theme: 'dark' | 'light'): Promise<void> {
  validateRequired(sandboxId, 'Sandbox ID');

  await serviceCall(async () => {
    await apiClient.put(`/sandbox/${sandboxId}/ide-theme`, { theme });
  });
}

async function getIDEUrl(sandboxId: string): Promise<string | null> {
  validateRequired(sandboxId, 'Sandbox ID');

  try {
    return await serviceCall(async () => {
      const response = await apiClient.get<{ url: string | null }>(`/sandbox/${sandboxId}/ide-url`);
      return response?.url ?? null;
    });
  } catch (error) {
    logger.error('IDE URL fetch failed', 'sandboxService', error);
    return null;
  }
}

export const sandboxService = {
  getPreviewLinks,
  getSandboxFilesMetadata,
  getFileContent,
  updateFile,
  getSecrets,
  addSecret,
  updateSecret,
  deleteSecret,
  downloadZip,
  updateIDETheme,
  getIDEUrl,
};
