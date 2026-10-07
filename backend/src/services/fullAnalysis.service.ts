import mongoose from 'mongoose';
import { Evaluation, IFullAnalysisJob, IEvaluationQuestionMark } from '../models/Evaluation';
import { AnswerBook, IQuestionPageMapping } from '../models/AnswerBook';
import { AnswerPage } from '../models/AnswerPage';
import { QuestionPaper } from '../models/QuestionPaper';
import { geminiManager, getAiPolicyConfig, isMappingConfident, evaluateConfidenceBand } from '../config';
import { requestAISuggestionForQuestion } from './evaluations.service';
import { emitToAll, emitToUser } from '../sockets';
import { areEntityIdsEqual } from '../utils/identity';
import { logAuditAction } from './audit.service';
import { autoMapAnswerBookPages } from './pageMapping.service';

// In-memory registry to track currently active jobs and enable cancellation
const activeJobs = new Map<string, { abortController: AbortController; evaluationId: string }>();

interface StartFullAnalysisOptions {
  userId: string;
  userRole: string;
  userName?: string;
  forceRefresh?: boolean;
}

/**
 * Async concurrency runner helper (concurrency limit = 2)
 */
async function runWithConcurrency<T, R>(
  items: T[],
  concurrencyLimit: number,
  taskFn: (item: T, index: number) => Promise<R>
): Promise<R[]> {
  const results: R[] = new Array(items.length);
  let currentIndex = 0;

  async function worker(): Promise<void> {
    while (currentIndex < items.length) {
      const idx = currentIndex++;
      results[idx] = await taskFn(items[idx], idx);
    }
  }

  const workers = Array.from(
    { length: Math.min(concurrencyLimit, items.length) },
    () => worker()
  );

  await Promise.all(workers);
  return results;
}

/**
 * Identifies which answer book pages correspond to which questions.
 * Delegates to the robust dynamic page mapping pipeline in pageMapping.service.ts
 * which inspects explicit headers, OCR key domain concepts, rubric/reference answer
 * matching, continuation page sequence, and multimodal image understanding.
 */
export async function identifyQuestionPageMappings(params: {
  answerBook: any;
  questionPaper: any;
  answerPages: any[];
  forceRemap?: boolean;
}): Promise<IQuestionPageMapping[]> {
  return autoMapAnswerBookPages(params);
}

/**
 * Starts the asynchronous full answer book AI analysis job.
 * Returns immediately with { jobId, status: 'QUEUED' } and executes in background.
 */
export async function startFullAnswerBookAnalysis(
  evaluationId: string,
  options: StartFullAnalysisOptions
): Promise<{ jobId: string; status: string; message: string; evaluation: any }> {
  // 1. Authorize & Validate Evaluation
  let evaluation = await Evaluation.findById(evaluationId);
  if (!evaluation) {
    evaluation = await Evaluation.findOne({ answerBookId: evaluationId });
  }
  if (!evaluation) {
    const error: any = new Error('Evaluation not found');
    error.status = 404;
    error.code = 'EVALUATION_NOT_FOUND';
    throw error;
  }

  if (options.userRole === 'EXAMINER') {
    const examinerId =
      typeof evaluation.examinerId === 'object' &&
      evaluation.examinerId !== null &&
      '_id' in (evaluation.examinerId as any)
        ? (evaluation.examinerId as any)._id.toString()
        : evaluation.examinerId.toString();

    if (!areEntityIdsEqual(examinerId, options.userId)) {
      const error: any = new Error('Access denied: You are not assigned to this evaluation');
      error.status = 403;
      error.code = 'ACCESS_DENIED';
      throw error;
    }
  }

  // 2. Fetch AnswerBook
  const answerBook = await AnswerBook.findById(evaluation.answerBookId);
  if (!answerBook) {
    const error: any = new Error('Associated answer book not found');
    error.status = 404;
    error.code = 'ANSWER_BOOK_NOT_FOUND';
    throw error;
  }

  // 3. Question Paper Requirement (Requirement 16)
  // Must exist AND be VERIFIED
  if (!answerBook.questionPaperId) {
    const error: any = new Error(
      'No Question Paper is associated with this Answer Book. Upload and verify a question paper before running full AI analysis.'
    );
    error.status = 400;
    error.code = 'QUESTION_PAPER_REQUIRED';
    throw error;
  }

  const questionPaper = await QuestionPaper.findById(answerBook.questionPaperId);
  if (!questionPaper) {
    const error: any = new Error('Associated Question Paper document was not found.');
    error.status = 404;
    error.code = 'QUESTION_PAPER_NOT_FOUND';
    throw error;
  }

  if (
    questionPaper.extractionStatus !== 'VERIFIED' ||
    !questionPaper.verifiedQuestions ||
    questionPaper.verifiedQuestions.length === 0
  ) {
    const error: any = new Error(
      'Verify the question paper before running full AI analysis. Extracted questions must be verified by the examiner.'
    );
    error.status = 400;
    error.code = 'QUESTION_PAPER_NOT_VERIFIED';
    throw error;
  }

  const verifiedQuestions = questionPaper.verifiedQuestions;

  // 4. Duplicate Concurrency Check (Requirement 10)
  if (
    evaluation.fullAnalysisJob &&
    (evaluation.fullAnalysisJob.status === 'RUNNING' ||
      evaluation.fullAnalysisJob.status === 'QUEUED')
  ) {
    const existingJob = activeJobs.get(evaluation.fullAnalysisJob.jobId);
    if (existingJob) {
      return {
        jobId: evaluation.fullAnalysisJob.jobId,
        status: evaluation.fullAnalysisJob.status,
        message: 'Analysis already running for this answer book.',
        evaluation,
      };
    } else {
      // In-flight job was from a prior Node.js server process that terminated/restarted
      console.log(`[FullAnalysisService] Reconciling orphaned job ${evaluation.fullAnalysisJob.jobId}`);
      evaluation.fullAnalysisJob.status = 'CANCELLED';
      await evaluation.save();
    }
  }

  // 5. Initialize Job on Evaluation
  const jobId = `job_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`;
  const totalPages = answerBook.pageCount || 1;

  // Sync / initialize questionMarks for all verified questions
  for (const vq of verifiedQuestions) {
    const qNum = vq.questionNumber;
    const existingIdx = evaluation.questionMarks.findIndex((qm) => qm.questionNumber === qNum);
    if (existingIdx >= 0) {
      evaluation.questionMarks[existingIdx].aiStatus = 'QUEUED';
      evaluation.questionMarks[existingIdx].aiError = undefined;
      evaluation.questionMarks[existingIdx].questionLabel = vq.questionLabel;
      evaluation.questionMarks[existingIdx].section = vq.section;
      evaluation.questionMarks[existingIdx].subquestion = vq.subquestion;
    } else {
      evaluation.questionMarks.push({
        questionNumber: qNum,
        questionLabel: vq.questionLabel,
        section: vq.section,
        subquestion: vq.subquestion,
        marks: 0,
        status: 'NOT_STARTED',
        aiStatus: 'QUEUED',
        examinerReviewed: false,
      });
    }
  }

  const jobData: IFullAnalysisJob = {
    jobId,
    status: 'QUEUED',
    questionPaperId: questionPaper._id,
    totalQuestions: verifiedQuestions.length,
    completedQuestions: 0,
    failedQuestions: 0,
    needsReviewQuestions: 0,
    totalPages,
    analyzedPages: 0,
    currentStep: 'Job queued for processing',
    startedAt: new Date(),
  };

  evaluation.fullAnalysisJob = jobData;
  await evaluation.save();

  // Create abort controller for cancellation support
  const abortController = new AbortController();
  activeJobs.set(jobId, { abortController, evaluationId: evaluation._id.toString() });

  // 6. Emit Socket.IO event immediately
  emitToAll('ai.full-analysis.started', {
    evaluationId: evaluation._id.toString(),
    answerBookId: answerBook._id.toString(),
    job: jobData,
  });

  // Audit log
  await logAuditAction({
    actorId: options.userId,
    actorName: options.userName || 'Assigned Examiner',
    actorRole: options.userRole,
    action: 'AI_FULL_ANALYSIS_STARTED',
    entityType: 'Evaluation',
    entityId: evaluation._id.toString(),
    metadata: {
      jobId,
      answerBookId: answerBook._id.toString(),
      questionPaperId: questionPaper._id.toString(),
      totalQuestions: verifiedQuestions.length,
    },
  });

  // 7. Launch background execution asynchronously (never blocking HTTP response)
  setImmediate(() => {
    executeFullAnalysisBackground({
      evaluationId: evaluation._id.toString(),
      jobId,
      answerBookId: answerBook._id.toString(),
      questionPaperId: questionPaper._id.toString(),
      options,
      abortController,
    }).catch((bgErr) => {
      console.error(`[FullAnalysisService] Background job ${jobId} uncaught error:`, bgErr);
    });
  });

  return {
    jobId,
    status: 'QUEUED',
    message: 'Full answer book AI analysis queued successfully.',
    evaluation,
  };
}

/**
 * Background execution pipeline for full answer book analysis
 */
export async function executeFullAnalysisBackground(params: {
  evaluationId: string;
  jobId: string;
  answerBookId: string;
  questionPaperId: string;
  options: StartFullAnalysisOptions;
  abortController: AbortController;
}): Promise<void> {
  const { evaluationId, jobId, answerBookId, questionPaperId, options, abortController } = params;

  try {
    const evaluation = await Evaluation.findById(evaluationId);
    if (!evaluation || !evaluation.fullAnalysisJob) return;

    const answerBook = await AnswerBook.findById(answerBookId);
    const questionPaper = await QuestionPaper.findById(questionPaperId);

    if (!answerBook || !questionPaper) {
      throw new Error('Required documents missing for background execution');
    }

    // Step 1: Update Job to RUNNING
    evaluation.fullAnalysisJob.status = 'RUNNING';
    evaluation.fullAnalysisJob.currentStep = 'Analyzing answer script pages & identifying question mappings...';
    await evaluation.save();

    emitToAll('ai.full-analysis.progress', {
      evaluationId,
      answerBookId,
      job: evaluation.fullAnalysisJob,
    });

    if (abortController.signal.aborted) {
      evaluation.fullAnalysisJob.status = 'CANCELLED';
      await evaluation.save();
      activeJobs.delete(jobId);
      return;
    }

    // Step 2: Fetch all AnswerPage documents
    const answerPages = await AnswerPage.find({ answerBookId: answerBook._id }).sort({
      pageNumber: 1,
    });

    // Step 3: Identify Question → Page Mappings
    await identifyQuestionPageMappings({
      answerBook,
      questionPaper,
      answerPages,
    });

    evaluation.fullAnalysisJob.analyzedPages = answerPages.length;
    evaluation.fullAnalysisJob.currentStep = 'Page identification complete. Beginning question evaluations...';
    await evaluation.save();

    emitToAll('ai.full-analysis.progress', {
      evaluationId,
      answerBookId,
      job: evaluation.fullAnalysisJob,
    });

    if (abortController.signal.aborted) {
      evaluation.fullAnalysisJob.status = 'CANCELLED';
      await evaluation.save();
      activeJobs.delete(jobId);
      return;
    }

    const verifiedQuestions = questionPaper.verifiedQuestions || [];

    const policy = getAiPolicyConfig();

    // Step 4: Evaluate Each Question with Controlled Concurrency
    await runWithConcurrency(verifiedQuestions, policy.concurrencyLimit, async (vq, idx) => {
      if (abortController.signal.aborted) return;

      const qNum = vq.questionNumber;

      // Update question status to ANALYZING
      await Evaluation.updateOne(
        { _id: evaluation._id, 'questionMarks.questionNumber': qNum },
        {
          $set: {
            'questionMarks.$.aiStatus': 'ANALYZING',
            'fullAnalysisJob.currentStep': `Evaluating Question ${vq.questionLabel || qNum}...`,
            'fullAnalysisJob.currentQuestionNumber': qNum,
          },
        }
      );

      emitToAll('evaluation.ai.updated', {
        evaluationId,
        answerBookId,
        questionNumber: qNum,
        aiStatus: 'ANALYZING',
      });

      // Verify mapped pages exist for this question (Case B: Unresolved mapping)
      const currentBook = await AnswerBook.findById(answerBookId);
      const qMapping = currentBook?.questionPageMapping?.find(
        (m: IQuestionPageMapping) => m.questionNumber === qNum
      );
      const hasPages = Boolean(qMapping?.pages && qMapping.pages.length > 0);

      if (!hasPages) {
        const unresolvedReason =
          qMapping?.reason ||
          `No explicit answer pages were detected for Question ${vq.questionLabel || qNum}. Examiner review and page assignment required.`;

        await Evaluation.updateOne(
          { _id: evaluation._id, 'questionMarks.questionNumber': qNum },
          {
            $set: {
              'questionMarks.$.aiStatus': 'NEEDS_REVIEW',
              'questionMarks.$.aiError': unresolvedReason,
              'questionMarks.$.aiAnalysis': null,
              'questionMarks.$.questionLabel': vq.questionLabel,
              'questionMarks.$.section': vq.section,
              'questionMarks.$.subquestion': vq.subquestion,
            },
            $inc: {
              'fullAnalysisJob.completedQuestions': 1,
              'fullAnalysisJob.needsReviewQuestions': 1,
            },
          }
        );

        emitToAll('evaluation.ai.updated', {
          evaluationId,
          answerBookId,
          questionNumber: qNum,
          aiStatus: 'NEEDS_REVIEW',
          aiError: unresolvedReason,
          aiAnalysis: null,
        });
        return;
      }

      try {
        // Run AI evaluation using canonical EvaluationAssistantService flow
        const result = await requestAISuggestionForQuestion(evaluationId, qNum, {
          userRole: options.userRole,
          userId: options.userId,
          userName: options.userName,
          answerBookId: answerBook._id.toString(),
          questionPaperId: questionPaper._id.toString(),
          questionId: (vq as any)._id?.toString(),
          forceRefresh: true,
        });

        const isNeedsReview =
          result.aiAnalysis?.needsHumanReview ||
          (result.aiAnalysis?.confidence !== undefined &&
            result.aiAnalysis.confidence < policy.aiGradingConfidence.medium);

        const newStatus = isNeedsReview ? 'NEEDS_REVIEW' : 'COMPLETED';

        // Update database with completed status
        await Evaluation.updateOne(
          { _id: evaluation._id, 'questionMarks.questionNumber': qNum },
          {
            $set: {
              'questionMarks.$.aiStatus': newStatus,
              'questionMarks.$.aiError': null,
              'questionMarks.$.questionLabel': vq.questionLabel,
              'questionMarks.$.section': vq.section,
              'questionMarks.$.subquestion': vq.subquestion,
            },
            $inc: {
              'fullAnalysisJob.completedQuestions': 1,
              ...(isNeedsReview ? { 'fullAnalysisJob.needsReviewQuestions': 1 } : {}),
            },
          }
        );

        emitToAll('evaluation.ai.updated', {
          evaluationId,
          answerBookId,
          questionNumber: qNum,
          aiStatus: newStatus,
          aiAnalysis: result.aiAnalysis,
        });
      } catch (qErr: any) {
        console.error(`[FullAnalysisService] Error evaluating Q${qNum}:`, qErr.message);

        // Individual question failure must NOT fail the complete script! (Requirement 8 & 20)
        await Evaluation.updateOne(
          { _id: evaluation._id, 'questionMarks.questionNumber': qNum },
          {
            $set: {
              'questionMarks.$.aiStatus': 'FAILED',
              'questionMarks.$.aiError': qErr.message || 'Evaluation failed for this question',
            },
            $inc: {
              'fullAnalysisJob.failedQuestions': 1,
            },
          }
        );

        emitToAll('evaluation.ai.updated', {
          evaluationId,
          answerBookId,
          questionNumber: qNum,
          aiStatus: 'FAILED',
          aiError: qErr.message,
        });
      }

      // Refresh in-memory evaluation job status and emit progress
      const currentEval = await Evaluation.findById(evaluationId);
      if (currentEval?.fullAnalysisJob) {
        emitToAll('ai.full-analysis.progress', {
          evaluationId,
          answerBookId,
          job: currentEval.fullAnalysisJob,
        });
      }
    });

    // Step 5: Finalize Job State
    const finalEval = await Evaluation.findById(evaluationId);
    if (!finalEval || !finalEval.fullAnalysisJob) return;

    const failedCount = finalEval.fullAnalysisJob.failedQuestions || 0;
    const needsReviewCount = finalEval.fullAnalysisJob.needsReviewQuestions || 0;
    const finalStatus =
      failedCount > 0
        ? 'COMPLETED_WITH_ERRORS'
        : needsReviewCount > 0
          ? 'COMPLETED_WITH_REVIEW'
          : 'COMPLETED';

    finalEval.fullAnalysisJob.status = finalStatus;
    finalEval.fullAnalysisJob.completedAt = new Date();
    finalEval.fullAnalysisJob.currentStep =
      finalStatus === 'COMPLETED'
        ? 'All questions evaluated successfully.'
        : finalStatus === 'COMPLETED_WITH_REVIEW'
          ? `Analysis complete. ${needsReviewCount} question(s) flagged for examiner review.`
          : `Completed with ${failedCount} question(s) requiring retry.`;

    await finalEval.save();

    emitToAll('ai.full-analysis.completed', {
      evaluationId,
      answerBookId,
      job: finalEval.fullAnalysisJob,
    });

    await logAuditAction({
      actorId: options.userId,
      actorName: options.userName || 'Assigned Examiner',
      actorRole: options.userRole,
      action: 'AI_FULL_ANALYSIS_COMPLETED',
      entityType: 'Evaluation',
      entityId: evaluationId,
      metadata: {
        jobId,
        status: finalStatus,
        completed: finalEval.fullAnalysisJob.completedQuestions,
        failed: failedCount,
        needsReview: finalEval.fullAnalysisJob.needsReviewQuestions,
      },
    });
  } catch (fatalErr: any) {
    console.error(`[FullAnalysisService] Fatal error in job ${jobId}:`, fatalErr);

    try {
      await Evaluation.updateOne(
        { _id: evaluationId },
        {
          $set: {
            'fullAnalysisJob.status': 'FAILED',
            'fullAnalysisJob.error': fatalErr.message || 'Fatal background analysis error',
            'fullAnalysisJob.completedAt': new Date(),
            'fullAnalysisJob.currentStep': 'Analysis job failed.',
          },
        }
      );

      emitToAll('ai.full-analysis.completed', {
        evaluationId,
        answerBookId,
        job: { status: 'FAILED', error: fatalErr.message },
      });
    } catch {
      // ignore secondary save error
    }
  } finally {
    activeJobs.delete(jobId);
  }
}

/**
 * Retries analysis for a single question that previously failed or needs re-checking
 */
export async function retryQuestionAnalysis(
  evaluationId: string,
  questionNumber: number,
  options: StartFullAnalysisOptions
): Promise<{ success: boolean; data: any }> {
  const evaluation = await Evaluation.findById(evaluationId);
  if (!evaluation) {
    const error: any = new Error('Evaluation not found');
    error.status = 404;
    error.code = 'EVALUATION_NOT_FOUND';
    throw error;
  }

  const answerBook = await AnswerBook.findById(evaluation.answerBookId);
  if (!answerBook) {
    const error: any = new Error('Answer book not found');
    error.status = 404;
    error.code = 'ANSWER_BOOK_NOT_FOUND';
    throw error;
  }

  // Set status to ANALYZING
  await Evaluation.updateOne(
    { _id: evaluation._id, 'questionMarks.questionNumber': questionNumber },
    {
      $set: {
        'questionMarks.$.aiStatus': 'ANALYZING',
        'questionMarks.$.aiError': null,
      },
    }
  );

  emitToAll('evaluation.ai.updated', {
    evaluationId: evaluation._id.toString(),
    answerBookId: answerBook._id.toString(),
    questionNumber,
    aiStatus: 'ANALYZING',
  });

  try {
    const result = await requestAISuggestionForQuestion(evaluation._id.toString(), questionNumber, {
      userRole: options.userRole,
      userId: options.userId,
      userName: options.userName,
      answerBookId: answerBook._id.toString(),
      questionPaperId: answerBook.questionPaperId?.toString(),
      forceRefresh: true,
    });

    const isNeedsReview =
      result.aiAnalysis?.needsHumanReview ||
      (result.aiAnalysis?.confidence !== undefined && result.aiAnalysis.confidence < 0.75);

    const newStatus = isNeedsReview ? 'NEEDS_REVIEW' : 'COMPLETED';

    // Check if previously was FAILED and decrement failed count
    const qm = evaluation.questionMarks.find((q) => q.questionNumber === questionNumber);
    const wasFailed = qm?.aiStatus === 'FAILED';

    const incUpdate: any = {};
    if (wasFailed && evaluation.fullAnalysisJob) {
      if ((evaluation.fullAnalysisJob.failedQuestions || 0) > 0) {
        incUpdate['fullAnalysisJob.failedQuestions'] = -1;
      }
      incUpdate['fullAnalysisJob.completedQuestions'] = 1;
    }
    if (isNeedsReview) {
      incUpdate['fullAnalysisJob.needsReviewQuestions'] = 1;
    }

    const updateDoc: any = {
      $set: {
        'questionMarks.$.aiStatus': newStatus,
        'questionMarks.$.aiError': null,
      },
    };
    if (Object.keys(incUpdate).length > 0) {
      updateDoc.$inc = incUpdate;
    }

    await Evaluation.updateOne(
      { _id: evaluation._id, 'questionMarks.questionNumber': questionNumber },
      updateDoc
    );

    // Recheck job overall status
    const refreshed = await Evaluation.findById(evaluation._id);
    if (refreshed?.fullAnalysisJob) {
      if (
        refreshed.fullAnalysisJob.status === 'COMPLETED_WITH_ERRORS' &&
        (refreshed.fullAnalysisJob.failedQuestions || 0) === 0
      ) {
        refreshed.fullAnalysisJob.status = 'COMPLETED';
        await refreshed.save();
      }
    }

    emitToAll('evaluation.ai.updated', {
      evaluationId: evaluation._id.toString(),
      answerBookId: answerBook._id.toString(),
      questionNumber,
      aiStatus: newStatus,
      aiAnalysis: result.aiAnalysis,
    });

    return { success: true, data: result.aiAnalysis };
  } catch (err: any) {
    await Evaluation.updateOne(
      { _id: evaluation._id, 'questionMarks.questionNumber': questionNumber },
      {
        $set: {
          'questionMarks.$.aiStatus': 'FAILED',
          'questionMarks.$.aiError': err.message || 'Retry evaluation failed',
        },
      }
    );

    emitToAll('evaluation.ai.updated', {
      evaluationId: evaluation._id.toString(),
      answerBookId: answerBook._id.toString(),
      questionNumber,
      aiStatus: 'FAILED',
      aiError: err.message,
    });

    throw err;
  }
}

/**
 * Cancels a running analysis job
 */
export async function cancelFullAnalysis(
  evaluationId: string,
  options: { userId: string; userRole: string }
): Promise<{ success: boolean; message: string }> {
  const evaluation = await Evaluation.findById(evaluationId);
  if (!evaluation || !evaluation.fullAnalysisJob) {
    return { success: true, message: 'No active analysis job found to cancel' };
  }

  const active = activeJobs.get(evaluation.fullAnalysisJob.jobId);
  if (active) {
    active.abortController.abort();
    activeJobs.delete(evaluation.fullAnalysisJob.jobId);
  }

  evaluation.fullAnalysisJob.status = 'CANCELLED';
  evaluation.fullAnalysisJob.currentStep = 'Analysis cancelled by examiner.';
  await evaluation.save();

  emitToAll('ai.full-analysis.completed', {
    evaluationId: evaluation._id.toString(),
    answerBookId: evaluation.answerBookId.toString(),
    job: evaluation.fullAnalysisJob,
  });

  return { success: true, message: 'Analysis job cancelled successfully' };
}

/**
 * Returns current status and progress of full analysis job
 */
export async function getFullAnalysisStatus(evaluationId: string): Promise<any> {
  let evaluation = await Evaluation.findById(evaluationId);
  if (!evaluation) {
    evaluation = await Evaluation.findOne({ answerBookId: evaluationId });
  }
  if (!evaluation) {
    const error: any = new Error('Evaluation not found');
    error.status = 404;
    error.code = 'EVALUATION_NOT_FOUND';
    throw error;
  }

  return {
    job: evaluation.fullAnalysisJob || null,
    questionMarks: evaluation.questionMarks,
  };
}

/**
 * Reconciles any jobs interrupted by a server restart or crash.
 * Called automatically during server startup.
 */
export async function recoverInterruptedJobs(): Promise<void> {
  try {
    const interruptedEvaluations = await Evaluation.find({
      'fullAnalysisJob.status': { $in: ['RUNNING', 'QUEUED'] },
    });

    if (interruptedEvaluations.length === 0) return;

    console.log(
      `[FullAnalysisService] Found ${interruptedEvaluations.length} interrupted full-analysis job(s). Recovering...`
    );

    for (const ev of interruptedEvaluations) {
      if (!ev.fullAnalysisJob) continue;

      let completedCount = 0;
      let failedCount = 0;
      let needsReviewCount = 0;

      ev.questionMarks.forEach((qm) => {
        if (qm.aiStatus === 'COMPLETED') {
          completedCount++;
        } else if (qm.aiStatus === 'NEEDS_REVIEW') {
          completedCount++;
          needsReviewCount++;
        } else if (qm.aiStatus === 'ANALYZING' || qm.aiStatus === 'QUEUED') {
          qm.aiStatus = 'FAILED';
          qm.aiError =
            'Analysis interrupted by server restart. Completed questions were preserved. Click Retry to re-evaluate.';
          failedCount++;
        } else if (qm.aiStatus === 'FAILED') {
          failedCount++;
        }
      });

      ev.fullAnalysisJob.completedQuestions = completedCount;
      ev.fullAnalysisJob.failedQuestions = failedCount;
      ev.fullAnalysisJob.needsReviewQuestions = needsReviewCount;
      ev.fullAnalysisJob.status = completedCount > 0 ? 'COMPLETED_WITH_ERRORS' : 'FAILED';
      ev.fullAnalysisJob.currentStep =
        'Job interrupted by server restart. Completed results preserved.';
      ev.fullAnalysisJob.completedAt = new Date();

      await ev.save();
      console.log(
        `[FullAnalysisService] Reconciled interrupted job ${ev.fullAnalysisJob.jobId} for evaluation ${ev._id}`
      );
    }
  } catch (err: any) {
    console.error('[FullAnalysisService] Error in recoverInterruptedJobs:', err.message);
  }
}

