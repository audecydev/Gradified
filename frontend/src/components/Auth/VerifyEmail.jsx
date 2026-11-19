import React, { useState } from 'react';
import { authAPI } from '../../api';
import { useAuth } from '../../context/AuthContext';
import { AuthBackdrop } from './AuthBackdrop';
import { FloatingInput } from '../FloatingInput';
import {
  GradifiedLogo,
  KeyIcon,
  CheckCircleIcon,
  AlertIcon,
  RefreshIcon,
  ArrowLeftIcon,
} from '../Icons';

export const VerifyEmail = ({ email, defaultCode, onBackToLogin }) => {
  const { login } = useAuth();
  const [code, setCode] = useState(defaultCode || '');
  const [loading, setLoading] = useState(false);
  const [resending, setResending] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const handleVerify = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await authAPI.verifyEmail({
        email,
        code: code.trim(),
      });
      login(res.user, res.tokens);
    } catch (err) {
      setError(err.message || 'Verification failed. Please check your code.');
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setError('');
    setSuccessMsg('');
    setResending(true);

    try {
      const res = await authAPI.resendVerification(email);
      setSuccessMsg('A new verification code has been dispatched.');
      if (res.verification_code) {
        setCode(res.verification_code);
      }
    } catch (err) {
      setError(err.message || 'Failed to resend verification code.');
    } finally {
      setResending(false);
    }
  };

  return (
    <AuthBackdrop>
      <div className="w-full max-w-[410px] bg-white/95 rounded-2xl shadow-lg shadow-slate-200/70 border border-slate-200/90 p-7 sm:p-8">
        <div className="text-center mb-6">
          <div className="flex justify-center mb-4">
            <GradifiedLogo className="h-9 w-auto" />
          </div>
          <h2 className="text-xl font-bold text-slate-900 tracking-tight">Verify your email</h2>
          <p className="text-xs text-slate-500 mt-1">
            We sent a verification code to <span className="font-semibold text-slate-900">{email}</span>
          </p>
        </div>

        {defaultCode && (
          <div className="mb-5 p-3.5 rounded-lg bg-slate-50 border border-slate-200 text-slate-900 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-semibold">Development Code:</span>
              <span className="font-mono bg-white px-2.5 py-1 rounded border border-slate-300 font-bold text-brand-primary tracking-wider">
                {defaultCode}
              </span>
            </div>
            <p className="mt-1 text-[11px] text-slate-500">Code automatically detected for quick verification.</p>
          </div>
        )}

        {error && (
          <div className="mb-5 p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start space-x-2">
            <AlertIcon className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {successMsg && (
          <div className="mb-5 p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-start space-x-2">
            <CheckCircleIcon className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <span>{successMsg}</span>
          </div>
        )}

        <form onSubmit={handleVerify} className="space-y-4">
          <FloatingInput
            label="6-Digit Verification Code"
            type="text"
            required
            maxLength={10}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            leftIcon={<KeyIcon className="w-4 h-4" />}
            inputClassName="font-mono text-center tracking-widest text-sm font-bold"
          />

          <button
            type="submit"
            disabled={loading || !code.trim()}
            className="w-full py-2.5 px-4 rounded-lg bg-brand-primary hover:bg-brand-primary-hover text-white font-semibold text-xs shadow-sm flex items-center justify-center space-x-2 transition disabled:opacity-50"
          >
            <CheckCircleIcon className="w-4 h-4" />
            <span>{loading ? 'Verifying...' : 'Verify & Launch Application'}</span>
          </button>
        </form>

        <div className="mt-6 pt-4 border-t border-slate-100 flex items-center justify-between text-xs">
          <button
            type="button"
            onClick={onBackToLogin}
            className="text-slate-500 hover:text-slate-700 flex items-center"
          >
            <ArrowLeftIcon className="w-3.5 h-3.5 mr-1" /> Back to Sign In
          </button>

          <button
            type="button"
            disabled={resending}
            onClick={handleResend}
            className="text-brand-primary hover:text-brand-primary-hover font-semibold flex items-center"
          >
            <RefreshIcon className={`w-3.5 h-3.5 mr-1 ${resending ? 'animate-spin' : ''}`} />
            {resending ? 'Sending...' : 'Resend Code'}
          </button>
        </div>
      </div>
    </AuthBackdrop>
  );
};
