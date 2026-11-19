import React, { useState, useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { subjectAPI, examAPI, submissionAPI } from '../../api';
import { CreateExamModal } from './CreateExamModal';
import { UploadAnswerSheetModal } from './UploadAnswerSheetModal';
import { GradingResultModal } from './GradingResultModal';
import {
  PlusIcon,
  BookIcon,
  UploadIcon,
  CheckCircleIcon,
  SchoolIcon,
  CpuIcon,
  RefreshIcon,
  FileTextIcon,
} from '../Icons';

export const TeacherDashboard = ({ activeTab = 'dashboard' }) => {
  const { user } = useAuth();
  const [subjects, setSubjects] = useState([]);
  const [selectedSubjectId, setSelectedSubjectId] = useState('');
  const [exams, setExams] = useState([]);
  const [submissions, setSubmissions] = useState([]);
  const [loading, setLoading] = useState(true);

  const [showCreateExam, setShowCreateExam] = useState(false);
  const [activeExamForUpload, setActiveExamForUpload] = useState(null);
  const [selectedSubmissionForView, setSelectedSubmissionForView] = useState(null);
  const [regradingId, setRegradingId] = useState(null);

  const loadInitialData = async () => {
    try {
      setLoading(true);
      const [subsData, examsData, recentsData] = await Promise.all([
        subjectAPI.getAll(),
        examAPI.getAll(),
        submissionAPI.getRecent(),
      ]);
      setSubjects(subsData);
      setExams(examsData);
      setSubmissions(recentsData);
    } catch (err) {
      console.error('Failed to load teacher workspace:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadInitialData();
  }, []);

  // Live polling for asynchronous background OCR workers:
  // Automatically refreshes submissions when any task is in PROCESSING state
  useEffect(() => {
    const hasProcessing = submissions.some(s => s.status === 'PROCESSING');
    if (!hasProcessing) return;

    const interval = setInterval(async () => {
      try {
        const recent = await submissionAPI.getRecent();
        setSubmissions(recent);
        examAPI.getAll(selectedSubjectId || null).then(setExams).catch(() => {});
      } catch (err) {
        console.warn('Background worker polling error:', err);
      }
    }, 2500);

    return () => clearInterval(interval);
  }, [submissions, selectedSubjectId]);

  const handleFilterBySubject = async (subId) => {
    setSelectedSubjectId(subId);
    try {
      const filtered = await examAPI.getAll(subId || null);
      setExams(filtered);
    } catch (err) {
      console.error('Error filtering exams:', err);
    }
  };

  const handleExamCreated = (newExam) => {
    setExams([newExam, ...exams]);
  };

  const handleSubjectCreated = (newSubject) => {
    setSubjects([...subjects, newSubject]);
  };

  const handleSubmissionGraded = (gradedSub) => {
    setSubmissions([gradedSub, ...submissions.filter(s => s.id !== gradedSub.id)]);
    examAPI.getAll(selectedSubjectId || null).then(setExams);
    setSelectedSubmissionForView(gradedSub);
  };

  const handleReGrade = async (subId) => {
    setRegradingId(subId);
    try {
      const updated = await submissionAPI.grade(subId);
      setSubmissions(submissions.map(s => s.id === subId ? updated : s));
      setSelectedSubmissionForView(updated);
    } catch (err) {
      alert('Re-grading failed: ' + err.message);
    } finally {
      setRegradingId(null);
    }
  };

  const handleViewSubmission = async (subId) => {
    try {
      const full = await submissionAPI.getById(subId);
      setSelectedSubmissionForView(full);
    } catch (err) {
      alert('Failed to load submission: ' + err.message);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Top Banner */}
      <div className="bg-logo-ink border border-feature-eval-border rounded-xl p-6 sm:p-8 text-white flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="space-y-2">
          <div className="flex items-center space-x-2">
            <span className="font-mono px-2.5 py-0.5 rounded text-[11px] font-medium bg-white/10 text-slate-200 border border-white/15">
              {user.organization_name || user.school_name || 'Academic Organization'}
            </span>
            <span className="font-mono px-2.5 py-0.5 rounded text-[11px] font-medium bg-logo-sage-deep/40 text-logo-sage border border-logo-sage/40">
              ROLE 3 · INSTRUCTOR
            </span>
          </div>
          <h1 className="font-display text-2xl sm:text-3xl font-bold tracking-tight">
            Welcome back, {user.username || 'Instructor'}
          </h1>
          <p className="text-sm text-slate-300 max-w-xl">
            Select a subject, upload question papers & rubrics, then upload student answer booklets to grade and view results via ocr-service.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => setShowCreateExam(true)}
            className="px-5 py-3 rounded-xl bg-brand-primary hover:bg-brand-primary-hover text-white font-bold text-xs sm:text-sm shadow-sm transition flex items-center space-x-2"
          >
            <PlusIcon className="w-4 h-4" />
            <span>Create Exam & Upload Paper</span>
          </button>
        </div>
      </div>

      {/* Subject Filter Bar */}
      <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center space-x-2 overflow-x-auto pb-1 sm:pb-0">
          <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-slate-500 mr-1">
            Subject:
          </span>
          <button
            onClick={() => handleFilterBySubject('')}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition whitespace-nowrap ${
              selectedSubjectId === ''
                ? 'bg-brand-primary text-white shadow-2xs'
                : 'bg-slate-100 text-slate-600 hover:text-slate-900'
            }`}
          >
            All Subjects
          </button>
          {subjects.map((sub) => (
            <button
              key={sub.id}
              onClick={() => handleFilterBySubject(sub.id)}
              className={`px-3 py-1.5 rounded-xl text-xs font-bold transition whitespace-nowrap ${
                selectedSubjectId === sub.id
                  ? 'bg-brand-primary text-white shadow-2xs'
                  : 'bg-slate-100 text-slate-600 hover:text-slate-900'
              }`}
            >
              {sub.name}
            </button>
          ))}
        </div>

        <span className="text-xs text-slate-400">
          Showing {exams.length} active exam{exams.length === 1 ? '' : 's'}
        </span>
      </div>

      {/* Exams Grid */}
      {(activeTab === 'dashboard' || activeTab === 'exams') && (
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-display text-lg font-bold text-logo-ink">
            Active Question Papers & Answer Rubrics
          </h2>
        </div>

        {loading ? (
          <div className="p-12 text-center text-slate-400 bg-white rounded-2xl border border-slate-200">
            Loading examination records...
          </div>
        ) : exams.length === 0 ? (
          <div className="p-12 text-center bg-white rounded-xl border border-dashed border-slate-300 space-y-3">
            <h3 className="font-display text-base font-bold text-slate-700">No exams created yet for this subject</h3>
            <p className="text-xs text-slate-500 max-w-md mx-auto leading-relaxed">
              Create an exam, define question specifications and rubrics, then ingest student answer booklets for OCR evaluation.
            </p>
            <button
              onClick={() => setShowCreateExam(true)}
              className="mt-2 px-4 py-2 bg-brand-primary hover:bg-brand-primary-hover text-white rounded-lg text-xs font-semibold transition"
            >
              + Create Question Paper
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {exams.map((exam) => (
              <div
                key={exam.id}
                className="bg-white rounded-xl border border-slate-200 shadow-xs p-6 hover:shadow-md transition space-y-4 flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-mono px-2 py-0.5 rounded text-[11px] font-medium bg-logo-sage-soft text-logo-sage-deep border border-logo-sage-border">
                      {exam.subject_name}
                    </span>
                    <span className="text-xs font-semibold text-slate-500">
                      Max: {exam.total_marks} pts
                    </span>
                  </div>

                  <h3 className="font-bold text-base text-slate-900 tracking-tight">
                    {exam.title}
                  </h3>

                  <p className="text-xs text-slate-500 mt-1 line-clamp-2">
                    {exam.question_paper_text || 'Structured questions with choice, numeric tolerances, and semantic criteria rubrics.'}
                  </p>
                </div>

                <div className="pt-4 border-t border-slate-100 space-y-3">
                  <div className="flex items-center justify-between text-xs text-slate-600">
                    <span>Graded Answer Sheets:</span>
                    <span className="font-bold text-brand-primary bg-blue-50 px-2 py-0.5 rounded">
                      {exam.submissions_count} submitted
                    </span>
                  </div>

                  {exam.average_score && (
                    <div className="flex items-center justify-between text-xs text-slate-600">
                      <span>Class Average:</span>
                      <span className="font-bold text-emerald-600">
                        {exam.average_score} / {exam.total_marks}
                      </span>
                    </div>
                  )}

                  <button
                    onClick={() => setActiveExamForUpload(exam)}
                    className="w-full py-2.5 px-4 rounded-xl bg-brand-primary hover:bg-brand-primary-hover text-white font-semibold text-xs shadow-2xs flex items-center justify-center space-x-1.5 transition"
                  >
                    <UploadIcon className="w-3.5 h-3.5" />
                    <span>Upload Answer Booklet & Grade</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      )}

      {/* Recent Graded Answer Booklets Table */}
      {(activeTab === 'dashboard' || activeTab === 'grading') && (
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xs overflow-hidden">
        <div className="p-5 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-slate-900 flex items-center">
              <CheckCircleIcon className="w-5 h-5 mr-2 text-emerald-600" />
              Recent OCR Evaluated Submissions
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Instant scores, criteria breakdowns, and evaluation reports returned by ocr-service engine.
            </p>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-600">
            <thead className="bg-slate-50 text-slate-700 text-xs uppercase font-semibold border-b border-slate-200">
              <tr>
                <th className="px-6 py-3.5">Student / Roll ID</th>
                <th className="px-6 py-3.5">Examination</th>
                <th className="px-6 py-3.5 text-center">Score</th>
                <th className="px-6 py-3.5 text-center">Percentage</th>
                <th className="px-6 py-3.5 text-center">Grade</th>
                <th className="px-6 py-3.5 text-center">Engine Status</th>
                <th className="px-6 py-3.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {submissions.length === 0 ? (
                <tr>
                  <td colSpan="7" className="px-6 py-10 text-center text-slate-400">
                    No answer sheets graded yet. Click "Upload Answer Sheet & Grade" on any exam above.
                  </td>
                </tr>
              ) : (
                submissions.map((sub) => (
                  <tr key={sub.id} className="hover:bg-slate-50/80 transition">
                    <td className="px-6 py-4">
                      <div>
                        <p className="font-bold text-slate-900">{sub.student_name}</p>
                        <p className="text-xs font-mono text-slate-400">{sub.student_id}</p>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <p className="text-xs font-semibold text-slate-800">{sub.exam_title}</p>
                      <p className="text-[11px] text-slate-400">{sub.subject_name}</p>
                    </td>
                    <td className="px-6 py-4 text-center">
                      <span className="font-extrabold text-slate-900 text-sm">
                        {sub.total_score ?? '-'}
                      </span>
                      <span className="text-xs text-slate-400 font-medium"> / {sub.max_possible_score ?? '-'}</span>
                    </td>
                    <td className="px-6 py-4 text-center">
                      <span className="font-bold text-slate-800">
                        {sub.percentage != null ? `${sub.percentage}%` : '-'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-center">
                      {sub.grade_letter ? (
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-extrabold ${
                          sub.grade_letter.startsWith('A') ? 'bg-emerald-100 text-emerald-800 border border-emerald-200' :
                          sub.grade_letter === 'B' ? 'bg-blue-100 text-blue-800 border border-blue-200' :
                          sub.grade_letter === 'C' ? 'bg-amber-100 text-amber-800 border border-amber-200' :
                          'bg-rose-100 text-rose-800 border border-rose-200'
                        }`}>
                          {sub.grade_letter}
                        </span>
                      ) : '-'}
                    </td>
                    <td className="px-6 py-4 text-center">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold ${
                        sub.status === 'GRADED' ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' :
                        sub.status === 'PROCESSING' ? 'bg-amber-50 text-amber-800 border border-amber-200 animate-pulse' :
                        sub.status === 'FAILED' ? 'bg-rose-50 text-rose-800 border border-rose-200' :
                        'bg-slate-100 text-slate-700 border border-slate-200'
                      }`} title={sub.error_message || sub.status}>
                        <CpuIcon className={`w-3 h-3 mr-1 ${sub.status === 'PROCESSING' ? 'animate-spin' : ''}`} />
                        {sub.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right space-x-2">
                      <button
                        onClick={() => handleViewSubmission(sub.id)}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-50 text-brand-primary hover:bg-blue-100 transition"
                      >
                        View Report
                      </button>
                      <button
                        onClick={() => handleReGrade(sub.id)}
                        disabled={regradingId === sub.id}
                        className="px-2.5 py-1.5 rounded-lg text-xs font-semibold border border-slate-200 text-slate-600 hover:bg-slate-100 transition"
                        title="Re-run grading engine"
                      >
                        <RefreshIcon className={`w-3.5 h-3.5 ${regradingId === sub.id ? 'animate-spin' : ''}`} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      )}

      {showCreateExam && (
        <CreateExamModal
          subjects={subjects}
          onExamCreated={handleExamCreated}
          onSubjectCreated={handleSubjectCreated}
          onClose={() => setShowCreateExam(false)}
        />
      )}

      {activeExamForUpload && (
        <UploadAnswerSheetModal
          exam={activeExamForUpload}
          onClose={() => setActiveExamForUpload(null)}
          onGraded={handleSubmissionGraded}
        />
      )}

      {selectedSubmissionForView && (
        <GradingResultModal
          submission={selectedSubmissionForView}
          onClose={() => setSelectedSubmissionForView(null)}
        />
      )}
    </div>
  );
};
