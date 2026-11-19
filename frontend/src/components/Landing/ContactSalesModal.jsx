import React, { useState } from 'react';
import { salesAPI } from '../../api';
import { FloatingInput } from '../FloatingInput';
import {
  GradifiedLogo,
  CloseIcon,
  CheckCircleIcon,
  AlertIcon,
  ArrowRightIcon,
} from '../Icons';

export const ContactSalesModal = ({ isOpen, onClose, onGoToLogin }) => {
  const [form, setForm] = useState({
    organization_name: '',
    contact_name: '',
    email: '',
    phone: '',
    expected_booklets: '500',
    notes: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [submitted, setSubmitted] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await salesAPI.submitDemoRequest({
        ...form,
        expected_booklets: parseInt(form.expected_booklets || '500', 10),
      });
      setSubmitted(true);
    } catch (err) {
      setError(err.message || 'Unable to submit demo request.');
    } finally {
      setLoading(false);
    }
  };

  const resetAndClose = () => {
    setSubmitted(false);
    setError('');
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/45 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-surface-card rounded-2xl max-w-md w-full p-6 sm:p-7 shadow-2xl border border-slate-200 relative">
        <button
          type="button"
          onClick={resetAndClose}
          aria-label="Close Contact Sales modal"
          className="absolute top-4 right-4 text-slate-400 hover:text-slate-700 p-1.5 rounded-lg hover:bg-slate-100 transition"
        >
          <CloseIcon className="w-4 h-4" />
        </button>

        {submitted ? (
          <div className="text-center py-4 space-y-4">
            <div className="w-12 h-12 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-600 flex items-center justify-center mx-auto">
              <CheckCircleIcon className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-900">Onboarding Request Received</h3>
              <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
                Our Application Admin team has received the demo request for{' '}
                <span className="font-semibold text-slate-800">{form.organization_name}</span> and will provision your organization access shortly.
              </p>
            </div>
            <div className="pt-2 flex flex-col sm:flex-row gap-2.5 justify-center">
              {onGoToLogin && (
                <button
                  type="button"
                  onClick={() => {
                    resetAndClose();
                    onGoToLogin();
                  }}
                  className="group inline-flex items-center justify-center space-x-1.5 px-4 py-2.5 rounded-lg bg-signup hover:bg-signup-hover text-signup-text text-xs font-semibold transition"
                >
                  <span>Explore Demo Platform</span>
                  <ArrowRightIcon className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
                </button>
              )}
              <button
                type="button"
                onClick={resetAndClose}
                className="px-4 py-2.5 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-semibold transition"
              >
                Done
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="mb-5">
              <GradifiedLogo className="h-7 w-auto mb-3" />
              <h3 className="text-lg font-bold text-slate-900">Request Organization Onboarding</h3>
              <p className="text-xs text-slate-500 mt-1">
                Book a live demo or request firm onboarding approved by our Application Admin.
              </p>
            </div>

            {error && (
              <div className="mb-4 p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start space-x-2">
                <AlertIcon className="w-4 h-4 mt-0.5 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-3.5">
              <FloatingInput
                label="School / Firm Name"
                type="text"
                required
                value={form.organization_name}
                onChange={(e) => setForm({ ...form, organization_name: e.target.value })}
              />
              <FloatingInput
                label="Your Full Name"
                type="text"
                required
                value={form.contact_name}
                onChange={(e) => setForm({ ...form, contact_name: e.target.value })}
              />
              <FloatingInput
                label="Work Email"
                type="email"
                required
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
              <div className="grid grid-cols-2 gap-3">
                <FloatingInput
                  label="Phone Number"
                  type="text"
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                />
                <FloatingInput
                  label="Monthly Booklets"
                  type="number"
                  value={form.expected_booklets}
                  onChange={(e) => setForm({ ...form, expected_booklets: e.target.value })}
                />
              </div>
              <FloatingInput
                label="Assessment Goals / Notes (Optional)"
                type="text"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />

              <button
                type="submit"
                disabled={loading}
                className="group w-full py-2.5 px-4 rounded-lg bg-signup hover:bg-signup-hover text-signup-text font-semibold text-xs shadow-sm flex items-center justify-center space-x-2 transition disabled:opacity-50"
              >
                <span>{loading ? 'Submitting Request...' : 'Submit Demo & Onboarding Request'}</span>
                {!loading && <ArrowRightIcon className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />}
              </button>
            </form>

            {onGoToLogin && (
              <div className="mt-4 pt-3 border-t border-slate-100 text-center text-[11px] text-slate-500">
                Want to explore immediately?{' '}
                <button
                  type="button"
                  onClick={() => {
                    resetAndClose();
                    onGoToLogin();
                  }}
                  className="text-brand-primary font-semibold hover:underline"
                >
                  Log in with Demo Accounts
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

