import { Evaluation } from '../models/Evaluation';
import { AnswerBook } from '../models/AnswerBook';
import { Moderation } from '../models/Moderation';
import { User } from '../models/User';
import { Exam } from '../models/Exam';
import { Question } from '../models/Question';
import { AnswerPage } from '../models/AnswerPage';
import { validateStateTransition } from './answerBooks.service';
import { logAuditAction } from './audit.service';
import { emitToAll } from '../sockets';
import {
  fetchAuthoritativeQuestions,
  validateQuestionMarksList,
} from './evaluations.service';

export async function fetchModerationQueue(status?: string) {
  const filter: Record<string, unknown> = {};
  if (status && status !== 'ALL') {
    filter.status = status;
  } else if (!status) {
    filter.status = { $in: ['SUBMITTED', 'UNDER_REVIEW'] };
  } else if (status === 'ALL') {
    filter.status = { $in: ['SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'RETURNED'] };
  }

  return Evaluation.find(filter)
    .populate({
      path: 'answerBookId',
      populate: { path: 'examId', select: 'title subjectCode subjectName maximumMarks' },
    })
    .populate('examinerId', 'name email')
    .sort({ submittedAt: -1 });
}

export async function fetchModerationById(id: string) {
  let evaluation = await Evaluation.findById(id)
    .populate({
      path: 'answerBookId',
      populate: { path: 'examId', select: 'title subjectCode subjectName academicSession maximumMarks totalQuestions' },
    })
    .populate('examinerId', 'name email');

  // If not found by evaluation ID, check if it's a moderation ID
  if (!evaluation) {
    const mod = await Moderation.findById(id);
    if (mod) {
      evaluation = await Evaluation.findById(mod.evaluationId)
        .populate({
          path: 'answerBookId',
          populate: { path: 'examId', select: 'title subjectCode subjectName academicSession maximumMarks totalQuestions' },
        })
        .populate('examinerId', 'name email');
    }
  }

  if (!evaluation) {
    const error: any = new Error('Evaluation not found');
    error.status = 404;
    error.code = 'EVALUATION_NOT_FOUND';
    throw error;
  }

  const moderationHistory = await Moderation.find({ evaluationId: evaluation._id })
    .populate('moderatorId', 'name email')
    .sort({ createdAt: -1 });

  // Check if a second evaluation exists for the same answer book
  const answerBookId = (evaluation.answerBookId as any)?._id || evaluation.answerBookId;
  const secondEvaluation = await Evaluation.findOne({
    answerBookId,
    _id: { $ne: evaluation._id },
    status: { $in: ['SUBMITTED', 'APPROVED', 'UNDER_REVIEW'] },
  }).populate('examinerId', 'name email');

  return { evaluation, moderationHistory, secondEvaluation };
}

export async function fetchModeratorHistory(moderatorId?: string) {
  const filter: Record<string, unknown> = {};
  if (moderatorId) {
    filter.moderatorId = moderatorId;
  }
  return Moderation.find(filter)
    .populate({
      path: 'evaluationId',
      populate: [
        {
          path: 'answerBookId',
          populate: { path: 'examId', select: 'title subjectCode subjectName maximumMarks' },
        },
        {
          path: 'examinerId',
          select: 'name email',
        },
      ],
    })
    .populate('moderatorId', 'name email')
    .sort({ createdAt: -1 });
}

export async function approveEvaluationByModerator(id: string, moderatorId: string) {
  let evaluation = await Evaluation.findById(id);
  if (!evaluation) {
    const mod = await Moderation.findById(id);
    if (mod) evaluation = await Evaluation.findById(mod.evaluationId);
  }

  if (!evaluation) {
    const error: any = new Error('Evaluation not found');
    error.status = 404;
    error.code = 'EVALUATION_NOT_FOUND';
    throw error;
  }

  if (!['SUBMITTED', 'UNDER_REVIEW'].includes(evaluation.status)) {
    const error: any = new Error(
      `Cannot approve evaluation with status: ${evaluation.status}. Must be SUBMITTED or UNDER_REVIEW.`
    );
    error.status = 400;
    error.code = 'INVALID_STATUS';
    throw error;
  }

  const answerBook = await AnswerBook.findById(evaluation.answerBookId);
  if (!answerBook) {
    const error: any = new Error('Associated answer book not found');
    error.status = 404;
    error.code = 'ANSWER_BOOK_NOT_FOUND';
    throw error;
  }

  // Reject approval if script requires rescan
  if (answerBook.qualityStatus === 'RESCAN_REQUIRED') {
    const error: any = new Error(
      `Cannot approve evaluation: Answer book '${answerBook.answerBookCode}' is marked as RESCAN_REQUIRED.`
    );
    error.status = 400;
    error.code = 'RESCAN_REQUIRED';
    throw error;
  }

  // Authoritatively validate question marks against examination specification
  const examId =
    typeof answerBook.examId === 'object' && answerBook.examId !== null && '_id' in (answerBook.examId as any)
      ? (answerBook.examId as any)._id
      : answerBook.examId;

  const authoritativeQuestions = await fetchAuthoritativeQuestions(examId);

  if (!evaluation.questionMarks || evaluation.questionMarks.length === 0) {
    const error: any = new Error('Cannot approve evaluation: Evaluation has no question marks recorded.');
    error.status = 400;
    error.code = 'NO_QUESTION_MARKS';
    throw error;
  }

  const { validatedList, computedTotal } = validateQuestionMarksList(
    evaluation.questionMarks as any,
    authoritativeQuestions,
    true // isSubmitting = true (all questions must be evaluated and within boundaries)
  );

  const exam = await Exam.findById(examId);
  const examMaximumMarks =
    exam?.maximumMarks ||
    (authoritativeQuestions.size > 0
      ? Array.from(authoritativeQuestions.values()).reduce((sum, q) => sum + q.maximumMarks, 0)
      : 100);

  if (computedTotal > examMaximumMarks) {
    const error: any = new Error(
      `Cannot approve evaluation: Total calculated marks (${computedTotal}) exceed examination maximum (${examMaximumMarks}).`
    );
    error.status = 400;
    error.code = 'TOTAL_EXCEEDS_EXAM_MAXIMUM';
    throw error;
  }

  if (
    typeof evaluation.totalMarks === 'number' &&
    Math.abs(evaluation.totalMarks - computedTotal) > 0.001
  ) {
    const error: any = new Error(
      `Cannot approve evaluation: Recorded total marks (${evaluation.totalMarks}) does not equal computed sum of questions (${computedTotal}).`
    );
    error.status = 400;
    error.code = 'TOTAL_MARKS_MISMATCH';
    throw error;
  }

  // Validate state transition
  validateStateTransition(answerBook.status, 'APPROVED');

  evaluation.questionMarks = validatedList as any;
  evaluation.totalMarks = computedTotal;
  evaluation.status = 'APPROVED';
  await evaluation.save();

  answerBook.status = 'APPROVED';
  await answerBook.save();

  // Create Moderation record
  const moderation = await Moderation.create({
    evaluationId: evaluation._id,
    moderatorId,
    status: 'APPROVED',
    decision: 'APPROVE',
  });

  await evaluation.populate({
    path: 'answerBookId',
    populate: { path: 'examId', select: 'title subjectCode subjectName' },
  });
  await evaluation.populate('examinerId', 'name email');

  await logAuditAction({
    actorId: moderatorId,
    action: 'MODERATION_APPROVED',
    entityType: 'Evaluation',
    entityId: evaluation._id.toString(),
    metadata: {
      answerBookId: evaluation.answerBookId.toString(),
      moderationId: moderation._id.toString(),
    },
  });

  emitToAll('moderation.approved', { evaluation, answerBook, moderation });

  return { evaluation, answerBook, moderation };
}

export async function returnEvaluationByModerator(
  id: string,
  reason: string,
  moderatorId: string
) {
  const trimmedReason = (reason || '').trim();
  if (trimmedReason.length < 5) {
    const error: any = new Error('Please provide a reason of at least 5 characters');
    error.status = 400;
    error.code = 'INVALID_RETURN_REASON';
    throw error;
  }

  let evaluation = await Evaluation.findById(id);
  if (!evaluation) {
    const mod = await Moderation.findById(id);
    if (mod) evaluation = await Evaluation.findById(mod.evaluationId);
  }

  if (!evaluation) {
    const error: any = new Error('Evaluation not found');
    error.status = 404;
    error.code = 'EVALUATION_NOT_FOUND';
    throw error;
  }

  if (!['SUBMITTED', 'UNDER_REVIEW'].includes(evaluation.status)) {
    const error: any = new Error(
      `Cannot return evaluation with status: ${evaluation.status}. Must be SUBMITTED or UNDER_REVIEW.`
    );
    error.status = 400;
    error.code = 'INVALID_STATUS';
    throw error;
  }

  const answerBook = await AnswerBook.findById(evaluation.answerBookId);
  if (!answerBook) {
    const error: any = new Error('Associated answer book not found');
    error.status = 404;
    error.code = 'ANSWER_BOOK_NOT_FOUND';
    throw error;
  }

  // Validate state transition
  validateStateTransition(answerBook.status, 'RETURNED');

  evaluation.status = 'RETURNED';
  evaluation.remarks = trimmedReason;
  await evaluation.save();

  answerBook.status = 'RETURNED';
  await answerBook.save();

  // Create Moderation record
  const moderation = await Moderation.create({
    evaluationId: evaluation._id,
    moderatorId,
    status: 'RETURNED',
    decision: 'RETURN',
    reason: trimmedReason,
  });

  await evaluation.populate({
    path: 'answerBookId',
    populate: { path: 'examId', select: 'title subjectCode subjectName' },
  });
  await evaluation.populate('examinerId', 'name email');

  await logAuditAction({
    actorId: moderatorId,
    action: 'MODERATION_RETURNED',
    entityType: 'Evaluation',
    entityId: evaluation._id.toString(),
    metadata: {
      reason,
      answerBookId: evaluation.answerBookId.toString(),
      examinerId: evaluation.examinerId.toString(),
      moderationId: moderation._id.toString(),
    },
  });

  emitToAll('moderation.returned', { evaluation, answerBook, moderation, reason });

  return { evaluation, answerBook, moderation };
}

export async function fetchModeratorStats() {
  const statusCounts = await Evaluation.aggregate([
    { $match: { status: { $in: ['SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'RETURNED'] } } },
    { $group: { _id: '$status', count: { $sum: 1 } } },
  ]);

  const stats = { submitted: 0, underReview: 0, approved: 0, returned: 0 };

  statusCounts.forEach(({ _id, count }: { _id: string; count: number }) => {
    switch (_id) {
      case 'SUBMITTED': stats.submitted = count; break;
      case 'UNDER_REVIEW': stats.underReview = count; break;
      case 'APPROVED': stats.approved = count; break;
      case 'RETURNED': stats.returned = count; break;
    }
  });

  return stats;
}

export interface IIntegrityIssue {
  id: string;
  ruleName: string;
  severity: 'HIGH' | 'MEDIUM' | 'LOW';
  answerBookCode: string;
  examCode: string;
  examinerName: string;
  description: string;
  timestamp: string;
  evaluationId?: string;
  answerBookId?: string;
}

export async function fetchIntegrityChecks(): Promise<IIntegrityIssue[]> {
  const issues: IIntegrityIssue[] = [];

  // Query evaluations with answer books and exams
  const evaluations = await Evaluation.find()
    .populate({
      path: 'answerBookId',
      populate: { path: 'examId', select: 'title subjectCode maximumMarks totalQuestions' },
    })
    .populate('examinerId', 'name email');

  // Also check for duplicate evaluations per answer book
  const abMap = new Map<string, number>();
  for (const ev of evaluations) {
    const abId = (ev.answerBookId as any)?._id?.toString();
    if (abId) {
      abMap.set(abId, (abMap.get(abId) || 0) + 1);
    }
  }

  // Pre-fetch official question rubrics for distinct exams
  const distinctExamIds = Array.from(
    new Set(
      evaluations
        .map((ev) => {
          const ab = ev.answerBookId as any;
          return ab?.examId?._id?.toString() || ab?.examId?.toString();
        })
        .filter(Boolean)
    )
  );

  const officialQuestions = await Question.find({ examId: { $in: distinctExamIds } }).select(
    'examId questionNumber maximumMarks'
  );

  const examQuestionMaxMarks = new Map<string, number>();
  for (const q of officialQuestions) {
    examQuestionMaxMarks.set(`${q.examId.toString()}_${q.questionNumber}`, q.maximumMarks);
  }

  for (const ev of evaluations) {
    const ab = ev.answerBookId as any;
    const exam = ab?.examId as any;
    const examiner = ev.examinerId as any;
    const abCode = ab?.answerBookCode || 'UNKNOWN';
    const examCode = exam?.subjectCode || '—';
    const examinerName = examiner?.name || 'Unassigned';
    const examIdStr = exam?._id?.toString() || (typeof ab?.examId === 'string' ? ab.examId : '');
    const evalIdStr = ev._id.toString();
    const abIdStr = ab?._id?.toString();

    // 1. Duplicate evaluation check
    if (ab?._id && (abMap.get(ab._id.toString()) || 0) > 1) {
      issues.push({
        id: `dup-${ev._id}`,
        ruleName: 'Duplicate Evaluation Detected',
        severity: 'HIGH',
        answerBookCode: abCode,
        examCode,
        examinerName,
        evaluationId: evalIdStr,
        answerBookId: abIdStr,
        description: `Multiple evaluation records point to the same answer book (${abCode}).`,
        timestamp: ev.updatedAt ? new Date(ev.updatedAt).toISOString() : new Date().toISOString(),
      });
    }

    // 2. Marks above maximum
    const totalMarks = ev.totalMarks ?? 0;
    if (exam && exam.maximumMarks !== undefined && totalMarks > exam.maximumMarks) {
      issues.push({
        id: `max-exceeded-${ev._id}`,
        ruleName: 'Marks Above Maximum Limit',
        severity: 'HIGH',
        answerBookCode: abCode,
        examCode,
        examinerName,
        evaluationId: evalIdStr,
        answerBookId: abIdStr,
        description: `Total marks awarded (${totalMarks}) exceeds the exam maximum (${exam.maximumMarks}).`,
        timestamp: ev.updatedAt ? new Date(ev.updatedAt).toISOString() : new Date().toISOString(),
      });
    }

    // 3. Question-level checks & Arithmetic totals
    if (ev.questionMarks && ev.questionMarks.length > 0) {
      const sum = ev.questionMarks.reduce((acc, q) => acc + (q.marks || 0), 0);
      if (Math.abs(sum - totalMarks) > 0.01) {
        issues.push({
          id: `invalid-total-${ev._id}`,
          ruleName: 'Arithmetic Sum Discrepancy',
          severity: 'MEDIUM',
          answerBookCode: abCode,
          examCode,
          examinerName,
          evaluationId: evalIdStr,
          answerBookId: abIdStr,
          description: `Total marks (${totalMarks}) does not match the sum of individual question marks (${sum}).`,
          timestamp: ev.updatedAt ? new Date(ev.updatedAt).toISOString() : new Date().toISOString(),
        });
      }

      // Check per question marks
      for (const q of ev.questionMarks) {
        if (q.marks < 0) {
          issues.push({
            id: `neg-mark-${ev._id}-Q${q.questionNumber}`,
            ruleName: 'Negative Mark Awarded',
            severity: 'HIGH',
            answerBookCode: abCode,
            examCode,
            examinerName,
            evaluationId: evalIdStr,
            answerBookId: abIdStr,
            description: `Question ${q.questionNumber} was assigned a negative score (${q.marks}).`,
            timestamp: ev.updatedAt ? new Date(ev.updatedAt).toISOString() : new Date().toISOString(),
          });
        }

        const maxRubricMarks = examIdStr ? examQuestionMaxMarks.get(`${examIdStr}_${q.questionNumber}`) : undefined;
        if (maxRubricMarks !== undefined && q.marks > maxRubricMarks) {
          issues.push({
            id: `rubric-exceeded-${ev._id}-Q${q.questionNumber}`,
            ruleName: 'Question Mark Exceeds Rubric Limit',
            severity: 'HIGH',
            answerBookCode: abCode,
            examCode,
            examinerName,
            evaluationId: evalIdStr,
            answerBookId: abIdStr,
            description: `Question ${q.questionNumber} was awarded ${q.marks} marks exceeding maximum rubric allowed (${maxRubricMarks}).`,
            timestamp: ev.updatedAt ? new Date(ev.updatedAt).toISOString() : new Date().toISOString(),
          });
        }

        if (q.status === 'NOT_ATTEMPTED' && q.marks > 0) {
          issues.push({
            id: `not-attempted-marks-${ev._id}-Q${q.questionNumber}`,
            ruleName: 'Unattempted Question Awarded Marks',
            severity: 'HIGH',
            answerBookCode: abCode,
            examCode,
            examinerName,
            evaluationId: evalIdStr,
            answerBookId: abIdStr,
            description: `Question ${q.questionNumber} was recorded as NOT_ATTEMPTED but awarded ${q.marks} mark(s).`,
            timestamp: ev.updatedAt ? new Date(ev.updatedAt).toISOString() : new Date().toISOString(),
          });
        }
      }
    }

    // 4. Incomplete evaluation for submitted scripts
    if (['SUBMITTED', 'UNDER_REVIEW', 'APPROVED'].includes(ev.status)) {
      if (exam && exam.totalQuestions && ev.questionMarks) {
        const accounted = ev.questionMarks.filter(
          (q) => q.status === 'MARKED' || q.status === 'NOT_ATTEMPTED' || q.status === 'FLAGGED'
        ).length;
        if (accounted < exam.totalQuestions) {
          issues.push({
            id: `incomplete-${ev._id}`,
            ruleName: 'Unchecked Questions in Submitted Script',
            severity: 'HIGH',
            answerBookCode: abCode,
            examCode,
            examinerName,
            evaluationId: evalIdStr,
            answerBookId: abIdStr,
            description: `Script was submitted with only ${accounted} of ${exam.totalQuestions} questions accounted for.`,
            timestamp: ev.updatedAt ? new Date(ev.updatedAt).toISOString() : new Date().toISOString(),
          });
        }
      }
    }

    // 5. Rescan required breach on active evaluation
    if (ab?.qualityStatus === 'RESCAN_REQUIRED' && ['SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'IN_PROGRESS'].includes(ev.status)) {
      issues.push({
        id: `rescan-active-${ev._id}`,
        ruleName: 'Rescan Required Pending Evaluation',
        severity: 'HIGH',
        answerBookCode: abCode,
        examCode,
        examinerName,
        evaluationId: evalIdStr,
        answerBookId: abIdStr,
        description: `Script ${abCode} is marked RESCAN_REQUIRED by scanner quality check, but has active evaluation (${ev.status}).`,
        timestamp: ev.updatedAt ? new Date(ev.updatedAt).toISOString() : new Date().toISOString(),
      });
    }

    // 6. Custody State Desynchronization
    if (ab && ev.status) {
      const isDesynced =
        (ev.status === 'APPROVED' && ab.status !== 'APPROVED' && ab.status !== 'FINALIZED') ||
        (ev.status === 'RETURNED' && ab.status !== 'RETURNED') ||
        (ev.status === 'SUBMITTED' && ab.status !== 'SUBMITTED' && ab.status !== 'UNDER_REVIEW');
      if (isDesynced) {
        issues.push({
          id: `custody-desync-${ev._id}`,
          ruleName: 'Custody State Desynchronization',
          severity: 'HIGH',
          answerBookCode: abCode,
          examCode,
          examinerName,
          evaluationId: evalIdStr,
          answerBookId: abIdStr,
          description: `Answer book state (${ab.status}) does not match evaluation custody status (${ev.status}).`,
          timestamp: ev.updatedAt ? new Date(ev.updatedAt).toISOString() : new Date().toISOString(),
        });
      }
    }
  }

  // 7. Missing pages check on AnswerBooks
  const defectiveBooks = await AnswerBook.find({ pageCount: { $lte: 0 } }).populate('examId', 'subjectCode');
  for (const db of defectiveBooks) {
    const exam = db.examId as any;
    issues.push({
      id: `missing-pages-${db._id}`,
      ruleName: 'Invalid Page Count',
      severity: 'MEDIUM',
      answerBookCode: db.answerBookCode,
      examCode: exam?.subjectCode || '—',
      examinerName: 'System Scanner',
      answerBookId: db._id.toString(),
      description: `Answer book registered with invalid or zero page count (${db.pageCount} pages).`,
      timestamp: new Date(db.createdAt).toISOString(),
    });
  }

  // 8. Defective / Failed Ingestion Pages on AnswerBooks
  const defectivePages = await AnswerPage.find({
    $or: [
      { 'quality.status': 'RESCAN_REQUIRED' },
      { processingStatus: 'FAILED' },
    ],
  }).populate({
    path: 'answerBookId',
    populate: { path: 'examId', select: 'subjectCode' },
  });

  for (const page of defectivePages) {
    const pageAb = page.answerBookId as any;
    const pageExam = pageAb?.examId as any;
    const reason =
      page.quality?.status === 'RESCAN_REQUIRED'
        ? 'unacceptable blur/legibility quality score'
        : 'processing pipeline failure';
    issues.push({
      id: `defective-page-${page._id}`,
      ruleName: 'Scanned Page Ingestion Defect',
      severity: 'MEDIUM',
      answerBookCode: pageAb?.answerBookCode || 'UNKNOWN',
      examCode: pageExam?.subjectCode || '—',
      examinerName: 'Scanner Ingestion',
      answerBookId: pageAb?._id?.toString(),
      description: `Page ${page.pageNumber} flagged with ${reason}.`,
      timestamp: page.updatedAt ? new Date(page.updatedAt).toISOString() : new Date().toISOString(),
    });
  }

  return issues;
}

export async function fetchExaminerAnalytics() {
  const examiners = await User.find({ role: 'EXAMINER' }).select('name email isActive').sort({ name: 1 });

  const analytics = await Promise.all(
    examiners.map(async (examiner) => {
      const assigned = await AnswerBook.countDocuments({ assignedExaminerId: examiner._id });
      const completed = await Evaluation.countDocuments({
        examinerId: examiner._id,
        status: { $in: ['SUBMITTED', 'APPROVED'] },
      });
      const returned = await Evaluation.countDocuments({
        examinerId: examiner._id,
        status: 'RETURNED',
      });

      // Compute average marks for submitted/approved evaluations
      const completedEvals = await Evaluation.find({
        examinerId: examiner._id,
        status: { $in: ['SUBMITTED', 'APPROVED'] },
      }).select('totalMarks startedAt submittedAt questionMarks');

      let averageMarks = 0;
      let averageEvaluationTimeMinutes = 0;
      let totalTimeMinutes = 0;
      let timeCount = 0;
      let flags = returned;

      if (completedEvals.length > 0) {
        const sumMarks = completedEvals.reduce((acc, ev) => acc + (ev.totalMarks || 0), 0);
        averageMarks = Math.round((sumMarks / completedEvals.length) * 10) / 10;

        for (const ev of completedEvals) {
          if (ev.startedAt && ev.submittedAt) {
            const diffMs = new Date(ev.submittedAt).getTime() - new Date(ev.startedAt).getTime();
            if (diffMs > 0) {
              totalTimeMinutes += diffMs / (1000 * 60);
              timeCount++;
            }
          }
          if (ev.questionMarks) {
            flags += ev.questionMarks.filter((q) => q.status === 'FLAGGED').length;
          }
        }

        if (timeCount > 0) {
          averageEvaluationTimeMinutes = Math.round(totalTimeMinutes / timeCount);
        }
      }

      return {
        examinerId: examiner._id,
        name: examiner.name,
        email: examiner.email,
        isActive: examiner.isActive,
        assigned,
        completed,
        returned,
        flags,
        averageMarks,
        averageEvaluationTimeMinutes,
      };
    })
  );

  return analytics;
}
