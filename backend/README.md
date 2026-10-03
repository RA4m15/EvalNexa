# EvalNexa — Backend API & Real-Time Engine

Production-grade shared backend powering the three EvalNexa frontend panels:
1. **Control Center** (`http://localhost:5173`) — Administrative dashboard, exam creation, answer book registration & examiner assignment
2. **Examiner Workspace** (`http://localhost:5174`) — Digital marking workspace, question rubrics, annotations & submission
3. **Moderation & Quality Center** (`http://localhost:5175`) — Review queue, score verification, audit inspection, approve & return workflows

---

## 🛠️ Stack & Architecture

- **Runtime**: Node.js & TypeScript
- **HTTP Server**: Express.js
- **Database**: MongoDB with Mongoose ODM (7 collections, indexes, timestamps)
- **Real-Time WebSockets**: Socket.IO with role-scoped & exam-scoped rooms
- **Security & Auth**: JWT (cookie & Bearer header), bcrypt password hashing, `express-rate-limit` on login, Helmet headers, CORS
- **Validation**: Zod schema validation middleware
- **Architecture**: Clean layered architecture — thin controllers, domain services, type-safe models

```
backend/
├── src/
│   ├── config/          # Environment configuration & origin resolution
│   ├── models/          # Mongoose models (User, Exam, Question, AnswerBook, Evaluation, Moderation, AuditLog)
│   ├── controllers/     # Thin HTTP controllers (request parsing & response formatting)
│   ├── services/        # Domain business logic & state transition validation
│   ├── routes/          # Express route definitions & role guards
│   ├── middleware/      # Auth, authorization, rate limiter, Zod validator, error handlers
│   ├── sockets/         # Socket.IO initialization, authentication, and targeted emitters
│   ├── validators/      # Zod validation schemas
│   ├── utils/           # Helper utilities
│   ├── scripts/         # Database seeding & user provisioning scripts
│   ├── app.ts           # Express application configuration
│   └── server.ts        # HTTP server entry point & Socket.IO attachment
└── README.md
```

---

## ⚙️ Installation & Setup

### 1. Prerequisites
- Node.js >= 18.x
- pnpm >= 8.x
- MongoDB instance (Local or MongoDB Atlas)

### 2. Install Dependencies
```bash
# From workspace root
pnpm install
```

### 3. Environment Variables Setup
Copy the example environment file:
```bash
cp .env.example backend/.env
```

Ensure `backend/.env` contains the required settings:
```env
PORT=5000
NODE_ENV=development
MONGODB_URI=mongodb://127.0.0.1:27017/evalnexa
JWT_SECRET=evalnexa-dev-secret-change-in-prod
JWT_EXPIRES_IN=7d

# Frontend Origins
CONTROL_CENTER_ORIGIN=http://localhost:5173
EXAMINER_ORIGIN=http://localhost:5174
MODERATION_ORIGIN=http://localhost:5175

# Dedicated Panel Credentials
ADMIN_NAME=System Administrator
ADMIN_EMAIL=admin@evalnexa.edu
ADMIN_PASSWORD=Admin@1234

EXAMINER_NAME=Dr. Sarah Mitchell
EXAMINER_EMAIL=examiner@evalnexa.edu
EXAMINER_PASSWORD=Examiner@5678

MODERATOR_NAME=Prof. James Harlow
MODERATOR_EMAIL=moderator@evalnexa.edu
MODERATOR_PASSWORD=Moderator@9012
```

---

## 👥 Panel Credentials Setup

EvalNexa includes a one-command seed utility that provisions dedicated credentials for each panel:

```bash
pnpm --filter backend seed-users
```

| Panel | URL | Email | Password | Role |
|-------|-----|-------|----------|------|
| **Control Center** | `http://localhost:5173` | `admin@evalnexa.edu` | `Admin@1234` | `ADMIN` |
| **Examiner Workspace** | `http://localhost:5174` | `examiner@evalnexa.edu` | `Examiner@5678` | `EXAMINER` |
| **Moderation Centre** | `http://localhost:5175` | `moderator@evalnexa.edu` | `Moderator@9012` | `MODERATOR` |

To populate a complete development dataset (exams, questions, answer books, evaluations, moderation records, and audit logs):
```bash
pnpm --filter backend seed
```

---

## 🚀 Running the Server

```bash
# Development mode with auto-reload (tsx watch)
pnpm --filter backend dev

# Build TypeScript to dist/
pnpm --filter backend build

# Production start
pnpm --filter backend start
```

---

## 🗄️ Database Collections & Models

### 1. `users` (`User.ts`)
- `name`: string
- `email`: string (unique, lowercase)
- `passwordHash`: string (bcrypt, `select: false`)
- `role`: `'ADMIN' | 'EXAMINER' | 'MODERATOR'`
- `institutionId`: string (optional)
- `isActive`: boolean (default: `true`)
- Timestamps (`createdAt`, `updatedAt`)

### 2. `exams` (`Exam.ts`)
- `title`: string
- `subjectCode`: string (uppercase)
- `subjectName`: string
- `academicSession`: string
- `maximumMarks`: number
- `totalQuestions`: number
- `status`: `'DRAFT' | 'READY' | 'EVALUATION_OPEN' | 'EVALUATION_CLOSED' | 'MODERATION' | 'FINALIZED'`
- `createdBy`: ObjectId (ref: `User`)
- Timestamps (`createdAt`, `updatedAt`)

### 3. `questions` (`Question.ts`)
- `examId`: ObjectId (ref: `Exam`, indexed)
- `questionNumber`: number
- `text`: string
- `maximumMarks`: number
- `rubric`: `[{ criterion: string, marks: number }]`
- Compound Index: `{ examId: 1, questionNumber: 1 }` (unique)
- Timestamps (`createdAt`, `updatedAt`)

### 4. `answerBooks` (`AnswerBook.ts`)
- `examId`: ObjectId (ref: `Exam`, indexed)
- `answerBookCode`: string (unique, uppercase)
- `studentCode`: string (uppercase)
- `pageCount`: number
- `status`: `'READY' | 'ASSIGNED' | 'IN_PROGRESS' | 'SUBMITTED' | 'UNDER_REVIEW' | 'APPROVED' | 'RETURNED' | 'FINALIZED'`
- `assignedExaminerId`: ObjectId (ref: `User`, nullable)
- Timestamps (`createdAt`, `updatedAt`)

### 5. `evaluations` (`Evaluation.ts`)
- `answerBookId`: ObjectId (ref: `AnswerBook`, indexed)
- `examinerId`: ObjectId (ref: `User`, indexed)
- `status`: `'NOT_STARTED' | 'IN_PROGRESS' | 'SUBMITTED' | 'UNDER_REVIEW' | 'APPROVED' | 'RETURNED'`
- `totalMarks`: number
- `remarks`: string
- `startedAt`: Date
- `submittedAt`: Date
- Timestamps (`createdAt`, `updatedAt`)

### 6. `moderations` (`Moderation.ts`)
- `evaluationId`: ObjectId (ref: `Evaluation`, indexed)
- `moderatorId`: ObjectId (ref: `User`, indexed)
- `status`: `'UNDER_REVIEW' | 'APPROVED' | 'RETURNED'`
- `decision`: `'APPROVE' | 'RETURN'`
- `reason`: string (optional)
- Timestamps (`createdAt`, `updatedAt`)

### 7. `auditLogs` (`AuditLog.ts`)
- `actorId`: ObjectId (ref: `User`)
- `action`: string (e.g. `EXAM_CREATED`, `ANSWER_BOOK_ASSIGNED`, `EVALUATION_SUBMITTED`, etc.)
- `entityType`: string (`Exam`, `AnswerBook`, `Evaluation`, `User`, `Question`)
- `entityId`: string
- `metadata`: Mixed JSON
- `createdAt`: Date (immutable)

---

## 🔒 Server-Side State Transitions

EvalNexa strictly validates state transitions on the server. Invalid jumps (e.g., `READY -> APPROVED`) return HTTP 400:

```
READY
  └── ASSIGNED (Admin assigns Examiner)
        └── IN_PROGRESS (Examiner starts marking)
              └── SUBMITTED (Examiner submits marks)
                    ├── UNDER_REVIEW (Moderator opens review)
                    │     ├── APPROVED (Moderator approves marks)
                    │     └── RETURNED (Moderator sends back with critique)
                    ├── APPROVED (Moderator direct approval)
                    └── RETURNED (Moderator direct return)
                          └── IN_PROGRESS / ASSIGNED (Examiner revises paper)
```

---

## 📡 API Endpoints

All responses follow a consistent envelope:

**Success**:
```json
{
  "success": true,
  "data": { ... }
}
```

**Error**:
```json
{
  "success": false,
  "message": "Human readable explanation",
  "code": "ERROR_CODE",
  "details": { ... }
}
```

### 1. Authentication (`/api/auth`)
| Method | Route | Access | Description |
|--------|-------|--------|-------------|
| `POST` | `/api/auth/login` | Public (Rate-limited) | Login with email and password, sets JWT cookie |
| `GET` | `/api/auth/me` | Authenticated | Fetch authenticated user profile |
| `POST` | `/api/auth/logout` | Authenticated | Clears auth token cookie |

### 2. User Management (`/api/users`)
| Method | Route | Access | Description |
|--------|-------|--------|-------------|
| `GET` | `/api/users` | `ADMIN` | List all users |
| `POST` | `/api/users` | `ADMIN` | Create user account |
| `GET` | `/api/users/examiners` | `ADMIN` | List active examiners |
| `GET` | `/api/users/:id` | `ADMIN` | Get user by ID |
| `PATCH` | `/api/users/:id` | `ADMIN` | Update user details or active status |

### 3. Examination Management (`/api/exams`)
| Method | Route | Access | Description |
|--------|-------|--------|-------------|
| `GET` | `/api/exams` | `ADMIN`, `MODERATOR` | List exams |
| `POST` | `/api/exams` | `ADMIN` | Create new examination |
| `GET` | `/api/exams/stats/dashboard` | `ADMIN` | Aggregated dashboard metrics |
| `GET` | `/api/exams/:id` | `ADMIN`, `MODERATOR` | Get exam details |
| `PATCH` | `/api/exams/:id` | `ADMIN` | Update exam |
| `DELETE` | `/api/exams/:id` | `ADMIN` | Delete exam (if no answer books exist) |

### 4. Examination Questions (`/api/exams/:examId/questions` & `/api/questions`)
| Method | Route | Access | Description |
|--------|-------|--------|-------------|
| `GET` | `/api/exams/:examId/questions` | Authenticated | List all questions for an exam |
| `POST` | `/api/exams/:examId/questions` | `ADMIN` | Add question with rubrics to exam |
| `GET` | `/api/questions/:id` | Authenticated | Get specific question details |
| `PATCH` | `/api/questions/:id` | `ADMIN` | Update question text, marks, or rubrics |
| `DELETE` | `/api/questions/:id` | `ADMIN` | Delete question |

### 5. Answer Books (`/api/answer-books`)
| Method | Route | Access | Description |
|--------|-------|--------|-------------|
| `GET` | `/api/answer-books` | `ADMIN`, `MODERATOR`, `EXAMINER` | List answer books (scoped to assigned examiner if `EXAMINER`) |
| `GET` | `/api/answer-books/my` | `EXAMINER` | List answer books assigned to authenticated examiner with counts |
| `POST` | `/api/answer-books` | `ADMIN` | Register new answer book |
| `GET` | `/api/answer-books/:id` | Authenticated | Get answer book and existing evaluation |
| `PATCH` | `/api/answer-books/:id` | `ADMIN` | Update answer book |
| `POST` | `/api/answer-books/:id/assign` | `ADMIN` | Assign answer book to active examiner |

### 6. Evaluations (`/api/evaluations`)
| Method | Route | Access | Description |
|--------|-------|--------|-------------|
| `GET` | `/api/evaluations` | Authenticated | List evaluations (scoped to self if `EXAMINER`) |
| `GET` | `/api/evaluations/:id` | Authenticated | Get evaluation details |
| `POST` | `/api/evaluations/:id/start` | `EXAMINER` | Start marking (transitions `ASSIGNED -> IN_PROGRESS`) |
| `PATCH` | `/api/evaluations/:id` | `EXAMINER` | Update draft marks & remarks |
| `POST` | `/api/evaluations/:id/submit` | `EXAMINER` | Submit marks (transitions `IN_PROGRESS -> SUBMITTED`) |

### 7. Moderation (`/api/moderation` or `/api/moderations`)
| Method | Route | Access | Description |
|--------|-------|--------|-------------|
| `GET` | `/api/moderation` | `MODERATOR`, `ADMIN` | Queue of submitted/under-review evaluations |
| `GET` | `/api/moderation/stats` | `MODERATOR`, `ADMIN` | Metric counts (submitted, under review, approved, returned) |
| `GET` | `/api/moderation/:id` | `MODERATOR`, `ADMIN` | Review evaluation details & moderation history |
| `POST` | `/api/moderation/:id/approve` | `MODERATOR` | Approve evaluation (`SUBMITTED -> APPROVED`) |
| `POST` | `/api/moderation/:id/return` | `MODERATOR` | Return evaluation with critique (`SUBMITTED -> RETURNED`) |

### 8. Audit Logs (`/api/audit-logs`)
| Method | Route | Access | Description |
|--------|-------|--------|-------------|
| `GET` | `/api/audit-logs` | `ADMIN`, `MODERATOR` | Paginated immutable audit trail with actor details |

---

## ⚡ Real-Time Socket.IO Architecture

Socket.IO provides zero-refresh updates across all three panels. The REST API remains the authoritative source of truth. Mutations persist to MongoDB, record an audit entry, and emit a typed event.

### Socket Rooms
- `role:admin` — Administrator notifications
- `role:examiner` — Examiner notifications
- `role:moderator` — Moderation queue events
- `user:{userId}` — Direct user alerts (e.g. personal assignment)
- `exam:{examId}` — Examination-specific channel

### Socket Events
| Event | Trigger | Target Audience |
|-------|---------|-----------------|
| `exam.created` | Admin creates exam | All clients |
| `exam.updated` | Admin updates exam | All clients |
| `question.created` | Question added to exam | Exam room |
| `question.updated` | Question rubric modified | Exam room |
| `answerbook.created` | Admin registers answer book | All clients |
| `answerbook.assigned` | Admin assigns to examiner | All clients & `user:{examinerId}` |
| `answerbook.status.changed` | Status transition | All clients |
| `evaluation.started` | Examiner starts evaluation | All clients |
| `evaluation.updated` | Examiner updates draft marks | All clients |
| `evaluation.submitted` | Examiner submits evaluation | All clients & `role:moderator` |
| `moderation.approved` | Moderator approves evaluation | All clients |
| `moderation.returned` | Moderator returns evaluation | All clients |
| `user.created` | New user provisioned | All clients |

---

## 🧪 Real-Time Verification Workflow

Test the complete lifecycle across three simultaneous browser windows:

1. **Browser 1 (`http://localhost:5173`)**: Log in as `admin@evalnexa.edu` (Control Center)
2. **Browser 2 (`http://localhost:5174`)**: Log in as `examiner@evalnexa.edu` (Examiner Workspace)
3. **Browser 3 (`http://localhost:5175`)**: Log in as `moderator@evalnexa.edu` (Moderation Centre)

### Lifecycle Steps:
1. **Admin creates exam** → Instantly visible in Control Center and database.
2. **Admin registers answer book** → Answer book appears with status `READY`.
3. **Admin assigns answer book to Examiner** → Examiner Workspace updates live without refresh (`ASSIGNED`).
4. **Examiner clicks 'Start Evaluation'** → Status updates to `IN_PROGRESS` across all panels without refresh.
5. **Examiner records marks and clicks 'Submit Evaluation'** → Moderation Centre queue updates live with new submission (`SUBMITTED`).
6. **Moderator clicks 'Approve'** → Status updates to `APPROVED` across all three panels in real-time.
7. **Refresh all browsers** → Data remains completely intact because MongoDB is the single source of truth.
