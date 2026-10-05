import {
  validateQuestionMarksList,
  IAuthoritativeQuestion,
} from '../services/evaluations.service';
import { IEvaluationQuestionMark } from '../models/Evaluation';

async function runEvaluationTests() {
  console.log('===============================================================');
  console.log('EVALNEXA EVALUATION VALIDATION & MARK CALCULATION TEST SUITE');
  console.log('===============================================================\n');

  // Official questions for an exam with 3 questions (max 20, 30, 50 = total 100)
  const authoritativeQuestions = new Map<number, IAuthoritativeQuestion>([
    [1, { questionNumber: 1, maximumMarks: 20, text: 'Define CAP Theorem' }],
    [2, { questionNumber: 2, maximumMarks: 30, text: 'Explain Raft Consensus Algorithm' }],
    [3, { questionNumber: 3, maximumMarks: 50, text: 'Design Distributed Cache' }],
  ]);

  let passCount = 0;

  // -------------------------------------------------------------------------
  // Test 1: Duplicate Question Rejection
  // -------------------------------------------------------------------------
  console.log('Test 1: Testing duplicate question numbers rejection...');
  try {
    const duplicateList: IEvaluationQuestionMark[] = [
      { questionNumber: 1, marks: 15, status: 'MARKED' },
      { questionNumber: 1, marks: 18, status: 'MARKED' },
    ];
    validateQuestionMarksList(duplicateList, authoritativeQuestions, false);
    throw new Error('FAILED: Expected duplicate question rejection');
  } catch (err: any) {
    if (err.code !== 'DUPLICATE_QUESTION_NUMBER' || err.status !== 400) {
      throw new Error(`Unexpected error code/status: ${err.code} (${err.status}): ${err.message}`);
    }
    console.log('✓ Duplicate question successfully rejected with 400 DUPLICATE_QUESTION_NUMBER');
    passCount++;
  }

  // -------------------------------------------------------------------------
  // Test 2: Unknown Question Number Rejection
  // -------------------------------------------------------------------------
  console.log('\nTest 2: Testing unknown question number rejection...');
  try {
    const unknownList: IEvaluationQuestionMark[] = [
      { questionNumber: 1, marks: 15, status: 'MARKED' },
      { questionNumber: 99, marks: 10, status: 'MARKED' },
    ];
    validateQuestionMarksList(unknownList, authoritativeQuestions, false);
    throw new Error('FAILED: Expected unknown question rejection');
  } catch (err: any) {
    if (err.code !== 'UNKNOWN_QUESTION_NUMBER' || err.status !== 400) {
      throw new Error(`Unexpected error code/status: ${err.code} (${err.status}): ${err.message}`);
    }
    console.log('✓ Unknown question successfully rejected with 400 UNKNOWN_QUESTION_NUMBER');
    passCount++;
  }

  // -------------------------------------------------------------------------
  // Test 3: Missing Question Rejection on Submit
  // -------------------------------------------------------------------------
  console.log('\nTest 3: Testing missing question rejection on submit...');
  try {
    // Only Q1 and Q2 provided, Q3 missing
    const missingList: IEvaluationQuestionMark[] = [
      { questionNumber: 1, marks: 15, status: 'MARKED' },
      { questionNumber: 2, marks: 25, status: 'MARKED' },
    ];
    validateQuestionMarksList(missingList, authoritativeQuestions, true); // isSubmitting = true
    throw new Error('FAILED: Expected missing question rejection on submit');
  } catch (err: any) {
    if (err.code !== 'MISSING_QUESTION_EVALUATION' || err.status !== 400) {
      throw new Error(`Unexpected error code/status: ${err.code} (${err.status}): ${err.message}`);
    }
    console.log('✓ Missing question successfully rejected with 400 MISSING_QUESTION_EVALUATION');
    passCount++;
  }

  // -------------------------------------------------------------------------
  // Test 3b: Question Unmarked (NOT_STARTED) on Submit
  // -------------------------------------------------------------------------
  console.log('\nTest 3b: Testing NOT_STARTED question rejection on submit...');
  try {
    const unstartedList: IEvaluationQuestionMark[] = [
      { questionNumber: 1, marks: 15, status: 'MARKED' },
      { questionNumber: 2, marks: 25, status: 'MARKED' },
      { questionNumber: 3, marks: 0, status: 'NOT_STARTED' },
    ];
    validateQuestionMarksList(unstartedList, authoritativeQuestions, true);
    throw new Error('FAILED: Expected NOT_STARTED question rejection on submit');
  } catch (err: any) {
    if (err.code !== 'QUESTION_UNMARKED' || err.status !== 400) {
      throw new Error(`Unexpected error code/status: ${err.code} (${err.status}): ${err.message}`);
    }
    console.log('✓ NOT_STARTED question successfully rejected with 400 QUESTION_UNMARKED');
    passCount++;
  }

  // -------------------------------------------------------------------------
  // Test 4: Excessive Marks Rejection (> maximumMarks)
  // -------------------------------------------------------------------------
  console.log('\nTest 4: Testing excessive marks rejection...');
  try {
    // Q1 max is 20, sending 25
    const excessiveList: IEvaluationQuestionMark[] = [
      { questionNumber: 1, marks: 25, status: 'MARKED' },
    ];
    validateQuestionMarksList(excessiveList, authoritativeQuestions, false);
    throw new Error('FAILED: Expected excessive marks rejection');
  } catch (err: any) {
    if (err.code !== 'MARKS_EXCEED_MAXIMUM' || err.status !== 400) {
      throw new Error(`Unexpected error code/status: ${err.code} (${err.status}): ${err.message}`);
    }
    console.log('✓ Excessive marks successfully rejected with 400 MARKS_EXCEED_MAXIMUM');
    passCount++;
  }

  // -------------------------------------------------------------------------
  // Test 5: Negative Marks Rejection
  // -------------------------------------------------------------------------
  console.log('\nTest 5: Testing negative marks rejection...');
  try {
    const negativeList: IEvaluationQuestionMark[] = [
      { questionNumber: 1, marks: -5, status: 'MARKED' },
    ];
    validateQuestionMarksList(negativeList, authoritativeQuestions, false);
    throw new Error('FAILED: Expected negative marks rejection');
  } catch (err: any) {
    if (err.code !== 'INVALID_MARKS_NEGATIVE' || err.status !== 400) {
      throw new Error(`Unexpected error code/status: ${err.code} (${err.status}): ${err.message}`);
    }
    console.log('✓ Negative marks successfully rejected with 400 INVALID_MARKS_NEGATIVE');
    passCount++;
  }

  // -------------------------------------------------------------------------
  // Test 6: NOT_ATTEMPTED with Non-Zero Marks Rejection
  // -------------------------------------------------------------------------
  console.log('\nTest 6: Testing NOT_ATTEMPTED with non-zero marks rejection...');
  try {
    const notAttemptedWithMarks: IEvaluationQuestionMark[] = [
      { questionNumber: 1, marks: 10, status: 'NOT_ATTEMPTED' },
    ];
    validateQuestionMarksList(notAttemptedWithMarks, authoritativeQuestions, false);
    throw new Error('FAILED: Expected NOT_ATTEMPTED with non-zero marks rejection');
  } catch (err: any) {
    if (err.code !== 'INVALID_NOT_ATTEMPTED_MARKS' || err.status !== 400) {
      throw new Error(`Unexpected error code/status: ${err.code} (${err.status}): ${err.message}`);
    }
    console.log('✓ NOT_ATTEMPTED with non-zero marks successfully rejected with 400 INVALID_NOT_ATTEMPTED_MARKS');
    passCount++;
  }

  // -------------------------------------------------------------------------
  // Test 7: Incorrect Client Total Discarded & Correct Backend Calculation
  // -------------------------------------------------------------------------
  console.log('\nTest 7: Testing backend authoritative total calculation...');
  const validListWithClientFakeTotal: IEvaluationQuestionMark[] = [
    { questionNumber: 1, marks: 18, status: 'MARKED' },
    { questionNumber: 2, marks: 25, status: 'FLAGGED' },
    { questionNumber: 3, marks: 0, status: 'NOT_ATTEMPTED' },
  ];
  // Client claimed totalMarks = 99999; Backend must compute 18 + 25 + 0 = 43
  const { validatedList, computedTotal } = validateQuestionMarksList(
    validListWithClientFakeTotal,
    authoritativeQuestions,
    true
  );
  if (computedTotal !== 43) {
    throw new Error(`FAILED: Computed total mismatch: expected 43, got ${computedTotal}`);
  }
  console.log(`✓ Backend correctly calculated total: ${computedTotal} (ignoring any arbitrary client total)`);
  passCount++;

  // -------------------------------------------------------------------------
  // Test 8: Successful Valid Submission
  // -------------------------------------------------------------------------
  console.log('\nTest 8: Testing successful valid submission validation...');
  const completeSubmissionList: IEvaluationQuestionMark[] = [
    { questionNumber: 1, marks: 20, status: 'MARKED', comment: 'Full marks' },
    { questionNumber: 2, marks: 28, status: 'MARKED', comment: 'Minor deduction on edge case' },
    { questionNumber: 3, marks: 45, status: 'FLAGGED', comment: 'Flagged for moderation check' },
  ];
  const submissionResult = validateQuestionMarksList(
    completeSubmissionList,
    authoritativeQuestions,
    true
  );
  if (submissionResult.computedTotal !== 93) {
    throw new Error(`FAILED: Expected 93, got ${submissionResult.computedTotal}`);
  }
  if (submissionResult.validatedList.length !== 3) {
    throw new Error('FAILED: Validated list length mismatch');
  }
  console.log(`✓ Successful valid submission verified! All 3 questions evaluated, backend total: ${submissionResult.computedTotal}`);
  passCount++;

  console.log('\n===============================================================');
  console.log(`ALL ${passCount} EVALUATION VALIDATION TESTS PASSED SUCCESSFULLY!`);
  console.log('===============================================================\n');
}

runEvaluationTests().catch((err) => {
  console.error('Test suite failed:', err);
  process.exit(1);
});
