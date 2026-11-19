import React, { useEffect, useState } from 'react';
import { authAPI } from '../../api';
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

export const Signup = ({
  onSwitchToLogin,
  onRegistered,
  onBackToHome,
  onOpenContactSales,
  defaultJoinOrg = false,
}) => {
  const [joinExistingOrg, setJoinExistingOrg] = useState(defaultJoinOrg);

  useEffect(() => {
    setJoinExistingOrg(defaultJoinOrg);
  }, [defaultJoinOrg]);
  const [username, setUsername] = useState('');
  const [schoolName, setSchoolName] = useState('');
  const [orgCode, setOrgCode] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [infoMsg, setInfoMsg] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setInfoMsg('');

    if (password.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match. Please re-enter confirm password.');
      return;
    }

    setLoading(true);

    try {
      const res = await authAPI.signup({
        email,
        password,
        confirm_password: confirmPassword,
        username,
        school_name: joinExistingOrg ? '' : schoolName,
        org_code: joinExistingOrg ? orgCode.trim() : '',
      });

      onRegistered(res.email, res.verification_code, res.verification_token);
    } catch (err) {
      setError(err.message || 'Registration failed. Please check your details.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthBackdrop>
      <div className="w-full max-w-[420px] mb-3">
        <button
          type="button"
          onClick={onBackToHome}
          className="inline-flex items-center space-x-1.5 text-xs font-medium text-slate-500 hover:text-slate-900 transition"
        >
          <ArrowLeftIcon className="w-3.5 h-3.5" />
          <span>Back to Home</span>
        </button>
      </div>

      <div className="w-full max-w-[420px] bg-white rounded-xl shadow-md shadow-slate-200/50 border border-slate-200 p-7 sm:p-8">
        <div className="text-center mb-5">
          <div className="flex justify-center mb-4">
            <GradifiedLogo className="h-9 w-auto" />
          </div>
          <h2 className="font-display text-xl font-bold text-logo-ink tracking-tight">
            {joinExistingOrg ? 'Join Firm as Instructor' : 'Register your Firm'}
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            {joinExistingOrg
              ? 'Enter your firm organization code. Your firm administrator will approve access.'
              : 'New firms await Application Admin approval upon onboarding.'}
          </p>
        </div>

        <button
          type="button"
          onClick={() => setInfoMsg('Google SSO is not configured locally. Please register using the form below.')}
          className="w-full py-2.5 px-4 rounded-lg bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-xs font-semibold flex items-center justify-center space-x-2.5 shadow-2xs transition"
        >
          <GoogleGIcon className="w-4 h-4" />
          <span>Continue with Google</span>
        </button>

        <div className="relative my-4">
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
            label="Full name"
            type="text"
            required
            autoComplete="name"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />

          {joinExistingOrg ? (
            <FloatingInput
              label="Organization Code (e.g. GW-2026)"
              type="text"
              required
              value={orgCode}
              onChange={(e) => setOrgCode(e.target.value.toUpperCase())}
              inputClassName="font-mono uppercase tracking-wider"
            />
          ) : (
            <FloatingInput
              label="Firm / School Name"
              type="text"
              required
              autoComplete="organization"
              value={schoolName}
              onChange={(e) => setSchoolName(e.target.value)}
            />
          )}

          <FloatingInput
            label="Work Email"
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
              minLength={6}
              autoComplete="new-password"
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
            <p className="text-[11px] text-slate-400 mt-1">Must be at least 6 characters.</p>
          </div>

          <div>
            <FloatingInput
              label="Confirm password"
              type={showConfirmPassword ? 'text' : 'password'}
              required
              minLength={6}
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              hasError={Boolean(confirmPassword && confirmPassword !== password)}
              rightElement={
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  aria-label={showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'}
                  className="text-slate-400 hover:text-slate-600 transition"
                >
                  {showConfirmPassword ? <EyeOffIcon className="w-4 h-4" /> : <EyeIcon className="w-4 h-4" />}
                </button>
              }
            />
            {confirmPassword && confirmPassword !== password && (
              <p className="text-[11px] text-rose-600 mt-1">Passwords do not match.</p>
            )}
          </div>

          <button
            type="submit"
            disabled={loading}
            className="group w-full mt-1 py-2.5 px-4 rounded-lg bg-signup hover:bg-signup-hover text-signup-text font-semibold text-xs shadow-sm flex items-center justify-center space-x-2 transition disabled:opacity-50"
          >
            <span>{loading ? 'Submitting...' : joinExistingOrg ? 'Request Instructor Access' : 'Create Firm Account'}</span>
            {!loading && <ArrowRightIcon className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform duration-200" />}
          </button>
        </form>

        <div className="mt-4 text-center">
          <button
            type="button"
            onClick={() => setJoinExistingOrg(!joinExistingOrg)}
            className="text-[11px] font-medium text-brand-primary hover:underline"
          >
            {joinExistingOrg
              ? 'Registering a new Firm instead?'
              : 'Have an invite code from your Firm? Join as Instructor'}
          </button>
        </div>

        <div className="mt-4 pt-4 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
          <button
            type="button"
            onClick={onSwitchToLogin}
            className="text-brand-primary hover:text-brand-primary-hover font-semibold"
          >
            Sign in
          </button>
          <button
            type="button"
            onClick={onOpenContactSales}
            className="text-slate-600 hover:text-slate-900 font-medium"
          >
            Contact Sales
          </button>
        </div>
      </div>
    </AuthBackdrop>
  );
};
