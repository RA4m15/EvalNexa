/**
 * EvalNexa – Comprehensive Development Seed Script
 *
 * Populates realistic users, exams, answer books, evaluations, and audit logs
 * for testing and demonstration across Control Center, Examiner Workspace, and Moderation Centre.
 *
 * Usage:
 *   pnpm --filter backend seed
 */
import dotenv from 'dotenv';
dotenv.config();

import bcrypt from 'bcryptjs';
import mongoose from 'mongoose';
import { User } from '../models/User';
import { Exam } from '../models/Exam';
import { Question } from '../models/Question';
import { AnswerBook } from '../models/AnswerBook';
import { Evaluation } from '../models/Evaluation';
import { Moderation } from '../models/Moderation';
import { AuditLog } from '../models/AuditLog';
import { config } from '../config';

const SEED_USERS = [
  {
    name: 'System Administrator',
    email: 'admin@evalnexa.dev',
    password: 'Admin@1234',
    role: 'ADMIN' as const,
  },
  {
    name: 'Dr. Sarah Mitchell',
    email: 'examiner@evalnexa.dev',
    password: 'Examiner@1234',
    role: 'EXAMINER' as const,
  },
  {
    name: 'Prof. Marcus Vance',
    email: 'examiner2@evalnexa.dev',
    password: 'Examiner@1234',
    role: 'EXAMINER' as const,
  },
  {
    name: 'Prof. James Harrington',
    email: 'moderator@evalnexa.dev',
    password: 'Moderator@1234',
    role: 'MODERATOR' as const,
  },
];

async function seed() {
  if (config.nodeEnv === 'production') {
    console.error('❌  Seed script cannot be run in production');
    process.exit(1);
  }

  if (!config.mongoUri) {
    console.error('❌  MONGODB_URI is not set');
    process.exit(1);
  }

  console.log('\n╔══════════════════════════════════════════════════════╗');
  console.log('║        EvalNexa – Enterprise Development Seed        ║');
  console.log('╚══════════════════════════════════════════════════════╝\n');

  await mongoose.connect(config.mongoUri);
  console.log('✅  Connected to MongoDB');

  // 1. Seed or find users
  const userMap: Record<string, any> = {};
  for (const userData of SEED_USERS) {
    let user = await User.findOne({ email: userData.email });
    if (!user) {
      const passwordHash = await bcrypt.hash(userData.password, 12);
      user = await User.create({
        name: userData.name,
        email: userData.email,
        passwordHash,
        role: userData.role,
        isActive: true,
      });
      console.log(`   ✅  Created user [${userData.role}]: ${userData.email}`);
    } else {
      console.log(`   ⏭  Found existing user [${userData.role}]: ${userData.email}`);
    }
    userMap[userData.email] = user;
  }

  const admin = userMap['admin@evalnexa.dev'];
  const examiner1 = userMap['examiner@evalnexa.dev'];
  const examiner2 = userMap['examiner2@evalnexa.dev'];
  const moderator = userMap['moderator@evalnexa.dev'];

  // 2. Seed Exams
  const sampleExams = [
    {
      title: 'CS-401 Advanced Distributed Systems & Cloud Architecture',
      subjectCode: 'CS-401',
      subjectName: 'Distributed Systems & Cloud Computing',
      academicSession: 'Fall 2026',
      maximumMarks: 100,
      totalQuestions: 10,
      status: 'EVALUATION_OPEN' as const,
      createdBy: admin._id,
    },
    {
      title: 'EE-204 Signals, Linear Systems & Spectral Analysis',
      subjectCode: 'EE-204',
      subjectName: 'Signals & Systems',
      academicSession: 'Fall 2026',
      maximumMarks: 75,
      totalQuestions: 8,
      status: 'EVALUATION_OPEN' as const,
      createdBy: admin._id,
    },
    {
      title: 'ME-302 Heat Transfer, Thermodynamics & Fluid Dynamics',
      subjectCode: 'ME-302',
      subjectName: 'Thermal Engineering',
      academicSession: 'Fall 2026',
      maximumMarks: 100,
      totalQuestions: 10,
      status: 'MODERATION' as const,
      createdBy: admin._id,
    },
  ];

  const examMap: Record<string, any> = {};
  for (const examData of sampleExams) {
    let exam = await Exam.findOne({ subjectCode: examData.subjectCode });
    if (!exam) {
      exam = await Exam.create(examData);
      console.log(`   ✅  Created Exam: [${exam.subjectCode}] ${exam.title}`);
      await AuditLog.create({
        actorId: admin._id,
        action: 'EXAM_CREATED',
        entityType: 'Exam',
        entityId: exam._id.toString(),
        metadata: { code: exam.subjectCode, title: exam.title },
      });
    } else {
      console.log(`   ⏭  Found existing Exam: [${exam.subjectCode}]`);
    }
    examMap[examData.subjectCode] = exam;
  }

  // 2b. Seed Sample Questions for CS-401
  const examCS = examMap['CS-401'];
  const sampleQuestionsCS = [
    {
      questionNumber: 1,
      text: 'Explain the CAP theorem and contrast AP vs CP trade-offs in modern distributed datastores with concrete examples.',
      maximumMarks: 10,
      rubric: [
        { criterion: 'Accurate definition of Consistency, Availability, Partition tolerance', marks: 4 },
        { criterion: 'Concrete real-world examples (Cassandra vs Spanner/Raft)', marks: 3 },
        { criterion: 'Formal trade-off analysis under active partition', marks: 3 },
      ],
    },
    {
      questionNumber: 2,
      text: 'Derive the safety and liveness invariants of the Raft consensus protocol during leader election and log replication.',
      maximumMarks: 15,
      rubric: [
        { criterion: 'Election timeout & randomized timer mechanisms', marks: 5 },
        { criterion: 'Log matching property & leader completeness proof', marks: 5 },
        { criterion: 'Safety invariant formulation', marks: 5 },
      ],
    },
    {
      questionNumber: 3,
      text: 'Describe vector clocks and their utility in causal consistency verification across peer-to-peer nodes.',
      maximumMarks: 10,
      rubric: [
        { criterion: 'Mathematical notation of vector increments', marks: 4 },
        { criterion: 'Concurrent event detection logic', marks: 3 },
        { criterion: 'Failure modes and pruning mechanisms', marks: 3 },
      ],
    },
  ];

  for (const qData of sampleQuestionsCS) {
    const existingQ = await Question.findOne({ examId: examCS._id, questionNumber: qData.questionNumber });
    if (!existingQ) {
      await Question.create({
        examId: examCS._id,
        questionNumber: qData.questionNumber,
        text: qData.text,
        maximumMarks: qData.maximumMarks,
        rubric: qData.rubric,
      });
      console.log(`   ✅  Created Question Q${qData.questionNumber} for [CS-401]`);
    } else {
      console.log(`   ⏭  Found existing Question Q${qData.questionNumber} for [CS-401]`);
    }
  }

  // 3. Seed Answer Books & Evaluations
  const examEE = examMap['EE-204'];
  const examME = examMap['ME-302'];

  const sampleAnswerBooks = [
    // CS-401 Answer Books
    {
      examId: examCS._id,
      answerBookCode: 'AN-2026-CS401-001',
      studentCode: 'STU-98421',
      pageCount: 16,
      status: 'ASSIGNED' as const,
      assignedExaminerId: examiner1._id,
      evaluation: null,
    },
    {
      examId: examCS._id,
      answerBookCode: 'AN-2026-CS401-002',
      studentCode: 'STU-98422',
      pageCount: 20,
      status: 'IN_PROGRESS' as const,
      assignedExaminerId: examiner1._id,
      evaluation: {
        status: 'IN_PROGRESS' as const,
        totalMarks: 72,
        remarks: 'Draft notes on Question 1-6 completed. Remaining questions under review.',
        startedAt: new Date(Date.now() - 3600 * 1000 * 4),
      },
    },
    {
      examId: examCS._id,
      answerBookCode: 'AN-2026-CS401-003',
      studentCode: 'STU-98423',
      pageCount: 14,
      status: 'SUBMITTED' as const,
      assignedExaminerId: examiner1._id,
      evaluation: {
        status: 'SUBMITTED' as const,
        totalMarks: 88.5,
        remarks: 'Exemplary answers on Paxos consensus algorithm and partition tolerance trade-offs. Minor derivation gap in Q7.',
        startedAt: new Date(Date.now() - 3600 * 1000 * 8),
        submittedAt: new Date(Date.now() - 3600 * 1000 * 2),
      },
    },
    {
      examId: examCS._id,
      answerBookCode: 'AN-2026-CS401-004',
      studentCode: 'STU-98424',
      pageCount: 18,
      status: 'READY' as const,
      assignedExaminerId: null,
      evaluation: null,
    },
    {
      examId: examCS._id,
      answerBookCode: 'AN-2026-CS401-005',
      studentCode: 'STU-98425',
      pageCount: 12,
      status: 'READY' as const,
      assignedExaminerId: null,
      evaluation: null,
    },

    // EE-204 Answer Books
    {
      examId: examEE._id,
      answerBookCode: 'AN-2026-EE204-001',
      studentCode: 'STU-88201',
      pageCount: 12,
      status: 'SUBMITTED' as const,
      assignedExaminerId: examiner1._id,
      evaluation: {
        status: 'SUBMITTED' as const,
        totalMarks: 64,
        remarks: 'Solid Fourier transform derivations. Missing Bode plot phase margin calculations in section C.',
        startedAt: new Date(Date.now() - 3600 * 1000 * 12),
        submittedAt: new Date(Date.now() - 3600 * 1000 * 3),
      },
    },
    {
      examId: examEE._id,
      answerBookCode: 'AN-2026-EE204-002',
      studentCode: 'STU-88202',
      pageCount: 15,
      status: 'APPROVED' as const,
      assignedExaminerId: examiner1._id,
      evaluation: {
        status: 'APPROVED' as const,
        totalMarks: 71,
        remarks: 'Excellent paper. Thorough step-by-step laplace domain solutions.',
        startedAt: new Date(Date.now() - 3600 * 1000 * 24),
        submittedAt: new Date(Date.now() - 3600 * 1000 * 18),
      },
    },
    {
      examId: examEE._id,
      answerBookCode: 'AN-2026-EE204-003',
      studentCode: 'STU-88203',
      pageCount: 10,
      status: 'RETURNED' as const,
      assignedExaminerId: examiner1._id,
      evaluation: {
        status: 'RETURNED' as const,
        totalMarks: 45,
        remarks: 'Question 4 mark discrepancy: step marks for partial fractions were omitted. Please re-tally and submit revised scoring.',
        startedAt: new Date(Date.now() - 3600 * 1000 * 16),
        submittedAt: new Date(Date.now() - 3600 * 1000 * 10),
      },
    },

    // ME-302 Answer Books
    {
      examId: examME._id,
      answerBookCode: 'AN-2026-ME302-001',
      studentCode: 'STU-77301',
      pageCount: 22,
      status: 'SUBMITTED' as const,
      assignedExaminerId: examiner2._id,
      evaluation: {
        status: 'SUBMITTED' as const,
        totalMarks: 91,
        remarks: 'Outstanding Navier-Stokes equation derivations and boundary layer thickness approximations.',
        startedAt: new Date(Date.now() - 3600 * 1000 * 6),
        submittedAt: new Date(Date.now() - 3600 * 1000 * 1),
      },
    },
    {
      examId: examME._id,
      answerBookCode: 'AN-2026-ME302-002',
      studentCode: 'STU-77302',
      pageCount: 18,
      status: 'APPROVED' as const,
      assignedExaminerId: examiner2._id,
      evaluation: {
        status: 'APPROVED' as const,
        totalMarks: 84.5,
        remarks: 'Verified and approved. All rubrics strictly followed.',
        startedAt: new Date(Date.now() - 3600 * 1000 * 30),
        submittedAt: new Date(Date.now() - 3600 * 1000 * 20),
      },
    },
  ];

  for (const abData of sampleAnswerBooks) {
    let ab = await AnswerBook.findOne({ answerBookCode: abData.answerBookCode });
    if (!ab) {
      ab = await AnswerBook.create({
        examId: abData.examId,
        answerBookCode: abData.answerBookCode,
        studentCode: abData.studentCode,
        pageCount: abData.pageCount,
        status: abData.status,
        assignedExaminerId: abData.assignedExaminerId,
      });
      console.log(`   ✅  Created AnswerBook: ${ab.answerBookCode} [${ab.status}]`);

      await AuditLog.create({
        actorId: admin._id,
        action: 'ANSWER_BOOK_CREATED',
        entityType: 'AnswerBook',
        entityId: ab._id.toString(),
        metadata: { code: ab.answerBookCode, studentCode: ab.studentCode },
      });

      if (ab.assignedExaminerId) {
        await AuditLog.create({
          actorId: admin._id,
          action: 'ANSWER_BOOK_ASSIGNED',
          entityType: 'AnswerBook',
          entityId: ab._id.toString(),
          metadata: { examinerId: ab.assignedExaminerId.toString() },
        });
      }

      if (abData.evaluation) {
        const evalDoc = await Evaluation.create({
          answerBookId: ab._id,
          examinerId: ab.assignedExaminerId,
          status: abData.evaluation.status,
          totalMarks: abData.evaluation.totalMarks,
          remarks: abData.evaluation.remarks,
          startedAt: abData.evaluation.startedAt,
          submittedAt: abData.evaluation.submittedAt,
        });

        await AuditLog.create({
          actorId: ab.assignedExaminerId,
          action: 'EVALUATION_STARTED',
          entityType: 'Evaluation',
          entityId: evalDoc._id.toString(),
          metadata: { answerBookId: ab._id.toString() },
        });

        if (['SUBMITTED', 'APPROVED', 'RETURNED'].includes(abData.evaluation.status)) {
          await AuditLog.create({
            actorId: ab.assignedExaminerId,
            action: 'EVALUATION_SUBMITTED',
            entityType: 'Evaluation',
            entityId: evalDoc._id.toString(),
            metadata: { totalMarks: abData.evaluation.totalMarks, answerBookId: ab._id.toString() },
          });
        }

        if (abData.evaluation.status === 'APPROVED') {
          await Moderation.create({
            evaluationId: evalDoc._id,
            moderatorId: moderator._id,
            status: 'APPROVED',
            decision: 'APPROVE',
          });

          await AuditLog.create({
            actorId: moderator._id,
            action: 'MODERATION_APPROVED',
            entityType: 'Evaluation',
            entityId: evalDoc._id.toString(),
            metadata: { answerBookId: ab._id.toString() },
          });
        }

        if (abData.evaluation.status === 'RETURNED') {
          await Moderation.create({
            evaluationId: evalDoc._id,
            moderatorId: moderator._id,
            status: 'RETURNED',
            decision: 'RETURN',
            reason: abData.evaluation.remarks,
          });

          await AuditLog.create({
            actorId: moderator._id,
            action: 'MODERATION_RETURNED',
            entityType: 'Evaluation',
            entityId: evalDoc._id.toString(),
            metadata: { reason: abData.evaluation.remarks, answerBookId: ab._id.toString() },
          });
        }
      }
    } else {
      console.log(`   ⏭  Found existing AnswerBook: ${ab.answerBookCode}`);
    }
  }

  console.log('\n════════════════════════════════════════════════════════');
  console.log('✅  EvalNexa seed completed successfully!');
  console.log('════════════════════════════════════════════════════════\n');
  console.log('🔐  Ready-to-use Role Accounts:');
  console.log('   ┌─────────────┬───────────────────────────┬───────────────┐');
  console.log('   │ Role        │ Email                     │ Password      │');
  console.log('   ├─────────────┼───────────────────────────┼───────────────┤');
  console.log('   │ ADMIN       │ admin@evalnexa.dev        │ Admin@1234    │');
  console.log('   │ EXAMINER    │ examiner@evalnexa.dev     │ Examiner@1234 │');
  console.log('   │ EXAMINER 2  │ examiner2@evalnexa.dev    │ Examiner@1234 │');
  console.log('   │ MODERATOR   │ moderator@evalnexa.dev    │ Moderator@1234│');
  console.log('   └─────────────┴───────────────────────────┴───────────────┘\n');

  await mongoose.disconnect();
  process.exit(0);
}

seed().catch((err) => {
  console.error('❌  Seed failed:', err);
  process.exit(1);
});
