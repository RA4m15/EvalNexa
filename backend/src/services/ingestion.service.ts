import mongoose from 'mongoose';
import {
  AnswerBook,
  IAnswerBook,
  ALLOWED_PROCESSING_TRANSITIONS,
  validateProcessingStateTransition,
} from '../models/AnswerBook';
import { AnswerPage, IAnswerPage } from '../models/AnswerPage';
import { Exam } from '../models/Exam';
import { ProcessingStatus, QualityStatus } from '@evalnexa/types';
import { validateAndFinalizeAnswerBook } from './answerBooks.service';
import {
  uploadMediaBuffer,
  replaceMediaAsset,
  deleteMediaAsset,
  buildPagePublicId,
  buildDocumentPublicId,
  validateMediaFile,
  generateAuthorizedMediaUrl,
} from './media.service';
import { logAuditAction } from './audit.service';
import { emitToAll, emitToUser } from '../sockets';

export interface IngestPageInput {
  pageNumber: number;
  ocr?: {
    text?: string;
    confidence?: number | null;
    language?: string;
  };
  quality?: {
    status?: QualityStatus;
    score?: number | null;
    reviewedAt?: Date;
    reviewedBy?: string;
  };
  processingStatus?: ProcessingStatus;
  cloudinary?: {
    publicId: string;
    assetId?: string;
    resourceType?: string;
    deliveryType?: string;
    format?: string;
    bytes?: number;
    width?: number;
    height?: number;
  };
}

export interface IngestAnswerBookInput {
  examId: string;
  answerBookCode: string;
  studentCode: string;
  pageCount?: number;
  scanBatch?: string;
  processingStatus?: ProcessingStatus;
  qualityStatus?: QualityStatus;
  pages?: IngestPageInput[];
  finalize?: boolean;
}

export {
  ALLOWED_PROCESSING_TRANSITIONS,
  validateProcessingStateTransition,
};

/**
 * Idempotently ingests or updates an AnswerBook and its scanned pages.
 */
export async function ingestAnswerBookData(
  input: IngestAnswerBookInput,
  files?: Express.Multer.File[]
): Promise<{ answerBook: IAnswerBook; pages: IAnswerPage[] }> {
  // 1. Validate exam exists
  const exam = await Exam.findById(input.examId);
  if (!exam) {
    const error: any = new Error(`Exam not found with id '${input.examId}'`);
    error.status = 404;
    error.code = 'EXAM_NOT_FOUND';
    throw error;
  }

  const cleanCode = input.answerBookCode.trim().toUpperCase();
  const cleanStudentCode = input.studentCode.trim().toUpperCase();

  // 2. Find existing AnswerBook or create new (Idempotent lookup)
  let answerBook = await AnswerBook.findOne({
    examId: exam._id,
    answerBookCode: cleanCode,
  });

  const isNewAnswerBook = !answerBook;

  if (!answerBook) {
    answerBook = new AnswerBook({
      examId: exam._id,
      answerBookCode: cleanCode,
      studentCode: cleanStudentCode,
      pageCount: input.pageCount || (input.pages ? input.pages.length : (files ? files.length : 1)),
      scanBatch: input.scanBatch,
      status: 'READY',
      processingStatus: input.processingStatus || 'RECEIVED',
      qualityStatus: input.qualityStatus || 'PENDING',
    });
    await answerBook.save();
  } else {
    // Update metadata if provided
    if (input.pageCount) answerBook.pageCount = input.pageCount;
    if (input.scanBatch) answerBook.scanBatch = input.scanBatch;
    if (input.processingStatus && input.processingStatus !== answerBook.processingStatus) {
      const previousStatus = answerBook.processingStatus;
      validateProcessingStateTransition(previousStatus, input.processingStatus);
      answerBook.processingStatus = input.processingStatus;

      await logAuditAction({
        actorName: 'Scanning Service',
        actorRole: 'SCANNING_SERVICE',
        action: 'PROCESSING_STATUS_UPDATED',
        entityType: 'AnswerBook',
        entityId: answerBook._id.toString(),
        metadata: {
          previousStatus,
          newStatus: input.processingStatus,
          qualityStatus: input.qualityStatus || answerBook.qualityStatus,
          answerBookCode: answerBook.answerBookCode,
          examId: exam._id.toString(),
          timestamp: new Date().toISOString(),
        },
      });
    }
    if (input.qualityStatus) {
      answerBook.qualityStatus = input.qualityStatus;
    }
    await answerBook.save();
  }

  const answerBookId = answerBook._id.toString();
  const examId = exam._id.toString();

  // 3. Process pages
  const processedPages: IAnswerPage[] = [];

  // Map files by page number if files were provided
  // Supported file fieldnames: "page_1", "page-1", "file_1", or indexed files
  const fileMap = new Map<number, Express.Multer.File>();
  if (files && files.length > 0) {
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      // Try to extract page number from fieldname (e.g. page_1 or page-1 or page1)
      const match = file.fieldname.match(/(?:page|file)?[_\-]?(\d+)/i);
      const pageNum = match ? parseInt(match[1], 10) : i + 1;
      fileMap.set(pageNum, file);
    }
  }

  // 4. Ingest/update each page
  const pagesData = input.pages || [];

  // Determine total pages to process
  const pageNumbersToProcess = new Set<number>();
  pagesData.forEach((p) => pageNumbersToProcess.add(p.pageNumber));
  fileMap.forEach((_, pNum) => pageNumbersToProcess.add(pNum));

  if (pageNumbersToProcess.size === 0 && files && files.length > 0) {
    for (let i = 1; i <= files.length; i++) {
      pageNumbersToProcess.add(i);
    }
  }

  for (const pageNumber of Array.from(pageNumbersToProcess).sort((a, b) => a - b)) {
    const pageMeta = pagesData.find((p) => p.pageNumber === pageNumber);
    const file = fileMap.get(pageNumber);

    let cloudinaryData = pageMeta?.cloudinary;

    // If file buffer is provided, upload to Cloudinary
    if (file) {
      const validation = validateMediaFile(file);
      if (!validation.isValid) {
        const error: any = new Error(`Page ${pageNumber} validation failed: ${validation.error}`);
        error.status = 400;
        throw error;
      }

      const publicId = buildPagePublicId(examId, answerBookId, pageNumber);
      const uploaded = await uploadMediaBuffer(file.buffer, {
        publicId,
        resourceType: file.mimetype === 'application/pdf' ? 'auto' : 'image',
        deliveryType: 'upload',
        overwrite: true,
      });

      cloudinaryData = {
        publicId: uploaded.publicId,
        assetId: uploaded.assetId,
        resourceType: uploaded.resourceType,
        deliveryType: uploaded.deliveryType,
        format: uploaded.format,
        bytes: uploaded.bytes,
        width: uploaded.width,
        height: uploaded.height,
      };
    }

    if (!cloudinaryData && !file) {
      // If no file and no cloudinaryData, check if AnswerPage already exists
      const existingPage = await AnswerPage.findOne({ answerBookId: answerBook._id, pageNumber });
      if (!existingPage) {
        throw new Error(`Page ${pageNumber} is missing both image upload and Cloudinary metadata`);
      }
      cloudinaryData = existingPage.cloudinary;
    }

    // Upsert AnswerPage (Idempotent: compound unique on answerBookId + pageNumber)
    const page = await AnswerPage.findOneAndUpdate(
      { answerBookId: answerBook._id, pageNumber },
      {
        $set: {
          cloudinary: cloudinaryData,
          ...(pageMeta?.ocr ? { ocr: pageMeta.ocr } : {}),
          ...(pageMeta?.quality ? { quality: pageMeta.quality } : {}),
          processingStatus: pageMeta?.processingStatus || 'COMPLETED',
          finalized: pageMeta?.processingStatus === 'FINALIZED' || Boolean(input.finalize),
        },
      },
      { new: true, upsert: true, setDefaultsOnInsert: true }
    );

    processedPages.push(page);

    // Audit log per page
    await logAuditAction({
      actorName: 'Scanning Service',
      actorRole: 'SCANNING_SERVICE',
      action: 'PAGE_INGESTED',
      entityType: 'AnswerPage',
      entityId: page._id.toString(),
      metadata: {
        answerBookId,
        pageNumber,
        publicId: cloudinaryData?.publicId,
      },
    });

    emitToAll('page.created', {
      answerBookId,
      pageNumber: page.pageNumber,
      pageId: page._id,
    });
  }

  // Update total page count on answer book
  const totalPagesInDb = await AnswerPage.countDocuments({ answerBookId: answerBook._id });
  answerBook.pageCount = Math.max(answerBook.pageCount, totalPagesInDb);
  await answerBook.save();

  // Audit log for script ingestion
  await logAuditAction({
    actorName: 'Scanning Service',
    actorRole: 'SCANNING_SERVICE',
    action: 'SCRIPT_INGESTED',
    entityType: 'AnswerBook',
    entityId: answerBook._id.toString(),
    metadata: {
      answerBookCode: answerBook.answerBookCode,
      examId,
      pageCount: totalPagesInDb,
      isNew: isNewAnswerBook,
    },
  });

  // Check if finalization is requested or possible
  if (input.finalize || input.processingStatus === 'FINALIZED' || input.processingStatus === 'READY_FOR_EVALUATION') {
    await attemptFinalization(answerBook);
  }

  // Populate references for return
  await answerBook.populate('examId', 'title subjectCode subjectName maximumMarks');
  if (answerBook.assignedExaminerId) {
    await answerBook.populate('assignedExaminerId', 'name email');
  }

  emitToAll(isNewAnswerBook ? 'answerbook.created' : 'script.processing.updated', {
    answerBook,
  });

  return { answerBook, pages: processedPages };
}

/**
 * Validates and finalizes an answer book when scanning and quality requirements are satisfied
 */
export async function attemptFinalization(answerBook: IAnswerBook): Promise<IAnswerBook> {
  return validateAndFinalizeAnswerBook(answerBook._id.toString(), {
    name: 'Scanning Service',
    role: 'SCANNING_SERVICE',
  });
}

/**
 * Handles server-to-server processing status webhook
 */
export async function updateScriptProcessingStatus(
  answerBookId: string,
  newStatus: ProcessingStatus,
  qualityStatus?: QualityStatus,
  actor?: { id?: string; name?: string; role?: string }
): Promise<IAnswerBook> {
  const answerBook = await AnswerBook.findById(answerBookId);
  if (!answerBook) {
    const error: any = new Error('Answer book not found');
    error.status = 404;
    error.code = 'ANSWER_BOOK_NOT_FOUND';
    throw error;
  }

  // Capture previous status BEFORE the new status is assigned
  const previousStatus = answerBook.processingStatus;

  // Validate state transition through authoritative validator
  validateProcessingStateTransition(previousStatus, newStatus);

  answerBook.processingStatus = newStatus;
  if (qualityStatus) {
    answerBook.qualityStatus = qualityStatus;
  }

  if (newStatus === 'FINALIZED' || newStatus === 'READY_FOR_EVALUATION') {
    await attemptFinalization(answerBook);
  } else {
    await answerBook.save();
  }

  await logAuditAction({
    actorId: actor?.id,
    actorName: actor?.name || 'Scanning Service',
    actorRole: actor?.role || 'SCANNING_SERVICE',
    action: 'PROCESSING_STATUS_UPDATED',
    entityType: 'AnswerBook',
    entityId: answerBook._id.toString(),
    metadata: {
      previousStatus,
      newStatus,
      qualityStatus: qualityStatus || answerBook.qualityStatus,
      answerBookCode: answerBook.answerBookCode,
      examId: answerBook.examId?.toString(),
      timestamp: new Date().toISOString(),
    },
  });

  emitToAll('script.processing.updated', { answerBook });

  return answerBook;
}
