import React, { useState, useEffect } from 'react';
import { examAPI, subjectAPI } from '../../api';
import {
  PlusIcon,
  BookIcon,
  UploadIcon,
  TrashIcon,
  CloseIcon,
  AlertIcon,
} from '../Icons';

export const CreateExamModal = ({ subjects, onExamCreated, onClose, onSubjectCreated }) => {
  const [title, setTitle] = useState('');
  const [subjectId, setSubjectId] = useState(subjects[0]?.id || '');
  const [manualTotal, setManualTotal] = useState(false);
  const [totalMarks, setTotalMarks] = useState(10);
  const [passingMarks, setPassingMarks] = useState(4);

  const [questionFile, setQuestionFile] = useState(null);
  const [questionText, setQuestionText] = useState('');
  const [answerFile, setAnswerFile] = useState(null);
  const [answerText, setAnswerText] = useState('');

  const [questions, setQuestions] = useState([
    {
      question_id: 'Q1',
      question_text: '',
      type: 'DIRECT',
      max_marks: 10,
      model_answer: '',
      rubric: { criteria: [] }
    }
  ]);

  const computedTotalMarks = questions.reduce((sum, q) => sum + (parseFloat(q.max_marks) || 0), 0);

  useEffect(() => {
    if (!manualTotal) {
      setTotalMarks(computedTotalMarks);
      setPassingMarks(Math.round(computedTotalMarks * 0.4 * 10) / 10);
    }
  }, [computedTotalMarks, manualTotal]);

  const [showNewSubject, setShowNewSubject] = useState(false);
  const [newSubName, setNewSubName] = useState('');
  const [newSubCode, setNewSubCode] = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleAddQuestion = () => {
    const nextNum = questions.length + 1;
    setQuestions([
      ...questions,
      {
        question_id: `Q${nextNum}`,
        question_text: '',
        type: 'DIRECT',
        max_marks: 10,
        model_answer: '',
        rubric: { criteria: [] }
      }
    ]);
  };

  const handleRemoveQuestion = (idx) => {
    setQuestions(questions.filter((_, i) => i !== idx));
  };

  const handleUpdateQuestion = (idx, field, value) => {
    const updated = [...questions];
    updated[idx] = { ...updated[idx], [field]: value };
    setQuestions(updated);
  };

  const handleCreateSubjectInline = async (e) => {
    e.preventDefault();
    if (!newSubName.trim()) return;

    try {
      const created = await subjectAPI.create({
        name: newSubName.trim(),
        code: newSubCode.trim(),
      });
      onSubjectCreated(created);
      setSubjectId(created.id);
      setShowNewSubject(false);
      setNewSubName('');
      setNewSubCode('');
    } catch (err) {
      alert('Failed to create subject: ' + err.message);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!title.trim() || !subjectId) {
      setError('Please provide Exam Title and select a Subject.');
      return;
    }

    setError('');
    setLoading(true);

    try {
      const formData = new FormData();
      formData.append('title', title.trim());
      formData.append('subject_id', subjectId);
      formData.append('total_marks', totalMarks);
      formData.append('passing_marks', passingMarks);
      formData.append('questions_data', JSON.stringify(questions));

      if (questionFile) formData.append('question_paper_file', questionFile);
      if (questionText.trim()) formData.append('question_paper_text', questionText.trim());
      if (answerFile) formData.append('answer_paper_file', answerFile);
      if (answerText.trim()) formData.append('answer_paper_text', answerText.trim());

      const res = await examAPI.create(formData);
      onExamCreated(res);
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to create exam');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-white rounded-xl max-w-3xl w-full p-6 sm:p-7 shadow-xl border border-slate-200 my-8 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between pb-4 border-b border-slate-100">
          <div>
            <h3 className="font-display font-bold text-lg text-logo-ink">Create Exam & Define Rubric</h3>
            <p className="text-xs text-slate-500 mt-0.5">Configure question specifications and grading criteria.</p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100 transition"
          >
            <CloseIcon className="w-5 h-5" />
          </button>
        </div>

        {error && (
          <div className="my-4 p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start space-x-2">
            <AlertIcon className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6 mt-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700">
                  Select Subject *
                </label>
                <button
                  type="button"
                  onClick={() => setShowNewSubject(!showNewSubject)}
                  className="text-[11px] text-brand-primary font-semibold hover:underline"
                >
                  {showNewSubject ? 'Select Existing' : '+ New Subject'}
                </button>
              </div>

              {showNewSubject ? (
                <div className="flex space-x-2">
                  <input
                    type="text"
                    value={newSubName}
                    onChange={(e) => setNewSubName(e.target.value)}
                    placeholder="Subject Name (e.g. Biology)"
                    className="flex-1 px-3 py-2 text-xs rounded-xl border border-slate-300"
                  />
                  <button
                    type="button"
                    onClick={handleCreateSubjectInline}
                    className="px-3 py-2 bg-brand-primary text-white rounded-xl text-xs font-semibold"
                  >
                    Add
                  </button>
                </div>
              ) : (
                <select
                  value={subjectId}
                  onChange={(e) => setSubjectId(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-primary bg-white"
                >
                  <option value="">-- Choose Subject --</option>
                  {subjects.map((sub) => (
                    <option key={sub.id} value={sub.id}>
                      {sub.name} {sub.code ? `(${sub.code})` : ''}
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                Exam Title *
              </label>
              <input
                type="text"
                required
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Midterm Physics & Mechanics Exam"
                className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-primary"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700">
                  Total Exam Marks
                </label>
                <span className="font-mono text-[10px] text-logo-sage-deep font-semibold">
                  Sum of questions: {computedTotalMarks} pts
                </span>
              </div>
              <input
                type="number"
                min="1"
                step="0.5"
                value={totalMarks}
                onChange={(e) => {
                  setTotalMarks(e.target.value);
                  setManualTotal(true);
                }}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-primary font-mono font-semibold"
              />
            </div>
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700">
                  Passing Marks
                </label>
                <span className="font-mono text-[10px] text-slate-400">
                  (40% standard: {Math.round(computedTotalMarks * 0.4 * 10) / 10} pts)
                </span>
              </div>
              <input
                type="number"
                min="0"
                step="0.5"
                value={passingMarks}
                onChange={(e) => setPassingMarks(e.target.value)}
                className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-primary font-mono font-semibold"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-800 mb-1 flex items-center">
                <UploadIcon className="w-3.5 h-3.5 mr-1 text-brand-primary" />
                Upload Question Paper (PDF / Doc / Image)
              </label>
              <input
                type="file"
                onChange={(e) => setQuestionFile(e.target.files[0] || null)}
                className="text-xs text-slate-600 file:mr-2 file:py-1 file:px-2.5 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-blue-50 file:text-brand-primary hover:file:bg-blue-100"
              />
              <textarea
                rows={2}
                value={questionText}
                onChange={(e) => setQuestionText(e.target.value)}
                placeholder="Or paste Question Paper content..."
                className="w-full mt-2 p-2 text-xs rounded-lg border border-slate-300 bg-white"
              />
            </div>

            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-800 mb-1 flex items-center">
                <UploadIcon className="w-3.5 h-3.5 mr-1 text-emerald-600" />
                Upload Answer Paper / Rubric Key
              </label>
              <input
                type="file"
                onChange={(e) => setAnswerFile(e.target.files[0] || null)}
                className="text-xs text-slate-600 file:mr-2 file:py-1 file:px-2.5 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-emerald-50 file:text-emerald-700 hover:file:bg-emerald-100"
              />
              <textarea
                rows={2}
                value={answerText}
                onChange={(e) => setAnswerText(e.target.value)}
                placeholder="Or paste Answer Paper / Rubric Key..."
                className="w-full mt-2 p-2 text-xs rounded-lg border border-slate-300 bg-white"
              />
            </div>
          </div>

          <div className="pt-2">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h4 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
                  Configured Questions & Evaluator Rubrics ({questions.length})
                </h4>
                <p className="text-xs text-slate-500">
                  Engine supports CHOICE (MCQ), NUMERIC (tolerances), and DIRECT (semantic criteria rubrics).
                </p>
              </div>
              <button
                type="button"
                onClick={handleAddQuestion}
                className="inline-flex items-center space-x-1 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 rounded-lg text-xs font-semibold text-slate-700 transition"
              >
                <PlusIcon className="w-3.5 h-3.5" />
                <span>Add Question</span>
              </button>
            </div>

            <div className="space-y-3">
              {questions.map((q, idx) => (
                <div key={idx} className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <input
                        type="text"
                        value={q.question_id}
                        onChange={(e) => handleUpdateQuestion(idx, 'question_id', e.target.value)}
                        className="w-16 px-2 py-1 text-xs font-mono font-bold bg-white border border-slate-300 rounded"
                      />
                      <select
                        value={q.type}
                        onChange={(e) => handleUpdateQuestion(idx, 'type', e.target.value)}
                        className="px-2 py-1 text-xs font-bold rounded bg-white border border-slate-300"
                      >
                        <option value="CHOICE">CHOICE (MCQ)</option>
                        <option value="NUMERIC">NUMERIC (Tolerances)</option>
                        <option value="DIRECT">DIRECT (Semantic Rubric)</option>
                      </select>
                    </div>

                    <div className="flex items-center space-x-2">
                      <label className="text-xs text-slate-500 font-semibold">Max Marks:</label>
                      <input
                        type="number"
                        value={q.max_marks}
                        onChange={(e) => handleUpdateQuestion(idx, 'max_marks', parseFloat(e.target.value) || 0)}
                        className="w-16 px-2 py-1 text-xs font-bold bg-white border border-slate-300 rounded text-center"
                      />
                      {questions.length > 1 && (
                        <button
                          type="button"
                          onClick={() => handleRemoveQuestion(idx)}
                          className="p-1 text-slate-400 hover:text-rose-600 transition"
                        >
                          <TrashIcon className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </div>

                  <input
                    type="text"
                    value={q.question_text}
                    onChange={(e) => handleUpdateQuestion(idx, 'question_text', e.target.value)}
                    placeholder="Question prompt..."
                    className="w-full px-3 py-1.5 text-xs rounded-lg border border-slate-300 bg-white"
                  />

                  {q.type === 'CHOICE' && (
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <label className="text-[11px] font-semibold text-slate-600">Correct Option:</label>
                        <input
                          type="text"
                          value={q.choice_spec?.correct_option || ''}
                          onChange={(e) => handleUpdateQuestion(idx, 'choice_spec', {
                            ...q.choice_spec,
                            correct_option: e.target.value.toUpperCase()
                          })}
                          placeholder="e.g. B"
                          className="w-full px-2 py-1 font-bold text-center border border-slate-300 rounded bg-white"
                        />
                      </div>
                    </div>
                  )}

                  {q.type === 'NUMERIC' && (
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <label className="text-[11px] font-semibold text-slate-600">Expected Value:</label>
                        <input
                          type="number"
                          step="any"
                          value={q.numeric_spec?.expected_value || ''}
                          onChange={(e) => handleUpdateQuestion(idx, 'numeric_spec', {
                            ...q.numeric_spec,
                            expected_value: parseFloat(e.target.value)
                          })}
                          placeholder="e.g. 42.0"
                          className="w-full px-2 py-1 border border-slate-300 rounded bg-white"
                        />
                      </div>
                      <div>
                        <label className="text-[11px] font-semibold text-slate-600">Tolerance (+/-):</label>
                        <input
                          type="number"
                          step="any"
                          value={q.numeric_spec?.tolerance || 0}
                          onChange={(e) => handleUpdateQuestion(idx, 'numeric_spec', {
                            ...q.numeric_spec,
                            tolerance: parseFloat(e.target.value)
                          })}
                          className="w-full px-2 py-1 border border-slate-300 rounded bg-white"
                        />
                      </div>
                    </div>
                  )}

                  {q.type === 'DIRECT' && (
                    <div>
                      <label className="text-[11px] font-semibold text-slate-600">Model Answer / Criteria Concept:</label>
                      <textarea
                        rows={2}
                        value={q.model_answer || ''}
                        onChange={(e) => handleUpdateQuestion(idx, 'model_answer', e.target.value)}
                        placeholder="Expected explanation or key concepts..."
                        className="w-full p-2 text-xs border border-slate-300 rounded bg-white"
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="flex items-center justify-end space-x-3 pt-4 border-t border-slate-100">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-5 py-2.5 rounded-xl bg-brand-primary hover:bg-brand-primary-hover text-white font-semibold text-xs shadow-sm transition disabled:opacity-50"
            >
              {loading ? 'Creating Exam & Question Paper...' : 'Save & Publish Exam'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
