import React from 'react';
import logoFull from '../assets/logo-full.webp';
import { THEME } from '../theme/colors';

export const GradifiedLogo = ({ className = 'h-8 w-auto' }) => (
  <div className="inline-flex items-center select-none">
    <img src={logoFull} alt="Gradified" className={`${className} object-contain`} />
  </div>
);

export const CheckCircleIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <circle cx="10" cy="10" r="8" />
    <path d="M6.8 10.2L9 12.4L13.5 7.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const ArrowRightIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8">
    <path d="M4 10H16M16 10L11 5M16 10L11 15" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const ArrowLeftIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8">
    <path d="M16 10H4M4 10L9 5M4 10L9 15" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const PlayCircleIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <circle cx="10" cy="10" r="8" />
    <path d="M8.5 7.2L13 10L8.5 12.8V7.2Z" fill="currentColor" stroke="none" />
  </svg>
);

export const ChevronDownIcon = ({ className = 'w-3.5 h-3.5' }) => (
  <svg className={className} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M4 6L8 10L12 6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const CloseIcon = ({ className = 'w-5 h-5' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8">
    <path d="M5 5L15 15M15 5L5 15" strokeLinecap="round" />
  </svg>
);

export const MailIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <rect x="2.5" y="4.5" width="15" height="11" rx="2" />
    <path d="M3 5.5L10 10.5L17 5.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const LockIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <rect x="4" y="9" width="12" height="8.5" rx="2" />
    <path d="M6.5 9V6.5C6.5 4.567 8.067 3 10 3C11.933 3 13.5 4.567 13.5 6.5V9" strokeLinecap="round" />
  </svg>
);

export const UserIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <circle cx="10" cy="6.5" r="3.2" />
    <path d="M4 17C4 13.8 6.686 11.5 10 11.5C13.314 11.5 16 13.8 16 17" strokeLinecap="round" />
  </svg>
);

export const SchoolIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M3 9L10 4L17 9" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M4.5 9V16.5H15.5V9" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M8.5 16.5V12.5H11.5V16.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const ShieldIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M10 2.5L16.5 5V9.5C16.5 13.6 13.7 16.7 10 17.8C6.3 16.7 3.5 13.6 3.5 9.5V5L10 2.5Z" strokeLinejoin="round" />
    <path d="M7.5 10L9.2 11.7L12.8 8.1" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const PhoneIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M4.5 3.5H7.5L8.8 6.8L7 8.1C7.9 9.9 9.4 11.4 11.2 12.3L12.5 10.5L15.8 11.8V14.8C15.8 15.6 15.1 16.3 14.3 16.3C8.5 15.9 4.1 11.5 3.7 5.7C3.7 4.9 4.4 3.5 4.5 3.5Z" strokeLinejoin="round" />
  </svg>
);

export const KeyIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <circle cx="7.5" cy="10" r="3.5" />
    <path d="M11 10H17M14.5 10V12.5M17 10V12.5" strokeLinecap="round" />
  </svg>
);

export const RefreshIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M16.5 10C16.5 13.59 13.59 16.5 10 16.5C6.41 16.5 3.5 13.59 3.5 10C3.5 6.41 6.41 3.5 10 3.5C12.2 3.5 14.15 4.6 15.32 6.28" strokeLinecap="round" />
    <path d="M16 3.5V6.8H12.7" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const AlertIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <circle cx="10" cy="10" r="8" />
    <path d="M10 6.5V10.5M10 13.5H10.01" strokeLinecap="round" />
  </svg>
);

export const LogoutIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M8 4H4.5C3.67 4 3 4.67 3 5.5V14.5C3 15.33 3.67 16 4.5 16H8" strokeLinecap="round" />
    <path d="M12.5 13.5L16.5 10L12.5 6.5M16.5 10H7.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const PlusIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8">
    <path d="M10 4V16M4 10H16" strokeLinecap="round" />
  </svg>
);

export const SearchIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <circle cx="9" cy="9" r="5.5" />
    <path d="M13.5 13.5L17 17" strokeLinecap="round" />
  </svg>
);

export const BookIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M3.5 4.5H8.5C9.33 4.5 10 5.17 10 6V16C10 15.17 9.33 14.5 8.5 14.5H3.5V4.5Z" strokeLinejoin="round" />
    <path d="M16.5 4.5H11.5C10.67 4.5 10 5.17 10 6V16C10 15.17 10.67 14.5 11.5 14.5H16.5V4.5Z" strokeLinejoin="round" />
  </svg>
);

export const FileTextIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M5 3H12L15.5 6.5V17H5V3Z" strokeLinejoin="round" />
    <path d="M12 3V6.5H15.5M7.5 10H12.5M7.5 13H11" strokeLinecap="round" />
  </svg>
);

export const UploadIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M10 13V4M10 4L6.5 7.5M10 4L13.5 7.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M3.5 13.5V15.5C3.5 16.05 3.95 16.5 4.5 16.5H15.5C16.05 16.5 16.5 16.05 16.5 15.5V13.5" strokeLinecap="round" />
  </svg>
);

export const BarChartIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M4.5 16V10.5M10 16V4.5M15.5 16V7.5" strokeLinecap="round" />
  </svg>
);

export const ScanIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M3.5 7V4.5C3.5 3.95 3.95 3.5 4.5 3.5H7M13 3.5H15.5C16.05 3.5 16.5 3.95 16.5 4.5V7M16.5 13V15.5C16.5 16.05 16.05 16.5 15.5 16.5H13M7 16.5H4.5C3.95 16.5 3.5 16.05 3.5 15.5V13" strokeLinecap="round" />
    <path d="M4 10H16" strokeLinecap="round" />
  </svg>
);

export const CpuIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <rect x="5.5" y="5.5" width="9" height="9" rx="1.5" />
    <path d="M8 3V5.5M12 3V5.5M8 14.5V17M12 14.5V17M3 8H5.5M3 12H5.5M14.5 8H17M14.5 12H17" strokeLinecap="round" />
  </svg>
);

export const TrashIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M4 5.5H16M7.5 5.5V3.5H12.5V5.5M6 5.5V16.5H14V5.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const PrinterIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M6 7V3.5H14V7M6 13.5H4V8.5H16V13.5H14M6 11.5H14V16.5H6V11.5Z" strokeLinejoin="round" />
  </svg>
);

export const DownloadIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M10 3.5V13M10 13L6.5 9.5M10 13L13.5 9.5M4 15.5H16" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const UsersIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <circle cx="7.5" cy="7" r="2.5" />
    <path d="M3 16C3 13.5 5 11.8 7.5 11.8C10 11.8 12 13.5 12 16" strokeLinecap="round" />
    <circle cx="13.5" cy="7.5" r="2" />
    <path d="M13.5 12.2C15.5 12.2 17 13.6 17 16" strokeLinecap="round" />
  </svg>
);

export const HashIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M4.5 7.5H15.5M4.5 12.5H15.5M8.5 4L6.5 16M13.5 4L11.5 16" strokeLinecap="round" />
  </svg>
);

export const EyeIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M2.5 10C4.3 6.6 7 5 10 5C13 5 15.7 6.6 17.5 10C15.7 13.4 13 15 10 15C7 15 4.3 13.4 2.5 10Z" strokeLinejoin="round" />
    <circle cx="10" cy="10" r="2.3" />
  </svg>
);

export const EyeOffIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M3 3L17 17" strokeLinecap="round" />
    <path d="M8.2 5.3C8.8 5.1 9.4 5 10 5C13 5 15.7 6.6 17.5 10C16.8 11.4 15.9 12.5 14.8 13.3M5.4 6.6C4.2 7.5 3.3 8.6 2.5 10C4.3 13.4 7 15 10 15C11.2 15 12.3 14.7 13.3 14.2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const GoogleGIcon = ({ className = 'w-4 h-4' }) => (
  <svg className={className} viewBox="0 0 24 24">
    <path fill={THEME.oauth.googleRed} d="M12 5c1.6 0 3 .6 4.1 1.6l3.1-3.1C17.3 1.7 14.8 1 12 1 7.4 1 3.5 3.6 1.6 7.4l3.7 2.8C6.2 7.2 8.9 5 12 5z" />
    <path fill={THEME.oauth.googleBlue} d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.5h6.5c-.3 1.5-1.1 2.8-2.4 3.6l3.7 2.9c2.2-2 3.7-5 3.7-8.7z" />
    <path fill={THEME.oauth.googleYellow} d="M5.3 14.8c-.2-.8-.4-1.8-.4-2.8s.2-2 .4-2.8L1.6 6.4C.6 8.3 0 10.1 0 12s.6 3.7 1.6 5.6l3.7-2.8z" />
    <path fill={THEME.oauth.googleGreen} d="M12 23c3.2 0 6-1.1 8-3l-3.7-2.9c-1.1.7-2.5 1.2-4.3 1.2-3.1 0-5.8-2.1-6.7-5l-3.7 2.8C3.5 20.4 7.4 23 12 23z" />
  </svg>
);

export const PaperPlaneTrailArrow = ({ className = 'w-56 h-32' }) => (
  <svg className={className} viewBox="0 0 250 130" fill="none" aria-hidden="true">
    <path
      d="M14 114 C48 88, 92 84, 134 90 C166 94, 178 76, 156 64 C138 55, 130 76, 152 84 C178 93, 206 60, 218 28"
      stroke={THEME.cta.trail}
      strokeWidth="1.6"
      strokeDasharray="4 4"
      strokeLinecap="round"
      className="animate-dash-trail"
    />
    <g className="animate-plane-bob">
      <path d="M208 21 L238 11 L226 37 L218 25 L208 21 Z" fill={THEME.cta.planeLight} />
      <path d="M238 11 L218 25 L221 33 L226 37 L238 11 Z" fill={THEME.cta.planeDark} />
    </g>
  </svg>
);


