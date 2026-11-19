import React, { useState } from 'react';
import { authAPI } from '../../api';
import { useAuth } from '../../context/AuthContext';
import { AuthBackdrop } from './AuthBackdrop';
import { FloatingInput } from '../FloatingInput';
import {
  GradifiedLogo,
  ArrowRightIcon,
  ArrowLeftIcon,
  AlertIcon,
  EyeIcon,
  EyeOffIcon,
  GoogleGIcon,
} from '../Icons';

export const Login = ({
  onSwitchToSignup,
  onJoinAsInstructor,
  onRequireVerification,
  onBackToHome,
  onOpenContactSales,
}) => {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [infoMsg, setInfoMsg] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setInfoMsg('');
    setLoading(true);

    try {
      const res = await authAPI.login({ email, password });
      login(res.user, res.tokens);
    } catch (err) {
      if (err.data?.requires_verification) {
        onRequireVerification(err.data.email, err.data.verification_code);
      } else {
        setError(err.message || 'Invalid email or password.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleQuickLogin = (demoEmail, demoPassword) => {
    setError('');
    setInfoMsg('');
    setEmail(demoEmail);
    setPassword(demoPassword);
  };

  return (
    <AuthBackdrop>
      <div className="w-full max-w-[440px] mb-3">
        <button
          type="button"
          onClick={onBackToHome}
          className="inline-flex items-center space-x-1.5 text-xs font-medium text-slate-500 hover:text-slate-900 transition"
        >
          <ArrowLeftIcon className="w-3.5 h-3.5" />
          <span>Back to Home</span>
        </button>
      </div>

      <div className="w-full max-w-[440px] bg-white rounded-xl shadow-md shadow-slate-200/50 border border-slate-200 p-7 sm:p-8">
        <div className="text-center mb-6">
          <div className="flex justify-center mb-4">
            <GradifiedLogo className="h-9 w-auto" />
          </div>
          <h2 className="font-display text-xl font-bold text-logo-ink tracking-tight">Welcome back</h2>
          <p className="text-xs text-slate-500 mt-1">Sign in to access your assigned workspace</p>
        </div>

        <button
          type="button"
          onClick={() => setInfoMsg('Google SSO is not configured in this local environment. Use your credentials or explore a demo role below.')}
          className="w-full py-2.5 px-4 rounded-lg bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-xs font-semibold flex items-center justify-center space-x-2.5 shadow-2xs transition"
        >
          <GoogleGIcon className="w-4 h-4" />
          <span>Continue with Google</span>
        </button>

        <div className="relative my-5">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-slate-200" />
          </div>
          <div className="relative flex justify-center text-[11px]">
            <span className="px-3 bg-white text-slate-400">or continue with email</span>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-start space-x-2">
            <AlertIcon className="w-4 h-4 mt-0.5 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {infoMsg && (
          <div className="mb-4 p-3 rounded-lg bg-slate-50 border border-slate-200 text-slate-600 text-xs">
            {infoMsg}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <FloatingInput
            label="Email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />

          <div>
            <FloatingInput
              label="Password"
              type={showPassword ? 'text' : 'password'}
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              rightElement={
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  className="text-slate-400 hover:text-slate-600 transition"
                >
                  {showPassword ? <EyeOffIcon className="w-4 h-4" /> : <EyeIcon className="w-4 h-4" />}
                </button>
              }
            />
            <div className="flex justify-end mt-1.5">
              <button
                type="button"
                onClick={() => setInfoMsg('Contact your Application Admin or Firm administrator to reset credentials.')}
                className="text-[11px] font-medium text-brand-primary hover:underline"
              >
                Forgot password?
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="group w-full py-2.5 px-4 rounded-lg bg-brand-primary hover:bg-brand-primary-hover text-white font-semibold text-xs shadow-sm flex items-center justify-center space-x-2 transition disabled:opacity-50"
          >
            <span>{loading ? 'Signing in...' : 'Sign In'}</span>
            {!loading && <ArrowRightIcon className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform duration-200" />}
          </button>
        </form>

        <div className="mt-4 text-center">
          <button
            type="button"
            onClick={onJoinAsInstructor}
            className="text-[11px] font-medium text-brand-primary hover:underline"
          >
            Have an invite code from your Firm? Join as Instructor
          </button>
        </div>

        <div className="mt-4 pt-4 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
          <button
            type="button"
            onClick={onOpenContactSales}
            className="text-brand-primary hover:text-brand-primary-hover font-semibold"
          >
            Contact Sales for Demo
          </button>
          <button
            type="button"
            onClick={onSwitchToSignup}
            className="text-slate-600 hover:text-slate-900 font-medium"
          >
            Register Firm
          </button>
        </div>
      </div>
    </AuthBackdrop>
  );
};
