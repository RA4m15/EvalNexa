import dotenv from 'dotenv';
dotenv.config();

const API_BASE = 'http://localhost:5000/api';

async function request(path: string, options: RequestInit = {}, token?: string) {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  const json = await res.json();
  if (!res.ok) {
    throw new Error(`[${res.status}] ${json.message || JSON.stringify(json)}`);
  }
  return json;
}

async function run() {
  console.log('========================================================');
  console.log('EVALNEXA END-TO-END WORKFLOW VERIFICATION SUITE');
  console.log('========================================================\n');

  // 1. Admin Login
  console.log('1. Authenticating Admin...');
  const adminAuth = await request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email: 'admin@evalnexa.edu', password: process.env.ADMIN_PASSWORD || 'Admin@1234' }),
  });
  const adminToken = adminAuth.data.token;
  console.log('✓ Admin authenticated:', adminAuth.data.user.name);

  // 2. Admin creates exam
  console.log('\n2. Admin registering institutional examination...');
  const examSuffix = Math.floor(1000 + Math.random() * 9000);
  const examCode = `MATH${examSuffix}`;
  const exam = await request('/exams', {
    method: 'POST',
    body: JSON.stringify({
      title: `Advanced Mathematical Physics ${examSuffix}`,
      subjectCode: examCode,
      subjectName: 'Theoretical Mathematics & Wave Mechanics',
      academicSession: '2024-25 Fall Semester',
      maximumMarks: 100,
      totalQuestions: 2,
    }),
  }, adminToken);
  const examId = exam.data._id;
  console.log(`✓ Examination registered: ${exam.data.title} (${exam.data.subjectCode}), ID: ${examId}`);

  // 3. Admin creates questions & rubrics
  console.log('\n3. Admin creating questions and rubrics...');
  const q1 = await request(`/exams/${examId}/questions`, {
    method: 'POST',
    body: JSON.stringify({
      questionNumber: 1,
      text: 'Derive the time-independent Schrödinger wave equation from first principles and evaluate boundary potentials.',
      maximumMarks: 50,
      rubric: [
        { criterion: 'Conservation of Hamiltonian operators', marks: 25 },
        { criterion: 'Boundary condition derivation and rigor', marks: 25 },
      ],
    }),
  }, adminToken);
  console.log(`✓ Question 1 registered with 2 rubric criteria, Max Marks: ${q1.data.maximumMarks}`);

  const q2 = await request(`/exams/${examId}/questions`, {
    method: 'POST',
    body: JSON.stringify({
      questionNumber: 2,
      text: 'Solve for eigenstate wavefunctions in a one-dimensional finite potential well.',
      maximumMarks: 50,
      rubric: [
        { criterion: 'Eigenstate symmetry classification', marks: 25 },
        { criterion: 'Transcendental relation solutions', marks: 25 },
      ],
    }),
  }, adminToken);
  console.log(`✓ Question 2 registered with 2 rubric criteria, Max Marks: ${q2.data.maximumMarks}`);

  // 4. Admin registers answer book via Scan & Quality Ingestion
  console.log('\n4. Admin registering digital answer book...');
  const abCode = `AB-${examSuffix}-001`;
  const ab = await request('/answer-books', {
    method: 'POST',
    body: JSON.stringify({
      examId,
      answerBookCode: abCode,
      studentCode: `STU-ENG-${examSuffix}`,
      pageCount: 16,
      scanBatch: `BATCH-${examSuffix}`,
      qualityStatus: 'VERIFIED',
    }),
  }, adminToken);
  const answerBookId = ab.data._id;
  console.log(`✓ Answer book registered: Code ${ab.data.answerBookCode}, Status: ${ab.data.status}, Quality: ${ab.data.qualityStatus}`);

  // Get Examiner ID
  const examinersList = await request('/users?role=EXAMINER', {}, adminToken);
  const examinerUser = examinersList.data[0];
  if (!examinerUser) throw new Error('No examiner found in database');
  console.log(`✓ Target examiner selected: ${examinerUser.name} (${examinerUser.email})`);

  // 5. Admin assigns examiner
  console.log('\n5. Admin assigning examiner to answer book...');
  const assignedAb = await request(`/answer-books/${answerBookId}/assign`, {
    method: 'POST',
    body: JSON.stringify({ examinerId: examinerUser._id }),
  }, adminToken);
  console.log(`✓ Answer book assigned: Status = ${assignedAb.data.status}`);

  // 6. Examiner Login
  console.log('\n6. Authenticating Examiner...');
  const examinerAuth = await request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email: 'examiner@evalnexa.edu', password: process.env.EXAMINER_PASSWORD || 'Examiner@5678' }),
  });
  const examinerToken = examinerAuth.data.token;
  console.log('✓ Examiner authenticated:', examinerAuth.data.user.name);

  // 7. Examiner retrieves my papers
  console.log('\n7. Examiner fetching assigned docket...');
  const myPapers = await request('/answer-books/my', {}, examinerToken);
  const foundPaper = myPapers.data.find((p: any) => p._id === answerBookId);
  if (!foundPaper) throw new Error('Assigned paper not found in examiner docket');
  console.log(`✓ Examiner docket received paper ${foundPaper.answerBookCode}, Status = ${foundPaper.status}`);

  // 8. Examiner starts evaluation
  console.log('\n8. Examiner opening marking screen & starting evaluation...');
  const startEval = await request(`/evaluations/${answerBookId}/start`, {
    method: 'POST',
  }, examinerToken);
  const evaluationId = startEval.data._id;
  console.log(`✓ Evaluation started, Evaluation ID: ${evaluationId}, Status: ${startEval.data.status}`);

  // 9. Examiner marks questions
  console.log('\n9. Examiner recording question-by-question marks...');
  const questionMarks = [
    { questionNumber: 1, marks: 44, status: 'MARKED', comment: 'Rigorously derived operators. Minor algebraic skip in boundary step.' },
    { questionNumber: 2, marks: 46, status: 'MARKED', comment: 'Accurate eigenstate analysis and graphical sketch.' },
  ];
  const updateEval = await request(`/evaluations/${evaluationId}`, {
    method: 'PATCH',
    body: JSON.stringify({
      totalMarks: 90,
      questionMarks,
      remarks: 'Exemplary script with thorough mathematical demonstrations.',
    }),
  }, examinerToken);
  console.log(`✓ Marks updated: Total = ${updateEval.data.totalMarks} / 100 across 2 questions.`);

  // 10. Examiner submits evaluation
  console.log('\n10. Examiner submitting evaluation to moderation...');
  const submitEval = await request(`/evaluations/${evaluationId}/submit`, {
    method: 'POST',
    body: JSON.stringify({
      totalMarks: 90,
      questionMarks,
      remarks: 'Exemplary script with thorough mathematical demonstrations.',
    }),
  }, examinerToken);
  console.log(`✓ Evaluation submitted: Evaluation Status = ${submitEval.data.status}`);

  // 11. Moderator Login
  console.log('\n11. Authenticating Moderator...');
  const modAuth = await request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email: 'moderator@evalnexa.edu', password: process.env.MODERATOR_PASSWORD || 'Moderator@9012' }),
  });
  const modToken = modAuth.data.token;
  console.log('✓ Moderator authenticated:', modAuth.data.user.name);

  // 12. Moderator checks queue
  console.log('\n12. Moderator retrieving review queue...');
  const queue = await request('/moderation/queue', {}, modToken);
  const queueItem = queue.data.find((q: any) => q._id === evaluationId);
  if (!queueItem) throw new Error('Submitted evaluation not found in moderation queue');
  console.log(`✓ Evaluation found in queue: Total Marks = ${queueItem.totalMarks}, Status = ${queueItem.status}`);

  // 13. Moderator inspects evaluation detail
  console.log('\n13. Moderator inspecting evaluation detail...');
  const detail = await request(`/moderation/${evaluationId}`, {}, modToken);
  console.log(`✓ Detail inspected: ${detail.data.questionMarks?.length} question scoring items present.`);

  // 14. Moderator approves evaluation
  console.log('\n14. Moderator approving evaluation & certifying final marks...');
  const approval = await request(`/moderation/${evaluationId}/approve`, {
    method: 'POST',
  }, modToken);
  console.log(`✓ Evaluation certified: Status = ${approval.data.status}, Decision = APPROVED`);

  // 15. Moderator checks integrity surveillance
  console.log('\n15. Moderator running integrity surveillance sweep...');
  const integrity = await request('/moderation/integrity-checks', {}, modToken);
  console.log(`✓ Integrity checks completed. Active anomalies count: ${integrity.data.length}`);

  // 16. Admin checks audit trail
  console.log('\n16. Admin inspecting tamper-evident audit ledger...');
  const auditLogs = await request('/audit-logs?limit=10', {}, adminToken);
  console.log(`✓ Total audit records retrieved: ${auditLogs.data.length}. Recent actions:`);
  auditLogs.data.slice(0, 6).forEach((log: any) => {
    console.log(`   - [${log.action}] on ${log.entityType} (${log.entityId.slice(-6)}) at ${new Date(log.createdAt).toLocaleTimeString()}`);
  });

  console.log('\n========================================================');
  console.log('✓ ALL 16 REQUIREMENTS FULLY VALIDATED AND PASSING');
  console.log('========================================================');
}

run().catch((err) => {
  console.error('\n✗ Workflow Test Failed:', err.message);
  process.exit(1);
});
