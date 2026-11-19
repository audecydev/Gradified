import os
from decimal import Decimal
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'grad_backend.settings')
django.setup()

from django.utils import timezone
from api.models import User, Organization, DemoRequest, Subject, Exam, Submission
from api.grading_service import grade_submission_with_ocr_engine


def seed():
    print("Seeding multi-role Gradified platform data...")

    # 1. Organizations (Firms / Schools)
    greenwood_org, _ = Organization.objects.get_or_create(
        code='GW-2026',
        defaults={
            'name': 'Greenwood Academy of Sciences',
            'contact_email': 'firm@greenwood.edu',
            'contact_person': 'Dr. Elena Rostova',
            'phone': '+1 (555) 234-5678',
            'status': 'APPROVED',
            'plan_tier': 'PRO',
            'cost_per_booklet': Decimal('20.00'),
            'cost_per_page': Decimal('4.00'),
            'monthly_budget_limit': Decimal('40000.00'),
        }
    )

    if greenwood_org.cost_per_booklet < Decimal('1.00'):
        greenwood_org.cost_per_booklet = Decimal('20.00')
        greenwood_org.cost_per_page = Decimal('4.00')
        greenwood_org.monthly_budget_limit = Decimal('40000.00')
        greenwood_org.save()

    springfield_org, _ = Organization.objects.get_or_create(
        code='SP-2026',
        defaults={
            'name': 'Springfield Preparatory Institute',
            'contact_email': 'director@springfield.edu',
            'contact_person': 'Seymour Skinner',
            'phone': '+91 98110 89012',
            'status': 'PENDING',
            'plan_tier': 'STARTER',
            'cost_per_booklet': Decimal('20.00'),
            'cost_per_page': Decimal('4.00'),
            'monthly_budget_limit': Decimal('25000.00'),
        }
    )

    if springfield_org.cost_per_booklet < Decimal('1.00'):
        springfield_org.cost_per_booklet = Decimal('20.00')
        springfield_org.cost_per_page = Decimal('4.00')
        springfield_org.monthly_budget_limit = Decimal('25000.00')
        springfield_org.save()

    # 2. Sample Inbound Contact Sales / Demo Request
    DemoRequest.objects.get_or_create(
        email='dean@stxaviers.edu',
        defaults={
            'organization_name': 'St. Xavier Collegiate Network',
            'contact_name': 'Fr. Thomas Mathew',
            'phone': '+91 98100 44120',
            'expected_booklets': 2500,
            'notes': 'Looking to evaluate 10th & 12th board mock answer booklets using ocr-service.',
            'status': 'PENDING',
        }
    )

    # 3. Role 1: Application Admin
    admin_user, created = User.objects.get_or_create(
        email='admin@gradified.com',
        defaults={
            'username': 'Application Admin',
            'role': 'admin',
            'school_name': 'Gradified Platform Operations',
            'is_verified': True,
            'is_approved': True,
            'is_staff': True,
            'is_superuser': True,
        }
    )
    if created:
        admin_user.set_password('admin123')
        admin_user.save()
        print("Created Role 1 (Admin): admin@gradified.com / admin123")

    # 4. Role 2: Firm / Organization Lead
    firm_user, created = User.objects.get_or_create(
        email='firm@greenwood.edu',
        defaults={
            'username': 'Dr. Elena Rostova',
            'role': 'firm',
            'organization': greenwood_org,
            'school_name': greenwood_org.name,
            'phone': '+1 (555) 234-5678',
            'is_verified': True,
            'is_approved': True,
        }
    )
    if created:
        firm_user.set_password('firm123')
        firm_user.save()
        print("Created Role 2 (Firm): firm@greenwood.edu / firm123")

    # Pending Firm Lead linked to Springfield
    pending_firm, created = User.objects.get_or_create(
        email='director@springfield.edu',
        defaults={
            'username': 'Seymour Skinner',
            'role': 'firm',
            'organization': springfield_org,
            'school_name': springfield_org.name,
            'is_verified': True,
            'is_approved': True,
        }
    )
    if created:
        pending_firm.set_password('spring123')
        pending_firm.save()

    # 5. Role 3: Instructors (Approved + Pending Firm Approval)
    inst_user, created = User.objects.get_or_create(
        email='instructor@greenwood.edu',
        defaults={
            'username': 'Prof. Sarah Jenkins',
            'role': 'instructor',
            'organization': greenwood_org,
            'school_name': greenwood_org.name,
            'phone': '+1 (555) 234-5699',
            'is_verified': True,
            'is_approved': True,
        }
    )
    if created:
        inst_user.set_password('inst123')
        inst_user.save()
        print("Created Role 3 (Instructor): instructor@greenwood.edu / inst123")

    pending_inst, created = User.objects.get_or_create(
        email='pending.instructor@greenwood.edu',
        defaults={
            'username': 'Prof. Marcus Vance',
            'role': 'instructor',
            'organization': greenwood_org,
            'school_name': greenwood_org.name,
            'phone': '+1 (555) 234-5611',
            'is_verified': True,
            'is_approved': False,
        }
    )
    if created:
        pending_inst.set_password('inst123')
        pending_inst.save()

    # 6. Standard Subjects
    subjects = [
        ('Social Studies', 'SST101', 'History, Civics, Geography and Democratic Governance'),
        ('Physics', 'PHY101', 'Classical Mechanics, Thermodynamics and Modern Physics'),
        ('Mathematics', 'MATH101', 'Calculus, Linear Algebra and Applied Discrete Mathematics'),
        ('Chemistry', 'CHEM101', 'Inorganic, Organic, and Physical Chemistry Principles'),
        ('Computer Science', 'CS101', 'Algorithms, Data Structures, and Computational Thinking'),
        ('English Literature', 'ENG101', 'Critical Reading, Literary Analysis and Composition'),
    ]

    subject_objs = {}
    for name, code, desc in subjects:
        sub, _ = Subject.objects.get_or_create(
            name=name,
            defaults={'code': code, 'description': desc}
        )
        subject_objs[name] = sub

    # 7. Sample Exam created by Instructor under Greenwood Org
    physics_sub = subject_objs['Physics']
    exam_questions = [
        {
            "question_id": "Q1",
            "question_text": "Multiple Choice: What is the SI unit of electric potential difference?",
            "type": "CHOICE",
            "max_marks": 5,
            "choice_spec": {
                "correct_option": "B",
                "options": ["A: Ampere (A)", "B: Volt (V)", "C: Ohm (Ω)", "D: Watt (W)"]
            }
        },
        {
            "question_id": "Q2",
            "question_text": "Numeric: A projectile is fired horizontally with initial velocity 20 m/s from a 45m high cliff. Calculate time of flight in seconds (g=10 m/s^2).",
            "type": "NUMERIC",
            "max_marks": 5,
            "numeric_spec": {
                "expected_value": 3.0,
                "tolerance": 0.2
            }
        },
        {
            "question_id": "Q3",
            "question_text": "Semantic / Explanation: Explain why evaporation causes cooling from a molecular kinetics standpoint.",
            "type": "DIRECT",
            "max_marks": 10,
            "model_answer": "Evaporation causes cooling because energetic molecules break intermolecular bonds and leave the liquid surface. This escape reduces the average kinetic energy of the remaining liquid molecules, causing the temperature to decrease.",
            "rubric": {
                "criteria": [
                    {
                        "criterion_id": "kinetic_theory",
                        "description": "Explains loss of highest kinetic energy molecules and subsequent decrease in average kinetic energy and temperature",
                        "levels": [
                            {"level_id": "EXCELLENT", "points": 10.0, "description": "Accurately details molecular kinetic energy distribution and particle escape mechanism"},
                            {"level_id": "GOOD", "points": 7.5, "description": "Explains particle escape with good physical reasoning"},
                            {"level_id": "PARTIAL", "points": 4.0, "description": "Mentions temperature drop or evaporation without complete kinetic basis"},
                            {"level_id": "INSUFFICIENT", "points": 0.0, "description": "Inaccurate or off-topic explanation"}
                        ]
                    }
                ]
            }
        }
    ]

    exam, created = Exam.objects.get_or_create(
        title="Physics Term 1 Final Assessment",
        subject=physics_sub,
        organization=greenwood_org,
        defaults={
            "school": inst_user,
            "total_marks": 20.0,
            "passing_marks": 8.0,
            "status": "ACTIVE",
            "question_paper_text": "Q1: What is the SI unit of electric potential difference?\nQ2: Calculate flight time: h=45m, g=10m/s^2.\nQ3: Explain why evaporation causes cooling.",
            "answer_paper_text": "Q1 Answer: B (Volt)\nQ2 Answer: 3.0 seconds\nQ3 Answer: Evaporation causes cooling because high kinetic energy molecules escape the surface.",
            "questions_data": exam_questions
        }
    )
    if not exam.organization:
        exam.organization = greenwood_org
        exam.save()

    # 8. Sample Exam for Social Studies (History & Democratic Politics)
    sst_sub = subject_objs['Social Studies']
    sst_exam_questions = [
        {
            "question_id": "Q1",
            "question_text": "Multiple Choice: Which of the following was a primary objective of the Treaty of Vienna (1815)?",
            "type": "CHOICE",
            "max_marks": 5,
            "choice_spec": {
                "correct_option": "B",
                "options": [
                    "A: Establish universal adult suffrage across Europe",
                    "B: Restore the Bourbon monarchy and maintain a conservative balance of power",
                    "C: Disband all royal armies in Central Europe",
                    "D: Create a unified German democratic republic"
                ]
            }
        },
        {
            "question_id": "Q2",
            "question_text": "Numeric / Year: In which calendar year was the Constitution of India formally adopted by the Constituent Assembly?",
            "type": "NUMERIC",
            "max_marks": 5,
            "numeric_spec": {
                "expected_value": 1949.0,
                "tolerance": 0.0
            }
        },
        {
            "question_id": "Q3",
            "question_text": "Descriptive / Rubric: Explain the principle of 'Federalism' and how power is distributed between the Union and State governments under the Constitution of India.",
            "type": "DIRECT",
            "max_marks": 10,
            "model_answer": "Federalism is a system of government in which sovereignty is constitutionally divided between a central authority and constituent regional units. Under the Constitution of India, legislative and administrative powers are demarcated into three lists: the Union List for matters of national defense and foreign policy, the State List for local police and public health, and the Concurrent List where both center and states hold jurisdiction.",
            "rubric": {
                "criteria": [
                    {
                        "criterion_id": "federalism_concept",
                        "description": "Defines federalism as constitutional division of powers between center and constituent states",
                        "levels": [
                            {"level_id": "EXCELLENT", "points": 5.0, "description": "Accurately defines federalism and constitutional sovereignty distribution"},
                            {"level_id": "GOOD", "points": 3.75, "description": "Accurate definition with minor conceptual omissions"},
                            {"level_id": "PARTIAL", "points": 2.0, "description": "Basic statement on shared power without full constitutional depth"},
                            {"level_id": "INSUFFICIENT", "points": 0.0, "description": "Inaccurate or off-topic explanation"}
                        ]
                    },
                    {
                        "criterion_id": "three_fold_distribution",
                        "description": "Details the three-fold distribution of legislative subjects across Union, State, and Concurrent Lists",
                        "levels": [
                            {"level_id": "EXCELLENT", "points": 5.0, "description": "Explicitly names and describes Union List, State List, and Concurrent List jurisdictions"},
                            {"level_id": "GOOD", "points": 3.75, "description": "Details lists with minor omission of jurisdiction details"},
                            {"level_id": "PARTIAL", "points": 2.0, "description": "Vague mention of center vs state laws without naming the three lists"},
                            {"level_id": "INSUFFICIENT", "points": 0.0, "description": "Inaccurate explanation"}
                        ]
                    }
                ]
            }
        }
    ]

    sst_exam, _ = Exam.objects.get_or_create(
        title="Class 10 Social Studies: Nationalism & Democratic Governance",
        subject=sst_sub,
        organization=greenwood_org,
        defaults={
            "school": inst_user,
            "total_marks": 20.0,
            "passing_marks": 8.0,
            "status": "ACTIVE",
            "question_paper_text": "Q1: What was a key objective of the Treaty of Vienna (1815)?\nQ2: In which year was the Constitution of India formally adopted?\nQ3: Explain the principle of Federalism and how power is shared between the Union and State governments under the Constitution of India.",
            "answer_paper_text": "Q1 Answer: B (Restore the Bourbon monarchy)\nQ2 Answer: 1949\nQ3 Answer: Federalism divides sovereignty between central and state governments using the Union List, State List, and Concurrent List.",
            "questions_data": sst_exam_questions
        }
    )
    if not sst_exam.organization:
        sst_exam.organization = greenwood_org
        sst_exam.save()

    # Class 6 Social Science Examination (Exploring Society - 80 Marks, 37 Questions)
    spec_path = os.path.join(os.path.dirname(__file__), 'media', '6th_ss_questions_spec.json')
    if os.path.exists(spec_path):
        with open(spec_path, 'r', encoding='utf-8') as f:
            class6_questions = json.load(f)

        Exam.objects.get_or_create(
            title="Class 6 Social Science: Exploring Society Mid-Term Examination",
            subject=sst_sub,
            organization=greenwood_org,
            defaults={
                "school": inst_user,
                "total_marks": Decimal("80.00"),
                "passing_marks": Decimal("32.00"),
                "status": "ACTIVE",
                "questions_data": class6_questions,
            }
        )

    print("Initial system configuration and standard subjects provisioned successfully!")


if __name__ == '__main__':
    seed()
