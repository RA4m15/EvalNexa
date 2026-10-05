import mongoose from 'mongoose';
import dotenv from 'dotenv';
import path from 'path';
import { Result } from '../models/Result';
import { Evaluation } from '../models/Evaluation';
import { AnswerBook } from '../models/AnswerBook';
import { Exam } from '../models/Exam';
import { Question } from '../models/Question';
import { User } from '../models/User';
import {
  finalizeEvaluationResult,
  fetchResults,
  fetchResultsForExam,
  fetchResultById,
} from '../services/results.service';

dotenv.config({ path: path.resolve(__dirname, '../../.env') });

async function runResultTests() {
  console.log('===============================================================');
  console.log('EVALNEXA RESULT FINALIZATION WORKFLOW TEST SUITE');
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
  let testUser: any = null;
  let testAdmin: any = null;
  let testBook: any = null;
  let testEval: any = null;

  try {
    // Setup test user, admin, exam, questions
    testUser = await User.findOne({ role: 'EXAMINER' });
    if (!testUser) {
      testUser = await User.create({
        name: 'Test Examiner',
        email: `examiner_${Date.now()}@evalnexa.test`,
        passwordHash: 'dummyhash',
        role: 'EXAMINER',
      });
    }

    testAdmin = await User.findOne({ role: 'ADMIN' });
    if (!testAdmin) {
      testAdmin = await User.create({
        name: 'Test Administrator',
        email: `admin_${Date.now()}@evalnexa.test`,
        passwordHash: 'dummyhash',
        role: 'ADMIN',
      });
    }

    testExam = await Exam.create({
      title: 'Finalization Automated Unit Exam',
      subjectCode: `TST-${Date.now().toString().slice(-4)}`,
      subjectName: 'Result Workflow Verification',
      academicSession: '2026-TEST',
      maximumMarks: 100,
      passingMarks: 40,
      totalQuestions: 2,
      durationMinutes: 180,
      status: 'EVALUATION_OPEN',
      createdBy: testAdmin._id,
    });

    await Question.create({
      examId: testExam._id,
      questionNumber: 1,
      text: 'Section A question',
      maximumMarks: 40,
      rubric: [{ criterion: 'Core answer', marks: 40 }],
    });

    await Question.create({
      examId: testExam._id,
      questionNumber: 2,
      text: 'Section B question',
      maximumMarks: 60,
      rubric: [{ criterion: 'Extended answer', marks: 60 }],
    });

    // -------------------------------------------------------------------------
    // Test 1: Rejection if Evaluation Not Found
    // -------------------------------------------------------------------------
    console.log('Test 1: Testing non-existent evaluation rejection...');
    try {
      const fakeId = new mongoose.Types.ObjectId().toString();
      await finalizeEvaluationResult(fakeId, testAdmin._id.toString());
      throw new Error('FAILED: Should have thrown 404 for missing evaluation');
    } catch (err: any) {
      if (err.code === 'EVALUATION_NOT_FOUND' && err.status === 404) {
        console.log('✓ Successfully rejected missing evaluation with 404 EVALUATION_NOT_FOUND');
        passCount++;
      } else {
        throw new Error(`Unexpected error: ${err.code} ${err.message}`);
      }
    }

    // Create a real AnswerBook and Evaluation for testing
    testBook = await AnswerBook.create({
      examId: testExam._id,
      answerBookCode: `SCRIPT-${Date.now()}`,
      studentCode: `STU-${Date.now().toString().slice(-4)}`,
      pageCount: 4,
      status: 'UNDER_REVIEW', // Not yet approved
    });

    testEval = await Evaluation.create({
      answerBookId: testBook._id,
      examinerId: testUser._id,
      status: 'UNDER_REVIEW', // Not yet approved
      questionMarks: [
        { questionNumber: 1, marks: 35, status: 'MARKED' },
        { questionNumber: 2, marks: 55, status: 'MARKED' },
      ],
      totalMarks: 90,
    });

    // -------------------------------------------------------------------------
    // Test 2: Rejection if Evaluation is not APPROVED
    // -------------------------------------------------------------------------
    console.log('\nTest 2: Testing unapproved evaluation rejection...');
    try {
      await finalizeEvaluationResult(testEval._id.toString(), testAdmin._id.toString());
      throw new Error('FAILED: Should have rejected unapproved evaluation');
    } catch (err: any) {
      if (err.code === 'INVALID_EVALUATION_STATUS' && err.status === 400) {
        console.log('✓ Successfully rejected unapproved evaluation with 400 INVALID_EVALUATION_STATUS');
        passCount++;
      } else {
        throw new Error(`Unexpected error: ${err.code} ${err.message}`);
      }
    }

    // Set evaluation status to APPROVED, but keep answerBook as UNDER_REVIEW
    testEval.status = 'APPROVED';
    await testEval.save();

    // -------------------------------------------------------------------------
    // Test 3: Rejection if AnswerBook is not APPROVED
    // -------------------------------------------------------------------------
    console.log('\nTest 3: Testing unapproved answer book rejection...');
    try {
      await finalizeEvaluationResult(testEval._id.toString(), testAdmin._id.toString());
      throw new Error('FAILED: Should have rejected unapproved answer book');
    } catch (err: any) {
      if (err.code === 'INVALID_ANSWER_BOOK_STATUS' && err.status === 400) {
        console.log('✓ Successfully rejected unapproved answer book with 400 INVALID_ANSWER_BOOK_STATUS');
        passCount++;
      } else {
        throw new Error(`Unexpected error: ${err.code} ${err.message}`);
      }
    }

    // -------------------------------------------------------------------------
    // Test 4: Rejection if total marks does not equal question marks sum
    // -------------------------------------------------------------------------
    console.log('\nTest 4: Testing mismatched total marks rejection...');
    testBook.status = 'APPROVED';
    await testBook.save();

    // Bypass mongoose pre-validate hook using direct MongoDB update
    await Evaluation.updateOne({ _id: testEval._id }, { $set: { totalMarks: 999 } });

    try {
      await finalizeEvaluationResult(testEval._id.toString(), testAdmin._id.toString());
      throw new Error('FAILED: Should have rejected mismatched total marks');
    } catch (err: any) {
      if (err.code === 'TOTAL_MARKS_MISMATCH' && err.status === 400) {
        console.log('✓ Successfully rejected mismatched total marks with 400 TOTAL_MARKS_MISMATCH');
        passCount++;
      } else {
        throw new Error(`Unexpected error: ${err.code} ${err.message}`);
      }
    }

    // Fix total marks back to sum of questions: 35 + 55 = 90
    await Evaluation.updateOne({ _id: testEval._id }, { $set: { totalMarks: 90 } });

    // -------------------------------------------------------------------------
    // Test 5: Successful Finalization & Calculations
    // -------------------------------------------------------------------------
    console.log('\nTest 5: Testing authoritative backend calculation and Result finalization...');
    const finalizedResult = await finalizeEvaluationResult(
      testEval._id.toString(),
      testAdmin._id.toString(),
      { name: testAdmin.name, role: testAdmin.role }
    );

    if (
      finalizedResult &&
      finalizedResult.status === 'FINALIZED' &&
      finalizedResult.totalMarks === 90 &&
      finalizedResult.maximumMarks === 100 &&
      finalizedResult.percentage === 90
    ) {
      console.log('✓ Result created with status FINALIZED');
      console.log(`✓ Total marks calculated authoritatively: ${finalizedResult.totalMarks}/${finalizedResult.maximumMarks} (${finalizedResult.percentage}%)`);
      passCount++;
    } else {
      throw new Error(`Finalized result has unexpected data: ${JSON.stringify(finalizedResult)}`);
    }

    // Verify AnswerBook status is now FINALIZED
    const updatedBook = await AnswerBook.findById(testBook._id);
    if (updatedBook?.status === 'FINALIZED') {
      console.log('✓ AnswerBook status transitioned to FINALIZED');
      passCount++;
    } else {
      throw new Error(`AnswerBook status is '${updatedBook?.status}', expected 'FINALIZED'`);
    }

    // Verify Evaluation status remains APPROVED
    const updatedEval = await Evaluation.findById(testEval._id);
    if (updatedEval?.status === 'APPROVED') {
      console.log('✓ Evaluation status remains APPROVED');
      passCount++;
    } else {
      throw new Error(`Evaluation status is '${updatedEval?.status}', expected 'APPROVED'`);
    }

    // -------------------------------------------------------------------------
    // Test 6: Idempotency (Calling finalize twice must return same result without duplicate)
    // -------------------------------------------------------------------------
    console.log('\nTest 6: Testing finalization idempotency...');
    const secondCall = await finalizeEvaluationResult(
      testEval._id.toString(),
      testAdmin._id.toString()
    );

    if (secondCall._id.toString() === finalizedResult._id.toString()) {
      const allResultsCount = await Result.countDocuments({ answerBookId: testBook._id });
      if (allResultsCount === 1) {
        console.log('✓ Idempotency verified: exactly 1 Result record exists, duplicate was prevented');
        passCount++;
      } else {
        throw new Error(`Duplicate results detected: count = ${allResultsCount}`);
      }
    } else {
      throw new Error('Second call returned a different Result instance');
    }

    // -------------------------------------------------------------------------
    // Test 7: Query services (fetchResults, fetchResultsForExam, fetchResultById)
    // -------------------------------------------------------------------------
    console.log('\nTest 7: Testing result retrieval services...');
    const allResults = await fetchResults({ examId: testExam._id.toString() });
    if (allResults.length >= 1) {
      console.log(`✓ fetchResults returned ${allResults.length} result(s)`);
      passCount++;
    } else {
      throw new Error('fetchResults returned no results for test exam');
    }

    const examResults = await fetchResultsForExam(testExam._id.toString());
    if (examResults.length >= 1) {
      console.log(`✓ fetchResultsForExam returned ${examResults.length} result(s)`);
      passCount++;
    } else {
      throw new Error('fetchResultsForExam returned no results');
    }

    const byId = await fetchResultById(finalizedResult._id.toString());
    if (byId && byId.totalMarks === 90) {
      console.log('✓ fetchResultById retrieved valid populated result');
      passCount++;
    } else {
      throw new Error('fetchResultById failed');
    }

    console.log('\n===============================================================');
    console.log(`TEST SUITE PASSED! (${passCount}/10 checks passed)`);
    console.log('===============================================================');
  } catch (err: any) {
    console.error('\n❌ Test Suite Failed with error:', err.message);
    process.exit(1);
  } finally {
    // Cleanup test data
    if (testExam) await Exam.findByIdAndDelete(testExam._id);
    if (testBook) await AnswerBook.findByIdAndDelete(testBook._id);
    if (testEval) await Evaluation.findByIdAndDelete(testEval._id);
    if (testBook) await Result.deleteMany({ answerBookId: testBook._id });
    if (testExam) await Question.deleteMany({ examId: testExam._id });
    await mongoose.disconnect();
    console.log('\nDisconnected from MongoDB. Cleanup completed.');
  }
}

runResultTests();
