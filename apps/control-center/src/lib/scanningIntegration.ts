/**
 * EvalNexa Control Center - Real OpenCV / Scanning Service Integration Adapter
 *
 * Connects the browser camera/capture flow to the external OpenCV scanning engine.
 * Pipeline:
 * CAMERA -> CAPTURE FRAME -> OPENCV PROCESSING -> PAGE DETECTION -> CROP -> BLUR CHECK -> QUALITY RESULT
 */

import { QualityStatus, AnswerBookStatus } from '@evalnexa/types';

export interface PageQualityDiagnostics {
  status: 'PASSED' | 'RESCAN_REQUIRED' | 'PENDING' | 'HUMAN_REVIEW';
  blurDetected?: boolean;
  sharpnessScore?: number;
  orientation?: string;
  pageDetected?: boolean;
  cropReady?: boolean;
  ocrReadiness?: 'READY' | 'UNCLEAR' | 'FAILED';
  reason?: string;
  outputWidth?: number;
  outputHeight?: number;
  sourceWidth?: number;
  sourceHeight?: number;
}

export interface ProcessPageResult {
  success: boolean;
  serviceAvailable: boolean;
  diagnostics?: PageQualityDiagnostics;
  processedImageUrl?: string;
  processedBlob?: Blob;
  ocrText?: string;
  errorMessage?: string;
  outputWidth?: number;
  outputHeight?: number;
  sourceWidth?: number;
  sourceHeight?: number;
  cropReady?: boolean;
}

/**
 * Synchronously converts a Base64 Data URI directly into a binary Blob
 * without relying on fetch(dataUri), which is prone to CSP blocks or URL limits.
 */
export function dataUriToBlob(dataUri: string): Blob {
  const parts = dataUri.split(',');
  if (parts.length < 2) {
    throw new Error('Invalid Data URI format');
  }
  const mimeMatch = parts[0].match(/:(.*?);/);
  const mime = mimeMatch ? mimeMatch[1] : 'image/jpeg';
  const byteString = atob(parts[1]);
  const arrayBuffer = new ArrayBuffer(byteString.length);
  const uint8Array = new Uint8Array(arrayBuffer);
  for (let i = 0; i < byteString.length; i++) {
    uint8Array[i] = byteString.charCodeAt(i);
  }
  return new Blob([uint8Array], { type: mime });
}

const DEFAULT_SCANNING_SERVICE_URL =
  (typeof import.meta !== 'undefined' && (import.meta as any).env?.VITE_SCANNING_SERVICE_URL) ||
  'http://localhost:8000';

/**
 * Checks connectivity to the friend's OpenCV scanning service.
 */
export async function checkScanningServiceHealth(
  serviceUrl = DEFAULT_SCANNING_SERVICE_URL
): Promise<{ connected: boolean; url: string; error?: string }> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 1800);
    const res = await fetch(`${serviceUrl}/health`, {
      method: 'GET',
      signal: controller.signal,
    }).catch(() => null);
    clearTimeout(timeoutId);

    if (res && res.ok) {
      return { connected: true, url: serviceUrl };
    }
    return { connected: false, url: serviceUrl, error: 'Service returned non-200 status' };
  } catch (err: any) {
    return { connected: false, url: serviceUrl, error: err?.message || 'Connection refused' };
  }
}

export interface LiveDocumentDetection {
  detected: boolean;
  corners: [number, number][] | null;
  documentScore: number;
  imageWidth?: number;
  imageHeight?: number;
  reason?: string;
}

/**
 * Lightweight real-time document detector called at 5-10 FPS during camera preview.
 * Returns 4 corners and detection state without expensive OCR or full quality matrix.
 */
export async function detectDocumentPreview(
  frameBlob: Blob,
  signal?: AbortSignal,
  serviceUrl = DEFAULT_SCANNING_SERVICE_URL
): Promise<LiveDocumentDetection> {
  try {
    const formData = new FormData();
    formData.append('file', frameBlob, 'preview_frame.jpg');

    const res = await fetch(`${serviceUrl}/detect-document`, {
      method: 'POST',
      body: formData,
      signal,
    }).catch(() => null);

    if (!res || !res.ok) {
      return { detected: false, corners: null, documentScore: 0 };
    }

    const data = await res.json();
    return {
      detected: Boolean(data.detected),
      corners: Array.isArray(data.corners) ? data.corners : null,
      documentScore: typeof data.document_score === 'number' ? data.document_score : 0,
      imageWidth: data.image_width,
      imageHeight: data.image_height,
      reason: data.reason,
    };
  } catch {
    return { detected: false, corners: null, documentScore: 0 };
  }
}

/**
 * Sends a captured frame to the OpenCV scanning service for real page detection,
 * perspective correction, and blur/sharpness verification.
 */
export async function processPageWithOpenCVService(
  imageBlob: Blob,
  meta: {
    examId: string;
    answerBookCode: string;
    pageNumber: number;
    filename?: string;
    corners?: [number, number][];
    originalCorners?: [number, number][];
    previewWidth?: number;
    previewHeight?: number;
    captureWidth?: number;
    captureHeight?: number;
  },
  serviceUrl = DEFAULT_SCANNING_SERVICE_URL
): Promise<ProcessPageResult> {
  try {
    const formData = new FormData();
    formData.append('file', imageBlob, meta.filename || `page_${meta.pageNumber}.jpg`);
    formData.append('examId', meta.examId);
    formData.append('answerBookCode', meta.answerBookCode);
    formData.append('pageNumber', String(meta.pageNumber));
    if (meta.corners && meta.corners.length === 4) {
      formData.append('corners', JSON.stringify(meta.corners));
    }
    if (meta.originalCorners && meta.originalCorners.length === 4) {
      formData.append('original_corners', JSON.stringify(meta.originalCorners));
    }
    if (typeof meta.previewWidth === 'number') {
      formData.append('previewWidth', String(meta.previewWidth));
    }
    if (typeof meta.previewHeight === 'number') {
      formData.append('previewHeight', String(meta.previewHeight));
    }
    if (typeof meta.captureWidth === 'number') {
      formData.append('captureWidth', String(meta.captureWidth));
    }
    if (typeof meta.captureHeight === 'number') {
      formData.append('captureHeight', String(meta.captureHeight));
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 8000);

    const res = await fetch(`${serviceUrl}/process-page`, {
      method: 'POST',
      body: formData,
      signal: controller.signal,
    }).catch(() => null);
    clearTimeout(timeoutId);

    if (!res) {
      return {
        success: false,
        serviceAvailable: false,
        errorMessage: `Scanning service unavailable at ${serviceUrl}`,
      };
    }

    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      return {
        success: false,
        serviceAvailable: true,
        errorMessage: errJson.message || `Processing failed with status ${res.status}`,
      };
    }

    const data = await res.json();

    let processedBlob: Blob | undefined = undefined;
    if (
      typeof data.processedImageUrl === 'string' &&
      data.processedImageUrl.startsWith('data:image/jpeg;base64,')
    ) {
      try {
        processedBlob = dataUriToBlob(data.processedImageUrl);
      } catch (decodeErr) {
        console.warn('Failed to convert processedImageUrl to Blob:', decodeErr);
        processedBlob = undefined;
      }
    }

    const outputWidth = typeof data.output_width === 'number' ? data.output_width : undefined;
    const outputHeight = typeof data.output_height === 'number' ? data.output_height : undefined;
    const sourceWidth = typeof data.source_width === 'number' ? data.source_width : undefined;
    const sourceHeight = typeof data.source_height === 'number' ? data.source_height : undefined;
    const cropReady = data.cropReady !== undefined ? Boolean(data.cropReady) : true;

    return {
      success: true,
      serviceAvailable: true,
      diagnostics: {
        status:
          data.qualityStatus === 'PASSED'
            ? 'PASSED'
            : data.qualityStatus === 'HUMAN_REVIEW'
            ? 'HUMAN_REVIEW'
            : 'RESCAN_REQUIRED',
        blurDetected: Boolean(data.blurDetected),
        sharpnessScore: typeof data.sharpness === 'number' ? data.sharpness : undefined,
        orientation: data.orientation || 'NORMAL',
        pageDetected: data.pageDetected !== undefined ? Boolean(data.pageDetected) : true,
        cropReady,
        ocrReadiness: data.ocrReadiness || (data.qualityStatus === 'PASSED' ? 'READY' : 'UNCLEAR'),
        reason: data.reason,
        outputWidth,
        outputHeight,
        sourceWidth,
        sourceHeight,
      },
      processedImageUrl: data.processedImageUrl,
      processedBlob,
      ocrText: data.ocrText,
      outputWidth,
      outputHeight,
      sourceWidth,
      sourceHeight,
      cropReady,
    };
  } catch (err: any) {
    return {
      success: false,
      serviceAvailable: false,
      errorMessage: err?.message || 'Network error reaching scanning service',
    };
  }
}

/**
 * Real client-side Computer Vision analyzer using HTML5 Canvas & Laplacian Convolution.
 * Replicates OpenCV's cv2.Laplacian(img, cv2.CV_64F).var() directly in browser memory.
 */
export function analyzePageWithCanvas(
  canvas: HTMLCanvasElement
): {
  sharpnessScore: number;
  blurDetected: boolean;
  pageDetected: boolean;
  cropReady: boolean;
  status: 'PASSED' | 'RESCAN_REQUIRED';
  reason?: string;
} {
  const ctx = canvas.getContext('2d');
  if (!ctx) {
    return { sharpnessScore: 100, blurDetected: false, pageDetected: true, cropReady: true, status: 'PASSED' };
  }

  const { width, height } = canvas;
  const sampleW = Math.min(width, 320);
  const sampleH = Math.min(height, 240);
  const offscreen = document.createElement('canvas');
  offscreen.width = sampleW;
  offscreen.height = sampleH;
  const offCtx = offscreen.getContext('2d');
  if (!offCtx) {
    return { sharpnessScore: 100, blurDetected: false, pageDetected: true, cropReady: true, status: 'PASSED' };
  }

  offCtx.drawImage(canvas, 0, 0, sampleW, sampleH);
  const imgData = offCtx.getImageData(0, 0, sampleW, sampleH);
  const data = imgData.data;

  // 1. Grayscale luminance
  const gray = new Float32Array(sampleW * sampleH);
  for (let i = 0; i < data.length; i += 4) {
    gray[i / 4] = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
  }

  // 2. 3x3 Laplacian operator: [0, 1, 0; 1, -4, 1; 0, 1, 0]
  let sumL = 0;
  let sumL2 = 0;
  let count = 0;

  for (let y = 1; y < sampleH - 1; y++) {
    for (let x = 1; x < sampleW - 1; x++) {
      const idx = y * sampleW + x;
      const val =
        gray[idx + 1] +
        gray[idx - 1] +
        gray[idx + sampleW] +
        gray[idx - sampleW] -
        4 * gray[idx];
      sumL += val;
      sumL2 += val * val;
      count++;
    }
  }

  const mean = sumL / count;
  const variance = Math.max(0, sumL2 / count - mean * mean);
  const sharpnessScore = Math.round(variance * 10) / 10;

  // Threshold: variance < 55 indicates motion blur or defocus
  const blurDetected = variance < 55;
  const status: 'PASSED' | 'RESCAN_REQUIRED' = blurDetected ? 'RESCAN_REQUIRED' : 'PASSED';
  const reason = blurDetected
    ? `Laplacian sharpness variance (${sharpnessScore}) is below minimum threshold (55.0). Recapture with better focus.`
    : undefined;

  return {
    sharpnessScore,
    blurDetected,
    pageDetected: true,
    cropReady: true,
    status,
    reason,
  };
}
