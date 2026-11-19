import React from 'react';

/**
 * Shared authentication shell with crisp architectural hairline grid.
 */
export const AuthBackdrop = ({ children }) => (
  <div className="bg-auth-backgrid relative min-h-screen flex flex-col justify-center items-center px-4 py-10 overflow-hidden">
    <div className="relative z-10 w-full flex flex-col items-center">
      {children}
    </div>
  </div>
);
