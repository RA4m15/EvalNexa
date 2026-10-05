import { v2 as cloudinary, UploadApiResponse } from 'cloudinary';
import { Readable } from 'stream';
import { config } from '../config';
import { CloudinaryAssetMetadata } from '@evalnexa/types';

// Initialize Cloudinary with environment variables
cloudinary.config({
  cloud_name: config.cloudinary.cloudName,
  api_key: config.cloudinary.apiKey,
  api_secret: config.cloudinary.apiSecret,
  secure: true,
});

export const ALLOWED_MIME_TYPES = [
  'image/jpeg',
  'image/png',
  'image/webp',
  'application/pdf',
];

export const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024; // 25MB

/**
 * Validates file MIME type, size, and magic bytes if available
 */
export function validateMediaFile(file: {
  mimetype: string;
  size: number;
  originalname?: string;
  buffer?: Buffer;
}): { isValid: boolean; error?: string } {
  if (!file) {
    return { isValid: false, error: 'No media file provided' };
  }

  if (!ALLOWED_MIME_TYPES.includes(file.mimetype.toLowerCase())) {
    return {
      isValid: false,
      error: `Unsupported file format '${file.mimetype}'. Supported formats: JPEG, PNG, WEBP, PDF`,
    };
  }

  if (file.size > MAX_FILE_SIZE_BYTES) {
    return {
      isValid: false,
      error: `File size (${(file.size / (1024 * 1024)).toFixed(2)}MB) exceeds limit of ${MAX_FILE_SIZE_BYTES / (1024 * 1024)}MB`,
    };
  }

  // Validate file signature/magic numbers if buffer is present
  if (file.buffer && file.buffer.length >= 4) {
    const header = file.buffer.subarray(0, 4);
    const isJpeg = header[0] === 0xff && header[1] === 0xd8 && header[2] === 0xff;
    const isPng = header[0] === 0x89 && header[1] === 0x50 && header[2] === 0x4e && header[3] === 0x47;
    const isPdf = header[0] === 0x25 && header[1] === 0x50 && header[2] === 0x44 && header[3] === 0x46; // %PDF
    const isRiff = header[0] === 0x52 && header[1] === 0x49 && header[2] === 0x46 && header[3] === 0x46; // RIFF (for WEBP)

    if (!isJpeg && !isPng && !isPdf && !isRiff) {
      return {
        isValid: false,
        error: 'File content does not match allowed media signatures (JPEG, PNG, WEBP, PDF)',
      };
    }
  }

  return { isValid: true };
}

/**
 * Builds predictable, stable public ID without student PII
 * Format: evalnexa/exams/{examId}/answer-books/{answerBookId}/pages/page-{pageNumber}
 */
export function buildPagePublicId(
  examId: string,
  answerBookId: string,
  pageNumber: number
): string {
  const paddedPage = String(pageNumber).padStart(4, '0');
  return `evalnexa/exams/${examId}/answer-books/${answerBookId}/pages/page-${paddedPage}`;
}

/**
 * Builds predictable public ID for answer-book documents (e.g. combined PDF)
 */
export function buildDocumentPublicId(
  examId: string,
  answerBookId: string,
  docType = 'complete-booklet'
): string {
  return `evalnexa/exams/${examId}/answer-books/${answerBookId}/documents/${docType}`;
}

/**
 * Uploads a buffer directly to Cloudinary using upload_stream
 */
export async function uploadMediaBuffer(
  buffer: Buffer,
  options: {
    publicId: string;
    resourceType?: 'image' | 'raw' | 'auto';
    deliveryType?: 'upload' | 'authenticated' | 'private';
    overwrite?: boolean;
    format?: string;
  }
): Promise<CloudinaryAssetMetadata> {
  const resourceType = options.resourceType || 'auto';
  const deliveryType = options.deliveryType || 'upload';

  return new Promise((resolve, reject) => {
    const uploadStream = cloudinary.uploader.upload_stream(
      {
        public_id: options.publicId,
        resource_type: resourceType,
        type: deliveryType,
        overwrite: options.overwrite !== undefined ? options.overwrite : true,
        invalidate: true,
        format: options.format,
      },
      (error, result: UploadApiResponse | undefined) => {
        if (error || !result) {
          return reject(error || new Error('Cloudinary upload returned no result'));
        }

        resolve({
          publicId: result.public_id,
          assetId: result.asset_id,
          resourceType: result.resource_type,
          deliveryType: result.type,
          format: result.format,
          bytes: result.bytes,
          width: result.width,
          height: result.height,
        });
      }
    );

    const stream = Readable.from(buffer);
    stream.pipe(uploadStream);
  });
}

/**
 * Generates an authorized, time-limited, cryptographically signed Cloudinary delivery URL.
 * Does not expose API secrets.
 */
export function generateAuthorizedMediaUrl(
  publicId: string,
  options: {
    resourceType?: string;
    deliveryType?: string;
    format?: string;
    expiresInSeconds?: number;
  } = {}
): { secureUrl: string; expiresAt: string } {
  const expiresInSeconds = options.expiresInSeconds || 3600; // 1 hour default
  const expiresTimestamp = Math.floor(Date.now() / 1000) + expiresInSeconds;
  const expiresAt = new Date(expiresTimestamp * 1000).toISOString();

  const resourceType = options.resourceType || 'image';
  const deliveryType = options.deliveryType || 'upload';

  if (!cloudinary.config().cloud_name) {
    cloudinary.config({
      cloud_name: config.cloudinary.cloudName || process.env.CLOUDINARY_CLOUD_NAME,
      api_key: config.cloudinary.apiKey || process.env.CLOUDINARY_API_KEY,
      api_secret: config.cloudinary.apiSecret || process.env.CLOUDINARY_API_SECRET,
      secure: true,
    });
  }

  // Generate signed secure URL
  const secureUrl = cloudinary.url(publicId, {
    resource_type: resourceType,
    type: deliveryType,
    format: options.format,
    sign_url: true,
    secure: true,
    expires_at: expiresTimestamp,
  });

  return {
    secureUrl,
    expiresAt,
  };
}

/**
 * Safely replaces a media asset:
 * 1. Uploads replacement asset
 * 2. Deletes old asset only after new asset is successfully stored
 */
export async function replaceMediaAsset(
  oldPublicId: string,
  newBuffer: Buffer,
  options: {
    newPublicId: string;
    resourceType?: 'image' | 'raw' | 'auto';
    deliveryType?: 'upload' | 'authenticated' | 'private';
    format?: string;
  }
): Promise<CloudinaryAssetMetadata> {
  // Step 1: Upload new asset
  const newAsset = await uploadMediaBuffer(newBuffer, {
    publicId: options.newPublicId,
    resourceType: options.resourceType || 'auto',
    deliveryType: options.deliveryType || 'upload',
    overwrite: true,
    format: options.format,
  });

  // Step 2: Delete old asset only if publicId changed
  if (oldPublicId && oldPublicId !== options.newPublicId) {
    try {
      await deleteMediaAsset(oldPublicId, options.resourceType || 'auto');
    } catch (delError) {
      console.warn(`[MediaService] Warning: Failed to cleanup old asset ${oldPublicId}:`, delError);
    }
  }

  return newAsset;
}

/**
 * Deletes an asset from Cloudinary
 */
export async function deleteMediaAsset(
  publicId: string,
  resourceType: 'image' | 'raw' | 'auto' = 'image',
  deliveryType = 'upload'
): Promise<boolean> {
  try {
    const result = await cloudinary.uploader.destroy(publicId, {
      resource_type: resourceType,
      type: deliveryType,
      invalidate: true,
    });
    return result.result === 'ok' || result.result === 'not found';
  } catch (error) {
    console.error(`[MediaService] Failed to delete asset ${publicId}:`, error);
    throw error;
  }
}
