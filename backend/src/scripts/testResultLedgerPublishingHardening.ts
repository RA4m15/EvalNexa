import mongoose from 'mongoose';
import dotenv from 'dotenv';
import path from 'path';
import { Result } from '../models/Result';
import { Evaluation } from '../models/Evaluation';
import { AnswerBook } from '../models/AnswerBook';
import { Exam } from '../models/Exam';
import { Question } from '../models/Question';
import { User } from '../models/User';
import { AuditLog } from '../models/AuditLog';
import {
  calculateGradeAndClassification,
  finalizeEvaluationResult,
  publishResult,
  publishResultsForExam,
  withholdResult,
  releaseWithheldResult,
  batchFinalizeApprovedEvaluations,
  fetchResults,
} from '../services/results.service';

dotenv.config({ path: path.resolve(__dirname, '../../.env') });

async function runHardeningTests() {
  console.log('========================================================================');
  console.log('EVALNEXA RESULT FINALIZATION, GRADING & LEDGER PUBLISHING TEST SUITE');
  console.log('========================================================================\n');

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
  let testAdmin: any = null;
  let testExaminer: any = null;
  let testExam: any = null;
  const createdBooks: any[] = [];
  const createdEvals: any[] = [];

  try {
    // -------------------------------------------------------------------------
    // Test 1: Pure Grading & Classification Helper Boundaries
    // -------------------------------------------------------------------------
    console.log('Test 1: Testing deterministic grading scale across boundary conditions...');
    const gradeCases = [
      { pct: 95, expGrade: 'A+', expGP: 10, expClass: 'FIRST_CLASS_DISTINCTION' },
      { pct: 90, expGrade: 'A+', expGP: 10, expClass: 'FIRST_CLASS_DISTINCTION' },
      { pct: 85, expGrade: 'A', expGP: 9, expClass: 'FIRST_CLASS_DISTINCTION' },
      { pct: 80, expGrade: 'A', expGP: 9, expClass: 'FIRST_CLASS_DISTINCTION' },
      { pct: 75, expGrade: 'B+', expGP: 8, expClass: 'FIRST_CLASS' },
      { pct: 70, expGrade: 'B+', expGP: 8, expClass: 'FIRST_CLASS' },
      { pct: 65, expGrade: 'B', expGP: 7, expClass: 'HIGHER_SECOND_CLASS' },
      { pct: 60, expGrade: 'B', expGP: 7, expClass: 'HIGHER_SECOND_CLASS' },
      { pct: 55, expGrade: 'C', expGP: 6, expClass: 'SECOND_CLASS' },
      { pct: 50, expGrade: 'C', expGP: 6, expClass: 'SECOND_CLASS' },
      { pct: 45, expGrade: 'P', expGP: 4, expClass: 'PASS' },
      { pct: 40, expGrade: 'P', expGP: 4, expClass: 'PASS' },
      { pct: 39.9, expGrade: 'F', expGP: 0, expClass: 'FAIL' },
      { pct: 0, expGrade: 'F', expGP: 0, expClass: 'FAIL' },
    ];

    for (const c of gradeCases) {
      const res = calculateGradeAndClassification(c.pct);
      if (res.grade !== c.expGrade || res.gradePoint !== c.expGP || res.classification !== c.expClass) {
        throw new Error(
          `Grading helper failed for ${c.pct}%: expected ${c.expGrade}/${c.expGP}/${c.expClass}, got ${res.grade}/${res.gradePoint}/${res.classification}`
        );
      }
    }
    console.log(`✓ All ${gradeCases.length} grading boundary tests validated successfully.`);
    passCount++;

    // Setup actors and test exam
    testExaminer = await User.findOne({ role: 'EXAMINER' });
    if (!testExaminer) {
      testExaminer = await User.create({
        name: 'Institutional Examiner',
        email: `examiner_${Date.now()}@evalnexa.test`,
        passwordHash: 'dummyhash',
        role: 'EXAMINER',
      });
    }

    testAdmin = await User.findOne({ role: 'ADMIN' });
    if (!testAdmin) {
      testAdmin = await User.create({
        name: 'Certification Officer',
        email: `certifier_${Date.now()}@evalnexa.test`,
        passwordHash: 'dummyhash',
        role: 'ADMIN',
      });
    }

    testExam = await Exam.create({
      title: 'Grading & Publishing Workflow Verification Exam',
      subjectCode: `PUB-${Date.now().toString().slice(-4)}`,
      subjectName: 'Institutional Examination Ledger',
      academicSession: '2026-AUTUMN',
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
      text: 'Part A Analysis',
      maximumMarks: 50,
      rubric: [{ criterion: 'Depth of analysis', marks: 50 }],
    });

    await Question.create({
      examId: testExam._id,
      questionNumber: 2,
      text: 'Part B Synthesis',
      maximumMarks: 50,
      rubric: [{ criterion: 'System synthesis', marks: 50 }],
    });

    // -------------------------------------------------------------------------
    // Test 2: Finalize Evaluation and Validate Grade & Classification Storage
    // -------------------------------------------------------------------------
    console.log('\nTest 2: Finalizing evaluation and asserting stored Grade & Classification...');
    const book1 = await AnswerBook.create({
      examId: testExam._id,
      answerBookCode: `SCRIPT-PUB-1-${Date.now()}`,
      studentCode: `STU-PUB-001`,
      pageCount: 6,
      status: 'APPROVED',
    });
    createdBooks.push(book1);

    const eval1 = await Evaluation.create({
      answerBookId: book1._id,
      examinerId: testExaminer._id,
      status: 'APPROVED',
      questionMarks: [
        { questionNumber: 1, marks: 44, status: 'MARKED' },
        { questionNumber: 2, marks: 42, status: 'MARKED' },
      ],
      totalMarks: 86, // 86% -> Grade 'A', gradePoint 9, 'FIRST_CLASS_DISTINCTION'
    });
    createdEvals.push(eval1);

    const finalizedResult = await finalizeEvaluationResult(
      eval1._id.toString(),
      testAdmin._id.toString(),
      { name: testAdmin.name, role: testAdmin.role }
    );

    if (
      finalizedResult.status === 'FINALIZED' &&
      finalizedResult.totalMarks === 86 &&
      finalizedResult.percentage === 86 &&
      finalizedResult.grade === 'A' &&
      finalizedResult.gradePoint === 9 &&
      finalizedResult.classification === 'FIRST_CLASS_DISTINCTION'
    ) {
      console.log('✓ Result finalized with grade: "A", points: 9, classification: "FIRST_CLASS_DISTINCTION"');
      passCount++;
    } else {
      throw new Error(`Finalized result has unexpected grading data: ${JSON.stringify(finalizedResult)}`);
    }

    // Verify AuditLog for RESULT_FINALIZED contains grade metadata
    const finalAudit = await AuditLog.findOne({
      entityId: finalizedResult._id.toString(),
      action: 'RESULT_FINALIZED',
    });
    if (finalAudit && (finalAudit.metadata as any)?.grade === 'A') {
      console.log('✓ RESULT_FINALIZED AuditLog verified with immutable grading metadata');
      passCount++;
    } else {
      throw new Error('AuditLog for RESULT_FINALIZED missing or lacks grade metadata');
    }

    // -------------------------------------------------------------------------
    // Test 3: Publish Single Result to Institutional Ledger
    // -------------------------------------------------------------------------
    console.log('\nTest 3: Publishing finalized Result to institutional ledger...');
    const publishedResult = await publishResult(
      finalizedResult._id.toString(),
      testAdmin._id.toString(),
      { name: testAdmin.name, role: testAdmin.role }
    );

    if (
      publishedResult.status === 'PUBLISHED' &&
      publishedResult.publishedAt !== undefined &&
      publishedResult.publishedBy !== undefined
    ) {
      console.log('✓ Result status transitioned to PUBLISHED with valid publishedAt and publishedBy timestamps');
      passCount++;
    } else {
      throw new Error(`Publish failed: ${JSON.stringify(publishedResult)}`);
    }

    // Verify RESULT_PUBLISHED AuditLog
    const pubAudit = await AuditLog.findOne({
      entityId: finalizedResult._id.toString(),
      action: 'RESULT_PUBLISHED',
    });
    if (pubAudit) {
      console.log('✓ RESULT_PUBLISHED AuditLog verified');
      passCount++;
    } else {
      throw new Error('RESULT_PUBLISHED AuditLog missing');
    }

    // -------------------------------------------------------------------------
    // Test 4: Withhold Result with Rationale
    // -------------------------------------------------------------------------
    console.log('\nTest 4: Testing withholding workflow with mandatory reason check...');
    try {
      await withholdResult(finalizedResult._id.toString(), '', testAdmin._id.toString());
      throw new Error('FAILED: Withhold should require a non-empty reason');
    } catch (err: any) {
      if (err.code === 'MISSING_WITHHOLD_REASON' && err.status === 400) {
        console.log('✓ Correctly rejected empty withhold reason with 400 MISSING_WITHHOLD_REASON');
        passCount++;
      } else {
        throw new Error(`Unexpected withhold error: ${err.message}`);
      }
    }

    const withheldReason = 'Suspected administrative integrity audit on script barcode mismatch';
    const withheldResult = await withholdResult(
      finalizedResult._id.toString(),
      withheldReason,
      testAdmin._id.toString(),
      { name: testAdmin.name, role: testAdmin.role }
    );

    if (
      withheldResult.status === 'WITHHELD' &&
      withheldResult.withheldReason === withheldReason
    ) {
      console.log(`✓ Result transitioned to WITHHELD with reason: "${withheldReason}"`);
      passCount++;
    } else {
      throw new Error(`Withhold failed: ${JSON.stringify(withheldResult)}`);
    }

    // -------------------------------------------------------------------------
    // Test 5: Release Withheld Result Back to Published Status
    // -------------------------------------------------------------------------
    console.log('\nTest 5: Releasing withheld Result back to PUBLISHED status...');
    const releasedResult = await releaseWithheldResult(
      finalizedResult._id.toString(),
      testAdmin._id.toString(),
      { name: testAdmin.name, role: testAdmin.role }
    );

    if (
      releasedResult.status === 'PUBLISHED' &&
      releasedResult.withheldReason === undefined
    ) {
      console.log('✓ Result restored to PUBLISHED status and withheldReason cleared');
      passCount++;
    } else {
      throw new Error(`Release failed: ${JSON.stringify(releasedResult)}`);
    }

    // -------------------------------------------------------------------------
    // Test 6: Batch Finalize Approved Evaluations for an Exam
    // -------------------------------------------------------------------------
    console.log('\nTest 6: Testing batch finalization of multiple approved evaluations...');
    // Create 2 additional approved scripts and evaluations
    const book2 = await AnswerBook.create({
      examId: testExam._id,
      answerBookCode: `SCRIPT-PUB-2-${Date.now()}`,
      studentCode: `STU-PUB-002`,
      pageCount: 8,
      status: 'APPROVED',
    });
    createdBooks.push(book2);

    const eval2 = await Evaluation.create({
      answerBookId: book2._id,
      examinerId: testExaminer._id,
      status: 'APPROVED',
      questionMarks: [
        { questionNumber: 1, marks: 36, status: 'MARKED' },
        { questionNumber: 2, marks: 38, status: 'MARKED' },
      ],
      totalMarks: 74, // 74% -> Grade 'B+', gradePoint 8
    });
    createdEvals.push(eval2);

    const book3 = await AnswerBook.create({
      examId: testExam._id,
      answerBookCode: `SCRIPT-PUB-3-${Date.now()}`,
      studentCode: `STU-PUB-003`,
      pageCount: 10,
      status: 'APPROVED',
    });
    createdBooks.push(book3);

    const eval3 = await Evaluation.create({
      answerBookId: book3._id,
      examinerId: testExaminer._id,
      status: 'APPROVED',
      questionMarks: [
        { questionNumber: 1, marks: 46, status: 'MARKED' },
        { questionNumber: 2, marks: 48, status: 'MARKED' },
      ],
      totalMarks: 94, // 94% -> Grade 'A+', gradePoint 10
    });
    createdEvals.push(eval3);

    const batchRes = await batchFinalizeApprovedEvaluations(
      testExam._id.toString(),
      testAdmin._id.toString(),
      { name: testAdmin.name, role: testAdmin.role }
    );

    if (batchRes.success && batchRes.finalizedCount === 2 && batchRes.errors.length === 0) {
      console.log(`✓ Batch finalization successful: ${batchRes.finalizedCount} approved scripts finalized.`);
      passCount++;
    } else {
      throw new Error(`Batch finalization failed: ${JSON.stringify(batchRes)}`);
    }

    // Verify books are transitioned to FINALIZED
    const updatedBook2 = await AnswerBook.findById(book2._id);
    const updatedBook3 = await AnswerBook.findById(book3._id);
    if (updatedBook2?.status === 'FINALIZED' && updatedBook3?.status === 'FINALIZED') {
      console.log('✓ All batch-finalized AnswerBooks transitioned to FINALIZED');
      passCount++;
    } else {
      throw new Error('Batch-finalized AnswerBooks did not transition to FINALIZED');
    }

    // -------------------------------------------------------------------------
    // Test 7: Batch Publish Exam Results
    // -------------------------------------------------------------------------
    console.log('\nTest 7: Testing batch publication of all finalized results for an exam...');
    const publishExamRes = await publishResultsForExam(
      testExam._id.toString(),
      testAdmin._id.toString(),
      { name: testAdmin.name, role: testAdmin.role }
    );

    if (publishExamRes.success && publishExamRes.publishedCount === 2) {
      console.log(`✓ Successfully batch-published ${publishExamRes.publishedCount} results for exam`);
      passCount++;
    } else {
      throw new Error(`Batch publish exam failed: ${JSON.stringify(publishExamRes)}`);
    }

    // Verify in MongoDB that all 3 results for this exam are now PUBLISHED
    const examResults = await fetchResults({ examId: testExam._id.toString(), status: 'PUBLISHED' });
    if (examResults.length === 3) {
      console.log(`✓ Confirmed in database: all 3 exam results are PUBLISHED with grades and classifications`);
      passCount++;
    } else {
      throw new Error(`Expected 3 published results, found ${examResults.length}`);
    }

    console.log('\n========================================================================');
    console.log(`ALL TESTS PASSED! (${passCount}/12 checks passed)`);
    console.log('========================================================================');
  } catch (err: any) {
    console.error('\n❌ Test Suite Failed with error:', err.message);
    process.exit(1);
  } finally {
    // Cleanup test data
    if (testExam) await Exam.findByIdAndDelete(testExam._id);
    if (testExam) await Question.deleteMany({ examId: testExam._id });
    for (const b of createdBooks) {
      await AnswerBook.findByIdAndDelete(b._id);
      await Result.deleteMany({ answerBookId: b._id });
    }
    for (const ev of createdEvals) {
      await Evaluation.findByIdAndDelete(ev._id);
    }
    await mongoose.disconnect();
    console.log('\nDisconnected from MongoDB. Cleanup completed.');
  }
}

runHardeningTests();
