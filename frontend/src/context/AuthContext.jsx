import React, { createContext, useContext, useState, useEffect } from 'react';
import { authAPI, getAuthTokens, setAuthTokens, getCurrentUser, setCurrentUser } from '../api';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(getCurrentUser());
  const [tokens, setTokens] = useState(getAuthTokens());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const initAuth = async () => {
      const storedTokens = getAuthTokens();
      if (storedTokens?.access) {
        try {
          const freshUser = await authAPI.me();
          setUser(freshUser);
          setCurrentUser(freshUser);
        } catch (err) {
          console.warn('Session expired or invalid token:', err);
          logout();
        }
      }
      setLoading(false);
    };

    initAuth();
  }, []);

  const login = (userData, tokenData) => {
    setUser(userData);
    setTokens(tokenData);
    setCurrentUser(userData);
    setAuthTokens(tokenData);
  };

  const logout = () => {
    setUser(null);
    setTokens(null);
    setCurrentUser(null);
    setAuthTokens(null);
  };

  return (
    <AuthContext.Provider value={{ user, tokens, login, logout, loading, setUser }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

