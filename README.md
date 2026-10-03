# EvalNexa

**Intelligent Digital Examination & On-Screen Evaluation Platform**

EvalNexa is a production-grade, real-time digital examination evaluation platform that orchestrates the complete lifecycle from exam creation through answer book ingestion, examiner assignment, on-screen evaluation, moderation, and result finalisation.

---

## Architecture Overview

```
University/Admin
      ↓
Exam Creation (Control Center)
      ↓
Answer Book Registration
      ↓
Examiner Assignment (real-time notification)
      ↓
On-Screen Evaluation (Examiner Workspace)
      ↓
Submission → Moderation Queue (real-time)
      ↓
Moderation Decision (Moderation Centre)
      ↓
Approved Results → Control Center Results
```

---

## Monorepo Structure

```
evalnexa/
├── apps/
│   ├── control-center/     # Admin interface  (port 5173)
│   ├── examiner/           # Examiner OSM     (port 5174)
│   └── moderation/         # Moderation QA    (port 5175)
│
├── backend/                # Express + Socket.IO API (port 5000)
│   └── src/
│       ├── config/
│       ├── controllers/
│       ├── middleware/
│       ├── models/
│       ├── routes/
│       ├── scripts/
│       ├── services/
│       ├── sockets/
│       ├── utils/
│       └── validators/
│
├── packages/
│   ├── ui/                 # Shared design system CSS
│   └── types/              # Shared TypeScript types
│
├── pnpm-workspace.yaml
├── package.json
└── .env.example
```

---

## Technology Stack

| Layer       | Technology                                    |
|-------------|-----------------------------------------------|
| Frontend    | React 18, TypeScript, Vite, React Router v6   |
| Server state| TanStack Query v5                             |
| Real-time   | Socket.IO v4 (client + server)                |
| Backend     | Node.js, Express, TypeScript                  |
| Database    | MongoDB (Mongoose)                            |
| Auth        | JWT + bcrypt (HTTP-only cookie + Bearer)       |
| Validation  | Zod (backend) + HTML5 (frontend)              |
| Package mgr | pnpm workspaces                               |

---

## Quick Start

### 1. Prerequisites

- Node.js ≥ 18
- pnpm ≥ 8 (`npm install -g pnpm`)
- MongoDB Atlas cluster (or local MongoDB)

### 2. Clone & Install

```bash
git clone <repo>
cd evalnexa
pnpm install --ignore-scripts
```

### 3. Configure Environment

```bash
# Edit backend/.env — set your MONGODB_URI
cp .env.example backend/.env
```

Required variables in `backend/.env`:
```
MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/evalnexa
JWT_SECRET=<strong-random-secret>
PORT=5000
```

### 4. Create Admin User

```bash
pnpm --filter backend create-admin
```

This interactive script creates the first ADMIN user. Credentials are stored securely (bcrypt-hashed) in MongoDB.

### 5. Seed Panel Users

```bash
pnpm --filter backend seed-users
```

Provisions role accounts (`ADMIN`, `EXAMINER`, `MODERATOR`) directly in MongoDB using your `SEED_*_EMAIL` and `SEED_*_PASSWORD` environment variables.

---

## Development

Start all services concurrently:

```bash
pnpm dev
```

Or start individually:

```bash
pnpm dev:server          # Backend API + Socket.IO
pnpm dev:control-center  # Admin UI   → http://localhost:5173
pnpm dev:examiner        # Examiner   → http://localhost:5174
pnpm dev:moderation      # Moderation → http://localhost:5175
```

---

## Frontend Ports

| Application        | URL                     | Role      |
|--------------------|-------------------------|-----------|
| Control Center     | http://localhost:5173   | ADMIN     |
| Examiner Workspace | http://localhost:5174   | EXAMINER  |
| Moderation Centre  | http://localhost:5175   | MODERATOR |
| Backend API (Live) | https://evalnexa.onrender.com | —   |
| Backend API (Local)| http://localhost:5000   | (Dev)     |

---

## API Reference

### Authentication

| Method | Endpoint         | Description       |
|--------|------------------|-------------------|
| POST   | /api/auth/login  | Login             |
| GET    | /api/auth/me     | Get current user  |
| POST   | /api/auth/logout | Logout            |

### Users (ADMIN only)

| Method | Endpoint             | Description         |
|--------|----------------------|---------------------|
| GET    | /api/users           | List all users      |
| POST   | /api/users           | Create user         |
| GET    | /api/users/examiners | List examiners      |
| GET    | /api/users/:id       | Get user            |
| PATCH  | /api/users/:id       | Update user         |

### Exams (ADMIN)

| Method | Endpoint                    | Description      |
|--------|-----------------------------|------------------|
| GET    | /api/exams                  | List exams       |
| POST   | /api/exams                  | Create exam      |
| GET    | /api/exams/stats/dashboard  | Dashboard stats  |
| GET    | /api/exams/:id              | Get exam detail  |
| PATCH  | /api/exams/:id              | Update exam      |
| DELETE | /api/exams/:id              | Delete draft     |

### Answer Books

| Method | Endpoint                       | Description        |
|--------|--------------------------------|--------------------|
| GET    | /api/answer-books              | List (ADMIN)       |
| POST   | /api/answer-books              | Register (ADMIN)   |
| GET    | /api/answer-books/my           | My books (EXAMINER)|
| GET    | /api/answer-books/:id          | Get detail         |
| PATCH  | /api/answer-books/:id          | Update (ADMIN)     |
| POST   | /api/answer-books/:id/assign   | Assign (ADMIN)     |

### Evaluations

| Method | Endpoint                        | Description        |
|--------|---------------------------------|--------------------|
| GET    | /api/evaluations                | List               |
| GET    | /api/evaluations/:id            | Get detail         |
| POST   | /api/evaluations/:id/start      | Start (EXAMINER)   |
| PATCH  | /api/evaluations/:id            | Save progress      |
| POST   | /api/evaluations/:id/submit     | Submit (EXAMINER)  |

### Moderation (MODERATOR/ADMIN)

| Method | Endpoint                       | Description      |
|--------|--------------------------------|------------------|
| GET    | /api/moderation                | Queue            |
| GET    | /api/moderation/stats          | Stats            |
| GET    | /api/moderation/:id            | Detail           |
| POST   | /api/moderation/:id/approve    | Approve          |
| POST   | /api/moderation/:id/return     | Return           |

### Audit (ADMIN/MODERATOR)

| Method | Endpoint          | Description           |
|--------|-------------------|-----------------------|
| GET    | /api/audit-logs   | Paginated audit trail |

---

## Socket.IO Events

All events carry a `timestamp` field.

| Event                      | Emitted When                        | Rooms                       |
|----------------------------|-------------------------------------|-----------------------------|
| `exam.created`             | Admin creates exam                  | All                         |
| `exam.updated`             | Admin updates exam                  | All                         |
| `answerbook.created`       | Admin registers answer book         | All                         |
| `answerbook.assigned`      | Admin assigns to examiner           | All + user:{examinerId}     |
| `answerbook.status.changed`| Status changes                      | All                         |
| `evaluation.started`       | Examiner starts evaluation          | All                         |
| `evaluation.updated`       | Examiner saves progress             | All                         |
| `evaluation.submitted`     | Examiner submits                    | All + role:moderator        |
| `moderation.approved`      | Moderator approves                  | All                         |
| `moderation.returned`      | Moderator returns                   | All                         |
| `user.created`             | Admin creates user                  | All                         |

### Socket Rooms

| Room               | Members              |
|--------------------|----------------------|
| `role:admin`       | All ADMIN users      |
| `role:examiner`    | All EXAMINER users   |
| `role:moderator`   | All MODERATOR users  |
| `user:{userId}`    | Specific user        |
| `exam:{examId}`    | Subscribers of exam  |

---

## Authentication & Security

- Passwords are hashed with **bcrypt** (cost factor 12). Plain-text passwords are never stored.
- **JWT** tokens are issued on login. Token is stored in both HTTP-only cookie and localStorage for cross-origin support.
- All backend routes verify the role from the **database**, not from the token payload.
- Examiner isolation: examiners can only access their own assigned answer books and evaluations.
- Input validation via **Zod** on all mutating endpoints.
- `passwordHash` field is never returned in any API response.

---

## Role Permissions

| Action                      | ADMIN | EXAMINER | MODERATOR |
|-----------------------------|:-----:|:--------:|:---------:|
| Create exams                | ✓     |          |           |
| View all exams              | ✓     |          | ✓         |
| Register answer books       | ✓     |          |           |
| Assign answer books         | ✓     |          |           |
| View own answer books       |       | ✓        |           |
| Start evaluation            |       | ✓        |           |
| Submit evaluation           |       | ✓        |           |
| View moderation queue       | ✓     |          | ✓         |
| Approve/Return evaluation   | ✓     |          | ✓         |
| View audit trail            | ✓     |          | ✓         |
| Manage users                | ✓     |          |           |

---

## Database Collections

| Collection   | Purpose                              |
|--------------|--------------------------------------|
| `users`      | All platform users with roles        |
| `exams`      | Examination records                  |
| `answerbooks`| Answer book register                 |
| `evaluations`| Evaluation lifecycle records         |
| `auditlogs`  | Immutable audit trail (append-only)  |

---

## Future AI Extension Points

The following service boundaries are defined but not yet implemented:

```
backend/src/services/ (future extension points)
├── ImageQualityService.ts
├── OCRService.ts
├── HandwritingRecognitionService.ts
├── AnswerSegmentationService.ts
├── EvaluationAssistantService.ts
└── AnomalyDetectionService.ts
```

The document viewer area in the Examiner Workspace is an explicit integration point for the imaging pipeline.

---

## Production Build

```bash
pnpm build
```

Builds all three frontend apps and the server TypeScript.

---

## License

Private — EvalNexa Examination Platform © 2024
