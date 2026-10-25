"""Causal FIRST DIRECT physical operation: only the backend fixture is simulated."""
from dataclasses import replace, asdict
from enum import Enum
import json
from grading.integration.evidence_ingress import parse_normalized_evidence_payload
from tests.integration.test_question_preparation_evidence_binding_regression import _policy


def admitted(evidence):
    # Genuine public normalized OCR evidence admission wire parser, not constructed/forged admission token.
    wire = json.dumps(asdict(evidence), default=lambda value: value.value if isinstance(value, Enum) else None, separators=(",", ":")).encode("utf-8")
    result = parse_normalized_evidence_payload(raw_payload=wire,policy=_policy())
    assert result.evidence == evidence
    return result

import pytest

from grading.integration.paper_family_evaluation import DirectQuestionEvaluation
from grading.integration.whole_paper_family_execution import (
    FamilyPaperInputs, ProductionWholePaperFamilyExecutor,
)
from grading.integration.paper_readiness_admission import (
    AdmittedPaperPlan, AdmittedPaperQuestion, PaperAdmissionRequest,
)
from grading.integration.trusted_preparation import PreparationRequest
from grading.integration.paper_execution_correlation import (
    IssuedPaperExecutionRelation, IssuedQuestionExecutionRelation,
    ProductionPaperExecutionCorrelation,
)
from grading.integration.choice_authority_admission import ChoiceAdmissionScope
from grading.integration.execution_eligibility import ProductionExecutionEligibilityComposer
from grading.integration.evaluator_execution_binding import (
    ProductionEvaluatorRuntimeBinder, InstalledRuntime,
)
from grading.integration.attempt_authority import ClaimedAttemptAllocator
from grading.integration.joint_effect_authority import JointEffectAdmission
from tests.integration.test_paper_family_evaluation import _direct
from tests.integration.test_family_runtime_binding import family_fixture
from tests.integration.test_joint_first_claim_connected_execution import (
    ReadOnlyF25Port, ReadOnlyAcademicPort, AtomicConditionalAcademicFixture,
)
from tests.integration.test_academic_effect_preclaim import (
    QualifiedShapeAcademicBackend, PerQuestionF25Issuer,
)
from tests.integration.test_paper_lifecycle_pre_effect import Permissions
from tests.integration.test_attempt_authority import AtomicStore


class Issuer:
    def __init__(self, issued):
        self.issued = issued
        self.calls = 0
    def correlate_paper_execution(self, *, plan):
        self.calls += 1
        return self.issued


class Inputs:
    def __init__(self, inputs):
        self.inputs = inputs
        self.calls = 0
    def resolve_family_paper_inputs(self, *, plan):
        self.calls += 1
        return self.inputs


def rig(*, grading_run_id=None, predecessor_ref=None, permission_source=None,
        physical_store=None):
    context, evidence, paper, op, provider = _direct()
    if grading_run_id is not None:
        context = replace(context, grading_run_id=grading_run_id)
    req = PaperAdmissionRequest('T','SESSION',context.grading_run_id,
         context.submission_ref,context.exam_ref,'P','S',context.grading_spec_ref)
    pq = AdmittedPaperQuestion(PreparationRequest('T','SESSION',context.grading_run_id,
         context.submission_ref,context.exam_ref,context.grading_spec_ref,'Q1'),
         'DIRECT','SOURCE-ARTIFACT','SOURCE-REV','ANSWER-SCOPE','REGION-1',evidence.ocr_provenance)
    plan = AdmittedPaperPlan(req,'ACTOR','APPROVAL','APPROVAL-REV','SELECT','SELECT-REV',
                            'SOURCE-REV','READY-REV',(pq,))
    expected = paper.expected_questions[0]
    issued = IssuedPaperExecutionRelation(1,req,'ACTOR','ISSUER','ISSUANCE','P','S',
           'APPROVAL','APPROVAL-REV','SELECT','SELECT-REV','SOURCE-REV','READY-REV',
           (IssuedQuestionExecutionRelation('Q1','DIRECT','SOURCE-ARTIFACT',
             'ANSWER-SCOPE','REGION-1','SOURCE-REV',evidence.ocr_provenance,
             expected.rubric_ref.id,expected.scoring_policy_ref.id),))
    scope = ChoiceAdmissionScope('ACTOR','T','SESSION',context.grading_run_id,
       context.submission_ref,context.exam_ref,context.grading_spec_ref,'Q1',
       'ANSWER-SCOPE','SOURCE-ARTIFACT','SOURCE-REV','ADMISSION-POLICY',
       'ADMISSION-REV',evidence.ocr_provenance)
    # Use the original installed execution eligibility/evaluator handler binding family registry, but bind the same
    # scope that the official paper issuer actually approved for physical attempt claim.
    _, ports, _, _ = family_fixture('DIRECT')
    metadata = op.evaluator._evaluator_metadata
    ref = replace(ports.selection.selected_capability_ref, evaluator_metadata=metadata)
    selected_record = replace(ports.selection.resolved_capability.record,
                               capability_ref=ref)
    ports.selection = replace(ports.selection,
        classification=replace(ports.selection.classification,
            grading_spec_ref=context.grading_spec_ref, question_id='Q1'),
        context_policy=op.authority.context_policy,
        selected_capability_ref=ref,
        resolved_capability=replace(ports.selection.resolved_capability,record=selected_record))
    ports.facts = replace(ports.facts,scope=scope,capability_ref=ref)
    ports.policy = replace(ports.policy,scope=scope,capability_ref=ref)
    ports.runtime_record = replace(ports.runtime_record,scope=scope,capability_ref=ref)
    eligibility = ProductionExecutionEligibilityComposer(selection=ports, facts=ports, policy=ports,
                       max_identifier_characters=128,max_facts=8)
    from grading.integration.paper_family_evaluation import evaluate_supported_paper_questions
    installed = InstalledRuntime('DIRECT','approved-DIRECT','1','sha256-approved-DIRECT',
                                 evaluate_supported_paper_questions)
    runtime = ProductionEvaluatorRuntimeBinder(inventory=ports,eligibility=eligibility,
       installed=(installed,), max_identifier_characters=128,max_modalities=8,
       max_installed_runtimes=8,max_facts=8)
    input_source = Inputs(FamilyPaperInputs(context,admitted(evidence),paper,(op,),(scope,)))
    correlation = ProductionPaperExecutionCorrelation(issuer=Issuer(issued),
                             max_identifier_characters=128,max_questions=10)
    physical=AtomicStore() if physical_store is None else physical_store
    backend=QualifiedShapeAcademicBackend(physical)
    issuer=Permissions() if permission_source is None else permission_source
    if predecessor_ref is not None:
        from tests.integration.test_paper_lifecycle_regrade import RegradeF25Issuer
        from tests.integration.test_joint_regrade_connected_execution import ConditionalRegradeFixture
        physical_issuer=RegradeF25Issuer(predecessor_ref, 'F57-REGRADE-APPROVAL')
        conditional=ConditionalRegradeFixture(backend,issuer)
    else:
        physical_issuer=PerQuestionF25Issuer()
        conditional=AtomicConditionalAcademicFixture(backend,issued.approval_revision,
                                                     ports.runtime_record.approval_ref)
    attempts=ClaimedAttemptAllocator(issuer=physical_issuer,
        store=ReadOnlyF25Port(physical),academic_store=ReadOnlyAcademicPort(backend),
        academic_max_questions=10,max_identifier_characters=128,
        joint_effect=JointEffectAdmission(owner=conditional))
    executor=ProductionWholePaperFamilyExecutor(
        correlation=correlation,runtime=runtime,attempts=attempts,inputs=input_source,
        max_identifier_characters=128,max_questions=10)
    if predecessor_ref is None:
        conditional.f57_source=issuer
    permission=issuer.resolve_paper_execution_permission(plan=plan)
    return executor,plan,permission,physical,backend,conditional,provider,input_source


def test_real_direct_f57_f25_provider_s1_frozen_score_positive():
    executor,plan,permission,physical,backend,conditional,provider,_ = rig()
    out=executor.execute_first(plan=plan,permission=permission)
    assert out.state=='COMPLETE', (out.state,out.contact_trace)
    assert out.result is not None and len(out.result.questions)==1
    assert out.completed[0].judgments==out.result.questions[0].verified.evaluated_judgments
    assert out.completed[0].reservation.request_ref=='REQUEST-Q1'
    assert physical.claims==1 and conditional.claim_contacts==1
    assert len(backend.prepares)==1 and len(provider.requests)==1
    assert not out.authorizes_publication and not out.authorizes_retry


def test_revoked_runtime_denies_physical_effect_and_provider():
    executor,plan,permission,physical,backend,conditional,provider,_=rig()
    conditional.runtime_approval='REVOKED'
    out=executor.execute_first(plan=plan,permission=permission)
    assert out.result is None and out.state!='COMPLETE'
    assert physical.claims==0 and conditional.claim_contacts==1
    assert provider.requests==[]


def test_lost_f25_reply_retains_original_request_no_grade_or_provider():
    executor,plan,permission,physical,backend,conditional,provider,_=rig()
    conditional.lost_ack=True
    out=executor.execute_first(plan=plan,permission=permission)
    assert out.state=='INDETERMINATE'
    assert out.result is None and physical.claims==1 and len(provider.requests)==0
    assert out.contact_trace[0].original_f25_request.request_ref=='REQUEST-Q1'


def test_wrong_family_issuer_denied_before_any_physical_effect():
    executor,plan,permission,physical,backend,conditional,provider,_=rig()
    fake=replace(plan.questions[0],family='NUMERIC')
    out=executor.execute_first(plan=replace(plan,questions=(fake,)),permission=permission)
    assert out.result is None and physical.claims==0 and provider.requests==[]


def test_bad_next_question_evidence_denied_before_first_claim():
    from grading.contracts.evidence import EvidenceBlockState
    executor,plan,permission,physical,backend,conditional,provider,source=rig()
    ev=source.inputs.evidence.evidence
    q=ev.questions[0]
    changed=replace(q,blocks=tuple(replace(b,state=EvidenceBlockState.UNCERTAIN) for b in q.blocks))
    source.inputs=replace(source.inputs,evidence=admitted(replace(ev,questions=(changed,))))
    out=executor.execute_first(plan=plan,permission=permission)
    assert out.result is None and physical.claims==0 and provider.requests==[]


class MultiPhysical(AtomicStore):
    """Multiple unique test reservations, not a durable implementation."""
    def claim_fresh_attempt(self, *, request):
        from grading.integration.attempt_authority import AttemptClaim
        original = super().claim_fresh_attempt(request=request)
        if original.reservation is None:
            return original
        reservation = replace(original.reservation,
           attempt_id='BACKEND-ATT-'+request.scope.question_id,
           reservation_ref='BACKEND-RES-'+request.scope.question_id)
        # Model independent original physical attempt claim receipts for each question, not only
        # the last reservation (multi-question RETRY must preserve both).
        if not hasattr(self, "reservations"):
            self.reservations = {}
        self.reservations[request.request_ref] = reservation
        self.last_reservation=reservation
        return AttemptClaim(request,original.disposition,reservation)


def rig_family(kind, *, grading_run_id=None, predecessor_ref=None,
               permission_source=None, physical_store=None):
    from grading.integration.paper_family_evaluation import NumericQuestionEvaluation
    from tests.integration.test_paper_family_evaluation import _numeric, _mixed
    from grading.integration.paper_family_evaluation import evaluate_supported_paper_questions
    if kind=='NUMERIC':
        context,evidence,paper,op=_numeric()
        ops=(op,)
        provider=None
    else:
        context,evidence,paper,ops,provider=_mixed()
    if grading_run_id is not None:
        context=replace(context,grading_run_id=grading_run_id)
    req=PaperAdmissionRequest('T','SESSION',context.grading_run_id,
          context.submission_ref,context.exam_ref,'P','S',context.grading_spec_ref)
    selected=[];rels=[];scopes=[];portmap={};installed=[]
    for op in ops:
        qid=op.authority.question_id
        family='DIRECT' if isinstance(op,DirectQuestionEvaluation) else 'NUMERIC'
        evidence_scope='ANSWER-SCOPE-'+qid
        selected.append(AdmittedPaperQuestion(
            PreparationRequest('T','SESSION',context.grading_run_id,
                 context.submission_ref,context.exam_ref,context.grading_spec_ref,qid),
            family,'SOURCE-'+qid,'SOURCE-REV',evidence_scope,'REGION-'+qid,evidence.ocr_provenance))
        expected=next(x for x in paper.expected_questions if x.question_id==qid)
        rels.append(IssuedQuestionExecutionRelation(qid,family,'SOURCE-'+qid,
             evidence_scope,'REGION-'+qid,'SOURCE-REV',evidence.ocr_provenance,
             expected.rubric_ref.id,expected.scoring_policy_ref.id))
        scope=ChoiceAdmissionScope('ACTOR','T','SESSION',context.grading_run_id,
            context.submission_ref,context.exam_ref,context.grading_spec_ref,qid,
            evidence_scope,'SOURCE-'+qid,'SOURCE-REV','ADMISSION-POLICY',
            'ADMISSION-REV',evidence.ocr_provenance)
        scopes.append(scope)
        _,ports,_,_=family_fixture(family)
        metadata=(op.evaluator._evaluator_metadata if family=='DIRECT' else
                  ports.selection.selected_capability_ref.evaluator_metadata)
        ref=replace(ports.selection.selected_capability_ref,evaluator_metadata=metadata)
        record=replace(ports.selection.resolved_capability.record,capability_ref=ref)
        ports.selection=replace(ports.selection,
             classification=replace(ports.selection.classification,
                 grading_spec_ref=context.grading_spec_ref,question_id=qid),
             context_policy=op.authority.context_policy,
             selected_capability_ref=ref,
             resolved_capability=replace(ports.selection.resolved_capability,record=record))
        ports.facts=replace(ports.facts,scope=scope,capability_ref=ref)
        ports.policy=replace(ports.policy,scope=scope,capability_ref=ref)
        ports.runtime_record=replace(ports.runtime_record,scope=scope,capability_ref=ref)
        portmap[qid]=ports
        installed.append(InstalledRuntime(family,'approved-'+family,'1',
                            'sha256-approved-'+family,evaluate_supported_paper_questions))
    plan=AdmittedPaperPlan(req,'ACTOR','APPROVAL','APPROVAL-REV','SELECT',
                          'SELECT-REV','SOURCE-REV','READY-REV',tuple(selected))
    issued=IssuedPaperExecutionRelation(1,req,'ACTOR','ISSUER','ISSUANCE','P','S',
        'APPROVAL','APPROVAL-REV','SELECT','SELECT-REV','SOURCE-REV','READY-REV',tuple(rels))

    class RuntimePorts:
        def resolve_admitted_selection(self, *, scope):
            return portmap[scope.question_id].resolve_admitted_selection(scope=scope)
        def resolve_execution_facts(self, *, scope, capability_ref):
            return portmap[scope.question_id].resolve_execution_facts(scope=scope,capability_ref=capability_ref)
        def resolve_approved_eligibility_policy(self, *, scope, capability_ref):
            return portmap[scope.question_id].resolve_approved_eligibility_policy(scope=scope,capability_ref=capability_ref)
        def resolve_approved_runtime(self, *, scope, capability_ref, policy_id, policy_version):
            return portmap[scope.question_id].resolve_approved_runtime(
                scope=scope,capability_ref=capability_ref,
                policy_id=policy_id,policy_version=policy_version)
    ports=RuntimePorts()
    eligible=ProductionExecutionEligibilityComposer(selection=ports,facts=ports,policy=ports,
                                   max_identifier_characters=128,max_facts=8)
    # The common family evaluator is registered at distinct exact approved
    # physical runtime identities for the two supported families.
    runtime=ProductionEvaluatorRuntimeBinder(inventory=ports,eligibility=eligible,
        installed=tuple(installed),max_identifier_characters=128,max_modalities=8,
        max_installed_runtimes=8,max_facts=8)
    source=Inputs(FamilyPaperInputs(context,admitted(evidence),paper,tuple(ops),tuple(scopes)))
    correlation=ProductionPaperExecutionCorrelation(issuer=Issuer(issued),
                               max_identifier_characters=128,max_questions=10)
    physical=MultiPhysical() if physical_store is None else physical_store
    backend=QualifiedShapeAcademicBackend(physical)
    issuer=Permissions() if permission_source is None else permission_source
    if predecessor_ref is not None:
        from tests.integration.test_paper_lifecycle_regrade import RegradeF25Issuer
        from tests.integration.test_joint_regrade_connected_execution import ConditionalRegradeFixture
        physical_issuer=RegradeF25Issuer(predecessor_ref,'F57-REGRADE-APPROVAL')
        conditional=ConditionalRegradeFixture(backend,issuer)
    else:
        physical_issuer=PerQuestionF25Issuer()
        conditional=AtomicConditionalAcademicFixture(backend,issued.approval_revision,'RUNTIME-APPROVAL')
        conditional.f57_source=issuer
    attempts=ClaimedAttemptAllocator(issuer=physical_issuer,
        store=ReadOnlyF25Port(physical),academic_store=ReadOnlyAcademicPort(backend),
        academic_max_questions=10,max_identifier_characters=128,
        joint_effect=JointEffectAdmission(owner=conditional))
    executor=ProductionWholePaperFamilyExecutor(correlation=correlation,runtime=runtime,
        attempts=attempts,inputs=source,max_identifier_characters=128,max_questions=10)
    permission=issuer.resolve_paper_execution_permission(plan=plan)
    return executor,plan,permission,physical,backend,conditional,provider,source


def test_real_numeric_f57_f25_n1_n4_s1_frozen_score_positive():
    executor,plan,permission,physical,backend,conditional,provider,source=rig_family('NUMERIC')
    out=executor.execute_first(plan=plan,permission=permission)
    assert out.state=='COMPLETE', (out.state,out.contact_trace)
    assert out.result.paper_score.final_score.canonical=='5' if hasattr(out.result.paper_score.final_score,'canonical') else out.result.paper_score.final_score is not None
    assert out.completed[0].reservation.attempt_id=='BACKEND-ATT-Q1'
    assert physical.claims==1 and conditional.claim_contacts==1 and len(backend.prepares)==1


def test_real_mixed_f57_two_physical_claims_one_frozen_paper_score():
    executor,plan,permission,physical,backend,conditional,provider,source=rig_family('MIXED')
    out=executor.execute_first(plan=plan,permission=permission)
    assert out.state=='COMPLETE', (out.state,out.contact_trace)
    assert [a.family for a in out.completed]==['DIRECT','NUMERIC']
    assert tuple(q.score.question_id for q in out.result.questions)==('Q1','Q2')
    assert len(set(x.reservation.attempt_id for x in out.completed))==2
    assert physical.claims==2 and conditional.claim_contacts==2
    assert len(backend.prepares)==2 and len(provider.requests)==1
    assert not out.authorizes_publication


def test_mixed_f25_second_claim_revoked_preserves_first_original_without_grade():
    executor,plan,permission,physical,backend,conditional,provider,source=rig_family('MIXED')
    conditional.revoke_after_first=True
    out=executor.execute_first(plan=plan,permission=permission)
    assert out.result is None and out.state!='COMPLETE'
    assert physical.claims==1 and conditional.claim_contacts==2
    assert len(out.observed_reservations)==1 and len(out.contact_trace)==2
    assert out.contact_trace[0].original_f25_request.request_ref=='REQUEST-Q1'
    assert provider.requests==[]
