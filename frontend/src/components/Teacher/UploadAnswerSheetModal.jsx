import React, { useState } from 'react';
import { submissionAPI } from '../../api';
import {
  UploadIcon,
  CpuIcon,
  AlertIcon,
  CloseIcon,
  UserIcon,
  HashIcon,
  CheckCircleIcon,
} from '../Icons';

export const UploadAnswerSheetModal = ({ exam, onClose, onGraded }) => {
  const [studentName, setStudentName] = useState('');
  const [studentId, setStudentId] = useState('');
  const [file, setFile] = useState(null);
  const [ocrText, setOcrText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!studentName.trim() || !studentId.trim()) {
      setError('Student Name and Student ID are required.');
      return;
    }

    if (!file && !ocrText.trim()) {
      setError('Please provide an answer sheet file or text.');
      return;
    }

    setError('');
    setLoading(true);

    try {
      const formData = new FormData();
      formData.append('student_name', studentName.trim());
      formData.append('student_id', studentId.trim());
      formData.append('auto_grade', 'true');

      if (file) {
        formData.append('answer_sheet_file', file);
      }
      if (ocrText.trim()) {
        formData.append('raw_ocr_text', ocrText.trim());
      }

      const res = await submissionAPI.create(exam.id, formData);
      onGraded(res);
      onClose();
    } catch (err) {
      setError(err.message || 'Evaluation failed in grading engine.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4 overflow-y-auto">
      <div className="bg-white rounded-xl max-w-2xl w-full p-6 sm:p-7 shadow-xl border border-slate-200 my-8">
        <div className="flex items-center justify-between pb-4 border-b border-slate-100">
          <div>
            <h3 className="font-display font-bold text-lg text-logo-ink">Upload Student Answer Sheet</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Exam: <span className="font-semibold text-slate-700">{exam.title}</span> ({exam.subject_name})
            </p>
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

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1">
                Student Name *
              </label>
              <div className="relative">
                <UserIcon className="w-4 h-4 text-slate-400 absolute left-3 top-2.5 pointer-events-none" />
                <input
                  type="text"
                  required
                  value={studentName}
                  onChange={(e) => setStudentName(e.target.value)}
                  placeholder="e.g. Jessica Miller"
                  className="w-full pl-9 pr-3 py-2 text-sm rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-primary"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1">
                Student Roll / ID *
              </label>
              <div className="relative">
                <HashIcon className="w-4 h-4 text-slate-400 absolute left-3 top-2.5 pointer-events-none" />
                <input
                  type="text"
                  required
                  value={studentId}
                  onChange={(e) => setStudentId(e.target.value)}
                  placeholder="e.g. ROLL-2026-402"
                  className="w-full pl-9 pr-3 py-2 text-sm rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-primary"
                />
              </div>
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600 mb-1">
              Upload Scanned Answer Sheet File (PDF, PNG, JPG, JSON, TXT)
            </label>
            <div className="border-2 border-dashed border-slate-300 hover:border-brand-primary rounded-xl p-4 text-center cursor-pointer transition bg-slate-50/50">
              <input
                type="file"
                id="file_upload"
                onChange={(e) => setFile(e.target.files[0] || null)}
                className="hidden"
              />
              <label htmlFor="file_upload" className="cursor-pointer block">
                <UploadIcon className="w-6 h-6 text-slate-400 mx-auto mb-1" />
                <p className="text-xs font-semibold text-slate-700">
                  {file ? file.name : 'Click to browse scanned answer sheet'}
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Supports Scanned Images, Normalized Evidence JSON, or Handwritten OCR Exports
                </p>
              </label>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-600">
                Answer Sheet Content / OCR Text
              </label>
              <span className="text-[11px] text-slate-400">Question markers (Q1:, Q2:, etc.)</span>
            </div>
            <textarea
              rows={5}
              value={ocrText}
              onChange={(e) => setOcrText(e.target.value)}
              placeholder="Paste or review OCR transcription here (e.g. Q1: Option B, Q2: 42, Q3: Explanation...)"
              className="w-full p-3 font-mono text-xs rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-primary bg-white"
            />
          </div>

          <div className="flex items-center justify-between pt-4 border-t border-slate-100">
            <span className="text-xs text-slate-500 flex items-center">
              <CpuIcon className="w-3.5 h-3.5 mr-1 text-brand-primary" /> Powered by ocr-service
            </span>

            <div className="flex space-x-2">
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
                className="px-5 py-2.5 rounded-xl bg-brand-primary hover:bg-brand-primary-hover text-white font-semibold text-xs shadow-sm flex items-center space-x-2 transition disabled:opacity-50"
              >
                <CheckCircleIcon className="w-4 h-4" />
                <span>{loading ? 'Running OCR & Evaluation...' : 'Grade with OCR Engine'}</span>
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};
