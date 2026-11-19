# Gradified — AI OCR Paper Grading & Assessment System

A full-stack web application integrating the **`ocr-service`** grading engine with **Django (REST Framework)** and **React (Vite)**.

---

## 🌟 Key Capabilities & Features

### 1. Two-Tier Role-Based Architecture
- **Admin (Platform Onboarder)**:
  - Onboard new schools and teaching staff (with automatic or manual verification).
  - Manage school status (active, verified, de-verified).
  - Platform-wide analytics (total schools, exams created, graded answer sheets, average student scores).
- **School (Teachers)**:
  - Select and create subjects (e.g. Physics, Mathematics, Chemistry, Computer Science, English).
  - Create Exams: Upload Question Papers & Answer Rubric Keys.
  - Configure Question Rubrics: Multiple Choice (`CHOICE`), Numeric with tolerances (`NUMERIC`), and Semantic criteria (`DIRECT`).
  - Upload Student Answer Sheets (Scanned PDFs, Images, Text, or OCR exports).
  - Instant automated grading powered by the **`ocr-service`** engine.
  - Detailed score reports with question-by-question marks, rubric performance levels, and evaluator rationales.

### 2. Email Verification & Authentication
- Secure JWT-based authentication (SimpleJWT).
- User signup with role selection (`school` or `admin`).
- 6-digit numeric OTP + UUID verification token workflow.
- Email verification gateway protecting access to the assessment workspace.
- Pre-seeded Demo Accounts for immediate evaluation:
  - **Teacher / School Demo**: `school@greenwood.edu` / `school123`
  - **Platform Admin Demo**: `admin@gradified.com` / `admin123`

### 3. Direct Ingress & Grading Engine Integration
- Complies strictly with the **Normalized Evidence Wire v1** schema (`gradified.normalized_answer_evidence.v1.schema.json`).
- Uses `parse_normalized_evidence_payload` with `NormalizedEvidenceAdmissionPolicy` from `ocr-service/src/grading/integration/evidence_ingress.py`.
- Scores questions using:
  - `grading.contracts.choice` & `choice_evaluator` for multiple choice questions.
  - `grading.numeric_evaluator` for numeric questions with tolerances.
  - `grading.semantic_evaluator` & `rubric` for direct text questions.
  - Exact decimal arithmetic via `grading.scoring.arithmetic.exact_sum` and `ScoringDecimal`.

---

## 🚀 Quick Start Guide

### 1. Run the Backend (Django)
```bash
cd backend
python seed_data.py   # Seeds default subjects, demo admin, teacher, and sample exam
python manage.py runserver 127.0.0.1:8000
```

### 2. Run the Frontend (React + Vite)
In a separate terminal:
```bash
cd frontend
npm run dev
```
Open **[http://localhost:5173](http://localhost:5173)** in your browser!

*(Alternatively, the production build of the React app is also bundled directly inside Django at **http://127.0.0.1:8000**).*

---

## 🧪 Running Integration Tests

To run the automated Django test suite covering signup, email verification, admin onboarding, and full OCR grading:
```bash
cd backend
python manage.py test api
```

To run the `ocr-service` unit and integration tests:
```bash
cd ocr-service
set "PYTHONPATH=src;."
python -m pytest tests/integration/test_family_first_scored_cas.py
python docs/examples/paper_operation_demo.py
python docs/examples/ocr_admission_demo.py
```

