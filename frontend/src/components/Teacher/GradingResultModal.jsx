import React, { useState, useEffect } from 'react';
import {
  CheckCircleIcon,
  CpuIcon,
  PrinterIcon,
  CloseIcon,
  RefreshIcon,
} from '../Icons';
import { submissionAPI } from '../../api';

export const GradingResultModal = ({ submission: initialSubmission, onClose, onUpdated }) => {
  if (!initialSubmission) return null;

  const [currentSub, setCurrentSub] = useState(initialSubmission);
  const [regrading, setRegrading] = useState(false);

  useEffect(() => {
    setCurrentSub(initialSubmission);
  }, [initialSubmission]);

  // Active polling if current submission is in background PROCESSING state
  useEffect(() => {
    if (currentSub?.status !== 'PROCESSING') return;

    const interval = setInterval(async () => {
      try {
        const fresh = await submissionAPI.getById(currentSub.id);
        if (fresh) {
          setCurrentSub(fresh);
          if (onUpdated) onUpdated(fresh);
        }
      } catch (err) {
        console.warn('Polling error for submission:', err);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [currentSub?.id, currentSub?.status, onUpdated]);

  const handleRetry = async () => {
    setRegrading(true);
    try {
      const fresh = await submissionAPI.grade(currentSub.id);
      setCurrentSub(fresh);
      if (onUpdated) onUpdated(fresh);
    } catch (err) {
      alert('Retry failed: ' + err.message);
    } finally {
      setRegrading(false);
    }
  };

  const details = currentSub.grading_details || {};
  const questionResults = details.question_results || [];
  const percentage = currentSub.percentage ?? details.percentage ?? 0;
  const grade = currentSub.grade_letter || details.grade_letter || 'N/A';
  const totalScore = currentSub.total_score ?? details.total_score ?? 0;
  const maxPossible = currentSub.max_possible_score ?? details.max_possible_score ?? 0;
  const isProcessing = currentSub.status === 'PROCESSING';
  const isFailed = currentSub.status === 'FAILED';

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-white rounded-2xl max-w-4xl w-full p-6 sm:p-8 shadow-2xl border border-slate-200 my-8 max-h-[90vh] overflow-y-auto">
        <div className="flex items-start justify-between pb-6 border-b border-slate-100">
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-mono px-2 py-0.5 rounded text-[11px] font-medium bg-logo-sage-soft text-logo-sage-deep border border-logo-sage-border">
                OCR Engine Telemetry
              </span>
              <span className="text-xs font-mono text-slate-400">Ref: {currentSub.submission_ref}</span>
            </div>
            <h2 className="font-display text-2xl font-bold text-logo-ink mt-1">
              Assessment Results: {currentSub.student_name}
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Roll / ID: <span className="font-mono font-semibold text-slate-700">{currentSub.student_id}</span> · Exam:{' '}
              <span className="font-semibold text-slate-700">{currentSub.exam_title}</span>
            </p>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={handlePrint}
              aria-label="Print Grade Sheet"
              className="p-2 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition"
              title="Print Grade Sheet"
            >
              <PrinterIcon className="w-4 h-4" />
            </button>
            <button
              onClick={onClose}
              aria-label="Close Modal"
              className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition"
            >
              <CloseIcon className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 my-6">
          <div className="bg-white p-4 rounded-lg border border-slate-200">
            <p className="font-mono text-[10px] uppercase tracking-wider text-slate-400">Total Score</p>
            <div className="mt-1 flex items-baseline space-x-1">
              <span className="font-mono text-2xl font-bold text-logo-ink">{totalScore}</span>
              <span className="font-mono text-xs text-slate-400">/ {maxPossible}</span>
            </div>
          </div>

          <div className="bg-white p-4 rounded-lg border border-slate-200">
            <p className="font-mono text-[10px] uppercase tracking-wider text-slate-400">Percentage</p>
            <div className="mt-1 flex items-baseline">
              <span className="font-mono text-2xl font-bold text-logo-sage-deep">{percentage}%</span>
            </div>
          </div>

          <div className="bg-white p-4 rounded-lg border border-slate-200">
            <p className="font-mono text-[10px] uppercase tracking-wider text-slate-400">Assigned Grade</p>
            <div className="mt-1 flex items-baseline">
              <span className="font-mono text-2xl font-bold text-logo-ink">{grade}</span>
            </div>
          </div>

          <div className={`p-4 rounded-lg border ${
            isFailed ? 'bg-rose-50/50 border-rose-200' :
            isProcessing ? 'bg-amber-50/50 border-amber-200' :
            'bg-white border-slate-200'
          }`}>
            <p className={`font-mono text-[10px] uppercase tracking-wider ${
              isFailed ? 'text-rose-500' : isProcessing ? 'text-amber-600' : 'text-slate-400'
            }`}>Evaluation Status</p>
            <div className="mt-1 flex items-center space-x-1.5">
              <span className={`w-2 h-2 rounded-full ${
                isFailed ? 'bg-rose-500' :
                isProcessing ? 'bg-amber-500 animate-ping' :
                'bg-logo-sage-deep'
              }`} />
              <span className={`font-mono text-xs font-semibold ${
                isFailed ? 'text-rose-700' :
                isProcessing ? 'text-amber-700' :
                'text-logo-ink'
              }`}>
                {isFailed ? 'OCR Failure' : isProcessing ? 'OCR Processing...' : 'Verified Graded'}
              </span>
            </div>
          </div>
        </div>

        {isProcessing && (
          <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl mb-6 flex items-center justify-between text-xs text-amber-900">
            <div className="flex items-center space-x-3">
              <CpuIcon className="w-5 h-5 text-amber-600 animate-spin flex-shrink-0" />
              <div>
                <p className="font-bold">OCR Background Worker Running</p>
                <p className="text-amber-700 text-[11px] mt-0.5">
                  Answer booklet is being processed asynchronously by the OCR worker. This screen will automatically refresh as soon as grading concludes.
                </p>
              </div>
            </div>
            <span className="font-mono text-xs font-semibold text-amber-700 animate-pulse px-2 py-1 bg-amber-100 rounded">
              Processing...
            </span>
          </div>
        )}

        {isFailed && (
          <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl mb-6 text-xs text-rose-900 space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start space-x-2">
                <CloseIcon className="w-4 h-4 text-rose-600 flex-shrink-0 mt-0.5" />
                <div>
                  <strong className="text-rose-900 font-semibold">OCR Microservice Evaluation Failure:</strong>
                  <p className="font-mono text-[11px] text-rose-700 mt-1 bg-white/80 p-2 rounded border border-rose-200">
                    {currentSub.error_message || 'The external OCR microservice could not transcribe this document (timeout or network error).'}
                  </p>
                </div>
              </div>
              <button
                onClick={handleRetry}
                disabled={regrading}
                className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-rose-600 hover:bg-rose-700 text-white transition flex-shrink-0 shadow-2xs"
              >
                <RefreshIcon className={`w-3.5 h-3.5 ${regrading ? 'animate-spin' : ''}`} />
                <span>{regrading ? 'Retrying...' : 'Retry OCR'}</span>
              </button>
            </div>
          </div>
        )}

        {!isProcessing && !isFailed && (
          <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl mb-6 flex items-center justify-between text-xs text-slate-600">
            <div className="flex items-center space-x-2">
              <CheckCircleIcon className="w-4 h-4 text-brand-primary flex-shrink-0" />
              <span>
                <strong>OCR Admitted:</strong> Schema v1 compliant answer evidence parsed and evaluated via{' '}
                <code className="bg-white px-1.5 py-0.5 rounded border border-slate-300 font-mono text-[11px] text-slate-800">
                  ocr-service.grading.integration
                </code>
              </span>
            </div>
            <span className="hidden sm:inline font-mono text-emerald-600 font-semibold">100% Validated</span>
          </div>
        )}

        <div className="space-y-4">
          <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
            Detailed Question Breakdown & Rubric Judgments
          </h3>

          {questionResults.length === 0 ? (
            <p className="text-sm text-slate-500 italic p-4 bg-slate-50 rounded-xl text-center">
              No individual question scores recorded.
            </p>
          ) : (
            questionResults.map((q, idx) => (
              <div
                key={q.question_id || idx}
                className="bg-slate-50/70 border border-slate-200 rounded-xl p-5 space-y-3 hover:bg-slate-50 transition"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center space-x-2">
                    <span className="px-2.5 py-1 bg-white border border-slate-300 rounded-lg font-mono font-bold text-xs text-slate-800 shadow-2xs">
                      {q.question_id}
                    </span>
                    <span className={`font-mono px-2 py-0.5 rounded text-[10px] font-semibold tracking-wider ${
                      q.type === 'CHOICE' ? 'bg-surface-subtle text-slate-700 border border-slate-300' :
                      q.type === 'NUMERIC' ? 'bg-logo-sage-soft text-logo-sage-deep border border-logo-sage-border' :
                      'bg-surface-card text-logo-ink border border-slate-300'
                    }`}>
                      {q.type}
                    </span>
                  </div>

                  <div className="text-right">
                    <span className="text-base font-extrabold text-slate-900">
                      {q.awarded_marks}
                    </span>
                    <span className="text-xs font-semibold text-slate-400"> / {q.max_marks} marks</span>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                  <div className="bg-white p-3 rounded-lg border border-slate-200">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                      Student OCR Extracted Answer
                    </p>
                    <p className="text-xs font-mono text-slate-800 whitespace-pre-wrap">
                      {q.student_answer || '<Empty / No text detected>'}
                    </p>
                  </div>

                  <div className="bg-white p-3 rounded-lg border border-slate-200">
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                      Model Answer / Marking Key
                    </p>
                    <p className="text-xs text-slate-700">
                      {q.type === 'CHOICE' ? `Correct Option: ${q.correct_choice}` :
                       q.type === 'NUMERIC' ? `Expected: ${q.expected_value} (tolerance: +/-${q.tolerance})` :
                       q.model_answer || 'Criterion Rubric Applied'}
                    </p>
                  </div>
                </div>

                <div className="bg-blue-50/50 p-3 rounded-lg border border-blue-100">
                  <div className="flex items-start space-x-2">
                    <CheckCircleIcon className="w-4 h-4 text-brand-primary mt-0.5 flex-shrink-0" />
                    <div className="text-xs space-y-1">
                      <p className="text-slate-900 font-semibold">
                        Evaluator Rationale: <span className="font-normal text-slate-700">{q.rationale}</span>
                      </p>

                      {q.criteria_judgments && q.criteria_judgments.length > 0 && (
                        <div className="pt-1.5 flex flex-wrap gap-2">
                          {q.criteria_judgments.map((cj, i) => (
                            <span
                              key={i}
                              className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-white border border-blue-200 text-slate-800"
                            >
                              Level: <span className="text-brand-primary ml-1 font-bold">{cj.selected_level}</span> ({cj.points} pts)
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        <div className="mt-8 pt-4 border-t border-slate-100 flex justify-end">
          <button
            onClick={onClose}
            className="px-6 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white font-semibold text-xs transition"
          >
            Close Report
          </button>
        </div>
      </div>
    </div>
  );
};
