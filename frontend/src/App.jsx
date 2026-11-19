import React, { useEffect, useState } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Navbar } from './components/Navbar';
import { LandingPage } from './components/Landing/LandingPage';
import { ContactSalesModal } from './components/Landing/ContactSalesModal';
import { Login } from './components/Auth/Login';
import { Signup } from './components/Auth/Signup';
import { VerifyEmail } from './components/Auth/VerifyEmail';
import { AdminDashboard } from './components/Admin/AdminDashboard';
import { FirmDashboard } from './components/Firm/FirmDashboard';
import { TeacherDashboard } from './components/Teacher/TeacherDashboard';
import { AuthBackdrop } from './components/Auth/AuthBackdrop';
import { GradifiedLogo, ShieldIcon } from './components/Icons';

const PendingApprovalScreen = ({ user, onLogout }) => {
  const isOrgPending = user.organization_status !== 'APPROVED';
  return (
    <AuthBackdrop>
      <div className="w-full max-w-md bg-white/95 rounded-2xl shadow-lg border border-slate-200 p-7 text-center space-y-4">
        <div className="flex justify-center">
          <GradifiedLogo className="h-8 w-auto" />
        </div>
        <div className="w-12 h-12 rounded-full bg-amber-50 border border-amber-200 text-amber-600 flex items-center justify-center mx-auto">
          <ShieldIcon className="w-6 h-6" />
        </div>
        <h2 className="text-lg font-bold text-slate-900">
          {isOrgPending ? 'Organization Awaiting Admin Approval' : 'Instructor Access Pending Firm Approval'}
        </h2>
        <p className="text-xs text-slate-500 leading-relaxed">
          {isOrgPending ? (
            <>
              <span className="font-semibold text-slate-800">{user.organization_name || 'Your organization'}</span> has been registered (Code: <span className="font-mono font-bold text-slate-800">{user.organization_code}</span>) and is currently waiting for Role 1 Application Admin approval.
            </>
          ) : (
            <>
              Your instructor request for <span className="font-semibold text-slate-800">{user.organization_name}</span> is waiting for approval by your Firm Administrator.
            </>
          )}
        </p>
        <div className="pt-2">
          <button
            onClick={onLogout}
            className="px-5 py-2.5 rounded-lg bg-brand-primary hover:bg-brand-primary-hover text-white text-xs font-semibold transition"
          >
            Sign Out & Return
          </button>
        </div>
      </div>
    </AuthBackdrop>
  );
};

const MainApp = () => {
  const { user, loading, logout } = useAuth();

  // Auth view state: 'landing' | 'login' | 'signup' | 'verify'
  const [authView, setAuthView] = useState('landing');
  const [signupInstructorMode, setSignupInstructorMode] = useState(false);
  const [contactSalesOpen, setContactSalesOpen] = useState(false);
  const [verifyEmail, setVerifyEmail] = useState('');
  const [verifyCode, setVerifyCode] = useState('');

  // Navigation tab
  const [activeTab, setActiveTab] = useState('dashboard');

  useEffect(() => {
    setActiveTab('dashboard');
  }, [user?.id]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white">
        <div className="text-center space-y-3">
          <div className="w-9 h-9 border-4 border-brand-primary border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-sm font-semibold text-slate-600">Initializing Gradified System...</p>
        </div>
      </div>
    );
  }

  // Not authenticated
  if (!user) {
    return (
      <>
        {authView === 'login' ? (
          <Login
            onSwitchToSignup={() => {
              setSignupInstructorMode(false);
              setAuthView('signup');
            }}
            onJoinAsInstructor={() => {
              setSignupInstructorMode(true);
              setAuthView('signup');
            }}
            onBackToHome={() => setAuthView('landing')}
            onOpenContactSales={() => setContactSalesOpen(true)}
            onRequireVerification={(email, code) => {
              setVerifyEmail(email);
              setVerifyCode(code);
              setAuthView('verify');
            }}
          />
        ) : authView === 'signup' ? (
          <Signup
            defaultJoinOrg={signupInstructorMode}
            onSwitchToLogin={() => setAuthView('login')}
            onBackToHome={() => setAuthView('landing')}
            onOpenContactSales={() => setContactSalesOpen(true)}
            onRegistered={(email, code) => {
              setVerifyEmail(email);
              setVerifyCode(code);
              setAuthView('verify');
            }}
          />
        ) : authView === 'verify' ? (
          <VerifyEmail
            email={verifyEmail}
            defaultCode={verifyCode}
            onBackToLogin={() => setAuthView('login')}
          />
        ) : (
          <LandingPage
            onGoToLogin={() => setAuthView('login')}
            onOpenContactSales={() => setContactSalesOpen(true)}
          />
        )}

        <ContactSalesModal
          isOpen={contactSalesOpen}
          onClose={() => setContactSalesOpen(false)}
          onGoToLogin={() => setAuthView('login')}
        />
      </>
    );
  }

  // Gate unapproved firms or unapproved instructors cleanly
  const isBlockedPending =
    user.role !== 'admin' &&
    (user.organization_status !== 'APPROVED' || (user.role === 'instructor' && !user.is_approved));

  if (isBlockedPending) {
    return <PendingApprovalScreen user={user} onLogout={logout} />;
  }

  // Authenticated Role Dispatch
  return (
    <div className="min-h-screen bg-slate-50/60 flex flex-col">
      <Navbar activeTab={activeTab} setActiveTab={setActiveTab} />
      <main className="flex-1 pb-16">
        {user.role === 'admin' ? (
          <AdminDashboard activeTab={activeTab} />
        ) : user.role === 'firm' ? (
          <FirmDashboard activeTab={activeTab} />
        ) : (
          <TeacherDashboard activeTab={activeTab} />
        )}
      </main>
      <footer className="border-t border-slate-200 py-6 text-center text-xs text-slate-500 bg-white">
        <p>Gradified Assessment Engine • Direct Integration with <span className="font-semibold text-slate-700">ocr-service</span> • Built with React & Django</p>
      </footer>
    </div>
  );
};

export default function App() {
  return (
    <AuthProvider>
      <MainApp />
    </AuthProvider>
  );
}
