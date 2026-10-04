import mongoose from 'mongoose';
import dotenv from 'dotenv';
import path from 'path';
import { Evaluation } from '../models/Evaluation';
import { AnswerBook } from '../models/AnswerBook';
import { Exam } from '../models/Exam';
import { Question } from '../models/Question';
import { User } from '../models/User';
import { Moderation } from '../models/Moderation';
import { AuditLog } from '../models/AuditLog';
import {
  approveEvaluationByModerator,
  returnEvaluationByModerator,
  fetchModerationById,
} from '../services/moderation.service';

dotenv.config({ path: path.resolve(__dirname, '../../.env') });

async function runModerationHardeningTests() {
  console.log('===============================================================');
  console.log('EVALNEXA MODERATION APPROVAL & RETURN HARDENING TEST SUITE');
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
  let testExam: any = null;
  let testExaminer: any = null;
  let testModerator: any = null;
  let testBook: any = null;
  let testEval: any = null;

  try {
    // 0. Setup test users and exam
    testExaminer = await User.findOne({ role: 'EXAMINER' });
    if (!testExaminer) {
      testExaminer = await User.create({
        name: 'Test Examiner Mod',
        email: `modexaminer_${Date.now()}@evalnexa.test`,
        passwordHash: 'dummyhash',
        role: 'EXAMINER',
      });
    }

    testModerator = await User.findOne({ role: 'MODERATOR' });
    if (!testModerator) {
      testModerator = await User.create({
        name: 'Test Moderator User',
        email: `moderator_${Date.now()}@evalnexa.test`,
        passwordHash: 'dummyhash',
        role: 'MODERATOR',
      });
    }

    testExam = await Exam.create({
      title: 'Advanced Computer Networks Exam',
      subjectCode: `CS-MOD-${Date.now().toString().slice(-4)}`,
      subjectName: 'Computer Networks',
      academicSession: '2025-2026',
      totalQuestions: 2,
      maximumMarks: 100,
      createdBy: testModerator._id,
    });

    await Question.create({
      examId: testExam._id,
      questionNumber: 1,
      text: 'Explain TCP handshake mechanism.',
      maximumMarks: 40,
      rubric: [{ criterion: 'Core protocol steps', marks: 40 }],
    });

    await Question.create({
      examId: testExam._id,
      questionNumber: 2,
      text: 'Explain BGP routing and autonomous systems.',
      maximumMarks: 60,
      rubric: [{ criterion: 'Routing analysis', marks: 60 }],
    });

    // -------------------------------------------------------------------------
    // Test 1: Reject approval if Evaluation does not exist
    // -------------------------------------------------------------------------
    console.log('Test 1: Reject approval on non-existent evaluation...');
    try {
      const fakeId = new mongoose.Types.ObjectId().toString();
      await approveEvaluationByModerator(fakeId, testModerator._id.toString());
      throw new Error('FAILED: Should have thrown 404 for missing evaluation');
    } catch (err: any) {
      if (err.code === 'EVALUATION_NOT_FOUND' && err.status === 404) {
        console.log('✓ Successfully rejected missing evaluation with 404 EVALUATION_NOT_FOUND');
        passCount++;
      } else {
        throw new Error(`Unexpected error: ${err.code} ${err.message}`);
      }
    }

    // -------------------------------------------------------------------------
    // Test 2: Reject return if reason is less than 5 characters
    // -------------------------------------------------------------------------
    console.log('\nTest 2: Reject return if reason is too short (< 5 chars)...');
    testBook = await AnswerBook.create({
      examId: testExam._id,
      answerBookCode: `SCRIPT-MOD-${Date.now()}`,
      studentCode: `STU-MOD-${Date.now().toString().slice(-4)}`,
      pageCount: 3,
      status: 'SUBMITTED',
    });

    testEval = await Evaluation.create({
      answerBookId: testBook._id,
      examinerId: testExaminer._id,
      status: 'SUBMITTED',
      questionMarks: [
        { questionNumber: 1, marks: 35, status: 'MARKED' },
        { questionNumber: 2, marks: 55, status: 'MARKED' },
      ],
      totalMarks: 90,
    });

    try {
      await returnEvaluationByModerator(testEval._id.toString(), 'Fix', testModerator._id.toString());
      throw new Error('FAILED: Should have rejected short return reason');
    } catch (err: any) {
      if (err.code === 'INVALID_RETURN_REASON' && err.status === 400) {
        console.log('✓ Successfully rejected short return reason with 400 INVALID_RETURN_REASON');
        passCount++;
      } else {
        throw new Error(`Unexpected error: ${err.code} ${err.message}`);
      }
    }

    // -------------------------------------------------------------------------
    // Test 3: Reject approval if AnswerBook has qualityStatus = RESCAN_REQUIRED
    // -------------------------------------------------------------------------
    console.log('\nTest 3: Reject approval if AnswerBook has RESCAN_REQUIRED...');
    testBook.qualityStatus = 'RESCAN_REQUIRED';
    await testBook.save();

    try {
      await approveEvaluationByModerator(testEval._id.toString(), testModerator._id.toString());
      throw new Error('FAILED: Should have rejected approval for RESCAN_REQUIRED script');
    } catch (err: any) {
      if (err.code === 'RESCAN_REQUIRED' && err.status === 400) {
        console.log('✓ Successfully rejected approval for RESCAN_REQUIRED with 400 RESCAN_REQUIRED');
        passCount++;
      } else {
        throw new Error(`Unexpected error: ${err.code} ${err.message}`);
      }
    }

    // Reset qualityStatus
    testBook.qualityStatus = 'VERIFIED';
    await testBook.save();

    // -------------------------------------------------------------------------
    // Test 4: Reject approval if questions are incomplete (NOT_STARTED or missing)
    // -------------------------------------------------------------------------
    console.log('\nTest 4: Reject approval if questions are incomplete...');
    testEval.questionMarks = [
      { questionNumber: 1, marks: 35, status: 'MARKED' },
      { questionNumber: 2, marks: 0, status: 'NOT_STARTED' },
    ];
    testEval.totalMarks = 35;
    await testEval.save();

    try {
      await approveEvaluationByModerator(testEval._id.toString(), testModerator._id.toString());
      throw new Error('FAILED: Should have rejected approval with NOT_STARTED question');
    } catch (err: any) {
      if ((err.code === 'QUESTION_UNMARKED' || err.code === 'INCOMPLETE_EVALUATION') && err.status === 400) {
        console.log(`✓ Successfully rejected approval with 400 ${err.code}: ${err.message}`);
        passCount++;
      } else {
        throw new Error(`Unexpected error: ${err.code} ${err.message}`);
      }
    }

    // -------------------------------------------------------------------------
    // Test 5: Reject approval if arithmetic sum does not equal totalMarks
    // -------------------------------------------------------------------------
    console.log('\nTest 5: Reject approval if question marks sum != totalMarks...');
    await Evaluation.updateOne(
      { _id: testEval._id },
      {
        $set: {
          questionMarks: [
            { questionNumber: 1, marks: 35, status: 'MARKED' },
            { questionNumber: 2, marks: 55, status: 'MARKED' },
          ],
          totalMarks: 80, // Bypasses pre-validate to test corrupted DB record
        },
      }
    );

    try {
      await approveEvaluationByModerator(testEval._id.toString(), testModerator._id.toString());
      throw new Error('FAILED: Should have rejected approval with total mismatch');
    } catch (err: any) {
      if (err.code === 'TOTAL_MARKS_MISMATCH' && err.status === 400) {
        console.log('✓ Successfully rejected approval with 400 TOTAL_MARKS_MISMATCH');
        passCount++;
      } else {
        throw new Error(`Unexpected error: ${err.code} ${err.message}`);
      }
    }

    // -------------------------------------------------------------------------
    // Test 6: Successful Return for Revision
    // -------------------------------------------------------------------------
    console.log('\nTest 6: Successful return for revision with valid reason...');
    testEval.totalMarks = 90;
    await testEval.save();

    const returnResult = await returnEvaluationByModerator(
      testEval._id.toString(),
      'Please re-evaluate Question 2 using the updated grading rubric.',
      testModerator._id.toString()
    );

    if (
      returnResult.evaluation.status === 'RETURNED' &&
      returnResult.answerBook.status === 'RETURNED' &&
      returnResult.moderation.status === 'RETURNED' &&
      returnResult.moderation.decision === 'RETURN' &&
      returnResult.evaluation.remarks?.includes('Question 2')
    ) {
      console.log('✓ Successfully returned evaluation: statuses updated to RETURNED with remarks recorded');
      passCount++;
    } else {
      throw new Error(`Return failed: ${JSON.stringify(returnResult)}`);
    }

    // Verify audit log for return
    const returnAudit = await AuditLog.findOne({
      entityId: testEval._id.toString(),
      action: 'MODERATION_RETURNED',
    });
    if (returnAudit) {
      console.log('✓ Audit log MODERATION_RETURNED verified in database');
      passCount++;
    } else {
      throw new Error('Missing audit log for MODERATION_RETURNED');
    }

    // -------------------------------------------------------------------------
    // Test 7: Reject approval of an evaluation in RETURNED status
    // -------------------------------------------------------------------------
    console.log('\nTest 7: Reject approval of an evaluation in RETURNED status...');
    try {
      await approveEvaluationByModerator(testEval._id.toString(), testModerator._id.toString());
      throw new Error('FAILED: Should have rejected approval for RETURNED evaluation');
    } catch (err: any) {
      if (err.code === 'INVALID_STATUS' && err.status === 400) {
        console.log('✓ Successfully rejected approval for RETURNED status with 400 INVALID_STATUS');
        passCount++;
      } else {
        throw new Error(`Unexpected error: ${err.code} ${err.message}`);
      }
    }

    // -------------------------------------------------------------------------
    // Test 8: Resubmit from Examiner and then successfully Approve by Moderator
    // -------------------------------------------------------------------------
    console.log('\nTest 8: Successful approval of resubmitted evaluation...');
    // Simulate examiner resubmission
    testEval = await Evaluation.findById(testEval._id);
    testBook = await AnswerBook.findById(testBook._id);
    testEval.status = 'SUBMITTED';
    testBook.status = 'SUBMITTED';
    testEval.questionMarks = [
      { questionNumber: 1, marks: 35, status: 'MARKED' },
      { questionNumber: 2, marks: 55, status: 'MARKED' },
    ];
    testEval.totalMarks = 90;
    await testEval.save();
    await testBook.save();

    const approvalResult = await approveEvaluationByModerator(
      testEval._id.toString(),
      testModerator._id.toString()
    );

    if (
      approvalResult.evaluation.status === 'APPROVED' &&
      approvalResult.answerBook.status === 'APPROVED' &&
      approvalResult.moderation.status === 'APPROVED' &&
      approvalResult.moderation.decision === 'APPROVE' &&
      approvalResult.evaluation.totalMarks === 90
    ) {
      console.log('✓ Successfully approved evaluation: statuses updated to APPROVED and marks certified');
      passCount++;
    } else {
      throw new Error(`Approval failed: ${JSON.stringify(approvalResult)}`);
    }

    // Verify audit log for approval
    const approveAudit = await AuditLog.findOne({
      entityId: testEval._id.toString(),
      action: 'MODERATION_APPROVED',
    });
    if (approveAudit) {
      console.log('✓ Audit log MODERATION_APPROVED verified in database');
      passCount++;
    } else {
      throw new Error('Missing audit log for MODERATION_APPROVED');
    }

    // -------------------------------------------------------------------------
    // Test 9: Verify fetchModerationById returns full docket and history
    // -------------------------------------------------------------------------
    console.log('\nTest 9: Verify fetchModerationById returns docket and moderation history...');
    const detail = await fetchModerationById(testEval._id.toString());
    if (
      detail.evaluation &&
      detail.evaluation.status === 'APPROVED' &&
      detail.moderationHistory.length >= 2 // Both return and approve records
    ) {
      console.log(`✓ fetchModerationById returned docket with ${detail.moderationHistory.length} history records`);
      passCount++;
    } else {
      throw new Error(`Detail fetch unexpected: ${JSON.stringify(detail)}`);
    }

    console.log('\n===============================================================');
    console.log(`ALL ${passCount} MODERATION HARDENING TESTS PASSED SUCCESSFULLY!`);
    console.log('===============================================================\n');
  } catch (error: any) {
    console.error('\n❌ Test Suite Failed:', error.message);
    process.exit(1);
  } finally {
    // Cleanup created test records
    try {
      if (testEval) await Evaluation.findByIdAndDelete(testEval._id);
      if (testBook) await AnswerBook.findByIdAndDelete(testBook._id);
      if (testExam) {
        await Question.deleteMany({ examId: testExam._id });
        await Exam.findByIdAndDelete(testExam._id);
      }
      if (testEval) await Moderation.deleteMany({ evaluationId: testEval._id });
      if (testEval) await AuditLog.deleteMany({ entityId: testEval._id.toString() });
      await mongoose.disconnect();
      console.log('Cleaned up test fixtures and disconnected from MongoDB.');
    } catch (cleanupErr: any) {
      console.error('Cleanup error:', cleanupErr.message);
    }
  }
}

runModerationHardeningTests();
