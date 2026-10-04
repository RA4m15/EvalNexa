import mongoose from 'mongoose';
import dotenv from 'dotenv';
import path from 'path';
import { Evaluation } from '../models/Evaluation';
import { AnswerBook } from '../models/AnswerBook';
import { Exam } from '../models/Exam';
import { Question } from '../models/Question';
import { User } from '../models/User';
import { AuditLog } from '../models/AuditLog';
import {
  computeQuestionMarksSummary,
  validateQuestionMarksList,
  submitEvaluationFinal,
} from '../services/evaluations.service';

dotenv.config({ path: path.resolve(__dirname, '../../.env') });

async function runSubmissionHardeningTests() {
  console.log('===============================================================');
  console.log('EVALNEXA EVALUATION SUBMISSION HARDENING TEST SUITE');
  console.log('===============================================================\n');

  const mongoUri = process.env.MONGODB_URI || 'mongodb://127.0.0.1:27017/evalnexa';
  console.log(`Connecting to MongoDB at: ${mongoUri}...`);
  try {
    await mongoose.connect(mongoUri);
    console.log('✓ Connected to MongoDB.\n');
  } catch (err: any) {
    console.error('Failed to connect to MongoDB:', err.message);
    process.exit(1);
  }

  let passCount = 0;

  try {
    // -------------------------------------------------------------------------
    // Setup test fixtures
    // -------------------------------------------------------------------------
    const examiner = await User.create({
      name: 'Hardened Examiner',
      email: `examiner-hardened-${Date.now()}@evalnexa.test`,
      passwordHash: 'hashed_pw_test',
      role: 'EXAMINER',
    });

    const testExam = await Exam.create({
      title: 'Final Hardening Exam',
      subjectCode: `HDN-${Date.now().toString().slice(-4)}`,
      subjectName: 'Hardened Submissions',
      academicSession: '2026-TEST',
      totalQuestions: 4,
      maximumMarks: 100,
      passingMarks: 40,
      durationMinutes: 180,
      status: 'EVALUATION_OPEN',
      createdBy: examiner._id,
    });

    const q1 = await Question.create({
      examId: testExam._id,
      questionNumber: 1,
      text: 'Question 1: Definition of distributed systems',
      maximumMarks: 25,
      rubric: [{ criterion: 'Definition', marks: 25 }],
    });

    const q2 = await Question.create({
      examId: testExam._id,
      questionNumber: 2,
      text: 'Question 2: CAP Theorem analysis',
      maximumMarks: 25,
      rubric: [{ criterion: 'Proof & tradeoff analysis', marks: 25 }],
    });

    const q3 = await Question.create({
      examId: testExam._id,
      questionNumber: 3,
      text: 'Question 3: Raft consensus protocol',
      maximumMarks: 25,
      rubric: [{ criterion: 'Leader election algorithm', marks: 25 }],
    });

    const q4 = await Question.create({
      examId: testExam._id,
      questionNumber: 4,
      text: 'Question 4: Byzantine Fault Tolerance',
      maximumMarks: 25,
      rubric: [{ criterion: 'PBFT explanation', marks: 25 }],
    });

    const answerBook = await AnswerBook.create({
      answerBookCode: `HARDEN-AB-${Date.now()}`,
      studentCode: 'STU-TEST-001',
      examId: testExam._id,
      assignedExaminerId: examiner._id,
      status: 'IN_PROGRESS',
      pageCount: 6,
    });

    const evaluation = await Evaluation.create({
      answerBookId: answerBook._id,
      examinerId: examiner._id,
      status: 'IN_PROGRESS',
      totalMarks: 0,
      questionMarks: [
        { questionNumber: 1, marks: 0, status: 'NOT_STARTED' },
        { questionNumber: 2, marks: 0, status: 'NOT_STARTED' },
        { questionNumber: 3, marks: 0, status: 'NOT_STARTED' },
        { questionNumber: 4, marks: 0, status: 'NOT_STARTED' },
      ],
    });

    const authoritativeMap = new Map([
      [1, { questionNumber: 1, maximumMarks: 25 }],
      [2, { questionNumber: 2, maximumMarks: 25 }],
      [3, { questionNumber: 3, maximumMarks: 25 }],
      [4, { questionNumber: 4, maximumMarks: 25 }],
    ]);

    // -------------------------------------------------------------------------
    // Test 1: computeQuestionMarksSummary computes exact breakdown
    // -------------------------------------------------------------------------
    console.log('Test 1: Testing exact breakdown determination...');
    const testList1: any[] = [
      { questionNumber: 1, marks: 20, status: 'MARKED' },
      { questionNumber: 2, marks: 0, status: 'NOT_ATTEMPTED' },
      { questionNumber: 3, marks: 18, status: 'FLAGGED' },
      { questionNumber: 4, marks: 0, status: 'NOT_STARTED' },
    ];
    const summary1 = computeQuestionMarksSummary(testList1, authoritativeMap);
    if (
      summary1.totalExpected !== 4 ||
      summary1.evaluatedQuestions !== 1 ||
      summary1.notAttemptedQuestions !== 1 ||
      summary1.flaggedQuestions !== 1 ||
      summary1.unansweredQuestions !== 1 ||
      summary1.missingQuestionNumbers.length !== 1 ||
      summary1.missingQuestionNumbers[0] !== 4
    ) {
      throw new Error(`Summary 1 mismatch: ${JSON.stringify(summary1)}`);
    }
    console.log('✓ Exact question summary metrics determined correctly:', summary1);
    passCount++;

    // -------------------------------------------------------------------------
    // Test 2: Submission blocked when question is NOT_STARTED
    // -------------------------------------------------------------------------
    console.log('\nTest 2: Testing submission blocked when a question is NOT_STARTED...');
    try {
      await submitEvaluationFinal(
        evaluation._id.toString(),
        {
          questionMarks: testList1,
        },
        examiner._id.toString()
      );
      throw new Error('FAILED: Expected submission rejection when Q4 is NOT_STARTED');
    } catch (err: any) {
      if (err.code !== 'QUESTION_UNMARKED' || err.status !== 400) {
        throw new Error(`Unexpected error code/status: ${err.code} (${err.status})`);
      }
      console.log('✓ Submission blocked with QUESTION_UNMARKED (Q4 was NOT_STARTED)');
      passCount++;
    }

    // -------------------------------------------------------------------------
    // Test 3: Submission blocked when question entry is missing entirely
    // -------------------------------------------------------------------------
    console.log('\nTest 3: Testing submission blocked when a question is missing entirely...');
    try {
      const missingList: any[] = [
        { questionNumber: 1, marks: 20, status: 'MARKED' },
        { questionNumber: 2, marks: 0, status: 'NOT_ATTEMPTED' },
        { questionNumber: 3, marks: 18, status: 'FLAGGED' },
        // Q4 is completely missing from the array
      ];
      await submitEvaluationFinal(
        evaluation._id.toString(),
        {
          questionMarks: missingList,
        },
        examiner._id.toString()
      );
      throw new Error('FAILED: Expected submission rejection when Q4 is missing');
    } catch (err: any) {
      if (err.code !== 'MISSING_QUESTION_EVALUATION' || err.status !== 400) {
        throw new Error(`Unexpected error code/status: ${err.code} (${err.status})`);
      }
      console.log('✓ Submission blocked with MISSING_QUESTION_EVALUATION (Q4 was missing)');
      passCount++;
    }

    // -------------------------------------------------------------------------
    // Test 4: AI suggestion present but status NOT_STARTED cannot bypass submission block
    // -------------------------------------------------------------------------
    console.log('\nTest 4: Verifying AI suggestion cannot bypass deterministic submission rules...');
    try {
      const aiSuggestedList: any[] = [
        { questionNumber: 1, marks: 20, status: 'MARKED' },
        { questionNumber: 2, marks: 0, status: 'NOT_ATTEMPTED' },
        { questionNumber: 3, marks: 18, status: 'FLAGGED' },
        {
          questionNumber: 4,
          marks: 0,
          status: 'NOT_STARTED',
          aiAnalysis: {
            suggestedMarks: 22,
            confidence: 0.95,
            criteria: [{ name: 'PBFT', awardedMarks: 22, maxMarks: 25 }],
          },
        },
      ];
      await submitEvaluationFinal(
        evaluation._id.toString(),
        {
          questionMarks: aiSuggestedList,
        },
        examiner._id.toString()
      );
      throw new Error('FAILED: AI suggestion should not bypass NOT_STARTED submission block');
    } catch (err: any) {
      if (err.code !== 'QUESTION_UNMARKED') {
        throw new Error(`Unexpected error code: ${err.code}`);
      }
      console.log('✓ AI suggestion verified non-authoritative: submission blocked until examiner evaluates');
      passCount++;
    }

    // -------------------------------------------------------------------------
    // Test 5: Rejection of invalid marks
    // -------------------------------------------------------------------------
    console.log('\nTest 5: Testing invalid marks rejection...');
    try {
      const invalidMarksList: any[] = [
        { questionNumber: 1, marks: 30, status: 'MARKED' }, // max is 25
        { questionNumber: 2, marks: 0, status: 'NOT_ATTEMPTED' },
        { questionNumber: 3, marks: 18, status: 'FLAGGED' },
        { questionNumber: 4, marks: 20, status: 'MARKED' },
      ];
      validateQuestionMarksList(invalidMarksList, authoritativeMap, true);
      throw new Error('FAILED: Expected invalid marks rejection');
    } catch (err: any) {
      if (err.code !== 'MARKS_EXCEED_MAXIMUM' || err.status !== 400) {
        throw new Error(`Unexpected error: ${err.code} (${err.status})`);
      }
      console.log('✓ Excessive marks rejected with 400 MARKS_EXCEED_MAXIMUM');
      passCount++;
    }

    // -------------------------------------------------------------------------
    // Test 6: Successful valid submission
    // -------------------------------------------------------------------------
    console.log('\nTest 6: Testing successful valid submission workflow...');
    const validList: any[] = [
      { questionNumber: 1, marks: 22, status: 'MARKED' },
      { questionNumber: 2, marks: 0, status: 'NOT_ATTEMPTED' },
      { questionNumber: 3, marks: 20, status: 'FLAGGED' },
      { questionNumber: 4, marks: 25, status: 'MARKED' },
    ];

    const result = await submitEvaluationFinal(
      evaluation._id.toString(),
      {
        questionMarks: validList,
        remarks: 'All 4 questions comprehensively evaluated',
      },
      examiner._id.toString()
    );

    // Expected total: 22 + 0 + 20 + 25 = 67
    if (result.evaluation.totalMarks !== 67) {
      throw new Error(`Expected totalMarks 67, got ${result.evaluation.totalMarks}`);
    }
    if (result.evaluation.status !== 'SUBMITTED') {
      throw new Error(`Expected evaluation status SUBMITTED, got ${result.evaluation.status}`);
    }
    if (result.answerBook.status !== 'SUBMITTED') {
      throw new Error(`Expected answerBook status SUBMITTED, got ${result.answerBook.status}`);
    }
    console.log('✓ Evaluation and AnswerBook successfully submitted with authoritative total: 67/100');
    passCount++;

    // -------------------------------------------------------------------------
    // Test 7: Verify audit log recorded summary
    // -------------------------------------------------------------------------
    console.log('\nTest 7: Verifying audit log creation with full summary metadata...');
    const auditRecord = await AuditLog.findOne({
      entityId: evaluation._id.toString(),
      action: 'EVALUATION_SUBMITTED',
    });
    if (!auditRecord) {
      throw new Error('Audit record not found for EVALUATION_SUBMITTED');
    }
    const meta = auditRecord.metadata as any;
    if (
      meta.totalMarks !== 67 ||
      meta.totalExpected !== 4 ||
      meta.evaluatedQuestions !== 2 ||
      meta.notAttemptedQuestions !== 1 ||
      meta.flaggedQuestions !== 1 ||
      meta.unansweredQuestions !== 0
    ) {
      throw new Error(`Audit metadata mismatch: ${JSON.stringify(meta)}`);
    }
    console.log('✓ Audit log confirmed with complete question breakdown metadata:', meta);
    passCount++;

    // -------------------------------------------------------------------------
    // Cleanup fixtures
    // -------------------------------------------------------------------------
    await Question.deleteMany({ examId: testExam._id });
    await Evaluation.findByIdAndDelete(evaluation._id);
    await AnswerBook.findByIdAndDelete(answerBook._id);
    await Exam.findByIdAndDelete(testExam._id);
    await User.findByIdAndDelete(examiner._id);
    await AuditLog.deleteMany({ entityId: evaluation._id.toString() });

    console.log('\n===============================================================');
    console.log(`ALL ${passCount} SUBMISSION HARDENING TESTS PASSED SUCCESSFULLY!`);
    console.log('===============================================================\n');
  } finally {
    await mongoose.disconnect();
    console.log('Disconnected from MongoDB. Cleanup completed.');
  }
}

runSubmissionHardeningTests().catch((err) => {
  console.error('\n❌ Submission Hardening Test Suite Failed:', err);
  process.exit(1);
});
