import mongoose from 'mongoose';
import dotenv from 'dotenv';
import path from 'path';
import { Evaluation } from '../models/Evaluation';
import { AnswerBook } from '../models/AnswerBook';
import { AnswerPage } from '../models/AnswerPage';
import { Exam } from '../models/Exam';
import { Question } from '../models/Question';
import { User } from '../models/User';
import { AuditLog } from '../models/AuditLog';
import { requestAISuggestionForQuestion } from '../services/evaluations.service';

dotenv.config({ path: path.resolve(__dirname, '../../.env') });

async function runAIIntegrationTests() {
  console.log('===============================================================');
  console.log('EVALNEXA EVALUATION AI-SUGGEST INTEGRATION TEST SUITE');
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
  let testExaminer1: any = null;
  let testExaminer2: any = null;
  let testAdmin: any = null;
  let testBook: any = null;
  let testPage: any = null;
  let testEval: any = null;
  let testQ1: any = null;

  try {
    // 1. Setup users
    testExaminer1 = await User.create({
      name: 'Assigned Examiner',
      email: `assigned_${Date.now()}@evalnexa.test`,
      passwordHash: 'dummyhash',
      role: 'EXAMINER',
    });

    testExaminer2 = await User.create({
      name: 'Unauthorized Examiner',
      email: `unauthorized_${Date.now()}@evalnexa.test`,
      passwordHash: 'dummyhash',
      role: 'EXAMINER',
    });

    testAdmin = await User.create({
      name: 'Administrator',
      email: `admin_${Date.now()}@evalnexa.test`,
      passwordHash: 'dummyhash',
      role: 'ADMIN',
    });

    // 2. Setup Exam & Question with Rubric & AI fields
    testExam = await Exam.create({
      title: 'AI Copilot Integration Test Exam',
      subjectCode: `AI-${Date.now().toString().slice(-4)}`,
      subjectName: 'Artificial Intelligence Evaluation',
      academicSession: '2026-TEST',
      maximumMarks: 20,
      passingMarks: 8,
      totalQuestions: 1,
      durationMinutes: 60,
      status: 'EVALUATION_OPEN',
      createdBy: testAdmin._id,
    });

    testQ1 = await Question.create({
      examId: testExam._id,
      questionNumber: 1,
      text: 'Explain Virtual Memory and Demand Paging.',
      maximumMarks: 20,
      rubric: [
        { criterion: 'Virtual Memory Concept & Address Space', marks: 8 },
        { criterion: 'Demand Paging & Page Fault Handling', marks: 12 },
      ],
      referenceAnswer:
        'Virtual memory provides an illusion of a large memory space by combining RAM and disk storage. Demand paging loads pages only when referenced.',
      keyConcepts: ['Address Translation', 'Page Table', 'Page Fault', 'Swap Space'],
      gradingNotes: 'Accept diagrams or clear step-by-step page fault flow.',
    });

    // 3. Setup AnswerBook & Page
    testBook = await AnswerBook.create({
      examId: testExam._id,
      answerBookCode: `SCRIPT-AI-${Date.now()}`,
      studentCode: `STU-AI-${Date.now().toString().slice(-4)}`,
      pageCount: 1,
      status: 'IN_PROGRESS',
      assignedExaminerId: testExaminer1._id,
    });

    testPage = await AnswerPage.create({
      answerBookId: testBook._id,
      pageNumber: 1,
      cloudinary: {
        publicId: `evalnexa/exams/${testExam._id}/answer-books/${testBook._id}/pages/page-0001`,
        resourceType: 'image',
        deliveryType: 'upload',
        format: 'jpg',
      },
      ocr: {
        text: 'Virtual memory separates user logical memory from physical memory. Demand paging brings execution pages into memory only when demanded. When an unmapped page is accessed, a page fault trap occurs.',
        confidence: 0.94,
        language: 'en',
      },
      processingStatus: 'COMPLETED',
    });

    // 4. Setup Evaluation
    testEval = await Evaluation.create({
      answerBookId: testBook._id,
      examinerId: testExaminer1._id,
      status: 'IN_PROGRESS',
      questionMarks: [
        {
          questionNumber: 1,
          marks: 0,
          status: 'NOT_STARTED',
        },
      ],
      totalMarks: 0,
    });

    // -------------------------------------------------------------------------
    // Test 1: Reject unauthorized examiner access
    // -------------------------------------------------------------------------
    console.log('Test 1: Testing unauthorized examiner access rejection...');
    try {
      await requestAISuggestionForQuestion(testEval._id.toString(), 1, {
        userRole: 'EXAMINER',
        userId: testExaminer2._id.toString(),
        userName: testExaminer2.name,
      });
      throw new Error('FAILED: Unauthorized examiner should have been rejected');
    } catch (err: any) {
      if (err.code === 'UNAUTHORIZED_EXAMINER_ACCESS' && err.status === 403) {
        console.log('✓ Successfully rejected unauthorized examiner with 403 UNAUTHORIZED_EXAMINER_ACCESS');
        passCount++;
      } else {
        throw err;
      }
    }

    // -------------------------------------------------------------------------
    // Test 2: Generate AI Suggestion by Assigned Examiner
    // -------------------------------------------------------------------------
    console.log('\nTest 2: Requesting AI evaluation suggestion by assigned examiner...');
    const result1 = await requestAISuggestionForQuestion(testEval._id.toString(), 1, {
      userRole: 'EXAMINER',
      userId: testExaminer1._id.toString(),
      userName: testExaminer1.name,
    });

    if (result1 && result1.aiAnalysis && result1.cached === false) {
      console.log('✓ AI suggestion successfully generated:');
      console.log(`  - Suggested Marks: ${result1.aiAnalysis.suggestedMarks}/${testQ1.maximumMarks}`);
      console.log(`  - Confidence: ${result1.aiAnalysis.confidence}`);
      console.log(`  - Needs Human Review: ${result1.aiAnalysis.needsHumanReview}`);
      console.log(`  - Criteria Count: ${result1.aiAnalysis.criteria.length}`);
      console.log(`  - Model: ${result1.aiAnalysis.model}`);
      console.log(`  - Generated At: ${result1.aiAnalysis.generatedAt}`);
      passCount++;
    } else {
      throw new Error(`Unexpected result: ${JSON.stringify(result1)}`);
    }

    // -------------------------------------------------------------------------
    // Test 3: Verify AI analysis is stored in evaluation model without altering examiner marks
    // -------------------------------------------------------------------------
    console.log('\nTest 3: Verifying AI analysis storage and independence from final examiner marks...');
    const updatedEval = await Evaluation.findById(testEval._id);
    const qm1 = updatedEval?.questionMarks.find((q) => q.questionNumber === 1);

    if (!qm1 || !qm1.aiAnalysis) {
      throw new Error('aiAnalysis was not saved into questionMarks');
    }

    if (qm1.marks === 0 && qm1.status === 'NOT_STARTED') {
      console.log('✓ Examiner marks remain independent: marks = 0, status = NOT_STARTED');
      passCount++;
    } else {
      throw new Error(`Examiner marks were tampered: marks=${qm1.marks}, status=${qm1.status}`);
    }

    if (updatedEval?.totalMarks === 0) {
      console.log('✓ Evaluation totalMarks untouched by AI suggestion (remains 0)');
      passCount++;
    } else {
      throw new Error(`Evaluation totalMarks was altered by AI: ${updatedEval?.totalMarks}`);
    }

    // -------------------------------------------------------------------------
    // Test 4: Repeated requests handle efficiently without duplicate AI generation (Caching)
    // -------------------------------------------------------------------------
    console.log('\nTest 4: Testing efficient handling of repeated requests (caching)...');
    const result2 = await requestAISuggestionForQuestion(testEval._id.toString(), 1, {
      userRole: 'EXAMINER',
      userId: testExaminer1._id.toString(),
      userName: testExaminer1.name,
      forceRefresh: false,
    });

    if (result2.cached === true && result2.aiAnalysis.model === result1.aiAnalysis.model) {
      console.log('✓ Repeated request returned cached analysis immediately (cached: true)');
      passCount++;
    } else {
      throw new Error(`Expected cached: true, got: ${JSON.stringify(result2)}`);
    }

    // -------------------------------------------------------------------------
    // Test 5: Forced re-evaluation generates fresh analysis
    // -------------------------------------------------------------------------
    console.log('\nTest 5: Testing forced refresh (forceRefresh: true)...');
    const result3 = await requestAISuggestionForQuestion(testEval._id.toString(), 1, {
      userRole: 'EXAMINER',
      userId: testExaminer1._id.toString(),
      userName: testExaminer1.name,
      forceRefresh: true,
    });

    if (result3.cached === false) {
      console.log('✓ Forced refresh re-executed assistant successfully (cached: false)');
      passCount++;
    } else {
      throw new Error(`Expected cached: false on forceRefresh, got: ${JSON.stringify(result3)}`);
    }

    // -------------------------------------------------------------------------
    // Test 6: Verify AuditLog entry for AI evaluation
    // -------------------------------------------------------------------------
    console.log('\nTest 6: Verifying audit log creation for AI assistance...');
    const auditEntries = await AuditLog.find({
      entityId: testEval._id.toString(),
      action: 'EVALUATION_AI_ASSISTED',
    });

    if (auditEntries.length >= 1) {
      const entry = auditEntries[0];
      console.log(`✓ Audit log verified: action = ${entry.action}, model = ${(entry.metadata as any)?.model}`);
      passCount++;
    } else {
      throw new Error('Audit log for EVALUATION_AI_ASSISTED not found');
    }

    // -------------------------------------------------------------------------
    // Test 7: Privileged role (ADMIN) can request suggestion
    // -------------------------------------------------------------------------
    console.log('\nTest 7: Testing privileged role access (ADMIN)...');
    const adminResult = await requestAISuggestionForQuestion(testEval._id.toString(), 1, {
      userRole: 'ADMIN',
      userId: testAdmin._id.toString(),
      userName: testAdmin.name,
    });

    if (adminResult && adminResult.aiAnalysis) {
      console.log('✓ Administrator successfully accessed AI evaluation suggestion');
      passCount++;
    } else {
      throw new Error('Administrator request failed');
    }

    console.log('\n===============================================================');
    console.log(`ALL ${passCount} INTEGRATION TESTS PASSED SUCCESSFULLY!`);
    console.log('===============================================================');
  } catch (err: any) {
    console.error('\n❌ Integration Test Failed:', err.message);
    process.exit(1);
  } finally {
    // Cleanup
    if (testExam) await Exam.findByIdAndDelete(testExam._id);
    if (testQ1) await Question.findByIdAndDelete(testQ1._id);
    if (testBook) await AnswerBook.findByIdAndDelete(testBook._id);
    if (testPage) await AnswerPage.findByIdAndDelete(testPage._id);
    if (testEval) await Evaluation.findByIdAndDelete(testEval._id);
    if (testExaminer1) await User.findByIdAndDelete(testExaminer1._id);
    if (testExaminer2) await User.findByIdAndDelete(testExaminer2._id);
    if (testAdmin) await User.findByIdAndDelete(testAdmin._id);
    if (testEval) await AuditLog.deleteMany({ entityId: testEval._id.toString() });
    await mongoose.disconnect();
    console.log('\nDisconnected from MongoDB. Cleanup completed.');
  }
}

runAIIntegrationTests();
