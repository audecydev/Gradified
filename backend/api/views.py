import uuid
import sys
import math
import random
import json
import logging
import re
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from django.utils import timezone
from django.db import close_old_connections
from django.db.models import Avg, Q, Sum

from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, Organization, DemoRequest, Subject, Exam, Submission
from .serializers import (
    OrganizationSerializer,
    UserSerializer,
    DemoRequestSerializer,
    SubjectSerializer,
    ExamSerializer,
    SubmissionListSerializer,
    SubmissionDetailSerializer,
)
from .grading_service import grade_submission_with_ocr_engine

logger = logging.getLogger(__name__)


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


def _check_role(user, allowed_roles):
    if not user.is_authenticated or user.role not in allowed_roles:
        return Response({'error': 'Insufficient role permissions for this action.'}, status=status.HTTP_403_FORBIDDEN)
    return None


def _check_workspace_access(user):
    """Ensure firm organizations and instructors are approved before running workspace mutations."""
    if user.role == 'admin':
        return None
    if not user.organization:
        return Response({'error': 'No organization is linked to your account.'}, status=status.HTTP_403_FORBIDDEN)
    if user.organization.status != 'APPROVED':
        return Response({
            'error': 'Your organization is awaiting Application Admin approval.',
            'organization_status': user.organization.status,
        }, status=status.HTTP_403_FORBIDDEN)
    if user.role == 'instructor' and not user.is_approved:
        return Response({
            'error': 'Your instructor account is pending Firm approval.',
            'is_approved': False,
        }, status=status.HTTP_403_FORBIDDEN)
    return None


def _estimate_pages_count(raw_ocr_input: str, uploaded_bytes: bytes | None) -> int:
    if uploaded_bytes:
        return max(1, math.ceil(len(uploaded_bytes) / 18000))
    if raw_ocr_input:
        lines = len([line for line in raw_ocr_input.splitlines() if line.strip()])
        return max(1, math.ceil(lines / 18))
    return 1


def _compute_submission_cost(organization: Organization | None, pages: int) -> Decimal:
    """Compute booklet OCR grading cost in Indian Rupees (INR)."""
    per_booklet = organization.cost_per_booklet if organization else Decimal('20.00')
    per_page = organization.cost_per_page if organization else Decimal('4.00')
    return (per_booklet + (Decimal(pages) * per_page)).quantize(Decimal('0.0001'))


def _apply_ocr_grading(submission: Submission, uploaded_bytes: bytes | None = None):
    """Evaluate a submission through ocr-service and record usage cost."""
    exam = submission.exam
    fn = submission.answer_sheet_file.name if submission.answer_sheet_file else ""
    result = grade_submission_with_ocr_engine(
        exam_questions_data=exam.questions_data,
        raw_ocr_input=submission.raw_ocr_text,
        submission_ref=submission.submission_ref,
        uploaded_file_bytes=uploaded_bytes,
        filename=fn,
    )
    pages = _estimate_pages_count(submission.raw_ocr_text, uploaded_bytes)
    org = exam.organization or (exam.school.organization if exam.school else None)

    # Re-sync raw_ocr_text if OCR transcribed the text from file
    if not submission.raw_ocr_text and result.get('normalized_evidence', {}).get('questions'):
        recovered_lines = []
        for qe in result['normalized_evidence']['questions']:
            qid = qe.get('question_id', '')
            content = " ".join([b.get('content', '') for b in qe.get('blocks', []) if b.get('content')])
            if content:
                recovered_lines.append(f"{qid}: {content}")
        if recovered_lines:
            submission.raw_ocr_text = "\n".join(recovered_lines)

    submission.status = result.get('status', 'GRADED')
    if result.get('error_message'):
        submission.error_message = result.get('error_message')
    submission.total_score = Decimal(str(result.get('total_score', 0.0)))
    submission.max_possible_score = Decimal(str(result.get('max_possible_score', 0.0)))
    submission.percentage = Decimal(str(result.get('percentage', 0.0)))
    submission.grade_letter = result.get('grade_letter', '')
    submission.normalized_evidence = result.get('normalized_evidence', {})
    submission.grading_details = result
    submission.pages_processed = pages
    submission.grading_cost = _compute_submission_cost(org, pages)
    submission.graded_at = timezone.now()
    submission.save()


# ---------------------------------------------------------------------------
# Background Worker Pool for OCR Grading Tasks
# Isolates OCR processing, retries, and network timeouts from HTTP web workers
# ---------------------------------------------------------------------------
OCR_GRADING_WORKERS = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ocr_grading_worker")


def _async_grade_worker(submission_id: int):
    """Worker task executing OCR grading asynchronously outside the HTTP request loop."""
    close_old_connections()
    try:
        submission = Submission.objects.filter(pk=submission_id).first()
        if not submission:
            logger.warning(f"Background OCR worker: Submission {submission_id} does not exist.")
            return

        uploaded_bytes = None
        if submission.answer_sheet_file:
            try:
                submission.answer_sheet_file.open('rb')
                uploaded_bytes = submission.answer_sheet_file.read()
                submission.answer_sheet_file.close()
            except Exception as e:
                logger.warning(f"Could not read answer sheet file for submission {submission_id}: {e}")

        _apply_ocr_grading(submission, uploaded_bytes)
        logger.info(f"Background OCR worker finished grading submission {submission_id} -> {submission.status}")
    except Exception as exc:
        logger.exception(f"Background OCR worker failed for submission {submission_id}: {exc}")
        try:
            sub = Submission.objects.filter(pk=submission_id).first()
            if sub:
                sub.status = 'FAILED'
                sub.error_message = f"OCR Service Error: {str(exc)}"
                sub.save()
        except Exception:
            pass
    finally:
        close_old_connections()


def dispatch_grading_task(submission: Submission, uploaded_bytes: bytes | None = None, sync: bool = False):
    """
    Dispatches grading to the background worker pool to prevent web server threads from blocking.
    Runs synchronously during unit testing or when sync=True is requested.
    """
    is_test = 'test' in sys.argv
    if sync or is_test:
        _apply_ocr_grading(submission, uploaded_bytes)
    else:
        submission.status = 'PROCESSING'
        submission.error_message = ''
        submission.save(update_fields=['status', 'error_message'])
        OCR_GRADING_WORKERS.submit(_async_grade_worker, submission.id)


def _scoped_exams_for_user(user):
    if user.role == 'admin':
        return Exam.objects.all()
    if user.organization:
        return Exam.objects.filter(organization=user.organization)
    return Exam.objects.filter(school=user)


# ==========================================
# CONTACT SALES / PUBLIC DEMO REQUEST
# ==========================================

class ContactSalesView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        org_name = request.data.get('organization_name', '').strip()
        contact_name = request.data.get('contact_name', '').strip()
        email = request.data.get('email', '').strip().lower()
        phone = request.data.get('phone', '').strip()
        notes = request.data.get('notes', '').strip()
        expected_booklets = request.data.get('expected_booklets', 500)

        if not org_name or not contact_name or not email:
            return Response(
                {'error': 'Organization name, contact name, and work email are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            expected_booklets = max(1, int(expected_booklets))
        except (TypeError, ValueError):
            expected_booklets = 500

        demo_req = DemoRequest.objects.create(
            organization_name=org_name,
            contact_name=contact_name,
            email=email,
            phone=phone,
            expected_booklets=expected_booklets,
            notes=notes,
            status='PENDING',
        )

        return Response({
            'message': 'Demo & onboarding request submitted! An Application Admin will review your organization shortly.',
            'request': DemoRequestSerializer(demo_req).data,
        }, status=status.HTTP_201_CREATED)


# ==========================================
# AUTHENTICATION & EMAIL VERIFICATION VIEWS
# ==========================================

class SignupView(APIView):
    """
    Public registration defaults to Firm / Organization signup pending Application Admin approval.
    Instructors join via their firm's organization code (is_approved=False until approved by Role 2 Firm).
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')
        confirm_password = request.data.get('confirm_password')
        username = request.data.get('username', '').strip() or email.split('@')[0]
        school_name = request.data.get('school_name', '').strip()
        org_code = request.data.get('org_code', '').strip().upper()
        phone = request.data.get('phone', '').strip()

        if not email or not password:
            return Response({'error': 'Email and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        if len(password) < 6:
            return Response({'error': 'Password must be at least 6 characters.'}, status=status.HTTP_400_BAD_REQUEST)

        if confirm_password is not None and password != confirm_password:
            return Response({'error': 'Passwords do not match.'}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=email).exists():
            return Response({'error': 'A user with this email already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        # Determine firm vs instructor based on whether joining an existing org code
        if org_code:
            try:
                org = Organization.objects.get(code=org_code)
            except Organization.DoesNotExist:
                return Response({'error': f"Organization code '{org_code}' not found."}, status=status.HTTP_404_NOT_FOUND)
            role = 'instructor'
            is_approved = False
            resolved_org_name = org.name
        else:
            if not school_name:
                return Response({'error': 'Firm / School name is required.'}, status=status.HTTP_400_BAD_REQUEST)
            role = 'firm'
            is_approved = True
            org = Organization.objects.create(
                name=school_name,
                contact_email=email,
                contact_person=username,
                phone=phone,
                status='PENDING',
            )
            resolved_org_name = org.name

        verification_code = f"{random.randint(100000, 999999)}"
        verification_token = str(uuid.uuid4())

        user = User.objects.create_user(
            email=email,
            password=password,
            username=username,
            role=role,
            organization=org,
            school_name=resolved_org_name,
            phone=phone,
            is_verified=False,
            is_approved=is_approved,
            verification_token=verification_token,
            verification_code=verification_code,
        )

        logger.info(f"User registered ({role}): {email}, Code: {verification_code}")

        return Response({
            'message': 'Registration successful! Please verify your email address to continue.',
            'email': user.email,
            'role': user.role,
            'organization_code': org.code,
            'organization_status': org.status,
            'verification_code': verification_code,
            'verification_token': verification_token,
        }, status=status.HTTP_201_CREATED)


class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        code = request.data.get('code', '').strip()
        token = request.data.get('token', '').strip()

        if not email:
            return Response({'error': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'User with this email does not exist.'}, status=status.HTTP_404_NOT_FOUND)

        if user.is_verified:
            return Response({
                'message': 'Email is already verified.',
                'tokens': get_tokens_for_user(user),
                'user': UserSerializer(user).data,
            }, status=status.HTTP_200_OK)

        is_valid = (code and user.verification_code == code) or (token and user.verification_token == token)
        if not is_valid:
            return Response({'error': 'Invalid verification code or token.'}, status=status.HTTP_400_BAD_REQUEST)

        user.is_verified = True
        user.verification_code = ''
        user.verification_token = ''
        user.save()

        return Response({
            'message': 'Email successfully verified!',
            'tokens': get_tokens_for_user(user),
            'user': UserSerializer(user).data,
        }, status=status.HTTP_200_OK)


class ResendVerificationView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        if not email:
            return Response({'error': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)

        if user.is_verified:
            return Response({'message': 'This email is already verified.'}, status=status.HTTP_200_OK)

        user.verification_code = f"{random.randint(100000, 999999)}"
        user.verification_token = str(uuid.uuid4())
        user.save()

        return Response({
            'message': 'Verification code sent.',
            'email': user.email,
            'verification_code': user.verification_code,
            'verification_token': user.verification_token,
        }, status=status.HTTP_200_OK)


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')

        if not email or not password:
            return Response({'error': 'Email and password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({'error': 'Invalid email or password.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.check_password(password):
            return Response({'error': 'Invalid email or password.'}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.is_verified:
            return Response({
                'error': 'Email address not verified.',
                'requires_verification': True,
                'email': user.email,
                'verification_code': user.verification_code,
                'verification_token': user.verification_token,
            }, status=status.HTTP_403_FORBIDDEN)

        return Response({
            'message': 'Login successful.',
            'tokens': get_tokens_for_user(user),
            'user': UserSerializer(user).data,
        }, status=status.HTTP_200_OK)


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


# ==========================================
# ROLE 1: APPLICATION ADMIN (ONBOARD & APPROVE ORGS)
# ==========================================

class AdminOrganizationsListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        err = _check_role(request.user, ['admin'])
        if err:
            return err
        orgs = Organization.objects.all().order_by('-created_at')
        return Response(OrganizationSerializer(orgs, many=True).data)


class AdminOnboardSchoolView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        err = _check_role(request.user, ['admin'])
        if err:
            return err

        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')
        school_name = request.data.get('school_name', '').strip()
        contact_person = request.data.get('contact_person', '').strip()
        phone = request.data.get('phone', '').strip()
        plan_tier = request.data.get('plan_tier', 'PRO')
        auto_approve = request.data.get('auto_verify', True)
        demo_request_id = request.data.get('demo_request_id')

        if not email or not password or not school_name:
            return Response({'error': 'Email, password, and organization name are required.'}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=email).exists():
            return Response({'error': 'A user with this email already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        org = Organization.objects.create(
            name=school_name,
            contact_email=email,
            contact_person=contact_person or school_name,
            phone=phone,
            plan_tier=plan_tier if plan_tier in ['STARTER', 'PRO', 'ENTERPRISE'] else 'PRO',
            status='APPROVED' if auto_approve else 'PENDING',
        )

        verification_code = '' if auto_approve else f"{random.randint(100000, 999999)}"
        user = User.objects.create_user(
            email=email,
            password=password,
            username=contact_person or school_name,
            role='firm',
            organization=org,
            school_name=org.name,
            phone=phone,
            is_verified=bool(auto_approve),
            is_approved=True,
            verification_code=verification_code,
        )

        if demo_request_id:
            DemoRequest.objects.filter(pk=demo_request_id).update(status='ONBOARDED', organization=org)

        return Response({
            'message': f"Organization '{org.name}' onboarded (Code: {org.code})!",
            'organization': OrganizationSerializer(org).data,
            'school': UserSerializer(user).data,
        }, status=status.HTTP_201_CREATED)


class AdminToggleOrgStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        err = _check_role(request.user, ['admin'])
        if err:
            return err

        try:
            org = Organization.objects.get(pk=pk)
        except Organization.DoesNotExist:
            return Response({'error': 'Organization not found.'}, status=status.HTTP_404_NOT_FOUND)

        if 'status' in request.data and request.data['status'] in ['PENDING', 'APPROVED', 'SUSPENDED']:
            org.status = request.data['status']
        if 'plan_tier' in request.data and request.data['plan_tier'] in ['STARTER', 'PRO', 'ENTERPRISE']:
            org.plan_tier = request.data['plan_tier']
        if 'monthly_budget_limit' in request.data:
            org.monthly_budget_limit = Decimal(str(request.data['monthly_budget_limit']))
        if 'is_verified' in request.data:
            org.status = 'APPROVED' if bool(request.data['is_verified']) else 'PENDING'

        org.save()
        return Response(OrganizationSerializer(org).data)


class AdminDemoRequestsListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        err = _check_role(request.user, ['admin'])
        if err:
            return err
        requests_qs = DemoRequest.objects.all().order_by('-created_at')
        return Response(DemoRequestSerializer(requests_qs, many=True).data)


class AdminDemoRequestActionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        err = _check_role(request.user, ['admin'])
        if err:
            return err
        try:
            demo_req = DemoRequest.objects.get(pk=pk)
        except DemoRequest.DoesNotExist:
            return Response({'error': 'Demo request not found.'}, status=status.HTTP_404_NOT_FOUND)

        if 'status' in request.data and request.data['status'] in ['PENDING', 'ONBOARDED', 'DISMISSED']:
            demo_req.status = request.data['status']
            demo_req.save()
        return Response(DemoRequestSerializer(demo_req).data)


class AdminStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        err = _check_role(request.user, ['admin'])
        if err:
            return err

        total_orgs = Organization.objects.count()
        approved_orgs = Organization.objects.filter(status='APPROVED').count()
        pending_orgs = Organization.objects.filter(status='PENDING').count()
        pending_demo_requests = DemoRequest.objects.filter(status='PENDING').count()
        total_instructors = User.objects.filter(role='instructor').count()
        total_subjects = Subject.objects.count()
        total_exams = Exam.objects.count()
        total_submissions = Submission.objects.count()
        graded_submissions = Submission.objects.filter(status='GRADED').count()
        avg_score = Submission.objects.filter(status='GRADED', total_score__isnull=False).aggregate(Avg('percentage'))['percentage__avg']
        total_cost = Submission.objects.aggregate(Sum('grading_cost'))['grading_cost__sum'] or Decimal('0.00')

        return Response({
            'total_schools': total_orgs,
            'verified_schools': approved_orgs,
            'total_orgs': total_orgs,
            'approved_orgs': approved_orgs,
            'pending_orgs': pending_orgs,
            'pending_demo_requests': pending_demo_requests,
            'total_instructors': total_instructors,
            'total_subjects': total_subjects,
            'total_exams': total_exams,
            'total_submissions': total_submissions,
            'graded_submissions': graded_submissions,
            'total_platform_cost': round(float(total_cost), 2),
            'average_percentage': round(avg_score, 1) if avg_score else 0.0,
        })


# ==========================================
# ROLE 2: FIRM / ORG MANAGER (RESULTS, INSTRUCTOR APPROVAL, COSTS)
# ==========================================

class FirmOverviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        err = _check_role(request.user, ['firm', 'admin'])
        if err:
            return err
        access_err = _check_workspace_access(request.user)
        if access_err:
            return access_err

        org = request.user.organization
        if not org:
            return Response({'error': 'No firm linked to account.'}, status=status.HTTP_400_BAD_REQUEST)

        exams = Exam.objects.filter(organization=org)
        submissions = Submission.objects.filter(exam__organization=org)
        graded = submissions.filter(status='GRADED')
        instructors = User.objects.filter(organization=org, role='instructor')

        booklets_processed = submissions.count()
        pages_processed = sum(s.pages_processed for s in submissions)
        total_cost = round(sum(float(s.grading_cost or 0) for s in submissions), 2)
        budget_limit = float(org.monthly_budget_limit or 40000)
        budget_used_pct = round(min(100.0, (total_cost / budget_limit) * 100.0), 1) if budget_limit > 0 else 0.0
        avg_pct = graded.aggregate(Avg('percentage'))['percentage__avg']
        passed_count = sum(1 for s in graded if float(s.percentage or 0) >= 40.0)
        pass_rate = round((passed_count / graded.count()) * 100.0, 1) if graded.exists() else 0.0

        # Per-instructor usage & cost breakdown
        instructor_usage = []
        for inst in instructors:
            inst_subs = submissions.filter(Q(submitted_by=inst) | Q(exam__school=inst))
            instructor_usage.append({
                'id': inst.id,
                'name': inst.username or inst.email,
                'email': inst.email,
                'is_approved': inst.is_approved,
                'exams_created': exams.filter(school=inst).count(),
                'booklets_graded': inst_subs.count(),
                'pages_processed': sum(s.pages_processed for s in inst_subs),
                'total_cost': round(sum(float(s.grading_cost or 0) for s in inst_subs), 2),
            })

        # Per-exam usage & results summary
        exam_usage = []
        for ex in exams:
            ex_subs = submissions.filter(exam=ex)
            ex_graded = ex_subs.filter(status='GRADED')
            ex_avg = ex_graded.aggregate(Avg('percentage'))['percentage__avg']
            exam_usage.append({
                'id': ex.id,
                'title': ex.title,
                'subject_name': ex.subject.name,
                'booklets_count': ex_subs.count(),
                'pages_processed': sum(s.pages_processed for s in ex_subs),
                'cost': round(sum(float(s.grading_cost or 0) for s in ex_subs), 2),
                'average_percentage': round(ex_avg, 1) if ex_avg is not None else None,
            })

        return Response({
            'organization': OrganizationSerializer(org).data,
            'metrics': {
                'total_exams': exams.count(),
                'total_instructors': instructors.count(),
                'pending_instructors': instructors.filter(is_approved=False).count(),
                'booklets_processed': booklets_processed,
                'graded_booklets': graded.count(),
                'pages_processed': pages_processed,
                'average_percentage': round(avg_pct, 1) if avg_pct else 0.0,
                'pass_rate': pass_rate,
                'total_cost': total_cost,
                'monthly_budget_limit': budget_limit,
                'budget_used_pct': budget_used_pct,
                'cost_per_booklet': float(org.cost_per_booklet),
                'cost_per_page': float(org.cost_per_page),
                'currency': 'INR',
            },
            'instructor_usage': instructor_usage,
            'exam_usage': exam_usage,
            'recent_submissions': SubmissionListSerializer(submissions[:12], many=True).data,
        })


class FirmInstructorsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        err = _check_role(request.user, ['firm', 'admin'])
        if err:
            return err
        access_err = _check_workspace_access(request.user)
        if access_err:
            return access_err

        instructors = User.objects.filter(organization=request.user.organization, role='instructor').order_by('-created_at')
        data = []
        for inst in instructors:
            exams_count = Exam.objects.filter(organization=request.user.organization, school=inst).count()
            subs = Submission.objects.filter(Q(submitted_by=inst) | Q(exam__school=inst), exam__organization=request.user.organization)
            data.append({
                'id': inst.id,
                'email': inst.email,
                'username': inst.username,
                'phone': inst.phone,
                'is_verified': inst.is_verified,
                'is_approved': inst.is_approved,
                'exams_count': exams_count,
                'submissions_count': subs.count(),
                'total_cost': round(sum(float(s.grading_cost or 0) for s in subs), 2),
                'created_at': inst.created_at,
            })
        return Response(data)

    def post(self, request):
        """Firm creates/invites an instructor directly under its organization."""
        err = _check_role(request.user, ['firm', 'admin'])
        if err:
            return err
        access_err = _check_workspace_access(request.user)
        if access_err:
            return access_err

        email = request.data.get('email', '').strip().lower()
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '').strip() or 'instructor123'
        phone = request.data.get('phone', '').strip()
        approve_now = request.data.get('is_approved', True)

        if not email or not username:
            return Response({'error': 'Instructor name and email are required.'}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=email).exists():
            return Response({'error': 'A user with this email already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        org = request.user.organization
        instructor = User.objects.create_user(
            email=email,
            password=password,
            username=username,
            role='instructor',
            organization=org,
            school_name=org.name if org else '',
            phone=phone,
            is_verified=True,
            is_approved=bool(approve_now),
        )
        return Response({
            'message': f"Instructor '{username}' added to {org.name}.",
            'instructor': UserSerializer(instructor).data,
        }, status=status.HTTP_201_CREATED)


class FirmApproveInstructorView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        err = _check_role(request.user, ['firm', 'admin'])
        if err:
            return err
        access_err = _check_workspace_access(request.user)
        if access_err:
            return access_err

        try:
            instructor = User.objects.get(pk=pk, organization=request.user.organization, role='instructor')
        except User.DoesNotExist:
            return Response({'error': 'Instructor not found in your organization.'}, status=status.HTTP_404_NOT_FOUND)

        if 'is_approved' in request.data:
            instructor.is_approved = bool(request.data['is_approved'])
        else:
            instructor.is_approved = not instructor.is_approved
        instructor.save()
        return Response(UserSerializer(instructor).data)


# ==========================================
# SUBJECT VIEWS (INSTRUCTOR / FIRM / ADMIN)
# ==========================================

class SubjectListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        access_err = _check_workspace_access(request.user)
        if access_err:
            return access_err
        user = request.user
        if user.role == 'admin':
            subjects = Subject.objects.all()
        else:
            subjects = Subject.objects.filter(Q(organization__isnull=True) | Q(organization=user.organization))
        return Response(SubjectSerializer(subjects.order_by('name'), many=True).data)

    def post(self, request):
        access_err = _check_workspace_access(request.user)
        if access_err:
            return access_err
        name = request.data.get('name', '').strip()
        code = request.data.get('code', '').strip()
        description = request.data.get('description', '').strip()

        if not name:
            return Response({'error': 'Subject name is required.'}, status=status.HTTP_400_BAD_REQUEST)

        subject = Subject.objects.create(
            name=name,
            code=code,
            description=description,
            organization=request.user.organization,
            school=request.user,
        )
        return Response(SubjectSerializer(subject).data, status=status.HTTP_201_CREATED)


# ==========================================
# EXAM VIEWS (ROLE 3 INSTRUCTOR + FIRM/ADMIN VISIBILITY)
# ==========================================

class ExamListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        access_err = _check_workspace_access(request.user)
        if access_err:
            return access_err
        queryset = _scoped_exams_for_user(request.user)
        subject_id = request.query_params.get('subject_id')
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)
        return Response(ExamSerializer(queryset, many=True).data)

    def post(self, request):
        access_err = _check_workspace_access(request.user)
        if access_err:
            return access_err
        user = request.user
        title = request.data.get('title', '').strip()
        subject_id = request.data.get('subject_id')
        total_marks_raw = request.data.get('total_marks')
        passing_marks_raw = request.data.get('passing_marks')

        question_paper_file = request.FILES.get('question_paper_file')
        question_paper_text = request.data.get('question_paper_text', '').strip()
        answer_paper_file = request.FILES.get('answer_paper_file')
        answer_paper_text = request.data.get('answer_paper_text', '').strip()

        questions_data_raw = request.data.get('questions_data')
        questions_data = []
        if questions_data_raw:
            if isinstance(questions_data_raw, str):
                try:
                    questions_data = json.loads(questions_data_raw)
                except Exception:
                    questions_data = []
            elif isinstance(questions_data_raw, list):
                questions_data = questions_data_raw

        if not title:
            return Response({'error': 'Exam title is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            subject = Subject.objects.get(pk=subject_id)
        except Subject.DoesNotExist:
            return Response({'error': 'Valid subject is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Dynamic marks and questions specification derivation
        hint_total = 100.0
        if total_marks_raw:
            try:
                hint_total = float(total_marks_raw)
            except (ValueError, TypeError):
                hint_total = 100.0

        if not questions_data and question_paper_text:
            questions_data = self._auto_generate_questions_spec(
                question_paper_text,
                answer_paper_text,
                total_marks_hint=hint_total
            )

        if questions_data:
            computed_total = sum(float(q.get('max_marks') or 0) for q in questions_data)
            total_marks = computed_total if computed_total > 0 else hint_total
        else:
            total_marks = hint_total

        if passing_marks_raw:
            try:
                passing_marks = float(passing_marks_raw)
            except (ValueError, TypeError):
                passing_marks = round(total_marks * 0.4, 2)
        else:
            passing_marks = round(total_marks * 0.4, 2)

        exam = Exam.objects.create(
            title=title,
            subject=subject,
            organization=user.organization,
            school=user,
            total_marks=total_marks,
            passing_marks=passing_marks,
            question_paper_file=question_paper_file,
            question_paper_text=question_paper_text,
            answer_paper_file=answer_paper_file,
            answer_paper_text=answer_paper_text,
            questions_data=questions_data,
        )
        return Response(ExamSerializer(exam).data, status=status.HTTP_201_CREATED)

    def _auto_generate_questions_spec(self, q_text: str, a_text: str, total_marks_hint: float = 100.0) -> list:
        if not q_text or not q_text.strip():
            return []

        pattern = r'(?m)(?:^|\n)(?=(?:Question\s*\d+|Q\d+|\d+[\.\)])\s*)'
        raw_chunks = [c.strip() for c in re.split(pattern, q_text.strip()) if c.strip()]

        if not raw_chunks:
            raw_chunks = [q_text.strip()]

        num_questions = len(raw_chunks)
        default_mark_per_q = round(total_marks_hint / max(1, num_questions), 2)

        answers_map = {}
        if a_text and a_text.strip():
            a_pattern = r'(?m)(?:^|\n)(?=(?:Answer\s*\d+|Ans\s*\d+|Q\d+\s*Answer|Q\d+|\d+[\.\)])\s*)'
            a_chunks = [ac.strip() for ac in re.split(a_pattern, a_text.strip()) if ac.strip()]
            for ac in a_chunks:
                m_aid = re.match(r'^(?:Answer\s*(\d+)|Ans\s*(\d+)|Q(\d+)\s*Answer|Q(\d+)|(\d+)[\.\)])\s*[:\-\.]?\s*(.*)', ac, re.DOTALL | re.IGNORECASE)
                if m_aid:
                    q_num = next(g for g in m_aid.groups()[:-1] if g is not None)
                    answers_map[f"Q{q_num}"] = m_aid.groups()[-1].strip()

        questions_spec = []
        for idx, chunk in enumerate(raw_chunks, start=1):
            q_id = f"Q{idx}"
            mark_match = re.search(r'[\(\[]\s*(\d+(?:\.\d+)?)\s*(?:marks?|pts?|points?)?\s*[\)\]]', chunk, re.IGNORECASE)
            if mark_match:
                try:
                    q_mark = float(mark_match.group(1))
                except (ValueError, TypeError):
                    q_mark = default_mark_per_q
            else:
                q_mark = default_mark_per_q

            cleaned_text = re.sub(r'^(?:Question\s*\d+|Q\d+|\d+[\.\)])\s*[:\-\.]?\s*', '', chunk, flags=re.IGNORECASE).strip()
            if not cleaned_text:
                cleaned_text = chunk

            ans_text = answers_map.get(q_id, "")

            choice_match = re.findall(r'(?m)^([A-Da-d])[\:\.\)]\s*(.+)$', cleaned_text)
            if choice_match and len(choice_match) >= 2:
                correct_opt = "A"
                if ans_text:
                    m_opt = re.search(r'\b([A-Da-d])\b', ans_text)
                    if m_opt:
                        correct_opt = m_opt.group(1).upper()
                questions_spec.append({
                    "question_id": q_id,
                    "question_text": cleaned_text,
                    "type": "CHOICE",
                    "max_marks": q_mark,
                    "choice_spec": {
                        "correct_option": correct_opt,
                        "options": [f"{letter.upper()}: {opt_txt.strip()}" for letter, opt_txt in choice_match]
                    }
                })
            else:
                num_match = re.search(r'[-+]?\d*\.\d+|\d+', ans_text) if ans_text else None
                is_numeric_stem = any(kw in cleaned_text.lower() for kw in ["calculate", "solve for", "evaluate the numerical", "what is the value of"])
                if is_numeric_stem and num_match:
                    exp_val = float(num_match.group(0))
                    questions_spec.append({
                        "question_id": q_id,
                        "question_text": cleaned_text,
                        "type": "NUMERIC",
                        "max_marks": q_mark,
                        "numeric_spec": {
                            "expected_value": exp_val,
                            "tolerance": round(abs(exp_val) * 0.05, 2) if exp_val != 0 else 0.5
                        }
                    })
                else:
                    model_answer = ans_text if ans_text else cleaned_text
                    questions_spec.append({
                        "question_id": q_id,
                        "question_text": cleaned_text,
                        "type": "DIRECT",
                        "max_marks": q_mark,
                        "model_answer": model_answer,
                        "rubric": {
                            "criteria": [
                                {
                                    "criterion_id": f"{q_id.lower()}_core_accuracy",
                                    "description": f"Accuracy of core explanation and key conceptual requirements for {q_id}",
                                    "levels": [
                                        {"level_id": "EXCELLENT", "points": float(q_mark), "description": "Completely accurate, thorough explanation matching expected rubric"},
                                        {"level_id": "GOOD", "points": round(float(q_mark) * 0.75, 2), "description": "Accurate explanation with minor conceptual omissions"},
                                        {"level_id": "PARTIAL", "points": round(float(q_mark) * 0.40, 2), "description": "Basic understanding demonstrated; key terminology missing"},
                                        {"level_id": "INSUFFICIENT", "points": 0.0, "description": "Inaccurate or off-topic response"}
                                    ]
                                }
                            ]
                        }
                    })

        return questions_spec


class ExamDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, user):
        return _scoped_exams_for_user(user).filter(pk=pk).first()

    def get(self, request, pk):
        access_err = _check_workspace_access(request.user)
        if access_err:
            return access_err
        exam = self.get_object(pk, request.user)
        if not exam:
            return Response({'error': 'Exam not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(ExamSerializer(exam).data)

    def put(self, request, pk):
        access_err = _check_workspace_access(request.user)
        if access_err:
            return access_err
        exam = self.get_object(pk, request.user)
        if not exam:
            return Response({'error': 'Exam not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ExamSerializer(exam, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        access_err = _check_workspace_access(request.user)
        if access_err:
            return access_err
        exam = self.get_object(pk, request.user)
        if not exam:
            return Response({'error': 'Exam not found.'}, status=status.HTTP_404_NOT_FOUND)
        exam.delete()
        return Response({'message': 'Exam deleted successfully.'}, status=status.HTTP_204_NO_CONTENT)


# ==========================================
# ANSWER BOOKLET SUBMISSION & OCR GRADING VIEWS
# ==========================================

class SubmissionListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, exam_id):
        access_err = _check_workspace_access(request.user)
        if access_err:
            return access_err
        exam = _scoped_exams_for_user(request.user).filter(pk=exam_id).first()
        if not exam:
            return Response({'error': 'Exam not found.'}, status=status.HTTP_404_NOT_FOUND)
        submissions = exam.submissions.all().order_by('-created_at')
        return Response(SubmissionListSerializer(submissions, many=True).data)

    def post(self, request, exam_id):
        access_err = _check_workspace_access(request.user)
        if access_err:
            return access_err
        exam = _scoped_exams_for_user(request.user).filter(pk=exam_id).first()
        if not exam:
            return Response({'error': 'Exam not found.'}, status=status.HTTP_404_NOT_FOUND)

        student_name = request.data.get('student_name', '').strip()
        student_id = request.data.get('student_id', '').strip()
        answer_sheet_file = request.FILES.get('answer_sheet_file')
        raw_ocr_text = request.data.get('raw_ocr_text', '').strip()
        auto_grade = request.data.get('auto_grade', True)

        if not student_name or not student_id:
            return Response({'error': 'Student Name and Student Roll/ID are required.'}, status=status.HTTP_400_BAD_REQUEST)

        submission_ref = f"sub-{uuid.uuid4().hex[:12]}"
        uploaded_bytes = answer_sheet_file.read() if answer_sheet_file else None

        submission = Submission.objects.create(
            exam=exam,
            submitted_by=request.user,
            student_name=student_name,
            student_id=student_id,
            submission_ref=submission_ref,
            answer_sheet_file=answer_sheet_file,
            raw_ocr_text=raw_ocr_text,
            status='PENDING',
        )

        if auto_grade:
            sync_requested = request.query_params.get('sync', '').lower() in ('true', '1')
            dispatch_grading_task(submission, uploaded_bytes, sync=sync_requested)
            submission.refresh_from_db()

        return Response(SubmissionDetailSerializer(submission).data, status=status.HTTP_201_CREATED)


class SubmissionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, pk, user):
        exams = _scoped_exams_for_user(user)
        return Submission.objects.filter(pk=pk, exam__in=exams).first()

    def get(self, request, pk):
        access_err = _check_workspace_access(request.user)
        if access_err:
            return access_err
        submission = self.get_object(pk, request.user)
        if not submission:
            return Response({'error': 'Submission not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(SubmissionDetailSerializer(submission).data)

    def delete(self, request, pk):
        access_err = _check_workspace_access(request.user)
        if access_err:
            return access_err
        submission = self.get_object(pk, request.user)
        if not submission:
            return Response({'error': 'Submission not found.'}, status=status.HTTP_404_NOT_FOUND)
        submission.delete()
        return Response({'message': 'Submission deleted.'}, status=status.HTTP_204_NO_CONTENT)


class SubmissionGradeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        access_err = _check_workspace_access(request.user)
        if access_err:
            return access_err
        exams = _scoped_exams_for_user(request.user)
        submission = Submission.objects.filter(pk=pk, exam__in=exams).first()
        if not submission:
            return Response({'error': 'Submission not found.'}, status=status.HTTP_404_NOT_FOUND)

        uploaded_bytes = None
        if submission.answer_sheet_file:
            try:
                submission.answer_sheet_file.open('rb')
                uploaded_bytes = submission.answer_sheet_file.read()
                submission.answer_sheet_file.close()
            except Exception:
                pass

        sync_requested = request.query_params.get('sync', '').lower() in ('true', '1')
        dispatch_grading_task(submission, uploaded_bytes, sync=sync_requested)
        submission.refresh_from_db()
        return Response(SubmissionDetailSerializer(submission).data, status=status.HTTP_200_OK)


class RecentSubmissionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        access_err = _check_workspace_access(request.user)
        if access_err:
            return access_err
        exams = _scoped_exams_for_user(request.user)
        recent = Submission.objects.filter(exam__in=exams).order_by('-created_at')[:15]
        return Response(SubmissionListSerializer(recent, many=True).data)
