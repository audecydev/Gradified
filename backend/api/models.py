import uuid
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email address is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'admin')
        extra_fields.setdefault('is_verified', True)
        extra_fields.setdefault('is_approved', True)
        return self.create_user(email, password, **extra_fields)


class Organization(models.Model):
    """School, firm, or educational institution managed by Role 1 (Admin) & Role 2 (Firm)."""
    STATUS_CHOICES = (
        ('PENDING', 'Pending Admin Approval'),
        ('APPROVED', 'Approved'),
        ('SUSPENDED', 'Suspended'),
    )
    PLAN_CHOICES = (
        ('STARTER', 'Starter'),
        ('PRO', 'Professional'),
        ('ENTERPRISE', 'Enterprise'),
    )

    name = models.CharField(max_length=255)
    code = models.CharField(max_length=32, unique=True, blank=True)
    contact_email = models.EmailField(blank=True, default='')
    contact_person = models.CharField(max_length=150, blank=True, default='')
    phone = models.CharField(max_length=50, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    plan_tier = models.CharField(max_length=20, choices=PLAN_CHOICES, default='PRO')

    # Real OCR & Grading Cost Ledger Parameters (INR)
    cost_per_booklet = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('20.00'))
    cost_per_page = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('4.00'))
    monthly_budget_limit = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('40000.00'))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = f"ORG-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.status})"


class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Application Admin'),
        ('firm', 'Firm / Organization Lead'),
        ('instructor', 'Instructor'),
    )

    username = models.CharField(max_length=150, unique=False, blank=True, null=True)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='firm')
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='members',
    )
    school_name = models.CharField(max_length=255, blank=True, default='')
    phone = models.CharField(max_length=50, blank=True, default='')

    # Approval & Verification Gates
    is_verified = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=True)
    verification_token = models.CharField(max_length=100, blank=True, default='')
    verification_code = models.CharField(max_length=10, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"


class DemoRequest(models.Model):
    """Inbound Contact Sales / Demo requests reviewed by Application Admin."""
    STATUS_CHOICES = (
        ('PENDING', 'Pending Review'),
        ('ONBOARDED', 'Onboarded'),
        ('DISMISSED', 'Dismissed'),
    )

    organization_name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True, default='')
    expected_booklets = models.PositiveIntegerField(default=500)
    notes = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='demo_requests',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.organization_name} - {self.email} ({self.status})"


class Subject(models.Model):
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=30, blank=True, default='')
    description = models.TextField(blank=True, default='')
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='subjects',
        null=True,
        blank=True,
    )
    school = models.ForeignKey(User, on_delete=models.CASCADE, related_name='subjects', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})" if self.code else self.name


class Exam(models.Model):
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('ACTIVE', 'Active / Ready for Submissions'),
        ('ARCHIVED', 'Archived'),
    )

    title = models.CharField(max_length=200)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='exams')
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='exams',
        null=True,
        blank=True,
    )
    school = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exams')
    total_marks = models.DecimalField(max_digits=6, decimal_places=2, default=100.0)
    passing_marks = models.DecimalField(max_digits=6, decimal_places=2, default=40.0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')

    # Uploaded question paper & answer paper
    question_paper_file = models.FileField(upload_to='question_papers/', null=True, blank=True)
    question_paper_text = models.TextField(blank=True, default='')

    answer_paper_file = models.FileField(upload_to='answer_papers/', null=True, blank=True)
    answer_paper_text = models.TextField(blank=True, default='')

    # Structured Rubric & Question Spec
    questions_data = models.JSONField(
        default=list,
        blank=True,
        help_text="Structured question items, types (DIRECT, NUMERIC, CHOICE), max marks, rubrics, and criteria"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.subject.name}"


class Submission(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending OCR / Grading'),
        ('PROCESSING', 'Processing in OCR Engine'),
        ('GRADED', 'Graded Successfully'),
        ('REVIEW_REQUIRED', 'Review Required'),
        ('FAILED', 'Evaluation Failed'),
    )

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='submissions')
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='submissions',
    )
    student_name = models.CharField(max_length=150)
    student_id = models.CharField(max_length=100)
    submission_ref = models.CharField(max_length=100, unique=True, default=uuid.uuid4)

    # Uploaded student answer booklet
    answer_sheet_file = models.FileField(upload_to='answer_sheets/', null=True, blank=True)
    raw_ocr_text = models.TextField(blank=True, default='')

    # Normalized Evidence Wire schema v1 compliant evidence
    normalized_evidence = models.JSONField(default=dict, blank=True)

    # Scoring & Evaluation Results
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='PENDING')
    total_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    max_possible_score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    grade_letter = models.CharField(max_length=5, blank=True, default='')

    # Real Usage & Cost Telemetry
    pages_processed = models.PositiveIntegerField(default=1)
    grading_cost = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal('0.0000'))

    # Detailed grading response (per question marks, rubric level judgments, rationale)
    grading_details = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default='')

    graded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student_name} ({self.student_id}) - {self.exam.title}"
