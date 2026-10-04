import mongoose from 'mongoose';
import dotenv from 'dotenv';
import path from 'path';
import { Evaluation } from '../models/Evaluation';
import { AnswerBook } from '../models/AnswerBook';
import { Exam } from '../models/Exam';
import { Question } from '../models/Question';
import { User } from '../models/User';
import { AnswerPage } from '../models/AnswerPage';
import { fetchIntegrityChecks } from '../services/moderation.service';

dotenv.config({ path: path.resolve(__dirname, '../../.env') });

async function runIntegritySurveillanceTests() {
  console.log('===============================================================');
  console.log('EVALNEXA INTEGRITY SURVEILLANCE & ANOMALY DETECTION TEST SUITE');
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
  let testPage: any = null;

  try {
    // Setup test examiner, moderator, and exam
    testExaminer = await User.findOne({ role: 'EXAMINER' });
    if (!testExaminer) {
      testExaminer = await User.create({
        name: 'Test Examiner Surveillance',
        email: `examiner_surv_${Date.now()}@evalnexa.test`,
        passwordHash: 'dummyhash',
        role: 'EXAMINER',
      });
    }

    testModerator = await User.findOne({ role: 'MODERATOR' });
    if (!testModerator) {
      testModerator = await User.create({
        name: 'Test Moderator Surveillance',
        email: `moderator_surv_${Date.now()}@evalnexa.test`,
        passwordHash: 'dummyhash',
        role: 'MODERATOR',
      });
    }

    testExam = await Exam.create({
      title: 'Information Security & Cryptography Exam',
      subjectCode: `SEC-SURV-${Date.now().toString().slice(-4)}`,
      subjectName: 'Information Security',
      academicSession: '2025-2026',
      totalQuestions: 2,
      maximumMarks: 100,
      createdBy: testModerator._id,
    });

    await Question.create({
      examId: testExam._id,
      questionNumber: 1,
      text: 'Explain RSA key generation algorithm.',
      maximumMarks: 40,
      rubric: [{ criterion: 'Mathematical correctness', marks: 40 }],
    });

    await Question.create({
      examId: testExam._id,
      questionNumber: 2,
      text: 'Analyze Elliptic Curve Diffie-Hellman protocol.',
      maximumMarks: 60,
      rubric: [{ criterion: 'Curve parameters & exchange', marks: 60 }],
    });

    testBook = await AnswerBook.create({
      examId: testExam._id,
      answerBookCode: `SCRIPT-SURV-${Date.now()}`,
      studentCode: `STU-SURV-${Date.now().toString().slice(-4)}`,
      pageCount: 4,
      status: 'SUBMITTED',
      qualityStatus: 'VERIFIED',
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

    // -------------------------------------------------------------------------
    // Test 1: Baseline Clean Evaluation produces 0 issues for this docket
    // -------------------------------------------------------------------------
    console.log('Test 1: Testing baseline clean docket detection...');
    let issues = await fetchIntegrityChecks();
    const docketIssues = issues.filter((i) => i.answerBookCode === testBook.answerBookCode);
    if (docketIssues.length === 0) {
      console.log('✓ Clean docket correctly verified with 0 integrity issues');
      passCount++;
    } else {
      throw new Error(`Expected 0 issues for clean docket, found: ${JSON.stringify(docketIssues)}`);
    }

    // -------------------------------------------------------------------------
    // Test 2: Rubric Limit Exceeded Anomaly
    // -------------------------------------------------------------------------
    console.log('\nTest 2: Testing Rubric Limit Exceeded detection (Q1 rubric max = 40, marks = 45)...');
    testEval.questionMarks = [
      { questionNumber: 1, marks: 45, status: 'MARKED' }, // Rubric max is 40
      { questionNumber: 2, marks: 45, status: 'MARKED' },
    ];
    testEval.totalMarks = 90;
    await testEval.save();

    issues = await fetchIntegrityChecks();
    const rubricIssue = issues.find(
      (i) => i.answerBookCode === testBook.answerBookCode && i.ruleName === 'Question Mark Exceeds Rubric Limit'
    );
    if (rubricIssue && rubricIssue.severity === 'HIGH' && rubricIssue.evaluationId === testEval._id.toString()) {
      console.log(`✓ Detected Rubric Limit Exceeded: ${rubricIssue.description}`);
      passCount++;
    } else {
      throw new Error(`Failed to detect Rubric Limit Exceeded: ${JSON.stringify(issues)}`);
    }

    // -------------------------------------------------------------------------
    // Test 3: Unattempted Question Awarded Marks
    // -------------------------------------------------------------------------
    console.log('\nTest 3: Testing Unattempted Question Awarded Marks detection...');
    testEval.questionMarks = [
      { questionNumber: 1, marks: 35, status: 'MARKED' },
      { questionNumber: 2, marks: 20, status: 'NOT_ATTEMPTED' }, // NOT_ATTEMPTED with marks!
    ];
    testEval.totalMarks = 55;
    await testEval.save();

    issues = await fetchIntegrityChecks();
    const unattemptedIssue = issues.find(
      (i) => i.answerBookCode === testBook.answerBookCode && i.ruleName === 'Unattempted Question Awarded Marks'
    );
    if (unattemptedIssue && unattemptedIssue.severity === 'HIGH') {
      console.log(`✓ Detected Unattempted Question Awarded Marks: ${unattemptedIssue.description}`);
      passCount++;
    } else {
      throw new Error(`Failed to detect Unattempted Question Awarded Marks: ${JSON.stringify(issues)}`);
    }

    // -------------------------------------------------------------------------
    // Test 4: Rescan Required Pending Evaluation Anomaly
    // -------------------------------------------------------------------------
    console.log('\nTest 4: Testing Rescan Required Pending Evaluation detection...');
    testBook.qualityStatus = 'RESCAN_REQUIRED';
    await testBook.save();

    testEval.questionMarks = [
      { questionNumber: 1, marks: 35, status: 'MARKED' },
      { questionNumber: 2, marks: 55, status: 'MARKED' },
    ];
    testEval.totalMarks = 90;
    await testEval.save();

    issues = await fetchIntegrityChecks();
    const rescanIssue = issues.find(
      (i) => i.answerBookCode === testBook.answerBookCode && i.ruleName === 'Rescan Required Pending Evaluation'
    );
    if (rescanIssue && rescanIssue.severity === 'HIGH') {
      console.log(`✓ Detected Rescan Required Pending Evaluation: ${rescanIssue.description}`);
      passCount++;
    } else {
      throw new Error(`Failed to detect Rescan Required: ${JSON.stringify(issues)}`);
    }

    // Reset qualityStatus
    testBook.qualityStatus = 'VERIFIED';
    await testBook.save();

    // -------------------------------------------------------------------------
    // Test 5: Custody State Desynchronization Anomaly
    // -------------------------------------------------------------------------
    console.log('\nTest 5: Testing Custody State Desynchronization detection...');
    testEval.status = 'APPROVED';
    testBook.status = 'RETURNED'; // Out of sync!
    await testEval.save();
    await testBook.save();

    issues = await fetchIntegrityChecks();
    const desyncIssue = issues.find(
      (i) => i.answerBookCode === testBook.answerBookCode && i.ruleName === 'Custody State Desynchronization'
    );
    if (desyncIssue && desyncIssue.severity === 'HIGH') {
      console.log(`✓ Detected Custody State Desynchronization: ${desyncIssue.description}`);
      passCount++;
    } else {
      throw new Error(`Failed to detect Custody State Desynchronization: ${JSON.stringify(issues)}`);
    }

    // Reset status
    testEval.status = 'SUBMITTED';
    testBook.status = 'SUBMITTED';
    await testEval.save();
    await testBook.save();

    // -------------------------------------------------------------------------
    // Test 6: Scanned Page Ingestion Defect Anomaly
    // -------------------------------------------------------------------------
    console.log('\nTest 6: Testing Scanned Page Ingestion Defect detection...');
    testPage = await AnswerPage.create({
      answerBookId: testBook._id,
      pageNumber: 3,
      cloudinary: {
        publicId: `test_page_${Date.now()}`,
        resourceType: 'image',
      },
      quality: {
        status: 'RESCAN_REQUIRED',
        score: 45,
      },
      processingStatus: 'COMPLETED',
      finalized: false,
    });

    issues = await fetchIntegrityChecks();
    const pageIssue = issues.find(
      (i) => i.answerBookCode === testBook.answerBookCode && i.ruleName === 'Scanned Page Ingestion Defect'
    );
    if (pageIssue && pageIssue.severity === 'MEDIUM') {
      console.log(`✓ Detected Scanned Page Ingestion Defect: ${pageIssue.description}`);
      passCount++;
    } else {
      throw new Error(`Failed to detect Scanned Page Ingestion Defect: ${JSON.stringify(issues)}`);
    }

    // -------------------------------------------------------------------------
    // Test 7: Verify Diagnostic Description and Navigation References
    // -------------------------------------------------------------------------
    console.log('\nTest 7: Verifying all issues include evaluationId or answerBookId for navigation...');
    const allHaveReferences = issues
      .filter((i) => i.answerBookCode === testBook.answerBookCode)
      .every((i) => Boolean(i.evaluationId || i.answerBookId));
    if (allHaveReferences) {
      console.log('✓ All detected anomalies include evaluationId or answerBookId for direct navigation');
      passCount++;
    } else {
      throw new Error('Some anomalies missing navigation references');
    }

    console.log('\n===============================================================');
    console.log(`ALL ${passCount} INTEGRITY SURVEILLANCE TESTS PASSED SUCCESSFULLY!`);
    console.log('===============================================================\n');
  } catch (error: any) {
    console.error('\n❌ Test Suite Failed:', error.message);
    process.exit(1);
  } finally {
    // Cleanup created test records
    try {
      if (testPage) await AnswerPage.findByIdAndDelete(testPage._id);
      if (testEval) await Evaluation.findByIdAndDelete(testEval._id);
      if (testBook) await AnswerBook.findByIdAndDelete(testBook._id);
      if (testExam) {
        await Question.deleteMany({ examId: testExam._id });
        await Exam.findByIdAndDelete(testExam._id);
      }
      await mongoose.disconnect();
      console.log('Cleaned up test fixtures and disconnected from MongoDB.');
    } catch (cleanupErr: any) {
      console.error('Cleanup error:', cleanupErr.message);
    }
  }
}

runIntegritySurveillanceTests();
