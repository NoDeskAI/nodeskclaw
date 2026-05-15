import { ERROR_CODES } from '@nodeskai/genehub-types';
import type { Context } from 'hono';

export class AppError extends Error {
  constructor(
    public code: number,
    public errorCode: string,
    message: string,
    public status: number = 400,
  ) {
    super(message);
    this.name = 'AppError';
  }

  static geneNotFound(slug: string) {
    return new AppError(ERROR_CODES.GENE_NOT_FOUND, 'gene_not_found', `基因 ${slug} 不存在`, 404);
  }

  static slugExists(slug: string) {
    return new AppError(
      ERROR_CODES.GENE_SLUG_EXISTS,
      'gene_slug_exists',
      `基因 slug ${slug} 已存在`,
      409,
    );
  }

  static manifestInvalid(detail: string) {
    return new AppError(
      ERROR_CODES.GENE_MANIFEST_INVALID,
      'gene_manifest_invalid',
      `Manifest 校验失败: ${detail}`,
      422,
    );
  }

  static versionNotFound(slug: string, version: string) {
    return new AppError(
      ERROR_CODES.GENE_VERSION_NOT_FOUND,
      'gene_version_not_found',
      `基因 ${slug} 版本 ${version} 不存在`,
      404,
    );
  }

  static versionConflict(slug: string, version: string) {
    return new AppError(
      ERROR_CODES.GENE_VERSION_CONFLICT,
      'gene_version_conflict',
      `基因 ${slug} 版本 ${version} 已存在`,
      409,
    );
  }

  static genomeNotFound(slug: string) {
    return new AppError(
      ERROR_CODES.GENOME_NOT_FOUND,
      'genome_not_found',
      `基因组 ${slug} 不存在`,
      404,
    );
  }

  static genomeSlugExists(slug: string) {
    return new AppError(
      ERROR_CODES.GENOME_SLUG_EXISTS,
      'genome_slug_exists',
      `基因组 slug ${slug} 已存在`,
      409,
    );
  }

  static genomeVersionConflict(slug: string, version: string) {
    return new AppError(
      ERROR_CODES.GENOME_VERSION_CONFLICT,
      'genome_version_conflict',
      `基因组 ${slug} 版本 ${version} 已存在`,
      409,
    );
  }

  static genomeVersionNotFound(slug: string, version: string) {
    return new AppError(
      ERROR_CODES.GENOME_VERSION_NOT_FOUND,
      'genome_version_not_found',
      `基因组 ${slug} 版本 ${version} 不存在`,
      404,
    );
  }

  static templateNotFound(slug: string) {
    return new AppError(
      ERROR_CODES.TEMPLATE_NOT_FOUND,
      'template_not_found',
      `AI 员工模板 ${slug} 不存在`,
      404,
    );
  }

  static templateSlugExists(slug: string) {
    return new AppError(
      ERROR_CODES.TEMPLATE_SLUG_EXISTS,
      'template_slug_exists',
      `AI 员工模板 slug ${slug} 已存在`,
      409,
    );
  }

  static templateVersionConflict(slug: string, version: string) {
    return new AppError(
      ERROR_CODES.TEMPLATE_VERSION_CONFLICT,
      'template_version_conflict',
      `AI 员工模板 ${slug} 版本 ${version} 已存在`,
      409,
    );
  }

  static templateVersionNotFound(slug: string, version: string) {
    return new AppError(
      ERROR_CODES.TEMPLATE_VERSION_NOT_FOUND,
      'template_version_not_found',
      `AI 员工模板 ${slug} 版本 ${version} 不存在`,
      404,
    );
  }

  static templateValidationFailed(detail: string) {
    return new AppError(
      ERROR_CODES.TEMPLATE_VALIDATION_FAILED,
      'template_validation_failed',
      `AI 员工模板校验失败: ${detail}`,
      422,
    );
  }

  static genomeValidationFailed(detail: string) {
    return new AppError(
      ERROR_CODES.GENOME_VALIDATION_FAILED,
      'genome_validation_failed',
      `基因组校验失败: ${detail}`,
      422,
    );
  }

  static dependencyResolveFailed(detail: string) {
    return new AppError(
      ERROR_CODES.DEPENDENCY_RESOLVE_FAILED,
      'dependency_resolve_failed',
      `依赖解析失败: ${detail}`,
      422,
    );
  }

  static compatibilityMismatch(detail: string) {
    return new AppError(
      ERROR_CODES.COMPATIBILITY_MISMATCH,
      'compatibility_mismatch',
      `兼容性不匹配: ${detail}`,
      422,
    );
  }

  static tokenInvalid() {
    return new AppError(ERROR_CODES.TOKEN_INVALID, 'token_invalid', '无效的 API Token', 401);
  }

  static permissionDenied() {
    return new AppError(ERROR_CODES.PERMISSION_DENIED, 'permission_denied', '权限不足', 403);
  }

  static giteaUnavailable() {
    return new AppError(
      ERROR_CODES.GITEA_UNAVAILABLE,
      'gitea_unavailable',
      'Gitea 文件存储服务不可用',
      503,
    );
  }

  static giteaRepoError(detail: string) {
    return new AppError(
      ERROR_CODES.GITEA_REPO_ERROR,
      'gitea_repo_error',
      `Gitea 仓库操作失败: ${detail}`,
      502,
    );
  }

  static internal(message = '内部错误') {
    return new AppError(ERROR_CODES.INTERNAL_ERROR, 'internal_error', message, 500);
  }
}

export function errorHandler(err: Error, c: Context) {
  if (err instanceof AppError) {
    return c.json(
      { code: err.code, error_code: err.errorCode, message: err.message, data: null },
      err.status as 400,
    );
  }

  console.error('Unhandled error:', err);
  return c.json(
    {
      code: ERROR_CODES.INTERNAL_ERROR,
      error_code: 'internal_error',
      message: '内部错误',
      data: null,
    },
    500,
  );
}
