from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from .models import User, Organization, DemoRequest, Subject, Exam, Submission


class MultiRolePlatformTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_contact_sales_and_admin_org_approval(self):
        # 1. Public visitor submits Contact Sales demo request
        sales_res = self.client.post('/api/contact-sales/', {
            'organization_name': 'Beacon Academy',
            'contact_name': 'Prof. Ozpin',
            'email': 'headmaster@beacon.edu',
            'phone': '+1 555 0199',
            'expected_booklets': 1200,
        }, format='json')
        self.assertEqual(sales_res.status_code, status.HTTP_201_CREATED)
        demo_id = sales_res.data['request']['id']

        # 2. Role 1 (Application Admin) onboards and approves organization
        admin = User.objects.create_superuser('admin@board.gov', 'adminpass', username='App Admin')
        self.client.force_authenticate(user=admin)

        onboard_res = self.client.post('/api/admin/onboard-school/', {
            'school_name': 'Beacon Academy',
            'email': 'firm@beacon.edu',
            'password': 'beaconpass123',
            'contact_person': 'Prof. Ozpin',
            'auto_verify': True,
            'demo_request_id': demo_id,
        }, format='json')
        self.assertEqual(onboard_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(onboard_res.data['organization']['status'], 'APPROVED')

        demo_req = DemoRequest.objects.get(pk=demo_id)
        self.assertEqual(demo_req.status, 'ONBOARDED')

        stats_res = self.client.get('/api/admin/stats/')
        self.assertEqual(stats_res.status_code, status.HTTP_200_OK)
        self.assertEqual(stats_res.data['approved_orgs'], 1)

    def test_firm_signup_verify_and_admin_approval_flow(self):
        # Mismatched confirm password rejected
        mismatch_res = self.client.post('/api/auth/signup/', {
            'email': 'owner@newfirm.edu',
            'password': 'password123',
            'confirm_password': 'differentpassword',
            'username': 'Firm Lead',
            'school_name': 'New Horizon Prep',
        }, format='json')
        self.assertEqual(mismatch_res.status_code, status.HTTP_400_BAD_REQUEST)

        # Signup defaults to 'firm' with PENDING org
        res = self.client.post('/api/auth/signup/', {
            'email': 'owner@newfirm.edu',
            'password': 'password123',
            'confirm_password': 'password123',
            'username': 'Firm Lead',
            'school_name': 'New Horizon Prep',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['role'], 'firm')
        self.assertEqual(res.data['organization_status'], 'PENDING')
        code = res.data['verification_code']

        verify_res = self.client.post('/api/auth/verify-email/', {
            'email': 'owner@newfirm.edu',
            'code': code
        }, format='json')
        self.assertEqual(verify_res.status_code, status.HTTP_200_OK)
        self.assertTrue(verify_res.data['user']['is_verified'])
        self.assertEqual(verify_res.data['user']['organization_status'], 'PENDING')

    def test_firm_instructor_approval_usage_cost_and_ocr_grading(self):
        org = Organization.objects.create(
            name='Clarke Academy',
            status='APPROVED',
            cost_per_booklet=Decimal('20.00'),
            cost_per_page=Decimal('4.00'),
            monthly_budget_limit=Decimal('20000.00'),
        )
        firm = User.objects.create_user(
            email='director@clarke.edu',
            password='firm123',
            username='Director Clarke',
            role='firm',
            organization=org,
            school_name=org.name,
            is_verified=True,
            is_approved=True,
        )
        instructor = User.objects.create_user(
            email='inst@clarke.edu',
            password='inst123',
            username='Instructor Ada',
            role='instructor',
            organization=org,
            school_name=org.name,
            is_verified=True,
            is_approved=False,
        )

        # Unapproved instructor cannot access subjects/exams
        self.client.force_authenticate(user=instructor)
        blocked_res = self.client.get('/api/subjects/')
        self.assertEqual(blocked_res.status_code, status.HTTP_403_FORBIDDEN)

        # Role 2 (Firm) approves instructor
        self.client.force_authenticate(user=firm)
        approve_res = self.client.patch(f'/api/firm/instructors/{instructor.id}/approve/', {
            'is_approved': True,
        }, format='json')
        self.assertEqual(approve_res.status_code, status.HTTP_200_OK)
        self.assertTrue(approve_res.data['is_approved'])

        # Role 3 (Instructor) creates subject, exam, and grades booklet via ocr-service
        instructor.refresh_from_db()
        self.client.force_authenticate(user=instructor)
        sub_res = self.client.post('/api/subjects/', {'name': 'Physics', 'code': 'PHY101'}, format='json')
        self.assertEqual(sub_res.status_code, status.HTTP_201_CREATED)
        subject_id = sub_res.data['id']

        exam_questions = [
            {
                "question_id": "Q1",
                "question_text": "What is the unit of force?",
                "type": "CHOICE",
                "max_marks": 5,
                "choice_spec": {"correct_option": "C", "options": ["A: Joule", "B: Pascal", "C: Newton"]}
            },
            {
                "question_id": "Q2",
                "question_text": "Calculate momentum: m=10kg, v=5 m/s.",
                "type": "NUMERIC",
                "max_marks": 5,
                "numeric_spec": {"expected_value": 50.0, "tolerance": 0.5}
            }
        ]
        exam_res = self.client.post('/api/exams/', {
            'title': 'Classical Mechanics Test',
            'subject_id': subject_id,
            'total_marks': 10,
            'passing_marks': 4,
            'questions_data': exam_questions,
        }, format='json')
        self.assertEqual(exam_res.status_code, status.HTTP_201_CREATED)
        exam_id = exam_res.data['id']

        sub_grade_res = self.client.post(f'/api/exams/{exam_id}/submissions/', {
            'student_name': 'Jane Doe',
            'student_id': 'STU-007',
            'raw_ocr_text': 'Q1: Option C\nQ2: 50',
            'auto_grade': True,
        }, format='json')
        self.assertEqual(sub_grade_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(sub_grade_res.data['status'], 'GRADED')
        self.assertEqual(float(sub_grade_res.data['total_score']), 10.0)
        self.assertGreater(float(sub_grade_res.data['grading_cost']), 0.0)

        # Role 2 (Firm) inspects overall results + real cost usage
        self.client.force_authenticate(user=firm)
        overview_res = self.client.get('/api/firm/overview/')
        self.assertEqual(overview_res.status_code, status.HTTP_200_OK)
        self.assertEqual(overview_res.data['metrics']['booklets_processed'], 1)
        self.assertEqual(overview_res.data['metrics']['currency'], 'INR')
        self.assertEqual(float(overview_res.data['metrics']['total_cost']), 24.00)

    def test_ocr_service_failure_isolation_and_timeout_resilience(self):
        from unittest.mock import patch
        import requests

        org = Organization.objects.create(name='Isolation High', status='APPROVED')
        instructor = User.objects.create_user(
            email='teacher@isolation.edu',
            password='pass',
            role='instructor',
            organization=org,
            is_verified=True,
            is_approved=True,
        )
        self.client.force_authenticate(user=instructor)

        subject = Subject.objects.create(name='Chemistry', code='CHM101')
        exam = Exam.objects.create(
            title='Organic Chemistry Midterm',
            subject=subject,
            organization=org,
            school=instructor,
            total_marks=Decimal('10.0'),
            passing_marks=Decimal('4.0'),
            questions_data=[{'question_id': 'Q1', 'type': 'DIRECT', 'max_marks': 10}]
        )

        # Simulate OCR microservice failing with timeout across retries
        with patch('requests.post') as mock_post, \
             patch.dict('os.environ', {'OCR_SERVICE_URL': 'http://ocr.local/api', 'OCR_MAX_RETRIES': '1'}):
            mock_post.side_effect = requests.exceptions.Timeout("Read timeout on OCR model computation")

            # Upload scanned PDF binary bytes
            from django.core.files.uploadedfile import SimpleUploadedFile
            fake_pdf = SimpleUploadedFile("booklet.pdf", b"%PDF-1.4\n1 0 obj\n<<>>\nstream\nfake_image_stream\nendstream\nendobj\n", content_type="application/pdf")

            res = self.client.post(f'/api/exams/{exam.id}/submissions/?sync=true', {
                'student_name': 'Test Student',
                'student_id': 'ISO-01',
                'answer_sheet_file': fake_pdf,
                'auto_grade': True,
            }, format='multipart')

            # Web application must return 201 Created and NOT crash or reset connection
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)
            sub_id = res.data['id']
            sub = Submission.objects.get(pk=sub_id)

            # Failure must be isolated to the OCR service with FAILED status and diagnostic message
            self.assertEqual(sub.status, 'FAILED')
            self.assertIn('OCR', sub.error_message)

            # Web application remains fully healthy and operational for other requests
            exams_res = self.client.get('/api/exams/')
            self.assertEqual(exams_res.status_code, status.HTTP_200_OK)
