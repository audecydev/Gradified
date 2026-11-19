from django.urls import path
from .views import (
    ContactSalesView,
    SignupView,
    VerifyEmailView,
    ResendVerificationView,
    LoginView,
    MeView,
    AdminOrganizationsListView,
    AdminOnboardSchoolView,
    AdminToggleOrgStatusView,
    AdminDemoRequestsListView,
    AdminDemoRequestActionView,
    AdminStatsView,
    FirmOverviewView,
    FirmInstructorsView,
    FirmApproveInstructorView,
    SubjectListCreateView,
    ExamListCreateView,
    ExamDetailView,
    SubmissionListCreateView,
    SubmissionDetailView,
    SubmissionGradeView,
    RecentSubmissionsView,
)

urlpatterns = [
    # Public Sales & Demo Requests
    path('contact-sales/', ContactSalesView.as_view(), name='contact-sales'),

    # Auth
    path('auth/signup/', SignupView.as_view(), name='signup'),
    path('auth/verify-email/', VerifyEmailView.as_view(), name='verify-email'),
    path('auth/resend-verification/', ResendVerificationView.as_view(), name='resend-verification'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/me/', MeView.as_view(), name='me'),

    # Role 1: Application Admin (Onboarding & Org Approvals)
    path('admin/organizations/', AdminOrganizationsListView.as_view(), name='admin-organizations'),
    path('admin/schools/', AdminOrganizationsListView.as_view(), name='admin-schools'),
    path('admin/onboard-school/', AdminOnboardSchoolView.as_view(), name='admin-onboard-school'),
    path('admin/organizations/<int:pk>/status/', AdminToggleOrgStatusView.as_view(), name='admin-org-status'),
    path('admin/schools/<int:pk>/toggle-status/', AdminToggleOrgStatusView.as_view(), name='admin-toggle-status'),
    path('admin/demo-requests/', AdminDemoRequestsListView.as_view(), name='admin-demo-requests'),
    path('admin/demo-requests/<int:pk>/', AdminDemoRequestActionView.as_view(), name='admin-demo-request-action'),
    path('admin/stats/', AdminStatsView.as_view(), name='admin-stats'),

    # Role 2: Firm / Org Manager (Overall Results, Instructor Approvals, Costs & Usage)
    path('firm/overview/', FirmOverviewView.as_view(), name='firm-overview'),
    path('firm/instructors/', FirmInstructorsView.as_view(), name='firm-instructors'),
    path('firm/instructors/<int:pk>/approve/', FirmApproveInstructorView.as_view(), name='firm-approve-instructor'),

    # Subjects
    path('subjects/', SubjectListCreateView.as_view(), name='subjects-list-create'),

    # Role 3: Instructor Exams (Question Paper & Answer Paper / Rubric)
    path('exams/', ExamListCreateView.as_view(), name='exams-list-create'),
    path('exams/<int:pk>/', ExamDetailView.as_view(), name='exam-detail'),

    # Answer Booklets & OCR Grading
    path('exams/<int:exam_id>/submissions/', SubmissionListCreateView.as_view(), name='exam-submissions'),
    path('submissions/<int:pk>/', SubmissionDetailView.as_view(), name='submission-detail'),
    path('submissions/<int:pk>/grade/', SubmissionGradeView.as_view(), name='submission-grade'),
    path('submissions/recent/', RecentSubmissionsView.as_view(), name='recent-submissions'),
]
