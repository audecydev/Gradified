from rest_framework import serializers
from .models import User, Organization, DemoRequest, Subject, Exam, Submission


class OrganizationSerializer(serializers.ModelSerializer):
    instructors_count = serializers.SerializerMethodField()
    pending_instructors_count = serializers.SerializerMethodField()
    exams_count = serializers.SerializerMethodField()
    submissions_count = serializers.SerializerMethodField()
    total_cost = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            'id', 'name', 'code', 'contact_email', 'contact_person', 'phone',
            'status', 'plan_tier', 'cost_per_booklet', 'cost_per_page', 'monthly_budget_limit',
            'instructors_count', 'pending_instructors_count', 'exams_count',
            'submissions_count', 'total_cost', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'code', 'created_at', 'updated_at']

    def get_instructors_count(self, obj):
        return obj.members.filter(role='instructor').count()

    def get_pending_instructors_count(self, obj):
        return obj.members.filter(role='instructor', is_approved=False).count()

    def get_exams_count(self, obj):
        return obj.exams.count()

    def get_submissions_count(self, obj):
        return Submission.objects.filter(exam__organization=obj).count()

    def get_total_cost(self, obj):
        subs = Submission.objects.filter(exam__organization=obj)
        total = sum(float(s.grading_cost or 0) for s in subs)
        return round(total, 2)


class UserSerializer(serializers.ModelSerializer):
    organization_name = serializers.SerializerMethodField()
    organization_code = serializers.SerializerMethodField()
    organization_status = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'role', 'organization',
            'organization_name', 'organization_code', 'organization_status',
            'school_name', 'phone', 'is_verified', 'is_approved', 'created_at'
        ]
        read_only_fields = ['id', 'is_verified', 'created_at']

    def get_organization_name(self, obj):
        return obj.organization.name if obj.organization else (obj.school_name or '')

    def get_organization_code(self, obj):
        return obj.organization.code if obj.organization else ''

    def get_organization_status(self, obj):
        if obj.role == 'admin':
            return 'APPROVED'
        return obj.organization.status if obj.organization else 'PENDING'


class DemoRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = DemoRequest
        fields = [
            'id', 'organization_name', 'contact_name', 'email', 'phone',
            'expected_booklets', 'notes', 'status', 'organization', 'created_at'
        ]
        read_only_fields = ['id', 'organization', 'created_at']


class SubjectSerializer(serializers.ModelSerializer):
    exams_count = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = ['id', 'name', 'code', 'description', 'organization', 'school', 'exams_count', 'created_at']
        read_only_fields = ['id', 'organization', 'school', 'created_at']

    def get_exams_count(self, obj):
        return obj.exams.count()


class ExamSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    organization_name = serializers.SerializerMethodField()
    school_name = serializers.SerializerMethodField()
    instructor_name = serializers.SerializerMethodField()
    submissions_count = serializers.SerializerMethodField()
    average_score = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = [
            'id', 'title', 'subject', 'subject_name', 'organization', 'organization_name',
            'school', 'school_name', 'instructor_name',
            'total_marks', 'passing_marks', 'status',
            'question_paper_file', 'question_paper_text',
            'answer_paper_file', 'answer_paper_text',
            'questions_data', 'submissions_count', 'average_score',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'school', 'created_at', 'updated_at']

    def get_organization_name(self, obj):
        return obj.organization.name if obj.organization else (obj.school.school_name or '')

    def get_school_name(self, obj):
        return obj.organization.name if obj.organization else (obj.school.school_name or '')

    def get_instructor_name(self, obj):
        return obj.school.username or obj.school.email

    def get_submissions_count(self, obj):
        return obj.submissions.count()

    def get_average_score(self, obj):
        graded = obj.submissions.filter(status='GRADED', total_score__isnull=False)
        if not graded.exists():
            return None
        total = sum(s.total_score for s in graded)
        return round(float(total / graded.count()), 2)


class SubmissionListSerializer(serializers.ModelSerializer):
    exam_title = serializers.CharField(source='exam.title', read_only=True)
    subject_name = serializers.CharField(source='exam.subject.name', read_only=True)
    instructor_name = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = [
            'id', 'exam', 'exam_title', 'subject_name', 'instructor_name',
            'student_name', 'student_id', 'submission_ref', 'status',
            'total_score', 'max_possible_score', 'percentage', 'grade_letter',
            'pages_processed', 'grading_cost', 'created_at', 'graded_at'
        ]

    def get_instructor_name(self, obj):
        actor = obj.submitted_by or obj.exam.school
        return actor.username or actor.email if actor else ''


class SubmissionDetailSerializer(serializers.ModelSerializer):
    exam_title = serializers.CharField(source='exam.title', read_only=True)
    subject_name = serializers.CharField(source='exam.subject.name', read_only=True)
    questions_data = serializers.JSONField(source='exam.questions_data', read_only=True)

    class Meta:
        model = Submission
        fields = [
            'id', 'exam', 'exam_title', 'subject_name', 'student_name', 'student_id',
            'submission_ref', 'answer_sheet_file', 'raw_ocr_text', 'normalized_evidence',
            'status', 'total_score', 'max_possible_score', 'percentage', 'grade_letter',
            'pages_processed', 'grading_cost', 'grading_details', 'error_message',
            'questions_data', 'created_at', 'graded_at'
        ]
