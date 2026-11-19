import React, { useEffect, useState } from 'react';
import { firmAPI, submissionAPI } from '../../api';
import { formatINR } from '../../utils/currency';
import { GradingResultModal } from '../Teacher/GradingResultModal';
import {
  SchoolIcon,
  UsersIcon,
  FileTextIcon,
  BarChartIcon,
  CheckCircleIcon,
  PlusIcon,
  CloseIcon,
  CpuIcon,
} from '../Icons';

export const FirmDashboard = ({ activeTab = 'dashboard' }) => {
  const [overview, setOverview] = useState(null);
  const [instructors, setInstructors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedSubmission, setSelectedSubmission] = useState(null);

  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteForm, setInviteForm] = useState({
    username: '',
    email: '',
    password: '',
    phone: '',
    is_approved: true,
  });
  const [inviteError, setInviteError] = useState('');
  const [inviteLoading, setInviteLoading] = useState(false);

  const loadFirmData = async () => {
    try {
      setLoading(true);
      const [overviewData, instructorsData] = await Promise.all([
        firmAPI.getOverview(),
        firmAPI.getInstructors(),
      ]);
      setOverview(overviewData);
      setInstructors(instructorsData);
    } catch (err) {
      console.error('Failed to load firm dashboard:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadFirmData();
  }, []);

  const handleToggleInstructor = async (instId, currentApproved) => {
    try {
      const updated = await firmAPI.toggleInstructorApproval(instId, {
        is_approved: !currentApproved,
      });
      setInstructors(
        instructors.map((inst) => (inst.id === instId ? { ...inst, is_approved: updated.is_approved } : inst))
      );
      firmAPI.getOverview().then(setOverview);
    } catch (err) {
      alert('Failed to update instructor approval: ' + err.message);
    }
  };

  const handleInviteSubmit = async (e) => {
    e.preventDefault();
    setInviteError('');
    setInviteLoading(true);
    try {
      await firmAPI.inviteInstructor(inviteForm);
      setInviteForm({ username: '', email: '', password: '', phone: '', is_approved: true });
      setShowInviteModal(false);
      await loadFirmData();
    } catch (err) {
      setInviteError(err.message || 'Failed to add instructor');
    } finally {
      setInviteLoading(false);
    }
  };

  const handleViewSubmission = async (subId) => {
    try {
      const full = await submissionAPI.getById(subId);
      setSelectedSubmission(full);
    } catch (err) {
      alert('Failed to load result details: ' + err.message);
    }
  };

  const metrics = overview?.metrics;
  const org = overview?.organization;
  const showResults = activeTab === 'dashboard';
  const showInstructors = activeTab === 'dashboard' || activeTab === 'instructors';
  const showCosts = activeTab === 'dashboard' || activeTab === 'costs';

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header Banner */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-start space-x-4">
          <div className="w-12 h-12 rounded-xl bg-blue-50 text-brand-primary flex items-center justify-center flex-shrink-0">
            <SchoolIcon className="w-6 h-6" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl sm:text-2xl font-bold text-slate-900">
                {org?.name || 'Firm Control Center'}
              </h1>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                Role 2: Firm Lead
              </span>
              {org?.code && (
                <span className="px-2.5 py-0.5 rounded-md text-xs font-mono font-bold bg-slate-100 text-slate-700 border border-slate-200">
                  Invite Code: {org.code}
                </span>
              )}
            </div>
            <p className="text-sm text-slate-500 mt-1">
              Monitor overall assessment results, approve instructors, and track real OCR grading costs & usage.
            </p>
          </div>
        </div>

        <button
          onClick={() => setShowInviteModal(true)}
          className="inline-flex items-center space-x-2 px-4 py-2.5 bg-brand-primary hover:bg-brand-primary-hover text-white rounded-xl font-semibold text-xs sm:text-sm shadow-sm transition"
        >
          <PlusIcon className="w-4 h-4" />
          <span>Add / Approve Instructor</span>
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-xl border border-slate-200">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-wider text-slate-500">Overall Results</p>
          <p className="font-mono text-2xl font-bold text-logo-ink mt-1.5">
            {metrics?.average_percentage !== undefined ? `${metrics.average_percentage}%` : '...'}
          </p>
          <span className="text-xs text-logo-sage-deep font-medium mt-1 inline-block">
            {metrics?.pass_rate ?? 0}% pass rate · {metrics?.graded_booklets ?? 0} graded
          </span>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-wider text-slate-500">Instructors</p>
          <p className="font-mono text-2xl font-bold text-logo-ink mt-1.5">{metrics?.total_instructors ?? '...'}</p>
          <span className="text-xs text-slate-500 mt-1 inline-block">
            {metrics?.pending_instructors ?? 0} awaiting approval
          </span>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-wider text-slate-500">Booklets & Pages</p>
          <p className="font-mono text-2xl font-bold text-logo-ink mt-1.5">{metrics?.booklets_processed ?? '...'}</p>
          <span className="text-xs text-slate-500 mt-1 inline-block">{metrics?.pages_processed ?? 0} OCR pages scanned</span>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-wider text-slate-500">Total OCR Cost</p>
          <p className="font-mono text-2xl font-bold text-logo-ink mt-1.5">
            {formatINR(metrics?.total_cost ?? 0)}
          </p>
          <span className="text-xs text-slate-500 mt-1 inline-block">
            {metrics?.budget_used_pct ?? 0}% of {formatINR(metrics?.monthly_budget_limit ?? 40000)} limit
          </span>
        </div>
      </div>

      {/* Instructor Approvals & Roster */}
      {showInstructors && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
          <div className="p-5 border-b border-slate-200 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Instructor Approvals & Activity</h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Approve instructors who joined via organization code or add new teaching staff.
              </p>
            </div>
            <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-100 text-slate-700">
              {instructors.length} total instructors
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-slate-700 text-xs uppercase font-semibold border-b border-slate-200">
                <tr>
                  <th className="px-6 py-3">Instructor</th>
                  <th className="px-6 py-3">Email</th>
                  <th className="px-6 py-3 text-center">Exams</th>
                  <th className="px-6 py-3 text-center">Booklets Graded</th>
                  <th className="px-6 py-3 text-right">Usage Cost</th>
                  <th className="px-6 py-3 text-center">Approval</th>
                  <th className="px-6 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {loading ? (
                  <tr>
                    <td colSpan="7" className="px-6 py-10 text-center text-slate-400">Loading instructors...</td>
                  </tr>
                ) : instructors.length === 0 ? (
                  <tr>
                    <td colSpan="7" className="px-6 py-10 text-center text-slate-400">
                      No instructors registered yet. Share code <span className="font-mono font-bold">{org?.code}</span> or invite one.
                    </td>
                  </tr>
                ) : (
                  instructors.map((inst) => (
                    <tr key={inst.id} className="hover:bg-slate-50/70 transition">
                      <td className="px-6 py-3.5 font-semibold text-slate-900">{inst.username || 'Instructor'}</td>
                      <td className="px-6 py-3.5 text-xs font-mono text-slate-600">{inst.email}</td>
                      <td className="px-6 py-3.5 text-center font-semibold">{inst.exams_count}</td>
                      <td className="px-6 py-3.5 text-center">{inst.submissions_count}</td>
                      <td className="px-6 py-3.5 text-right font-mono text-xs font-bold text-slate-800">
                        {formatINR(inst.total_cost)}
                      </td>
                      <td className="px-6 py-3.5 text-center">
                        {inst.is_approved ? (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            <CheckCircleIcon className="w-3 h-3 mr-1" /> Approved
                          </span>
                        ) : (
                          <span className="inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                            Pending Approval
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-3.5 text-right">
                        <button
                          onClick={() => handleToggleInstructor(inst.id, inst.is_approved)}
                          className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition ${inst.is_approved
                              ? 'border-slate-200 text-slate-700 hover:bg-slate-100'
                              : 'border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100'
                            }`}
                        >
                          {inst.is_approved ? 'Revoke Access' : 'Approve Instructor'}
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

      {/* Costs & Usage Ledger */}
      {showCosts && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6 space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
            <div>
              <h2 className="text-lg font-bold text-slate-900">OCR Usage & Cost Breakdown</h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Rate Card: {formatINR(metrics?.cost_per_booklet ?? 20)} / booklet + {formatINR(metrics?.cost_per_page ?? 4)} / OCR page
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs text-slate-500">Monthly Budget Utilization</p>
              <p className="font-mono text-sm font-bold text-slate-900">
                {formatINR(metrics?.total_cost ?? 0)} / {formatINR(metrics?.monthly_budget_limit ?? 40000)}
              </p>
            </div>
          </div>

          <div className="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden">
            <div
              className="h-full bg-brand-primary rounded-full transition-all duration-500"
              style={{ width: `${metrics?.budget_used_pct ?? 0}%` }}
            />
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-slate-700 text-xs uppercase font-semibold border-b border-slate-200">
                <tr>
                  <th className="px-4 py-3">Assessment Title</th>
                  <th className="px-4 py-3">Subject</th>
                  <th className="px-4 py-3 text-center">Booklets</th>
                  <th className="px-4 py-3 text-center">OCR Pages</th>
                  <th className="px-4 py-3 text-center">Avg Score</th>
                  <th className="px-4 py-3 text-right">Exam Cost</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {(overview?.exam_usage || []).map((ex) => (
                  <tr key={ex.id} className="hover:bg-slate-50/70">
                    <td className="px-4 py-3 font-semibold text-slate-900">{ex.title}</td>
                    <td className="px-4 py-3 text-xs">{ex.subject_name}</td>
                    <td className="px-4 py-3 text-center">{ex.booklets_count}</td>
                    <td className="px-4 py-3 text-center">{ex.pages_processed}</td>
                    <td className="px-4 py-3 text-center font-semibold text-brand-primary">
                      {ex.average_percentage !== null ? `${ex.average_percentage}%` : '—'}
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-bold text-slate-900">
                      {formatINR(ex.cost)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Firm-Wide Recent Overall Results */}
      {showResults && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
          <div className="p-5 border-b border-slate-200">
            <h2 className="text-lg font-bold text-slate-900">Recent Evaluated Booklets (All Instructors)</h2>
            <p className="text-xs text-slate-500 mt-0.5">Overall student scores evaluated through ocr-service.</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-slate-700 text-xs uppercase font-semibold border-b border-slate-200">
                <tr>
                  <th className="px-6 py-3">Student</th>
                  <th className="px-6 py-3">Exam & Instructor</th>
                  <th className="px-6 py-3 text-center">Score</th>
                  <th className="px-6 py-3 text-right">OCR Cost</th>
                  <th className="px-6 py-3 text-right">Report</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {(overview?.recent_submissions || []).map((sub) => (
                  <tr key={sub.id} className="hover:bg-slate-50/80 transition">
                    <td className="px-6 py-3.5">
                      <p className="font-semibold text-slate-900">{sub.student_name}</p>
                      <p className="text-xs text-slate-400">ID: {sub.student_id}</p>
                    </td>
                    <td className="px-6 py-3.5">
                      <p className="font-medium text-slate-800">{sub.exam_title}</p>
                      <p className="text-xs text-slate-400">By {sub.instructor_name}</p>
                    </td>
                    <td className="px-6 py-3.5 text-center font-bold text-slate-900">
                      {sub.total_score ?? 0} / {sub.max_possible_score ?? 0} ({sub.percentage ?? 0}%)
                    </td>
                    <td className="px-6 py-3.5 text-right font-mono text-xs text-slate-700">
                      {formatINR(sub.grading_cost)}
                    </td>
                    <td className="px-6 py-3.5 text-right">
                      <button
                        onClick={() => handleViewSubmission(sub.id)}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-50 text-brand-primary hover:bg-blue-100 transition"
                      >
                        View Result
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Invite / Create Instructor Modal */}
      {showInviteModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100">
              <h3 className="font-bold text-lg text-slate-900">Add / Approve Instructor</h3>
              <button onClick={() => setShowInviteModal(false)} className="text-slate-400 hover:text-slate-600 p-1">
                <CloseIcon className="w-4 h-4" />
              </button>
            </div>
            {inviteError && (
              <div className="mt-3 p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs">{inviteError}</div>
            )}
            <form onSubmit={handleInviteSubmit} className="space-y-3.5 mt-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Full Name *</label>
                <input
                  type="text"
                  required
                  value={inviteForm.username}
                  onChange={(e) => setInviteForm({ ...inviteForm, username: e.target.value })}
                  placeholder="Prof. Ada Lovelace"
                  className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-primary"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Email *</label>
                <input
                  type="email"
                  required
                  value={inviteForm.email}
                  onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })}
                  placeholder="ada@greenwood.edu"
                  className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-primary"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Temporary Password</label>
                <input
                  type="password"
                  value={inviteForm.password}
                  onChange={(e) => setInviteForm({ ...inviteForm, password: e.target.value })}
                  placeholder="Default: instructor123"
                  className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-primary"
                />
              </div>
              <div className="flex items-center space-x-2 pt-1">
                <input
                  type="checkbox"
                  id="inst_approved"
                  checked={inviteForm.is_approved}
                  onChange={(e) => setInviteForm({ ...inviteForm, is_approved: e.target.checked })}
                  className="rounded text-brand-primary h-4 w-4"
                />
                <label htmlFor="inst_approved" className="text-xs text-slate-700 font-medium">
                  Approve instructor access immediately
                </label>
              </div>
              <div className="flex justify-end space-x-3 pt-4 border-t border-slate-100">
                <button type="button" onClick={() => setShowInviteModal(false)} className="px-4 py-2 text-xs font-semibold text-slate-600">
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={inviteLoading}
                  className="px-5 py-2.5 text-xs font-semibold bg-brand-primary hover:bg-brand-primary-hover text-white rounded-xl shadow-sm transition disabled:opacity-50"
                >
                  {inviteLoading ? 'Adding...' : 'Save Instructor'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {selectedSubmission && (
        <GradingResultModal
          submission={selectedSubmission}
          onClose={() => setSelectedSubmission(null)}
        />
      )}
    </div>
  );
};

