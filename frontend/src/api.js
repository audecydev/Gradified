// API helper functions with token injection and error handling

const API_BASE = '/api';

export const getAuthTokens = () => {
  const tokens = localStorage.getItem('grad_tokens');
  return tokens ? JSON.parse(tokens) : null;
};

export const setAuthTokens = (tokens) => {
  if (tokens) {
    localStorage.setItem('grad_tokens', JSON.stringify(tokens));
  } else {
    localStorage.removeItem('grad_tokens');
  }
};

export const getCurrentUser = () => {
  const user = localStorage.getItem('grad_user');
  return user ? JSON.parse(user) : null;
};

export const setCurrentUser = (user) => {
  if (user) {
    localStorage.setItem('grad_user', JSON.stringify(user));
  } else {
    localStorage.removeItem('grad_user');
  }
};

export const apiRequest = async (endpoint, options = {}) => {
  const tokens = getAuthTokens();
  const headers = {
    ...options.headers,
  };

  if (tokens?.access) {
    headers['Authorization'] = `Bearer ${tokens.access}`;
  }

  if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const url = `${API_BASE}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (response.status === 204) {
    return null;
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const errorMsg = data?.error || data?.detail || data?.message || 'Request failed';
    const error = new Error(errorMsg);
    error.status = response.status;
    error.data = data;
    throw error;
  }

  return data;
};

export const salesAPI = {
  submitDemoRequest: (payload) => apiRequest('/contact-sales/', { method: 'POST', body: JSON.stringify(payload) }),
};

export const authAPI = {
  signup: (payload) => apiRequest('/auth/signup/', { method: 'POST', body: JSON.stringify(payload) }),
  verifyEmail: (payload) => apiRequest('/auth/verify-email/', { method: 'POST', body: JSON.stringify(payload) }),
  resendVerification: (email) => apiRequest('/auth/resend-verification/', { method: 'POST', body: JSON.stringify({ email }) }),
  login: (payload) => apiRequest('/auth/login/', { method: 'POST', body: JSON.stringify(payload) }),
  me: () => apiRequest('/auth/me/'),
};

export const adminAPI = {
  getOrganizations: () => apiRequest('/admin/organizations/'),
  getSchools: () => apiRequest('/admin/organizations/'),
  onboardSchool: (payload) => apiRequest('/admin/onboard-school/', { method: 'POST', body: JSON.stringify(payload) }),
  updateOrgStatus: (id, payload) => apiRequest(`/admin/organizations/${id}/status/`, { method: 'PATCH', body: JSON.stringify(payload) }),
  toggleSchoolStatus: (id, payload) => apiRequest(`/admin/organizations/${id}/status/`, { method: 'PATCH', body: JSON.stringify(payload) }),
  getDemoRequests: () => apiRequest('/admin/demo-requests/'),
  updateDemoRequest: (id, payload) => apiRequest(`/admin/demo-requests/${id}/`, { method: 'PATCH', body: JSON.stringify(payload) }),
  getStats: () => apiRequest('/admin/stats/'),
};

export const firmAPI = {
  getOverview: () => apiRequest('/firm/overview/'),
  getInstructors: () => apiRequest('/firm/instructors/'),
  inviteInstructor: (payload) => apiRequest('/firm/instructors/', { method: 'POST', body: JSON.stringify(payload) }),
  toggleInstructorApproval: (id, payload) => apiRequest(`/firm/instructors/${id}/approve/`, { method: 'PATCH', body: JSON.stringify(payload) }),
};

export const subjectAPI = {
  getAll: () => apiRequest('/subjects/'),
  create: (payload) => apiRequest('/subjects/', { method: 'POST', body: JSON.stringify(payload) }),
};

export const examAPI = {
  getAll: (subjectId = null) => apiRequest(`/exams/${subjectId ? `?subject_id=${subjectId}` : ''}`),
  getById: (id) => apiRequest(`/exams/${id}/`),
  create: (formData) => apiRequest('/exams/', { method: 'POST', body: formData }),
  update: (id, payload) => apiRequest(`/exams/${id}/`, { method: 'PUT', body: JSON.stringify(payload) }),
  delete: (id) => apiRequest(`/exams/${id}/`, { method: 'DELETE' }),
};

export const submissionAPI = {
  getByExam: (examId) => apiRequest(`/exams/${examId}/submissions/`),
  create: (examId, formData) => apiRequest(`/exams/${examId}/submissions/`, { method: 'POST', body: formData }),
  getById: (id) => apiRequest(`/submissions/${id}/`),
  grade: (id) => apiRequest(`/submissions/${id}/grade/`, { method: 'POST' }),
  getRecent: () => apiRequest('/submissions/recent/'),
  delete: (id) => apiRequest(`/submissions/${id}/`, { method: 'DELETE' }),
};
