import React, { useEffect, useRef, useState } from 'react';
import { THEME } from '../../theme/colors';
import {
  GradifiedLogo,
  ArrowRightIcon,
  DownloadIcon,
  PaperPlaneTrailArrow,
} from '../Icons';

const TRUSTED_SCHOOLS = [
  { name: 'GD GOENKA', sub: 'SCHOOL NETWORK' },
  { name: 'DELHI PUBLIC SCHOOL', sub: 'DPS SOCIETY' },
  { name: 'ORCHIDS', sub: 'THE INTERNATIONAL SCHOOL' },
  { name: 'RYAN INTERNATIONAL', sub: 'EDUCATIONAL GROUP' },
  { name: 'GREENWOOD', sub: 'ACADEMY OF SCIENCES' },
  { name: 'DAV PUBLIC', sub: 'INSTITUTION NETWORK' },
  { name: 'ST. XAVIER', sub: 'COLLEGIATE SCHOOL' },
];

export const LandingPage = ({ onGoToLogin, onOpenContactSales }) => {
  const [selectedQuestionType, setSelectedQuestionType] = useState('Subjective');
  const [inHero, setInHero] = useState(true);
  const [inBottomCta, setInBottomCta] = useState(false);

  const heroCtaRef = useRef(null);
  const bottomCtaRef = useRef(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.target === heroCtaRef.current) {
            setInHero(entry.isIntersecting);
          }
          if (entry.target === bottomCtaRef.current) {
            setInBottomCta(entry.isIntersecting);
          }
        });
      },
      { threshold: 0.1 }
    );

    if (heroCtaRef.current) observer.observe(heroCtaRef.current);
    if (bottomCtaRef.current) observer.observe(bottomCtaRef.current);

    return () => observer.disconnect();
  }, []);

  const showFloatingCta = !inHero && !inBottomCta;

  const scrollToSection = (id) => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div className="min-h-screen bg-surface-page text-slate-900 font-sans overflow-x-clip">
      {/* 1. Solid Architectural Navigation Bar */}
      <header className="sticky top-0 z-40 bg-surface-page border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <button
            type="button"
            className="cursor-pointer focus:outline-none"
            onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          >
            <GradifiedLogo className="h-8 w-auto" />
          </button>

          <nav className="hidden md:flex items-center space-x-8 text-sm font-medium text-slate-600">
            <button onClick={() => scrollToSection('features')} className="hover:text-logo-ink transition">
              Features
            </button>
            <button onClick={() => scrollToSection('how-it-works')} className="hover:text-logo-ink transition">
              Workflow
            </button>
            <button onClick={() => scrollToSection('stats-bar')} className="hover:text-logo-ink transition">
              Scale
            </button>
            <button onClick={() => scrollToSection('testimonials')} className="hover:text-logo-ink transition">
              Institutions
            </button>
          </nav>

          <div className="flex items-center space-x-3">
            <button
              onClick={onGoToLogin}
              className="text-sm font-medium text-slate-700 hover:text-logo-ink px-3 py-2 transition"
            >
              Log In
            </button>
            <button
              onClick={onOpenContactSales}
              className="group inline-flex items-center space-x-1.5 text-sm font-semibold text-signup-text bg-signup hover:bg-signup-hover px-4 py-2 rounded-lg transition-colors duration-200"
            >
              <span>Contact Sales</span>
              <ArrowRightIcon className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform duration-200" />
            </button>
          </div>
        </div>
      </header>

      {/* 2. Hero Section with Clean Architectural Backgrid */}
      <section className="relative overflow-hidden border-b border-slate-200 bg-backgrid">
        <div className="relative z-10 max-w-7xl mx-auto rail-guides px-4 sm:px-6 lg:px-8 pt-14 pb-20 lg:pt-20 lg:pb-24">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
            {/* Left Copy */}
            <div className="lg:col-span-6 space-y-6">
              <p className="font-mono text-[11px] font-medium uppercase tracking-[0.18em] text-logo-sage-deep">
                Institutional Assessment Infrastructure
              </p>

              <h1 className="font-display text-4xl sm:text-5xl lg:text-[54px] font-bold tracking-[-0.03em] leading-[1.06] text-logo-ink">
                Smarter Grading.
                <span className="block text-slate-500 mt-1">Better Learning.</span>
              </h1>

              <p className="text-base sm:text-[17px] text-slate-600 leading-relaxed max-w-xl">
                Gradified automates handwritten booklet evaluation, delivers audit-ready analytics, and reduces faculty workload so educators can stay focused on instruction.
              </p>

              {/* 2-Column Structured Capability List */}
              <div className="grid grid-cols-2 gap-x-8 gap-y-2.5 max-w-md pt-1 text-sm text-slate-700">
                {[
                  'AI-Powered Grading',
                  'Instant Scorecards',
                  'Cohort Analytics',
                  'Custom Rubrics',
                  'CBSE / ICSE Aligned',
                  'Role-Gated Access',
                ].map((cap) => (
                  <div key={cap} className="flex items-center space-x-2.5">
                    <span className="w-3 h-[1.5px] bg-logo-sage-deep flex-shrink-0" />
                    <span className="font-medium text-slate-800">{cap}</span>
                  </div>
                ))}
              </div>

              {/* CTA Buttons */}
              <div ref={heroCtaRef} className="flex flex-wrap items-center gap-3.5 pt-2">
                <button
                  onClick={onGoToLogin}
                  className="group inline-flex items-center space-x-2 px-5 py-3 rounded-lg bg-signup hover:bg-signup-hover text-signup-text font-semibold text-sm transition-colors duration-200"
                >
                  <span>Log In to Explore</span>
                  <ArrowRightIcon className="w-4 h-4 group-hover:translate-x-1 transition-transform duration-200" />
                </button>
                <button
                  onClick={onOpenContactSales}
                  className="inline-flex items-center px-5 py-3 rounded-lg bg-surface-card hover:bg-slate-50 text-logo-ink border border-slate-300 font-semibold text-sm transition"
                >
                  Contact Sales
                </button>
              </div>

              {/* Hairline Institutional Summary */}
              <div className="pt-5 border-t border-slate-200/90 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-slate-500 font-mono">
                <span>150+ PARTNER SCHOOLS</span>
                <span className="text-slate-300">|</span>
                <span>2.4M+ SCRIPTS EVALUATED</span>
                <span className="text-slate-300">|</span>
                <span>98.1% OCR VERIFIED</span>
              </div>
            </div>

            {/* Right Dashboard Preview Mockup */}
            <div className="lg:col-span-6">
              <div className="bg-surface-card rounded-xl border border-slate-200 shadow-lg shadow-slate-200/50 overflow-hidden">
                {/* Mockup Top Bar */}
                <div className="px-4 py-2.5 border-b border-slate-200 flex items-center justify-between bg-surface-preview">
                  <GradifiedLogo className="h-5 w-auto" />
                  <div className="hidden sm:flex items-center bg-surface-card border border-slate-200 rounded px-2.5 py-1 w-48 text-[10px] text-slate-400">
                    Search assessments, cohorts...
                  </div>
                  <div className="flex items-center space-x-2">
                    <span className="px-1.5 py-0.5 rounded border border-logo-sage-border bg-logo-sage-soft text-[9px] font-mono font-semibold text-logo-sage-deep">
                      FIRM ADMIN
                    </span>
                  </div>
                </div>

                {/* Mockup Body */}
                <div className="grid grid-cols-12 bg-surface-preview-canvas">
                  {/* Sidebar */}
                  <div className="col-span-3 border-r border-slate-200/80 bg-surface-card p-2.5 space-y-1 text-[10px] hidden sm:block">
                    {['Overview', 'Assessments', 'Booklets', 'Instructors', 'Analytics', 'Question Bank', 'Reports', 'Usage & Costs'].map((item, idx) => (
                      <div
                        key={item}
                        className={`px-2 py-1.5 rounded font-medium ${idx === 0
                            ? 'bg-logo-sage-soft text-logo-ink font-semibold border border-logo-sage-border/70'
                            : 'text-slate-500'
                          }`}
                      >
                        {item}
                      </div>
                    ))}
                  </div>

                  {/* Main Preview Canvas */}
                  <div className="col-span-12 sm:col-span-9 p-3.5 space-y-3">
                    {/* 4 KPI tiles */}
                    <div className="grid grid-cols-4 gap-2">
                      <div className="bg-surface-card p-2.5 rounded-lg border border-slate-200/90">
                        <p className="text-[8px] uppercase tracking-wider text-slate-400 font-semibold">Scripts</p>
                        <p className="font-mono text-xs font-bold text-logo-ink mt-0.5">82,450</p>
                        <p className="text-[8px] text-logo-sage-deep font-semibold">+18% MoM</p>
                      </div>
                      <div className="bg-surface-card p-2.5 rounded-lg border border-slate-200/90">
                        <p className="text-[8px] uppercase tracking-wider text-slate-400 font-semibold">Students</p>
                        <p className="font-mono text-xs font-bold text-logo-ink mt-0.5">12,540</p>
                        <p className="text-[8px] text-logo-sage-deep font-semibold">+9% MoM</p>
                      </div>
                      <div className="bg-surface-card p-2.5 rounded-lg border border-slate-200/90">
                        <p className="text-[8px] uppercase tracking-wider text-slate-400 font-semibold">Accuracy</p>
                        <p className="font-mono text-xs font-bold text-logo-ink mt-0.5">96.8%</p>
                        <p className="text-[8px] text-logo-sage-deep font-semibold">Verified</p>
                      </div>
                      <div className="bg-surface-card p-2.5 rounded-lg border border-slate-200/90">
                        <p className="text-[8px] uppercase tracking-wider text-slate-400 font-semibold">Latency</p>
                        <p className="font-mono text-xs font-bold text-logo-ink mt-0.5">18 sec</p>
                        <p className="text-[8px] text-slate-400">per booklet</p>
                      </div>
                    </div>

                    {/* Middle Charts Row */}
                    <div className="grid grid-cols-12 gap-2">
                      <div className="col-span-6 bg-surface-card p-2.5 rounded-lg border border-slate-200/90">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-[9px] font-semibold text-logo-ink">Evaluation Accuracy</span>
                          <span className="font-mono text-[8px] text-slate-400">7D</span>
                        </div>
                        <svg viewBox="0 0 200 65" className="w-full h-16">
                          <path d="M0 50 L35 45 L70 39 L105 32 L140 24 L175 17 L200 10 L200 65 L0 65 Z" fill={THEME.chart.primarySoft} />
                          <path d="M0 50 L35 45 L70 39 L105 32 L140 24 L175 17 L200 10" fill="none" stroke={THEME.chart.primary} strokeWidth="2" />
                        </svg>
                      </div>

                      <div className="col-span-3 bg-surface-card p-2.5 rounded-lg border border-slate-200/90 flex flex-col items-center justify-center">
                        <span className="text-[9px] font-semibold text-logo-ink mb-1">Pass Rate</span>
                        <div className="relative w-14 h-14 flex items-center justify-center">
                          <svg viewBox="0 0 36 36" className="w-14 h-14 -rotate-90">
                            <circle cx="18" cy="18" r="14" fill="none" stroke={THEME.chart.track} strokeWidth="3.5" />
                            <circle cx="18" cy="18" r="14" fill="none" stroke={THEME.chart.primary} strokeWidth="3.5" strokeDasharray="84 100" />
                          </svg>
                          <span className="font-mono absolute text-[10px] font-bold text-logo-ink">96%</span>
                        </div>
                      </div>

                      <div className="col-span-3 bg-surface-card p-2.5 rounded-lg border border-slate-200/90 space-y-1.5">
                        <span className="text-[9px] font-semibold text-logo-ink block">Recent Batches</span>
                        {[
                          { name: 'Math - Gr. 10', status: 'Done' },
                          { name: 'Phys - Gr. 11', status: 'Done' },
                          { name: 'Eng - Gr. 9', status: 'Done' },
                        ].map((row) => (
                          <div key={row.name} className="flex items-center justify-between text-[8px]">
                            <span className="text-slate-600 truncate pr-1">{row.name}</span>
                            <span className="px-1 py-0.5 rounded bg-logo-sage-soft text-logo-sage-deep font-mono font-semibold">{row.status}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Bottom Mini Row */}
                    <div className="grid grid-cols-12 gap-2">
                      <div className="col-span-4 bg-surface-card p-2.5 rounded-lg border border-slate-200/90">
                        <span className="text-[8px] font-semibold text-logo-ink block mb-1">Cohort Mean</span>
                        <div className="flex items-end space-x-1.5 h-10 pt-1">
                          {[45, 55, 62, 70, 78, 86].map((h, i) => (
                            <div
                              key={i}
                              style={{ height: `${h}%` }}
                              className={`flex-1 rounded-t-xs ${i >= 4 ? 'bg-logo-sage-deep' : 'bg-logo-sage'}`}
                            />
                          ))}
                        </div>
                      </div>
                      <div className="col-span-4 bg-surface-card p-2.5 rounded-lg border border-slate-200/90 flex items-center space-x-2">
                        <svg viewBox="0 0 36 36" className="w-10 h-10 flex-shrink-0">
                          <circle cx="18" cy="18" r="12" fill="none" stroke={THEME.chart.primary} strokeWidth="5" strokeDasharray="40 100" />
                          <circle cx="18" cy="18" r="12" fill="none" stroke={THEME.chart.secondary} strokeWidth="5" strokeDasharray="35 100" strokeDashoffset="-40" />
                          <circle cx="18" cy="18" r="12" fill="none" stroke={THEME.chart.sage} strokeWidth="5" strokeDasharray="25 100" strokeDashoffset="-75" />
                        </svg>
                        <div className="text-[8px] space-y-0.5 text-slate-600">
                          <p className="font-semibold text-logo-ink">Subjects</p>
                          <p>Math 40% · Sci 35%</p>
                          <p>English 25%</p>
                        </div>
                      </div>
                      <div className="col-span-4 bg-surface-card p-2.5 rounded-lg border border-slate-200/90 text-[8px] space-y-0.5">
                        <span className="font-semibold text-logo-ink block mb-1">Top Campuses</span>
                        <div className="flex justify-between text-slate-600"><span>DPS Noida</span><span className="font-mono font-semibold text-logo-ink">98%</span></div>
                        <div className="flex justify-between text-slate-600"><span>GD Goenka</span><span className="font-mono font-semibold text-logo-ink">95%</span></div>
                        <div className="flex justify-between text-slate-600"><span>Ryan Int.</span><span className="font-mono font-semibold text-logo-ink">93%</span></div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 3. Trusted By Leading Schools Marquee (Clean Editorial Wordmarks) */}
      <section className="py-9 border-b border-slate-200 bg-surface-page overflow-hidden">
        <div className="max-w-7xl mx-auto rail-guides px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-6">
            <p className="font-mono text-[11px] font-medium uppercase tracking-[0.22em] text-slate-500">
              TRUSTED BY LEADING SCHOOLS
            </p>
          </div>

          <div className="relative overflow-hidden border-x border-slate-200">
            <div className="animate-schools-marquee">
              {[...TRUSTED_SCHOOLS, ...TRUSTED_SCHOOLS].map((school, idx) => (
                <div
                  key={`${school.name}-${idx}`}
                  className="flex items-center px-8 sm:px-12 flex-shrink-0 border-r border-slate-100"
                >
                  <div className="flex flex-col items-start">
                    <span className="font-display text-sm font-bold tracking-tight text-logo-ink/75 hover:text-logo-ink transition whitespace-nowrap">
                      {school.name}
                    </span>
                    <span className="font-mono text-[9px] tracking-[0.16em] text-slate-400 whitespace-nowrap mt-0.5">
                      {school.sub}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* 4. Features Bento Section */}
      <section id="features" className="py-20 bg-surface-page">
        <div className="max-w-7xl mx-auto rail-guides px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-10">
            <div className="max-w-xl space-y-2">
              <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-logo-sage-deep">
                PLATFORM CAPABILITIES
              </p>
              <h2 className="font-display text-3xl sm:text-4xl font-bold text-logo-ink tracking-tight leading-tight">
                Everything Needed to Build Modern AI Assessments
              </h2>
              <p className="text-sm sm:text-base text-slate-500">
                Create exams, evaluate answer booklets, analyze performance, and automate reporting from one controlled system.
              </p>
            </div>
            <button
              onClick={onOpenContactSales}
              className="group inline-flex items-center space-x-1.5 text-sm font-semibold text-logo-ink hover:text-logo-sage-deep transition"
            >
              <span>Request Institutional Demo</span>
              <ArrowRightIcon className="w-4 h-4 group-hover:translate-x-1 transition-transform duration-200" />
            </button>
          </div>

          {/* Row 1 Bento */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 mb-5">
            {/* Wide Evaluation Card (Charcoal Logo Ink Surface) */}
            <div className="lg:col-span-6 rounded-xl bg-feature-eval-surface border border-feature-eval-border animate-sage-border p-6 sm:p-7 text-white flex flex-col justify-between gap-6">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                <div className="space-y-2 max-w-sm">
                  <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-logo-sage">
                    01 / AI EVALUATION
                  </span>
                  <h3 className="font-display text-xl font-bold text-white">AI-Powered Evaluation</h3>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    Evaluate handwritten and digital answer sheets within seconds using structured OCR and rubric scoring.
                  </p>
                </div>
                <ul className="grid grid-cols-2 sm:grid-cols-1 gap-1.5 text-xs text-slate-200 flex-shrink-0">
                  {['OCR Extraction', 'Stepwise Scoring', 'Rubric Feedback', 'Instant Ledger'].map((item) => (
                    <li key={item} className="flex items-center space-x-2">
                      <span className="w-2.5 h-[1.5px] bg-logo-sage flex-shrink-0" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Embedded Crisp Evaluation Report Card */}
              <div className="bg-surface-card text-slate-900 rounded-lg border border-slate-200 p-4 space-y-3">
                <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                  <span className="text-xs font-semibold text-logo-ink flex items-center">
                    <span className="w-1.5 h-1.5 rounded-full bg-logo-sage-deep mr-2" />
                    Evaluation Ledger — Batch #204
                  </span>
                  <span className="font-mono text-[10px] font-medium px-2 py-0.5 rounded bg-slate-100 text-slate-600">
                    VERIFIED
                  </span>
                </div>

                <div className="grid grid-cols-4 gap-3 py-1">
                  <div>
                    <p className="text-[10px] text-slate-400">Scripts</p>
                    <p className="font-mono text-sm font-bold text-logo-ink">2,350</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-400">Evaluated</p>
                    <p className="font-mono text-sm font-bold text-logo-ink">2,298</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-400">Accuracy</p>
                    <p className="font-mono text-sm font-bold text-logo-sage-deep">98.1%</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-400">Mean</p>
                    <p className="font-mono text-sm font-bold text-logo-ink">82.6%</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-slate-100 items-center">
                  <div className="flex items-center space-x-3">
                    <div className="relative w-12 h-12 flex items-center justify-center flex-shrink-0">
                      <svg viewBox="0 0 36 36" className="w-12 h-12 -rotate-90">
                        <circle cx="18" cy="18" r="13" fill="none" stroke={THEME.chart.track} strokeWidth="4" />
                        <circle cx="18" cy="18" r="13" fill="none" stroke={THEME.chart.secondary} strokeWidth="4" strokeDasharray="55 100" />
                        <circle cx="18" cy="18" r="13" fill="none" stroke={THEME.chart.primary} strokeWidth="4" strokeDasharray="25 100" strokeDashoffset="-55" />
                      </svg>
                      <span className="font-mono absolute text-[9px] font-bold text-logo-ink">2,298</span>
                    </div>
                    <div className="text-[10px] text-slate-600 space-y-0.5 font-mono">
                      <p className="font-sans font-semibold text-logo-ink text-[11px]">Distribution</p>
                      <p>90–100%: 785</p>
                      <p>75–89%: 742</p>
                    </div>
                  </div>
                  <div>
                    <div className="flex items-center justify-between text-[10px] mb-1">
                      <span className="font-semibold text-logo-ink">Trend</span>
                      <span className="font-mono px-1.5 py-0.5 rounded bg-logo-ink text-white text-[9px]">82.6% AVG</span>
                    </div>
                    <svg viewBox="0 0 120 32" className="w-full h-8">
                      <path d="M0 26 Q20 22 40 24 T80 15 T120 10" fill="none" stroke={THEME.chart.primary} strokeWidth="2" />
                    </svg>
                  </div>
                </div>
              </div>
            </div>

            {/* Performance Analytics Card */}
            <div className="lg:col-span-3 rounded-xl bg-surface-card border border-slate-200 p-6 flex flex-col justify-between overflow-hidden">
              <div>
                <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-logo-sage-deep">
                  02 / ANALYTICS
                </span>
                <h3 className="font-display text-lg font-bold text-logo-ink mt-2">Performance Analytics</h3>
                <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
                  Track every cohort with question-level breakdowns and subject benchmarking.
                </p>
                <ul className="mt-4 space-y-1.5 text-xs text-slate-700">
                  {['Class comparison', 'Weak topic detection', 'Percentile forecasting'].map((item) => (
                    <li key={item} className="flex items-center space-x-2">
                      <span className="w-2.5 h-[1.5px] bg-logo-sage-deep flex-shrink-0" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="mt-6 -mx-6 -mb-6 pt-3">
                <div className="px-6 flex items-baseline justify-between">
                  <span className="font-mono text-[10px] text-slate-400 uppercase">Mean Trajectory</span>
                  <span className="font-mono text-sm font-bold text-logo-sage-deep">85.0%</span>
                </div>
                <svg viewBox="0 0 240 60" className="w-full h-14 mt-1">
                  <path d="M0 45 Q40 25 75 40 T145 30 T210 18 L240 26 L240 60 L0 60 Z" fill={THEME.chart.primarySoft} />
                  <path d="M0 45 Q40 25 75 40 T145 30 T210 18 L240 26" fill="none" stroke={THEME.chart.primary} strokeWidth="2.2" />
                  <circle cx="176" cy="23" r="3" fill={THEME.chart.primary} />
                </svg>
              </div>
            </div>

            {/* Smart OCR Card */}
            <div className="lg:col-span-3 rounded-xl bg-surface-card border border-slate-200 p-6 flex flex-col justify-between">
              <div>
                <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-logo-sage-deep">
                  03 / DOCUMENT OCR
                </span>
                <h3 className="font-display text-lg font-bold text-logo-ink mt-2">Structured OCR</h3>
                <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
                  Ingest scanned answer booklets with automatic field alignment and crop segmentation.
                </p>
                <ul className="mt-4 space-y-1.5 text-xs text-slate-700">
                  {['Multi-page PDFs', 'Auto region crop', 'Handwriting normalization'].map((item) => (
                    <li key={item} className="flex items-center space-x-2">
                      <span className="w-2.5 h-[1.5px] bg-logo-sage-deep flex-shrink-0" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Structured OCR Telemetry Panel */}
              <div className="mt-6 bg-surface-subtle border border-slate-200 rounded-lg p-3 space-y-2 font-mono text-[10px]">
                <div className="flex items-center justify-between text-slate-500 border-b border-slate-200/80 pb-1.5">
                  <span>BOOKLET #4082</span>
                  <span className="text-logo-sage-deep font-semibold">99.4% CONF</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Roll ID</span>
                  <span className="font-semibold text-logo-ink">24CS081</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Regions Parsed</span>
                  <span className="font-semibold text-logo-ink">12 / 12</span>
                </div>
                <div className="w-full h-1.5 bg-slate-200 rounded-full overflow-hidden">
                  <div className="h-full bg-logo-sage-deep w-[94%]" />
                </div>
              </div>
            </div>
          </div>

          {/* Row 2 Bento */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            {/* Automated Reports Card */}
            <div className="lg:col-span-5 rounded-xl bg-feature-reports-surface border border-slate-200 p-6 flex flex-col sm:flex-row gap-5 justify-between">
              <div className="sm:w-5/12 flex flex-col justify-between space-y-4">
                <div>
                  <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-logo-sage-deep">
                    04 / REPORTING
                  </span>
                  <h3 className="font-display text-lg font-bold text-logo-ink mt-2">Automated Reports</h3>
                  <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
                    Generate standardized academic transcripts and institutional exports in one click.
                  </p>
                </div>
                <ul className="space-y-1.5 text-xs text-slate-700">
                  {['Grade Transcripts', 'PDF Scorecards', 'CSV / Excel Ledgers', 'Audit History'].map((item) => (
                    <li key={item} className="flex items-center space-x-2">
                      <span className="w-2.5 h-[1.5px] bg-logo-ink flex-shrink-0" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="sm:w-7/12 bg-surface-card rounded-lg border border-slate-200 p-4 flex flex-col justify-between">
                <div className="flex items-center justify-between text-xs pb-2 border-b border-slate-100">
                  <span className="font-semibold text-logo-ink">Class Performance</span>
                  <span className="font-mono text-[10px] text-slate-500">GRADE 10-A</span>
                </div>

                <div className="flex items-center space-x-4 py-3">
                  <div className="relative w-16 h-16 flex items-center justify-center flex-shrink-0">
                    <svg viewBox="0 0 36 36" className="w-16 h-16 -rotate-90">
                      <circle cx="18" cy="18" r="13" fill="none" stroke={THEME.chart.track} strokeWidth="4" />
                      <circle cx="18" cy="18" r="13" fill="none" stroke={THEME.chart.primary} strokeWidth="4" strokeDasharray="78 100" />
                    </svg>
                    <div className="absolute text-center">
                      <span className="font-mono block text-xs font-bold text-logo-ink">92%</span>
                      <span className="block text-[7px] uppercase text-slate-400">Pass</span>
                    </div>
                  </div>
                  <div className="text-[11px] space-y-1 flex-1">
                    <div className="flex justify-between"><span className="text-slate-600">Distinction (A+)</span><span className="font-mono font-semibold text-logo-ink">65%</span></div>
                    <div className="flex justify-between"><span className="text-slate-600">First Class (B)</span><span className="font-mono font-semibold text-logo-ink">22%</span></div>
                    <div className="flex justify-between"><span className="text-slate-600">Standard (C)</span><span className="font-mono font-semibold text-logo-ink">13%</span></div>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-1.5 pt-2 border-t border-slate-100 font-mono text-[10px] font-medium text-slate-700">
                  <div className="py-1.5 bg-surface-subtle border border-slate-200 rounded text-center">PDF</div>
                  <div className="py-1.5 bg-surface-subtle border border-slate-200 rounded text-center">XLSX</div>
                  <div className="py-1.5 bg-surface-subtle border border-slate-200 rounded text-center">EXPORT</div>
                </div>
              </div>
            </div>

            {/* Custom Assessment Builder Card */}
            <div className="lg:col-span-7 rounded-xl bg-surface-card border border-slate-200 p-6 flex flex-col sm:flex-row gap-6 justify-between">
              <div className="sm:w-5/12 flex flex-col justify-between space-y-4">
                <div>
                  <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-logo-sage-deep">
                    05 / AUTHORING
                  </span>
                  <h3 className="font-display text-xl font-bold text-logo-ink mt-2">Custom Assessment Builder</h3>
                  <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
                    Configure rubrics, subjective marking schemes, objective sections, and code prompts cleanly.
                  </p>
                </div>

                <div className="flex flex-wrap gap-1.5">
                  {['MCQ', 'Subjective', 'Coding', 'File Upload', 'Match', 'True / False'].map((tag) => (
                    <span
                      key={tag}
                      className="font-mono px-2 py-1 rounded bg-surface-subtle border border-slate-200 text-[10px] font-medium text-slate-700"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>

              <div className="sm:w-7/12 grid grid-cols-12 gap-2.5">
                <div className="col-span-7 bg-surface-card border border-slate-200 rounded-lg p-3 space-y-2.5">
                  <div className="flex items-center justify-between text-[11px] font-semibold text-logo-ink border-b border-slate-100 pb-1.5">
                    <span>Prompt Editor</span>
                    <span className="font-mono text-[10px] text-slate-400">RUBRIC 10 PTS</span>
                  </div>
                  <div>
                    <p className="font-mono text-[9px] uppercase text-slate-400 mb-1">Question Stem</p>
                    <div className="p-2 rounded border border-slate-200 text-[11px] text-slate-700 bg-surface-subtle">
                      Explain the light-dependent reactions of photosynthesis.
                    </div>
                  </div>
                  <div>
                    <p className="font-mono text-[9px] uppercase text-slate-400 mb-1">Response Format</p>
                    <div className="px-2.5 py-1.5 rounded border border-slate-200 text-[11px] font-semibold text-logo-ink flex items-center justify-between">
                      <span>{selectedQuestionType}</span>
                      <span className="font-mono text-[9px] text-logo-sage-deep">ACTIVE</span>
                    </div>
                  </div>
                </div>

                <div className="col-span-5 bg-surface-subtle border border-slate-200 rounded-lg p-2.5 space-y-1 text-[10px]">
                  <p className="font-mono text-[9px] uppercase text-slate-400 px-1.5 pb-1">Select Format</p>
                  {['Multiple Choice', 'Subjective', 'True / False', 'Match', 'File Upload', 'Code Submit'].map((opt) => (
                    <button
                      type="button"
                      key={opt}
                      onClick={() => setSelectedQuestionType(opt)}
                      className={`w-full text-left px-2 py-1 rounded font-medium transition ${selectedQuestionType === opt
                          ? 'bg-surface-card text-logo-ink border border-slate-300 font-semibold'
                          : 'text-slate-600 hover:text-logo-ink'
                        }`}
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 5. How It Works Section */}
      <section id="how-it-works" className="py-20 bg-surface-page border-t border-slate-200 bg-backgrid relative">
        <div className="max-w-7xl mx-auto rail-guides px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
            {/* Left Steps (Architectural Typographic Numbering) */}
            <div className="lg:col-span-5 space-y-6">
              <div>
                <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-logo-sage-deep">
                  WORKFLOW
                </p>
                <h2 className="font-display text-3xl sm:text-4xl font-bold text-logo-ink tracking-tight mt-2 leading-tight">
                  Simplify Assessment in 3 Controlled Steps
                </h2>
                <p className="text-sm text-slate-500 mt-3 leading-relaxed">
                  From booklet upload to institutional oversight, every stage stays traceable and auditable.
                </p>
              </div>

              <div className="divide-y divide-slate-200 border-t border-b border-slate-200 bg-surface-card rounded-lg px-5">
                {[
                  {
                    step: '01',
                    title: 'Upload Question Papers & Answer Booklets',
                    desc: 'Instructors register the official rubric and batch-upload scanned PDFs or answer scripts.',
                  },
                  {
                    step: '02',
                    title: 'Automated OCR & Rubric Scoring',
                    desc: 'Each response is transcribed and evaluated against expected marking criteria with clear rationale.',
                  },
                  {
                    step: '03',
                    title: 'Publish & Audit Institutional Analytics',
                    desc: 'Firm leads review cohort trends, approve faculty accounts, and track evaluation usage.',
                  },
                ].map((item) => (
                  <div key={item.step} className="py-4 flex items-start space-x-4">
                    <span className="font-mono text-xs font-semibold px-2 py-1 rounded border border-slate-200 bg-surface-subtle text-logo-ink flex-shrink-0">
                      {item.step}
                    </span>
                    <div>
                      <h3 className="text-sm font-bold text-logo-ink">{item.title}</h3>
                      <p className="text-xs text-slate-500 mt-1 leading-relaxed">{item.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Right Assessment Report Card */}
            <div className="lg:col-span-7">
              <div className="bg-surface-card rounded-xl border border-slate-200 shadow-lg shadow-slate-200/40 p-6 sm:p-7 space-y-6">
                <div className="flex items-center justify-between pb-4 border-b border-slate-200">
                  <div>
                    <p className="font-mono text-[10px] uppercase tracking-wider text-slate-400">COHORT REPORT</p>
                    <h3 className="font-display text-base font-bold text-logo-ink mt-0.5">Mid-Term Examination</h3>
                  </div>
                  <button
                    type="button"
                    onClick={onGoToLogin}
                    className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border border-slate-300 text-xs font-medium text-logo-ink hover:bg-slate-50 transition"
                  >
                    <DownloadIcon className="w-3.5 h-3.5" />
                    <span>Export PDF</span>
                  </button>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-12 gap-4">
                  <div className="sm:col-span-4 bg-surface-subtle border border-slate-200 rounded-lg p-4 flex flex-col justify-between">
                    <p className="font-mono text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                      OVERALL MEAN
                    </p>
                    <p className="font-mono text-4xl font-bold text-logo-ink my-2">85%</p>
                    <div>
                      <span className="font-mono text-[11px] font-semibold text-logo-sage-deep">EXCELLENT STANDING</span>
                      <p className="text-[11px] text-slate-500 mt-0.5">+15% vs previous term</p>
                    </div>
                  </div>

                  <div className="sm:col-span-8 bg-surface-subtle border border-slate-200 rounded-lg p-4">
                    <p className="font-mono text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-3">
                      SCORE DISTRIBUTION
                    </p>
                    <div className="flex items-end justify-between space-x-3 h-28 pt-3">
                      {[
                        { pct: '3%', h: 12, range: '0-20' },
                        { pct: '8%', h: 24, range: '21-40' },
                        { pct: '22%', h: 52, range: '41-60' },
                        { pct: '35%', h: 82, range: '61-80' },
                        { pct: '32%', h: 72, range: '81-100' },
                      ].map((bar) => (
                        <div key={bar.range} className="flex-1 flex flex-col items-center h-full justify-end">
                          <span className="font-mono text-[10px] font-semibold text-logo-ink mb-1">{bar.pct}</span>
                          <div
                            style={{ height: `${bar.h}%` }}
                            className="w-full bg-chart-bar rounded-t-sm"
                          />
                          <span className="font-mono text-[10px] text-slate-500 mt-1.5">{bar.range}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Uniform Hairline Metric Cells (Zero Pastel Candy Boxes) */}
                <div className="grid grid-cols-1 sm:grid-cols-12 gap-4 pt-2 border-t border-slate-100">
                  <div className="sm:col-span-8">
                    <p className="font-mono text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-2.5">
                      CLASS SUMMARY
                    </p>
                    <div className="grid grid-cols-2 gap-2.5">
                      {[
                        { label: 'Total Students', val: '45' },
                        { label: 'Average Score', val: '78%' },
                        { label: 'Highest Score', val: '98%' },
                        { label: 'Lowest Score', val: '35%' },
                      ].map((cell) => (
                        <div key={cell.label} className="p-3 rounded-lg bg-surface-card border border-slate-200 flex items-baseline justify-between">
                          <span className="text-[11px] text-slate-500 font-medium">{cell.label}</span>
                          <span className="font-mono text-sm font-bold text-logo-ink">{cell.val}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="sm:col-span-4 flex flex-col">
                    <p className="font-mono text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-2.5">
                      TOP RANK
                    </p>
                    <div className="flex-1 rounded-lg bg-logo-sage-soft border border-logo-sage-border p-4 flex flex-col justify-between">
                      <span className="font-mono text-[10px] font-semibold text-logo-sage-deep">RANK #01</span>
                      <div>
                        <p className="text-sm font-bold text-logo-ink">Rahul Sharma</p>
                        <p className="font-mono text-xs font-bold text-logo-sage-deep mt-0.5">98 / 100</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* 6. Architectural KPI Ledger */}
          <div
            id="stats-bar"
            className="mt-16 bg-surface-card rounded-xl border border-slate-200 divide-y sm:divide-y-0 sm:divide-x divide-slate-200 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5"
          >
            {[
              { value: '500+', label: 'Partner Institutions' },
              { value: '50K+', label: 'Active Educators' },
              { value: '1M+', label: 'Enrolled Students' },
              { value: '20M+', label: 'Scripts Graded' },
              { value: '95%', label: 'Scoring Agreement' },
            ].map((stat) => (
              <div key={stat.label} className="px-6 py-5 text-center sm:text-left">
                <p className="font-mono text-2xl font-bold text-logo-ink leading-none">{stat.value}</p>
                <p className="text-xs text-slate-500 mt-1.5 font-medium">{stat.label}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 7. Testimonials Section (Clean Editorial Grid, No Avatars or Fake Dots) */}
      <section id="testimonials" className="py-20 bg-surface-page border-t border-slate-200">
        <div className="max-w-7xl mx-auto rail-guides px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-xl mx-auto mb-12">
            <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-logo-sage-deep">
              INSTITUTIONAL FEEDBACK
            </p>
            <h2 className="font-display text-3xl font-bold text-logo-ink tracking-tight mt-2">
              Trusted by Academic Leadership
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              {
                quote: 'Gradified reduced our term-end booklet evaluation cycle from eleven days to under twenty-four hours while maintaining strict marking consistency.',
                name: 'Mrs. Priya Sharma',
                role: 'Principal, DPS Noida',
              },
              {
                quote: 'Question-level analytics give our department heads immediate clarity on conceptual gaps before parent-teacher conferences.',
                name: 'Mr. Arvind Patel',
                role: 'Academic Director, Ryan International',
              },
              {
                quote: 'Having firm-level cost governance alongside instructor approval gives our administration complete control across campuses.',
                name: 'Ms. Neha Verma',
                role: 'Vice Principal, GD Goenka',
              },
            ].map((item) => (
              <div
                key={item.name}
                className="bg-surface-card rounded-xl border border-slate-200 border-t-2 border-t-logo-ink p-6 flex flex-col justify-between"
              >
                <p className="text-sm text-slate-700 leading-relaxed">“{item.quote}”</p>
                <div className="mt-6 pt-4 border-t border-slate-100">
                  <p className="text-xs font-bold text-logo-ink">{item.name}</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">{item.role}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 8. Bottom CTA Section with Backgrid Rails & Paper Plane Arrow */}
      <section ref={bottomCtaRef} className="py-16 bg-surface-page border-t border-slate-200 bg-backgrid relative overflow-hidden">
        <div className="relative z-10 max-w-7xl mx-auto rail-guides px-4 sm:px-6 lg:px-8 py-4">
          <div className="grid grid-cols-1 md:grid-cols-12 gap-8 items-center">
            <div className="md:col-span-7 space-y-2 text-center md:text-left">
              <p className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-logo-sage-deep">
                ENTERPRISE ONBOARDING
              </p>
              <h2 className="font-display text-2xl sm:text-3xl font-bold text-logo-ink tracking-tight leading-tight">
                Ready to Standardize Institutional Assessment?
              </h2>
              <p className="text-sm text-slate-500 max-w-xl">
                Connect with our team to provision your organization, configure grading cost controls, and invite faculty.
              </p>
            </div>

            <div className="md:col-span-5 relative flex flex-col items-center md:items-end justify-center pt-10 pb-8 md:pr-6">
              <PaperPlaneTrailArrow className="w-56 h-32 pointer-events-none hidden sm:block absolute -top-6 right-0 z-0" />

              <div className="relative z-10 flex flex-wrap items-center justify-center md:justify-end gap-3 w-full">
                <button
                  onClick={onOpenContactSales}
                  className="group inline-flex items-center space-x-2 px-5 py-3 rounded-lg bg-signup hover:bg-signup-hover text-signup-text font-semibold text-sm transition-colors duration-200"
                >
                  <span>Contact Sales</span>
                  <ArrowRightIcon className="w-4 h-4 group-hover:translate-x-1 transition-transform duration-200" />
                </button>
                <button
                  onClick={onGoToLogin}
                  className="px-5 py-3 rounded-lg bg-surface-card hover:bg-slate-50 text-logo-ink border border-slate-300 font-semibold text-sm transition"
                >
                  Log In
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 9. Footer */}
      <footer id="footer" className="bg-surface-page border-t border-slate-200 pt-14 pb-10">
        <div className="max-w-7xl mx-auto rail-guides px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-12 gap-8 pb-12 border-b border-slate-200">
            <div className="col-span-2 md:col-span-4 space-y-4">
              <GradifiedLogo className="h-7 w-auto" />
              <p className="text-xs text-slate-500 max-w-xs leading-relaxed">
                Structured OCR and AI assessment infrastructure built for educational institutions.
              </p>
              <p className="font-mono text-[11px] text-slate-500">enterprise@gradified.com</p>
            </div>

            <div className="col-span-1 md:col-span-2 space-y-2.5 text-xs">
              <p className="font-bold text-logo-ink">Product</p>
              <ul className="space-y-2 text-slate-500">
                <li><button onClick={() => scrollToSection('features')} className="hover:text-logo-ink">Features</button></li>
                <li><button onClick={onGoToLogin} className="hover:text-logo-ink">Assessments</button></li>
                <li><button onClick={onGoToLogin} className="hover:text-logo-ink">Reports</button></li>
                <li><button onClick={() => scrollToSection('features')} className="hover:text-logo-ink">Analytics</button></li>
              </ul>
            </div>

            <div className="col-span-1 md:col-span-2 space-y-2.5 text-xs">
              <p className="font-bold text-logo-ink">Roles</p>
              <ul className="space-y-2 text-slate-500">
                <li><button onClick={onOpenContactSales} className="hover:text-logo-ink">For Institutions</button></li>
                <li><button onClick={onGoToLogin} className="hover:text-logo-ink">For Instructors</button></li>
                <li><button onClick={onGoToLogin} className="hover:text-logo-ink">Platform Admin</button></li>
              </ul>
            </div>

            <div className="col-span-1 md:col-span-2 space-y-2.5 text-xs">
              <p className="font-bold text-logo-ink">Company</p>
              <ul className="space-y-2 text-slate-500">
                <li><button onClick={() => scrollToSection('testimonials')} className="hover:text-logo-ink">Institutions</button></li>
                <li><button onClick={onOpenContactSales} className="hover:text-logo-ink">Request Demo</button></li>
                <li><button onClick={() => scrollToSection('stats-bar')} className="hover:text-logo-ink">Scale Metrics</button></li>
              </ul>
            </div>

            <div className="col-span-1 md:col-span-2 space-y-2.5 text-xs">
              <p className="font-bold text-logo-ink">Resources</p>
              <ul className="space-y-2 text-slate-500">
                <li><button onClick={() => scrollToSection('how-it-works')} className="hover:text-logo-ink">Workflow Guide</button></li>
                <li><button onClick={() => scrollToSection('footer')} className="hover:text-logo-ink">Security & Privacy</button></li>
                <li><button onClick={() => scrollToSection('footer')} className="hover:text-logo-ink">Terms of Service</button></li>
              </ul>
            </div>
          </div>

          <div className="pt-6 text-xs text-slate-500 flex flex-col sm:flex-row justify-between gap-2">
            <span>© 2026 Gradified. All rights reserved.</span>
          </div>
        </div>
      </footer>

      {/* Always-In-Screen Floating CTA Dock while scrolling */}
      <div
        className={`fixed bottom-3 right-3 sm:bottom-5 sm:right-5 z-40 max-w-[calc(100vw-1.5rem)] transition-all duration-300 ${showFloatingCta
            ? 'opacity-100 translate-y-0 pointer-events-auto'
            : 'opacity-0 translate-y-4 pointer-events-none'
          }`}
      >
        <div className="flex items-center space-x-2 bg-logo-ink text-white border border-logo-sage-border/30 rounded-xl shadow-lg px-2.5 py-1.5">
          <button
            onClick={onGoToLogin}
            className="px-2.5 py-1 rounded-lg hover:bg-white/10 text-slate-100 text-xs font-semibold transition whitespace-nowrap"
          >
            Log In
          </button>
          <button
            onClick={onOpenContactSales}
            className="group inline-flex items-center space-x-1.5 px-3 py-1 rounded-lg bg-signup hover:bg-signup-hover text-signup-text text-xs font-semibold transition-colors duration-200 whitespace-nowrap"
          >
            <span>Contact Sales</span>
            <ArrowRightIcon className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform duration-200" />
          </button>
        </div>
      </div>
    </div>
  );
};
