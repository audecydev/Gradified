import React, { useState, useEffect } from 'react';
import { adminAPI } from '../../api';
import { formatINR } from '../../utils/currency';
import {
  SchoolIcon,
  BookIcon,
  FileTextIcon,
  PlusIcon,
  CheckCircleIcon,
  BarChartIcon,
  SearchIcon,
  MailIcon,
  LockIcon,
  CloseIcon,
  UsersIcon,
  ShieldIcon,
} from '../Icons';

const STATUS_BADGES = {
  APPROVED: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  PENDING: 'bg-amber-50 text-amber-700 border-amber-200',
  SUSPENDED: 'bg-rose-50 text-rose-700 border-rose-200',
  ONBOARDED: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  DISMISSED: 'bg-slate-100 text-slate-600 border-slate-200',
};

export const AdminDashboard = ({ activeTab = 'dashboard' }) => {
  const [stats, setStats] = useState(null);
  const [orgs, setOrgs] = useState([]);
  const [demoRequests, setDemoRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  const [showModal, setShowModal] = useState(false);
  const [newOrg, setNewOrg] = useState({
    school_name: '',
    email: '',
    password: '',
    contact_person: '',
    phone: '',
    plan_tier: 'PRO',
    auto_verify: true,
    demo_request_id: null,
  });
  const [modalLoading, setModalLoading] = useState(false);
  const [modalError, setModalError] = useState('');
  const [modalSuccess, setModalSuccess] = useState('');

  const loadData = async () => {
    try {
      setLoading(true);
      const [statsData, orgsData, requestsData] = await Promise.all([
        adminAPI.getStats(),
        adminAPI.getOrganizations(),
        adminAPI.getDemoRequests(),
      ]);
      setStats(statsData);
      setOrgs(orgsData);
      setDemoRequests(requestsData);
    } catch (err) {
      console.error('Failed to load admin data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleOrgStatus = async (orgId, nextStatus) => {
    try {
      const updated = await adminAPI.updateOrgStatus(orgId, { status: nextStatus });
      setOrgs(orgs.map((o) => (o.id === orgId ? updated : o)));
      adminAPI.getStats().then(setStats);
    } catch (err) {
      alert('Failed to update organization status: ' + err.message);
    }
  };

  const handleDismissDemo = async (reqId) => {
    try {
      const updated = await adminAPI.updateDemoRequest(reqId, { status: 'DISMISSED' });
      setDemoRequests(demoRequests.map((r) => (r.id === reqId ? updated : r)));
      adminAPI.getStats().then(setStats);
    } catch (err) {
      alert('Failed to update demo request: ' + err.message);
    }
  };

  const openOnboardFromDemo = (req) => {
    setNewOrg({
      school_name: req.organization_name || '',
      email: req.email || '',
      password: '',
      contact_person: req.contact_name || '',
      phone: req.phone || '',
      plan_tier: req.expected_booklets >= 2000 ? 'ENTERPRISE' : 'PRO',
      auto_verify: true,
      demo_request_id: req.id,
    });
    setModalError('');
    setModalSuccess('');
    setShowModal(true);
  };

  const handleOnboardSubmit = async (e) => {
    e.preventDefault();
    setModalError('');
    setModalSuccess('');
    setModalLoading(true);

    try {
      const res = await adminAPI.onboardSchool(newOrg);
      setModalSuccess(res.message);
      setNewOrg({
        school_name: '',
        email: '',
        password: '',
        contact_person: '',
        phone: '',
        plan_tier: 'PRO',
        auto_verify: true,
        demo_request_id: null,
      });
      await loadData();
      setTimeout(() => {
        setShowModal(false);
        setModalSuccess('');
      }, 1200);
    } catch (err) {
      setModalError(err.message || 'Failed to onboard organization');
    } finally {
      setModalLoading(false);
    }
  };

  const filteredOrgs = orgs.filter((o) =>
    o.name?.toLowerCase().includes(search.toLowerCase()) ||
    o.contact_email?.toLowerCase().includes(search.toLowerCase()) ||
    o.code?.toLowerCase().includes(search.toLowerCase())
  );

  const showOrgsTable = activeTab === 'dashboard' || activeTab === 'schools';
  const showDemoQueue = activeTab === 'dashboard' || activeTab === 'requests';

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2.5">
            <h1 className="font-display text-2xl font-bold text-logo-ink">Application Admin Console</h1>
            <span className="font-mono px-2.5 py-0.5 rounded text-[11px] font-medium bg-logo-sage-soft text-logo-ink border border-logo-sage-border">
              ROLE 1 · AUTHORITY
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Review inbound demo requests, onboard schools & firms, and approve organization access.
          </p>
        </div>

        <button
          onClick={() => {
            setNewOrg({
              school_name: '',
              email: '',
              password: '',
              contact_person: '',
              phone: '',
              plan_tier: 'PRO',
              auto_verify: true,
              demo_request_id: null,
            });
            setShowModal(true);
          }}
          className="inline-flex items-center space-x-2 px-4 py-2.5 bg-brand-primary hover:bg-brand-primary-hover text-white rounded-xl shadow-sm font-semibold text-sm transition"
        >
          <PlusIcon className="w-4 h-4" />
          <span>Onboard New Organization</span>
        </button>
      </div>

      {/* Platform Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-xl border border-slate-200">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-wider text-slate-500">Organizations</p>
          <p className="font-mono text-2xl font-bold text-logo-ink mt-1.5">{stats?.total_orgs ?? '...'}</p>
          <span className="text-xs text-logo-sage-deep font-medium mt-1 inline-block">
            {stats?.approved_orgs ?? 0} approved · {stats?.pending_orgs ?? 0} pending
          </span>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-wider text-slate-500">Demo Queue</p>
          <p className="font-mono text-2xl font-bold text-logo-ink mt-1.5">{stats?.pending_demo_requests ?? '...'}</p>
          <span className="text-xs text-slate-500 mt-1 inline-block">awaiting onboarding</span>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-wider text-slate-500">Instructors & Booklets</p>
          <p className="font-mono text-2xl font-bold text-logo-ink mt-1.5">{stats?.total_instructors ?? '...'}</p>
          <span className="text-xs text-logo-sage-deep font-medium mt-1 inline-block">{stats?.graded_submissions ?? 0} booklets graded</span>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200">
          <p className="font-mono text-[11px] font-semibold uppercase tracking-wider text-slate-500">Platform OCR Usage</p>
          <p className="font-mono text-2xl font-bold text-logo-ink mt-1.5">
            {formatINR(stats?.total_platform_cost ?? 0)}
          </p>
          <span className="text-xs text-slate-500 mt-1 inline-block">Avg score {stats?.average_percentage ?? 0}%</span>
        </div>
      </div>

      {/* Contact Sales / Demo Queue */}
      {showDemoQueue && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
          <div className="p-5 border-b border-slate-200 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Contact Sales & Onboarding Requests</h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Inbound school & firm inquiries submitted from the landing page. Approve to provision Firm Lead credentials.
              </p>
            </div>
            <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
              {demoRequests.filter((r) => r.status === 'PENDING').length} Pending
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-slate-700 text-xs uppercase font-semibold border-b border-slate-200">
                <tr>
                  <th className="px-6 py-3">Organization</th>
                  <th className="px-6 py-3">Contact</th>
                  <th className="px-6 py-3">Est. Volume</th>
                  <th className="px-6 py-3">Notes</th>
                  <th className="px-6 py-3 text-center">Status</th>
                  <th className="px-6 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {demoRequests.length === 0 ? (
                  <tr>
                    <td colSpan="6" className="px-6 py-8 text-center text-slate-400">
                      No inbound demo requests yet.
                    </td>
                  </tr>
                ) : (
                  demoRequests.map((req) => (
                    <tr key={req.id} className="hover:bg-slate-50/70 transition">
                      <td className="px-6 py-3.5 font-semibold text-slate-900">{req.organization_name}</td>
                      <td className="px-6 py-3.5">
                        <p className="font-medium text-slate-800">{req.contact_name}</p>
                        <p className="text-xs font-mono text-slate-500">{req.email}</p>
                      </td>
                      <td className="px-6 py-3.5 text-xs font-semibold text-slate-700">
                        {req.expected_booklets} booklets/mo
                      </td>
                      <td className="px-6 py-3.5 text-xs text-slate-500 max-w-xs truncate">
                        {req.notes || '—'}
                      </td>
                      <td className="px-6 py-3.5 text-center">
                        <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold border ${STATUS_BADGES[req.status] || STATUS_BADGES.PENDING}`}>
                          {req.status}
                        </span>
                      </td>
                      <td className="px-6 py-3.5 text-right space-x-2">
                        {req.status === 'PENDING' && (
                          <>
                            <button
                              onClick={() => openOnboardFromDemo(req)}
                              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-brand-primary hover:bg-brand-primary-hover text-white transition"
                            >
                              Onboard & Approve
                            </button>
                            <button
                              onClick={() => handleDismissDemo(req.id)}
                              className="px-2.5 py-1.5 rounded-lg text-xs font-semibold border border-slate-200 text-slate-600 hover:bg-slate-100 transition"
                            >
                              Dismiss
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Organizations / Firms Table */}
      {showOrgsTable && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
          <div className="p-5 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Registered Organizations & Schools</h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Approve pending firms, monitor instructor enrollment, exams, and monthly OCR usage costs.
              </p>
            </div>

            <div className="relative">
              <SearchIcon className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search orgs, email or code..."
                className="pl-9 pr-4 py-1.5 text-xs rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-primary w-full sm:w-64"
              />
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-slate-700 text-xs uppercase font-semibold border-b border-slate-200">
                <tr>
                  <th className="px-6 py-3.5">Organization & Code</th>
                  <th className="px-6 py-3.5">Firm Lead</th>
                  <th className="px-6 py-3.5 text-center">Instructors</th>
                  <th className="px-6 py-3.5 text-center">Exams / Sheets</th>
                  <th className="px-6 py-3.5 text-right">Usage Cost</th>
                  <th className="px-6 py-3.5 text-center">Org Status</th>
                  <th className="px-6 py-3.5 text-right">Approval</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {loading ? (
                  <tr>
                    <td colSpan="7" className="px-6 py-12 text-center text-slate-400">
                      Loading organization records...
                    </td>
                  </tr>
                ) : filteredOrgs.length === 0 ? (
                  <tr>
                    <td colSpan="7" className="px-6 py-12 text-center text-slate-400">
                      No organizations found matching your search.
                    </td>
                  </tr>
                ) : (
                  filteredOrgs.map((org) => (
                    <tr key={org.id} className="hover:bg-slate-50/80 transition">
                      <td className="px-6 py-4">
                        <div className="flex items-center space-x-3">
                          <div className="w-9 h-9 rounded-lg bg-slate-100 text-slate-700 flex items-center justify-center font-bold text-xs">
                            <SchoolIcon className="w-5 h-5" />
                          </div>
                          <div>
                            <p className="font-semibold text-slate-900">{org.name}</p>
                            <p className="text-xs font-mono text-brand-primary font-semibold">
                              Code: {org.code} • {org.plan_tier}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <p className="font-medium text-slate-800">{org.contact_person || 'Primary Lead'}</p>
                        <p className="text-xs font-mono text-slate-500">{org.contact_email}</p>
                      </td>
                      <td className="px-6 py-4 text-center">
                        <span className="font-semibold text-slate-800">{org.instructors_count}</span>
                        {org.pending_instructors_count > 0 && (
                          <span className="block text-[10px] text-amber-600 font-medium">
                            {org.pending_instructors_count} pending firm approval
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4 text-center">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-brand-primary">
                          {org.exams_count} exams • {org.submissions_count} sheets
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right font-mono text-xs font-bold text-slate-800">
                        {formatINR(org.total_cost)}
                      </td>
                      <td className="px-6 py-4 text-center">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border ${STATUS_BADGES[org.status] || STATUS_BADGES.PENDING}`}>
                          {org.status === 'APPROVED' && <CheckCircleIcon className="w-3 h-3 mr-1 text-emerald-600" />}
                          {org.status}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right space-x-1.5">
                        {org.status !== 'APPROVED' ? (
                          <button
                            onClick={() => handleOrgStatus(org.id, 'APPROVED')}
                            className="text-xs px-3 py-1.5 rounded-lg font-semibold border border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 transition"
                          >
                            Approve Org
                          </button>
                        ) : (
                          <button
                            onClick={() => handleOrgStatus(org.id, 'SUSPENDED')}
                            className="text-xs px-3 py-1.5 rounded-lg font-semibold border border-slate-200 text-slate-700 hover:bg-slate-100 transition"
                          >
                            Suspend
                          </button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Onboard Organization Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100">
              <div className="flex items-center space-x-2">
                <div className="w-8 h-8 rounded-lg bg-blue-50 text-brand-primary flex items-center justify-center">
                  <PlusIcon className="w-5 h-5" />
                </div>
                <h3 className="font-bold text-lg text-slate-900">Onboard Organization & Firm Lead</h3>
              </div>
              <button
                onClick={() => setShowModal(false)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                <CloseIcon className="w-4 h-4" />
              </button>
            </div>

            {modalError && (
              <div className="my-4 p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs">
                {modalError}
              </div>
            )}

            {modalSuccess && (
              <div className="my-4 p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs">
                {modalSuccess}
              </div>
            )}

            <form onSubmit={handleOnboardSubmit} className="space-y-4 mt-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  School / Organization Name *
                </label>
                <div className="relative">
                  <SchoolIcon className="w-4 h-4 text-slate-400 absolute left-3 top-3 pointer-events-none" />
                  <input
                    type="text"
                    required
                    value={newOrg.school_name}
                    onChange={(e) => setNewOrg({ ...newOrg, school_name: e.target.value })}
                    placeholder="e.g. St. Jude International Academy"
                    className="w-full pl-9 pr-3 py-2 text-sm rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-primary"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                    Firm Lead Contact Name
                  </label>
                  <input
                    type="text"
                    value={newOrg.contact_person}
                    onChange={(e) => setNewOrg({ ...newOrg, contact_person: e.target.value })}
                    placeholder="Prof. Robert Dean"
                    className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-primary"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                    Plan Tier
                  </label>
                  <select
                    value={newOrg.plan_tier}
                    onChange={(e) => setNewOrg({ ...newOrg, plan_tier: e.target.value })}
                    className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-primary bg-white"
                  >
                    <option value="STARTER">Starter</option>
                    <option value="PRO">Professional</option>
                    <option value="ENTERPRISE">Enterprise</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  Firm Lead Login Email *
                </label>
                <div className="relative">
                  <MailIcon className="w-4 h-4 text-slate-400 absolute left-3 top-3 pointer-events-none" />
                  <input
                    type="email"
                    required
                    value={newOrg.email}
                    onChange={(e) => setNewOrg({ ...newOrg, email: e.target.value })}
                    placeholder="lead@stjude.edu"
                    className="w-full pl-9 pr-3 py-2 text-sm rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-primary"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
                  Initial Password *
                </label>
                <div className="relative">
                  <LockIcon className="w-4 h-4 text-slate-400 absolute left-3 top-3 pointer-events-none" />
                  <input
                    type="password"
                    required
                    minLength={6}
                    value={newOrg.password}
                    onChange={(e) => setNewOrg({ ...newOrg, password: e.target.value })}
                    placeholder="Minimum 6 characters"
                    className="w-full pl-9 pr-3 py-2 text-sm rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-brand-primary"
                  />
                </div>
              </div>

              <div className="flex items-center space-x-2 pt-2">
                <input
                  type="checkbox"
                  id="auto_verify"
                  checked={newOrg.auto_verify}
                  onChange={(e) => setNewOrg({ ...newOrg, auto_verify: e.target.checked })}
                  className="rounded text-brand-primary focus:ring-brand-primary h-4 w-4"
                />
                <label htmlFor="auto_verify" className="text-xs text-slate-700 font-medium">
                  Immediately approve organization and activate Firm Lead login
                </label>
              </div>

              <div className="flex justify-end space-x-3 pt-4 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={modalLoading}
                  className="px-5 py-2.5 text-xs font-semibold bg-brand-primary hover:bg-brand-primary-hover text-white rounded-xl shadow-sm transition disabled:opacity-50"
                >
                  {modalLoading ? 'Onboarding...' : 'Onboard & Approve Org'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
