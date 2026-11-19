import React from 'react';
import { useAuth } from '../context/AuthContext';
import {
  GradifiedLogo,
  LogoutIcon,
} from './Icons';

const ROLE_TABS = {
  admin: [
    { key: 'dashboard', label: 'Platform Overview' },
    { key: 'schools', label: 'Organizations' },
    { key: 'requests', label: 'Sales Queue' },
  ],
  firm: [
    { key: 'dashboard', label: 'Overall Results' },
    { key: 'instructors', label: 'Approve Instructors' },
    { key: 'costs', label: 'Costs & Usage' },
  ],
  instructor: [
    { key: 'dashboard', label: 'Instructor Workspace' },
    { key: 'exams', label: 'Question Papers' },
    { key: 'grading', label: 'Answer Booklets' },
  ],
};

export const Navbar = ({ activeTab, setActiveTab }) => {
  const { user, logout } = useAuth();
  const tabs = ROLE_TABS[user?.role] || ROLE_TABS.instructor;

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between items-center h-16">
          {/* Logo & Brand */}
          <div className="flex items-center space-x-3 cursor-pointer" onClick={() => setActiveTab('dashboard')}>
            <GradifiedLogo className="h-8 w-auto" />
            <span className="hidden sm:inline-flex items-center px-2 py-0.5 rounded font-mono text-[10px] font-medium bg-surface-subtle text-slate-600 border border-slate-200">
              OCR ENGINE v1
            </span>
          </div>

          {/* Navigation Links for Authenticated Users */}
          {user && (
            <div className="flex items-center space-x-4">
              <div className="hidden sm:flex items-center space-x-1 bg-slate-100 p-1 rounded-lg">
                {tabs.map((tab) => (
                  <button
                    key={tab.key}
                    onClick={() => setActiveTab(tab.key)}
                    className={`px-3 py-1.5 rounded-md text-xs font-semibold transition ${
                      activeTab === tab.key
                        ? 'bg-white shadow-xs text-brand-primary font-bold'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* User Identity Pill */}
              <div className="flex items-center space-x-3 pl-3 border-l border-slate-200">
                <div className="text-right hidden md:block">
                  <div className="flex items-center justify-end space-x-1.5">
                    <span className="text-sm font-semibold text-logo-ink">{user.username || user.email}</span>
                  </div>
                  <span className="text-xs text-slate-500 flex items-center justify-end font-mono">
                    {user.role === 'admin' ? (
                      <span className="text-logo-ink font-semibold">
                        Application Admin
                      </span>
                    ) : user.role === 'firm' ? (
                      <span className="text-logo-sage-deep font-medium">
                        Firm Lead · {user.organization_name || user.school_name}
                      </span>
                    ) : (
                      <span className="text-logo-sage-deep font-medium">
                        Instructor · {user.organization_name || user.school_name}
                      </span>
                    )}
                  </span>
                </div>

                <button
                  onClick={logout}
                  title="Sign Out"
                  className="p-2 text-slate-500 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition"
                >
                  <LogoutIcon className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
